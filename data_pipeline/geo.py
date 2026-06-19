from __future__ import annotations

from functools import lru_cache

import pyproj


@lru_cache(maxsize=1)
def _transformer() -> pyproj.Transformer:
    # always_xy=True => transform takes (x=easting/lon, y=northing/lat)
    return pyproj.Transformer.from_crs("EPSG:28992", "EPSG:4326", always_xy=True)


def rd_to_wgs84(x: float, y: float) -> tuple[float, float]:
    """Dutch RD (EPSG:28992) easting/northing -> (lat, lon) in WGS84."""
    lon, lat = _transformer().transform(x, y)
    return lat, lon
