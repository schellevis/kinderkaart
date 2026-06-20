# Kinderkaart Plan 7 — Agent-Curated Restaurant Source Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development or superpowers:executing-plans.

**Goal:** Add the `restaurant_kidfriendly` category as a **codespace-only, agent-curated** source
module that enforces the spec §8.1 evidence contract (≥1 **direct** signal, auditable evidence),
without fabricating or auto-publishing unverified data.

**Architecture:** A standard source module `sources/restaurants_agent/` whose `normalize` reads a
**curated evidence file** (`curated.yaml`, populated manually/by an agent in a codespace) and emits
`restaurant_kidfriendly` `SourcePOI`s — **dropping any record without ≥1 direct signal** and
carrying the evidence in `tags["evidence"]` for the UI. `runtime: codespace-only` → never runs in
CI; the user adds its NDJSON via the orchestrator's `--include` flow (Plan 6 runbook) when permitted.
The detail builder is extended to pass `tags` through so the front-end can show the evidence.

**Tech Stack:** Python 3.13/uv, pydantic, PyYAML.

## Global Constraints

- Inherits prior constraints. `runtime: codespace-only` (excluded from CI).
- **Evidence gate:** a record is included only if it has ≥1 evidence entry with `direct: true`.
  Direct signal types: `kindermenu`, `speelhoek`, `kinderstoel`, `verschoontafel`. Indirect (e.g.
  `nabije_speeltuin`) is supplementary and never sufficient alone.
- Each evidence entry carries `{signal, direct, source_url, evidence_date}` — a URL alone is not
  auditable; `evidence_date` is required.
- The module ships an **example** curated file clearly marked as examples, not published data.
- Quality bar: `uv run ruff check . && uv run mypy data_pipeline sources scripts && uv run pytest`.

---

### Task 1: Restaurant source module + evidence gate

**Files:** Create `sources/restaurants_agent/{__init__.py, manifest.yaml, adapter.py, curated.example.yaml, README.md}`;
Test `tests/test_restaurants_agent.py` + fixture `tests/fixtures/restaurants_curated.yaml`.

**Interfaces:** `snapshot` raises `NotImplementedError` (codespace-only; the curated file is the
input, not a fetch); `normalize(path, *, fetched_at) -> Iterator[SourcePOI]` reads the curated YAML
list, applies the evidence gate, and emits `SourcePOI(categories=["restaurant_kidfriendly"],
tags={"evidence": [...]})` with a stable `source_record_id` = `restaurants-agent:{fnv1a(name|lat|lon)}`.

- [ ] **Step 1: Fixture** `tests/fixtures/restaurants_curated.yaml`:
```yaml
- name: "Restaurant De Speelhoek"
  lat: 52.0907
  lon: 5.1214
  website: "https://example.com/speelhoek"
  evidence:
    - {signal: speelhoek, direct: true, source_url: "https://example.com/speelhoek/kids", evidence_date: "2026-06-19"}
    - {signal: nabije_speeltuin, direct: false, source_url: "https://example.com/park", evidence_date: "2026-06-19"}
- name: "Café Zonder Bewijs"
  lat: 52.10
  lon: 5.12
  evidence:
    - {signal: nabije_speeltuin, direct: false, source_url: "https://example.com/x", evidence_date: "2026-06-19"}
```

- [ ] **Step 2: Failing test** `tests/test_restaurants_agent.py`:
```python
from datetime import datetime, timezone
from pathlib import Path

from sources.restaurants_agent.adapter import normalize

FIXTURE = Path(__file__).parent / "fixtures" / "restaurants_curated.yaml"
FIXED = datetime(2026, 6, 19, tzinfo=timezone.utc)


def test_only_records_with_direct_signal_included():
    pois = list(normalize(FIXTURE, fetched_at=FIXED))
    assert len(pois) == 1  # "Café Zonder Bewijs" dropped (no direct signal)
    p = pois[0]
    assert p.categories == ["restaurant_kidfriendly"]
    assert p.name == "Restaurant De Speelhoek"
    assert p.source_id == "restaurants-agent"
    assert any(e["direct"] for e in p.tags["evidence"])
    assert p.website == "https://example.com/speelhoek"
    # stable id is deterministic
    assert list(normalize(FIXTURE, fetched_at=FIXED))[0].source_record_id == p.source_record_id
```

- [ ] **Step 3: Implement**

`sources/restaurants_agent/manifest.yaml`:
```yaml
schema_version: 1
id: restaurants-agent
name: Kindvriendelijke restaurants (agent-gecureerd)
country: nl
endpoint: null
license: CC-BY-4.0
license_url: "https://creativecommons.org/licenses/by/4.0/"
license_evidence_date: "2026-06-19"
republication_terms: "Curated compilation; each record cites its evidence source(s)"
attribution: "Kinderkaart (gecureerd)"
runtime: codespace-only
update_frequency: manual
expected_count: [0, 2000]
contact_policy: "Manual curation; verify each record's direct evidence"
category_map:
  "restaurant_kidfriendly": [restaurant_kidfriendly]
entrypoint: adapter.py
```

`sources/restaurants_agent/adapter.py`:
```python
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
```

`sources/restaurants_agent/curated.example.yaml` — a copy of the fixture's first entry, with a
header comment: "EXAMPLE ONLY — replace with verified entries. Each record needs ≥1 direct signal
(kindermenu/speelhoek/kinderstoel/verschoontafel) with a real source_url + evidence_date."

`sources/restaurants_agent/README.md` — the curation workflow: copy `curated.example.yaml` to
`curated.yaml`, populate via web research (an agent may draft, a human verifies each direct signal),
then run `uv run python -m sources.restaurants_agent.adapter normalize curated.yaml --fetched-at <ISO>`
and feed the NDJSON to the merge via the Plan 6 orchestrator `--include restaurants-agent`. Never
commit unverified entries; the gate drops records lacking a direct signal.

- [ ] **Step 4: Green + commit** `feat: add codespace-only agent-curated restaurant source with evidence gate`

---

### Task 2: Surface evidence in detail output

**Files:** Modify `data_pipeline/build_detail.py`; Test update in `tests/test_build_detail.py`

- [ ] Extend `_detail(poi)` to include `"tags": poi.tags` (so `evidence` reaches the front-end detail
panel). Add a test asserting a POI with `tags={"evidence":[...]}` round-trips into the shard detail.
(The front-end detail panel already renders provenance/sources; a follow-up front-end tweak can show
`detail.tags.evidence` — note it, but the data path is the deliverable here.)
- [ ] **Green + commit** `feat: pass tags (incl. restaurant evidence) into detail shards`

---

## Self-Review
- Codespace-only source, excluded from CI → manifest `runtime` + Plan 6 ✓
- Evidence gate: ≥1 direct signal, else dropped → Task 1 `_has_direct` + test ✓
- Auditable evidence (signal/source_url/evidence_date) carried in tags → Task 1 ✓
- No fabricated/auto-published data: example file is marked; real curation is manual → README ✓
- Evidence reaches the UI data path → Task 2 ✓

## Notes
- A future front-end tweak (small) can render `detail.tags.evidence` as a "waarom kindvriendelijk?"
  list showing each signal + its source link (using the existing `safeHttpUrl` allowlist).
- The public MVP can ship without this source (like museum.nl); it is additive and manual.
