# Kinderkaart Plan 2 — Source Adapters + Reprojection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the remaining MVP data-source adapters — OSM (osmium), RCE Musea (WFS GeoJSON
+ RD→WGS84), Den Haag and Eindhoven (Opendatasoft GeoJSON) — on top of the Plan 1 foundation,
plus a shared reprojection helper, evolving the adapter contract from a byte-stream to a
**snapshot path** so binary/large sources (the 1.3 GB OSM `.pbf`) work cleanly.

**Architecture:** Builds directly on Plan 1 (`data_pipeline/`, `sources/`, the `SourcePOI`
schema, the manifest contract). Task 1 evolves the contract: `normalize` now receives the
snapshot **path** (`Path`) instead of a `BinaryIO`, and `download` gains a retry loop around the
stream. Tasks 2–6 add a reprojection helper and four manifest-driven adapters, each following
the Plan 1 Task-5 pattern (manifest-driven config, `snapshot`/`normalize`, fixture-tested).

**Tech Stack:** Python 3.13, uv, pydantic v2, httpx, PyYAML, **osmium (pyosmium 4.x)**,
**pyproj**, pytest, ruff, mypy.

## Global Constraints

- Inherits all Plan 1 Global Constraints (two-phase models, `extra="forbid"`, country⊆supported,
  category dedup, tz-aware UTC `fetched_at`, URL allowlist, manifest-as-source-of-truth,
  `manifest.id` kebab-case → package dir `id.replace("-", "_")`).
- **Adapter contract (evolved this plan):** `snapshot(output: BinaryIO, *, client) -> SnapshotMetadata`
  (unchanged) and **`normalize(path: Path, *, fetched_at: datetime) -> Iterator[SourcePOI]`**
  (changed: receives the snapshot file path, opens it itself).
- **Categories come from the manifest** (`category_map`), never hard-coded — for multi-type OSM
  this is load-bearing.
- New deps added via `uv add osmium pyproj`; commit the refreshed `uv.lock`.
- Quality bar before every commit: `uv run ruff check . && uv run mypy data_pipeline sources && uv run pytest`.
- Verified API facts (already confirmed on this machine): `pyproj.Transformer.from_crs("EPSG:28992","EPSG:4326", always_xy=True).transform(x, y)` returns `(lon, lat)`; `osmium.FileProcessor(path).with_locations()` yields objects where nodes expose `.location.lat/.lon` and way nodes expose `.location` (compute centroid; guard `.location.valid()`); `dict(obj.tags)` gives tags.

---

### Task 1: Evolve adapter contract to path-based `normalize`

**Files:**
- Modify: `data_pipeline/adapter_base.py` (`run_cli` normalize branch; `download` retry loop)
- Modify: `sources/wikidata_museums/adapter.py` (`normalize` signature + body)
- Modify: `sources/_template/adapter.py` (`normalize` signature)
- Modify: `tests/test_wikidata_museums.py` (pass paths, not handles)
- Test: `tests/test_adapter_base.py` (add download-retry test)

**Interfaces:**
- Changed: `normalize(path: Path, *, fetched_at: datetime) -> Iterator[SourcePOI]` (all adapters)
- Changed: `download(url, output, *, client, sleep, params=None, max_attempts=3, backoff=0.5) -> str`
  now retries retryable statuses/transport errors around a streamed request.

- [ ] **Step 1: Update the failing tests first (red)** — in `tests/test_wikidata_museums.py`,
replace handle-passing with paths and add a temp-file for the invalid-QID case:

```python
def test_one_poi_per_distinct_qid():
    pois = list(normalize(FIXTURE, fetched_at=FIXED))
    ...  # (rest unchanged)


def test_missing_website_is_none():
    pois = list(normalize(FIXTURE, fetched_at=FIXED))
    ...


def test_invalid_qid_raises(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"results": {"bindings": [{
        "item": {"value": "http://www.wikidata.org/entity/NOTAQID"},
        "itemLabel": {"value": "x"},
        "coord": {"value": "Point(5 52)"},
    }]}}))
    with pytest.raises(ValueError):
        list(normalize(bad, fetched_at=FIXED))
```

Remove the now-unused `import io` if nothing else uses it (run ruff to confirm).

Add to `tests/test_adapter_base.py`:
```python
def test_download_retries_on_503_then_streams():
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(503)
        return httpx.Response(200, content=b"payload")

    from data_pipeline.adapter_base import download
    buf = io.BytesIO()
    with _client(handler) as client:
        checksum = download("https://x/f", buf, client=client, sleep=_no_sleep, max_attempts=3)
    assert calls["n"] == 2
    assert buf.getvalue() == b"payload"
    import hashlib
    assert checksum == hashlib.sha256(b"payload").hexdigest()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_wikidata_museums.py tests/test_adapter_base.py -q`
Expected: failures (normalize still takes a handle; download has no retry).

- [ ] **Step 3: Update `run_cli` and `download` in `data_pipeline/adapter_base.py`**

Change the `download` body to retry around a streamed request, and the `run_cli` normalize
branch to pass a `Path`:
```python
def download(
    url: str,
    output: BinaryIO,
    *,
    client: httpx.Client,
    sleep: SleepFn,
    params: dict | None = None,
    max_attempts: int = 3,
    backoff: float = 0.5,
    timeout: float = 30.0,
) -> str:
    hdrs = {"User-Agent": USER_AGENT}
    last_exc: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            with client.stream(
                "GET", url, params=params, headers=hdrs, timeout=timeout,
                follow_redirects=True,
            ) as resp:
                if resp.status_code in RETRYABLE_STATUS:
                    last_exc = httpx.HTTPStatusError(
                        f"retryable status {resp.status_code}",
                        request=resp.request, response=resp,
                    )
                    if attempt < max_attempts:
                        sleep(_retry_after(resp, backoff * 2 ** (attempt - 1)))
                    continue
                resp.raise_for_status()
                digest = hashlib.sha256()
                for chunk in resp.iter_bytes():
                    output.write(chunk)
                    digest.update(chunk)
                return digest.hexdigest()
        except httpx.HTTPError as exc:
            last_exc = exc
            if attempt < max_attempts:
                sleep(backoff * 2 ** (attempt - 1))
    raise RuntimeError(f"GET {url} failed after {max_attempts} attempts") from last_exc
```
In `run_cli`, change the normalize branch's call to pass a path:
```python
        from pathlib import Path as _Path  # if Path not already imported at top
        with open(args.path, "rb"):  # existence check optional; remove if undesired
            pass
        for line_obj in []:  # no-op placeholder removed below
            pass
```
(Keep it simple — the actual change is one line.) Replace the body of the `normalize`
branch with:
```python
        write_ndjson(normalize(Path(args.path), fetched_at=fetched))
```
`Path` is already imported in `adapter_base.py`. The `SnapshotMetadata`/`fetched_at` resolution
above the call is unchanged.

- [ ] **Step 4: Update the Wikidata adapter `normalize`**

`sources/wikidata_museums/adapter.py`:
```python
def normalize(path: Path, *, fetched_at: datetime) -> Iterator[SourcePOI]:
    with path.open("rb") as fh:
        data = json.load(fh)  # adapter-specific: Wikidata JSON read fully into memory
    # ... rest of the consolidation logic unchanged ...
```
Change the import `from typing import BinaryIO` → remove if unused (ruff will tell you); `Path`
is already imported.

- [ ] **Step 5: Update the `_template` adapter signature**

`sources/_template/adapter.py`:
```python
def normalize(path: Path, *, fetched_at: datetime) -> Iterator[SourcePOI]:
    raise NotImplementedError("read `path` and map records to SourcePOI objects")
    yield  # pragma: no cover
```
Update the docstring's contract line to `normalize(path, *, fetched_at) -> Iterator[SourcePOI]`.
Remove the now-unused `BinaryIO` import if present.

- [ ] **Step 6: Green + quality bar + commit**

Run: `uv run ruff check . && uv run mypy data_pipeline sources && uv run pytest -q`
Expected: all green (≈43 passed).

```bash
git add -A
git commit -m "refactor: path-based normalize contract + retrying streamed download"
```

---

### Task 2: Reprojection helper (RD → WGS84)

**Files:**
- Create: `data_pipeline/geo.py`
- Test: `tests/test_geo.py`

**Interfaces:**
- Produces: `data_pipeline.geo.rd_to_wgs84(x: float, y: float) -> tuple[float, float]` returning
  `(lat, lon)` (note: returns lat, lon — adapters consume that order).

- [ ] **Step 1: Add deps**

Run: `uv add osmium pyproj`
Expected: updates `pyproject.toml` + `uv.lock`.

- [ ] **Step 2: Write the failing test**

`tests/test_geo.py`:
```python
from data_pipeline.geo import rd_to_wgs84


def test_rd_centre_of_nl():
    # RD (155000, 463000) is ~the geodetic anchor near Amersfoort.
    lat, lon = rd_to_wgs84(155000.0, 463000.0)
    assert abs(lat - 52.1552) < 0.01
    assert abs(lon - 5.3872) < 0.01
```

- [ ] **Step 3: Run to verify it fails**

Run: `uv run pytest tests/test_geo.py -q`
Expected: FAIL (`ModuleNotFoundError: data_pipeline.geo`).

- [ ] **Step 4: Implement**

`data_pipeline/geo.py`:
```python
from __future__ import annotations

from functools import lru_cache

import pyproj


@lru_cache(maxsize=1)
def _transformer() -> pyproj.Transformer:
    # always_xy=True => transform takes (x=easting/lon, y=northing/lat)
    return pyproj.Transformer.from_crs("EPSG:28992", "EPSG:4326", always_xy=True)


def rd_to_wgs84(x: float, y: float) -> tuple[float, float]:
    """Dutch RD (EPSG:28992) easting/northing -> (lat, lon) in WGS84."""
    lon, lat = _transformer().transform(x, y)
    return lat, lon
```

- [ ] **Step 5: Green + quality bar + commit**

Run: `uv run pytest tests/test_geo.py -q` → PASS, then the full bar.
```bash
git add data_pipeline/geo.py tests/test_geo.py pyproject.toml uv.lock
git commit -m "feat: add RD->WGS84 reprojection helper + osmium/pyproj deps"
```

---

### Task 3: RCE "Musea in Nederland" adapter (WFS GeoJSON + reprojection)

**Files:**
- Create: `sources/rce_musea/__init__.py`, `sources/rce_musea/manifest.yaml`, `sources/rce_musea/adapter.py`
- Test: `tests/test_rce_musea.py`, fixture `tests/fixtures/rce_musea_response.json`

**Interfaces:**
- `snapshot(output, *, client) -> SnapshotMetadata`, `normalize(path, *, fetched_at) -> Iterator[SourcePOI]`
- Source id `rce-musea`; category `museum`; reprojects RD→WGS84 when coords are in EPSG:28992.

- [ ] **Step 1: Manifest**

`sources/rce_musea/manifest.yaml`:
```yaml
schema_version: 1
id: rce-musea
name: RCE Musea in Nederland
country: nl
endpoint: "https://services.rce.geovoorziening.nl/Veiligheid_van_Erfgoed/wfs"
license: CC0-1.0
license_url: "https://creativecommons.org/publicdomain/zero/1.0/"
license_evidence_date: "2026-06-19"
republication_terms: "Public domain (CC0); no attribution required"
attribution: null
runtime: github-action
update_frequency: monthly
expected_count: [400, 800]
contact_policy: "User-Agent with contact; honor 429/Retry-After"
category_map:
  "overzichtmusea": [museum]
entrypoint: adapter.py
```

- [ ] **Step 2: Fixture** — a 2-feature GeoJSON in EPSG:28992 (RD), as the WFS returns by default.

`tests/fixtures/rce_musea_response.json`:
```json
{
  "type": "FeatureCollection",
  "crs": {"type": "name", "properties": {"name": "urn:ogc:def:crs:EPSG::28992"}},
  "features": [
    {"type": "Feature", "id": "overzichtmusea.1",
     "geometry": {"type": "Point", "coordinates": [121687.0, 487462.0]},
     "properties": {"naam": "Rijksmuseum", "plaats": "Amsterdam", "postcode": "1071 ZC"}},
    {"type": "Feature", "id": "overzichtmusea.2",
     "geometry": {"type": "Point", "coordinates": [136502.0, 455849.0]},
     "properties": {"naam": "Spoorwegmuseum", "plaats": "Utrecht", "postcode": "3581 XW"}}
  ]
}
```

- [ ] **Step 3: Failing test**

`tests/test_rce_musea.py`:
```python
from datetime import datetime, timezone
from pathlib import Path

from sources.rce_musea.adapter import MANIFEST, normalize

FIXTURE = Path(__file__).parent / "fixtures" / "rce_musea_response.json"
FIXED = datetime(2026, 6, 19, tzinfo=timezone.utc)


def test_normalize_reprojects_and_maps():
    pois = list(normalize(FIXTURE, fetched_at=FIXED))
    assert len(pois) == 2
    p = pois[0]
    assert p.source_id == "rce-musea"
    assert p.source_record_id == "overzichtmusea.1"
    assert p.name == "Rijksmuseum"
    assert p.categories == ["museum"]
    assert p.country == "nl"
    # RD (121687, 487462) ~ Amsterdam centre
    assert abs(p.lat - 52.36) < 0.05
    assert abs(p.lon - 4.89) < 0.05
    assert p.address == {"city": "Amsterdam", "postcode": "1071 ZC"}
    assert p.field_provenance["lat"] == "rce-musea"


def test_manifest_country_and_id():
    assert MANIFEST.id == "rce-musea"
```

- [ ] **Step 4: Run to verify it fails** → `uv run pytest tests/test_rce_musea.py -q` (ModuleNotFound).

- [ ] **Step 5: Implement**

`sources/rce_musea/__init__.py` (empty).

`sources/rce_musea/adapter.py`:
```python
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
from data_pipeline.schema import Address, SourcePOI

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
            address=Address(**addr) if addr else None,
            fetched_at=fetched_at, field_provenance=prov,
        )


if __name__ == "__main__":
    run_cli(snapshot, normalize)
```

- [ ] **Step 6: Green + quality bar + commit**
```bash
git add sources/rce_musea tests/test_rce_musea.py tests/fixtures/rce_musea_response.json
git commit -m "feat: add RCE musea adapter (WFS GeoJSON, RD->WGS84)"
```

---

### Task 4: Den Haag playgrounds adapter (Opendatasoft GeoJSON)

**Files:**
- Create: `sources/den_haag_speeltuinen/__init__.py`, `manifest.yaml`, `adapter.py`
- Test: `tests/test_den_haag_speeltuinen.py`, fixture `tests/fixtures/den_haag_response.json`

**Interfaces:**
- `snapshot`/`normalize` as above; source id `den-haag-speeltuinen`; category `playground`;
  Opendatasoft GeoJSON export is already WGS84 (lon, lat order).

- [ ] **Step 1: Manifest**

`sources/den_haag_speeltuinen/manifest.yaml`:
```yaml
schema_version: 1
id: den-haag-speeltuinen
name: Gemeente Den Haag speelplaatsen
country: nl
endpoint: "https://den-haag-opendata.opendatasoft.com/api/explore/v2.1/catalog/datasets/speelplaatsen/exports/geojson"
license: CC-BY-4.0
license_url: "https://creativecommons.org/licenses/by/4.0/"
license_evidence_date: "2026-06-19"
republication_terms: "Attribute Gemeente Den Haag; redistribution allowed"
attribution: "© Gemeente Den Haag"
runtime: github-action
update_frequency: monthly
expected_count: [100, 2000]
contact_policy: "User-Agent with contact; honor 429/Retry-After"
category_map:
  "speelplaats": [playground]
entrypoint: adapter.py
```

- [ ] **Step 2: Fixture** — Opendatasoft GeoJSON (WGS84), Point + a Polygon (centroid needed).

`tests/fixtures/den_haag_response.json`:
```json
{
  "type": "FeatureCollection",
  "features": [
    {"type": "Feature",
     "geometry": {"type": "Point", "coordinates": [4.300, 52.070]},
     "properties": {"straatnaam": "Laan van Meerdervoort", "buurt": "Vruchtenbuurt"}},
    {"type": "Feature",
     "geometry": {"type": "Polygon", "coordinates": [[[4.30,52.07],[4.302,52.07],[4.302,52.072],[4.30,52.072],[4.30,52.07]]]},
     "properties": {"straatnaam": "Thomsonlaan"}}
  ]
}
```

- [ ] **Step 3: Failing test**

`tests/test_den_haag_speeltuinen.py`:
```python
from datetime import datetime, timezone
from pathlib import Path

from sources.den_haag_speeltuinen.adapter import normalize

FIXTURE = Path(__file__).parent / "fixtures" / "den_haag_response.json"
FIXED = datetime(2026, 6, 19, tzinfo=timezone.utc)


def test_point_and_polygon_centroid():
    pois = list(normalize(FIXTURE, fetched_at=FIXED))
    assert len(pois) == 2
    assert pois[0].categories == ["playground"]
    assert pois[0].source_id == "den-haag-speeltuinen"
    assert abs(pois[0].lat - 52.070) < 1e-6 and abs(pois[0].lon - 4.300) < 1e-6
    # polygon centroid ~ middle of the square
    assert abs(pois[1].lat - 52.071) < 1e-3 and abs(pois[1].lon - 4.301) < 1e-3
    # stable per-feature id derived from index when no source id field
    assert pois[0].source_record_id == "den-haag-speeltuinen:0"
```

- [ ] **Step 4: Run to verify it fails.**

- [ ] **Step 5: Implement**

`sources/den_haag_speeltuinen/__init__.py` (empty).

`sources/den_haag_speeltuinen/adapter.py`:
```python
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
```

- [ ] **Step 6: Green + quality bar + commit**
```bash
git add sources/den_haag_speeltuinen tests/test_den_haag_speeltuinen.py tests/fixtures/den_haag_response.json
git commit -m "feat: add Den Haag playgrounds adapter (Opendatasoft GeoJSON)"
```

---

### Task 5: Eindhoven playgrounds adapter (Opendatasoft GeoJSON)

**Files:**
- Create: `sources/eindhoven_speeltuinen/__init__.py`, `manifest.yaml`, `adapter.py`
- Create: `data_pipeline/geojson.py` (shared `representative_point`, extracted from Task 4)
- Modify: `sources/den_haag_speeltuinen/adapter.py` to import the shared helper (DRY)
- Test: `tests/test_eindhoven_speeltuinen.py`, `tests/test_geojson.py`, fixture `tests/fixtures/eindhoven_response.json`

**Interfaces:**
- Produces: `data_pipeline.geojson.representative_point(geom: dict) -> tuple[float, float]` (lat, lon)
- Eindhoven adapter mirrors Den Haag (id `eindhoven-speeltuinen`, category `playground`).

- [ ] **Step 1: Extract the shared helper (DRY) with its own test**

Create `data_pipeline/geojson.py` containing `representative_point` (move the body from Den Haag's
`_representative_point` verbatim). Add `tests/test_geojson.py`:
```python
import pytest

from data_pipeline.geojson import representative_point


def test_point():
    assert representative_point({"type": "Point", "coordinates": [4.3, 52.07]}) == (52.07, 4.3)


def test_polygon_centroid():
    lat, lon = representative_point({"type": "Polygon", "coordinates": [
        [[4.30, 52.07], [4.302, 52.07], [4.302, 52.072], [4.30, 52.072], [4.30, 52.07]]]})
    assert abs(lat - 52.071) < 1e-9 and abs(lon - 4.301) < 1e-9


def test_unsupported_raises():
    with pytest.raises(ValueError):
        representative_point({"type": "LineString", "coordinates": [[0, 0], [1, 1]]})
```
Then update `sources/den_haag_speeltuinen/adapter.py` to `from data_pipeline.geojson import
representative_point` and delete its local `_representative_point`. Run the Den Haag test to
confirm it still passes.

- [ ] **Step 2: Eindhoven manifest**

`sources/eindhoven_speeltuinen/manifest.yaml`:
```yaml
schema_version: 1
id: eindhoven-speeltuinen
name: Gemeente Eindhoven speelplekken
country: nl
endpoint: "https://data.eindhoven.nl/api/explore/v2.1/catalog/datasets/speelplekken/exports/geojson"
license: CC-BY-4.0
license_url: "https://creativecommons.org/licenses/by/4.0/"
license_evidence_date: "2026-06-19"
republication_terms: "Attribute Gemeente Eindhoven; redistribution allowed"
attribution: "© Gemeente Eindhoven"
runtime: github-action
update_frequency: monthly
expected_count: [50, 2000]
contact_policy: "User-Agent with contact; honor 429/Retry-After"
category_map:
  "speelplek": [playground]
entrypoint: adapter.py
```

- [ ] **Step 3: Fixture**

`tests/fixtures/eindhoven_response.json`:
```json
{
  "type": "FeatureCollection",
  "features": [
    {"type": "Feature",
     "geometry": {"type": "Point", "coordinates": [5.478, 51.441]},
     "properties": {"straatnaam": "Stratumsedijk", "naam": "Speeltuin Stratum"}}
  ]
}
```

- [ ] **Step 4: Failing test**

`tests/test_eindhoven_speeltuinen.py`:
```python
from datetime import datetime, timezone
from pathlib import Path

from sources.eindhoven_speeltuinen.adapter import normalize

FIXTURE = Path(__file__).parent / "fixtures" / "eindhoven_response.json"
FIXED = datetime(2026, 6, 19, tzinfo=timezone.utc)


def test_normalize():
    pois = list(normalize(FIXTURE, fetched_at=FIXED))
    assert len(pois) == 1
    assert pois[0].source_id == "eindhoven-speeltuinen"
    assert pois[0].categories == ["playground"]
    assert pois[0].name == "Speeltuin Stratum"
    assert abs(pois[0].lat - 51.441) < 1e-6 and abs(pois[0].lon - 5.478) < 1e-6
```

- [ ] **Step 5: Implement** — `sources/eindhoven_speeltuinen/adapter.py` is the Den Haag adapter
with the manifest path being its own folder's `manifest.yaml` and `name` falling back to
`props.get("naam") or props.get("straatnaam")`. (Copy Den Haag's adapter, change nothing but the
`__init__.py` empty file and rely on `MANIFEST` loading from the adjacent manifest. The
`representative_point` import and the rest are identical.)

`sources/eindhoven_speeltuinen/__init__.py` (empty), and the adapter:
```python
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


def normalize(path: Path, *, fetched_at: datetime) -> Iterator[SourcePOI]:
    with path.open("rb") as fh:
        data = json.load(fh)
    for i, feat in enumerate(data["features"]):
        lat, lon = representative_point(feat["geometry"])
        props = feat.get("properties", {})
        name = props.get("naam") or props.get("straatnaam") or f"Speelplek {i}"
        yield SourcePOI(
            source_id=MANIFEST.id, source_record_id=f"{MANIFEST.id}:{i}", name=name,
            categories=list(CATEGORIES), lat=lat, lon=lon, country=MANIFEST.country,
            fetched_at=fetched_at,
            field_provenance={"name": MANIFEST.id, "lat": MANIFEST.id, "lon": MANIFEST.id},
        )


if __name__ == "__main__":
    run_cli(snapshot, normalize)
```

- [ ] **Step 6: Green + quality bar + commit**
```bash
git add data_pipeline/geojson.py tests/test_geojson.py sources/den_haag_speeltuinen/adapter.py sources/eindhoven_speeltuinen tests/test_eindhoven_speeltuinen.py tests/fixtures/eindhoven_response.json
git commit -m "feat: add Eindhoven adapter + shared geojson representative_point helper"
```

---

### Task 6: OSM adapter (osmium, multi-category via manifest)

**Files:**
- Create: `sources/osm/__init__.py`, `sources/osm/manifest.yaml`, `sources/osm/adapter.py`
- Test: `tests/test_osm.py`, fixture `tests/fixtures/osm_sample.osm` (XML — osmium reads it)

**Interfaces:**
- `snapshot` downloads the Geofabrik `.pbf` (streamed, with retry — Task 1's `download`).
- `normalize(path, *, fetched_at)` uses `osmium.FileProcessor(str(path)).with_locations()`,
  maps OSM `key=value` tags to categories via `MANIFEST.category_map`, computes way centroids,
  and emits one `SourcePOI` per matched node/way. **Multi-category, manifest-driven.**

- [ ] **Step 1: Manifest** (category_map keyed by `key=value`; `zoo=petting_zoo` wins over `tourism=zoo`)

`sources/osm/manifest.yaml`:
```yaml
schema_version: 1
id: osm
name: OpenStreetMap (NL)
country: nl
endpoint: "https://download.geofabrik.de/europe/netherlands-latest.osm.pbf"
license: ODbL
license_url: "https://opendatacommons.org/licenses/odbl/1-0/"
license_evidence_date: "2026-06-19"
republication_terms: "ODbL share-alike; attribute © OpenStreetMap contributors"
attribution: "© OpenStreetMap contributors"
runtime: github-action
update_frequency: weekly
expected_count: [30000, 60000]
contact_policy: "User-Agent with contact; honor 429/Retry-After"
category_map:
  "leisure=playground": [playground]
  "tourism=zoo": [zoo]
  "zoo=petting_zoo": [petting_zoo]
  "leisure=water_park": [play_park]
entrypoint: adapter.py
```

- [ ] **Step 2: Fixture** — small OSM XML with a playground node, a petting-zoo way, a plain node
to ignore.

`tests/fixtures/osm_sample.osm`:
```xml
<?xml version="1.0" encoding="UTF-8"?>
<osm version="0.6" generator="test">
  <node id="1" lat="52.36" lon="4.885" version="1">
    <tag k="leisure" v="playground"/>
    <tag k="name" v="Speeltuin Vondelpark"/>
  </node>
  <node id="2" lat="52.0" lon="5.0" version="1"/>
  <node id="3" lat="52.002" lon="5.0" version="1"/>
  <node id="4" lat="52.002" lon="5.004" version="1"/>
  <node id="5" lat="52.0" lon="5.004" version="1"/>
  <way id="100" version="1">
    <nd ref="2"/><nd ref="3"/><nd ref="4"/><nd ref="5"/><nd ref="2"/>
    <tag k="tourism" v="zoo"/>
    <tag k="zoo" v="petting_zoo"/>
    <tag k="name" v="Kinderboerderij De Buurt"/>
  </way>
  <node id="9" lat="52.1" lon="5.1" version="1">
    <tag k="amenity" v="bench"/>
  </node>
</osm>
```

- [ ] **Step 3: Failing test**

`tests/test_osm.py`:
```python
from datetime import datetime, timezone
from pathlib import Path

from sources.osm.adapter import normalize

FIXTURE = Path(__file__).parent / "fixtures" / "osm_sample.osm"
FIXED = datetime(2026, 6, 19, tzinfo=timezone.utc)


def test_maps_node_and_way_skips_unmatched():
    pois = {p.source_record_id: p for p in normalize(FIXTURE, fetched_at=FIXED)}
    assert set(pois) == {"node/1", "way/100"}  # bench node ignored

    play = pois["node/1"]
    assert play.categories == ["playground"]
    assert play.name == "Speeltuin Vondelpark"
    assert abs(play.lat - 52.36) < 1e-6 and abs(play.lon - 4.885) < 1e-6
    assert play.source_id == "osm"

    zoo = pois["way/100"]
    # petting_zoo wins; zoo also present -> both, deduped/ordered
    assert set(zoo.categories) == {"zoo", "petting_zoo"}
    assert abs(zoo.lat - 52.001) < 1e-3 and abs(zoo.lon - 5.002) < 1e-3
```

- [ ] **Step 4: Run to verify it fails.**

- [ ] **Step 5: Implement**

`sources/osm/__init__.py` (empty).

`sources/osm/adapter.py`:
```python
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
        if obj.is_node():
            if not obj.location.valid():
                continue
            lat, lon, kind = obj.location.lat, obj.location.lon, "node"
        elif obj.is_way():
            c = _way_centroid(obj)
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
```

- [ ] **Step 6: Green + quality bar + commit**

Note: if mypy complains about `osmium` types, the project's mypy config already sets
`ignore_missing_imports = true`, so the `import osmium` is fine.

```bash
git add sources/osm tests/test_osm.py tests/fixtures/osm_sample.osm
git commit -m "feat: add OSM adapter (osmium, manifest-driven multi-category)"
```

---

## Self-Review

**Spec coverage (Plan 2 = the remaining MVP adapters, spec §8 + §5 + §4 reprojection):**
- Path-based `normalize` contract evolution (needed for osmium) → Task 1 ✓
- Retrying streamed `download` (the Plan 1 review's noted gap, needed for the 1.3 GB `.pbf`) → Task 1 ✓
- RD→WGS84 reprojection (spec §8 RCE note) → Task 2 ✓
- RCE Musea (CC0, WFS GeoJSON) → Task 3 ✓
- Den Haag + Eindhoven (CC-BY, Opendatasoft) → Tasks 4, 5 ✓
- OSM (ODbL, osmium, manifest-driven multi-category incl. `zoo=petting_zoo`) → Task 6 ✓
- All adapters manifest-driven (no hard-coded categories) → every task ✓
- museum.nl deliberately NOT in this plan (release-gated, spec §11).

**Placeholder scan:** none. Verified API patterns (pyproj/osmium) were run on this machine before
writing. The Step-3 `run_cli` snippet's placeholder lines are explanatory; the real change is the
single `write_ndjson(normalize(Path(args.path), ...))` line — the implementer applies that line.

**Type consistency:** `normalize(path: Path, *, fetched_at) -> Iterator[SourcePOI]` is identical
across all adapters and the template after Task 1. `download(..., max_attempts, backoff)` matches
Task 1's signature. `representative_point` (Task 5) is consumed by Den Haag + Eindhoven with the
same `(lat, lon)` return contract. `rd_to_wgs84` returns `(lat, lon)`, consumed correctly in Task 3.

## Notes for later plans
- **OSM node-location memory:** `with_locations()` uses an in-memory index; at full-NL `.pbf`
  scale this needs several GB RAM. Fine on GitHub Actions/Codespace runners; if it OOMs, switch to
  a disk-backed index (`node_store='sparse_file_array,<path>'` via `osmium.NodeLocationsForWays`).
  Flagged for Plan 6 (CI), not a correctness issue for the fixture-scale tests.
- **Opendatasoft/RCE endpoints** were verified live on 2026-06-19; the implementer should expect to
  adapt property field names (`naam`/`straatnaam`/`plaats`) if a live snapshot differs from the fixture.
