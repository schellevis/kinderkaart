from datetime import datetime, timezone
from pathlib import Path

from scripts.build_pipeline import _raw_snapshot_path, run
from sources.restaurants_agent.adapter import normalize as normalize_restaurants


def test_smoke_pipeline(tmp_path):
    out = tmp_path / "out"
    manifest = run(Path("sources"), tmp_path / "work", out, country="nl",
                   data_version="smoke", only_runtime="github-action",
                   exclude_ids={"osm"}, smoke=True)
    assert manifest["nl"]["counts"]["total"] >= 4
    assert (out / "data" / "nl" / "smoke" / "points.json").exists()
    assert (out / "data" / "nl" / "identity.json").exists()


def test_prebuilt_codespace_source_is_added_to_normal_pipeline(tmp_path):
    out = tmp_path / "out"
    prebuilt = tmp_path / "restaurants.ndjson"
    pois = normalize_restaurants(
        Path("tests/fixtures/restaurants_curated.yaml"),
        fetched_at=datetime(2026, 6, 19, tzinfo=timezone.utc),
    )
    prebuilt.write_text("\n".join(p.model_dump_json() for p in pois) + "\n")
    manifest = run(
        Path("sources"), tmp_path / "work", out, country="nl",
        data_version="smoke", only_runtime="github-action",
        exclude_ids={"osm"},
        prebuilt_sources={
            "restaurants-agent": prebuilt
        },
        smoke=True,
    )
    assert manifest["nl"]["counts"]["restaurant_kidfriendly"] == 1


def test_raw_snapshot_path_preserves_endpoint_suffixes(tmp_path):
    assert _raw_snapshot_path(
        tmp_path,
        "osm",
        "https://download.geofabrik.de/europe/netherlands-latest.osm.pbf",
    ) == tmp_path / "osm.raw.osm.pbf"
    assert _raw_snapshot_path(
        tmp_path,
        "eindhoven-speeltuinen",
        "https://example.test/data.json",
    ) == tmp_path / "eindhoven-speeltuinen.raw.json"
    assert _raw_snapshot_path(tmp_path, "museum-nl", None) == tmp_path / "museum-nl.raw"
