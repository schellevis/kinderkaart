from datetime import datetime, timezone
import random

import pytest

from data_pipeline.build_detail import build_detail, choose_shard_count, shard_count_for, shard_of
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


def test_tags_evidence_round_trips_into_detail():
    ref = SourceRef(source_id="restaurants-agent", source_record_id="restaurants-agent:12345", fetched_at=T)
    evidence = [{"signal": "speelhoek", "direct": True, "source_url": "https://example.com/kids", "evidence_date": "2026-06-19"}]
    poi = CanonicalPOI(
        poi_id="restaurants-agent/1",
        name="Restaurant De Speelhoek",
        categories=["restaurant_kidfriendly"],
        lat=52.0907,
        lon=5.1214,
        country="nl",
        contributing=[ref],
        field_provenance={},
        tags={"evidence": evidence},
    )
    detail = build_detail([poi], 1)
    sh = list(detail.values())[0]
    record = sh["restaurants-agent/1"]
    assert "tags" in record
    assert record["tags"]["evidence"] == evidence


def test_alias_is_resolvable_from_its_own_hash_shard():
    poi = _canon("rce-musea/current")
    poi.aliases = ["wikidata-museums/old"]
    count, detail = choose_shard_count([poi])
    alias_shard = shard_of("wikidata-museums/old", count)
    assert detail[alias_shard]["wikidata-museums/old"] == {
        "redirect_to": "rce-musea/current"
    }


def test_chosen_shards_enforce_record_limit():
    canon = [_canon(f"osm/node/{i}") for i in range(1000)]
    _, detail = choose_shard_count(canon, max_records=25)
    assert max(map(len, detail.values())) <= 25


def test_single_oversized_detail_fails_instead_of_looping_forever():
    poi = _canon("osm/node/large")
    poi.tags = {"blob": random.Random(42).randbytes(100_000).hex()}
    with pytest.raises(ValueError, match="exceeds gzip limit"):
        choose_shard_count([poi])
