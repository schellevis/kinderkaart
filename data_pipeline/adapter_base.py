from __future__ import annotations

import argparse
import hashlib
import sys
from collections.abc import Callable, Iterable
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import BinaryIO, Protocol

import httpx
from pydantic import BaseModel, ConfigDict

from data_pipeline.schema import SourcePOI

USER_AGENT = "kinderkaart/0.1 (+https://github.com/joostschellevis/kinderkaart)"
RETRYABLE_STATUS: frozenset[int] = frozenset({429, 500, 502, 503, 504})

SleepFn = Callable[[float], None]


class SnapshotMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_id: str
    endpoint: str
    query: str | None = None
    checksum: str
    fetched_at: datetime
    adapter_version: str


def _retry_after(resp: httpx.Response, default: float) -> float:
    raw = resp.headers.get("Retry-After")
    if raw is None:
        return default
    if raw.isdigit():
        return float(raw)
    try:
        when = parsedate_to_datetime(raw)
        delta = (when - datetime.now(timezone.utc)).total_seconds()
        return max(0.0, delta)
    except (TypeError, ValueError):
        return default


def http_get(
    url: str,
    *,
    client: httpx.Client,
    sleep: SleepFn,
    params: dict | None = None,
    headers: dict | None = None,
    max_attempts: int = 3,
    backoff: float = 0.5,
    timeout: float = 30.0,
) -> httpx.Response:
    hdrs = dict(headers or {})
    hdrs["User-Agent"] = USER_AGENT  # set last: not overridable
    last_exc: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            resp = client.get(url, params=params, headers=hdrs, timeout=timeout)
        except httpx.HTTPError as exc:
            last_exc = exc
            if attempt < max_attempts:
                sleep(backoff * 2 ** (attempt - 1))
            continue
        if resp.status_code in RETRYABLE_STATUS:
            last_exc = httpx.HTTPStatusError(
                f"retryable status {resp.status_code}", request=resp.request, response=resp
            )
            if attempt < max_attempts:
                sleep(_retry_after(resp, backoff * 2 ** (attempt - 1)))
            continue
        resp.raise_for_status()  # permanent 4xx -> raised, not retried
        return resp
    raise RuntimeError(f"GET {url} failed after {max_attempts} attempts") from last_exc


def download(
    url: str,
    output: BinaryIO,
    *,
    client: httpx.Client,
    sleep: SleepFn,
    params: dict | None = None,
) -> str:
    """Stream-download *url* to *output*, returning a sha256 hex digest.

    Note: this performs a single streamed attempt without the retry loop of
    http_get.  Retry parity can be added in Plan 2 if needed.
    """
    digest = hashlib.sha256()
    with client.stream(
        "GET",
        url,
        params=params,
        headers={"User-Agent": USER_AGENT},
        timeout=30.0,
        follow_redirects=True,
    ) as resp:
        if resp.status_code in RETRYABLE_STATUS:
            raise httpx.HTTPStatusError(
                f"retryable status {resp.status_code}",
                request=resp.request,
                response=resp,
            )
        resp.raise_for_status()
        for chunk in resp.iter_bytes():
            output.write(chunk)
            digest.update(chunk)
    return digest.hexdigest()


def write_ndjson(pois: Iterable[SourcePOI], out=None) -> int:
    if out is None:
        out = sys.stdout
    n = 0
    for poi in pois:
        out.write(poi.model_dump_json())
        out.write("\n")
        n += 1
    return n


class _SnapshotFn(Protocol):
    def __call__(self, output: BinaryIO, *, client: httpx.Client) -> SnapshotMetadata: ...


class _NormalizeFn(Protocol):
    def __call__(self, input: BinaryIO, *, fetched_at: datetime) -> Iterable[SourcePOI]: ...


def run_cli(snapshot: _SnapshotFn, normalize: _NormalizeFn) -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)
    snap = sub.add_parser("snapshot")
    snap.add_argument("--output", required=True)
    norm = sub.add_parser("normalize")
    norm.add_argument("path")
    norm.add_argument("--fetched-at")
    args = parser.parse_args()

    if args.cmd == "snapshot":
        with httpx.Client() as client, open(args.output, "wb") as fh:
            meta = snapshot(fh, client=client)
        Path(args.output + ".meta.json").write_text(meta.model_dump_json(indent=2))
    elif args.cmd == "normalize":
        if args.fetched_at:
            fetched = datetime.fromisoformat(args.fetched_at)
        else:
            meta_path = Path(args.path + ".meta.json")
            meta = SnapshotMetadata.model_validate_json(meta_path.read_text())
            fetched = meta.fetched_at
        if fetched.tzinfo is None:
            raise SystemExit("fetched_at must be timezone-aware")
        with open(args.path, "rb") as fh:
            write_ndjson(normalize(fh, fetched_at=fetched))
