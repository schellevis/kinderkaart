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

2. Run the adapter's snapshot + normalize directly — for example, for `museum-nl`:

   ```bash
   # Snapshot raw data to a temp file
   uv run python -m sources.museum_nl.adapter snapshot --out /tmp/museum_nl_raw.json

   # Normalize to NDJSON (inspect output before including it)
   uv run python -m sources.museum_nl.adapter normalize \
       /tmp/museum_nl_raw.json \
       --out /tmp/museum_nl.ndjson
   ```

3. Re-run the orchestrator with `--include` to inject the NDJSON before the merge step. The `--include` flag limits which adapters run via their manifests; for a source not wired as `github-action` you can also pass the pre-built NDJSON directly:

   ```bash
   # Copy the NDJSON into the work dir that the orchestrator will pick up
   cp /tmp/museum_nl.ndjson /tmp/work/museum-nl.ndjson

   # Then run the orchestrator pointing at the existing work dir
   # (sources with existing NDJSON are merged; others are fetched live)
   uv run python -m scripts.build_pipeline \
       --sources sources \
       --work /tmp/work \
       --out site \
       --country nl \
       --data-version "$(date -u +%Y.%m.%d)-local"
   ```

   After Plan 7 (agent restaurants) lands, the curated NDJSON for that source is added to `/tmp/work/` the same way.

---

## Legal release gate for museum.nl

Before museum.nl data can be published:

1. Obtain written permission from museum.nl to redistribute their POI data under the project's combined-DB license terms.
2. Update `sources/museum_nl/manifest.yaml`: change `runtime: codespace-only` to `runtime: github-action` and add the permission evidence date.
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

This respects the `concurrency: group: data-refresh` lock, so concurrent runs will queue rather than race the identity-registry commit.
