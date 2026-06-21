from datetime import datetime, timezone

from data_pipeline.publish_gate import partition
from data_pipeline.schema import CanonicalPOI, SourceRef

T = datetime(2026, 6, 19, tzinfo=timezone.utc)


def _c(poi_id, sid="osm", lat=52.0, lon=5.0):
    ref = SourceRef(source_id=sid, source_record_id="x", fetched_at=T)
    return CanonicalPOI(poi_id=poi_id, name="X", categories=["museum"], lat=lat, lon=lon,
                        country="nl", contributing=[ref], field_provenance={})


def test_pass():
    res = partition([_c("a", "osm"), _c("b", "rce-musea")],
                    required_source_ids={"osm", "rce-musea"})
    assert res.errors == []
    assert len(res.kept) == 2
    assert res.dropped == []


def test_duplicate_poi_id_fails():
    res = partition([_c("a"), _c("a")], required_source_ids={"osm"})
    assert any("duplicate" in e.lower() for e in res.errors)


def test_missing_required_source_fails():
    res = partition([_c("a", "osm")], required_source_ids={"osm", "rce-musea"})
    assert any("rce-musea" in e for e in res.errors)


def test_empty_fails():
    assert partition([], required_source_ids=set()).errors != []


def test_out_of_box_is_dropped_under_threshold():
    # Many in-box POIs + one Caribbean-NL (Bonaire) museum: it is dropped, not a hard error.
    canon = [_c(str(i), "osm") for i in range(300)]
    canon.append(_c("bonaire", "wikidata-museums", lat=12.15, lon=-68.28))
    res = partition(canon, required_source_ids={"osm"})
    assert res.errors == []
    assert any(poi_id == "bonaire" for poi_id, _ in res.dropped)
    assert all(poi.poi_id != "bonaire" for poi in res.kept)


def test_too_many_out_of_box_fails():
    # A flood of out-of-box coords signals upstream breakage and must stop the publish.
    canon = [_c("a", "osm"), _c("b", "osm", lat=12.15, lon=-68.28)]
    res = partition(canon, required_source_ids={"osm"})
    assert any("too many" in e.lower() for e in res.errors)
