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
    # If url has a scheme (contains ://), only accept http/https
    if "://" in url:
        return url if re.match(r"^https?://", url, re.IGNORECASE) else None
    # If url contains : but no ://, it's likely a scheme like mailto:, reject it
    if ":" in url:
        return None
    # Otherwise, prepend https://
    return "https://" + url
