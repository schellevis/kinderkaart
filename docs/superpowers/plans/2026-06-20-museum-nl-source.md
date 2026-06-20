# museum.nl Data Source Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `sources/museum_nl/` adapter that scrapes museum.nl detail pages and emits `SourcePOI` museum records (coordinates, address, phone, website, description) from each page's JSON-LD.

**Architecture:** Same two-phase contract as every other source. `snapshot()` enumerates detail-page slugs from the sitemap, fetches each page's HTML, and writes one NDJSON record `{slug, url, html}` per page (all network here). `normalize()` is deterministic and network-free: it extracts the `@type: Museum` JSON-LD block + meta description from each stored HTML and maps them to `SourcePOI`. The existing matcher merges these into canonical museum entries. `runtime: codespace-only` (excluded from CI; fed via `--prebuilt`).

**Tech Stack:** Python 3.13, pydantic v2, httpx, stdlib `re`/`json`/`hashlib`. No new dependency (JSON-LD is structured; no HTML parser needed once opening hours are deferred).

## Global Constraints

- **Quality bar (run before every commit):** `uv run ruff check . && uv run mypy data_pipeline sources scripts && uv run pytest`. Ruff default line length 88.
- **Stable `source_record_id`:** `f"museum-nl:{slug}"` — never an enumeration index.
- **`categories`** derived from `MANIFEST.category_map` (never hard-coded).
- **`field_provenance`** set to `MANIFEST.id` for every populated field.
- **URL allowlist:** any stored URL must be http(s) (schema validators enforce; normalize website accordingly).
- **All network in `snapshot()`; `normalize()` does no I/O beyond reading its input file.**
- **Deterministic:** `json.dumps(..., sort_keys=True)` for envelope lines; sorted slug iteration.
- **`package_dir("museum-nl") == "museum_nl"`** (the guard test `tests/test_sources_manifests.py` enforces dir name == `package_dir(id)`).

---

### Task 1: Package scaffold + manifest

**Files:**
- Create: `sources/museum_nl/__init__.py` (empty)
- Create: `sources/museum_nl/manifest.yaml`
- Create: `sources/museum_nl/adapter.py` (stub: `snapshot`/`normalize` raise `NotImplementedError`, `run_cli` wired)
- Test: `tests/test_sources_manifests.py` (existing guard — no new file)

**Interfaces:**
- Produces: importable `sources.museum_nl.adapter` exposing `snapshot` and `normalize`; `MANIFEST` (loaded manifest), `CATEGORIES` (`["museum"]`), `ADAPTER_VERSION = "1"`.

- [ ] **Step 1: Create the package files**

`sources/museum_nl/__init__.py`: empty file.

`sources/museum_nl/manifest.yaml`:
```yaml
schema_version: 1
id: museum-nl
name: Museum.nl
country: nl
endpoint: "https://www.museum.nl/sitemap.xml"
license: "Permission (museum.nl)"
license_url: "https://www.museum.nl/nl/over-ons"
license_evidence_date: "2026-06-20"
republication_terms: "Used with written permission from Museumvereniging/museum.nl; not openly licensed."
attribution: "© Museumvereniging / museum.nl"
runtime: codespace-only
update_frequency: manual
expected_count: [300, 500]
contact_policy: "User-Agent with contact; honor 429/Retry-After"
category_map:
  "museum": [museum]
entrypoint: adapter.py
```

`sources/museum_nl/adapter.py` (stub):
```python
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
```

- [ ] **Step 2: Run the manifest guard tests**

Run: `uv run pytest tests/test_sources_manifests.py -v`
Expected: PASS — all four tests, including `test_real_source_package_dir_matches_id` and `test_real_source_entrypoint_is_importable` for `museum_nl`.

- [ ] **Step 3: Run ruff + mypy on the new package**

Run: `uv run ruff check sources/museum_nl && uv run mypy sources`
Expected: PASS (no errors).

- [ ] **Step 4: Commit**

```bash
git add sources/museum_nl/
git commit -m "feat(museum-nl): scaffold source package + manifest"
```

---

### Task 2: Pure parsing helpers (`parse.py`)

**Files:**
- Create: `sources/museum_nl/parse.py`
- Test: `tests/test_museum_nl_parse.py`

**Interfaces:**
- Produces (all pure, no project imports):
  - `extract_slugs(sitemap_xml: str) -> list[str]` — sorted, de-duped single-segment `/nl/<slug>` slugs.
  - `extract_museum_jsonld(html: str) -> dict | None` — first JSON-LD node whose `@type` is/contains `"Museum"`, else `None`.
  - `extract_meta_description(html: str) -> str | None` — `<meta name="description">` then `og:description`.
  - `split_street(street_address: str) -> tuple[str, str | None]` — `(street, housenumber|None)`.
  - `normalize_website(same_as) -> str | None` — http(s) URL or `None`.

- [ ] **Step 1: Write the failing tests**

`tests/test_museum_nl_parse.py`:
```python
from sources.museum_nl.parse import (
    extract_meta_description,
    extract_museum_jsonld,
    extract_slugs,
    normalize_website,
    split_street,
)

SITEMAP = """<?xml version="1.0"?>
<urlset>
  <url><loc>https://www.museum.nl/nl/anne-frank-huis</loc></url>
  <url><loc>https://www.museum.nl/nl/rijksmuseum-amsterdam</loc></url>
  <url><loc>https://www.museum.nl/nl/amsterdam</loc></url>
  <url><loc>https://www.museum.nl/nl/zien-en-doen/musea</loc></url>
  <url><loc>https://www.museum.nl/en/anne-frank-huis</loc></url>
  <url><loc>https://www.museum.nl/nl/anne-frank-huis</loc></url>
</urlset>"""

MUSEUM_HTML = """<html><head>
<meta name="description" content="Een mooi museum.">
<script type="application/ld+json">
{"@context":"https://schema.org","@type":"Museum","name":"Anne Frank Huis",
 "telephone":"020   55 67 105",
 "address":{"@type":"PostalAddress","streetAddress":"Westermarkt 20",
   "addressLocality":"Amsterdam","postalCode":"1016 DK","addressCountry":"NL"},
 "geo":{"@type":"GeoCoordinates","latitude":52.375083,"longitude":4.884031},
 "sameAs":"www.annefrank.org"}
</script></head><body></body></html>"""

THEME_HTML = """<html><head>
<script type="application/ld+json">
{"@context":"https://schema.org","@type":"WebPage","name":"Amsterdam"}
</script></head><body></body></html>"""


def test_extract_slugs_keeps_single_segment_nl_pages():
    assert extract_slugs(SITEMAP) == ["amsterdam", "anne-frank-huis", "rijksmuseum-amsterdam"]


def test_extract_museum_jsonld_returns_museum_node():
    node = extract_museum_jsonld(MUSEUM_HTML)
    assert node is not None and node["name"] == "Anne Frank Huis"
    assert node["geo"]["latitude"] == 52.375083


def test_extract_museum_jsonld_none_for_non_museum():
    assert extract_museum_jsonld(THEME_HTML) is None


def test_extract_meta_description():
    assert extract_meta_description(MUSEUM_HTML) == "Een mooi museum."
    assert extract_meta_description("<html></html>") is None


def test_split_street():
    assert split_street("Westermarkt 20") == ("Westermarkt", "20")
    assert split_street("Museumplein") == ("Museumplein", None)


def test_normalize_website():
    assert normalize_website("www.annefrank.org") == "https://www.annefrank.org"
    assert normalize_website("https://x.nl") == "https://x.nl"
    assert normalize_website(["http://a.nl", "http://b.nl"]) == "http://a.nl"
    assert normalize_website("mailto:x@y.nl") is None
    assert normalize_website(None) is None
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_museum_nl_parse.py -v`
Expected: FAIL with `ModuleNotFoundError: sources.museum_nl.parse`.

- [ ] **Step 3: Implement `parse.py`**

`sources/museum_nl/parse.py`:
```python
from __future__ import annotations

import json
import re
from collections.abc import Iterator

_LD_RE = re.compile(
    r'<script[^>]+type="application/ld\+json"[^>]*>(.*?)</script>',
    re.DOTALL | re.IGNORECASE,
)
_META_DESC_RE = re.compile(
    r'<meta[^>]+name="description"[^>]+content="([^"]*)"', re.IGNORECASE
)
_OG_DESC_RE = re.compile(
    r'<meta[^>]+property="og:description"[^>]+content="([^"]*)"', re.IGNORECASE
)
_LOC_RE = re.compile(r"<loc>\s*(https?://[^<\s]+?)\s*</loc>", re.IGNORECASE)
_DETAIL_RE = re.compile(r"^https?://(?:www\.)?museum\.nl/nl/([^/]+)/?$", re.IGNORECASE)
_STREET_RE = re.compile(r"^(.*?)\s+(\d+\s*\w*)$")


def extract_slugs(sitemap_xml: str) -> list[str]:
    slugs: set[str] = set()
    for url in _LOC_RE.findall(sitemap_xml):
        m = _DETAIL_RE.match(url)
        if m:
            slugs.add(m.group(1))
    return sorted(slugs)


def _iter_jsonld(html: str) -> Iterator[dict]:
    for body in _LD_RE.findall(html):
        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            continue
        if isinstance(data, list):
            yield from (d for d in data if isinstance(d, dict))
        elif isinstance(data, dict):
            yield data


def _is_museum(node: dict) -> bool:
    t = node.get("@type")
    if isinstance(t, list):
        return "Museum" in t
    return t == "Museum"


def extract_museum_jsonld(html: str) -> dict | None:
    for node in _iter_jsonld(html):
        if _is_museum(node):
            return node
    return None


def extract_meta_description(html: str) -> str | None:
    m = _META_DESC_RE.search(html) or _OG_DESC_RE.search(html)
    if not m:
        return None
    return m.group(1).strip() or None


def split_street(street_address: str) -> tuple[str, str | None]:
    m = _STREET_RE.match(street_address.strip())
    if m:
        return m.group(1).strip(), m.group(2).strip()
    return street_address.strip(), None


def normalize_website(same_as: object) -> str | None:
    if isinstance(same_as, list):
        same_as = same_as[0] if same_as else None
    if not isinstance(same_as, str) or not same_as.strip():
        return None
    url = same_as.strip()
    if "://" in url:
        return url if re.match(r"^https?://", url, re.IGNORECASE) else None
    return "https://" + url
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/test_museum_nl_parse.py -v`
Expected: PASS (6 tests).

- [ ] **Step 5: Commit**

```bash
git add sources/museum_nl/parse.py tests/test_museum_nl_parse.py
git commit -m "feat(museum-nl): JSON-LD/sitemap parsing helpers"
```

---

### Task 3: `normalize()` — JSON-LD → SourcePOI

**Files:**
- Modify: `sources/museum_nl/adapter.py` (implement `normalize`, add imports)
- Create: `tests/fixtures/museum_nl/museum.html`, `tests/fixtures/museum_nl/no_geo.html`, `tests/fixtures/museum_nl/theme.html`
- Test: `tests/test_museum_nl.py`

**Interfaces:**
- Consumes: `parse.extract_museum_jsonld`, `parse.extract_meta_description`, `parse.split_street`, `parse.normalize_website`; `schema.Address`, `schema.SourcePOI`.
- Produces: `normalize(path: Path, *, fetched_at: datetime) -> Iterator[SourcePOI]` over an NDJSON envelope of `{slug, url, html}` records.

- [ ] **Step 1: Create fixtures**

`tests/fixtures/museum_nl/museum.html`:
```html
<html><head>
<meta name="description" content="Ruim 2 jaar zat Anne Frank ondergedoken.">
<script type="application/ld+json">
{"@context":"https://schema.org","@type":"Museum","name":"Anne Frank Huis",
 "telephone":"020   55 67 105",
 "address":{"@type":"PostalAddress","streetAddress":"Westermarkt 20",
   "addressLocality":"Amsterdam","postalCode":"1016 DK","addressCountry":"NL"},
 "geo":{"@type":"GeoCoordinates","latitude":52.375083,"longitude":4.884031},
 "sameAs":"www.annefrank.org"}
</script></head><body></body></html>
```

`tests/fixtures/museum_nl/no_geo.html` (Museum node but no geo — must be skipped):
```html
<html><head>
<script type="application/ld+json">
{"@context":"https://schema.org","@type":"Museum","name":"Geen Coords Museum"}
</script></head><body></body></html>
```

`tests/fixtures/museum_nl/theme.html` (non-museum — must be skipped):
```html
<html><head>
<script type="application/ld+json">
{"@context":"https://schema.org","@type":"WebPage","name":"Amsterdam"}
</script></head><body></body></html>
```

- [ ] **Step 2: Write the failing test**

`tests/test_museum_nl.py`:
```python
import json
from datetime import datetime, timezone
from pathlib import Path

from sources.museum_nl.adapter import normalize

FIXTURES = Path(__file__).parent / "fixtures" / "museum_nl"
FIXED = datetime(2026, 6, 20, tzinfo=timezone.utc)


def _envelope(tmp_path: Path) -> Path:
    records = [
        {"slug": "anne-frank-huis", "url": "https://www.museum.nl/nl/anne-frank-huis",
         "html": (FIXTURES / "museum.html").read_text(encoding="utf-8")},
        {"slug": "geen-coords", "url": "https://www.museum.nl/nl/geen-coords",
         "html": (FIXTURES / "no_geo.html").read_text(encoding="utf-8")},
        {"slug": "amsterdam", "url": "https://www.museum.nl/nl/amsterdam",
         "html": (FIXTURES / "theme.html").read_text(encoding="utf-8")},
    ]
    path = tmp_path / "envelope.ndjson"
    with path.open("w", encoding="utf-8") as fh:
        for rec in records:
            fh.write(json.dumps(rec, sort_keys=True) + "\n")
    return path


def test_normalize_maps_museum_and_skips_others(tmp_path):
    pois = list(normalize(_envelope(tmp_path), fetched_at=FIXED))
    assert len(pois) == 1  # no_geo and theme are skipped
    poi = pois[0]
    assert poi.source_id == "museum-nl"
    assert poi.source_record_id == "museum-nl:anne-frank-huis"
    assert poi.categories == ["museum"]
    assert poi.name == "Anne Frank Huis"
    assert abs(poi.lat - 52.375083) < 1e-9 and abs(poi.lon - 4.884031) < 1e-9
    assert poi.address is not None
    assert poi.address.street == "Westermarkt" and poi.address.housenumber == "20"
    assert poi.address.postcode == "1016 DK" and poi.address.city == "Amsterdam"
    assert poi.website == "https://www.annefrank.org"
    assert poi.tags["phone"] == "020 55 67 105"
    assert poi.tags["description"] == "Ruim 2 jaar zat Anne Frank ondergedoken."
    assert poi.field_provenance["name"] == "museum-nl"
    assert poi.field_provenance["address"] == "museum-nl"
    assert poi.field_provenance["website"] == "museum-nl"
    assert poi.field_provenance["tags"] == "museum-nl"
```

- [ ] **Step 3: Run to verify it fails**

Run: `uv run pytest tests/test_museum_nl.py -v`
Expected: FAIL with `NotImplementedError`.

- [ ] **Step 4: Implement `normalize` (replace the stub + add imports)**

In `sources/museum_nl/adapter.py`, add imports near the existing ones:
```python
import json

from data_pipeline.schema import Address
from sources.museum_nl.parse import (
    extract_meta_description,
    extract_museum_jsonld,
    normalize_website,
    split_street,
)
```

Replace the `normalize` stub with:
```python
def _to_poi(slug: str, html: str, fetched_at: datetime) -> SourcePOI | None:
    node = extract_museum_jsonld(html)
    if node is None:
        return None
    geo = node.get("geo")
    if not isinstance(geo, dict):
        return None
    try:
        lat = float(geo["latitude"])
        lon = float(geo["longitude"])
    except (KeyError, TypeError, ValueError):
        return None
    name = str(node.get("name") or "").strip()
    if not name:
        return None

    prov = {
        "name": MANIFEST.id, "categories": MANIFEST.id,
        "lat": MANIFEST.id, "lon": MANIFEST.id, "country": MANIFEST.id,
    }

    address: Address | None = None
    addr = node.get("address")
    if isinstance(addr, dict):
        street, house = split_street(str(addr.get("streetAddress") or ""))
        address = Address(
            street=street or None,
            housenumber=house,
            postcode=(addr.get("postalCode") or None),
            city=(addr.get("addressLocality") or None),
        )
        prov["address"] = MANIFEST.id

    website = normalize_website(node.get("sameAs"))
    if website:
        prov["website"] = MANIFEST.id

    tags: dict = {}
    phone = node.get("telephone")
    if isinstance(phone, str) and phone.strip():
        tags["phone"] = " ".join(phone.split())
    description = extract_meta_description(html)
    if description:
        tags["description"] = description
    if tags:
        prov["tags"] = MANIFEST.id

    return SourcePOI(
        source_id=MANIFEST.id,
        source_record_id=f"{MANIFEST.id}:{slug}",
        name=name,
        categories=list(CATEGORIES),
        lat=lat,
        lon=lon,
        country=MANIFEST.country,
        address=address,
        website=website,
        tags=tags,
        fetched_at=fetched_at,
        field_provenance=prov,
    )


def normalize(path: Path, *, fetched_at: datetime) -> Iterator[SourcePOI]:
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            poi = _to_poi(rec["slug"], rec["html"], fetched_at)
            if poi is not None:
                yield poi
```

- [ ] **Step 5: Run to verify it passes**

Run: `uv run pytest tests/test_museum_nl.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add sources/museum_nl/adapter.py tests/test_museum_nl.py tests/fixtures/museum_nl/
git commit -m "feat(museum-nl): normalize JSON-LD detail pages to SourcePOI"
```

---

### Task 4: `snapshot()` — sitemap → pages → NDJSON envelope

**Files:**
- Modify: `sources/museum_nl/adapter.py` (implement `snapshot`, add imports)
- Test: `tests/test_museum_nl_snapshot.py`

**Interfaces:**
- Consumes: `adapter_base.http_get`, `adapter_base.SnapshotMetadata`, `parse.extract_slugs`.
- Produces: `snapshot(output, *, client) -> SnapshotMetadata` writing NDJSON `{slug, url, html}` (sorted keys) per museum page; `checksum = sha256` of written bytes.

- [ ] **Step 1: Write the failing test**

`tests/test_museum_nl_snapshot.py`:
```python
import io
import json

import httpx

from sources.museum_nl.adapter import snapshot

SITEMAP = """<?xml version="1.0"?>
<urlset>
  <url><loc>https://www.museum.nl/nl/anne-frank-huis</loc></url>
  <url><loc>https://www.museum.nl/nl/rijksmuseum-amsterdam</loc></url>
</urlset>"""
PAGES = {
    "anne-frank-huis": "<html>afh</html>",
    "rijksmuseum-amsterdam": "<html>rijks</html>",
}


def _handler(request: httpx.Request) -> httpx.Response:
    if request.url.path.endswith("sitemap.xml"):
        return httpx.Response(200, text=SITEMAP)
    slug = request.url.path.rsplit("/", 1)[-1]
    return httpx.Response(200, text=PAGES[slug])


def test_snapshot_writes_envelope():
    client = httpx.Client(transport=httpx.MockTransport(_handler))
    buf = io.BytesIO()
    meta = snapshot(buf, client=client)

    assert meta.source_id == "museum-nl"
    assert len(meta.checksum) == 64  # sha256 hex
    lines = buf.getvalue().decode("utf-8").splitlines()
    assert len(lines) == 2
    first = json.loads(lines[0])
    assert set(first) == {"slug", "url", "html"}
    assert first["slug"] == "anne-frank-huis"  # sorted slug order
    assert first["html"] == "<html>afh</html>"
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_museum_nl_snapshot.py -v`
Expected: FAIL with `NotImplementedError`.

- [ ] **Step 3: Implement `snapshot` (replace the stub + add imports)**

In `sources/museum_nl/adapter.py`, add imports:
```python
import hashlib
import time
from datetime import timezone

from data_pipeline.adapter_base import http_get
from sources.museum_nl.parse import extract_slugs
```
(Update the existing `from datetime import datetime` line to `from datetime import datetime, timezone` instead of importing `timezone` separately if that reads cleaner — either is fine.)

Replace the `snapshot` stub with:
```python
def snapshot(output: BinaryIO, *, client: httpx.Client) -> SnapshotMetadata:
    fetched = datetime.now(timezone.utc)
    sitemap = http_get(MANIFEST.endpoint or "", client=client, sleep=time.sleep).text
    digest = hashlib.sha256()
    for slug in extract_slugs(sitemap):
        url = f"https://www.museum.nl/nl/{slug}"
        try:
            html = http_get(url, client=client, sleep=time.sleep).text
        except (httpx.HTTPError, RuntimeError):
            continue
        line = json.dumps(
            {"slug": slug, "url": url, "html": html}, sort_keys=True
        ) + "\n"
        data = line.encode("utf-8")
        output.write(data)
        digest.update(data)
    return SnapshotMetadata(
        source_id=MANIFEST.id,
        endpoint=MANIFEST.endpoint or "",
        query=None,
        checksum=digest.hexdigest(),
        fetched_at=fetched,
        adapter_version=ADAPTER_VERSION,
    )
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/test_museum_nl_snapshot.py -v`
Expected: PASS.

- [ ] **Step 5: Run the full quality bar**

Run: `uv run ruff check . && uv run mypy data_pipeline sources scripts && uv run pytest`
Expected: PASS (ruff clean, mypy clean, all tests green).

- [ ] **Step 6: Commit**

```bash
git add sources/museum_nl/adapter.py tests/test_museum_nl_snapshot.py
git commit -m "feat(museum-nl): snapshot sitemap + detail pages to NDJSON envelope"
```

---

### Task 5: Docs — record the module now that it exists

**Files:**
- Modify: `CLAUDE.md` (Implemented sources list; gate-section "is being built" → "exists")
- Modify: `AGENTS.md` (keep byte-identical via `cp`)
- Modify: `docs/RUNBOOK.md` (museum.nl "no source module yet" note → built; how to run it)

**Interfaces:** none (documentation only).

- [ ] **Step 1: Update CLAUDE.md**

In the Repo-layout `sources/<id>/` bullet, add `museum_nl` to the codespace-only list, e.g. change
`` `restaurants_agent` (`codespace-only`) `` to `` `restaurants_agent`, `museum_nl` (both `codespace-only`) ``.

In the "Licensing & legal gates" section, change `a `sources/museum_nl/` module is being built` to
`a `sources/museum_nl/` module exists (`codespace-only`)`.

- [ ] **Step 2: Sync AGENTS.md byte-identically**

Run: `cp CLAUDE.md AGENTS.md && diff CLAUDE.md AGENTS.md && echo IDENTICAL`
Expected: `IDENTICAL`.

- [ ] **Step 3: Update RUNBOOK.md**

In the codespace-only table, the museum.nl row is already present — leave it. In the "Legal release
gate for museum.nl — PASSED" section, change step 1 from "Build the `sources/museum_nl/` module…" to
note the module now exists, and document running it in codespace:
```bash
uv run python -m sources.museum_nl.adapter snapshot --output /tmp/museum_nl.raw.ndjson
uv run python -m sources.museum_nl.adapter normalize /tmp/museum_nl.raw.ndjson \
    --fetched-at "$(date -u +%Y-%m-%dT%H:%M:%S+00:00)" > /tmp/museum_nl.ndjson
```
then include it via `--prebuilt museum-nl=/tmp/museum_nl.ndjson` (same pattern as restaurants-agent).

- [ ] **Step 4: Verify docs build/quality bar still green**

Run: `uv run pytest -q`
Expected: PASS (docs-only change; sanity check nothing imports broke).

- [ ] **Step 5: Commit**

```bash
git add CLAUDE.md AGENTS.md docs/RUNBOOK.md
git commit -m "docs(museum-nl): record built codespace-only source"
```

---

## Self-Review

**Spec coverage:**
- Two-phase / SourcePOI emission → Tasks 1, 3 ✓
- JSON-LD acquisition, no PDOK → Tasks 3, 4 ✓
- snapshot all-network NDJSON `{slug,url,html}` → Task 4 ✓
- normalize deterministic, JSON-LD + meta, museum filter, skip no-geo → Task 3 ✓
- Fields name/lat/lon/address/website/phone/description + provenance → Task 3 ✓
- Stable `source_record_id` slug-based → Task 3 ✓
- Manifest (license/permission, category_map, expected_count, codespace-only) → Task 1 ✓
- No new dependency → confirmed (stdlib only) ✓
- Tests (parse helpers + normalize fixtures + snapshot mock) → Tasks 2, 3, 4 ✓
- Opening hours out of scope → not implemented (correct) ✓
- Docs reflect built module → Task 5 ✓

**Placeholder scan:** no TBD/TODO; every code step shows full code. ✓

**Type consistency:** `extract_slugs`/`extract_museum_jsonld`/`extract_meta_description`/`split_street`/
`normalize_website` signatures match between Task 2 (definition) and Task 3/4 (use). `snapshot`/`normalize`
signatures match `run_cli` Protocols and `SnapshotMetadata` fields (`source_id`, `endpoint`, `query`,
`checksum`, `fetched_at`, `adapter_version`). `http_get(url, *, client, sleep)` keyword usage matches
`adapter_base`. ✓
