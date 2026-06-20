# Kinderkaart Runbook

Operational procedures for data refresh, codespace-only sources, and deployment.

---

## Codespace-only sources

These sources require interactive credentials or a paid API key and are **not run in CI**:

| Source | Why codespace-only |
|---|---|
| museum.nl | Written permission not yet secured (spec §11 legal gate) |
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

   > **Note:** the `museum.nl` source is **not yet implemented** — it is release-gated (see below).
   > When/if it is added (a `sources/museum_nl/` module with a `snapshot`+`normalize` adapter), it
   > follows the same `snapshot --output PATH` / `normalize PATH` contract as the other adapters.

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

## Legal release gate for museum.nl

museum.nl has **no source module yet** (deliberately not built — RCE + Wikidata already cover
museums under open licences). Before any museum.nl data could be published:

1. Obtain written permission from museum.nl to redistribute their POI data under the project's combined-DB license terms.
2. Add a `sources/museum_nl/` module (manifest + adapter, same contract as the others). Start it `runtime: codespace-only`; flip to `github-action` only once permission + evidence date are recorded.
3. Satisfy the ODbL combined-DB review for the full dataset (spec §11).
4. Only then trigger `deploy-pages.yml` (see below).

---

## Triggering the Pages deploy (after legal go/no-go)

`deploy-pages.yml` is **manual only** — it has no push or schedule trigger. Do not trigger it until both legal conditions in the workflow's `# LEGAL GATE` comment are satisfied.

Once the legal go/no-go is confirmed:

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
