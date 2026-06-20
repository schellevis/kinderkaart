import json
from datetime import datetime, timezone
from pathlib import Path

from data_pipeline.merge import run_merge
from data_pipeline.schema import SourcePOI

T = datetime(2026, 6, 19, tzinfo=timezone.utc)


def _write_ndjson(path: Path, pois: list[SourcePOI]) -> None:
    path.write_text("\n".join(p.model_dump_json() for p in pois) + "\n")


def test_merge_dedups_and_is_idempotent(tmp_path):
    rce = SourcePOI(source_id="rce-musea", source_record_id="m1", name="Rijksmuseum",
                    categories=["museum"], lat=52.3600, lon=4.8852, country="nl", fetched_at=T)
    wd = SourcePOI(source_id="wikidata-museums", source_record_id="Q190804", name="Rijksmuseum",
                   categories=["museum"], lat=52.3601, lon=4.8853, country="nl", fetched_at=T,
                   external_ids={"wikidata": "Q190804"})
    play = SourcePOI(source_id="osm", source_record_id="node/1", name="Speeltuin",
                     categories=["playground"], lat=52.9, lon=4.0, country="nl", fetched_at=T)
    src_a = tmp_path / "rce.ndjson"
    _write_ndjson(src_a, [rce])
    src_b = tmp_path / "other.ndjson"
    _write_ndjson(src_b, [wd, play])
    idp = tmp_path / "identity.json"
    out = tmp_path / "canonical.ndjson"

    n = run_merge([src_a, src_b], idp, out, build_version="2026.06.19")
    assert n == 2  # museum (merged) + playground
    lines = out.read_text().strip().split("\n")
    pois = [json.loads(line) for line in lines]
    museum = next(p for p in pois if "museum" in p["categories"])
    assert museum["poi_id"] == "rce-musea/m1"
    assert museum["external_ids"] == {"wikidata": "Q190804"}
    assert museum["build_version"] == "2026.06.19"
    assert {r["source_id"] for r in museum["contributing"]} == {"rce-musea", "wikidata-museums"}

    out2 = tmp_path / "canonical2.ndjson"
    run_merge([src_a, src_b], idp, out2, build_version="2026.06.19")
    assert out2.read_text() == out.read_text()  # idempotent re-run, stable ids
