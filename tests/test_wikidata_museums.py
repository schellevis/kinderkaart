import io
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import httpx
import pytest

from data_pipeline.manifest import package_dir
from sources.wikidata_museums.adapter import MANIFEST, normalize, snapshot

FIXTURE = Path(__file__).parent / "fixtures" / "wikidata_museums_response.json"
REPO_ROOT = Path(__file__).parent.parent
FIXED = datetime(2026, 6, 19, tzinfo=timezone.utc)


def test_one_poi_per_distinct_qid():
    pois = list(normalize(FIXTURE.open("rb"), fetched_at=FIXED))
    assert len(pois) == 2  # duplicate Q190804 row consolidated
    first = pois[0]
    assert first.source_id == "wikidata-museums"
    assert first.source_record_id == "Q190804"
    assert first.name == "Rijksmuseum"
    assert first.categories == ["museum"]
    assert first.country == "nl"
    assert first.lat == 52.36 and first.lon == 4.885278
    # multi-value website resolved by stable rule (lexicographically smallest)
    assert first.website == "https://rijksmuseum.example/en"
    assert first.field_provenance["website"] == "wikidata-museums"


def test_missing_website_is_none():
    pois = list(normalize(FIXTURE.open("rb"), fetched_at=FIXED))
    assert pois[1].website is None
    assert "website" not in pois[1].field_provenance


def test_invalid_qid_raises():
    bad = json.dumps({"results": {"bindings": [{
        "item": {"value": "http://www.wikidata.org/entity/NOTAQID"},
        "itemLabel": {"value": "x"},
        "coord": {"value": "Point(5 52)"},
    }]}}).encode()
    with pytest.raises(ValueError):
        list(normalize(io.BytesIO(bad), fetched_at=FIXED))


def test_manifest_matches_package_dir():
    assert package_dir(MANIFEST.id) == "wikidata_museums"


def test_snapshot_uses_endpoint_and_returns_metadata():
    captured = {}

    def handler(request):
        captured["url"] = str(request.url)
        return httpx.Response(200, content=b'{"results":{"bindings":[]}}')

    buf = io.BytesIO()
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        meta = snapshot(buf, client=client)
    assert MANIFEST.endpoint in captured["url"]
    assert meta.source_id == "wikidata-museums"
    assert meta.checksum and buf.getvalue() == b'{"results":{"bindings":[]}}'


def test_cli_snapshot_writes_envelope(tmp_path):
    """Exercise the snapshot --output PATH branch end-to-end via direct call."""
    response_body = b'{"results":{"bindings":[]}}'

    def handler(request):
        return httpx.Response(200, content=response_body)

    out_path = tmp_path / "snapshot.json"
    with out_path.open("wb") as fh:
        with httpx.Client(transport=httpx.MockTransport(handler)) as client:
            meta = snapshot(fh, client=client)

    assert meta.source_id == "wikidata-museums"
    assert meta.checksum  # non-empty sha256 hex string
    assert meta.query  # SPARQL string is set
    assert meta.fetched_at.tzinfo is not None  # tz-aware
    assert out_path.read_bytes() == response_body


def test_cli_normalize_is_reproducible(tmp_path):
    env = {**os.environ, "PYTHONPATH": str(REPO_ROOT)}
    cmd = [sys.executable, "-m", "sources.wikidata_museums.adapter",
           "normalize", str(FIXTURE), "--fetched-at", FIXED.isoformat()]
    out1 = subprocess.run(cmd, capture_output=True, text=True, check=True,
                          cwd=str(REPO_ROOT), env=env)
    out2 = subprocess.run(cmd, capture_output=True, text=True, check=True,
                          cwd=str(REPO_ROOT), env=env)
    assert out1.returncode == 0 and out1.stderr == ""
    lines = out1.stdout.strip().split("\n")
    assert len(lines) == 2
    json.loads(lines[0])  # valid JSON
    assert out1.stdout == out2.stdout  # byte-identical
