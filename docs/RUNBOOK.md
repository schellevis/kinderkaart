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

## Legal release gate for museum.nl — PASSED 2026-06-20

Both spec §11 gates are cleared: (1) the ODbL combined-DB legal review is **go**, and (2) **written
permission from museum.nl is secured**. museum.nl data may now appear in public artifacts.

Remaining work to actually publish museum.nl data:

1. The `sources/museum_nl/` module is **built** (`codespace-only`, implemented and tested). Run it in
   a Codespace to produce normalized NDJSON (see "Running a codespace-only source manually" above).
2. Include its output via `--prebuilt museum-nl=/tmp/museum_nl.ndjson` (codespace-only, as above).
3. Trigger `deploy-pages.yml` (see below) — manual, with an explicit human go-ahead.

---

## Triggering the Pages deploy

`deploy-pages.yml` is **manual only** — it has no push or schedule trigger. The legal gates are
passed (2026-06-20), but the deploy is a public, hard-to-reverse action: launch it only on an
explicit human decision, never autonomously.

To deploy:

1. Go to **Actions → Deploy to GitHub Pages → Run workflow** in the GitHub UI (or use the CLI):

   ```bash
   gh workflow run deploy-pages.yml --ref main
   ```

2. The workflow will:
   - Run the full live pipeline (all `github-action` sources including OSM).
   - Build the web app (`npm ci && npm run build`).
   - Assemble `public_site/` (web dist + data).
   - Deploy to GitHub Pages.

3. Verify the deployment URL shown in the workflow summary.

---

## Rolling back a bad deploy

### Roll back the identity registry commit

If a data-refresh run committed a bad `identity.json`:

```bash
# Find the last-known-good commit for identity.json
git log --oneline -- site/data/nl/identity.json

# Revert to that commit's version
git checkout <good-sha> -- site/data/nl/identity.json
git commit -m "fix: revert identity registry to last-known-good"
git push
```

### Roll back a Pages deploy

1. Identify the last good workflow run under **Actions → Deploy to GitHub Pages**.
2. Re-run that workflow (the artifact from that run is used).
   - Or revert the offending commit and dispatch a new deploy run.

### Re-dispatch a data refresh

```bash
gh workflow run data-refresh.yml --ref main
```

This respects the shared `concurrency: group: identity-registry` lock, so refresh and deploy runs queue rather than race the registry commit.
