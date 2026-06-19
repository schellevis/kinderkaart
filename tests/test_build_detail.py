from datetime import datetime, timezone

from data_pipeline.build_detail import build_detail, shard_count_for, shard_of
from data_pipeline.schema import CanonicalPOI, SourceRef

T = datetime(2026, 6, 19, tzinfo=timezone.utc)


def _canon(poi_id):
    ref = SourceRef(source_id="osm", source_record_id="x", fetched_at=T)
    return CanonicalPOI(poi_id=poi_id, name="X", categories=["museum"], lat=52.0, lon=5.0,
                        country="nl", contributing=[ref], field_provenance={})


def test_shard_count_and_membership():
    assert shard_count_for(0) == 1
    assert shard_count_for(300) == 1
    assert shard_count_for(301) == 2
    assert shard_count_for(60000) == 200


def test_deeplink_lookup_without_tile():
    canon = [_canon(f"osm/node/{i}") for i in range(1000)]
    sc = shard_count_for(len(canon))
    detail = build_detail(canon, sc)
    # a deep-link can find any poi by hashing its id -> shard, no map tile needed
    target = "osm/node/777"
    sh = shard_of(target, sc)
    assert target in detail[sh]
    assert detail[sh][target]["name"] == "X"


def test_deterministic():
    canon = [_canon(f"osm/node/{i}") for i in range(50)]
    assert build_detail(canon, 4) == build_detail(canon, 4)
