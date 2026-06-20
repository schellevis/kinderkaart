from datetime import date, datetime, timezone

from data_pipeline.merge_fields import merge_cluster
from data_pipeline.schema import SourcePOI

T = datetime(2026, 6, 19, tzinfo=timezone.utc)


def test_priority_wins_and_provenance_records_source_record():
    rce = SourcePOI(source_id="rce-musea", source_record_id="m1", name="Rijksmuseum",
                    categories=["museum"], lat=52.36, lon=4.885, country="nl", fetched_at=T,
                    field_provenance={"name": "rce-musea"})
    wd = SourcePOI(source_id="wikidata-museums", source_record_id="Q190804", name="Rijksmuseum NL",
                   categories=["museum"], lat=52.3601, lon=4.8853, country="nl", fetched_at=T,
                   website="https://rijksmuseum.nl", external_ids={"wikidata": "Q190804"},
                   field_provenance={"name": "wikidata-museums"})
    poi = merge_cluster([wd, rce], poi_id="rce-musea/m1")
    assert poi.poi_id == "rce-musea/m1"
    assert poi.name == "Rijksmuseum"  # rce-musea outranks wikidata
    assert poi.field_provenance["name"] == "rce-musea/m1"
    # website only from wikidata -> provenance points there
    assert poi.website == "https://rijksmuseum.nl"
    assert poi.field_provenance["website"] == "wikidata-museums/Q190804"
    assert poi.external_ids == {"wikidata": "Q190804"}
    assert poi.categories == ["museum"]
    assert poi.field_provenance["/categories/0"] == "rce-musea/m1"
    assert poi.field_provenance["/external_ids/wikidata"] == "wikidata-museums/Q190804"
    assert {r.source_id for r in poi.contributing} == {"rce-musea", "wikidata-museums"}
    # contributing sorted by source rank: rce-musea (rank 0) first
    assert poi.contributing[0].source_id == "rce-musea"
    assert poi.last_updated == date(2026, 6, 19)


def test_categories_unioned_across_cluster():
    a = SourcePOI(source_id="osm", source_record_id="way/1", name="X", categories=["zoo"],
                  lat=52.0, lon=5.0, country="nl", fetched_at=T)
    b = SourcePOI(source_id="osm", source_record_id="way/2", name="X", categories=["petting_zoo"],
                  lat=52.0, lon=5.0, country="nl", fetched_at=T)
    poi = merge_cluster([a, b], poi_id="osm/way/1")
    assert set(poi.categories) == {"zoo", "petting_zoo"}


def test_tags_survive_merge_with_record_level_provenance():
    source = SourcePOI(
        source_id="restaurants-agent", source_record_id="r1", name="Restaurant",
        categories=["restaurant_kidfriendly"], lat=52.0, lon=5.0, country="nl",
        fetched_at=T, tags={"evidence": [{"direct": True}]},
    )
    poi = merge_cluster([source], poi_id="restaurants-agent/r1")
    assert poi.tags == source.tags
    assert poi.field_provenance["/tags/evidence"] == "restaurants-agent/r1"
