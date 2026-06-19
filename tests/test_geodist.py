from data_pipeline.geodist import haversine_m


def test_haversine_known_distance():
    # ~1 deg longitude at 52N is ~68.5 km; check a small known hop (~111m per 0.001 lat)
    d = haversine_m(52.0, 5.0, 52.0009, 5.0)
    assert 95 < d < 105


def test_haversine_zero():
    assert haversine_m(52.0, 5.0, 52.0, 5.0) == 0.0
