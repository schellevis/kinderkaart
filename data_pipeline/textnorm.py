from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher
from urllib.parse import urlparse

_ARTICLES = {"de", "het", "een", "t", "the"}
_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def normalize_name(s: str) -> str:
    decomposed = unicodedata.normalize("NFKD", s)
    ascii_str = "".join(c for c in decomposed if not unicodedata.combining(c))
    lowered = _NON_ALNUM.sub(" ", ascii_str.lower())
    tokens = [t for t in lowered.split() if t and t not in _ARTICLES]
    return " ".join(tokens)


def name_similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, normalize_name(a), normalize_name(b)).ratio()


def website_host(url: str | None) -> str | None:
    if not url:
        return None
    host = (urlparse(url).hostname or "").lower()
    return host[4:] if host.startswith("www.") else host or None
