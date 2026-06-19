from __future__ import annotations

import math

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


def build_detail(canon: list[CanonicalPOI], shard_count: int) -> dict[int, dict[str, dict]]:
    shards: dict[int, dict[str, dict]] = {}
    for poi in sorted(canon, key=lambda p: p.poi_id):
        sh = shard_of(poi.poi_id, shard_count)
        shards.setdefault(sh, {})[poi.poi_id] = _detail(poi)
    return shards
