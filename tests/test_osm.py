from datetime import datetime, timezone
from pathlib import Path

from sources.osm.adapter import _categories_for, normalize

FIXTURE = Path(__file__).parent / "fixtures" / "osm_sample.osm"
FIXED = datetime(2026, 6, 19, tzinfo=timezone.utc)


def test_maps_node_and_way_skips_unmatched():
    pois = {p.source_record_id: p for p in normalize(FIXTURE, fetched_at=FIXED)}
    assert set(pois) == {"node/1", "way/100"}  # bench node ignored

    play = pois["node/1"]
    assert play.categories == ["playground"]
    assert play.name == "Speeltuin Vondelpark"
    assert abs(play.lat - 52.36) < 1e-6 and abs(play.lon - 4.885) < 1e-6
    assert play.source_id == "osm"
    assert pois["node/1"].external_ids == {"wikidata": "Q42"}

    zoo = pois["way/100"]
    # petting_zoo wins; zoo also present -> both, deduped/ordered
    assert set(zoo.categories) == {"zoo", "petting_zoo"}
    assert abs(zoo.lat - 52.001) < 1e-3 and abs(zoo.lon - 5.002) < 1e-3


def test_pool_mapping_is_in_mvp_source_contract():
    assert _categories_for({"leisure": "swimming_pool"}) == ["pool"]
