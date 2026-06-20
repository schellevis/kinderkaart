from __future__ import annotations

import json
import time
from collections.abc import Iterator
from datetime import datetime, timezone
from pathlib import Path
from typing import BinaryIO

import httpx

from data_pipeline.adapter_base import SnapshotMetadata, download, run_cli
from data_pipeline.geojson import representative_point
from data_pipeline.manifest import load_manifest
from data_pipeline.schema import SourcePOI

ADAPTER_VERSION = "1"
MANIFEST = load_manifest(Path(__file__).with_name("manifest.yaml"))
CATEGORIES = sorted({c for cats in MANIFEST.category_map.values() for c in cats})


def snapshot(output: BinaryIO, *, client: httpx.Client) -> SnapshotMetadata:
    fetched = datetime.now(timezone.utc)
    checksum = download(MANIFEST.endpoint or "", output, client=client, sleep=time.sleep)
    return SnapshotMetadata(
        source_id=MANIFEST.id, endpoint=MANIFEST.endpoint or "", query=None,
        checksum=checksum, fetched_at=fetched, adapter_version=ADAPTER_VERSION,
    )


def _coords(feat: dict) -> tuple[float, float] | None:
    geometry = feat.get("geometry")
    if geometry is not None:
        return representative_point(geometry)

    point = feat.get("geo_point_2d")
    if isinstance(point, dict):
        lat = point.get("lat")
        lon = point.get("lon")
        if isinstance(lat, (int, float)) and isinstance(lon, (int, float)):
            return float(lat), float(lon)
    return None


def normalize(path: Path, *, fetched_at: datetime) -> Iterator[SourcePOI]:
    with path.open("rb") as fh:
        data = json.load(fh)
    for i, feat in enumerate(data["features"]):
        coords = _coords(feat)
        if coords is None:
            continue
        lat, lon = coords
        props = feat.get("properties", {})
        name = props.get("naam") or props.get("straatnaam") or f"Speelplek {i}"
        # Use coordinate-based id for stability across re-fetches; Opendatasoft has no
        # stable native feature id, so index-based ids would break the identity registry.
        yield SourcePOI(
            source_id=MANIFEST.id,
            source_record_id=f"{MANIFEST.id}:{round(lat, 5)},{round(lon, 5)}",
            name=name,
            categories=list(CATEGORIES), lat=lat, lon=lon, country=MANIFEST.country,
            fetched_at=fetched_at,
            field_provenance={
                "name": MANIFEST.id, "categories": MANIFEST.id,
                "lat": MANIFEST.id, "lon": MANIFEST.id, "country": MANIFEST.id,
            },
        )


if __name__ == "__main__":
    run_cli(snapshot, normalize)
