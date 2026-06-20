# Source template

1. Copy this folder to `sources/<package_dir>/` where `package_dir = id.replace("-", "_")`.
2. Edit `manifest.yaml` (id, license + evidence date + republication terms, runtime,
   category_map, expected_count).
3. Implement `snapshot()` and `normalize()` in `adapter.py`; fill `field_provenance`.
4. Add `tests/test_<package_dir>.py` with a small fixture asserting `normalize` output
   (one SourcePOI per distinct source record; stable rules for multi-values).
5. Run the full bar: `uv run ruff check . && uv run mypy data_pipeline sources && uv run pytest`.
