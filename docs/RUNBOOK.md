# Kinderkaart Runbook

Operational procedures for data refresh, codespace-only sources, and deployment.

---

## Codespace-only sources

These sources require interactive credentials or a paid API key and are **not run in CI**:

| Source | Why codespace-only |
|---|---|
| museum.nl | Scrape source; runs codespace-only (no live fetch in CI). Permission secured 2026-06-20 |
| Agent restaurants | Requires a paid/authenticated API key; curated NDJSON workflow |

### Running a codespace-only source manually

1. Open the repository in a GitHub Codespace (or a local dev environment with credentials set up).

2. Run the adapter's normalize directly. The implemented codespace-only source is
   `restaurants-agent` (curated; see `sources/restaurants_agent/README.md`):

   ```bash
   # Curate sources/restaurants_agent/curated.yaml first (each record needs >=1 direct signal),
   # then normalize it to NDJSON (inspect output before including it):
   uv run python -m sources.restaurants_agent.adapter normalize \
       sources/restaurants_agent/curated.yaml \
       --fetched-at "$(date -u +%Y-%m-%dT%H:%M:%S+00:00)" > /tmp/restaurants.ndjson
   ```

   The `museum.nl` source is now implemented (`codespace-only`). Run it the same way:

   ```bash
   uv run python -m sources.museum_nl.adapter snapshot --output /tmp/museum_nl.raw.ndjson
   uv run python -m sources.museum_nl.adapter normalize /tmp/museum_nl.raw.ndjson \
       --fetched-at "$(date -u +%Y-%m-%dT%H:%M:%S+00:00)" > /tmp/museum_nl.ndjson
   ```

   Then pass it via `--prebuilt museum-nl=/tmp/museum_nl.ndjson` (same pattern as below).

3. Pass the normalized stream explicitly to the orchestrator with `--prebuilt`:

   ```bash
   uv run python -m scripts.build_pipeline \
       --sources sources \
       --work /tmp/work \
       --out site \
       --country nl \
       --prebuilt restaurants-agent=/tmp/restaurants.ndjson \
       --data-version "$(date -u +%Y.%m.%d)-local"
   ```

---

## Committed-NDJSON route for codespace-only data (DECIDED 2026-06-21)

The pipeline runs in the `data-refresh` job, which skips `codespace-only` sources (they can't fetch
in CI). The chosen route to publish their data: **generate the NDJSON in a codespace and commit it
into the repo**, where the `data-refresh` job picks it up automatically.

Procedure, per codespace-only source `<id>` (`museum-nl`, `restaurants-agent`):

1. Generate the normalized NDJSON in a codespace (see sections above for the per-source commands).
2. Commit it under a stable path:

   ```bash
   mkdir -p data/prebuilt
   cp /tmp/<id>.ndjson data/prebuilt/<id>.ndjson   # e.g. data/prebuilt/museum-nl.ndjson
   git add data/prebuilt/<id>.ndjson
   git commit -m "data(<id>): refresh committed prebuilt snapshot"
   ```

3. Nothing else to wire. `data-refresh.yml` **auto-includes every `data/prebuilt/*.ndjson`** via
   `--prebuilt` (the file basename maps to the source id; `_` and `-` both work). Run a data
   refresh to fold it into the published data layer.

   For `museum-nl` the source package must also be on `main` (done — merge `0571ad3`) and its
   `license_url` confirmed.

---

## Publishing museum.nl data

`museum-nl` is `codespace-only` (not openly licensed; attribute "© Museumvereniging / museum.nl").
To publish it:

1. The `sources/museum_nl/` module is **built** (implemented and tested). Run it in a Codespace to
   produce normalized NDJSON (see "Running a codespace-only source manually" above).
2. Commit its output as `data/prebuilt/museum-nl.ndjson` (committed-NDJSON route above) — the
   `data-refresh` job auto-includes it.
3. Run `data-refresh` (rebuilds the `data` branch), then trigger `deploy-pages.yml` (see below) —
   manual, with an explicit human go-ahead.

---

## Data refresh vs. deploy (decoupled)

The two workflows are **decoupled** so web changes don't trigger the slow OSM build:

- **`data-refresh.yml`** (weekly cron + `workflow_dispatch`) runs the pipeline (OSM download/parse,
  ~30–45 min) and publishes the built artifacts to the **`data` branch**. It auto-includes any
  committed `data/prebuilt/*.ndjson`. The identity registry lives on the `data` branch and is
  restored at the start of each run for id stability.
- **`deploy-pages.yml`** (auto on push to `main` + `workflow_dispatch`) builds the web app and
  publishes it together with the `data` branch — **no pipeline run**, ~2 min. A push to `main`
  deploys without rebuilding data. Data updates land on the `data` branch (not `main`), so they do
  **not** auto-deploy — dispatch a deploy after a refresh.

> The **first deploy requires the `data` branch to exist** — run `data-refresh` at least once first.

## Triggering the Pages deploy

`deploy-pages.yml` auto-deploys on every push to `main`. To deploy current `main` without a code
change, or to publish a fresh `data`-branch build, dispatch it manually:

1. Go to **Actions → Deploy to GitHub Pages → Run workflow** in the GitHub UI (or use the CLI):

   ```bash
   gh workflow run deploy-pages.yml --ref main
   ```

2. The workflow will:
   - Check out the web code (`main`) + the pre-built data (`data` branch).
   - Build the web app (`npm ci && npm run build`).
   - Assemble `public_site/` (web dist + data branch contents).
   - Deploy to GitHub Pages.

3. Verify the deployment URL shown in the workflow summary.

---

## Rolling back

### Roll back the data layer (incl. identity registry)

The published data + `identity.json` live on the **`data` branch**. To revert to a prior good build:

```bash
git fetch origin data
git log --oneline origin/data            # pick the last-known-good <good-sha>
git push origin <good-sha>:data --force-with-lease
```

Then re-run `deploy-pages.yml` to publish the reverted data. (Alternatively just re-run
`data-refresh` to rebuild from current sources.)

### Roll back a Pages deploy

1. Identify the last good workflow run under **Actions → Deploy to GitHub Pages**.
2. Re-run that workflow (its artifact is used).
   - Or revert the offending commit / data-branch state and dispatch a new deploy run.

### Re-dispatch a data refresh

```bash
gh workflow run data-refresh.yml --ref main
```

`data-refresh` serializes on `concurrency: group: data-branch`; the deploy uses a separate
`pages-deploy` group, so a deploy reads a consistent `data`-branch commit even if a refresh is mid-run.
