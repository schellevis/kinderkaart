from datetime import datetime, timezone

from data_pipeline.matcher import cluster, is_match
from data_pipeline.schema import SourcePOI

T = datetime(2026, 6, 19, tzinfo=timezone.utc)


def poi(sid, rid, name, lat, lon, cats=("museum",), **kw):
    return SourcePOI(source_id=sid, source_record_id=rid, name=name, lat=lat, lon=lon,
                     categories=list(cats), country="nl", fetched_at=T, **kw)


def test_same_museum_two_sources_merges():
    a = poi("rce-musea", "1", "Rijksmuseum", 52.3600, 4.8852)
    b = poi("wikidata-museums", "Q190804", "Het Rijksmuseum", 52.3601, 4.8853,
            external_ids={"wikidata": "Q190804"})
    assert is_match(a, b)


def test_strong_key_external_id_merges_despite_name():
    a = poi("osm", "node/9", "RM", 52.3605, 4.8860, external_ids={"wikidata": "Q190804"})
    b = poi("wikidata-museums", "Q190804", "Rijksmuseum", 52.3601, 4.8853,
            external_ids={"wikidata": "Q190804"})
    assert is_match(a, b)


def test_two_nearby_different_playgrounds_do_not_merge():
    a = poi("osm", "node/1", "Speeltuin Noord", 52.0000, 5.0000, cats=("playground",))
    b = poi("osm", "node/2", "Speeltuin Zuid", 52.0003, 5.0000, cats=("playground",))
    assert not is_match(a, b)  # ~33m apart but names differ


def test_same_name_far_apart_do_not_merge():
    a = poi("osm", "node/1", "Rijksmuseum", 52.36, 4.88)
    b = poi("rce-musea", "2", "Rijksmuseum", 51.00, 4.00)
    assert not is_match(a, b)


def test_cluster_groups_transitively_and_is_sorted():
    a = poi("rce-musea", "1", "Rijksmuseum", 52.3600, 4.8852)
    b = poi("wikidata-museums", "Q190804", "Rijksmuseum", 52.3601, 4.8853)
    c = poi("osm", "node/5", "Speeltuin", 52.9, 4.0, cats=("playground",))
    clusters = cluster([a, b, c])
    assert clusters == [[0, 1], [2]]


def test_strong_key_blocking_covers_full_two_km_sanity_radius():
    a = poi("osm", "node/1", "A", 52.0, 5.0, external_ids={"wikidata": "Q1"})
    b = poi("wikidata-museums", "Q1", "B", 52.015, 5.0,
            external_ids={"wikidata": "Q1"})
    assert is_match(a, b)
    assert cluster([a, b]) == [[0, 1]]
