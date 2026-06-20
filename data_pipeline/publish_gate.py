from __future__ import annotations

import math

from data_pipeline.schema import CanonicalPOI

# Generous NL bounding box (incl. islands / margin).
_LAT = (50.5, 53.8)
_LON = (3.2, 7.3)


def check(canon: list[CanonicalPOI], required_source_ids: set[str]) -> list[str]:
    errors: list[str] = []
    if not canon:
        errors.append("empty dataset")
        return errors

    seen: set[str] = set()
    for poi in canon:
        if poi.poi_id in seen:
            errors.append(f"duplicate poi_id: {poi.poi_id}")
        seen.add(poi.poi_id)
        if not (math.isfinite(poi.lat) and math.isfinite(poi.lon)):
            errors.append(f"non-finite coords: {poi.poi_id}")
        elif not (_LAT[0] <= poi.lat <= _LAT[1] and _LON[0] <= poi.lon <= _LON[1]):
            errors.append(f"coords outside NL: {poi.poi_id} ({poi.lat},{poi.lon})")

    contributing_sources = {r.source_id for poi in canon for r in poi.contributing}
    for sid in sorted(required_source_ids):
        if sid not in contributing_sources:
            errors.append(f"required source missing from output: {sid}")
    return errors
