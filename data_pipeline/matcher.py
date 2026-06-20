from __future__ import annotations

from collections import defaultdict

from data_pipeline.geodist import haversine_m
from data_pipeline.merge_config import (
    MATCH_RADIUS_M,
    NAME_THRESHOLD,
    _MAX_STRONGKEY_M,
)
from data_pipeline.schema import SourcePOI
from data_pipeline.textnorm import name_similarity, website_host
from data_pipeline.vocab import CATEGORIES

# Fail fast at import if any category lacks a match radius (M1).
assert CATEGORIES <= set(MATCH_RADIUS_M), (
    f"categories without a match radius: {CATEGORIES - set(MATCH_RADIUS_M)}"
)


def _shares_external_id(a: SourcePOI, b: SourcePOI) -> bool:
    for k, v in a.external_ids.items():
        if b.external_ids.get(k) == v:
            return True
    return False


def _shares_website(a: SourcePOI, b: SourcePOI) -> bool:
    ha, hb = website_host(a.website), website_host(b.website)
    return ha is not None and ha == hb


def is_match(a: SourcePOI, b: SourcePOI) -> bool:
    dist = haversine_m(a.lat, a.lon, b.lat, b.lon)
    # Strong keys: shared external id or website host (with a sanity distance cap).
    if (_shares_external_id(a, b) or _shares_website(a, b)) and dist <= _MAX_STRONGKEY_M:
        return True
    # Scored path: requires category overlap, proximity within the tighter radius, name match.
    shared = set(a.categories) & set(b.categories)
    if not shared:
        return False
    radius = min(MATCH_RADIUS_M[c] for c in shared)
    if dist > radius:
        return False
    return name_similarity(a.name, b.name) >= NAME_THRESHOLD


def _cell(lat: float, lon: float) -> tuple[int, int]:
    # ~0.02 deg: adjacent cells cover the 2 km strong-key sanity radius too.
    return (round(lat * 50), round(lon * 50))


def cluster(pois: list[SourcePOI]) -> list[list[int]]:
    parent = list(range(len(pois)))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(x: int, y: int) -> None:
        rx, ry = find(x), find(y)
        if rx != ry:
            parent[max(rx, ry)] = min(rx, ry)

    grid: dict[tuple[int, int], list[int]] = defaultdict(list)
    for i, p in enumerate(pois):
        grid[_cell(p.lat, p.lon)].append(i)

    for i, p in enumerate(pois):
        ci, cj = _cell(p.lat, p.lon)
        for di in (-1, 0, 1):
            for dj in (-1, 0, 1):
                for j in grid.get((ci + di, cj + dj), ()):
                    if j > i and is_match(p, pois[j]):
                        union(i, j)

    groups: dict[int, list[int]] = defaultdict(list)
    for i in range(len(pois)):
        groups[find(i)].append(i)
    clusters = [sorted(members) for members in groups.values()]
    clusters.sort(key=lambda m: m[0])
    return clusters
