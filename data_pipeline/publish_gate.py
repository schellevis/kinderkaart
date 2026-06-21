from __future__ import annotations

import math
from dataclasses import dataclass

from data_pipeline.schema import CanonicalPOI

# Generous European-NL bounding box (incl. islands / margin). POIs outside it — Caribbean
# Netherlands (BES), or junk/swapped coordinates — are dropped from the published set rather
# than failing the whole build.
_LAT = (50.5, 53.8)
_LON = (3.2, 7.3)

# Fail the build only if more than this fraction of POIs fall outside the box. A few out-of-scope
# records drop quietly (logged); a flood signals upstream breakage and must stop the publish.
DROP_FRACTION_THRESHOLD = 0.005


@dataclass
class GateResult:
    kept: list[CanonicalPOI]
    dropped: list[tuple[str, str]]  # (poi_id, reason)
    errors: list[str]               # hard errors -> build must fail


def partition(canon: list[CanonicalPOI], required_source_ids: set[str]) -> GateResult:
    """Split canon into publishable POIs vs. dropped (out-of-bounds) ones, plus hard errors."""
    if not canon:
        return GateResult(kept=[], dropped=[], errors=["empty dataset"])

    errors: list[str] = []
    kept: list[CanonicalPOI] = []
    dropped: list[tuple[str, str]] = []
    seen: set[str] = set()
    for poi in canon:
        if poi.poi_id in seen:
            errors.append(f"duplicate poi_id: {poi.poi_id}")
        seen.add(poi.poi_id)
        if not (math.isfinite(poi.lat) and math.isfinite(poi.lon)):
            dropped.append((poi.poi_id, "non-finite coords"))
            continue
        if not (_LAT[0] <= poi.lat <= _LAT[1] and _LON[0] <= poi.lon <= _LON[1]):
            dropped.append((poi.poi_id, f"coords outside NL ({poi.lat},{poi.lon})"))
            continue
        kept.append(poi)

    if dropped:
        fraction = len(dropped) / len(canon)
        if fraction > DROP_FRACTION_THRESHOLD:
            errors.append(
                f"too many out-of-bounds POIs: dropped {len(dropped)}/{len(canon)} "
                f"({fraction:.2%} > {DROP_FRACTION_THRESHOLD:.2%}) — suspected upstream breakage"
            )

    contributing_sources = {r.source_id for poi in kept for r in poi.contributing}
    for sid in sorted(required_source_ids):
        if sid not in contributing_sources:
            errors.append(f"required source missing from output: {sid}")

    return GateResult(kept=kept, dropped=dropped, errors=errors)
