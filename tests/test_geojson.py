import pytest

from data_pipeline.geojson import representative_point


def test_point():
    assert representative_point({"type": "Point", "coordinates": [4.3, 52.07]}) == (52.07, 4.3)


def test_polygon_centroid():
    lat, lon = representative_point({"type": "Polygon", "coordinates": [
        [[4.30, 52.07], [4.302, 52.07], [4.302, 52.072], [4.30, 52.072], [4.30, 52.07]]]})
    assert abs(lat - 52.071) < 1e-9 and abs(lon - 4.301) < 1e-9


def test_unsupported_raises():
    with pytest.raises(ValueError):
        representative_point({"type": "LineString", "coordinates": [[0, 0], [1, 1]]})
