from __future__ import annotations

import math
import gzip
import json

from data_pipeline.hashing import fnv1a
from data_pipeline.schema import CanonicalPOI


def shard_count_for(n: int, target: int = 300) -> int:
    return max(1, math.ceil(n / target))


def shard_of(poi_id: str, shard_count: int) -> int:
    return fnv1a(poi_id) % shard_count


def _detail(poi: CanonicalPOI) -> dict:
    return {
        "name": poi.name,
        "lat": round(poi.lat, 5),
        "lon": round(poi.lon, 5),
        "categories": poi.categories,
        "address": poi.address.model_dump(exclude_none=True) if poi.address else None,
        "opening_hours": poi.opening_hours,
        "website": poi.website,
        "images": [img.model_dump() for img in poi.images],
        "provenance": poi.field_provenance,
        "sources": [
            {"source_id": r.source_id, "source_record_id": r.source_record_id,
             "source_url": r.source_url}
            for r in poi.contributing
        ],
        "last_updated": poi.last_updated.isoformat() if poi.last_updated else None,
        "tags": poi.tags,
    }


def _encoded_size(payload: dict) -> int:
    raw = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode() + b"\n"
    return len(gzip.compress(raw, compresslevel=9, mtime=0))


def build_detail(canon: list[CanonicalPOI], shard_count: int) -> dict[int, dict[str, dict]]:
    shards: dict[int, dict[str, dict]] = {}
    for poi in sorted(canon, key=lambda p: p.poi_id):
        sh = shard_of(poi.poi_id, shard_count)
        shards.setdefault(sh, {})[poi.poi_id] = _detail(poi)
        for alias in sorted(poi.aliases):
            alias_shard = shard_of(alias, shard_count)
            shards.setdefault(alias_shard, {})[alias] = {"redirect_to": poi.poi_id}
    return shards


def choose_shard_count(
    canon: list[CanonicalPOI],
    *,
    max_records: int = 300,
    max_gzip_bytes: int = 50 * 1024,
) -> tuple[int, dict[int, dict[str, dict]]]:
    """Choose the smallest deterministic shard count satisfying both hard limits."""
    entries = len(canon) + sum(len(p.aliases) for p in canon)
    for poi in canon:
        if _encoded_size({poi.poi_id: _detail(poi)}) > max_gzip_bytes:
            raise ValueError(f"detail record exceeds gzip limit: {poi.poi_id}")
    count = shard_count_for(entries, max_records)
    max_count = max(count, entries * 10, 1)
    while count <= max_count:
        shards = build_detail(canon, count)
        if all(
            len(payload) <= max_records and _encoded_size(payload) <= max_gzip_bytes
            for payload in shards.values()
        ):
            return count, shards
        count += 1
    raise ValueError("could not satisfy detail shard limits")
