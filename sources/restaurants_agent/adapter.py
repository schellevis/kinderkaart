from __future__ import annotations

from collections.abc import Iterator
from datetime import date, datetime
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
_CATEGORIES = sorted(
    {category for categories in MANIFEST.category_map.values() for category in categories}
)


def snapshot(output: BinaryIO, *, client: httpx.Client) -> SnapshotMetadata:
    raise NotImplementedError("codespace-only: edit curated.yaml; there is no fetch step")


def _has_direct(evidence: list[dict]) -> bool:
    return any(e.get("direct") and e.get("signal") in _DIRECT for e in evidence)


def _validate_evidence(evidence: list[dict]) -> None:
    for item in evidence:
        required = {"signal", "direct", "source_record_id", "source_url", "evidence_date"}
        missing = required - item.keys()
        if missing:
            raise ValueError(f"restaurant evidence missing fields: {sorted(missing)}")
        if not str(item["source_record_id"]).strip():
            raise ValueError("restaurant evidence source_record_id must not be blank")
        if not str(item["source_url"]).startswith(("http://", "https://")):
            raise ValueError("restaurant evidence source_url must be http(s)")
        date.fromisoformat(str(item["evidence_date"]))


def normalize(path: Path, *, fetched_at: datetime) -> Iterator[SourcePOI]:
    records = yaml.safe_load(path.read_text()) or []
    for rec in records:
        evidence = rec.get("evidence", [])
        _validate_evidence(evidence)
        if not _has_direct(evidence):
            continue  # gate: at least one DIRECT signal required (spec §8.1)
        key = f"{rec['name']}|{rec['lat']}|{rec['lon']}"
        yield SourcePOI(
            source_id=MANIFEST.id,
            source_record_id=f"{MANIFEST.id}:{fnv1a(key)}",
            name=rec["name"],
            categories=list(_CATEGORIES),
            lat=float(rec["lat"]),
            lon=float(rec["lon"]),
            country=MANIFEST.country,
            website=rec.get("website"),
            tags={"evidence": evidence},
            fetched_at=fetched_at,
            field_provenance={
                "name": MANIFEST.id, "categories": MANIFEST.id,
                "lat": MANIFEST.id, "lon": MANIFEST.id, "country": MANIFEST.id,
                "tags": MANIFEST.id,
                **({"website": MANIFEST.id} if rec.get("website") else {}),
            },
        )


if __name__ == "__main__":
    run_cli(snapshot, normalize)
