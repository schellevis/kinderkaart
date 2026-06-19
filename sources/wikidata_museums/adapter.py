from __future__ import annotations

import json
import re
import time
from collections.abc import Iterator
from datetime import datetime, timezone
from pathlib import Path
from typing import BinaryIO

import httpx

from data_pipeline.adapter_base import (
    SnapshotMetadata,
    download,
    run_cli,
)
from data_pipeline.manifest import load_manifest
from data_pipeline.schema import SourcePOI

ADAPTER_VERSION = "1"
MANIFEST = load_manifest(Path(__file__).with_name("manifest.yaml"))
CATEGORIES = sorted({c for cats in MANIFEST.category_map.values() for c in cats})
_QID = re.compile(r"^Q[1-9][0-9]*$")

SPARQL = """
SELECT ?item ?itemLabel ?coord ?website WHERE {
  ?item wdt:P31/wdt:P279* wd:Q33506 .
  ?item wdt:P17 wd:Q55 .
  ?item wdt:P625 ?coord .
  OPTIONAL { ?item wdt:P856 ?website . }
  SERVICE wikibase:label { bd:serviceParam wikibase:language "nl,en". }
}
"""


def snapshot(output: BinaryIO, *, client: httpx.Client) -> SnapshotMetadata:
    fetched = datetime.now(timezone.utc)  # start of fetch
    # Pass params to httpx so the SPARQL query is correctly percent-encoded.
    checksum = download(
        MANIFEST.endpoint or "",
        output,
        client=client,
        sleep=time.sleep,
        params={"format": "json", "query": SPARQL},
    )
    return SnapshotMetadata(
        source_id=MANIFEST.id,
        endpoint=MANIFEST.endpoint or "",
        query=SPARQL.strip(),
        checksum=checksum,
        fetched_at=fetched,
        adapter_version=ADAPTER_VERSION,
    )


def _parse_point(wkt: str) -> tuple[float, float]:
    """'Point(lon lat)' -> (lat, lon)."""
    inner = wkt[wkt.index("(") + 1 : wkt.index(")")]
    lon_s, lat_s = inner.split()
    return float(lat_s), float(lon_s)


def normalize(input: BinaryIO, *, fetched_at: datetime) -> Iterator[SourcePOI]:
    data = json.load(input)  # adapter-specific: Wikidata JSON is read fully into memory
    # Consolidate multi-row bindings per QID deterministically.
    by_qid: dict[str, dict] = {}
    order: list[str] = []
    for b in data["results"]["bindings"]:
        qid = b["item"]["value"].rsplit("/", 1)[-1]
        if not _QID.match(qid):
            raise ValueError(f"invalid Wikidata QID: {qid!r}")
        if qid not in by_qid:
            by_qid[qid] = {"label": None, "coords": set(), "websites": set()}
            order.append(qid)
        rec = by_qid[qid]
        rec["label"] = rec["label"] or b.get("itemLabel", {}).get("value")
        rec["coords"].add(b["coord"]["value"])
        if "website" in b:
            rec["websites"].add(b["website"]["value"])

    for qid in order:
        rec = by_qid[qid]
        lat, lon = _parse_point(sorted(rec["coords"])[0])  # stable rule
        provenance = {"name": MANIFEST.id, "lat": MANIFEST.id, "lon": MANIFEST.id}
        website = None
        if rec["websites"]:
            website = sorted(rec["websites"])[0]  # stable rule
            provenance["website"] = MANIFEST.id
        yield SourcePOI(
            source_id=MANIFEST.id,
            source_record_id=qid,
            name=rec["label"] or qid,
            categories=list(CATEGORIES),
            lat=lat,
            lon=lon,
            country=MANIFEST.country,
            website=website,
            source_url=f"http://www.wikidata.org/entity/{qid}",
            fetched_at=fetched_at,
            field_provenance=provenance,
        )


if __name__ == "__main__":
    run_cli(snapshot, normalize)
