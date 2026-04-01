# Cron Tracking — 8f2a4ac1 (SAM.gov Daily Monitor)

This directory stores *state* for the scheduled SAM.gov Daily Monitor task so runs can be incremental and deduplicated.

## Files
- `state.json` — last_run_utc, last_postedTo_date, seen_notice_ids (bounded), last_output_files
- `run_log.ndjson` — append-only structured log (bounded via rotation if needed)

## Notes
- Keep `seen_notice_ids` capped to avoid linear growth.
