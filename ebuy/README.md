# eBuy Monitor — Cron Tracking

This directory holds runtime state for the **eBuy ledger** cron job.

## Files

| File | Purpose |
|---|---|
| `ebuy_history.jsonl` | Append-only event log (one event per line) |
| `state.json` | Run state: last_run_iso, counters, status |
| `parse_errors.jsonl` | Parser failure log (one error per line; empty file = no errors) |

## Cron Schedule

- **Weekdays (Mon–Fri)**: 9 AM and 4 PM ET (2 runs/day)
- **Weekends (Sat/Sun)**: 12 PM ET only (1 run/day)
- **Weekly reconciliation**: Sundays 8 PM ET (searches last 14 days for missed events)

## Dedupe key

`sha1(request_id + "|" + status + "|" + posted_date)[:16]`

Amendments, Q&A additions, and status changes count as **separate events** — they never overwrite an existing row.

## Deliverables

- `/home/user/workspace/ebuy-ledger.html` — full Changeis-branded ledger
- `/home/user/workspace/ebuy-portal-widget.html` — drop-in snippet for portal.html
- GitHub: `vm-coderock/VM2-P-Taskers/ebuy/`
- Dropbox mirror: `V M2/VM2-main-folder/VM2-eBuy/`
