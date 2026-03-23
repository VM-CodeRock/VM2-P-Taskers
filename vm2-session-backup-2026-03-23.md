# VM2 Session Backup — March 23, 2026

## Session Summary
This session continued from the March 22 compaction summary. Key work done:
- Created CCC Cardio Tennis weekly cron (20aefc72) and process deliverable HTML
- Added search/filter bar to the VM2 index (text search, 15 type pills, date range)
- Ran compliance audit #3 (12 deliverables audited, 6 index entries auto-fixed)
- Optimized cron schedules to reduce credit usage by ~62%
- Gmail cron ran 67 times total (runs #58-67 in this session, all quiet)

## Active Cron Configuration (OPTIMIZED March 23)

| ID | Name | Schedule (UTC) | Notes |
|---|---|---|---|
| aa619acf | VM2 Gmail Task Intake | 29 12-23 * * 1-5 | Business hours Mon-Fri only (was 24/7) |
| 5d17753f | VM2 Nightly Compliance Audit | 0 2 * * 0,1,3,5 | Every other day (was nightly) |
| f60246a0 | VM2 Daily Todoist Auto-Helper | 0 11 * * * | Daily, unchanged |
| 4dcac333 | VM2 Weekly Digest & Git Tag | 0 12 * * 6 | Saturdays, unchanged |
| 9819e0d3 | VM2 Monthly Dropbox Integrity | 0 13 1 * * | 1st of month, unchanged |
| 20aefc72 | CCC Cardio Tennis Weekly | 0 12 * * 0 | Sundays 8am ET, NEW this session |

## Key Details to Preserve
- Git config: user.email=vm2@changeis.com, user.name="VM2 Perplexity Computer"
- StaticCrypt password: **97harry23!** (standardized from changeis2026/jungpura23 in prior session)
- StaticCrypt command: `staticrypt file.html -p "97harry23!" --short -d . --config false`
- VM-CodeRock session still uses old passwords sometimes -- compliance audit catches regressions
- Dropbox target path: "V M2/VM2-main-folder/VM2-P/"
- Gmail connector source_id: `gcal` (CONNECTED) -- cannot apply labels or archive
- Todoist connector source_id: `todoist__pipedream` (CONNECTED) -- VM2 label ID: 2183231010
- Dropbox connector source_id: `dropbox` (CONNECTED) -- export_files has no schema (known issue)
- Outlook connector source_id: `outlook` (CONNECTED)

## Deliverables Created This Session
1. **ccc-cardio-tennis-automation-2026-03-22.html** -- Process documentation for CCC Cardio Tennis weekly automation
2. **compliance-audit-2026-03-23.html** -- Nightly audit #3, 12 deliverables, 6 auto-fixed
3. **Index filter bar** -- Added text search, type pills, date range to index.html

## Index State
- 75 deliverables in index (was 67 at session start)
- 6 entries added by compliance audit (VM-CodeRock files not indexed)
- 1 entry added for CCC Cardio Tennis deliverable
- 1 entry added for compliance audit #3
- Pre-encrypt source: /home/user/workspace/index_pre_encrypt.html

## Gmail Pipeline State
- 50 processed email IDs, 7 system-skipped IDs
- 21 tasks executed total across all sessions
- Watch thread: YPO Couples Retreat RSVPs (0 responses so far)
- All pending actions completed (cardio tennis cron + deliverable)

## Connector Details
- GitHub: `api_credentials=["github"]` for all git/gh commands. Repo: vm-coderock/VM2-P-Taskers
- Gmail: source_id `gcal` -- cannot apply labels or archive
- Todoist: source_id `todoist__pipedream` -- VM2 label ID 2183231010
- Dropbox: source_id `dropbox` -- export_files returns no schema
- Outlook: source_id `outlook`

## User Instructions (Verbatim)
- "Keep this updated for every task: https://vm-coderock.github.io/VM2-P-Taskers/index.html; also keep a copy in Dropbox"
- "Push to GitHub Pages (ask when) - always assume yes. Behind a password."
- "In most cases the VM2 instructions will be at the top of the body of the gmail."
- "Once you have completed executing a task, please label it as 'vm2-done'."
- "Each VM2 task MUST be executed as a separate Perplexity Computer session"
- "ALWAYS use: staticrypt file.html -p '97harry23!' --short -d . --config false"
- "NEVER re-encrypt a file that already contains 'staticrypt-html'"
- "Dont automatically sign up [for CCC tennis]. Ask me by sending me an email."
- "Make sure this [CCC tennis] gets logged as a deliverable in the index and also document the process"
- Credit optimization: Gmail check business hours only, compliance audit every other day

## CCC Cardio Tennis
- Cron ID: 20aefc72, every Sunday 12:00 UTC (8am ET)
- CCC login: vmalhotra / Pencil@2407
- Calendar URL: https://www.ccclub.org/Default.aspx?p=v35Calendar&title=Tennis%20Events&view=l5&ssid=323474&vnf=1
- Congressional Country Club, 8500 River Rd, Bethesda, MD 20817
- RULE: Never auto-sign up. Email Varun with calendar + conflicts, wait for YES reply.
- First run: Sunday March 29, 2026

## Files on Disk
- /home/user/workspace/index_pre_encrypt.html -- Unencrypted index (75 entries + filter bar)
- /home/user/workspace/cron_tracking/aa619acf/state.json -- Gmail cron state
- /home/user/workspace/cron_tracking/5d17753f/state.json -- Compliance audit state
- /home/user/workspace/cron_tracking/f60246a0/state.json -- Auto-Helper state
- /home/user/workspace/cron_tracking/4dcac333/state.json -- Weekly digest state
- /home/user/workspace/todoist_full_scan.json -- Full Todoist scan
- /home/user/workspace/active_projects.json -- 34 active Todoist projects
- /home/user/workspace/vm2-deliverable-template.md -- VM2 HTML style guide
