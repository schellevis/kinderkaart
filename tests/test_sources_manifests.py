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
