# VM2-P-Taskers — Deployment Quickstart

5-minute checklist to bring the Projects API live alongside the existing nginx portal.

> **Prerequisite**: You already have the `vm2-portal` Railway service running. This guide adds Service B (`vm2-projects-api`) and wires the proxy.

---

## Step 1 — Create the API service on Railway (3 min)

1. Open your existing Railway project (the one with `vm2-portal`)
2. Click **+ New** → **GitHub Repo** → select `vm-coderock/VM2-P-Taskers`
3. After it imports, go to **Settings** of the new service:
   - **Service Name**: `vm2-projects-api` (this is critical — nginx.conf references this exact name)
   - **Build → Custom Build Command**: leave blank
   - **Build → Dockerfile Path**: `api/Dockerfile`
   - **Build → Watch Paths**: `api/**` (so it only rebuilds when API code changes)
   - **Networking**: do NOT generate a public domain. The service is internal-only.

## Step 2 — Set environment variables on `vm2-projects-api` (1 min)

Variables panel → Raw Editor → paste:

```
GITHUB_TOKEN=<your PAT with repo scope — generate at https://github.com/settings/tokens>
GIT_USER_EMAIL=vm2@changeis.com
GIT_USER_NAME=VM2 Projects API
```

The PAT needs **only the `repo` scope**. Use a fine-grained PAT with access scoped to `vm-coderock/VM2-P-Taskers` for least privilege.

## Step 3 — Wait for deploy (1 min)

Railway will build the Docker image and start the container. Watch the Logs tab:

```
[entrypoint] Cloning https://github.com/vm-coderock/VM2-P-Taskers.git → /repo
[entrypoint] Starting API on port 8000
INFO: Started server process [1]
INFO: Application startup complete.
INFO: Uvicorn running on http://0.0.0.0:8000
```

If you see `Healthcheck succeeded` — you're done with Step 3.

## Step 4 — Verify the proxy works through nginx (30 sec)

Browser, basic-auth as `vm2`:

```
https://vm2-p-taskers-production.up.railway.app/api/health
```

Expected JSON:
```json
{"ok": true, "repo": "/repo", "repo_exists": true}
```

If this works, the projects.html command center is now fully interactive:

```
https://vm2-p-taskers-production.up.railway.app/projects.html
```

## Step 5 — End-to-end smoke test (30 sec)

1. Open any patched Army MAPS deliverable, e.g. [`army-maps-bid-decision-2026-04-14.html`](https://vm2-p-taskers-production.up.railway.app/army-maps-bid-decision-2026-04-14.html)
2. Top-right shows **📌 Army MAPS Recompete** badge (already linked)
3. Open a different deliverable that's not in any project
4. Click **📌 Promote to Project ▾** → dropdown shows the 3 existing projects
5. Either pick one or type a new slug → click Promote
6. Confirmation toast → page reloads with the new badge

---

## Troubleshooting

### `502 Bad Gateway` on `/api/*`
- nginx can't reach the API service. Check Service Name on Railway is exactly `vm2-projects-api`.
- Or override in nginx via env var: `VM2_PROJECTS_API_URL=http://<actual-internal-host>:8000` on the `vm2-portal` service.

### `git push` fails from API logs
- `GITHUB_TOKEN` missing or wrong scope. Regenerate with `repo` scope.
- Token expired. Use a fine-grained PAT with no expiration if possible.

### API container restart loop
- Check logs for `git clone` failure → repo URL or token wrong
- Check logs for Python import errors → `scripts/project_helper.py` may have a syntax issue; fix and push

### `409 conflict` toast on Promote button
- A cron pushed concurrently. Click again; the API does pull-rebase before push.

### projects.html shows "Could not load projects"
- API service is down or not deployed. See the `/api/health` check above.

---

## Rollback

If anything breaks, the system fails-safe:
- Disable the `vm2-projects-api` service → projects.html cards stop loading, but everything else works
- Remove the `/api/projects` and `/api/deliverables` blocks from `nginx.conf` and push → portal goes back to pre-MVP state
- The Promote button degrades gracefully (it shows but clicks fail with a toast)

No data is destroyed. Project state lives in committed `project-<slug>.html` files.
