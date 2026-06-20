from datetime import datetime, timezone
from pathlib import Path

from scripts.build_pipeline import run
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
