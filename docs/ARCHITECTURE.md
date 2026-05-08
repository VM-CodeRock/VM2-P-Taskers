# VM2-P-Taskers — System Architecture

**Last updated**: 2026-05-08
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

**Critical rule**: Never freeform-edit `portal.html` or `project-<slug>.html`. Always use the helper scripts (or the Projects API). See `scripts/README.md`.

---

## 3. Hosting topology (Railway)

There are **two Railway services** in one Railway project:

### Service A: `vm2-portal` (nginx static)

- **Source**: top-level `Dockerfile` + `nginx.conf` + `entrypoint.sh`
- **Image**: `nginx:alpine`
- **Public URL**: `vm2-p-taskers-production.up.railway.app`
- **Auth**: nginx basic-auth (username `vm2`, password from `VM2_AUTH_PASSWORD` env var) **OR** magic-link bypass (see below)
- **Routes**:
  - `/` → static files from the repo
  - `/go` and `/go.html` → share-link helper page (basic-auth required, magic-link bypass disabled)
  - `/api/todoist/*` → proxies to Todoist API (with server-side bearer token)
  - `/api/projects`, `/api/deliverables`, `/api/health` → proxies to Service B
- **Required env vars**:
  - `VM2_AUTH_USERNAME` (default: `vm2`)
  - `VM2_AUTH_PASSWORD` (default: `97harry23!`)
  - `VM2_TODOIST_TOKEN` (for Todoist deep-dive proxy)
- **Optional env vars**:
  - `VM2_PROJECTS_API_URL` — override the default `http://vm2-projects-api.railway.internal:8000`
  - `VM2_PUBLIC_KEYS` — comma-separated list of magic-link bypass keys (rotate manually). Empty/unset = bypass disabled (basic-auth required for everything). See `docs/SHARE-LINKS.md`.
- **Critical config**: `nginx.conf` MUST include a `resolver` directive
  with the container's actual nameserver from `/etc/resolv.conf`. Railway
  internal DNS uses IPv6 (e.g. `fd12::10`) which must be wrapped in
  `[brackets]`. `entrypoint.sh` injects this at boot via sed-replacing
  `__RESOLVER_PLACEHOLDER__` in `nginx.conf`. Public DNS like 1.1.1.1
  CANNOT resolve `*.railway.internal` hostnames.

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
- **Endpoints** (see `api/projects_api.py` for Pydantic models):
  - **GET** `/api/health` — liveness
  - **GET** `/api/projects` — list all projects with summary metadata
  - **GET** `/api/deliverables` — list all dated HTML files with project membership
  - **POST** `/api/projects/promote` — create a new project from a slug (pulls all matching files)
  - **POST** `/api/projects/create-empty` — create a project with no deliverables yet
  - **POST** `/api/projects/add-snapshot` — add a single deliverable to existing project
  - **POST** `/api/projects/add-many` — bulk-add multiple deliverables atomically
  - **POST** `/api/projects/move-snapshot` — reassign deliverable to different project (or detach)
  - **POST** `/api/projects/append` — append a timestamped update note to timeline
  - **POST** `/api/projects/merge` — fold one project into another, dedup, delete source
  - **POST** `/api/projects/rename` — rename a project slug, update back-references
  - **POST** `/api/projects/set-status` — change project status (active/watching/closed)
  - **POST** `/api/projects/set-summary` — manually replace Latest Summary text
  - **POST** `/api/projects/refresh-summary` — re-extract summary from latest snapshot
  - **POST** `/api/projects/set-metadata` — category, stage, tags, identifier, auto_summary
  - **POST** `/api/projects/add-open-item` — add open item with optional due_date
  - **POST** `/api/projects/toggle-open-item` — flip done state, stamp done_date
  - **POST** `/api/projects/add-key-date` — add a label+date entry to sidebar

### Magic-link auth bypass (added 2026-05-08)

A second authentication mode runs alongside basic-auth. When `VM2_PUBLIC_KEYS` is set, any of those keys passed as `?key=<value>` (or stored in the `vm2_key` cookie) lets the request through without a basic-auth challenge.

Implementation in `nginx.conf`:

1. **Two map directives**:
   - `map $arg_key $effective_key` — query param wins, falls back to cookie
   - `map $effective_key $key_valid` — `1` if key is in the active list, else `0`. The list is spliced in at boot by `entrypoint.sh` between `# __VM2_PUBLIC_KEYS_BEGIN__` / `# __VM2_PUBLIC_KEYS_END__` markers.
2. **`satisfy any` + `auth_request /__noop`** at the server level. nginx accepts the request if EITHER basic-auth succeeds OR the `/__noop` sub-request returns 200. The internal `/__noop` location returns 200 when `$key_valid = 1`, else 401.
3. **Cookie persistence** via a third map (`$arg_key → $vm2_set_cookie`) and an unconditional `add_header Set-Cookie $vm2_set_cookie always;`. We can't use `if ($arg_key) { add_header ... }` because nginx rejects `add_header` inside a server-level `if` block.
4. **`/go` is fail-closed**: explicitly uses `satisfy all` so the share-link helper page itself always requires basic-auth, regardless of magic-link state.

Known sharp edges (codified in nginx.conf comments):
- `auth_basic` directive does NOT support variable values like `$auth_realm`. The directive is parsed at config-load time, not per-request. That's why we use `satisfy any` instead.
- The `/__noop` location MUST set `auth_basic off;` and `auth_request off;` or nginx recurses into auth-checking its own auth-check sub-request.
- `add_header` inside a server-level `if` block is rejected with `"add_header" directive is not allowed here`. Use a map + unconditional `add_header` instead.

Key rotation is manual: edit `VM2_PUBLIC_KEYS` on Railway → vm2-portal → Variables. Container restarts automatically; old keys stop working as soon as the new deploy is live. See `docs/SHARE-LINKS.md` for the operator workflow.

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
├── ... rendered v3 page (header, KPIs, summary, beat chart, timeline, sidebar)
└── <!-- PROJECT_STATE_JSON_BEGIN
    {
      "slug": "army-maps",
      "title": "Army MAPS Recompete (W15P7T-26-R-A006)",
      "status": "active",                    // active | watching | closed
      "category": "bd",                       // bd | internal | personal | strategy | ""
      "stage": "Subcontractor track",          // free-text
      "identifier": "W15P7T-26-R-A006",        // optional ID (RFP#, etc.)
      "owner": "Varun",
      "created": "2026-05-05",
      "updated": "2026-05-06",
      "latest_summary": "...",                 // 3-paragraph synthesis
      "auto_summary": true,                    // false if user manually edited
      "tags": ["recompete", "sub", "army"],
      "key_dates": [
        {"label": "Industry Day", "date": "2026-04-22"},
        {"label": "Proposal due", "date": "2026-06-30"}
      ],
      "open_items": [
        {"text": "Confirm teaming partner", "done": false, "due_date": "2026-05-15"},
        {"text": "Industry Day registered", "done": true, "done_date": "2026-05-04"}
      ],
      "related": ["faa-clmrs", "eitss-2"],
      "timeline": [
        {"file": "...html", "date": "...", "title": "...", "kind": "snapshot", "body": ""},
        {"date": "...", "title": "...", "kind": "update", "body": "..."}
      ]
    }
    PROJECT_STATE_JSON_END -->
```

### Category color coding

| Category | Color | Use for |
|---|---|---|
| `bd` | `#c53a3a` (red) | Business development pursuits |
| `internal` | `#1f4d78` (navy) | Internal Changeis ops |
| `personal` | `#2d7d4a` (green) | Personal projects (golf, family) |
| `strategy` | `#6b4c9a` (purple) | Strategic/exploratory |
| `""` (none) | `#b9b6ad` (gray) | Uncategorized |

Applied as colored left border on cards/headers and as filter pill dots.

### Components

| File | Purpose |
|---|---|
| `scripts/project_helper.py` | CLI + render engine. Subcommands: `list`, `promote`, `add-snapshot`, `append`, `link`, `rename`, `set-status`, `set-summary`. Also provides `write_project()` used by API. Includes helpers for relative time, beat chart bucketing, grouped-timeline rendering, open-item badge logic. |
| `scripts/project_template.py` | v3 redesigned Charter-serif template: two-column layout, KPI dashboard, beat chart, grouped collapsible timeline, due-date-aware open items, compose dock, sticky sidebar with metadata + key dates + related + quick actions. |
| `scripts/promote_button.html` | Self-contained deliverable toolkit: 📌 Project link/picker + ✎ Revise dropdown (Quick note / Request rewrite tabs). |
| `api/projects_api.py` | FastAPI sidecar exposing 18 endpoints. Imports `project_helper` directly (no subprocess). |
| `projects.html` | v3 command center: sticky stats strip, category pills, status-grouped cards with KPI bands and 8-month sparklines, + New Project modal, attach-deliverables modal. |

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
| Railway env (`vm2-portal`) | `VM2_PUBLIC_KEYS` | nginx magic-link bypass (treat like passwords) |
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
2. **Use the helpers.** Never freeform-edit `portal.html` or `project-<slug>.html`. Use `portal_add_entry.py` and `project_helper.py` (or the API endpoints that wrap them).
3. **Lint before push.** `portal_lint.py` must exit 0 after any change touching `portal.html`.
4. **Slug naming.** Lowercase, hyphenated, alphanumeric only. Topic-first. No version numbers in slug.
5. **Filename convention.** `<slug>-YYYY-MM-DD.html` for snapshots. `project-<slug>.html` for projects.
6. **API has no auth of its own.** Always behind nginx basic-auth. Never expose `vm2-projects-api` directly.
7. **Concurrent commits.** API does `pull --rebase --autostash` before push; on conflict returns 409. Browser retries once.
8. **nginx resolver for Railway internal DNS.** Public DNS cannot resolve `*.railway.internal`. Use container's `/etc/resolv.conf` resolver, wrapped in `[brackets]` for IPv6.
9. **Cron task instructions must use the API or helper.** A cron freeform-editing `portal.html` was the root cause of multiple corruption incidents. The auto-cron `vm2-gmail-tasks` skill v3 documents the correct workflow.

---

## 9. File reference

```
VM2-P-Taskers/
├── Dockerfile                  ← Service A (nginx static)
├── nginx.conf                  ← Service A config (resolver, magic-link maps, basic-auth)
├── entrypoint.sh               ← Service A boot (resolver, htpasswd, magic-key splice)
├── go.html                     ← Share-link helper page (/go, basic-auth required)
├── portal.html                 ← Canonical index (table) with project decoration JS
├── projects.html               ← v3 project command center
├── project-<slug>.html         ← One per project (3 active)
├── <slug>-YYYY-MM-DD.html      ← 689+ dated deliverables
├── api/
│   ├── projects_api.py         ← FastAPI service (18 endpoints)
│   ├── Dockerfile              ← Service B image
│   ├── entrypoint.sh           ← Clones repo, configures git, exec uvicorn
│   ├── requirements.txt        ← Pinned deps (FastAPI, uvicorn, pydantic)
│   ├── railway.toml            ← Railway service config
│   └── README.md               ← API operator notes
├── scripts/
│   ├── portal_add_entry.py     ← Safe portal mutator (THE ONLY way to add rows)
│   ├── portal_lint.py          ← Integrity guard (5/6 cell counts, no stray <li>, etc.)
│   ├── project_helper.py       ← Project CLI + render engine
│   ├── project_template.py     ← v3 project HTML template
│   ├── promote_button.html     ← Deliverable toolkit (📌 Project + ✎ Revise)
│   ├── generate_share_key.sh   ← Magic-link key generator (k-YYMMDD-22charsBase62)
│   └── README.md               ← Helper guide
├── docs/
│   ├── ARCHITECTURE.md         ← This file
│   ├── DEPLOYMENT.md           ← 5-min Railway deployment checklist
│   ├── DR-RUNBOOK.md           ← Disaster recovery (P0–P3)
│   ├── SHARE-LINKS.md          ← Magic-link bypass operator guide
│   └── README.md               ← Doc index
├── _system/
│   ├── deep-dive-button.js     ← Existing daily-brief button (legacy)
│   ├── deep-dive-spec.md       ← Spec for that button
│   └── ...
├── vm2-tests.sh                ← End-to-end tests
└── .gitignore
```

## 10. Recent change history

| Date | What |
|---|---|
| 2026-03-25 | Migrated from GitHub Pages + StaticCrypt to Railway + nginx basic-auth |
| 2026-04-30 | portal.html corruption fix; lint guard added |
| 2026-05-05 | Project Threads MVP (helper, template, button, projects.html) |
| 2026-05-05 | Architecture + DR docs created |
| 2026-05-05 | Deployed Projects API service B on Railway |
| 2026-05-05 | Fixed nginx IPv6 resolver for Railway internal DNS |
| 2026-05-05 | Cross-page integration: portal Project column, projects.html +New Project, deliverable toolkit with Revise button, move-snapshot/create-empty/merge endpoints, auto-summary-on-add |
| 2026-05-06 | v3 redesign shipped: stats strip, color categories, KPI dashboard, beat chart, month-grouped timeline, sidebar, due-date-aware open items, 6 new API endpoints (set-summary, refresh-summary, set-metadata, add-open-item, toggle-open-item, add-key-date) |
| 2026-05-08 | Magic-link auth bypass shipped: `VM2_PUBLIC_KEYS` env var, `satisfy any` + `auth_request /__noop` pattern, `/go` share-link helper page, `generate_share_key.sh`, `SHARE-LINKS.md` operator guide |
