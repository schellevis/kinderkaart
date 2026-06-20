# Kinderkaart Plan 6 — CI Orchestration + Deploy Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development or superpowers:executing-plans.

**Goal:** Make the project **deployment-ready**: one orchestrator that runs the whole data
pipeline (github-action sources → merge → build), GitHub Actions workflows (scheduled data refresh
+ Pages deploy of `web/dist` + data), with concurrency locking and the identity registry committed
back. **The actual public Pages deploy stays gated** behind the spec §11 legal go/no-go and is
triggered manually, not automatically.

**Architecture:** A single `scripts/build_pipeline.py` orchestrates: discover source manifests with
`runtime: github-action`, run each adapter's `snapshot`+`normalize`, `merge` (reading/committing
`data/<land>/identity.json`), then `build` into a staging dir. A `data-refresh.yml` workflow runs it
on a weekly cron + manual dispatch, commits the refreshed identity registry, and uploads the built
data as an artifact. A `deploy-pages.yml` workflow (manual `workflow_dispatch` only — the legal gate)
builds `web/`, assembles `dist/` + `data/`, and deploys to GitHub Pages. codespace-only sources
(museum.nl, agent restaurants) are excluded from CI and documented in a runbook.

**Tech Stack:** Python 3.13/uv, Node 24, GitHub Actions, actions/deploy-pages.

## Global Constraints

- Inherits prior constraints. **No automatic public publish** — `deploy-pages.yml` is
  `workflow_dispatch` only; its description states the legal go/no-go (ODbL combined-DB review +
  museum.nl permission) must be satisfied first.
- **museum.nl + agent restaurants are codespace-only** → NOT run in CI.
- Pin action versions (`actions/checkout@v4`, `actions/setup-node@v4`, `astral-sh/setup-uv@v5`,
  `actions/configure-pages@v5`, `actions/upload-pages-artifact@v3`, `actions/deploy-pages@v4`).
- **Concurrency:** the data-refresh workflow uses a `concurrency` group so two runs never race the
  identity-registry commit.
- `data_version` = the run's UTC date + short SHA (passed in; scripts don't call `Date.now()`).
- The orchestrator must run locally too (for verification), with a `--sources-filter` to skip the
  heavy OSM download during a smoke run.

---

### Task 1: Pipeline orchestrator script

**Files:** Create `scripts/build_pipeline.py`; Test `tests/test_build_pipeline.py`

**Interfaces:** `build_pipeline.run(sources_dir: Path, work_dir: Path, out_dir: Path, country: str,
data_version: str, only_runtime: str = "github-action", include_ids: set[str] | None = None,
exclude_ids: set[str] | None = None) -> dict` — discovers manifests, runs snapshot+normalize per
included source into `work_dir`, merges into `work_dir/canon.ndjson` (identity at
`out_dir/data/<country>/identity.json`, read+written), builds into `out_dir`, returns the manifest.
A `--smoke` CLI flag sets `exclude_ids={"osm"}` and uses adapters' fixtures instead of live snapshot
(via an env hook) — keep the smoke path simple: smoke uses each source's test fixture as the
snapshot input rather than fetching.

- [ ] **Step 1: Failing test** — `tests/test_build_pipeline.py` runs `run(...)` in **smoke mode**
(fixtures, exclude osm) against the repo `sources/` + `tests/fixtures/`, into a tmp dir, and asserts:
the manifest has `nl` with `counts.total >= 4`, `points.json` exists, and the identity registry file
was written. (Mirrors the manual end-to-end smoke already proven.)

```python
from pathlib import Path
from scripts.build_pipeline import run


def test_smoke_pipeline(tmp_path):
    out = tmp_path / "out"
    manifest = run(Path("sources"), tmp_path / "work", out, country="nl",
                   data_version="smoke", only_runtime="github-action",
                   exclude_ids={"osm"}, smoke=True)
    assert manifest["nl"]["counts"]["total"] >= 4
    assert (out / "data" / "nl" / "smoke" / "points.json").exists()
    assert (out / "data" / "nl" / "identity.json").exists()
```

- [ ] **Step 2:** Implement `scripts/build_pipeline.py`. For each included source it imports
`sources.<package_dir>.adapter`; in smoke mode it maps each source id to its fixture
(`tests/fixtures/<...>.json|.osm`) and calls `normalize(fixture_path, fetched_at=...)`, writing
NDJSON; in live mode it calls `snapshot` (writing a temp file + `.meta.json`) then `normalize`.
Then calls `data_pipeline.merge.run_merge` and `data_pipeline.build.build_site`. The identity path is
`out_dir/data/<country>/identity.json` (created if absent, committed by CI). Add a `__init__.py` to
`scripts/` if needed for import, and ensure `pythonpath=["."]` covers it (it does).
Provide a `main()` CLI: `--sources --work --out --country --data-version --smoke --exclude`.

- [ ] **Step 3:** `uv run pytest tests/test_build_pipeline.py` green; full bar; **commit**
`feat: add pipeline orchestrator (snapshot->normalize->merge->build) with smoke mode`.

---

### Task 2: Data-refresh workflow

**Files:** Create `.github/workflows/data-refresh.yml`

- [ ] Workflow: `on: { schedule: [{cron: "0 3 * * 1"}], workflow_dispatch: {} }`;
`concurrency: { group: data-refresh, cancel-in-progress: false }`; permissions `contents: write`.
Steps: checkout; `astral-sh/setup-uv@v5`; `uv sync`; compute `DATA_VERSION=$(date -u +%Y.%m.%d)-${GITHUB_SHA::7}`;
run `uv run python -m scripts.build_pipeline --sources sources --work /tmp/work --out site --country nl --data-version "$DATA_VERSION" --exclude ""` (live, includes OSM — note the OSM `.pbf` download is ~1.3 GB; the runner has the disk/time on a weekly cron);
commit the updated `site/data/nl/identity.json` back to the branch (`git add` + commit "chore: refresh identity registry [skip ci]" guarded by `git diff --quiet || commit`);
`actions/upload-artifact@v4` the `site/` dir (name `site-data`).

- [ ] **Validation (local):** `actionlint` if available, else `uv run python -c "import yaml,glob;[yaml.safe_load(open(f)) for f in glob.glob('.github/workflows/*.yml')]"` to assert valid YAML. **Commit** `ci: add weekly data-refresh workflow`.

---

### Task 3: Pages deploy workflow (manual, legal-gated)

**Files:** Create `.github/workflows/deploy-pages.yml`

- [ ] Workflow: `on: { workflow_dispatch: {} }` ONLY (no push/schedule). A top `# LEGAL GATE`
comment: do not run until the ODbL combined-DB legal review is "go" and museum.nl is either absent
or permission-secured (spec §11). `permissions: { pages: write, id-token: write, contents: read }`;
`concurrency: { group: pages, cancel-in-progress: true }`. Steps: checkout; setup-uv + setup-node;
`uv sync`; run the orchestrator (live) to produce `site/data`; `cd web && npm ci && npm run build`;
assemble: copy `web/dist/*` to `public_site/` and `site/data` to `public_site/data`;
`actions/configure-pages@v5`; `actions/upload-pages-artifact@v3` with `path: public_site`;
deploy job uses `actions/deploy-pages@v4` with `environment: github-pages`.

- [ ] Validate YAML as in Task 2. **Commit** `ci: add manual (legal-gated) Pages deploy workflow`.

---

### Task 4: Runbook for codespace-only sources

**Files:** Create `docs/RUNBOOK.md`

- [ ] Document: how to run codespace-only sources manually (`museum.nl`, agent restaurants) — when
permitted — by running their adapter snapshot+normalize locally and re-running the orchestrator with
`--include` to add their NDJSON before merge; the legal release-gate for museum.nl; how to trigger
`deploy-pages.yml` once the legal go/no-go is satisfied; how to roll back (revert the identity commit
+ re-dispatch). **Commit** `docs: add runbook for codespace-only sources + deploy`.

---

## Self-Review
- Orchestrator (snapshot→normalize→merge→build), smoke-tested → Task 1 ✓ (mirrors proven manual run)
- Weekly data-refresh + identity commit + concurrency → Task 2 ✓
- Pages deploy, manual + legal-gated (no auto publish) → Task 3 ✓ (respects spec §11 go/no-go)
- codespace-only sources excluded from CI + runbook → Tasks 1,4 ✓
- Pinned action versions, valid YAML → Tasks 2,3 ✓

## Notes
- Real OSM `.pbf` live fetch only runs in CI / live mode; local verification uses `--smoke` (fixtures).
- After Plan 7 (agent restaurants) lands, the runbook's `--include` flow covers adding its curated NDJSON.
