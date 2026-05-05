# VM2-P-Taskers — System Architecture

**Last updated**: 2026-05-05
**Owner**: Varun Malhotra (varun@changeis.com)
**Repo**: [vm-coderock/VM2-P-Taskers](https://github.com/vm-coderock/VM2-P-Taskers)
**Live URL**: https://vm2-p-taskers-production.up.railway.app

This document is the authoritative reference for how the VM2 publishing system fits together. Read this first if you (or a future agent) need to understand, debug, or rebuild any component.

---

## 1. Layered overview

```
┌─────────────────────────────────────────────────────────────────────┐
│  AUTHORING / GENERATION LAYER                                       │
│                                                                     │
│  Perplexity Computer ─── crons ──────────────────────┐              │
│    └─ Email-driven                                    │              │
│    └─ Scheduled (Gmail intake, compliance, briefs)    │              │
│                                                       ▼              │
│         (writes HTML files + commits + pushes to GitHub)             │
└─────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│  STORAGE LAYER                                                       │
│                                                                     │
│  GitHub: vm-coderock/VM2-P-Taskers                                  │
│    ├─ portal.html              ← canonical index of all deliverables│
│    ├─ projects.html            ← command center for project threads │
│    ├─ project-<slug>.html      ← long-lived project pages           │
│    ├─ <slug>-YYYY-MM-DD.html   ← dated immutable snapshots (681+)   │
│    ├─ scripts/                 ← portal/project helpers + lint      │
│    ├─ api/                     ← FastAPI sidecar source             │
│    ├─ Dockerfile + nginx.conf  ← static-site Railway service        │
│    └─ docs/                    ← this folder                         │
└─────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│  HOSTING LAYER (Railway, two services)                              │
│                                                                     │
│  ┌─────────────────────────┐      ┌──────────────────────────────┐  │
│  │ Service A: vm2-portal   │      │ Service B: vm2-projects-api  │  │
│  │   nginx:alpine          │      │   python:3.12 + FastAPI      │  │
│  │   Serves static HTML    │◄────►│   Serves /api/projects/*     │  │
│  │   Basic-auth gate       │      │   /api/deliverables          │  │
│  │   Proxies /api/* → B    │      │   /api/health                │  │
│  │   Public URL            │      │   Internal-only on .railway  │  │
│  └─────────────────────────┘      └──────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
                       (Browser, basic-auth)
```

---

## 2. The four primary file types

| File | Mutable? | Created by | Purpose |
|---|---|---|---|
| `<slug>-YYYY-MM-DD.html` | No | Email-task crons | Dated snapshot deliverable; immutable record |
| `project-<slug>.html` | Yes | `project_helper.py` | Long-lived topic page; aggregates snapshots + update notes |
| `portal.html` | Yes | `portal_add_entry.py` | Canonical index of all files (table view) |
| `projects.html` | Yes (rendered) | `projects.html` itself + API | Project command center (cards / list / compact views, picker modal) |

**Critical rule**: Never freeform-edit `portal.html` or `project-<slug>.html`. Always use the helper scripts. See `scripts/README.md`.

---

## 3. Hosting topology (Railway)

There are **two Railway services** in one Railway project:

### Service A: `vm2-portal` (nginx static)

- **Source**: top-level `Dockerfile` + `nginx.conf` + `entrypoint.sh`
- **Image**: `nginx:alpine`
- **Public URL**: `vm2-p-taskers-production.up.railway.app`
- **Auth**: nginx basic-auth (username `vm2`, password from `VM2_AUTH_PASSWORD` env var)
- **Routes**:
  - `/` → static files from the repo
  - `/api/todoist/*` → proxies to Todoist API (with server-side bearer token)
  - `/api/projects`, `/api/deliverables`, `/api/health` → proxies to Service B
- **Required env vars**:
  - `VM2_AUTH_USERNAME` (default: `vm2`)
  - `VM2_AUTH_PASSWORD` (default: `97harry23!`)
  - `VM2_TODOIST_TOKEN` (for Todoist deep-dive proxy)
- **Optional env vars**:
  - `VM2_PROJECTS_API_URL` — override the default `http://vm2-projects-api.railway.internal:8000`

### Service B: `vm2-projects-api` (FastAPI)

- **Source**: `api/Dockerfile` + `api/projects_api.py`
- **Image**: `python:3.12-slim`
- **URL**: Internal only (`vm2-projects-api.railway.internal:8000`); not exposed publicly
- **Auth**: None of its own — depends on nginx basic-auth in front
- **Behavior at boot**:
  1. Clones `vm-coderock/VM2-P-Taskers` to `/repo` (using `GITHUB_TOKEN`)
  2. Configures git author identity
  3. Imports `project_helper.py` from `/repo/scripts/`
  4. Starts uvicorn on `$PORT`
- **Required env vars**:
  - `GITHUB_TOKEN` — PAT with `repo` scope
  - `GIT_USER_EMAIL=vm2@changeis.com`
  - `GIT_USER_NAME=VM2 Projects API`
- **Endpoints** (see `api/README.md` for full Pydantic models):
  - `GET /api/health` — liveness
  - `GET /api/projects` — list all projects
  - `GET /api/deliverables` — list all dated HTML files with project membership
  - `POST /api/projects/promote` — create a new project
  - `POST /api/projects/add-snapshot` — add a single deliverable to existing project
  - `POST /api/projects/add-many` — bulk-add multiple deliverables atomically
  - `POST /api/projects/append` — append an update note to a project's timeline
  - `POST /api/projects/rename` — rename a project slug
  - `POST /api/projects/set-status` — change project status

### Communication

```
Browser → https://<railway-url>/projects.html
        ↳ HTML loads (basic-auth required)
        ↳ JS calls /api/projects → nginx proxies → vm2-projects-api → returns JSON
        ↳ User clicks "+ Add deliverable"
        ↳ JS calls /api/projects/add-many → API mutates /repo, commits, pushes
        ↳ GitHub webhook triggers Railway redeploy of vm2-portal
        ↳ Updated static HTML live in ~30s
```

---

## 4. Authoring layer (Perplexity Computer + crons)

Six recurring tasks publish to the repo. Each one is a separate Perplexity Computer cron.

| Cron | Schedule (UTC) | Skill | Output |
|---|---|---|---|
| Gmail Task Intake | `29 12-23 * * 1-5` | `vm2-gmail-tasks` | `<slug>-YYYY-MM-DD.html` |
| Nightly Compliance Audit | `0 2 * * 0,1,3,5` | `vm2-wrapup` | `compliance-report-YYYY-MM-DD.html` |
| Daily Todoist Auto-Helper | `0 11 * * *` | `vm2-gmail-tasks` (subset) | `vm2-auto-helper-YYYY-MM-DD.html` |
| Weekly Digest & Git Tag | `0 12 * * 6` | `vm2-wrapup` | `weekly-digest-YYYY-MM-DD.html` |
| Monthly Dropbox Integrity | `0 13 1 * *` | (inline task) | Dropbox sync only |
| CCC Cardio Tennis Check-In | `0 12 * * 0` | (inline task) | Email only |

Cron specifics live in the Perplexity scheduler. Recreate from memory or from the disaster-recovery runbook.

### Standard publish flow for any cron

```bash
# 1. Generate HTML deliverable
echo "<html>...</html>" > <slug>-YYYY-MM-DD.html

# 2. Add proper row to portal (NEVER edit portal.html directly)
python3 scripts/portal_add_entry.py \
    --file <slug>-YYYY-MM-DD.html \
    --title "<title>" \
    --type "<Daily Brief|Auto-Helper|...>" \
    --date YYYY-MM-DD

# 3. Verify integrity
python3 scripts/portal_lint.py

# 4. Commit and push (Railway auto-redeploys)
git add <slug>-YYYY-MM-DD.html portal.html
git commit -m "..."
git push
```

The Promote-to-Project button (`scripts/promote_button.html`) should be embedded in every new deliverable via `</body>` injection. The skill `vm2-gmail-tasks` documents this.

---

## 5. Project Threads system (added May 5, 2026)

The newest layer. Solves the "every deliverable is a dead-end snapshot" problem by adding a project abstraction above individual files.

### Data model

Each project page is **self-contained**: a styled HTML view of state, plus a JSON state block embedded in an HTML comment for round-tripping. No separate database.

```
project-army-maps.html
├── <!DOCTYPE html>
├── ... rendered Charter-serif page (status pill, summary, timeline, related)
└── <!-- PROJECT_STATE_JSON_BEGIN
    {
      "slug": "army-maps",
      "title": "Army MAPS Recompete (W15P7T-26-R-A006)",
      "status": "active",
      "owner": "Varun",
      "created": "2026-05-05",
      "updated": "2026-05-05",
      "latest_summary": "...",
      "open_items": [{"text": "...", "done": false}],
      "related": ["faa-clmrs", "..."],
      "timeline": [
        {"file": "...html", "date": "...", "title": "...", "kind": "snapshot", "body": ""},
        {"date": "...", "title": "...", "kind": "update", "body": "..."}
      ]
    }
    PROJECT_STATE_JSON_END -->
```

### Components

| File | Purpose |
|---|---|
| `scripts/project_helper.py` | CLI for managing projects (`promote`, `add-snapshot`, `append`, `link`, `rename`, `set-status`, `set-summary`, `list`) |
| `scripts/project_template.py` | Charter-serif HTML template; imported by helper |
| `scripts/promote_button.html` | Self-contained UI snippet — embed in every deliverable |
| `api/projects_api.py` | FastAPI sidecar exposing `/api/projects/*` endpoints |
| `projects.html` | Command-center view (cards/list/compact + picker modal) |

### Workflow patterns

**A. Manual promotion via email** (Varun's preferred entry):
```
VM2 promote army-maps to project
  → cron picks up email
  → runs project_helper.py promote --slug army-maps
  → all army-maps-*.html files are pulled into timeline (slug-prefix match)
  → project page committed and pushed
```

**B. UI promotion via button**:
```
User clicks "📌 Promote to Project ▾" on any deliverable
  → dropdown fetches /api/projects, populates picker
  → user picks existing or creates new
  → POST /api/projects/promote or /add-snapshot
  → API mutates project page, commits, pushes
  → page reloads with "📌 <Project Title>" badge
```

**C. Bulk historical attachment via projects.html**:
```
User opens /projects.html
  → clicks "+ Add deliverable" on a project card
  → modal browses all 681 dated files (filter by text, toggle linked/unlinked)
  → user multi-selects 10 files
  → POST /api/projects/add-many → atomic insert + push
```

**D. Update note (no new file)**:
```
VM2 update army-maps: Booz Allen confirmed as prime
  → cron parses syntax
  → POST /api/projects/append
  → timestamped section appended to project's timeline
```

---

## 6. Auth / secrets inventory

| Where stored | What | Used by |
|---|---|---|
| Railway env (`vm2-portal`) | `VM2_AUTH_PASSWORD` | nginx basic-auth |
| Railway env (`vm2-portal`) | `VM2_TODOIST_TOKEN` | Todoist API proxy |
| Railway env (`vm2-projects-api`) | `GITHUB_TOKEN` | git push from API |
| Honcho Memory MCP | StaticCrypt password references (deprecated) | Historical only |
| Local Perplexity scheduler | Cron task instructions | Perplexity Computer |
| Honcho memory | Cron IDs, decisions, preferences | Cross-session continuity |

**Password protection**: All passwords gate at nginx; the API has no auth of its own. **Never expose `vm2-projects-api` directly to the public internet.**

---

## 7. Adjacent systems (not in this repo but interconnected)

- **Honcho Memory MCP** — `https://web-production-1cfeca.up.railway.app/mcp` — durable cross-session memory for Perplexity Computer. Bootstrap at session start, closeout at end.
- **Dropbox** — `V M2/VM2-main-folder/VM2-P/` — backup copies of every deliverable, plus configuration and session backups.
- **Gmail (vm2.viru@gmail.com)** — task submission channel; Gmail cron parses inbox.
- **Todoist** — task management; VM2 label triggers automation; vm2-done label closes the loop.
- **Perplexity Computer scheduler** — hosts the recurring crons.

---

## 8. Critical invariants (DO NOT BREAK)

1. **Plain HTML only.** No StaticCrypt. No client-side encryption. Auth is nginx basic-auth.
2. **Use the helpers.** Never freeform-edit `portal.html` or `project-<slug>.html`. Use `portal_add_entry.py` and `project_helper.py`.
3. **Lint before push.** `portal_lint.py` must exit 0 after any change touching `portal.html`.
4. **Slug naming.** Lowercase, hyphenated, alphanumeric only. Topic-first. No version numbers in slug.
5. **Filename convention.** `<slug>-YYYY-MM-DD.html` for snapshots. `project-<slug>.html` for projects.
6. **API has no auth of its own.** Always behind nginx basic-auth.
7. **Concurrent commits.** API does pull-rebase before push; on conflict returns 409. Browser retries once.

---

## 9. File reference

```
VM2-P-Taskers/
├── Dockerfile                  ← Service A (nginx static)
├── nginx.conf                  ← Service A config
├── entrypoint.sh               ← Service A boot
├── portal.html                 ← Canonical index (table)
├── projects.html               ← Project command center
├── project-<slug>.html         ← One per project (3 today)
├── <slug>-YYYY-MM-DD.html      ← 681 dated deliverables
├── api/
│   ├── projects_api.py         ← Service B (FastAPI)
│   ├── Dockerfile              ← Service B
│   ├── entrypoint.sh           ← Service B boot
│   ├── requirements.txt        ← Pinned deps
│   ├── railway.toml            ← Railway service config
│   └── README.md               ← API operator notes
├── scripts/
│   ├── portal_add_entry.py     ← Safe portal mutator
│   ├── portal_lint.py          ← Integrity guard
│   ├── project_helper.py       ← Project CLI
│   ├── project_template.py     ← Project HTML template
│   ├── promote_button.html     ← UI snippet for deliverables
│   └── README.md               ← Helper guide
├── docs/
│   ├── ARCHITECTURE.md         ← This file
│   └── DR-RUNBOOK.md           ← Disaster recovery
├── _system/
│   ├── deep-dive-button.js     ← Existing daily-brief button
│   ├── deep-dive-spec.md       ← Spec for that button
│   └── ...
├── vm2-tests.sh                ← End-to-end tests
└── .gitignore
```
