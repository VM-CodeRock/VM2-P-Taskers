# VM2-OPP eBuy Ledger — Design Spec

**Version**: 2.0 (revised — notification capture only)
**Author**: VM2 / Perplexity Computer
**Date**: 2026-05-19
**Owner**: Varun Malhotra
**Status**: Spec — pending review

---

## 1. Problem

GSA eBuy consolidated notices arrive in Varun's Outlook from `ebuy_admin@gsa.gov`. The notice contains lightweight metadata (Request ID, Status, Buyer, Posted Date, Due By, Title, Contract Vehicle). **Full RFI/RFQ content lives behind a password-protected GSA portal** and cannot be fetched programmatically.

Today these notices:
- Sit in Outlook with the `BD (Superhuman/AI)` label
- Are not captured in any structured ledger
- Have no historical view of status changes (AMENDED, Q&A ADDED, CANCELED)
- Require manual triage with no audit trail of what was reviewed when

Goal: **capture every notice as it arrives, log it forever, surface a daily review view, and route interesting ones to a human analyst via a pre-drafted email.** No RAG, no auto-analysis, no deep dive — those happen later by humans after the analyst downloads the materials.

---

## 2. Design Principles

1. **Ledger only — no analysis.** Content is behind auth; we capture metadata only.
2. **Append-only history.** Every notice event is a new row. Nothing is ever overwritten.
3. **Dedupe on (Request ID + Status + Posted Date)** so amendments and Q&A additions are preserved as new events.
4. **One action per row**: "Request Analyst Download" — drafts an email to a human who can log into eBuy and pull the files.
5. **Daily review surface.** Varun reviews the ledger every day; the UI makes "what's new since yesterday" obvious.
6. **Deliverables are memory.** Ledger HTML in `VM2-P-Taskers` + JSONL in Dropbox = permanent record.

---

## 3. Architecture

### 3.1 New cron: `ebuy_monitor`

| Field | Value |
|---|---|
| Cron ID | TBD (assigned at creation) |
| Schedule | **Weekdays**: 9 AM and 4 PM ET — 2 runs/day<br>**Weekends**: 12 PM ET only — 1 run/day |
| Cron expression (UTC) | `0 13,20 * * 1-5` (weekday 9 AM/4 PM ET) + `0 16 * * 0,6` (weekend noon ET) — during EDT; auto-shifts for EST |
| Source | Outlook `search_email` with `from:ebuy_admin@gsa.gov` |
| Mailbox | `varun@changeis.com` |
| State file | `cron_tracking/ebuy_monitor/state.json` |
| History file | `cron_tracking/ebuy_monitor/ebuy_history.jsonl` |
| Repo path | `VM2-P-Taskers/ebuy/` |

**Note on cadence**: Per Varun's spec, two checks per weekday (morning + late afternoon) and one weekend run at noon. eBuy notices that arrive overnight will be picked up by the 9 AM weekday run. Each run uses a 24-hour overlap window on the Outlook search to ensure no notice is missed if a previous run failed. Weekly reconciliation cron (Sundays 8 PM ET) searches last 14 days to backstop any gaps.

### 3.2 Per-run logic

```
1. Load state.json → { last_run_iso, seen_event_hashes: [...] }
2. Search Outlook: from:ebuy_admin@gsa.gov after:{last_run_iso minus 24h overlap}
3. For each email:
   a. Parse body for Request rows (regex per §5)
   b. For each Request row, build event hash = sha1(request_id + status + posted_date)
   c. If hash NOT in seen_event_hashes:
      - Build event record (schema §4)
      - Append to ebuy_history.jsonl
      - Add hash to seen list
4. Regenerate ledger HTML from full jsonl
5. Update portal.html "Last 24h" widget
6. Update state.json (last_run_iso = now UTC)
7. Commit to VM2-P-Taskers (GitHub)
8. Mirror jsonl to Dropbox V M2/VM2-main-folder/VM2-eBuy/
```

### 3.3 No integration with combined daily brief

eBuy ledger is **standalone**. The 10 AM combined brief (cron `2eabb699`) remains APFS + SAM.gov only. Varun reviews the eBuy ledger directly as a separate daily ritual. (If integration is wanted later, easy to add — but kept out of v2.0 scope.)

---

## 4. Data Schema

### 4.1 ebuy_history.jsonl (one JSON object per line)

```json
{
  "event_id": "uuid-v4",
  "event_hash": "sha1 of request_id+status+posted_date",
  "captured_at_utc": "2026-05-19T13:00:00Z",
  "event_type": "NEW_REQUEST | AMENDED | QA_ADDED | CANCELED",
  "request_id": "RFI1812266",
  "request_title": "DOT FTA - Business Operations Specialist Support",
  "buyer": "General Services Administration / Federal Acquisition Service",
  "buyer_program": "GSA MARKET RESEARCH",
  "posted_date_et": "2026-05-15T14:19:00-04:00",
  "due_date_et": "2026-05-28T17:00:00-04:00",
  "contract_vehicle": "47QTCA18D0078",
  "source_email_id": "AAMkAD...=",
  "source_email_subject": "GSA eBuy Requests and Quotes/Bids (Consolidated Notice) - 47QTCA18D0078",
  "source_email_date_utc": "2026-05-19T03:19:17Z",
  "source_email_web_link": "https://outlook.office365.com/owa/?ItemID=...",
  "ebuy_portal_url": "https://www.ebuy.gsa.gov/",
  "download_request_status": "none | requested | received",
  "download_request_sent_at": null,
  "download_request_analyst_email": null,
  "reviewed_by_varun": false,
  "reviewed_at": null,
  "notes": ""
}
```

### 4.2 state.json

```json
{
  "last_run_iso": "2026-05-19T13:00:00Z",
  "seen_event_hashes": ["sha1...", "sha1..."],
  "total_events": 247,
  "total_unique_request_ids": 189,
  "version": "2.0"
}
```

---

## 5. Parsing rules

### 5.1 Email body pattern

```
Request ID      Status  Date/Buyer      Quote/Bid Due By        Request Title
RFI1812266      NEW REQUEST     05/15/2026 02:19 PM EDT
GSA MARKET RESEARCH
General Services Administration
Federal Acquisition Service     05/28/2026 05:00 PM EDT DOT FTA - Business Operations Specialist Support -
```

- Split body on lines matching `^(RFI|RFQ|RFP)\d+` → one block per Request
- Status = next token after Request ID (NEW REQUEST | Q&A ADDED | AMENDED | CANCELED)
- Posted date = first match of `\d{2}/\d{2}/\d{4} \d{2}:\d{2} [AP]M (EDT|EST)`
- Due date = second match of same pattern
- Buyer = lines between status line and due-date line (joined with " / ")
- Title = text following the due-date timestamp on the same line, or the next non-empty line
- Contract vehicle = extracted from subject: `Consolidated Notice\) - (\w+)`

### 5.2 Parse failures

- Any block that fails to yield a Request ID + Status + Due Date → logged to `parse_errors.jsonl`
- Ledger shows count of unparsed blocks with link to source email for manual review

---

## 6. Ledger UI

### 6.1 Full ledger page: `VM2-P-Taskers/ebuy/ebuy-ledger.html`

**Layout**:

```
┌──────────────────────────────────────────────────────────────────────┐
│  Changeis eBuy Ledger                              [Export CSV]      │
│                                                                      │
│  ▼ Today's Review (3 new since last review)                          │
│  ┌────────────────────────────────────────────────────────────────┐ │
│  │ ☐  RFI1812266 NEW  DOT FTA Bus Ops  Due 5/28  [Request DL] [✓] │ │
│  │ ☐  RFI1812181 AMD  DOT TR Program   Due 5/22  [Request DL] [✓] │ │
│  │ ☐  RFQ1811998 NEW  HHS Data Mgmt    Due 5/30  [Request DL] [✓] │ │
│  └────────────────────────────────────────────────────────────────┘ │
│  [Mark All Reviewed]                                                 │
│                                                                      │
│  Filters:                                                            │
│    Status: [NEW] [AMD] [Q&A] [CXL]                                   │
│    Tier:   active / closed / all                                     │
│    Buyer:  [______________]                                          │
│    Date range: [____] to [____]                                      │
│    Search:  [_________________________]                              │
│                                                                      │
│  Full History  (247 events, 189 unique requests)                     │
│  ┌──────────────────────────────────────────────────────────────────┐│
│  │ ▼ RFI1812266 — DOT FTA Business Ops (3 events)                  ││
│  │   2026-05-19  NEW REQUEST  Due 5/28   [Request DL] [Source]     ││
│  │   2026-05-21  Q&A ADDED    Due 5/28   [Request DL] [Source]     ││
│  │   2026-05-25  AMENDED      Due 6/02   [Request DL] [Source]     ││
│  │                                                                  ││
│  │ ▶ RFI1812181 — DOT TR Program (1 event)                         ││
│  │ ▶ RFQ1811998 — HHS Data Management (1 event)                    ││
│  │ ...                                                              ││
│  └──────────────────────────────────────────────────────────────────┘│
└──────────────────────────────────────────────────────────────────────┘
```

**Columns**: Date Captured | Request ID | Status | Buyer | Title | Vehicle | Due By | Days Left | Source Email | Download Status | Action

**Features**:
- Sortable on every column
- Filters: status (multi), active/closed (by due date), buyer (text), date range, search across title+buyer
- Status-change events nest under parent Request ID — expandable to show full lifecycle
- "Reviewed" checkbox per row (state stored in jsonl)
- "Mark All Reviewed" bulk action for today's new items
- CSV export of current filtered view
- Branded with `changeis-style` skill
- Context slug + cost estimate per VM2 deliverable rules
- Linked from portal.html

### 6.2 Portal summary widget

Insert into `portal.html`:

```
┌─────────────────────────────────────────────────────┐
│ eBuy Ledger — Last 24h                              │
│                                                     │
│  3 new  •  1 amended  •  0 Q&A  •  0 canceled       │
│  ⚠ 3 unreviewed                                     │
│                                                     │
│  Latest:                                            │
│  • RFI1812266 NEW  DOT FTA Bus Ops (due 5/28)       │
│  • RFI1812181 AMD  DOT TR Program  (due 5/22)       │
│  • RFQ1811998 NEW  HHS Data Mgmt   (due 5/30)       │
│                                                     │
│  [Open Ledger →]                                    │
└─────────────────────────────────────────────────────┘
```

---

## 7. The Single Action: "Request Analyst Download"

### 7.1 Behavior

Click on any ledger row → opens pre-drafted email. Two implementation options (decide at build time):

- **Option A (simpler)**: `mailto:` link with URL-encoded subject/body. Opens user's default mail client.
- **Option B (server-side)**: Calls Outlook connector `draft_email` to create a draft in the user's Outlook drafts folder. Better UX (proper rich formatting, attachments possible, threads correctly) but requires the ledger page to call back to a small endpoint.

**Recommendation**: Start with Option A (mailto), upgrade to Option B if needed.

### 7.2 Email template

```
To: {analyst_email}  ← TBD, Varun to provide
Subject: eBuy Download Request — {Request ID} — {Title}

Hi,

Please log into GSA eBuy and download all materials for the following notice:

  Request ID:   {Request ID}
  Status:       {Status}
  Title:        {Title}
  Buyer:        {Buyer}
  Posted:       {Posted Date ET}
  Due By:       {Due By ET}  ({Days Left} days remaining)
  Vehicle:      {Contract Vehicle}

eBuy portal:  https://www.ebuy.gsa.gov/

Once downloaded, please save all attachments to Dropbox at:
  V M2/VM2-main-folder/VM2-eBuy/{Request ID}/

Then reply to this thread so I can review and decide on next steps.

Thanks,
Varun
```

### 7.3 Row state tracking

- Before click: action button reads "Request Download"
- After click: row updates to `download_request_status: "requested"` with timestamp; button reads "Re-request" (still clickable)
- When analyst replies confirming upload: Varun (or future automation) marks row "received" — manual for v2.0

---

## 8. Daily review workflow

Varun's daily routine:

1. Morning: open portal.html → see "Last 24h" widget → click into ledger
2. Ledger opens scrolled to "Today's Review" section
3. For each new/amended/Q&A notice:
   - Skim title + buyer + due date
   - If interesting → click "Request Download" (drafts email)
   - Check the "reviewed" box
4. Click "Mark All Reviewed" when done
5. Closes loop — full audit trail of what was seen, when, and what was actioned

---

## 9. Backfill (Phase 0, before cron goes live)

1. Search Outlook for ALL `from:ebuy_admin@gsa.gov` emails (paginate, no date limit)
2. Parse every email body, extract every Request row
3. Build full `ebuy_history.jsonl`
4. Generate ledger.html with full history
5. Commit + push to VM2-P-Taskers
6. Add portal.html widget
7. Verify ledger renders correctly
8. **Then** turn cron on, with `last_run_iso` = timestamp of most recent backfilled email

---

## 10. Failure modes & safeguards

| Failure | Mitigation |
|---|---|
| Outlook search misses an email | 24h overlap window on every run |
| 6-hour gap means weekend overnight notice arrives late | Acceptable per Varun's cadence choice; weekly reconciliation cron searches last 14 days to catch gaps |
| Email body format changes | Parser logs unparsed blocks to `parse_errors.jsonl`; ledger shows banner if any unparsed events |
| Duplicate events | Event hash dedup prevents double-logging |
| Outlook connector disconnected | vm2-wrapup nightly audit checks `last_run_iso` freshness; alerts if stale > 24 hours |
| Analyst email not configured | "Request Download" button shows "⚠ Configure analyst email" tooltip; clicking opens a settings prompt |

---

## 11. Files to create

| Path | Purpose |
|---|---|
| `cron_tracking/ebuy_monitor/state.json` | Run state |
| `cron_tracking/ebuy_monitor/ebuy_history.jsonl` | Append-only event log |
| `cron_tracking/ebuy_monitor/parse_errors.jsonl` | Parser failure log |
| `VM2-P-Taskers/ebuy/ebuy-ledger.html` | Full ledger UI |
| `VM2-P-Taskers/ebuy/_data/ebuy_history.json` | Ledger data feed (mirrored from jsonl) |
| `VM2-P-Taskers/ebuy/_data/config.json` | Analyst email + other settings |
| `VM2-P-Taskers/_system/ebuy_monitor.py` | Cron script |
| `VM2-P-Taskers/_system/ebuy_parser.py` | Email body parser (unit-testable) |
| `VM2-P-Taskers/_system/ebuy_ledger_generator.py` | HTML generator |
| `VM2-P-Taskers/_system/ebuy_reconcile.py` | Weekly reconciliation script |
| Dropbox `V M2/VM2-main-folder/VM2-eBuy/` | Offline mirror of jsonl + per-RFI download folders |

---

## 12. Files to modify

| Path | Change |
|---|---|
| `VM2-P-Taskers/portal.html` | Add eBuy "Last 24h" widget; add nav link to ledger |
| vm2-opp-deep-dive skill | Add `ebuy_monitor` to cron table (note: ledger only, no deep-dive integration) |
| vm2-wrapup skill | Add eBuy monitor freshness check to nightly audit |

---

## 13. Build sequence (when approved)

1. **Spec sign-off** (this document)
2. **Analyst email captured** — Varun provides address; stored in `config.json`
3. **Parser module + unit tests** — `ebuy_parser.py` with fixtures from known emails
4. **Backfill script** — run once, build full historical jsonl
5. **Ledger generator + first render** — verify HTML, test filters/sort
6. **Portal widget** — add to portal.html
7. **Cron script** — `ebuy_monitor.py`
8. **Cron registration** — weekdays 9/12/3/6 ET + weekends 12 ET
9. **Weekly reconciliation cron** — Sundays 8 PM ET, search last 14 days, fill gaps
10. **Skill updates** — vm2-opp-deep-dive, vm2-wrapup
11. **End-to-end test** — wait for next live ebuy_admin email, verify capture
12. **Documentation** — update skills, README in `VM2-P-Taskers/ebuy/`

---

## 14. Open items

- [ ] **Analyst email address** — Varun to provide later; ledger will show placeholder until configured
- [ ] Confirm contract vehicle 47QTCA18D0078 is the only eBuy distribution Varun receives, or are there others
- [ ] Should "reviewed" state persist in jsonl, or in a separate `review_state.json` (cleaner separation since reviews aren't immutable events)?
- [ ] Optional v2.1: in-app notification at 9 AM weekday run if new unreviewed notices exist
- [ ] Optional v2.1: auto-mark "received" when analyst reply hits Outlook with matching Request ID in subject

---

## 15. Cost estimate

- **Per-run cost**: pure parsing + HTML regen, ~1k tokens, negligible
- **Backfill (one-time)**: ~10–20k tokens depending on historical email count
- **Monthly steady state**: <$0.50/mo incremental
- **No LLM-heavy operations** — this is mechanical parsing + templating

---

*End of spec v2.0.*
