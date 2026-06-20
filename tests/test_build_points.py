from datetime import datetime, timezone

from data_pipeline.build_points import build_points
from data_pipeline.schema import CanonicalPOI, SourceRef
from data_pipeline.vocab import CATEGORIES

T = datetime(2026, 6, 19, tzinfo=timezone.utc)


def _canon(poi_id, cats, **kw):
    ref = SourceRef(source_id="osm", source_record_id="x", fetched_at=T)
    return CanonicalPOI(poi_id=poi_id, name=kw.get("name", "X"), categories=cats,
                        lat=kw.get("lat", 52.0), lon=kw.get("lon", 5.0), country="nl",
                        contributing=[ref], field_provenance={}, **{k: v for k, v in kw.items()
                        if k in {"indoor", "free", "age_min", "age_max"}})


def test_build_points_shape_and_bitmask():
    sorted_cats = sorted(CATEGORIES)
    payload = build_points([
        _canon("b/2", ["museum"], indoor=True),
        _canon("a/1", ["playground", "petting_zoo"], free=False, age_min=2, age_max=12),
    ])
    assert payload["categories"] == sorted_cats
    assert payload["fields"] == ["poi_id", "lat", "lon", "cats", "name",
                                 "indoor", "free", "age_min", "age_max"]
    # sorted by poi_id -> a/1 first
    a = payload["points"][0]
    assert a[0] == "a/1"
    expected_mask = (1 << sorted_cats.index("playground")) | (1 << sorted_cats.index("petting_zoo"))
    assert a[3] == expected_mask
    assert a[6] is False and a[7] == 2 and a[8] == 12
    b = payload["points"][1]
    assert b[0] == "b/2" and b[5] is True
