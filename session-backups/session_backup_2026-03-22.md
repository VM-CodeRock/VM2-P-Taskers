# Session Backup — March 22, 2026

## Session Summary
Completed the Cron Monitor Redesign with RAG Integration + Daily Email pipeline. Created workflow specification document. Fixed SAM.gov cron to use internal API instead of browser automation. Seeded baselines. First combined email sent successfully.

---

## Active Cron Jobs

### 1. DHS APFS Daily Monitor
- **Cron ID**: f7adf3cd
- **Schedule**: 0 12 * * * UTC (8:00 AM AST)
- **Status**: Running successfully (6 runs completed)
- **Method**: curl to https://apfs-cloud.dhs.gov/api/forecast/ → filter 46 NAICS → diff vs previous → RAG match ALL new/updated → save results
- **Output files**:
  - `/home/user/workspace/cron_tracking/f7adf3cd/apfs_rag_results.json`
  - `/home/user/workspace/cron_tracking/f7adf3cd/apfs_naics_validation.json`
  - `/home/user/workspace/cron_tracking/f7adf3cd/apfs_changes.json`
  - `/home/user/workspace/cron_tracking/f7adf3cd/apfs_previous.json` (baseline for next run)
  - `/home/user/workspace/cron_tracking/f7adf3cd/run_summary.json`
  - `/home/user/workspace/cron_tracking/f7adf3cd/apfs_current_raw.json`
  - `/home/user/workspace/cron_tracking/f7adf3cd/apfs_current_filtered.json`
- **Last run**: March 22, 2026 — 764 total records, 256 filtered, 0 new/updated

### 2. SAM.gov Daily Opportunity Monitor
- **Cron ID**: 30af1ae5
- **Schedule**: 0 13 * * * UTC (9:00 AM AST)
- **Status**: Updated March 22 — switched from browser_task to curl API
- **Method**: curl to SAM.gov internal search API → search 11 priority NAICS → diff vs previous → RAG match ALL new/updated → save results
- **SAM.gov API**: `https://sam.gov/api/prod/sgs/v1/search/?index=opp&page={PAGE}&sort=-modifiedDate&size=25&mode=search&is_active=true&q={NAICS_CODE}` (no auth required)
- **SAM.gov detail API**: `https://sam.gov/api/prod/opps/v2/opportunities/{opp_id}` (includes NAICS codes)
- **Output files**:
  - `/home/user/workspace/cron_tracking/30af1ae5/sam_rag_results.json`
  - `/home/user/workspace/cron_tracking/30af1ae5/sam_naics_validation.json`
  - `/home/user/workspace/cron_tracking/30af1ae5/sam_changes.json`
  - `/home/user/workspace/cron_tracking/30af1ae5/sam_previous.json` (baseline for next run)
- **Baseline**: Seeded March 22, 2026 — 334 unique opportunities across 11 NAICS codes

### 3. Changeis Daily Opportunity Intelligence Email
- **Cron ID**: b7a2f309
- **Schedule**: 0 14 * * * UTC (10:00 AM AST)
- **Status**: Running successfully (first email sent March 22)
- **Method**: Reads apfs_rag_results.json + sam_rag_results.json → builds Changeis-branded HTML → sends via Outlook to varun@changeis.com
- **Outlook constraint**: Body must be plain text; full HTML attached as daily_email.html
- **Output files**:
  - `/home/user/workspace/cron_tracking/daily_email.html`
  - `/home/user/workspace/cron_tracking/email_log.json`

---

## NAICS Codes (46 total, 11 priority)

### Priority NAICS (searched daily on SAM.gov)
- 541511 — Custom Computer Programming Services
- 541512 — Computer Systems Design Services
- 541513 — Computer Facilities Management Services
- 541519 — Other Computer Related Services
- 541611 — Administrative Management and General Management Consulting
- 541612 — Human Resources Consulting Services
- 541613 — Marketing Consulting Services
- 541614 — Process, Physical Distribution, and Logistics Consulting
- 541618 — Other Management Consulting Services
- 541715 — R&D in Physical, Engineering, and Life Sciences
- 541990 — All Other Professional, Scientific, and Technical Services

### Full 46-Code Set (used for APFS filtering)
541110, 541120, 541191, 541199, 541211, 541213, 541214, 541219, 541310, 541320, 541330, 541340, 541350, 541360, 541370, 541380, 541410, 541420, 541430, 541490, 541511, 541512, 541513, 541519, 541611, 541612, 541613, 541614, 541618, 541620, 541690, 541710, 541715, 541720, 541810, 541820, 541830, 541840, 541850, 541860, 541870, 541890, 541910, 541921, 541922, 541930, 541940, 541990

---

## RAG Engine Configuration

- **URL**: https://changeis-bd-rag-production.up.railway.app
- **Auth**: X-API-Key: a3-nFpt4YJHCXpsTHS7ZAikNllzrPtCORKBoSN8tAAE
- **Endpoints**: POST /match (top_n), POST /query (top_k), POST /answer
- **Scoring Tiers**:
  - STRONG: 0.65+ (green #2D7D4A) — pursue actively
  - MODERATE: 0.50–0.64 (orange #D97D2A) — evaluate for teaming/prime
  - LOW: below 0.50 (gray #888888) — awareness only
- **NAICS Validation Recommendations**:
  - RETAIN: avg >= 0.50 or max >= 0.65
  - MONITOR: avg 0.30–0.49
  - REVIEW: avg < 0.30
- **Retry Pattern**: 3 attempts, exponential backoff (5s, 10s, 15s), 30s timeout

---

## Deliverables Created This Session

1. **Opportunity Intelligence Workflow Specification** (changeis_opportunity_workflow_spec.docx)
   - 18 pages, Changeis branded
   - Covers all 3 pipeline stages, RAG engine spec, NAICS validation, error handling, appendices
   - Pushed to GitHub: vm-coderock/VM2-P-Taskers/deliverables/changeis_opportunity_workflow_spec.docx
   - Shared as "Opportunity Intelligence Workflow Spec"

---

## Platform Constraints Documented

1. **Outlook send_email**: Body field only accepts plain text (not HTML/Markdown). Workaround: plain text summary in body + HTML attached via attachment_files parameter.
2. **File export connectors**: Dropbox, Box, Google Drive all return empty schemas from describe_external_tools — platform-level bug. SharePoint only supports list/delete.
3. **Background cron agents**: Do NOT have access to browser_task. Must use curl/fetch_url/search_web instead.
4. **GitHub push**: Works via `gh` CLI with `api_credentials=["github"]`. Requires `git config --global --add safe.directory /tmp/VM2-P-Taskers`.

---

## Shared Assets (use same name to update)
- FAA Opportunity Intelligence Report
- DHS APFS Opportunity Intelligence Report
- apfs_it_shortlist
- apfs_changes
- Changeis Opportunity Database
- Changeis Capability Matrix
- apfs_shortlist
- BAA Draft White Paper Responses
- ARAP0012 Research Brief
- ARSS0009 Research Brief
- BAA Research Prompt
- apfs_run_summary
- FHWA Safety RAG Match Report
- eFAST Corporate Experience Narrative
- eFAST Job Descriptions
- eFAST Technical Approach
- Opportunity Intelligence Workflow Spec

---

## Connected Services
- outlook (send_email confirmed working)
- github_mcp_direct (use gh CLI with api_credentials=["github"])
- gcal, fireflies, jira_mcp_merge, microsoft_teams_mcp_merge
- dropbox, sharepoint, google_drive, box (all have export issues)
- todoist__pipedream

---

## User Instructions (Persistent)
- All deliverables use Changeis brand style guide (skills/changeis-style)
- All files should be saved to Dropbox at base path 'V M2/VM2-main-folder/VM2-P/'
- GitPages: https://vm-coderock.github.io/VM2-P-Taskers/ (encrypted with StaticCrypt, password: changeis2026)
- GitHub repo: vm-coderock/VM2-P-Taskers
- Email daily analysis to varun@changeis.com
- One combined daily email for APFS + SAM.gov
- Deep-dive option for highest-rated opportunities
- RAG matching against ALL new opportunities for NAICS validation
- User timezone: America/Aruba (AST, UTC-4, no DST)

---

## Changeis Company Context
- Federal IT and management consulting firm
- President: Varun Malhotra
- Core: ERP modernization (IFS), DevSecOps, agile (SAFe), AI integration, program management, cloud (AWS/ROSA)
- Incumbent on FAA CLMRS (6973GH-22-D-00063), SCOAR IDIQ via Volpe (6913G619D300021)
- Strategic expansion target: DHS
- 46 relevant NAICS codes, 11 priority IT/consulting codes

---

## Next Expected Actions
1. Monday March 23 — first full pipeline run with real diffs (APFS 8 AM, SAM.gov 9 AM, email 10 AM)
2. NAICS validation tracking begins accumulating data
3. After 2-4 weeks, review NAICS dashboard to refine the 46-code filter set
4. User can request deep-dive on any STRONG/MODERATE opportunity from the daily email
