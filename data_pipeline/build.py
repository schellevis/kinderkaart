from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

from data_pipeline.build_detail import choose_shard_count
from data_pipeline.build_manifest import build_license_report
from data_pipeline.build_points import build_points
from data_pipeline.manifest import load_manifest
from data_pipeline.publish_gate import partition
from data_pipeline.schema import CanonicalPOI
from data_pipeline.vocab import CATEGORIES


class BuildGateError(Exception):
    def __init__(self, errors: list[str]) -> None:
        super().__init__("; ".join(errors))
        self.errors = errors


def _load_canon(path: Path) -> list[CanonicalPOI]:
    out = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if line:
            out.append(CanonicalPOI.model_validate_json(line))
    return out


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True,
                               separators=(",", ":")) + "\n")


def build_site(canon_ndjson: Path, sources_dir: Path, out_dir: Path, country: str,
               data_version: str, required_source_ids: set[str],
               enforce_expected_counts: bool = False) -> dict:
    canon = _load_canon(canon_ndjson)
    total_in = len(canon)
    gate = partition(canon, required_source_ids)
    if gate.dropped:
        print(
            f"publish-gate: dropped {len(gate.dropped)}/{total_in} out-of-bounds POIs",
            file=sys.stderr,
        )
        for poi_id, reason in gate.dropped[:20]:
            print(f"  - {poi_id}: {reason}", file=sys.stderr)
        if len(gate.dropped) > 20:
            print(f"  … and {len(gate.dropped) - 20} more", file=sys.stderr)
    canon = gate.kept
    errors = list(gate.errors)
    manifest_paths = sorted(sources_dir.glob("*/manifest.yaml"))
    manifest_paths = [p for p in manifest_paths if p.parent.name != "_template"]
    loaded_manifests = [(load_manifest(path), path) for path in manifest_paths]
    manifests = {manifest.id: (manifest, path) for manifest, path in loaded_manifests}
    contributing_ids = {ref.source_id for poi in canon for ref in poi.contributing}
    if enforce_expected_counts:
        refs = {
            (ref.source_id, ref.source_record_id)
            for poi in canon
            for ref in poi.contributing
        }
        counts = Counter(source_id for source_id, _ in refs)
        for source_id in sorted(required_source_ids):
            expected = manifests[source_id][0].expected_count
            if expected is not None and not expected[0] <= counts[source_id] <= expected[1]:
                errors.append(
                    f"source count outside expected_count: {source_id}="
                    f"{counts[source_id]} not in [{expected[0]}, {expected[1]}]"
                )
    if errors:
        raise BuildGateError(errors)

    try:
        shard_count, shards = choose_shard_count(canon)
    except ValueError as exc:
        raise BuildGateError([str(exc)]) from exc

    version_dir = out_dir / "data" / country / data_version
    _write_json(version_dir / "points.json", build_points(canon))

    for sh in range(shard_count):
        _write_json(version_dir / "detail" / f"{sh}.json", shards.get(sh, {}))

    included_manifest_paths = [
        path for source_id, (_, path) in manifests.items() if source_id in contributing_ids
    ]
    _write_json(
        version_dir / "license.json", build_license_report(included_manifest_paths)
    )

    cat_counts: Counter = Counter()
    for poi in canon:
        for c in poi.categories:
            cat_counts[c] += 1

    base = f"data/{country}/{data_version}"
    country_manifest = {
        "data_version": data_version,
        "shard_count": shard_count,
        "categories": sorted(CATEGORIES),
        "paths": {
            "points": f"{base}/points.json",
            "detail": f"{base}/detail",
            "license": f"{base}/license.json",
        },
        "counts": {"total": len(canon), **dict(sorted(cat_counts.items()))},
    }

    # Manifest LAST (atomic switch). Merge with any existing manifest (other countries).
    manifest_path = out_dir / "data" / "manifest.json"
    existing = {}
    if manifest_path.exists():
        existing = json.loads(manifest_path.read_text())
    existing[country] = country_manifest
    _write_json(manifest_path, existing)
    return existing


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--canon", required=True)
    ap.add_argument("--sources", default="sources")
    ap.add_argument("--out", required=True)
    ap.add_argument("--country", default="nl")
    ap.add_argument("--data-version", required=True)
    ap.add_argument("--require", default="")
    args = ap.parse_args()
    req = {s for s in args.require.split(",") if s}
    try:
        build_site(Path(args.canon), Path(args.sources), Path(args.out), args.country,
                   args.data_version, req, enforce_expected_counts=True)
    except BuildGateError as e:
        raise SystemExit(f"publish-gate FAILED (last-known-good kept): {e}")
    print(f"built {args.country}/{args.data_version}")


if __name__ == "__main__":
    main()
