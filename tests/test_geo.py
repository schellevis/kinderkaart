from data_pipeline.geo import rd_to_wgs84


def test_rd_centre_of_nl():
    # RD (155000, 463000) is ~the geodetic anchor near Amersfoort.
    lat, lon = rd_to_wgs84(155000.0, 463000.0)
    assert abs(lat - 52.1552) < 0.01
    assert abs(lon - 5.3872) < 0.01
