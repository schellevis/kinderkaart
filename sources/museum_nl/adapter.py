from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Iterator
from datetime import datetime, timezone
from pathlib import Path
from typing import BinaryIO

import httpx

from data_pipeline.adapter_base import SnapshotMetadata, http_get, run_cli
from data_pipeline.manifest import load_manifest
from data_pipeline.schema import Address, SourcePOI
from sources.museum_nl.parse import (
    extract_meta_description,
    extract_museum_jsonld,
    extract_slugs,
    normalize_website,
    split_street,
)

ADAPTER_VERSION = "1"
MANIFEST = load_manifest(Path(__file__).with_name("manifest.yaml"))
CATEGORIES = sorted({c for cats in MANIFEST.category_map.values() for c in cats})


def snapshot(output: BinaryIO, *, client: httpx.Client) -> SnapshotMetadata:
    fetched = datetime.now(timezone.utc)
    sitemap = http_get(MANIFEST.endpoint or "", client=client, sleep=time.sleep).text
    digest = hashlib.sha256()
    for slug in extract_slugs(sitemap):
        url = f"https://www.museum.nl/nl/{slug}"
        try:
            html = http_get(url, client=client, sleep=time.sleep).text
        except (httpx.HTTPError, RuntimeError):
            continue
        line = json.dumps(
            {"slug": slug, "url": url, "html": html}, sort_keys=True
        ) + "\n"
        data = line.encode("utf-8")
        output.write(data)
        digest.update(data)
    return SnapshotMetadata(
        source_id=MANIFEST.id,
        endpoint=MANIFEST.endpoint or "",
        query=None,
        checksum=digest.hexdigest(),
        fetched_at=fetched,
        adapter_version=ADAPTER_VERSION,
    )


def _to_poi(slug: str, html: str, fetched_at: datetime) -> SourcePOI | None:
    node = extract_museum_jsonld(html)
    if node is None:
        return None
    geo = node.get("geo")
    if not isinstance(geo, dict):
        return None
    try:
        lat = float(geo["latitude"])
        lon = float(geo["longitude"])
    except (KeyError, TypeError, ValueError):
        return None
    name = str(node.get("name") or "").strip()
    if not name:
        return None

    prov = {
        "name": MANIFEST.id,
        "categories": MANIFEST.id,
        "lat": MANIFEST.id,
        "lon": MANIFEST.id,
        "country": MANIFEST.id,
    }

    address: Address | None = None
    addr = node.get("address")
    if isinstance(addr, dict):
        street, house = split_street(str(addr.get("streetAddress") or ""))
        address = Address(
            street=street or None,
            housenumber=house,
            postcode=(addr.get("postalCode") or None),
            city=(addr.get("addressLocality") or None),
        )
        prov["address"] = MANIFEST.id

    website = normalize_website(node.get("sameAs"))
    if website:
        prov["website"] = MANIFEST.id

    tags: dict[str, str] = {}
    phone = node.get("telephone")
    if isinstance(phone, str) and phone.strip():
        tags["phone"] = " ".join(phone.split())
    description = extract_meta_description(html)
    if description:
        tags["description"] = description
    if tags:
        prov["tags"] = MANIFEST.id

    return SourcePOI(
        source_id=MANIFEST.id,
        source_record_id=f"{MANIFEST.id}:{slug}",
        name=name,
        categories=list(CATEGORIES),
        lat=lat,
        lon=lon,
        country=MANIFEST.country,
        address=address,
        website=website,
        tags=tags,
        fetched_at=fetched_at,
        field_provenance=prov,
    )


def normalize(path: Path, *, fetched_at: datetime) -> Iterator[SourcePOI]:
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            poi = _to_poi(rec["slug"], rec["html"], fetched_at)
            if poi is not None:
                yield poi


if __name__ == "__main__":
    run_cli(snapshot, normalize)
