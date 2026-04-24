# Tango / MakeGov integration for VM2-OPP

Read-only Tango API client and monitor for the Changeis opportunity intelligence workflow. Complements (does not replace) the existing SAM and APFS monitors under `backups/scripts/`.

## What's here

- `tango/client.py` — `TangoClient`: GET-only HTTP client with auth, pagination (`next` URL), shape support (`?shape=`), and bounded retry/backoff for 429 + 5xx. Auth header is configurable.
- `tango/normalizer.py` — maps Tango `opportunity` / `forecast` / `contract` rows to the VM2-OPP field shape (same keys the SAM monitor emits, plus a `source` discriminator and `tango_link`).
- `tango/enrichment.py` — incumbent / recompete lookup via `/api/contracts/`.
- `tango/monitor.py` — CLI entrypoint (`python -m tango.monitor`) that runs a full dry-run pass and writes JSON + Markdown + HTML artifacts.
- `tango/mock.py` — file-backed `MockTangoClient` for offline runs (no network, no API key).
- `tango/fixtures/*.json` — canned Tango payloads used by mock mode and tests.
- `tango/tests/` — 42 stdlib `unittest` cases for client, normalizer, enrichment, monitor.

## Environment variables

| Var | Required | Default | Purpose |
|---|---|---|---|
| `TANGO_API_KEY` | yes (live mode) | — | API key from https://tango.makegov.com/accounts/profile/. Not required with `--mock`. |
| `TANGO_AUTH_HEADER` | no | `X-API-KEY` | Override the header name if Tango standardizes on something different (e.g. `Authorization`). |

Nothing is hardcoded; the client raises `TangoAuthError` when the key is missing in live mode.

Auth style was confirmed from https://tango.makegov.com/docs/getting-started/authentication :

```
curl -H "X-API-KEY: your-api-key-here" https://tango.makegov.com/api/contracts/
```

## Sample commands

```bash
# Offline dry run — no API key required
python -m tango.monitor --mock --output-dir tango/output

# Live dry run with defaults (Changeis priority NAICS + agencies)
TANGO_API_KEY=... python -m tango.monitor --output-dir tango/output

# Narrow the scope
TANGO_API_KEY=... python -m tango.monitor \
  --naics 541511 --naics 541512 \
  --agency "Department of the Army" \
  --max-opportunities 100 \
  --output-dir tango/output

# Override attachment-search keyword clusters
TANGO_API_KEY=... python -m tango.monitor \
  --keyword-cluster "ai=large language model OR generative AI" \
  --keyword-cluster "cyber=zero trust OR RMF" \
  --output-dir tango/output

# Skip incumbent/recompete enrichment (fewer API calls)
TANGO_API_KEY=... python -m tango.monitor --no-enrich --output-dir tango/output
```

Artifacts written per run (date-stamped):

- `tango-dry-run-YYYY-MM-DD.json` — full structured output (downstream consumers parse this).
- `tango-dry-run-YYYY-MM-DD.md` — human-readable summary.
- `tango-dry-run-YYYY-MM-DD.html` — brief-compatible HTML card (matches the VM2-OPP Calibri/navy palette).

## Tests

```bash
python3 -m unittest discover -s tango/tests -v
```

42 tests, no network, no API key required. The monitor end-to-end test exercises the full pipeline against `MockTangoClient`.

## Wire-up plan for the daily combined brief + Todoist queue

Current behavior: **nothing is wired into production.** The monitor only writes dry-run files. The existing `backups/scripts/run_sam_monitor.py` and APFS monitor cron jobs are untouched.

To enable in production, follow this staged rollout:

1. **Dry-run in parallel (days 1–7)**
   Schedule `python -m tango.monitor --output-dir /home/user/workspace/cron_tracking/tango` daily at the same cadence as the SAM monitor. Review the Markdown output next to the SAM baseline. No Todoist push, no combined-brief inclusion.
   - Success criteria: Tango returns the expected NAICS/agency set; normalized rows match the VM2-OPP shape (the `test_vm2_opp_shape_parity` test already verifies this).

2. **Merge into the combined daily brief (days 8–14)**
   Extend `backups/scripts/generate_daily_brief.py` to read `tango-dry-run-<date>.json` alongside `sam_rag_results.json` and `apfs_rag_results.json`. Deduplicate by `solicitation_number` (Tango wins when both sources have hits, since Tango carries attachment snippets and incumbent enrichment). Render Tango items under a new "MakeGov/Tango" subsection in the brief.
   - Backout path: comment out the new read; brief falls back to SAM + APFS.

3. **Score + push to the vm2-opp Todoist queue (day 15+)**
   Pipe Tango opportunities through the existing Changeis RAG scorer (`call_rag(...)` in `run_sam_monitor.py`). For rows with `rag_tier` in `{"STRONG", "MODERATE"}` **and** an incumbent match within the recompete window, push a Todoist task tagged `vm2-opp` and `tango`. Gate this behind a `--push-todoist` flag that currently only logs a warning; the flag is the kill-switch for production.
   - The monitor already accepts `--push-todoist`; the actual HTTP call to Todoist should reuse the existing helper in `backups/scripts/build_daily_email.py` or whatever module the SAM monitor currently uses (search for "todoist" in that dir).

4. **Attachment deep-dive (day 30+)**
   When a Tango opportunity has high-value attachment snippets (e.g. cluster=`ai_ml` with score > 0.8), auto-route the sol number into the existing deep-dive brief generator (`_system/deep-dive-spec.md`).

## Safety rails already in place

- `--push-todoist` currently only logs a warning; it never creates tasks.
- The monitor never modifies data in Tango (GET-only client).
- No cron files were edited by this branch; the operator owns enablement.
- `MockTangoClient` is a full drop-in, so CI can run without secrets.

## Open questions for Varun

- Preferred header if Tango enterprise accounts use OAuth2 instead of API key. Default is `X-API-KEY`; switch via `TANGO_AUTH_HEADER`.
- Confirm the agency naming convention Tango uses internally — the default `PRIORITY_AGENCIES` list uses Department full names. If Tango expects codes (e.g. `9700`), swap or add the codes to `tango/config.py`.
- Decide whether forecasts should be scored by the RAG pipeline at dry-run time or only when promoted to Todoist.
