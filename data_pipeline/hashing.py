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
