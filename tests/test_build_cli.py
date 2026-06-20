import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from data_pipeline.build import BuildGateError, build_site
from data_pipeline.schema import CanonicalPOI, SourceRef

T = datetime(2026, 6, 19, tzinfo=timezone.utc)


def _write_canon(path: Path, ids_sources):
    lines = []
    for poi_id, sid in ids_sources:
        ref = SourceRef(source_id=sid, source_record_id="x", fetched_at=T)
        c = CanonicalPOI(poi_id=poi_id, name="X", categories=["museum"], lat=52.0, lon=5.0,
                         country="nl", contributing=[ref], field_provenance={}, last_updated=T.date())
        lines.append(c.model_dump_json())
    path.write_text("\n".join(lines) + "\n")


def test_build_writes_versioned_artifacts_and_manifest(tmp_path):
    canon = tmp_path / "canon.ndjson"
    _write_canon(canon, [("rce-musea/m1", "rce-musea"), ("osm/node/1", "osm")])
    out = tmp_path / "site"
    manifest = build_site(canon, Path("sources"), out, country="nl",
                          data_version="2026.06.19", required_source_ids={"osm", "rce-musea"})
    base = out / "data" / "nl" / "2026.06.19"
    assert (base / "points.json").exists()
    assert (out / "data" / "manifest.json").exists()
    points = json.loads((base / "points.json").read_text())
    assert len(points["points"]) == 2
    assert manifest["nl"]["data_version"] == "2026.06.19"
    assert manifest["nl"]["counts"]["total"] == 2
    # detail shard is resolvable
    sc = manifest["nl"]["shard_count"]
    from data_pipeline.build_detail import shard_of
    sh = shard_of("osm/node/1", sc)
    detail = json.loads((base / "detail" / f"{sh}.json").read_text())
    assert "osm/node/1" in detail


def test_gate_failure_keeps_last_known_good(tmp_path):
    out = tmp_path / "site"
    # First good build
    good = tmp_path / "good.ndjson"
    _write_canon(good, [("osm/node/1", "osm")])
    build_site(good, Path("sources"), out, country="nl", data_version="v1",
               required_source_ids={"osm"})
    manifest_before = (out / "data" / "manifest.json").read_text()
    # Second build fails the gate (duplicate id)
    bad = tmp_path / "bad.ndjson"
    _write_canon(bad, [("osm/dup", "osm"), ("osm/dup", "osm")])
    with pytest.raises(BuildGateError):
        build_site(bad, Path("sources"), out, country="nl", data_version="v2",
                   required_source_ids={"osm"})
    # manifest.json unchanged (last-known-good)
    assert (out / "data" / "manifest.json").read_text() == manifest_before


def test_expected_source_count_is_a_publish_gate(tmp_path):
    sources = tmp_path / "sources"
    source = sources / "tiny"
    source.mkdir(parents=True)
    (source / "manifest.yaml").write_text(
        """schema_version: 1
id: tiny
name: Tiny
country: nl
endpoint: https://example.com/data
license: CC0-1.0
license_url: https://creativecommons.org/publicdomain/zero/1.0/
license_evidence_date: 2026-06-19
republication_terms: Public domain
attribution: null
runtime: github-action
expected_count: [2, 3]
category_map:
  museum: [museum]
entrypoint: adapter.py
"""
    )
    canon = tmp_path / "canon.ndjson"
    _write_canon(canon, [("tiny/1", "tiny")])
    with pytest.raises(BuildGateError, match="expected_count"):
        build_site(
            canon, sources, tmp_path / "out", country="nl", data_version="v1",
            required_source_ids={"tiny"}, enforce_expected_counts=True,
        )
