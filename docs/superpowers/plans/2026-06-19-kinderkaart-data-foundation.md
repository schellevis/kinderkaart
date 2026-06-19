# Kinderkaart Data Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the typed POI schema, the source-adapter contract, and one working
end-to-end adapter, so every later subsystem (dedup, build, search, front-end) has a
validated data contract and a reproducible way to produce normalized POIs.

**Architecture:** Python pipeline package (`data_pipeline/`) holds the shared POI schema,
the manifest model, and adapter base utilities (HTTP with retries, NDJSON CLI runner).
Each data source is a self-contained package under `sources/<id>/` with a `manifest.yaml`
and an `adapter.py` exposing two pure-ish steps — `snapshot()` (fetch raw bytes) and
`normalize(raw)` (stream validated `POI` objects). This plan delivers the schema, the
contract, a copyable `_template`, and the Wikidata-museums adapter as the first concrete
implementation.

**Tech Stack:** Python 3.13, uv, pydantic v2, httpx, PyYAML, pytest.

## Global Constraints

- Python `>=3.13` (from `pyproject.toml`); manage deps with `uv`.
- POI `country` is ISO 3166-1 alpha-2, **lowercase** (e.g. `nl`).
- Categories are restricted to the fixed vocabulary: `playground`, `museum`, `zoo`,
  `petting_zoo`, `pool`, `play_park`, `restaurant_kidfriendly`.
- "Unknown" is `null`, never `false` — optional facet fields default to `None`.
- Adapters expose exactly two CLI subcommands: `snapshot` and `normalize`.
- `normalize` accepts an injectable `fetched_at` so tests are deterministic.
- All outbound HTTP sends the shared `User-Agent` and honors `429`/`Retry-After`.
- Run tests with `uv run pytest`. Commit after every green task.

---

### Task 1: Project setup + POI/Image schema

**Files:**
- Modify: `pyproject.toml`
- Create: `data_pipeline/__init__.py`
- Create: `data_pipeline/categories.py`
- Create: `data_pipeline/schema.py`
- Test: `tests/test_schema.py`

**Interfaces:**
- Produces: `data_pipeline.categories.CATEGORIES: set[str]`
- Produces: `data_pipeline.schema.Image` (pydantic model: `url, source_page, author|None, license, license_url`)
- Produces: `data_pipeline.schema.POI` (pydantic model, fields per spec §4; `fetched_at: datetime` required, optional facets default `None`, `categories: list[str]` validated against `CATEGORIES`, `country` ISO-alpha-2 lowercase, `lat`/`lon` range-checked)

- [ ] **Step 1: Add dependencies and pytest config to `pyproject.toml`**

```toml
[project]
name = "kinderkaart"
version = "0.1.0"
description = "Map of fun things to do with kids"
readme = "README.md"
requires-python = ">=3.13"
dependencies = [
    "pydantic>=2.7",
    "httpx>=0.27",
    "pyyaml>=6.0",
]

[tool.uv]
dev-dependencies = ["pytest>=8"]

[tool.pytest.ini_options]
pythonpath = ["."]
testpaths = ["tests"]
```

- [ ] **Step 2: Create the category vocabulary**

`data_pipeline/__init__.py` (empty file).

`data_pipeline/categories.py`:
```python
"""The fixed, language-independent category vocabulary (spec §13)."""

CATEGORIES: set[str] = {
    "playground",
    "museum",
    "zoo",
    "petting_zoo",
    "pool",
    "play_park",
    "restaurant_kidfriendly",
}
```

- [ ] **Step 3: Write the failing schema test**

`tests/test_schema.py`:
```python
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from data_pipeline.schema import POI, Image


def _base_poi(**overrides):
    data = dict(
        poi_id="wikidata:Q123",
        name="Test Museum",
        categories=["museum"],
        lat=52.09,
        lon=5.12,
        country="nl",
        fetched_at=datetime(2026, 6, 19, tzinfo=timezone.utc),
    )
    data.update(overrides)
    return data


def test_minimal_poi_validates_and_defaults_unknown_to_none():
    poi = POI(**_base_poi())
    assert poi.poi_id == "wikidata:Q123"
    assert poi.indoor is None  # unknown != false
    assert poi.free is None
    assert poi.images == []
    assert poi.external_ids == {}


def test_unknown_category_rejected():
    with pytest.raises(ValidationError):
        POI(**_base_poi(categories=["spaceport"]))


def test_empty_categories_rejected():
    with pytest.raises(ValidationError):
        POI(**_base_poi(categories=[]))


def test_country_must_be_lowercase_alpha2():
    with pytest.raises(ValidationError):
        POI(**_base_poi(country="NL"))
    with pytest.raises(ValidationError):
        POI(**_base_poi(country="nld"))


def test_out_of_range_coords_rejected():
    with pytest.raises(ValidationError):
        POI(**_base_poi(lat=200.0))
    with pytest.raises(ValidationError):
        POI(**_base_poi(lon=-999.0))


def test_image_model_requires_license():
    with pytest.raises(ValidationError):
        Image(url="http://x/y.jpg", source_page="http://x")  # missing license/license_url
```

- [ ] **Step 4: Run the test to verify it fails**

Run: `uv run pytest tests/test_schema.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'data_pipeline.schema'`

- [ ] **Step 5: Implement the schema**

`data_pipeline/schema.py`:
```python
from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, Field, field_validator

from data_pipeline.categories import CATEGORIES


class Image(BaseModel):
    url: str
    source_page: str
    author: str | None = None
    license: str
    license_url: str


class POI(BaseModel):
    # Identity (spec §4)
    poi_id: str
    external_ids: dict[str, str] = Field(default_factory=dict)
    aliases: list[str] = Field(default_factory=list)

    # Core
    name: str
    categories: list[str]
    lat: float
    lon: float
    country: str
    address: dict | None = None

    # Canonical facets — unknown is None, never False
    indoor: bool | None = None
    free: bool | None = None
    price_model: str | None = None
    age_min: int | None = None
    age_max: int | None = None
    accessibility: dict | None = None
    opening_hours: str | None = None

    # Media & links
    website: str | None = None
    images: list[Image] = Field(default_factory=list)

    # Provenance
    sources: list[str] = Field(default_factory=list)
    source_urls: dict[str, str] = Field(default_factory=dict)
    field_provenance: dict[str, str] = Field(default_factory=dict)
    source_date: date | None = None
    fetched_at: datetime
    build_version: str | None = None

    @field_validator("categories")
    @classmethod
    def _validate_categories(cls, v: list[str]) -> list[str]:
        if not v:
            raise ValueError("at least one category is required")
        unknown = set(v) - CATEGORIES
        if unknown:
            raise ValueError(f"unknown categories: {sorted(unknown)}")
        return v

    @field_validator("country")
    @classmethod
    def _validate_country(cls, v: str) -> str:
        if len(v) != 2 or not v.islower() or not v.isalpha():
            raise ValueError("country must be ISO 3166-1 alpha-2, lowercase")
        return v

    @field_validator("lat")
    @classmethod
    def _validate_lat(cls, v: float) -> float:
        if not -90.0 <= v <= 90.0:
            raise ValueError("lat out of range")
        return v

    @field_validator("lon")
    @classmethod
    def _validate_lon(cls, v: float) -> float:
        if not -180.0 <= v <= 180.0:
            raise ValueError("lon out of range")
        return v
```

- [ ] **Step 6: Run the test to verify it passes**

Run: `uv run pytest tests/test_schema.py -v`
Expected: PASS (6 passed)

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml data_pipeline/__init__.py data_pipeline/categories.py data_pipeline/schema.py tests/test_schema.py
git commit -m "feat: add typed POI/Image schema and category vocabulary"
```

---

### Task 2: Manifest model + loader

**Files:**
- Create: `data_pipeline/manifest.py`
- Test: `tests/test_manifest.py`
- Test fixture: `tests/fixtures/manifest_valid.yaml`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `data_pipeline.manifest.Manifest` (pydantic model with fields:
  `schema_version: int, id: str, name: str, country: str, endpoint: str|None,
  license: str, license_url: str, attribution: str|None, runtime: str,
  update_frequency: str|None, expected_count: list[int]|None, contact_policy: str|None,
  category_map: dict[str, list[str]], entrypoint: str`)
- Produces: `data_pipeline.manifest.load_manifest(path: str | Path) -> Manifest`

- [ ] **Step 1: Create the fixture manifest**

`tests/fixtures/manifest_valid.yaml`:
```yaml
schema_version: 1
id: wikidata-museums
name: Wikidata museums (NL)
country: nl
endpoint: "https://query.wikidata.org/sparql"
license: CC0-1.0
license_url: "https://creativecommons.org/publicdomain/zero/1.0/"
attribution: null
runtime: github-action
update_frequency: weekly
expected_count: [900, 1300]
contact_policy: "User-Agent with contact; honor 429/Retry-After"
category_map:
  "Q33506": [museum]
entrypoint: adapter.py
```

- [ ] **Step 2: Write the failing manifest test**

`tests/test_manifest.py`:
```python
from pathlib import Path

import pytest
from pydantic import ValidationError

from data_pipeline.manifest import Manifest, load_manifest

FIXTURE = Path(__file__).parent / "fixtures" / "manifest_valid.yaml"


def test_load_valid_manifest():
    m = load_manifest(FIXTURE)
    assert m.id == "wikidata-museums"
    assert m.country == "nl"
    assert m.runtime == "github-action"
    assert m.expected_count == [900, 1300]
    assert m.category_map == {"Q33506": ["museum"]}


def test_invalid_runtime_rejected():
    with pytest.raises(ValidationError):
        Manifest(
            schema_version=1, id="x", name="x", country="nl",
            license="CC0-1.0", license_url="http://x", runtime="lambda",
            entrypoint="adapter.py",
        )


def test_expected_count_must_be_pair():
    with pytest.raises(ValidationError):
        Manifest(
            schema_version=1, id="x", name="x", country="nl",
            license="CC0-1.0", license_url="http://x", runtime="github-action",
            expected_count=[5], entrypoint="adapter.py",
        )
```

- [ ] **Step 3: Run the test to verify it fails**

Run: `uv run pytest tests/test_manifest.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'data_pipeline.manifest'`

- [ ] **Step 4: Implement the manifest model and loader**

`data_pipeline/manifest.py`:
```python
from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, Field, field_validator

RUNTIMES = {"github-action", "codespace-only"}


class Manifest(BaseModel):
    schema_version: int
    id: str
    name: str
    country: str
    endpoint: str | None = None
    license: str
    license_url: str
    attribution: str | None = None
    runtime: str
    update_frequency: str | None = None
    expected_count: list[int] | None = None
    contact_policy: str | None = None
    category_map: dict[str, list[str]] = Field(default_factory=dict)
    entrypoint: str

    @field_validator("runtime")
    @classmethod
    def _validate_runtime(cls, v: str) -> str:
        if v not in RUNTIMES:
            raise ValueError(f"runtime must be one of {sorted(RUNTIMES)}")
        return v

    @field_validator("country")
    @classmethod
    def _validate_country(cls, v: str) -> str:
        if len(v) != 2 or not v.islower() or not v.isalpha():
            raise ValueError("country must be ISO 3166-1 alpha-2, lowercase")
        return v

    @field_validator("expected_count")
    @classmethod
    def _validate_expected_count(cls, v: list[int] | None) -> list[int] | None:
        if v is not None and len(v) != 2:
            raise ValueError("expected_count must be [min, max]")
        return v


def load_manifest(path: str | Path) -> Manifest:
    data = yaml.safe_load(Path(path).read_text())
    return Manifest.model_validate(data)
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `uv run pytest tests/test_manifest.py -v`
Expected: PASS (3 passed)

- [ ] **Step 6: Commit**

```bash
git add data_pipeline/manifest.py tests/test_manifest.py tests/fixtures/manifest_valid.yaml
git commit -m "feat: add source manifest model and loader"
```

---

### Task 3: Adapter base — HTTP helper + NDJSON CLI runner

**Files:**
- Create: `data_pipeline/adapter_base.py`
- Test: `tests/test_adapter_base.py`

**Interfaces:**
- Consumes: `data_pipeline.schema.POI`
- Produces: `data_pipeline.adapter_base.USER_AGENT: str`
- Produces: `http_get(url, *, params=None, headers=None, retries=3, backoff=0.0, timeout=30.0) -> httpx.Response`
  (sends `USER_AGENT`; on `429` sleeps `Retry-After` then retries; raises `RuntimeError` after exhausting retries)
- Produces: `write_ndjson(pois: Iterable[POI], out=sys.stdout) -> int` (one `POI.model_dump_json()` per line; returns count)
- Produces: `run_cli(snapshot: Callable[[], bytes], normalize: Callable[[bytes], Iterable[POI]]) -> None`
  (argparse with `snapshot` and `normalize` subcommands; `snapshot` writes raw bytes to stdout, `normalize` reads stdin bytes and writes NDJSON)

- [ ] **Step 1: Write the failing adapter-base test**

`tests/test_adapter_base.py`:
```python
import io
from datetime import datetime, timezone

import httpx
import pytest

from data_pipeline.adapter_base import USER_AGENT, http_get, write_ndjson
from data_pipeline.schema import POI


def _poi():
    return POI(
        poi_id="wikidata:Q1", name="A", categories=["museum"],
        lat=52.0, lon=5.0, country="nl",
        fetched_at=datetime(2026, 6, 19, tzinfo=timezone.utc),
    )


def test_http_get_sends_user_agent(monkeypatch):
    captured = {}

    def fake_get(url, params=None, headers=None, timeout=None, follow_redirects=None):
        captured["headers"] = headers
        return httpx.Response(200, json={"ok": True}, request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx, "get", fake_get)
    resp = http_get("https://example.test/api")
    assert resp.status_code == 200
    assert captured["headers"]["User-Agent"] == USER_AGENT


def test_http_get_retries_on_429_then_succeeds(monkeypatch):
    calls = {"n": 0}

    def fake_get(url, params=None, headers=None, timeout=None, follow_redirects=None):
        calls["n"] += 1
        req = httpx.Request("GET", url)
        if calls["n"] == 1:
            return httpx.Response(429, headers={"Retry-After": "0"}, request=req)
        return httpx.Response(200, json={"ok": True}, request=req)

    monkeypatch.setattr(httpx, "get", fake_get)
    resp = http_get("https://example.test/api", retries=3)
    assert resp.status_code == 200
    assert calls["n"] == 2


def test_write_ndjson_emits_one_line_per_poi():
    buf = io.StringIO()
    n = write_ndjson([_poi(), _poi()], out=buf)
    lines = buf.getvalue().strip().split("\n")
    assert n == 2
    assert len(lines) == 2
    assert '"poi_id":"wikidata:Q1"' in lines[0]
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/test_adapter_base.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'data_pipeline.adapter_base'`

- [ ] **Step 3: Implement the adapter base**

`data_pipeline/adapter_base.py`:
```python
from __future__ import annotations

import argparse
import sys
import time
from collections.abc import Callable, Iterable

import httpx

from data_pipeline.schema import POI

USER_AGENT = "kinderkaart/0.1 (+https://github.com/joostschellevis/kinderkaart)"


def http_get(
    url: str,
    *,
    params: dict | None = None,
    headers: dict | None = None,
    retries: int = 3,
    backoff: float = 0.0,
    timeout: float = 30.0,
) -> httpx.Response:
    hdrs = {"User-Agent": USER_AGENT}
    if headers:
        hdrs.update(headers)
    last_exc: Exception | None = None
    for attempt in range(retries):
        try:
            resp = httpx.get(
                url, params=params, headers=hdrs, timeout=timeout, follow_redirects=True
            )
            if resp.status_code == 429:
                wait = float(resp.headers.get("Retry-After", backoff * (2**attempt)))
                time.sleep(wait)
                continue
            resp.raise_for_status()
            return resp
        except httpx.HTTPError as exc:
            last_exc = exc
            time.sleep(backoff * (2**attempt))
    raise RuntimeError(f"GET {url} failed after {retries} attempts") from last_exc


def write_ndjson(pois: Iterable[POI], out=sys.stdout) -> int:
    n = 0
    for poi in pois:
        out.write(poi.model_dump_json())
        out.write("\n")
        n += 1
    return n


def run_cli(
    snapshot: Callable[[], bytes],
    normalize: Callable[[bytes], Iterable[POI]],
) -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("snapshot", help="fetch raw source bytes to stdout")
    sub.add_parser("normalize", help="read raw bytes on stdin, stream POI NDJSON")
    args = parser.parse_args()
    if args.cmd == "snapshot":
        sys.stdout.buffer.write(snapshot())
    elif args.cmd == "normalize":
        raw = sys.stdin.buffer.read()
        write_ndjson(normalize(raw))
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `uv run pytest tests/test_adapter_base.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add data_pipeline/adapter_base.py tests/test_adapter_base.py
git commit -m "feat: add adapter base (http_get, write_ndjson, run_cli)"
```

---

### Task 4: Wikidata-museums adapter (first concrete source)

**Files:**
- Create: `sources/__init__.py`
- Create: `sources/wikidata_museums/__init__.py`
- Create: `sources/wikidata_museums/manifest.yaml`
- Create: `sources/wikidata_museums/adapter.py`
- Test: `tests/test_wikidata_museums.py`
- Test fixture: `tests/fixtures/wikidata_museums_response.json`

**Interfaces:**
- Consumes: `data_pipeline.adapter_base.http_get`, `run_cli`; `data_pipeline.schema.POI`
- Produces: `sources.wikidata_museums.adapter.snapshot() -> bytes`
- Produces: `sources.wikidata_museums.adapter.normalize(raw: bytes, *, fetched_at: datetime | None = None) -> Iterator[POI]`
  (each POI: `poi_id=f"wikidata:{qid}"`, `external_ids={"wikidata": qid}`, `categories=["museum"]`,
  `country="nl"`, `sources=["wikidata-museums"]`, coords parsed from the `Point(lon lat)` WKT literal)

- [ ] **Step 1: Create the manifest**

`sources/wikidata_museums/manifest.yaml`:
```yaml
schema_version: 1
id: wikidata-museums
name: Wikidata museums (NL)
country: nl
endpoint: "https://query.wikidata.org/sparql"
license: CC0-1.0
license_url: "https://creativecommons.org/publicdomain/zero/1.0/"
attribution: null
runtime: github-action
update_frequency: weekly
expected_count: [900, 1300]
contact_policy: "User-Agent with contact; honor 429/Retry-After"
category_map:
  "Q33506": [museum]
entrypoint: adapter.py
```

- [ ] **Step 2: Create the response fixture**

`tests/fixtures/wikidata_museums_response.json`:
```json
{
  "results": {
    "bindings": [
      {
        "item": {"type": "uri", "value": "http://www.wikidata.org/entity/Q190804"},
        "itemLabel": {"type": "literal", "value": "Rijksmuseum"},
        "coord": {"type": "literal", "value": "Point(4.885278 52.36)"},
        "website": {"type": "uri", "value": "https://www.rijksmuseum.nl/"}
      },
      {
        "item": {"type": "uri", "value": "http://www.wikidata.org/entity/Q1129456"},
        "itemLabel": {"type": "literal", "value": "Spoorwegmuseum"},
        "coord": {"type": "literal", "value": "Point(5.13 52.0907)"}
      }
    ]
  }
}
```

- [ ] **Step 3: Write the failing adapter test**

`tests/test_wikidata_museums.py`:
```python
from datetime import datetime, timezone
from pathlib import Path

from sources.wikidata_museums.adapter import normalize

FIXTURE = Path(__file__).parent / "fixtures" / "wikidata_museums_response.json"
FIXED = datetime(2026, 6, 19, tzinfo=timezone.utc)


def test_normalize_maps_bindings_to_pois():
    raw = FIXTURE.read_bytes()
    pois = list(normalize(raw, fetched_at=FIXED))
    assert len(pois) == 2

    first = pois[0]
    assert first.poi_id == "wikidata:Q190804"
    assert first.external_ids == {"wikidata": "Q190804"}
    assert first.name == "Rijksmuseum"
    assert first.categories == ["museum"]
    assert first.country == "nl"
    # WKT is Point(lon lat) -> lat=52.36, lon=4.885278
    assert first.lat == 52.36
    assert first.lon == 4.885278
    assert first.website == "https://www.rijksmuseum.nl/"
    assert first.sources == ["wikidata-museums"]
    assert first.fetched_at == FIXED


def test_normalize_handles_missing_optional_website():
    raw = FIXTURE.read_bytes()
    pois = list(normalize(raw, fetched_at=FIXED))
    assert pois[1].website is None
```

- [ ] **Step 4: Run the test to verify it fails**

Run: `uv run pytest tests/test_wikidata_museums.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'sources.wikidata_museums'`

- [ ] **Step 5: Implement the adapter**

`sources/__init__.py` (empty file).
`sources/wikidata_museums/__init__.py` (empty file).

`sources/wikidata_museums/adapter.py`:
```python
from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import datetime, timezone

from data_pipeline.adapter_base import http_get, run_cli
from data_pipeline.schema import POI

ENDPOINT = "https://query.wikidata.org/sparql"
SOURCE_ID = "wikidata-museums"

SPARQL = """
SELECT ?item ?itemLabel ?coord ?website WHERE {
  ?item wdt:P31/wdt:P279* wd:Q33506 .
  ?item wdt:P17 wd:Q55 .
  ?item wdt:P625 ?coord .
  OPTIONAL { ?item wdt:P856 ?website . }
  SERVICE wikibase:label { bd:serviceParam wikibase:language "nl,en". }
}
"""


def snapshot() -> bytes:
    resp = http_get(ENDPOINT, params={"query": SPARQL, "format": "json"})
    return resp.content


def _parse_point(wkt: str) -> tuple[float, float]:
    """'Point(lon lat)' -> (lat, lon)."""
    inner = wkt[wkt.index("(") + 1 : wkt.index(")")]
    lon_s, lat_s = inner.split()
    return float(lat_s), float(lon_s)


def normalize(raw: bytes, *, fetched_at: datetime | None = None) -> Iterator[POI]:
    fetched = fetched_at or datetime.now(timezone.utc)
    data = json.loads(raw)
    for b in data["results"]["bindings"]:
        qid = b["item"]["value"].rsplit("/", 1)[-1]
        lat, lon = _parse_point(b["coord"]["value"])
        website = b.get("website", {}).get("value")
        yield POI(
            poi_id=f"wikidata:{qid}",
            external_ids={"wikidata": qid},
            name=b.get("itemLabel", {}).get("value", qid),
            categories=["museum"],
            lat=lat,
            lon=lon,
            country="nl",
            website=website,
            sources=[SOURCE_ID],
            source_urls={SOURCE_ID: b["item"]["value"]},
            field_provenance={"name": SOURCE_ID, "lat": SOURCE_ID, "lon": SOURCE_ID},
            fetched_at=fetched,
        )


if __name__ == "__main__":
    run_cli(snapshot, normalize)
```

- [ ] **Step 6: Run the test to verify it passes**

Run: `uv run pytest tests/test_wikidata_museums.py -v`
Expected: PASS (2 passed)

- [ ] **Step 7: Verify the CLI contract end-to-end against the fixture**

Run: `uv run python -m sources.wikidata_museums.adapter normalize < tests/fixtures/wikidata_museums_response.json | head -n 1`
Expected: a single JSON line starting with `{"poi_id":"wikidata:Q190804"`

- [ ] **Step 8: Commit**

```bash
git add sources/__init__.py sources/wikidata_museums tests/test_wikidata_museums.py tests/fixtures/wikidata_museums_response.json
git commit -m "feat: add wikidata-museums adapter (first source)"
```

---

### Task 5: Copyable `_template` source + manifest validation guard

**Files:**
- Create: `sources/_template/manifest.yaml`
- Create: `sources/_template/adapter.py`
- Create: `sources/_template/README.md`
- Test: `tests/test_sources_manifests.py`

**Interfaces:**
- Consumes: `data_pipeline.manifest.load_manifest`
- Produces: a documented starting point an LLM/agent copies to add a new source.

- [ ] **Step 1: Create the template manifest**

`sources/_template/manifest.yaml`:
```yaml
schema_version: 1
id: my-source-id            # unique, kebab-case
name: Human readable name
country: nl
endpoint: "https://example.com/data"   # or null for codespace-only/agent sources
license: CC-BY-4.0
license_url: "https://creativecommons.org/licenses/by/4.0/"
attribution: "© Source name"
runtime: github-action      # or: codespace-only
update_frequency: weekly
expected_count: [100, 5000]
contact_policy: "User-Agent with contact; honor 429/Retry-After"
category_map:
  "source-type-key": [playground]   # source key -> our categories
entrypoint: adapter.py
```

- [ ] **Step 2: Create the template adapter stub**

`sources/_template/adapter.py`:
```python
"""Template adapter. Copy this folder to sources/<your-id>/ and fill in.

Contract (spec §5):
  snapshot()  -> raw source bytes (also written to stdout by the CLI)
  normalize(raw, *, fetched_at=None) -> Iterator[POI]  (validated, streamed as NDJSON)
"""
from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime, timezone

from data_pipeline.adapter_base import http_get, run_cli  # noqa: F401
from data_pipeline.schema import POI

SOURCE_ID = "my-source-id"


def snapshot() -> bytes:
    raise NotImplementedError("fetch raw source bytes here")


def normalize(raw: bytes, *, fetched_at: datetime | None = None) -> Iterator[POI]:
    fetched = fetched_at or datetime.now(timezone.utc)
    raise NotImplementedError("map raw records to POI objects here")
    yield  # pragma: no cover  (makes this a generator)


if __name__ == "__main__":
    run_cli(snapshot, normalize)
```

- [ ] **Step 3: Create the template README**

`sources/_template/README.md`:
```markdown
# Source template

1. Copy this folder to `sources/<your-id>/`.
2. Edit `manifest.yaml` (id, license, runtime, category_map, expected_count).
3. Implement `snapshot()` and `normalize()` in `adapter.py`.
4. Add `tests/test_<your_id>.py` with a small fixture and assert `normalize` output.
5. Run `uv run pytest`.
```

- [ ] **Step 4: Write the failing manifest-guard test**

`tests/test_sources_manifests.py`:
```python
from pathlib import Path

from data_pipeline.manifest import load_manifest

SOURCES_DIR = Path(__file__).parent.parent / "sources"


def _manifest_paths():
    return [
        p
        for p in SOURCES_DIR.glob("*/manifest.yaml")
        if p.parent.name != "_template"
    ]


def test_every_real_source_manifest_validates():
    paths = _manifest_paths()
    assert paths, "expected at least one real source manifest"
    for path in paths:
        load_manifest(path)  # raises ValidationError on a broken manifest


def test_source_ids_are_unique():
    ids = [load_manifest(p).id for p in _manifest_paths()]
    assert len(ids) == len(set(ids)), f"duplicate source ids: {ids}"
```

- [ ] **Step 5: Run the test to verify it fails, then passes**

Run: `uv run pytest tests/test_sources_manifests.py -v`
Expected: PASS once `sources/wikidata_museums/manifest.yaml` (Task 4) exists and validates.
If it fails, fix the offending manifest until both tests pass.

- [ ] **Step 6: Run the full suite**

Run: `uv run pytest -v`
Expected: PASS (all tasks' tests green)

- [ ] **Step 7: Commit**

```bash
git add sources/_template tests/test_sources_manifests.py
git commit -m "feat: add source _template and manifest validation guard"
```

---

## Self-Review

**Spec coverage (this plan = the data-foundation slice of spec §4, §5, §13):**
- §4 typed POI schema (identity, facets, provenance, Image) → Task 1 ✓
- §4 "unknown is null, never false" → Task 1 default-`None` test ✓
- §5 manifest contract + schema validation → Tasks 2, 5 ✓
- §5 adapter = CLI with `snapshot`/`normalize`, central HTTP/retries/User-Agent → Task 3 ✓
- §5 NDJSON streaming output → Task 3 (`write_ndjson`) ✓
- §8 first real source (Wikidata, CC0) → Task 4 ✓
- §5 copyable starting point for LLM/agent sources → Task 5 ✓
- Out of scope here (own plans below): merge/dedup (§6), pipeline/CI + last-known-good (§7), PMTiles build (§2/§10), search benchmark (§9), front-end (§10).

**Placeholder scan:** No TBD/TODO in delivered code. The `_template/adapter.py`
`NotImplementedError` is intentional (it is a template, not a deliverable) and is not
referenced by any test that asserts behavior.

**Type consistency:** `normalize(raw, *, fetched_at=None) -> Iterator[POI]` signature is
identical in the template (Task 5) and Wikidata adapter (Task 4). `POI`/`Image` field
names used in Task 4 match Task 1's definitions. `http_get`/`write_ndjson`/`run_cli`
signatures used in Task 4 match Task 3's definitions.

---

## Roadmap: subsequent plans

Each is its own `writing-plans` pass and produces working, testable software. Note the
spec's **two spikes (§9, §9b)** gate the front-end/build plans: they need representative
merged data (Plans 2–3) and pre-registered acceptance thresholds before they can decide.

1. **Plan 2 — More adapters + reprojection:** OSM (Geofabrik `.pbf` + osmium, fixture-tested
   `normalize`), RCE Musea (WFS GeoJSON + RD→WGS84 via pyproj), Den Haag/Eindhoven
   Opendatasoft. Each follows the Task-4 pattern.
2. **Plan 3 — Merge/dedup engine + identity registry (spec §6):** strong-key matching,
   per-category scoring, normalization, `overrides.yaml`, **persistent versioned identity
   registry** that preserves `poi_id` + `aliases` across builds (deterministic merge alone is
   insufficient — historical state required), labeled regression set, determinism/idempotency tests.
3. **Spike 1 — Search architecture (spec §9):** on the real merged dataset, with thresholds
   fixed first; produce pass/fail + route choice; implement the winner.
4. **Spike 2 — Tile/filter/cluster/detail model (spec §9b):** validate *unclustered* PMTiles
   + client-side clustering over filtered features + sharded lazy detail lookup against
   pre-registered perf budgets; lock the tile contract (zoom levels, attribute set, shard
   scheme, cache) before the front-end plan.
5. **Plan 4 — Build + publication (spec §7):** canonical DB → **unclustered** PMTiles +
   sharded detail JSON + license report, `data_version` stamping, versioned immutable
   artifacts + `manifest.json` atomic switch + cache headers, publish-gate (count bands,
   coord validity, missing-source), last-known-good, snapshot retention/GC.
6. **Plan 5 — Front-end (spec §10):** MapLibre + unclustered-PMTiles browse with client-side
   filtered clustering, lazy detail-shard fetch, typed facet filters, distance reference,
   deep-links (view + `poi_id` + query/filters), verified/pinned PDOK BRT-A basemap +
   raster fallback, attribution UI, a11y.
7. **Plan 6 — CI orchestration (spec §7):** dispatcher workflow (matrix over manifests),
   `workflow_dispatch` for codespace-only sources, concurrency locking, freshness monitoring,
   pinned action/tool versions, atomic Pages + search-index deploy.
8. **Plan 7 — Agent restaurant source (spec §8.1):** codespace-only curated source with
   `evidence` fields, ≥1 verifiable signal gate, manual review before publication.
