import io
from datetime import datetime, timezone

import httpx
import pytest

from data_pipeline.adapter_base import (
    USER_AGENT,
    SnapshotMetadata,
    http_get,
    write_ndjson,
)
from data_pipeline.schema import SourcePOI


def _client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def _no_sleep(_seconds):  # records nothing; deterministic
    return None


def _poi():
    return SourcePOI(
        source_id="s", source_record_id="r1", name="A", categories=["museum"],
        lat=52.0, lon=5.0, country="nl",
        fetched_at=datetime(2026, 6, 19, tzinfo=timezone.utc),
    )


def test_user_agent_cannot_be_overridden():
    seen = {}

    def handler(request):
        seen["ua"] = request.headers.get("user-agent")
        return httpx.Response(200, json={"ok": True})

    with _client(handler) as client:
        http_get("https://x/api", client=client, sleep=_no_sleep,
                 headers={"User-Agent": "evil"})
    assert seen["ua"] == USER_AGENT


def test_retries_on_503_then_succeeds():
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(503)
        return httpx.Response(200, json={"ok": True})

    with _client(handler) as client:
        resp = http_get("https://x/api", client=client, sleep=_no_sleep, max_attempts=3)
    assert resp.status_code == 200
    assert calls["n"] == 2


def test_permanent_4xx_not_retried():
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        return httpx.Response(404)

    with _client(handler) as client:
        with pytest.raises(httpx.HTTPStatusError):
            http_get("https://x/api", client=client, sleep=_no_sleep, max_attempts=3)
    assert calls["n"] == 1


def test_exhausted_retries_raises_runtimeerror():
    def handler(request):
        return httpx.Response(503)

    with _client(handler) as client:
        with pytest.raises(RuntimeError):
            http_get("https://x/api", client=client, sleep=_no_sleep, max_attempts=2)


def test_retry_after_http_date_is_accepted():
    slept = []
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(429, headers={"Retry-After": "Wed, 21 Oct 2099 07:28:00 GMT"})
        return httpx.Response(200, json={"ok": True})

    with _client(handler) as client:
        http_get("https://x/api", client=client, sleep=slept.append, max_attempts=3)
    assert slept and slept[0] >= 0  # parsed, did not crash


def test_write_ndjson_emits_one_line_per_poi():
    buf = io.StringIO()
    n = write_ndjson([_poi(), _poi()], out=buf)
    lines = buf.getvalue().strip().split("\n")
    assert n == 2 and len(lines) == 2
    assert '"source_record_id":"r1"' in lines[0]


def test_snapshot_metadata_is_strict():
    with pytest.raises(Exception):
        SnapshotMetadata(
            source_id="s", endpoint="https://x", query=None, checksum="ab",
            fetched_at=datetime(2026, 6, 19, tzinfo=timezone.utc),
            adapter_version="1", extra="boom",
        )


def test_download_retries_on_503_then_streams():
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(503)
        return httpx.Response(200, content=b"payload")

    from data_pipeline.adapter_base import download
    buf = io.BytesIO()
    with _client(handler) as client:
        checksum = download("https://x/f", buf, client=client, sleep=_no_sleep, max_attempts=3)
    assert calls["n"] == 2
    assert buf.getvalue() == b"payload"
    import hashlib
    assert checksum == hashlib.sha256(b"payload").hexdigest()


def test_download_passes_params_and_returns_checksum():
    import hashlib

    from data_pipeline.adapter_base import download

    seen = {}

    def handler(request):
        seen["url"] = str(request.url)
        return httpx.Response(200, content=b"hello")

    buf = io.BytesIO()
    with _client(handler) as client:
        checksum = download("https://x/api", buf, client=client, sleep=_no_sleep,
                            params={"a": "b"})
    assert "a=b" in seen["url"]
    assert buf.getvalue() == b"hello"
    assert checksum == hashlib.sha256(b"hello").hexdigest()
