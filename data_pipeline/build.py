from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

from data_pipeline.build_detail import build_detail, shard_count_for
from data_pipeline.build_manifest import build_license_report
from data_pipeline.build_points import build_points
from data_pipeline.publish_gate import check
from data_pipeline.schema import CanonicalPOI


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
               data_version: str, required_source_ids: set[str]) -> dict:
    canon = _load_canon(canon_ndjson)
    errors = check(canon, required_source_ids)
    if errors:
        raise BuildGateError(errors)

    version_dir = out_dir / "data" / country / data_version
    _write_json(version_dir / "points.json", build_points(canon))

    shard_count = shard_count_for(len(canon))
    shards = build_detail(canon, shard_count)
    for sh in range(shard_count):
        _write_json(version_dir / "detail" / f"{sh}.json", shards.get(sh, {}))

    manifest_paths = sorted(sources_dir.glob("*/manifest.yaml"))
    manifest_paths = [p for p in manifest_paths if p.parent.name != "_template"]
    _write_json(version_dir / "license.json", build_license_report(manifest_paths))

    cat_counts: Counter = Counter()
    for poi in canon:
        for c in poi.categories:
            cat_counts[c] += 1

    base = f"data/{country}/{data_version}"
    country_manifest = {
        "data_version": data_version,
        "shard_count": shard_count,
        "categories": sorted({c for poi in canon for c in poi.categories}),
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
                   args.data_version, req)
    except BuildGateError as e:
        raise SystemExit(f"publish-gate FAILED (last-known-good kept): {e}")
    print(f"built {args.country}/{args.data_version}")


if __name__ == "__main__":
    main()
