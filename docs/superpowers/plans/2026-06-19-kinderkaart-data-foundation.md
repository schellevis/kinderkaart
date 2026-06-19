# Kinderkaart Data Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the typed two-phase POI schema, the reproducible file/stream source-adapter
contract, and one working end-to-end adapter, so every later subsystem (dedup, build,
search, front-end) has a validated, migration-proof data contract.

**Architecture:** A Python pipeline package (`data_pipeline/`) holds the shared facet model,
the **`SourcePOI`** adapter-output model (the merge later produces `CanonicalPOI` — Plan 3),
the manifest model (the runtime source of truth), and adapter base utilities (an injectable
HTTP client with correct retry semantics, an NDJSON writer, a file/stream CLI runner with a
snapshot **envelope** and a reproducible `--fetched-at`). Each source is a package under
`sources/<package_dir>/` with a `manifest.yaml` and an `adapter.py` exposing
`snapshot(output, *, client) -> SnapshotMetadata` and
`normalize(input, *, fetched_at) -> Iterator[SourcePOI]`. This plan delivers the schema, the
contract, a copyable `_template`, and the Wikidata-museums adapter.

**Tech Stack:** Python 3.13, uv (+ committed `uv.lock`), pydantic v2, httpx, PyYAML, pytest,
ruff, mypy.

## Global Constraints

- Python `>=3.13`; manage deps with `uv`; **commit `uv.lock`** (reproducible toolchain).
- All contract models use `model_config = ConfigDict(extra="forbid")` — unknown fields are
  errors, never silently dropped.
- **Two phases, two models:** adapters emit `SourcePOI` (own `source_id` + `source_record_id`,
  no public `poi_id`); the merge (Plan 3) emits `CanonicalPOI`. Never reuse one for the other.
- `country` is ISO 3166-1 alpha-2 lowercase **and** must be in `SUPPORTED_COUNTRIES`
  (`frozenset({"nl"})` for now; extended per spec §12).
- Categories: fixed vocabulary `playground, museum, zoo, petting_zoo, pool, play_park,
  restaurant_kidfriendly`; lists are de-duplicated and must be non-empty.
- `fetched_at` is timezone-aware, normalized to UTC, and means **the start of the fetch**.
- "Unknown" is `null`, never `false`.
- URL fields (`website`, `source_url`, image URLs) accept only `http`/`https`.
- The manifest is the **runtime source of truth**: adapters read config from their own
  `manifest.yaml`; they do not hard-code `id`/endpoint/country/category.
- Adapter CLI: `snapshot --output PATH` (chunked download + `PATH.meta.json` envelope) and
  `normalize PATH [--fetched-at ISO]` (streams `SourcePOI` NDJSON). Same snapshot + metadata
  → byte-identical NDJSON.
- HTTP: injectable client + sleep; retry only retryable statuses/transport errors; never
  retry permanent 4xx; `Retry-After` supports seconds **and** HTTP-date; `User-Agent` is not
  overridable.
- `manifest.id` is kebab-case; its Python package dir is `id.replace("-", "_")`.
- Before **every** commit run the full quality bar: `uv run ruff check . && uv run mypy
  data_pipeline sources && uv run pytest`.

---

### Task 1: Project setup + vocabulary + tooling

**Files:**
- Modify: `pyproject.toml`
- Create: `uv.lock` (generated)
- Create: `data_pipeline/__init__.py`
- Create: `data_pipeline/vocab.py`
- Test: `tests/test_vocab.py`

**Interfaces:**
- Produces: `data_pipeline.vocab.CATEGORIES: frozenset[str]`
- Produces: `data_pipeline.vocab.SUPPORTED_COUNTRIES: frozenset[str]`

- [ ] **Step 1: Configure `pyproject.toml`**

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
dev-dependencies = ["pytest>=8", "ruff>=0.6", "mypy>=1.11", "types-PyYAML>=6"]

[tool.pytest.ini_options]
pythonpath = ["."]
testpaths = ["tests"]

[tool.ruff]
target-version = "py313"

[tool.mypy]
python_version = "3.13"
plugins = ["pydantic.mypy"]
ignore_missing_imports = true
```

- [ ] **Step 2: Lock and verify the toolchain**

Run: `uv lock && uv sync`
Expected: creates/updates `uv.lock` and installs deps without error.

- [ ] **Step 3: Create the vocabulary (immutable)**

`data_pipeline/__init__.py` (empty file).

`data_pipeline/vocab.py`:
```python
"""Fixed, language-independent vocabularies (spec §13, §12)."""

CATEGORIES: frozenset[str] = frozenset(
    {
        "playground",
        "museum",
        "zoo",
        "petting_zoo",
        "pool",
        "play_park",
        "restaurant_kidfriendly",
    }
)

# Extended per supported country (spec §12).
SUPPORTED_COUNTRIES: frozenset[str] = frozenset({"nl"})
```

- [ ] **Step 4: Write and run the vocabulary test**

`tests/test_vocab.py`:
```python
from data_pipeline.vocab import CATEGORIES, SUPPORTED_COUNTRIES


def test_vocabularies_are_immutable_frozensets():
    assert isinstance(CATEGORIES, frozenset)
    assert isinstance(SUPPORTED_COUNTRIES, frozenset)
    assert "playground" in CATEGORIES
    assert "nl" in SUPPORTED_COUNTRIES
```

Run: `uv run pytest tests/test_vocab.py -v`
Expected: PASS (1 passed)

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml uv.lock data_pipeline/__init__.py data_pipeline/vocab.py tests/test_vocab.py
git commit -m "chore: project setup, locked toolchain, category vocabulary"
```

---

### Task 2: Shared facet model + `SourcePOI`

**Files:**
- Create: `data_pipeline/schema.py`
- Test: `tests/test_schema.py`

**Interfaces:**
- Consumes: `data_pipeline.vocab.CATEGORIES`, `SUPPORTED_COUNTRIES`
- Produces: `data_pipeline.schema.Address`, `Accessibility`, `Image`, `FacetFields`, `SourcePOI`
- `SourcePOI` adds to `FacetFields`: `source_id: str`, `source_record_id: str`,
  `source_url: str|None`, `source_date: date|None`, `fetched_at: datetime` (tz-aware UTC),
  `field_provenance: dict[str, str]`. **No** `poi_id`/`aliases`/`build_version`
  (those belong to `CanonicalPOI`, Plan 3).

- [ ] **Step 1: Write the failing schema test**

`tests/test_schema.py`:
```python
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from data_pipeline.schema import Image, SourcePOI


def _src(**overrides):
    data = dict(
        source_id="wikidata-museums",
        source_record_id="Q190804",
        name="Rijksmuseum",
        categories=["museum"],
        lat=52.36,
        lon=4.885278,
        country="nl",
        fetched_at=datetime(2026, 6, 19, tzinfo=timezone.utc),
        field_provenance={"name": "wikidata-museums"},
    )
    data.update(overrides)
    return data


def test_minimal_sourcepoi_validates_with_unknown_as_none():
    poi = SourcePOI(**_src())
    assert poi.source_record_id == "Q190804"
    assert poi.indoor is None
    assert poi.images == []


def test_extra_fields_forbidden():
    with pytest.raises(ValidationError):
        SourcePOI(**_src(poi_id="wikidata:Q190804"))  # canonical-only field


def test_unknown_category_and_empty_rejected():
    with pytest.raises(ValidationError):
        SourcePOI(**_src(categories=["spaceport"]))
    with pytest.raises(ValidationError):
        SourcePOI(**_src(categories=[]))


def test_duplicate_categories_are_deduped_preserving_order():
    poi = SourcePOI(**_src(categories=["museum", "museum"]))
    assert poi.categories == ["museum"]


def test_country_must_be_supported():
    with pytest.raises(ValidationError):
        SourcePOI(**_src(country="zz"))  # syntactically ok, not supported
    with pytest.raises(ValidationError):
        SourcePOI(**_src(country="NL"))


def test_out_of_range_coords_rejected():
    with pytest.raises(ValidationError):
        SourcePOI(**_src(lat=200.0))


def test_age_constraints():
    with pytest.raises(ValidationError):
        SourcePOI(**_src(age_min=-1))
    with pytest.raises(ValidationError):
        SourcePOI(**_src(age_min=8, age_max=4))


def test_price_model_consistency_with_free():
    with pytest.raises(ValidationError):
        SourcePOI(**_src(free=True, price_model="paid"))
    ok = SourcePOI(**_src(free=True, price_model="free"))
    assert ok.price_model == "free"


def test_url_protocol_allowlist():
    with pytest.raises(ValidationError):
        SourcePOI(**_src(website="javascript:alert(1)"))
    ok = SourcePOI(**_src(website="https://example.org"))
    assert ok.website == "https://example.org"


def test_fetched_at_must_be_tz_aware_and_normalized_to_utc():
    with pytest.raises(ValidationError):
        SourcePOI(**_src(fetched_at=datetime(2026, 6, 19)))  # naive
    poi = SourcePOI(**_src(fetched_at=datetime(2026, 6, 19, 12, tzinfo=timezone(__import__("datetime").timedelta(hours=2)))))
    assert poi.fetched_at.utcoffset().total_seconds() == 0


def test_empty_name_rejected():
    with pytest.raises(ValidationError):
        SourcePOI(**_src(name="  "))


def test_image_requires_license_fields():
    with pytest.raises(ValidationError):
        Image(url="https://x/y.jpg", source_page="https://x")
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/test_schema.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'data_pipeline.schema'`

- [ ] **Step 3: Implement the schema**

`data_pipeline/schema.py`:
```python
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from data_pipeline.vocab import CATEGORIES, SUPPORTED_COUNTRIES

_ALLOWED_URL_SCHEMES = ("http://", "https://")


def _check_url(value: str | None) -> str | None:
    if value is not None and not value.startswith(_ALLOWED_URL_SCHEMES):
        raise ValueError(f"URL must be http(s): {value!r}")
    return value


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Address(_Strict):
    street: str | None = None
    housenumber: str | None = None
    postcode: str | None = None
    city: str | None = None


class Accessibility(_Strict):
    wheelchair: bool | None = None
    toilet: bool | None = None
    baby_changing: bool | None = None


class Image(_Strict):
    url: str
    source_page: str
    author: str | None = None
    license: str
    license_url: str

    @field_validator("url", "source_page", "license_url")
    @classmethod
    def _urls(cls, v: str) -> str:
        return _check_url(v)  # type: ignore[return-value]


class FacetFields(_Strict):
    name: str
    categories: list[str]
    lat: float
    lon: float
    country: str
    address: Address | None = None

    indoor: bool | None = None
    free: bool | None = None
    price_model: Literal["free", "paid", "donation", "mixed"] | None = None
    age_min: int | None = None
    age_max: int | None = None
    accessibility: Accessibility | None = None
    opening_hours: str | None = None

    website: str | None = None
    images: list[Image] = Field(default_factory=list)
    tags: dict = Field(default_factory=dict)

    @field_validator("name")
    @classmethod
    def _name_not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("name must not be blank")
        return v

    @field_validator("categories")
    @classmethod
    def _categories(cls, v: list[str]) -> list[str]:
        deduped = list(dict.fromkeys(v))
        if not deduped:
            raise ValueError("at least one category is required")
        unknown = set(deduped) - CATEGORIES
        if unknown:
            raise ValueError(f"unknown categories: {sorted(unknown)}")
        return deduped

    @field_validator("country")
    @classmethod
    def _country(cls, v: str) -> str:
        if v not in SUPPORTED_COUNTRIES:
            raise ValueError(f"country must be one of {sorted(SUPPORTED_COUNTRIES)}")
        return v

    @field_validator("lat")
    @classmethod
    def _lat(cls, v: float) -> float:
        if not -90.0 <= v <= 90.0:
            raise ValueError("lat out of range")
        return v

    @field_validator("lon")
    @classmethod
    def _lon(cls, v: float) -> float:
        if not -180.0 <= v <= 180.0:
            raise ValueError("lon out of range")
        return v

    @field_validator("website")
    @classmethod
    def _website(cls, v: str | None) -> str | None:
        return _check_url(v)

    @model_validator(mode="after")
    def _cross_field(self) -> "FacetFields":
        if self.age_min is not None and self.age_min < 0:
            raise ValueError("age_min must be >= 0")
        if self.age_max is not None and self.age_max < 0:
            raise ValueError("age_max must be >= 0")
        if (
            self.age_min is not None
            and self.age_max is not None
            and self.age_min > self.age_max
        ):
            raise ValueError("age_min must be <= age_max")
        if self.free is True and self.price_model not in (None, "free"):
            raise ValueError("free=True is inconsistent with price_model")
        if self.free is False and self.price_model == "free":
            raise ValueError("free=False is inconsistent with price_model='free'")
        return self


class SourcePOI(FacetFields):
    source_id: str
    source_record_id: str
    source_url: str | None = None
    source_date: date | None = None
    fetched_at: datetime
    field_provenance: dict[str, str] = Field(default_factory=dict)

    @field_validator("source_id", "source_record_id")
    @classmethod
    def _non_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("must not be blank")
        return v

    @field_validator("source_url")
    @classmethod
    def _source_url(cls, v: str | None) -> str | None:
        return _check_url(v)

    @field_validator("fetched_at")
    @classmethod
    def _utc(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            raise ValueError("fetched_at must be timezone-aware")
        return v.astimezone(timezone.utc)
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `uv run pytest tests/test_schema.py -v`
Expected: PASS (12 passed)

- [ ] **Step 5: Lint, typecheck, commit**

```bash
uv run ruff check . && uv run mypy data_pipeline && uv run pytest
git add data_pipeline/schema.py tests/test_schema.py
git commit -m "feat: add SourcePOI + shared facet/address/accessibility/image models"
```

---

### Task 3: Manifest model (runtime source of truth) + JSON schema export

**Files:**
- Create: `data_pipeline/manifest.py`
- Create: `sources/manifest.schema.json` (generated, committed)
- Test: `tests/test_manifest.py`
- Test fixture: `tests/fixtures/manifest_valid.yaml`

**Interfaces:**
- Consumes: `data_pipeline.vocab.CATEGORIES`, `SUPPORTED_COUNTRIES`
- Produces: `data_pipeline.manifest.Manifest` (strict; fields below)
- Produces: `load_manifest(path) -> Manifest`
- Produces: `package_dir(manifest_id: str) -> str` (`id.replace("-", "_")`)
- Produces: `export_json_schema(path) -> None` (writes `Manifest.model_json_schema()`)

- [ ] **Step 1: Create the fixture**

`tests/fixtures/manifest_valid.yaml`:
```yaml
schema_version: 1
id: wikidata-museums
name: Wikidata museums (NL)
country: nl
endpoint: "https://query.wikidata.org/sparql"
license: CC0-1.0
license_url: "https://creativecommons.org/publicdomain/zero/1.0/"
license_evidence_date: "2026-06-19"
republication_terms: "Public domain; no attribution required"
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
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from data_pipeline.manifest import (
    Manifest,
    export_json_schema,
    load_manifest,
    package_dir,
)

FIXTURE = Path(__file__).parent / "fixtures" / "manifest_valid.yaml"


def _kwargs(**overrides):
    data = dict(
        schema_version=1, id="wikidata-museums", name="X", country="nl",
        license="CC0-1.0", license_url="https://x", license_evidence_date="2026-06-19",
        republication_terms="public domain", runtime="github-action",
        category_map={"Q33506": ["museum"]}, entrypoint="adapter.py",
    )
    data.update(overrides)
    return data


def test_load_valid_manifest():
    m = load_manifest(FIXTURE)
    assert m.id == "wikidata-museums"
    assert m.expected_count == [900, 1300]
    assert m.category_map == {"Q33506": ["museum"]}


def test_unknown_field_rejected():
    with pytest.raises(ValidationError):
        Manifest(**_kwargs(surprise="x"))


def test_id_must_be_kebab_case():
    with pytest.raises(ValidationError):
        Manifest(**_kwargs(id="Wikidata_Museums"))


def test_bad_runtime_rejected():
    with pytest.raises(ValidationError):
        Manifest(**_kwargs(runtime="lambda"))


def test_category_map_must_use_known_nonempty_categories():
    with pytest.raises(ValidationError):
        Manifest(**_kwargs(category_map={"Q1": ["nope"]}))
    with pytest.raises(ValidationError):
        Manifest(**_kwargs(category_map={"Q1": []}))


def test_expected_count_bounds():
    with pytest.raises(ValidationError):
        Manifest(**_kwargs(expected_count=[5]))
    with pytest.raises(ValidationError):
        Manifest(**_kwargs(expected_count=[10, 5]))  # min > max
    with pytest.raises(ValidationError):
        Manifest(**_kwargs(expected_count=[-1, 5]))


def test_license_url_must_be_http():
    with pytest.raises(ValidationError):
        Manifest(**_kwargs(license_url="file:///etc/passwd"))


def test_package_dir_rule():
    assert package_dir("wikidata-museums") == "wikidata_museums"


def test_committed_json_schema_is_up_to_date(tmp_path):
    out = tmp_path / "schema.json"
    export_json_schema(out)
    committed = Path(__file__).parent.parent / "sources" / "manifest.schema.json"
    assert json.loads(out.read_text()) == json.loads(committed.read_text())
```

- [ ] **Step 3: Run the test to verify it fails**

Run: `uv run pytest tests/test_manifest.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'data_pipeline.manifest'`

- [ ] **Step 4: Implement the manifest module**

`data_pipeline/manifest.py`:
```python
from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, field_validator

from data_pipeline.vocab import CATEGORIES, SUPPORTED_COUNTRIES

RUNTIMES = {"github-action", "codespace-only"}
SUPPORTED_SCHEMA_VERSIONS = {1}
_KEBAB = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")


class Manifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: int
    id: str
    name: str
    country: str
    endpoint: str | None = None
    license: str
    license_url: str
    license_evidence_date: date
    republication_terms: str
    attribution: str | None = None
    runtime: str
    update_frequency: str | None = None
    expected_count: list[int] | None = None
    contact_policy: str | None = None
    category_map: dict[str, list[str]]
    entrypoint: str

    @field_validator("schema_version")
    @classmethod
    def _schema_version(cls, v: int) -> int:
        if v not in SUPPORTED_SCHEMA_VERSIONS:
            raise ValueError(f"unsupported schema_version: {v}")
        return v

    @field_validator("id")
    @classmethod
    def _id(cls, v: str) -> str:
        if not _KEBAB.match(v):
            raise ValueError("id must be kebab-case")
        return v

    @field_validator("country")
    @classmethod
    def _country(cls, v: str) -> str:
        if v not in SUPPORTED_COUNTRIES:
            raise ValueError(f"country must be one of {sorted(SUPPORTED_COUNTRIES)}")
        return v

    @field_validator("license_url")
    @classmethod
    def _license_url(cls, v: str) -> str:
        if not v.startswith(("http://", "https://")):
            raise ValueError("license_url must be http(s)")
        return v

    @field_validator("runtime")
    @classmethod
    def _runtime(cls, v: str) -> str:
        if v not in RUNTIMES:
            raise ValueError(f"runtime must be one of {sorted(RUNTIMES)}")
        return v

    @field_validator("category_map")
    @classmethod
    def _category_map(cls, v: dict[str, list[str]]) -> dict[str, list[str]]:
        for key, cats in v.items():
            if not cats:
                raise ValueError(f"category_map[{key!r}] must be non-empty")
            unknown = set(cats) - CATEGORIES
            if unknown:
                raise ValueError(f"unknown categories in map: {sorted(unknown)}")
        return v

    @field_validator("expected_count")
    @classmethod
    def _expected_count(cls, v: list[int] | None) -> list[int] | None:
        if v is None:
            return v
        if len(v) != 2:
            raise ValueError("expected_count must be [min, max]")
        lo, hi = v
        if lo < 0 or hi < 0:
            raise ValueError("expected_count must be non-negative")
        if lo > hi:
            raise ValueError("expected_count min must be <= max")
        return v


def package_dir(manifest_id: str) -> str:
    return manifest_id.replace("-", "_")


def load_manifest(path: str | Path) -> Manifest:
    data = yaml.safe_load(Path(path).read_text())
    return Manifest.model_validate(data)


def export_json_schema(path: str | Path) -> None:
    schema = Manifest.model_json_schema()
    Path(path).write_text(json.dumps(schema, indent=2, sort_keys=True) + "\n")
```

- [ ] **Step 5: Generate the committed JSON schema**

Run: `uv run python -c "from data_pipeline.manifest import export_json_schema; export_json_schema('sources/manifest.schema.json')"`
Expected: writes `sources/manifest.schema.json`.

- [ ] **Step 6: Run the test, lint, typecheck, commit**

Run: `uv run pytest tests/test_manifest.py -v`
Expected: PASS (9 passed)

```bash
uv run ruff check . && uv run mypy data_pipeline && uv run pytest
git add data_pipeline/manifest.py sources/manifest.schema.json tests/test_manifest.py tests/fixtures/manifest_valid.yaml
git commit -m "feat: add strict manifest model, loader, and exported JSON schema"
```

---

### Task 4: Adapter base — snapshot envelope, HTTP, NDJSON, file/stream CLI

**Files:**
- Create: `data_pipeline/adapter_base.py`
- Test: `tests/test_adapter_base.py`

**Interfaces:**
- Consumes: `data_pipeline.schema.SourcePOI`
- Produces: `USER_AGENT: str`; `RETRYABLE_STATUS: frozenset[int]`
- Produces: `SnapshotMetadata` (strict model: `source_id, endpoint, query|None, checksum,
  fetched_at: datetime, adapter_version: str`)
- Produces: `http_get(url, *, client, sleep, params=None, headers=None, max_attempts=3,
  backoff=0.5, timeout=30.0) -> httpx.Response`
- Produces: `download(url, output, *, client, sleep) -> str` (chunked write, returns sha256 hex)
- Produces: `write_ndjson(pois, out=None) -> int`
- Produces: `run_cli(snapshot, normalize) -> None` where
  `snapshot(output: BinaryIO, *, client: httpx.Client) -> SnapshotMetadata` and
  `normalize(input: BinaryIO, *, fetched_at: datetime) -> Iterable[SourcePOI]`

- [ ] **Step 1: Write the failing adapter-base test**

`tests/test_adapter_base.py`:
```python
import io
from datetime import datetime, timezone

import httpx
import pytest

from data_pipeline.adapter_base import (
    USER_AGENT,
    SnapshotMetadata,
    http_get,
    write_ndjson,
)
from data_pipeline.schema import SourcePOI


def _client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def _no_sleep(_seconds):  # records nothing; deterministic
    return None


def _poi():
    return SourcePOI(
        source_id="s", source_record_id="r1", name="A", categories=["museum"],
        lat=52.0, lon=5.0, country="nl",
        fetched_at=datetime(2026, 6, 19, tzinfo=timezone.utc),
    )


def test_user_agent_cannot_be_overridden():
    seen = {}

    def handler(request):
        seen["ua"] = request.headers.get("user-agent")
        return httpx.Response(200, json={"ok": True})

    with _client(handler) as client:
        http_get("https://x/api", client=client, sleep=_no_sleep,
                 headers={"User-Agent": "evil"})
    assert seen["ua"] == USER_AGENT


def test_retries_on_503_then_succeeds():
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(503)
        return httpx.Response(200, json={"ok": True})

    with _client(handler) as client:
        resp = http_get("https://x/api", client=client, sleep=_no_sleep, max_attempts=3)
    assert resp.status_code == 200
    assert calls["n"] == 2


def test_permanent_4xx_not_retried():
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        return httpx.Response(404)

    with _client(handler) as client:
        with pytest.raises(httpx.HTTPStatusError):
            http_get("https://x/api", client=client, sleep=_no_sleep, max_attempts=3)
    assert calls["n"] == 1


def test_exhausted_retries_raises_runtimeerror():
    def handler(request):
        return httpx.Response(503)

    with _client(handler) as client:
        with pytest.raises(RuntimeError):
            http_get("https://x/api", client=client, sleep=_no_sleep, max_attempts=2)


def test_retry_after_http_date_is_accepted():
    slept = []
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(429, headers={"Retry-After": "Wed, 21 Oct 2099 07:28:00 GMT"})
        return httpx.Response(200, json={"ok": True})

    with _client(handler) as client:
        http_get("https://x/api", client=client, sleep=slept.append, max_attempts=3)
    assert slept and slept[0] >= 0  # parsed, did not crash


def test_write_ndjson_emits_one_line_per_poi():
    buf = io.StringIO()
    n = write_ndjson([_poi(), _poi()], out=buf)
    lines = buf.getvalue().strip().split("\n")
    assert n == 2 and len(lines) == 2
    assert '"source_record_id":"r1"' in lines[0]


def test_snapshot_metadata_is_strict():
    with pytest.raises(Exception):
        SnapshotMetadata(
            source_id="s", endpoint="https://x", query=None, checksum="ab",
            fetched_at=datetime(2026, 6, 19, tzinfo=timezone.utc),
            adapter_version="1", extra="boom",
        )
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/test_adapter_base.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'data_pipeline.adapter_base'`

- [ ] **Step 3: Implement the adapter base**

`data_pipeline/adapter_base.py`:
```python
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections.abc import Callable, Iterable
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import BinaryIO, Protocol

import httpx
from pydantic import BaseModel, ConfigDict

from data_pipeline.schema import SourcePOI

USER_AGENT = "kinderkaart/0.1 (+https://github.com/joostschellevis/kinderkaart)"
RETRYABLE_STATUS: frozenset[int] = frozenset({429, 500, 502, 503, 504})

SleepFn = Callable[[float], None]


class SnapshotMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_id: str
    endpoint: str
    query: str | None = None
    checksum: str
    fetched_at: datetime
    adapter_version: str


def _retry_after(resp: httpx.Response, default: float) -> float:
    raw = resp.headers.get("Retry-After")
    if raw is None:
        return default
    if raw.isdigit():
        return float(raw)
    try:
        when = parsedate_to_datetime(raw)
        delta = (when - datetime.now(timezone.utc)).total_seconds()
        return max(0.0, delta)
    except (TypeError, ValueError):
        return default


def http_get(
    url: str,
    *,
    client: httpx.Client,
    sleep: SleepFn,
    params: dict | None = None,
    headers: dict | None = None,
    max_attempts: int = 3,
    backoff: float = 0.5,
    timeout: float = 30.0,
) -> httpx.Response:
    hdrs = dict(headers or {})
    hdrs["User-Agent"] = USER_AGENT  # set last: not overridable
    last_exc: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            resp = client.get(url, params=params, headers=hdrs, timeout=timeout)
        except httpx.HTTPError as exc:
            last_exc = exc
            if attempt < max_attempts:
                sleep(backoff * 2 ** (attempt - 1))
            continue
        if resp.status_code in RETRYABLE_STATUS:
            last_exc = httpx.HTTPStatusError(
                f"retryable status {resp.status_code}", request=resp.request, response=resp
            )
            if attempt < max_attempts:
                sleep(_retry_after(resp, backoff * 2 ** (attempt - 1)))
            continue
        resp.raise_for_status()  # permanent 4xx -> raised, not retried
        return resp
    raise RuntimeError(f"GET {url} failed after {max_attempts} attempts") from last_exc


def download(url: str, output: BinaryIO, *, client: httpx.Client, sleep: SleepFn) -> str:
    resp = http_get(url, client=client, sleep=sleep)
    digest = hashlib.sha256()
    for chunk in resp.iter_bytes():
        output.write(chunk)
        digest.update(chunk)
    return digest.hexdigest()


def write_ndjson(pois: Iterable[SourcePOI], out=None) -> int:
    if out is None:
        out = sys.stdout
    n = 0
    for poi in pois:
        out.write(poi.model_dump_json())
        out.write("\n")
        n += 1
    return n


class _SnapshotFn(Protocol):
    def __call__(self, output: BinaryIO, *, client: httpx.Client) -> SnapshotMetadata: ...


class _NormalizeFn(Protocol):
    def __call__(self, input: BinaryIO, *, fetched_at: datetime) -> Iterable[SourcePOI]: ...


def run_cli(snapshot: _SnapshotFn, normalize: _NormalizeFn) -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)
    snap = sub.add_parser("snapshot")
    snap.add_argument("--output", required=True)
    norm = sub.add_parser("normalize")
    norm.add_argument("path")
    norm.add_argument("--fetched-at")
    args = parser.parse_args()

    if args.cmd == "snapshot":
        with httpx.Client() as client, open(args.output, "wb") as fh:
            meta = snapshot(fh, client=client)
        Path(args.output + ".meta.json").write_text(meta.model_dump_json(indent=2))
    elif args.cmd == "normalize":
        if args.fetched_at:
            fetched = datetime.fromisoformat(args.fetched_at)
        else:
            meta_path = Path(args.path + ".meta.json")
            meta = SnapshotMetadata.model_validate_json(meta_path.read_text())
            fetched = meta.fetched_at
        if fetched.tzinfo is None:
            raise SystemExit("fetched_at must be timezone-aware")
        with open(args.path, "rb") as fh:
            write_ndjson(normalize(fh, fetched_at=fetched))
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `uv run pytest tests/test_adapter_base.py -v`
Expected: PASS (7 passed)

- [ ] **Step 5: Lint, typecheck, commit**

```bash
uv run ruff check . && uv run mypy data_pipeline && uv run pytest
git add data_pipeline/adapter_base.py tests/test_adapter_base.py
git commit -m "feat: add adapter base (envelope, retry-correct http, file/stream CLI)"
```

---

### Task 5: Wikidata-museums adapter (manifest-driven, deterministic per QID)

**Files:**
- Create: `sources/__init__.py`
- Create: `sources/wikidata_museums/__init__.py`
- Create: `sources/wikidata_museums/manifest.yaml`
- Create: `sources/wikidata_museums/adapter.py`
- Test: `tests/test_wikidata_museums.py`
- Test fixture: `tests/fixtures/wikidata_museums_response.json`

**Interfaces:**
- Consumes: `http_get`, `download`, `run_cli`, `SnapshotMetadata`, `SourcePOI`,
  `load_manifest`, `package_dir`
- Produces: `sources.wikidata_museums.adapter.MANIFEST` (loaded `Manifest`),
  `snapshot(output, *, client) -> SnapshotMetadata`,
  `normalize(input, *, fetched_at) -> Iterator[SourcePOI]` (one `SourcePOI` per **distinct**
  QID; multi-value websites/coords consolidated by a stable rule; QID format validated;
  malformed binding raises)

- [ ] **Step 1: Create the manifest (copied from Task 3 fixture content)**

`sources/wikidata_museums/manifest.yaml`:
```yaml
schema_version: 1
id: wikidata-museums
name: Wikidata museums (NL)
country: nl
endpoint: "https://query.wikidata.org/sparql"
license: CC0-1.0
license_url: "https://creativecommons.org/publicdomain/zero/1.0/"
license_evidence_date: "2026-06-19"
republication_terms: "Public domain; no attribution required"
attribution: null
runtime: github-action
update_frequency: weekly
expected_count: [900, 1300]
contact_policy: "User-Agent with contact; honor 429/Retry-After"
category_map:
  "Q33506": [museum]
entrypoint: adapter.py
```

- [ ] **Step 2: Create the response fixture (with a duplicate-QID row)**

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
        "item": {"type": "uri", "value": "http://www.wikidata.org/entity/Q190804"},
        "itemLabel": {"type": "literal", "value": "Rijksmuseum"},
        "coord": {"type": "literal", "value": "Point(4.885278 52.36)"},
        "website": {"type": "uri", "value": "https://rijksmuseum.example/en"}
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
import io
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import httpx
import pytest

from data_pipeline.manifest import load_manifest, package_dir
from sources.wikidata_museums.adapter import MANIFEST, normalize, snapshot

FIXTURE = Path(__file__).parent / "fixtures" / "wikidata_museums_response.json"
FIXED = datetime(2026, 6, 19, tzinfo=timezone.utc)


def test_one_poi_per_distinct_qid():
    pois = list(normalize(FIXTURE.open("rb"), fetched_at=FIXED))
    assert len(pois) == 2  # duplicate Q190804 row consolidated
    first = pois[0]
    assert first.source_id == "wikidata-museums"
    assert first.source_record_id == "Q190804"
    assert first.name == "Rijksmuseum"
    assert first.categories == ["museum"]
    assert first.country == "nl"
    assert first.lat == 52.36 and first.lon == 4.885278
    # multi-value website resolved by stable rule (lexicographically smallest)
    assert first.website == "https://rijksmuseum.example/en"
    assert first.field_provenance["website"] == "wikidata-museums"


def test_missing_website_is_none():
    pois = list(normalize(FIXTURE.open("rb"), fetched_at=FIXED))
    assert pois[1].website is None
    assert "website" not in pois[1].field_provenance


def test_invalid_qid_raises():
    bad = json.dumps({"results": {"bindings": [{
        "item": {"value": "http://www.wikidata.org/entity/NOTAQID"},
        "itemLabel": {"value": "x"},
        "coord": {"value": "Point(5 52)"},
    }]}}).encode()
    with pytest.raises(ValueError):
        list(normalize(io.BytesIO(bad), fetched_at=FIXED))


def test_manifest_matches_package_dir():
    assert package_dir(MANIFEST.id) == "wikidata_museums"


def test_snapshot_uses_endpoint_and_returns_metadata():
    captured = {}

    def handler(request):
        captured["url"] = str(request.url)
        return httpx.Response(200, content=b'{"results":{"bindings":[]}}')

    buf = io.BytesIO()
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        meta = snapshot(buf, client=client)
    assert MANIFEST.endpoint in captured["url"]
    assert meta.source_id == "wikidata-museums"
    assert meta.checksum and buf.getvalue() == b'{"results":{"bindings":[]}}'


def test_cli_normalize_is_reproducible(tmp_path):
    out1 = subprocess.run(
        [sys.executable, "-m", "sources.wikidata_museums.adapter",
         "normalize", str(FIXTURE), "--fetched-at", FIXED.isoformat()],
        capture_output=True, text=True, check=True,
    )
    out2 = subprocess.run(
        [sys.executable, "-m", "sources.wikidata_museums.adapter",
         "normalize", str(FIXTURE), "--fetched-at", FIXED.isoformat()],
        capture_output=True, text=True, check=True,
    )
    assert out1.returncode == 0 and out1.stderr == ""
    lines = out1.stdout.strip().split("\n")
    assert len(lines) == 2
    json.loads(lines[0])  # valid JSON
    assert out1.stdout == out2.stdout  # byte-identical
```

- [ ] **Step 4: Run the test to verify it fails**

Run: `uv run pytest tests/test_wikidata_museums.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'sources.wikidata_museums'`

- [ ] **Step 5: Implement the adapter**

`sources/__init__.py` (empty). `sources/wikidata_museums/__init__.py` (empty).

`sources/wikidata_museums/adapter.py`:
```python
from __future__ import annotations

import json
import re
from collections.abc import Iterator
from datetime import datetime, timezone
from pathlib import Path
from typing import BinaryIO

import httpx

from data_pipeline.adapter_base import (
    SnapshotMetadata,
    download,
    run_cli,
)
from data_pipeline.manifest import load_manifest
from data_pipeline.schema import SourcePOI

ADAPTER_VERSION = "1"
MANIFEST = load_manifest(Path(__file__).with_name("manifest.yaml"))
_QID = re.compile(r"^Q[1-9][0-9]*$")

SPARQL = """
SELECT ?item ?itemLabel ?coord ?website WHERE {
  ?item wdt:P31/wdt:P279* wd:Q33506 .
  ?item wdt:P17 wd:Q55 .
  ?item wdt:P625 ?coord .
  OPTIONAL { ?item wdt:P856 ?website . }
  SERVICE wikibase:label { bd:serviceParam wikibase:language "nl,en". }
}
"""


def snapshot(output: BinaryIO, *, client: httpx.Client) -> SnapshotMetadata:
    fetched = datetime.now(timezone.utc)  # start of fetch
    url = f"{MANIFEST.endpoint}?format=json&query={httpx.QueryParams({'q': SPARQL})['q']}"
    checksum = download(url, output, client=client, sleep=__import__("time").sleep)
    return SnapshotMetadata(
        source_id=MANIFEST.id,
        endpoint=MANIFEST.endpoint or "",
        query=SPARQL.strip(),
        checksum=checksum,
        fetched_at=fetched,
        adapter_version=ADAPTER_VERSION,
    )


def _parse_point(wkt: str) -> tuple[float, float]:
    """'Point(lon lat)' -> (lat, lon)."""
    inner = wkt[wkt.index("(") + 1 : wkt.index(")")]
    lon_s, lat_s = inner.split()
    return float(lat_s), float(lon_s)


def normalize(input: BinaryIO, *, fetched_at: datetime) -> Iterator[SourcePOI]:
    data = json.load(input)  # adapter-specific: Wikidata JSON is read fully into memory
    # Consolidate multi-row bindings per QID deterministically.
    by_qid: dict[str, dict] = {}
    order: list[str] = []
    for b in data["results"]["bindings"]:
        qid = b["item"]["value"].rsplit("/", 1)[-1]
        if not _QID.match(qid):
            raise ValueError(f"invalid Wikidata QID: {qid!r}")
        if qid not in by_qid:
            by_qid[qid] = {"label": None, "coords": set(), "websites": set()}
            order.append(qid)
        rec = by_qid[qid]
        rec["label"] = rec["label"] or b.get("itemLabel", {}).get("value")
        rec["coords"].add(b["coord"]["value"])
        if "website" in b:
            rec["websites"].add(b["website"]["value"])

    for qid in order:
        rec = by_qid[qid]
        lat, lon = _parse_point(sorted(rec["coords"])[0])  # stable rule
        provenance = {"name": MANIFEST.id, "lat": MANIFEST.id, "lon": MANIFEST.id}
        website = None
        if rec["websites"]:
            website = sorted(rec["websites"])[0]  # stable rule
            provenance["website"] = MANIFEST.id
        yield SourcePOI(
            source_id=MANIFEST.id,
            source_record_id=qid,
            name=rec["label"] or qid,
            categories=["museum"],
            lat=lat,
            lon=lon,
            country=MANIFEST.country,
            website=website,
            source_url=f"http://www.wikidata.org/entity/{qid}",
            fetched_at=fetched_at,
            field_provenance=provenance,
        )


if __name__ == "__main__":
    run_cli(snapshot, normalize)
```

- [ ] **Step 6: Run the test, lint, typecheck**

Run: `uv run pytest tests/test_wikidata_museums.py -v`
Expected: PASS (6 passed)

```bash
uv run ruff check . && uv run mypy data_pipeline sources && uv run pytest
```

- [ ] **Step 7: Commit**

```bash
git add sources/__init__.py sources/wikidata_museums tests/test_wikidata_museums.py tests/fixtures/wikidata_museums_response.json
git commit -m "feat: add manifest-driven, deterministic wikidata-museums adapter"
```

---

### Task 6: Copyable `_template` + manifest guard (incl. template)

**Files:**
- Create: `sources/_template/manifest.yaml`
- Create: `sources/_template/adapter.py`
- Create: `sources/_template/README.md`
- Test: `tests/test_sources_manifests.py`

**Interfaces:**
- Consumes: `load_manifest`, `package_dir`
- Produces: a documented, **validating** starting point (manifest + adapter + mapping docs +
  a minimal contract test snippet) that an LLM/agent copies.

- [ ] **Step 1: Create the template manifest (must itself validate)**

`sources/_template/manifest.yaml`:
```yaml
schema_version: 1
id: template-source            # rename to your kebab-case id
name: Human readable name
country: nl
endpoint: "https://example.com/data"   # or null for codespace-only/agent sources
license: CC-BY-4.0
license_url: "https://creativecommons.org/licenses/by/4.0/"
license_evidence_date: "2026-06-19"
republication_terms: "Attribute the source; redistribution allowed"
attribution: "© Source name"
runtime: github-action          # or: codespace-only
update_frequency: weekly
expected_count: [100, 5000]
contact_policy: "User-Agent with contact; honor 429/Retry-After"
category_map:
  "source-type-key": [playground]
entrypoint: adapter.py
```

- [ ] **Step 2: Create the template adapter (with mapping docs)**

`sources/_template/adapter.py`:
```python
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

from data_pipeline.adapter_base import SnapshotMetadata, download, run_cli
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
```

- [ ] **Step 3: Create the template README**

`sources/_template/README.md`:
```markdown
# Source template

1. Copy this folder to `sources/<package_dir>/` where `package_dir = id.replace("-", "_")`.
2. Edit `manifest.yaml` (id, license + evidence date + republication terms, runtime,
   category_map, expected_count).
3. Implement `snapshot()` and `normalize()` in `adapter.py`; fill `field_provenance`.
4. Add `tests/test_<package_dir>.py` with a small fixture asserting `normalize` output
   (one SourcePOI per distinct source record; stable rules for multi-values).
5. Run the full bar: `uv run ruff check . && uv run mypy data_pipeline sources && uv run pytest`.
```

- [ ] **Step 4: Write the manifest guard test (validates ALL manifests incl. template)**

`tests/test_sources_manifests.py`:
```python
import importlib
from pathlib import Path

from data_pipeline.manifest import load_manifest, package_dir

SOURCES_DIR = Path(__file__).parent.parent / "sources"


def _all_manifests():
    # Guard test: every manifest under sources/, including _template, must validate.
    return sorted(SOURCES_DIR.glob("*/manifest.yaml"))


def test_every_manifest_validates():
    paths = _all_manifests()
    assert paths, "expected at least one manifest"
    for path in paths:
        load_manifest(path)  # raises ValidationError on a broken manifest


def test_source_ids_unique():
    ids = [load_manifest(p).id for p in _all_manifests()]
    assert len(ids) == len(set(ids)), f"duplicate ids: {ids}"


def test_real_source_package_dir_matches_id():
    # _template lives in a literal "_template" dir, so skip it for the dir-name rule.
    for path in _all_manifests():
        if path.parent.name == "_template":
            continue
        m = load_manifest(path)
        assert path.parent.name == package_dir(m.id)


def test_real_source_entrypoint_is_importable():
    for path in _all_manifests():
        if path.parent.name == "_template":
            continue
        m = load_manifest(path)
        mod = importlib.import_module(f"sources.{path.parent.name}.adapter")
        assert hasattr(mod, "snapshot") and hasattr(mod, "normalize")
        assert (path.parent / m.entrypoint).exists()
```

- [ ] **Step 5: Run the guard test (RED → GREEN)**

Run: `uv run pytest tests/test_sources_manifests.py -v`
Expected: initially FAIL if `sources/_template/manifest.yaml` is missing/invalid; PASS once
both the template and `wikidata-museums` manifests validate and the package-dir rule holds.

- [ ] **Step 6: Run the full bar and commit**

Run: `uv run ruff check . && uv run mypy data_pipeline sources && uv run pytest -v`
Expected: PASS (entire suite green)

```bash
git add sources/_template tests/test_sources_manifests.py
git commit -m "feat: add validating source _template and manifest guard tests"
```

---

## Self-Review

**Spec coverage (this plan = the data-foundation slice of spec §4, §5, §13):**
- §4 two-phase model — `SourcePOI` here; `CanonicalPOI` deferred to Plan 3 (merge) → Task 2 ✓
- §4 `extra="forbid"`, typed facets, price/free consistency, age constraints, country⊆supported,
  tz-aware UTC `fetched_at`, URL allowlist, non-blank, deduped categories → Task 2 ✓
- §5 manifest as runtime source of truth + strict validation + JSON schema export → Tasks 3, 5 ✓
- §5 file/stream CLI (`snapshot --output`, `normalize PATH --fetched-at`), snapshot envelope,
  reproducible NDJSON → Tasks 4, 5 ✓
- §5 central HTTP: injectable client/sleep, retryable-only, no-retry-4xx, Retry-After
  seconds+date, non-overridable User-Agent → Task 4 ✓
- §8 first real source (Wikidata, CC0), deterministic per QID → Task 5 ✓
- §5 copyable, validating template with mapping docs → Task 6 ✓
- Toolchain reproducibility (`uv.lock`, ruff, mypy) → Task 1 + per-task quality bar ✓
- Out of scope here (own plans): merge + identity registry (§6), build/publication (§7),
  the two spikes (§9, §9b), front-end (§10), CI (§7), agent restaurant source (§8.1).

**Placeholder scan:** No TBD/TODO in delivered code. `_template/adapter.py`
`NotImplementedError` is intentional (a template, not a deliverable) and no behavioral test
asserts against it.

**Type consistency:** `snapshot(output: BinaryIO, *, client) -> SnapshotMetadata` and
`normalize(input: BinaryIO, *, fetched_at: datetime) -> Iterator[SourcePOI]` are identical in
the template (Task 6), Wikidata adapter (Task 5), and the `run_cli` protocols (Task 4).
`SourcePOI`/`SnapshotMetadata`/`Manifest` field names used in later tasks match their Task 2/3/4
definitions. `package_dir` (Task 3) is used consistently in Tasks 5–6.

---

## Roadmap: subsequent plans

Each is its own `writing-plans` pass and produces working, testable software. Note the
spec's **two spikes (§9, §9b)** gate the front-end/build plans: they need representative
merged data (Plans 2–3) and pre-registered acceptance thresholds before they can decide.

1. **Plan 2 — More adapters + reprojection:** OSM (Geofabrik `.pbf` + osmium, fixture-tested
   `normalize`, streaming file contract), RCE Musea (WFS GeoJSON + RD→WGS84 via pyproj),
   Den Haag/Eindhoven Opendatasoft. Each follows the Task-5 pattern (manifest-driven).
2. **Plan 3 — Merge/dedup engine + identity registry (spec §6):** `SourcePOI` → `CanonicalPOI`;
   strong-key matching, per-category scoring, normalization, `overrides.yaml`, **persistent
   versioned identity registry** preserving `poi_id` + `aliases` across builds, labeled
   regression set, determinism/idempotency tests.
3. **Spike 1 — Search architecture (spec §9):** on the real merged dataset, thresholds fixed
   first; pass/fail + route choice; implement the winner.
4. **Spike 2 — Tile/filter/cluster/detail model (spec §9b):** validate *unclustered* PMTiles +
   client-side clustering over filtered features + sharded lazy detail lookup against
   pre-registered perf budgets; lock the tile contract before the front-end plan.
5. **Plan 4 — Build + publication (spec §7):** canonical DB → unclustered PMTiles + sharded
   detail JSON + license report, `data_version` stamping, versioned immutable artifacts +
   `manifest.json` atomic switch + cache headers, publish-gate, last-known-good, snapshot
   retention/GC.
6. **Plan 5 — Front-end (spec §10):** MapLibre + unclustered-PMTiles browse with client-side
   filtered clustering, lazy detail-shard fetch, typed facet filters, distance reference,
   browser geolocation with auto-center + fallback NL view, mobile-first responsive layout
   (desktop side-panel overview), deep-links (view + `poi_id` + query/filters),
   verified/pinned PDOK BRT-A basemap + raster fallback, attribution UI, a11y.
7. **Plan 6 — CI orchestration (spec §7):** dispatcher workflow (matrix over manifests),
   `workflow_dispatch` for codespace-only sources, concurrency locking, freshness monitoring,
   pinned action/tool versions, atomic Pages + search-index deploy.
8. **Plan 7 — Agent restaurant source (spec §8.1):** codespace-only curated source with
   `evidence` fields, ≥1 verifiable signal gate, manual review before publication.
