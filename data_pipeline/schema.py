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
    address: dict[str, str] | None = None

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
