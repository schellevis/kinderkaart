# Committed prebuilt NDJSON

Normalized NDJSON for **codespace-only** sources (`museum-nl`, `restaurants-agent`) that cannot
fetch in CI. Generated in a codespace, committed here, and fed to the CI deploy via
`--prebuilt <id>=data/prebuilt/<id>.ndjson`.

See `docs/RUNBOOK.md` → "Committed-NDJSON route for codespace-only data" for the full procedure.

Only add a `--prebuilt` flag to `deploy-pages.yml` once the matching `<id>.ndjson` exists here,
or the deploy fails on a missing file.
