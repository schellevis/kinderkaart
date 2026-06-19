# Kindvriendelijke restaurants (agent-gecureerd)

This is a **codespace-only** source. It has no automated fetch step; entries are curated
manually (or by an agent in a codespace) and verified by a human before inclusion.

## Curation workflow

1. Copy `curated.example.yaml` to `curated.yaml` in this directory:
   ```
   cp curated.example.yaml curated.yaml
   ```

2. Populate `curated.yaml` with verified restaurant entries. Each entry needs:
   - `name`, `lat`, `lon` (required)
   - `website` (optional but recommended)
   - `evidence` list with at least one entry having `direct: true` and a signal from:
     `kindermenu`, `speelhoek`, `kinderstoel`, `verschoontafel`
   - Each evidence entry must have `signal`, `direct`, `source_url`, and `evidence_date`

   An agent may draft entries; a human must verify each direct signal against the source URL.

3. Run the normalizer to produce NDJSON:
   ```
   uv run python -m sources.restaurants_agent.adapter normalize curated.yaml --fetched-at 2026-06-19T00:00:00+00:00
   ```

4. Feed the NDJSON to the merge via the Plan 6 orchestrator `--include` flag:
   ```
   uv run python -m data_pipeline.orchestrator --include restaurants-agent ...
   ```

## Evidence gate

Records lacking at least one evidence entry with `direct: true` and a recognized direct
signal (`kindermenu`, `speelhoek`, `kinderstoel`, `verschoontafel`) are **dropped silently**.
Indirect signals such as `nabije_speeltuin` are supplementary only and never sufficient alone.

## Never commit unverified entries

Do not commit `curated.yaml` with entries whose direct evidence you have not personally
verified. The example file (`curated.example.yaml`) is for illustration only and must not
be published as real data.
