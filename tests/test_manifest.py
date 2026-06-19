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
