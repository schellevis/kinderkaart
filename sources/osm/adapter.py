from __future__ import annotations

import time
from collections.abc import Iterator
from datetime import datetime, timezone
from pathlib import Path
from typing import BinaryIO

import httpx
import osmium

from data_pipeline.adapter_base import SnapshotMetadata, download, run_cli
from data_pipeline.manifest import load_manifest
from data_pipeline.schema import SourcePOI

ADAPTER_VERSION = "1"
MANIFEST = load_manifest(Path(__file__).with_name("manifest.yaml"))
# {"leisure": {"playground": [...]}, "tourism": {"zoo": [...]}, ...}
_CATMAP: dict[str, dict[str, list[str]]] = {}
for _kv, _cats in MANIFEST.category_map.items():
    _k, _v = _kv.split("=", 1)
    _CATMAP.setdefault(_k, {})[_v] = _cats


def snapshot(output: BinaryIO, *, client: httpx.Client) -> SnapshotMetadata:
    fetched = datetime.now(timezone.utc)
    checksum = download(MANIFEST.endpoint or "", output, client=client, sleep=time.sleep)
    return SnapshotMetadata(
        source_id=MANIFEST.id, endpoint=MANIFEST.endpoint or "", query=None,
        checksum=checksum, fetched_at=fetched, adapter_version=ADAPTER_VERSION,
    )


def _categories_for(tags: dict[str, str]) -> list[str]:
    cats: list[str] = []
    for key, values in _CATMAP.items():
        v = tags.get(key)
        if v is not None and v in values:
            cats.extend(values[v])
    # dedupe preserving order
    return list(dict.fromkeys(cats))


def _way_centroid(obj: osmium.osm.Way) -> tuple[float, float] | None:
    lats = [n.location.lat for n in obj.nodes if n.location.valid()]
    lons = [n.location.lon for n in obj.nodes if n.location.valid()]
    if not lats:
        return None
    return sum(lats) / len(lats), sum(lons) / len(lons)


def normalize(path: Path, *, fetched_at: datetime) -> Iterator[SourcePOI]:
    fp = osmium.FileProcessor(str(path)).with_locations()
    for obj in fp:
        tags = dict(obj.tags)
        cats = _categories_for(tags)
        if not cats:
            continue
        if obj.is_node():  # type: ignore[union-attr]
            if not obj.location.valid():  # type: ignore[union-attr]
                continue
            lat, lon, kind = obj.location.lat, obj.location.lon, "node"  # type: ignore[union-attr]
        elif obj.is_way():  # type: ignore[union-attr]
            c = _way_centroid(obj)  # type: ignore[arg-type]
            if c is None:
                continue
            lat, lon, kind = c[0], c[1], "way"
        else:
            continue
        yield SourcePOI(
            source_id=MANIFEST.id,
            source_record_id=f"{kind}/{obj.id}",
            name=tags.get("name") or f"{kind}/{obj.id}",
            categories=cats,
            lat=lat, lon=lon, country=MANIFEST.country,
            fetched_at=fetched_at,
            field_provenance={"name": MANIFEST.id, "lat": MANIFEST.id, "lon": MANIFEST.id},
        )


if __name__ == "__main__":
    run_cli(snapshot, normalize)
