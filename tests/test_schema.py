from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from data_pipeline.schema import Image, SourcePOI


def _src(**overrides):
    data = dict(
        source_id="wikidata-museums",
        source_record_id="Q190804",
        name="Rijksmuseum",
        categories=["museum"],
        lat=52.36,
        lon=4.885278,
        country="nl",
        fetched_at=datetime(2026, 6, 19, tzinfo=timezone.utc),
        field_provenance={"name": "wikidata-museums"},
    )
    data.update(overrides)
    return data


def test_minimal_sourcepoi_validates_with_unknown_as_none():
    poi = SourcePOI(**_src())
    assert poi.source_record_id == "Q190804"
    assert poi.indoor is None
    assert poi.images == []


def test_extra_fields_forbidden():
    with pytest.raises(ValidationError):
        SourcePOI(**_src(poi_id="wikidata:Q190804"))  # canonical-only field


def test_unknown_category_and_empty_rejected():
    with pytest.raises(ValidationError):
        SourcePOI(**_src(categories=["spaceport"]))
    with pytest.raises(ValidationError):
        SourcePOI(**_src(categories=[]))


def test_duplicate_categories_are_deduped_preserving_order():
    poi = SourcePOI(**_src(categories=["museum", "museum"]))
    assert poi.categories == ["museum"]


def test_country_must_be_supported():
    with pytest.raises(ValidationError):
        SourcePOI(**_src(country="zz"))  # syntactically ok, not supported
    with pytest.raises(ValidationError):
        SourcePOI(**_src(country="NL"))


def test_out_of_range_coords_rejected():
    with pytest.raises(ValidationError):
        SourcePOI(**_src(lat=200.0))


def test_age_constraints():
    with pytest.raises(ValidationError):
        SourcePOI(**_src(age_min=-1))
    with pytest.raises(ValidationError):
        SourcePOI(**_src(age_min=8, age_max=4))


def test_price_model_consistency_with_free():
    with pytest.raises(ValidationError):
        SourcePOI(**_src(free=True, price_model="paid"))
    ok = SourcePOI(**_src(free=True, price_model="free"))
    assert ok.price_model == "free"


def test_url_protocol_allowlist():
    with pytest.raises(ValidationError):
        SourcePOI(**_src(website="javascript:alert(1)"))
    ok = SourcePOI(**_src(website="https://example.org"))
    assert ok.website == "https://example.org"


def test_fetched_at_must_be_tz_aware_and_normalized_to_utc():
    with pytest.raises(ValidationError):
        SourcePOI(**_src(fetched_at=datetime(2026, 6, 19)))  # naive
    poi = SourcePOI(**_src(fetched_at=datetime(2026, 6, 19, 12, tzinfo=timezone(__import__("datetime").timedelta(hours=2)))))
    assert poi.fetched_at.utcoffset().total_seconds() == 0


def test_empty_name_rejected():
    with pytest.raises(ValidationError):
        SourcePOI(**_src(name="  "))


def test_image_requires_license_fields():
    with pytest.raises(ValidationError):
        Image(url="https://x/y.jpg", source_page="https://x")
