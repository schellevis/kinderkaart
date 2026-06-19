from __future__ import annotations

import json
import time
from collections.abc import Iterator
from datetime import datetime, timezone
from pathlib import Path
from typing import BinaryIO

import httpx

from data_pipeline.adapter_base import SnapshotMetadata, download, run_cli
from data_pipeline.geo import rd_to_wgs84
from data_pipeline.manifest import load_manifest
from data_pipeline.schema import SourcePOI

ADAPTER_VERSION = "1"
MANIFEST = load_manifest(Path(__file__).with_name("manifest.yaml"))
CATEGORIES = sorted({c for cats in MANIFEST.category_map.values() for c in cats})

_WFS_PARAMS = {
    "service": "WFS",
    "version": "2.0.0",
    "request": "GetFeature",
    "typeName": "Veiligheid_van_Erfgoed:overzichtmusea",
    "outputFormat": "application/json",
}


def snapshot(output: BinaryIO, *, client: httpx.Client) -> SnapshotMetadata:
    fetched = datetime.now(timezone.utc)
    checksum = download(MANIFEST.endpoint or "", output, client=client, sleep=time.sleep,
                        params=_WFS_PARAMS)
    return SnapshotMetadata(
        source_id=MANIFEST.id, endpoint=MANIFEST.endpoint or "",
        query=json.dumps(_WFS_PARAMS, sort_keys=True), checksum=checksum,
        fetched_at=fetched, adapter_version=ADAPTER_VERSION,
    )


def _is_rd(collection: dict) -> bool:
    name = (collection.get("crs", {}).get("properties", {}).get("name") or "").upper()
    return "28992" in name


def normalize(path: Path, *, fetched_at: datetime) -> Iterator[SourcePOI]:
    with path.open("rb") as fh:
        data = json.load(fh)
    rd = _is_rd(data)
    for feat in data["features"]:
        x, y = feat["geometry"]["coordinates"][:2]
        lat, lon = rd_to_wgs84(x, y) if rd else (y, x)
        props = feat.get("properties", {})
        addr = {k: v for k, v in (("city", props.get("plaats")),
                                  ("postcode", props.get("postcode"))) if v}
        prov = {"name": MANIFEST.id, "lat": MANIFEST.id, "lon": MANIFEST.id}
        if addr:
            prov["address"] = MANIFEST.id
        yield SourcePOI(
            source_id=MANIFEST.id,
            source_record_id=str(feat["id"]),
            name=props.get("naam") or str(feat["id"]),
            categories=list(CATEGORIES),
            lat=lat, lon=lon, country=MANIFEST.country,
            address=addr if addr else None,
            fetched_at=fetched_at, field_provenance=prov,
        )


if __name__ == "__main__":
    run_cli(snapshot, normalize)
