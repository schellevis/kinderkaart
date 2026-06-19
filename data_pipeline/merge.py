from __future__ import annotations

import argparse
from pathlib import Path

import yaml

from data_pipeline.identity import Registry
from data_pipeline.matcher import cluster
from data_pipeline.merge_fields import merge_cluster
from data_pipeline.schema import CanonicalPOI, SourcePOI


def _load_sources(paths: list[Path]) -> list[SourcePOI]:
    pois: list[SourcePOI] = []
    for p in paths:
        for line in p.read_text().splitlines():
            line = line.strip()
            if line:
                pois.append(SourcePOI.model_validate_json(line))
    # Deterministic input order.
    pois.sort(key=lambda x: (x.source_id, x.source_record_id))
    return pois


def _apply_overrides(clusters: list[list[int]], pois: list[SourcePOI],
                     overrides: dict) -> list[list[int]]:
    if not overrides:
        return clusters
    key_to_idx = {f"{p.source_id}/{p.source_record_id}": i for i, p in enumerate(pois)}
    # force_merge: list of lists of member keys that must end up together
    parent = list(range(len(pois)))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: int, b: int) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[max(ra, rb)] = min(ra, rb)

    for members in clusters:
        for m in members[1:]:
            union(members[0], m)
    for group in overrides.get("force_merge", []):
        idxs = [key_to_idx[k] for k in group if k in key_to_idx]
        for k in idxs[1:]:
            union(idxs[0], k)
    forced_apart = {tuple(sorted(g)) for g in overrides.get("force_split", [])}
    from collections import defaultdict
    groups: dict[int, list[int]] = defaultdict(list)
    for i in range(len(pois)):
        groups[find(i)].append(i)
    result = []
    for members in groups.values():
        members = sorted(members)
        keys = tuple(sorted(f"{pois[i].source_id}/{pois[i].source_record_id}" for i in members))
        if keys in forced_apart:
            result.extend([[i] for i in members])
        else:
            result.append(members)
    result.sort(key=lambda m: m[0])
    return result


def run_merge(source_ndjson_paths: list[Path], identity_path: Path, out_path: Path,
              build_version: str, overrides_path: Path | None = None) -> int:
    pois = _load_sources(source_ndjson_paths)
    overrides: dict = {}
    if overrides_path and overrides_path.exists():
        overrides = yaml.safe_load(overrides_path.read_text()) or {}

    clusters = cluster(pois)
    clusters = _apply_overrides(clusters, pois, overrides)

    member_clusters = [
        sorted(f"{pois[i].source_id}/{pois[i].source_record_id}" for i in members)
        for members in clusters
    ]
    reg = Registry.load(identity_path)
    idx_to_id = reg.assign(member_clusters)
    reg.save(identity_path)

    canon: list[CanonicalPOI] = []
    for idx, members in enumerate(clusters):
        poi = merge_cluster([pois[i] for i in members], poi_id=idx_to_id[idx])
        poi.build_version = build_version
        poi.aliases = reg.aliases_for(poi.poi_id)
        canon.append(poi)
    canon.sort(key=lambda c: c.poi_id)
    out_path.write_text("\n".join(c.model_dump_json() for c in canon) + "\n")
    return len(canon)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--identity", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--build-version", required=True)
    ap.add_argument("--overrides")
    ap.add_argument("sources", nargs="+")
    args = ap.parse_args()
    n = run_merge([Path(s) for s in args.sources], Path(args.identity), Path(args.out),
                  build_version=args.build_version,
                  overrides_path=Path(args.overrides) if args.overrides else None)
    print(f"wrote {n} canonical POIs")


if __name__ == "__main__":
    main()
