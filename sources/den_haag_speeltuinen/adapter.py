from __future__ import annotations

import json
import time
from collections.abc import Iterator
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, BinaryIO

import httpx

from data_pipeline.adapter_base import SnapshotMetadata, download, run_cli
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


def _representative_point(geom: dict) -> tuple[float, float]:
    """Return (lat, lon). GeoJSON is (lon, lat). Polygon -> centroid of outer ring."""
    gtype = geom["type"]
    coords: Any = geom["coordinates"]
    if gtype == "Point":
        lon, lat = coords[:2]
        return lat, lon
    if gtype == "Polygon":
        ring = coords[0][:-1] or coords[0]  # drop closing point if present
        lons = [c[0] for c in ring]
        lats = [c[1] for c in ring]
        return sum(lats) / len(lats), sum(lons) / len(lons)
    if gtype == "MultiPolygon":
        ring = coords[0][0][:-1] or coords[0][0]
        lons = [c[0] for c in ring]
        lats = [c[1] for c in ring]
        return sum(lats) / len(lats), sum(lons) / len(lons)
    raise ValueError(f"unsupported geometry: {gtype}")


def normalize(path: Path, *, fetched_at: datetime) -> Iterator[SourcePOI]:
    with path.open("rb") as fh:
        data = json.load(fh)
    for i, feat in enumerate(data["features"]):
        lat, lon = _representative_point(feat["geometry"])
        props = feat.get("properties", {})
        name = props.get("straatnaam") or props.get("naam") or f"Speeltuin {props.get('buurt', i)}"
        yield SourcePOI(
            source_id=MANIFEST.id,
            source_record_id=f"{MANIFEST.id}:{i}",
            name=name,
            categories=list(CATEGORIES),
            lat=lat, lon=lon, country=MANIFEST.country,
            fetched_at=fetched_at,
            field_provenance={"name": MANIFEST.id, "lat": MANIFEST.id, "lon": MANIFEST.id},
        )


if __name__ == "__main__":
    run_cli(snapshot, normalize)
