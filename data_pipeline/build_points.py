from __future__ import annotations

from data_pipeline.schema import CanonicalPOI
from data_pipeline.vocab import CATEGORIES

FIELDS = ["poi_id", "lat", "lon", "cats", "name", "indoor", "free", "age_min", "age_max"]


def build_points(canon: list[CanonicalPOI]) -> dict:
    sorted_cats = sorted(CATEGORIES)
    bit = {c: i for i, c in enumerate(sorted_cats)}
    points = []
    for poi in sorted(canon, key=lambda p: p.poi_id):
        mask = 0
        for c in poi.categories:
            mask |= 1 << bit[c]
        points.append([
            poi.poi_id, round(poi.lat, 5), round(poi.lon, 5), mask, poi.name,
            poi.indoor, poi.free, poi.age_min, poi.age_max,
        ])
    return {"fields": FIELDS, "categories": sorted_cats, "points": points}
