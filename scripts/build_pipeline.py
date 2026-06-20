"""Pipeline orchestrator: discover sources → snapshot/normalize → merge → build.

CLI usage:
    uv run python -m scripts.build_pipeline \
        --sources sources --work /tmp/work --out site \
        --country nl --data-version 2026.06.19 \
        [--smoke] [--exclude osm,museum-nl]

In smoke mode, each source's fixture file is used directly instead of fetching.
"""

from __future__ import annotations

import argparse
import importlib
import os
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

from data_pipeline.build import build_site
from data_pipeline.manifest import load_manifest, package_dir
from data_pipeline.merge import run_merge

# Map source id → fixture filename (relative to tests/fixtures/).
_SMOKE_FIXTURES: dict[str, str] = {
    "wikidata-museums": "wikidata_museums_response.json",
    "rce-musea": "rce_musea_response.json",
    "den-haag-speeltuinen": "den_haag_response.json",
    "eindhoven-speeltuinen": "eindhoven_response.json",
    "osm": "osm_sample.osm",
}


def run(
    sources_dir: Path,
    work_dir: Path,
    out_dir: Path,
    country: str,
    data_version: str,
    only_runtime: str = "github-action",
    include_ids: set[str] | None = None,
    exclude_ids: set[str] | None = None,
    prebuilt_sources: dict[str, Path] | None = None,
    smoke: bool = False,
) -> dict:
    """Run the full pipeline and return the site manifest dict."""
    work_dir.mkdir(parents=True, exist_ok=True)
    out_dir.mkdir(parents=True, exist_ok=True)

    # Discover source manifests.
    manifest_paths = sorted(sources_dir.glob("*/manifest.yaml"))
    manifest_paths = [p for p in manifest_paths if p.parent.name != "_template"]

    fetched_at = datetime.now(timezone.utc)

    ndjson_paths: list[Path] = []
    included_source_ids: list[str] = []

    for manifest_path in manifest_paths:
        manifest = load_manifest(manifest_path)

        prebuilt = (prebuilt_sources or {}).get(manifest.id)

        # Filter by runtime unless an explicitly supplied normalized stream is used.
        if manifest.runtime != only_runtime and prebuilt is None:
            continue

        # Apply include/exclude filters.
        if include_ids is not None and manifest.id not in include_ids:
            continue
        if exclude_ids is not None and manifest.id in exclude_ids:
            continue

        ndjson_path = work_dir / f"{manifest.id}.ndjson"

        if prebuilt is not None:
            shutil.copyfile(prebuilt, ndjson_path)
            ndjson_paths.append(ndjson_path)
            included_source_ids.append(manifest.id)
            continue

        pkg = package_dir(manifest.id)
        adapter = importlib.import_module(f"sources.{pkg}.adapter")

        if smoke:
            fixture_name = _SMOKE_FIXTURES.get(manifest.id)
            if fixture_name is None:
                print(
                    f"[smoke] no fixture for {manifest.id!r}, skipping",
                    file=sys.stderr,
                )
                continue
            # Resolve fixture path relative to repo root (tests/fixtures/).
            fixture_path = Path("tests") / "fixtures" / fixture_name
            if not fixture_path.exists():
                raise FileNotFoundError(
                    f"smoke fixture not found: {fixture_path}"
                )
            pois = list(adapter.normalize(fixture_path, fetched_at=fetched_at))
        else:
            # Live mode: snapshot to temp file, then normalize.
            import httpx

            raw_path = work_dir / f"{manifest.id}.raw"
            with raw_path.open("wb") as fh:
                client = httpx.Client(
                    headers={"User-Agent": "kinderkaart/0.1 contact@nos.nl"},
                    follow_redirects=True,
                    timeout=300,
                )
                with client:
                    adapter.snapshot(fh, client=client)
            pois = list(adapter.normalize(raw_path, fetched_at=fetched_at))

        ndjson_path.write_text(
            "\n".join(p.model_dump_json() for p in pois) + "\n"
        )
        ndjson_paths.append(ndjson_path)
        included_source_ids.append(manifest.id)

    if not ndjson_paths:
        raise RuntimeError("No sources produced output — nothing to merge.")

    # Merge.
    canon_path = work_dir / "canon.ndjson"
    identity_dir = out_dir / "data" / country
    identity_dir.mkdir(parents=True, exist_ok=True)
    identity_path = identity_dir / "identity.json"
    next_identity_path = work_dir / "identity.next.json"
    if identity_path.exists():
        shutil.copyfile(identity_path, next_identity_path)
    elif next_identity_path.exists():
        next_identity_path.unlink()

    run_merge(
        ndjson_paths,
        next_identity_path,
        canon_path,
        build_version=data_version,
        authoritative_source_ids=set(included_source_ids),
    )

    # Build.
    site_manifest = build_site(
        canon_path,
        sources_dir,
        out_dir,
        country=country,
        data_version=data_version,
        required_source_ids=set(included_source_ids),
        enforce_expected_counts=not smoke,
    )

    # Commit registry state only after every publication gate succeeded.
    os.replace(next_identity_path, identity_path)

    return site_manifest


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Run the full Kinderkaart data pipeline."
    )
    ap.add_argument("--sources", default="sources", help="Path to sources/ dir")
    ap.add_argument("--work", default="/tmp/kinderkaart-work", help="Scratch dir")
    ap.add_argument("--out", default="site", help="Output dir")
    ap.add_argument("--country", default="nl")
    ap.add_argument("--data-version", required=True)
    ap.add_argument(
        "--smoke",
        action="store_true",
        help="Use test fixtures instead of fetching live data",
    )
    ap.add_argument(
        "--exclude",
        default="",
        help="Comma-separated source ids to exclude",
    )
    ap.add_argument(
        "--include",
        default="",
        help="Comma-separated source ids to include (empty = all)",
    )
    ap.add_argument("--only-runtime", default="github-action")
    ap.add_argument(
        "--prebuilt",
        action="append",
        default=[],
        metavar="SOURCE_ID=PATH",
        help="Add an already-normalized NDJSON stream (repeatable)",
    )
    args = ap.parse_args()

    exclude_ids: set[str] | None = (
        {s for s in args.exclude.split(",") if s} or None
    )
    include_ids: set[str] | None = (
        {s for s in args.include.split(",") if s} or None
    )

    prebuilt_sources: dict[str, Path] = {}
    for item in args.prebuilt:
        source_id, separator, path = item.partition("=")
        if not separator or not source_id or not path:
            ap.error("--prebuilt must be SOURCE_ID=PATH")
        prebuilt_sources[source_id] = Path(path)

    manifest = run(
        Path(args.sources),
        Path(args.work),
        Path(args.out),
        country=args.country,
        data_version=args.data_version,
        only_runtime=args.only_runtime,
        include_ids=include_ids,
        exclude_ids=exclude_ids,
        prebuilt_sources=prebuilt_sources,
        smoke=args.smoke,
    )
    print(f"built: {list(manifest.keys())}")


if __name__ == "__main__":
    main()
