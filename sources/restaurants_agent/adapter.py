from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime
from pathlib import Path
from typing import BinaryIO

import httpx  # noqa: F401  (kept for the run_cli snapshot signature parity)
import yaml

from data_pipeline.adapter_base import SnapshotMetadata, run_cli  # noqa: F401
from data_pipeline.hashing import fnv1a
from data_pipeline.manifest import load_manifest
from data_pipeline.schema import SourcePOI

MANIFEST = load_manifest(Path(__file__).with_name("manifest.yaml"))
_DIRECT = {"kindermenu", "speelhoek", "kinderstoel", "verschoontafel"}


def snapshot(output: BinaryIO, *, client: httpx.Client) -> SnapshotMetadata:
    raise NotImplementedError("codespace-only: edit curated.yaml; there is no fetch step")


def _has_direct(evidence: list[dict]) -> bool:
    return any(e.get("direct") and e.get("signal") in _DIRECT for e in evidence)


def normalize(path: Path, *, fetched_at: datetime) -> Iterator[SourcePOI]:
    records = yaml.safe_load(path.read_text()) or []
    for rec in records:
        evidence = rec.get("evidence", [])
        if not _has_direct(evidence):
            continue  # gate: at least one DIRECT signal required (spec §8.1)
        key = f"{rec['name']}|{rec['lat']}|{rec['lon']}"
        yield SourcePOI(
            source_id=MANIFEST.id,
            source_record_id=f"{MANIFEST.id}:{fnv1a(key)}",
            name=rec["name"],
            categories=["restaurant_kidfriendly"],
            lat=float(rec["lat"]),
            lon=float(rec["lon"]),
            country=MANIFEST.country,
            website=rec.get("website"),
            tags={"evidence": evidence},
            fetched_at=fetched_at,
            field_provenance={"name": MANIFEST.id, "lat": MANIFEST.id, "lon": MANIFEST.id},
        )


if __name__ == "__main__":
    run_cli(snapshot, normalize)
