"""Template adapter. Copy this folder to sources/<package_dir>/ and fill in.

Conventions:
  - manifest.id is kebab-case (e.g. "den-haag-playgrounds").
  - the package directory is id.replace("-", "_") (e.g. "den_haag_playgrounds").

Contract (spec §5):
  snapshot(output, *, client) -> SnapshotMetadata
      Download raw bytes chunked into `output`; return the envelope.
  normalize(input, *, fetched_at) -> Iterator[SourcePOI]
      Stream validated SourcePOI. Map each source field and record its origin in
      `field_provenance` for EVERY field you actually populate.

Mapping checklist:
  - source_record_id: a stable per-source key (never changes for the same place).
  - categories: map source types via manifest.category_map -> our vocabulary.
  - facets (indoor/free/age_*/...): leave None when the source does not say.
"""
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


def snapshot(output: BinaryIO, *, client: httpx.Client) -> SnapshotMetadata:
    raise NotImplementedError("download raw source bytes into `output`")


def normalize(input: BinaryIO, *, fetched_at: datetime) -> Iterator[SourcePOI]:
    raise NotImplementedError("map raw records to SourcePOI objects")
    yield  # pragma: no cover  (keeps this a generator)


if __name__ == "__main__":
    run_cli(snapshot, normalize)
