from data_pipeline.hashing import fnv1a


def test_known_vectors():
    # Canonical FNV-1a 32-bit test vectors.
    assert fnv1a("") == 2166136261
    assert fnv1a("a") == 0xE40C292C
    assert fnv1a("foobar") == 0xBF9CF968


def test_range_and_determinism():
    for s in ["rce-musea/m1", "osm/node/1", "wikidata-museums/Q190804"]:
        h = fnv1a(s)
        assert 0 <= h < 2**32
        assert fnv1a(s) == h
