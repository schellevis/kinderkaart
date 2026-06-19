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
