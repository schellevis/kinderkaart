from datetime import datetime, timezone

from data_pipeline.publish_gate import check
from data_pipeline.schema import CanonicalPOI, SourceRef

T = datetime(2026, 6, 19, tzinfo=timezone.utc)


def _c(poi_id, sid="osm", lat=52.0, lon=5.0):
    ref = SourceRef(source_id=sid, source_record_id="x", fetched_at=T)
    return CanonicalPOI(poi_id=poi_id, name="X", categories=["museum"], lat=lat, lon=lon,
                        country="nl", contributing=[ref], field_provenance={})


def test_pass():
    assert check([_c("a", "osm"), _c("b", "rce-musea")],
                 required_source_ids={"osm", "rce-musea"}) == []


def test_duplicate_poi_id_fails():
    errs = check([_c("a"), _c("a")], required_source_ids={"osm"})
    assert any("duplicate" in e.lower() for e in errs)


def test_missing_required_source_fails():
    errs = check([_c("a", "osm")], required_source_ids={"osm", "rce-musea"})
    assert any("rce-musea" in e for e in errs)


def test_empty_fails():
    assert check([], required_source_ids=set()) != []
