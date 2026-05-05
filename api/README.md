# VM2 Projects API

Sidecar FastAPI service that powers the **Promote to Project** button on every deliverable. Deployed alongside the existing nginx static-file server on Railway.

## Architecture

```
Browser
   │
   │ click "Promote to Project ▾"
   ▼
nginx (Railway)
   │
   ├── / → static files (portal.html, deliverables, project-*.html)
   └── /api/* → projects_api.py (this service)
                    │
                    ▼
                  /repo (cloned at boot)
                    │
                    ├── scripts/project_helper.py  (imported)
                    ├── project-<slug>.html        (read/written)
                    └── .git                        (commit + push)
```

The API imports `project_helper.py` directly (no subprocess overhead), mutates the repo, and pushes changes back to GitHub. nginx serves the updated static files within ~5 seconds (Railway redeploys on push).

## Endpoints

| Method | Path | Body | Description |
|---|---|---|---|
| GET | `/api/health` | — | Liveness probe |
| GET | `/api/projects` | — | List all projects (for the picker dropdown) |
| POST | `/api/projects/promote` | `PromoteRequest` | Create a new project |
| POST | `/api/projects/add-snapshot` | `AddSnapshotRequest` | Add deliverable to existing project |
| POST | `/api/projects/append` | `AppendRequest` | Append an update note |
| POST | `/api/projects/rename` | `RenameRequest` | Rename a project slug |
| POST | `/api/projects/set-status` | `StatusRequest` | Change status |

See `projects_api.py` for full Pydantic models.

## Local dev

```bash
cd VM2-P-Taskers
REPO_PATH=$(pwd) PYTHONPATH=$(pwd)/scripts \
  uvicorn api.projects_api:app --reload --port 8000

# Test
curl http://localhost:8000/api/health
curl http://localhost:8000/api/projects
```

## Railway deployment

1. **New Railway service** in the same project as nginx
2. Source: this repo, Dockerfile path = `api/Dockerfile`
3. Environment variables:
   - `GITHUB_TOKEN` — Personal Access Token with `repo` scope
   - `GIT_USER_EMAIL=vm2@changeis.com`
   - `GIT_USER_NAME=VM2 Projects API`
4. **Update nginx.conf** to proxy `/api/*` → this service:
   ```nginx
   location /api/ {
       proxy_pass http://projects-api.railway.internal:8000;
       proxy_set_header Host $host;
       proxy_set_header X-Real-IP $remote_addr;
   }
   ```
   Basic auth on the nginx side already protects it; no extra auth needed in the API.
5. Deploy. Confirm with: `curl -u vm2:<password> https://<railway-url>/api/health`

## Concurrency

Multiple cron jobs and the API can all push to the repo. The API does `git pull --rebase --autostash` before push and returns 409 on conflict. Browser side should retry once on 409.

## Security note

The API has no auth of its own — it relies on nginx basic-auth being mandatory in front of it. **Never expose this service directly to the public internet** without auth.
