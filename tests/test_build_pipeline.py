from pathlib import Path

from scripts.build_pipeline import run


def test_smoke_pipeline(tmp_path):
    out = tmp_path / "out"
    manifest = run(Path("sources"), tmp_path / "work", out, country="nl",
                   data_version="smoke", only_runtime="github-action",
                   exclude_ids={"osm"}, smoke=True)
    assert manifest["nl"]["counts"]["total"] >= 4
    assert (out / "data" / "nl" / "smoke" / "points.json").exists()
    assert (out / "data" / "nl" / "identity.json").exists()
