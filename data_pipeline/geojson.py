from __future__ import annotations

from typing import Any


def representative_point(geom: dict) -> tuple[float, float]:
    """Return (lat, lon). GeoJSON is (lon, lat). Polygon -> centroid of outer ring."""
    gtype = geom["type"]
    coords: Any = geom["coordinates"]
    if gtype == "Point":
        lon, lat = coords[:2]
        return lat, lon
    if gtype == "Polygon":
        ring = coords[0][:-1] or coords[0]  # drop closing point if present
        lons = [c[0] for c in ring]
        lats = [c[1] for c in ring]
        return sum(lats) / len(lats), sum(lons) / len(lons)
    if gtype == "MultiPolygon":
        ring = coords[0][0][:-1] or coords[0][0]
        lons = [c[0] for c in ring]
        lats = [c[1] for c in ring]
        return sum(lats) / len(lats), sum(lons) / len(lons)
    raise ValueError(f"unsupported geometry: {gtype}")
