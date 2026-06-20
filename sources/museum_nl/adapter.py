from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime
from pathlib import Path
from typing import BinaryIO

import httpx

from data_pipeline.adapter_base import SnapshotMetadata, run_cli
from data_pipeline.manifest import load_manifest
from data_pipeline.schema import SourcePOI

ADAPTER_VERSION = "1"
MANIFEST = load_manifest(Path(__file__).with_name("manifest.yaml"))
CATEGORIES = sorted({c for cats in MANIFEST.category_map.values() for c in cats})


def snapshot(output: BinaryIO, *, client: httpx.Client) -> SnapshotMetadata:
    raise NotImplementedError


def normalize(path: Path, *, fetched_at: datetime) -> Iterator[SourcePOI]:
    raise NotImplementedError
    yield  # pragma: no cover


if __name__ == "__main__":
    run_cli(snapshot, normalize)
