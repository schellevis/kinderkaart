# Kinderkaart Plan 4 — Build + Publication Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the merged `CanonicalPOI` stream into the **static publication artifacts** the
front-end consumes — a compact client point index, sharded detail JSON, and a versioned
`manifest.json` — behind a publish-gate, all under `data/<land>/<data_version>/` for GitHub Pages.

**Architecture:** Builds on Plans 1–3 (spikes resolved → fully static, no Vercel/PMTiles/Releases).
Adds: a shared deterministic `fnv1a` hash (used identically by the JS client in Plan 5 for shard
lookup); a points-index builder; a detail-shard builder + lookup; a manifest + license-report
builder; a publish-gate; and a build CLI that writes a versioned artifact set with a manifest-last
atomic switch and last-known-good behavior. Pure stdlib + pydantic + PyYAML.

**Tech Stack:** Python 3.13, uv, pydantic v2, PyYAML, pytest, ruff, mypy.

## Global Constraints

- Inherits all prior constraints. Determinism: identical `CanonicalPOI` input + `data_version` →
  byte-identical artifacts.
- **Search index is built in-browser** from `points.json` names (Plan 5); the build does NOT
  produce a separate search file.
- **Shard assignment** uses `fnv1a(poi_id) % shard_count`; `shard_count` is stored in the manifest
  so a deep-link resolves a POI's shard **without loading any map tile**.
- **Category bit order** is the sorted `CATEGORIES` vocabulary, emitted in the manifest so the
  client decodes the `cats` bitmask identically.
- Artifacts live under `data/<land>/<data_version>/`: `points.json`, `detail/<n>.json`,
  `license.json`; plus a top-level `data/manifest.json`.
- **Publish-gate** failures → keep last-known-good (do not overwrite the manifest); gate checks:
  per-category counts within each source manifest's `expected_count` band (aggregated), all coords
  valid, **unique `poi_id`**, every required source contributed ≥1 record.
- museum.nl is NOT a required source and is excluded from public artifacts (spec §11).
- Quality bar before every commit: `uv run ruff check . && uv run mypy data_pipeline sources && uv run pytest`.

## File Structure

- `data_pipeline/hashing.py` — `fnv1a(s) -> int` (shared with JS client).
- `data_pipeline/build_points.py` — `build_points(canon) -> dict` (points.json payload).
- `data_pipeline/build_detail.py` — `build_detail(canon, shard_count) -> dict[int, dict]`, `shard_count_for(n)`.
- `data_pipeline/build_manifest.py` — `build_manifest(...)`, `build_license_report(manifests)`.
- `data_pipeline/publish_gate.py` — `check(canon, source_manifests) -> list[str]`.
- `data_pipeline/build.py` — `build_site(...)` + CLI.

---

### Task 1: Shared `fnv1a` hash

**Files:** Create `data_pipeline/hashing.py`; Test `tests/test_hashing.py`

**Interfaces:** `fnv1a(s: str) -> int` — 32-bit FNV-1a over the UTF-8 bytes, returns an int in
`[0, 2**32)`. Must match the canonical FNV-1a constants (offset 2166136261, prime 16777619) so the
JS client (Plan 5) reproduces it exactly.

- [ ] **Step 1: Failing test**

`tests/test_hashing.py`:
```python
from data_pipeline.hashing import fnv1a


def test_known_vectors():
    # Canonical FNV-1a 32-bit test vectors.
    assert fnv1a("") == 2166136261
    assert fnv1a("a") == 0xE40C292C
    assert fnv1a("foobar") == 0xBF9CF968


def test_range_and_determinism():
    for s in ["rce-musea/m1", "osm/node/1", "wikidata-museums/Q190804"]:
        h = fnv1a(s)
        assert 0 <= h < 2**32
        assert fnv1a(s) == h
```

- [ ] **Step 2: Run → fails.**

- [ ] **Step 3: Implement**

`data_pipeline/hashing.py`:
```python
from __future__ import annotations

_OFFSET = 2166136261
_PRIME = 16777619
_MASK = 0xFFFFFFFF


def fnv1a(s: str) -> int:
    h = _OFFSET
    for byte in s.encode("utf-8"):
        h ^= byte
        h = (h * _PRIME) & _MASK
    return h
```

- [ ] **Step 4: Green + commit** `feat: add shared fnv1a hash for deterministic sharding`

---

### Task 2: Points-index builder

**Files:** Create `data_pipeline/build_points.py`; Test `tests/test_build_points.py`

**Interfaces:** `build_points(canon: list[CanonicalPOI]) -> dict` returning
`{"fields": [...], "categories": [...sorted...], "points": [[...]...]}` where each point is
`[poi_id, lat, lon, cats_bitmask, name, indoor, free, age_min, age_max]`. `cats_bitmask` is an int
over the sorted-`CATEGORIES` bit order; bool fields are `true|false|null`; ages `int|null`. Points
sorted by `poi_id`.

- [ ] **Step 1: Failing test**

`tests/test_build_points.py`:
```python
from datetime import datetime, timezone

from data_pipeline.build_points import build_points
from data_pipeline.schema import CanonicalPOI, SourceRef
from data_pipeline.vocab import CATEGORIES

T = datetime(2026, 6, 19, tzinfo=timezone.utc)


def _canon(poi_id, cats, **kw):
    ref = SourceRef(source_id="osm", source_record_id="x", fetched_at=T)
    return CanonicalPOI(poi_id=poi_id, name=kw.get("name", "X"), categories=cats,
                        lat=kw.get("lat", 52.0), lon=kw.get("lon", 5.0), country="nl",
                        contributing=[ref], field_provenance={}, **{k: v for k, v in kw.items()
                        if k in {"indoor", "free", "age_min", "age_max"}})


def test_build_points_shape_and_bitmask():
    sorted_cats = sorted(CATEGORIES)
    payload = build_points([
        _canon("b/2", ["museum"], indoor=True),
        _canon("a/1", ["playground", "petting_zoo"], free=False, age_min=2, age_max=12),
    ])
    assert payload["categories"] == sorted_cats
    assert payload["fields"] == ["poi_id", "lat", "lon", "cats", "name",
                                 "indoor", "free", "age_min", "age_max"]
    # sorted by poi_id -> a/1 first
    a = payload["points"][0]
    assert a[0] == "a/1"
    expected_mask = (1 << sorted_cats.index("playground")) | (1 << sorted_cats.index("petting_zoo"))
    assert a[3] == expected_mask
    assert a[6] is False and a[7] == 2 and a[8] == 12
    b = payload["points"][1]
    assert b[0] == "b/2" and b[5] is True
```

- [ ] **Step 2: Run → fails.**

- [ ] **Step 3: Implement**

`data_pipeline/build_points.py`:
```python
from __future__ import annotations

from data_pipeline.schema import CanonicalPOI
from data_pipeline.vocab import CATEGORIES

FIELDS = ["poi_id", "lat", "lon", "cats", "name", "indoor", "free", "age_min", "age_max"]


def build_points(canon: list[CanonicalPOI]) -> dict:
    sorted_cats = sorted(CATEGORIES)
    bit = {c: i for i, c in enumerate(sorted_cats)}
    points = []
    for poi in sorted(canon, key=lambda p: p.poi_id):
        mask = 0
        for c in poi.categories:
            mask |= 1 << bit[c]
        points.append([
            poi.poi_id, round(poi.lat, 5), round(poi.lon, 5), mask, poi.name,
            poi.indoor, poi.free, poi.age_min, poi.age_max,
        ])
    return {"fields": FIELDS, "categories": sorted_cats, "points": points}
```

- [ ] **Step 4: Green + commit** `feat: add points-index builder`

---

### Task 3: Detail-shard builder + lookup

**Files:** Create `data_pipeline/build_detail.py`; Test `tests/test_build_detail.py`

**Interfaces:**
- `shard_count_for(n: int, target: int = 300) -> int` → `max(1, ceil(n / target))`
- `shard_of(poi_id: str, shard_count: int) -> int` → `fnv1a(poi_id) % shard_count`
- `build_detail(canon: list[CanonicalPOI], shard_count: int) -> dict[int, dict[str, dict]]`
  mapping shard index → `{poi_id: detail_dict}`, where detail includes
  `name, lat, lon, categories, address, opening_hours, website, images, contributing(provenance),
  last_updated`. Deterministic.

- [ ] **Step 1: Failing test**

`tests/test_build_detail.py`:
```python
from datetime import datetime, timezone

from data_pipeline.build_detail import build_detail, shard_count_for, shard_of
from data_pipeline.schema import CanonicalPOI, SourceRef

T = datetime(2026, 6, 19, tzinfo=timezone.utc)


def _canon(poi_id):
    ref = SourceRef(source_id="osm", source_record_id="x", fetched_at=T)
    return CanonicalPOI(poi_id=poi_id, name="X", categories=["museum"], lat=52.0, lon=5.0,
                        country="nl", contributing=[ref], field_provenance={})


def test_shard_count_and_membership():
    assert shard_count_for(0) == 1
    assert shard_count_for(300) == 1
    assert shard_count_for(301) == 2
    assert shard_count_for(60000) == 200


def test_deeplink_lookup_without_tile():
    canon = [_canon(f"osm/node/{i}") for i in range(1000)]
    sc = shard_count_for(len(canon))
    detail = build_detail(canon, sc)
    # a deep-link can find any poi by hashing its id -> shard, no map tile needed
    target = "osm/node/777"
    sh = shard_of(target, sc)
    assert target in detail[sh]
    assert detail[sh][target]["name"] == "X"


def test_deterministic():
    canon = [_canon(f"osm/node/{i}") for i in range(50)]
    assert build_detail(canon, 4) == build_detail(canon, 4)
```

- [ ] **Step 2: Run → fails.**

- [ ] **Step 3: Implement**

`data_pipeline/build_detail.py`:
```python
from __future__ import annotations

import math

from data_pipeline.hashing import fnv1a
from data_pipeline.schema import CanonicalPOI


def shard_count_for(n: int, target: int = 300) -> int:
    return max(1, math.ceil(n / target))


def shard_of(poi_id: str, shard_count: int) -> int:
    return fnv1a(poi_id) % shard_count


def _detail(poi: CanonicalPOI) -> dict:
    return {
        "name": poi.name,
        "lat": round(poi.lat, 5),
        "lon": round(poi.lon, 5),
        "categories": poi.categories,
        "address": poi.address.model_dump(exclude_none=True) if poi.address else None,
        "opening_hours": poi.opening_hours,
        "website": poi.website,
        "images": [img.model_dump() for img in poi.images],
        "provenance": poi.field_provenance,
        "sources": [
            {"source_id": r.source_id, "source_record_id": r.source_record_id,
             "source_url": r.source_url}
            for r in poi.contributing
        ],
        "last_updated": poi.last_updated.isoformat() if poi.last_updated else None,
    }


def build_detail(canon: list[CanonicalPOI], shard_count: int) -> dict[int, dict[str, dict]]:
    shards: dict[int, dict[str, dict]] = {}
    for poi in sorted(canon, key=lambda p: p.poi_id):
        sh = shard_of(poi.poi_id, shard_count)
        shards.setdefault(sh, {})[poi.poi_id] = _detail(poi)
    return shards
```

- [ ] **Step 4: Green + commit** `feat: add detail-shard builder + deterministic lookup`

---

### Task 4: Publish-gate

**Files:** Create `data_pipeline/publish_gate.py`; Test `tests/test_publish_gate.py`

**Interfaces:** `check(canon: list[CanonicalPOI], required_source_ids: set[str]) -> list[str]`
returning a list of human-readable failure strings (empty = pass). Checks: unique `poi_id`; all
coords in NL-plausible range and finite; every required source id appears in some POI's
`contributing`; non-empty result.

- [ ] **Step 1: Failing test**

`tests/test_publish_gate.py`:
```python
from datetime import datetime, timezone

from data_pipeline.publish_gate import check
from data_pipeline.schema import CanonicalPOI, SourceRef

T = datetime(2026, 6, 19, tzinfo=timezone.utc)


def _c(poi_id, sid="osm", lat=52.0, lon=5.0):
    ref = SourceRef(source_id=sid, source_record_id="x", fetched_at=T)
    return CanonicalPOI(poi_id=poi_id, name="X", categories=["museum"], lat=lat, lon=lon,
                        country="nl", contributing=[ref], field_provenance={})


def test_pass():
    assert check([_c("a", "osm"), _c("b", "rce-musea")],
                 required_source_ids={"osm", "rce-musea"}) == []


def test_duplicate_poi_id_fails():
    errs = check([_c("a"), _c("a")], required_source_ids={"osm"})
    assert any("duplicate" in e.lower() for e in errs)


def test_missing_required_source_fails():
    errs = check([_c("a", "osm")], required_source_ids={"osm", "rce-musea"})
    assert any("rce-musea" in e for e in errs)


def test_empty_fails():
    assert check([], required_source_ids=set()) != []
```

- [ ] **Step 2: Run → fails.**

- [ ] **Step 3: Implement**

`data_pipeline/publish_gate.py`:
```python
from __future__ import annotations

import math

from data_pipeline.schema import CanonicalPOI

# Generous NL bounding box (incl. islands / margin).
_LAT = (50.5, 53.8)
_LON = (3.2, 7.3)


def check(canon: list[CanonicalPOI], required_source_ids: set[str]) -> list[str]:
    errors: list[str] = []
    if not canon:
        errors.append("empty dataset")
        return errors

    seen: set[str] = set()
    for poi in canon:
        if poi.poi_id in seen:
            errors.append(f"duplicate poi_id: {poi.poi_id}")
        seen.add(poi.poi_id)
        if not (math.isfinite(poi.lat) and math.isfinite(poi.lon)):
            errors.append(f"non-finite coords: {poi.poi_id}")
        elif not (_LAT[0] <= poi.lat <= _LAT[1] and _LON[0] <= poi.lon <= _LON[1]):
            errors.append(f"coords outside NL: {poi.poi_id} ({poi.lat},{poi.lon})")

    contributing_sources = {r.source_id for poi in canon for r in poi.contributing}
    for sid in sorted(required_source_ids):
        if sid not in contributing_sources:
            errors.append(f"required source missing from output: {sid}")
    return errors
```

- [ ] **Step 4: Green + commit** `feat: add publish-gate (unique ids, coord sanity, required sources)`

---

### Task 5: Build CLI (artifacts + manifest + last-known-good)

**Files:** Create `data_pipeline/build_manifest.py`, `data_pipeline/build.py`; Test `tests/test_build_cli.py`

**Interfaces:**
- `build_manifest.build_license_report(source_manifest_paths: list[Path]) -> dict` →
  `{source_id: {license, license_url, attribution, evidence_date, republication_terms}}`
- `build.build_site(canon_ndjson: Path, sources_dir: Path, out_dir: Path, country: str,
  data_version: str, required_source_ids: set[str]) -> dict` →
  runs the publish-gate; on failure raises `BuildGateError(errors)` WITHOUT touching `manifest.json`
  (last-known-good); on success writes `out_dir/data/<country>/<data_version>/points.json`,
  `.../detail/<n>.json`, `.../license.json`, then **last** writes `out_dir/data/manifest.json`
  (`{country: {data_version, shard_count, paths, counts, categories, attribution}}`). Returns the
  manifest dict. CLI: `python -m data_pipeline.build --canon C.ndjson --sources sources --out site
  --country nl --data-version V --require osm,rce-musea`.

- [ ] **Step 1: Failing test**

`tests/test_build_cli.py`:
```python
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from data_pipeline.build import BuildGateError, build_site
from data_pipeline.schema import CanonicalPOI, SourceRef

T = datetime(2026, 6, 19, tzinfo=timezone.utc)


def _write_canon(path: Path, ids_sources):
    lines = []
    for poi_id, sid in ids_sources:
        ref = SourceRef(source_id=sid, source_record_id="x", fetched_at=T)
        c = CanonicalPOI(poi_id=poi_id, name="X", categories=["museum"], lat=52.0, lon=5.0,
                         country="nl", contributing=[ref], field_provenance={}, last_updated=T.date())
        lines.append(c.model_dump_json())
    path.write_text("\n".join(lines) + "\n")


def test_build_writes_versioned_artifacts_and_manifest(tmp_path):
    canon = tmp_path / "canon.ndjson"
    _write_canon(canon, [("rce-musea/m1", "rce-musea"), ("osm/node/1", "osm")])
    out = tmp_path / "site"
    manifest = build_site(canon, Path("sources"), out, country="nl",
                          data_version="2026.06.19", required_source_ids={"osm", "rce-musea"})
    base = out / "data" / "nl" / "2026.06.19"
    assert (base / "points.json").exists()
    assert (out / "data" / "manifest.json").exists()
    points = json.loads((base / "points.json").read_text())
    assert len(points["points"]) == 2
    assert manifest["nl"]["data_version"] == "2026.06.19"
    assert manifest["nl"]["counts"]["total"] == 2
    # detail shard is resolvable
    sc = manifest["nl"]["shard_count"]
    from data_pipeline.build_detail import shard_of
    sh = shard_of("osm/node/1", sc)
    detail = json.loads((base / "detail" / f"{sh}.json").read_text())
    assert "osm/node/1" in detail


def test_gate_failure_keeps_last_known_good(tmp_path):
    out = tmp_path / "site"
    # First good build
    good = tmp_path / "good.ndjson"
    _write_canon(good, [("osm/node/1", "osm")])
    build_site(good, Path("sources"), out, country="nl", data_version="v1",
               required_source_ids={"osm"})
    manifest_before = (out / "data" / "manifest.json").read_text()
    # Second build fails the gate (duplicate id)
    bad = tmp_path / "bad.ndjson"
    _write_canon(bad, [("osm/dup", "osm"), ("osm/dup", "osm")])
    with pytest.raises(BuildGateError):
        build_site(bad, Path("sources"), out, country="nl", data_version="v2",
                   required_source_ids={"osm"})
    # manifest.json unchanged (last-known-good)
    assert (out / "data" / "manifest.json").read_text() == manifest_before
```

- [ ] **Step 2: Run → fails.**

- [ ] **Step 3: Implement**

`data_pipeline/build_manifest.py`:
```python
from __future__ import annotations

from pathlib import Path

from data_pipeline.manifest import load_manifest


def build_license_report(source_manifest_paths: list[Path]) -> dict:
    report = {}
    for p in sorted(source_manifest_paths):
        m = load_manifest(p)
        report[m.id] = {
            "license": m.license,
            "license_url": m.license_url,
            "attribution": m.attribution,
            "evidence_date": m.license_evidence_date.isoformat(),
            "republication_terms": m.republication_terms,
        }
    return report
```

`data_pipeline/build.py`:
```python
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

from data_pipeline.build_detail import build_detail, shard_count_for, shard_of
from data_pipeline.build_manifest import build_license_report
from data_pipeline.build_points import build_points
from data_pipeline.publish_gate import check
from data_pipeline.schema import CanonicalPOI


class BuildGateError(Exception):
    def __init__(self, errors: list[str]) -> None:
        super().__init__("; ".join(errors))
        self.errors = errors


def _load_canon(path: Path) -> list[CanonicalPOI]:
    out = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if line:
            out.append(CanonicalPOI.model_validate_json(line))
    return out


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True,
                               separators=(",", ":")) + "\n")


def build_site(canon_ndjson: Path, sources_dir: Path, out_dir: Path, country: str,
               data_version: str, required_source_ids: set[str]) -> dict:
    canon = _load_canon(canon_ndjson)
    errors = check(canon, required_source_ids)
    if errors:
        raise BuildGateError(errors)

    version_dir = out_dir / "data" / country / data_version
    _write_json(version_dir / "points.json", build_points(canon))

    shard_count = shard_count_for(len(canon))
    shards = build_detail(canon, shard_count)
    for sh in range(shard_count):
        _write_json(version_dir / "detail" / f"{sh}.json", shards.get(sh, {}))

    manifest_paths = sorted(sources_dir.glob("*/manifest.yaml"))
    manifest_paths = [p for p in manifest_paths if p.parent.name != "_template"]
    _write_json(version_dir / "license.json", build_license_report(manifest_paths))

    cat_counts: Counter = Counter()
    for poi in canon:
        for c in poi.categories:
            cat_counts[c] += 1

    base = f"data/{country}/{data_version}"
    country_manifest = {
        "data_version": data_version,
        "shard_count": shard_count,
        "categories": sorted({c for poi in canon for c in poi.categories}),
        "paths": {
            "points": f"{base}/points.json",
            "detail": f"{base}/detail",
            "license": f"{base}/license.json",
        },
        "counts": {"total": len(canon), **dict(sorted(cat_counts.items()))},
    }

    # Manifest LAST (atomic switch). Merge with any existing manifest (other countries).
    manifest_path = out_dir / "data" / "manifest.json"
    existing = {}
    if manifest_path.exists():
        existing = json.loads(manifest_path.read_text())
    existing[country] = country_manifest
    _write_json(manifest_path, existing)
    return existing


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--canon", required=True)
    ap.add_argument("--sources", default="sources")
    ap.add_argument("--out", required=True)
    ap.add_argument("--country", default="nl")
    ap.add_argument("--data-version", required=True)
    ap.add_argument("--require", default="")
    args = ap.parse_args()
    req = {s for s in args.require.split(",") if s}
    try:
        build_site(Path(args.canon), Path(args.sources), Path(args.out), args.country,
                   args.data_version, req)
    except BuildGateError as e:
        raise SystemExit(f"publish-gate FAILED (last-known-good kept): {e}")
    print(f"built {args.country}/{args.data_version}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Green + quality bar + commit** `feat: add build CLI (static artifacts, manifest-last switch, last-known-good)`

---

## Self-Review

**Spec coverage (Plan 4 = spec §7 build/publication, spike-resolved static design):**
- points.json client index (spike 2) → Task 2 ✓
- sharded detail + deep-link lookup without tile (spike 2) → Task 3 ✓
- shared deterministic hash for JS parity → Task 1 ✓
- manifest.json + versioned paths + manifest-last atomic switch → Task 5 ✓
- license report from per-source manifests (§11) → Tasks 5/3 ✓
- publish-gate (unique ids, coord sanity, required sources) + last-known-good → Tasks 4, 5 ✓
- museum.nl not required / excluded → Task 5 (`required_source_ids` excludes it) ✓
- Out of scope: running the snapshot/normalize/merge orchestration end-to-end (Plan 6 CI); the
  in-browser consumption of these artifacts (Plan 5).

**Placeholder scan:** none. **Type consistency:** `CanonicalPOI` fields consumed match Plan 3;
`shard_of`/`shard_count_for`/`fnv1a` consistent across Tasks 1/3/5; `build_points`/`build_detail`
signatures used by Task 5 match Tasks 2/3.

## Notes for later plans
- Plan 5 (front-end) reproduces `fnv1a` in JS for shard lookup and decodes the `cats` bitmask via
  `manifest.categories` order; it builds the FlexSearch index in-browser from `points.json` names.
- Plan 6 (CI) wires: per-source `snapshot`+`normalize` → `merge` → `build` → commit `site/` to the
  Pages branch; `data_version` = build date/run id; required sources = the github-action runtime
  sources (osm, wikidata-museums, rce-musea, den-haag, eindhoven).
