from data_pipeline.vocab import CATEGORIES, SUPPORTED_COUNTRIES


def test_vocabularies_are_immutable_frozensets():
    assert isinstance(CATEGORIES, frozenset)
    assert isinstance(SUPPORTED_COUNTRIES, frozenset)
    assert "playground" in CATEGORIES
    assert "nl" in SUPPORTED_COUNTRIES
