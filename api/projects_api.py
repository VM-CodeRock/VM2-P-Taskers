"""
VM2 Projects API — sidecar for the Promote-to-Project button.

Runs alongside the nginx static-file server on Railway. nginx proxies
/api/* to this FastAPI app. Same basic-auth credentials gate the API
(handled by nginx, so this app can stay simple).

Endpoints:
  GET  /api/health                   — Liveness probe
  GET  /api/projects                 — List all projects (for the picker)
  POST /api/projects/promote         — Create a new project + add this deliverable
  POST /api/projects/add-snapshot    — Add this deliverable to existing project
  POST /api/projects/append          — Append an update note
  POST /api/projects/rename          — Rename a project slug
  POST /api/projects/set-status      — Change project status

The button workflow:
  1. User clicks "Promote to Project" on any deliverable
  2. Dropdown calls GET /api/projects to populate the picker
  3. User picks existing OR types a new slug
  4. On submit: POST to /api/projects/promote (new) or /add-snapshot (existing)
  5. API runs project_helper.py, commits, pushes to GitHub
  6. Browser shows toast with the new project URL

Deploy:
  uvicorn api.projects_api:app --host 0.0.0.0 --port 8000

Env vars:
  REPO_PATH        — Absolute path to the VM2-P-Taskers checkout (default: /repo)
  GITHUB_TOKEN     — PAT for git push (read from Railway env, never logged)
  GIT_USER_EMAIL   — Commit author email
  GIT_USER_NAME    — Commit author name
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Literal, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

REPO = Path(os.environ.get("REPO_PATH", "/repo"))
SCRIPTS = REPO / "scripts"
sys.path.insert(0, str(SCRIPTS))

# Import helper functions directly (faster + better error handling than subprocess)
try:
    from project_helper import (  # type: ignore
        list_projects, load_state, write_project, discover_snapshots,
        SLUG_RE, today_iso,
    )
except Exception as e:  # pragma: no cover
    print(f"WARN: project_helper not importable yet: {e}", file=sys.stderr)
    list_projects = load_state = write_project = discover_snapshots = None  # type: ignore
    SLUG_RE = today_iso = None  # type: ignore


app = FastAPI(title="VM2 Projects API", version="0.1")

# Allow the portal pages (served by nginx on the same host) to call us
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


# ─── git helpers ────────────────────────────────────────────────────────

def git(*args: str) -> str:
    env = os.environ.copy()
    env["GIT_AUTHOR_EMAIL"] = env["GIT_COMMITTER_EMAIL"] = os.environ.get(
        "GIT_USER_EMAIL", "vm2@changeis.com"
    )
    env["GIT_AUTHOR_NAME"] = env["GIT_COMMITTER_NAME"] = os.environ.get(
        "GIT_USER_NAME", "VM2 Projects API"
    )
    r = subprocess.run(
        ["git", "-C", str(REPO), *args],
        capture_output=True, text=True, env=env,
    )
    if r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {r.stderr.strip()}")
    return r.stdout.strip()


def git_commit_and_push(message: str, files: list[str]) -> str:
    """Add specific files, commit, push. Returns the new HEAD SHA."""
    git("add", *files)
    # Skip if nothing changed
    diff = subprocess.run(
        ["git", "-C", str(REPO), "diff", "--cached", "--quiet"],
        capture_output=True,
    )
    if diff.returncode == 0:
        return "no-op"
    git("commit", "-m", message)
    # Pull-rebase to handle concurrent cron pushes
    try:
        git("pull", "--rebase", "--autostash")
    except RuntimeError:
        # Conflict — abort cleanly so the caller sees a useful error
        try: git("rebase", "--abort")
        except Exception: pass
        raise HTTPException(409, "Concurrent push conflicted; retry the action.")
    git("push")
    return git("rev-parse", "HEAD")


# ─── models ─────────────────────────────────────────────────────────────

class ProjectSummary(BaseModel):
    slug: str
    title: str
    status: str
    deliverable_count: int
    updated: str


class PromoteRequest(BaseModel):
    slug: str = Field(pattern=r"^[a-z0-9][a-z0-9-]*[a-z0-9]$", min_length=2, max_length=64)
    title: Optional[str] = None
    status: Literal["active", "watching", "closed"] = "active"
    owner: str = "Varun"
    deliverable_file: Optional[str] = None  # If provided, ensure this file is in timeline
    summary: Optional[str] = None


class AddSnapshotRequest(BaseModel):
    slug: str
    deliverable_file: str
    title: Optional[str] = None
    body: Optional[str] = None
    summary: Optional[str] = None


class AppendRequest(BaseModel):
    slug: str
    note: str = Field(min_length=1, max_length=2000)


class RenameRequest(BaseModel):
    old_slug: str
    new_slug: str = Field(pattern=r"^[a-z0-9][a-z0-9-]*[a-z0-9]$")


class StatusRequest(BaseModel):
    slug: str
    status: Literal["active", "watching", "closed"]


class APIResponse(BaseModel):
    ok: bool
    project_url: Optional[str] = None
    commit: Optional[str] = None
    message: str = ""


# ─── endpoints ──────────────────────────────────────────────────────────

@app.get("/api/health")
def health():
    return {"ok": True, "repo": str(REPO), "repo_exists": REPO.exists()}


@app.get("/api/projects", response_model=list[ProjectSummary])
def get_projects():
    if list_projects is None:
        raise HTTPException(500, "project_helper not loaded")
    return list_projects()


@app.post("/api/projects/promote", response_model=APIResponse)
def promote(req: PromoteRequest):
    if load_state(req.slug):
        raise HTTPException(409, f"Project '{req.slug}' already exists. Use add-snapshot.")

    snapshots = discover_snapshots(req.slug)
    # If a deliverable_file was named and not picked up by slug-prefix, add it explicitly
    if req.deliverable_file and not any(s["file"] == req.deliverable_file for s in snapshots):
        f = REPO / req.deliverable_file
        if f.exists():
            import re
            m = re.search(r"(\d{4}-\d{2}-\d{2})", req.deliverable_file)
            date = m.group(1) if m else today_iso()
            snapshots.append({
                "file": req.deliverable_file,
                "date": date,
                "title": req.deliverable_file.replace(".html", "").replace("-", " ").title(),
                "kind": "snapshot",
                "body": "",
            })

    state = {
        "slug": req.slug,
        "title": req.title or req.slug.replace("-", " ").title(),
        "status": req.status,
        "owner": req.owner,
        "created": today_iso(),
        "updated": today_iso(),
        "latest_summary": req.summary or "",
        "open_items": [],
        "related": [],
        "timeline": snapshots,
    }
    p = write_project(state)
    commit = git_commit_and_push(
        f"Promote project: {req.slug}",
        [p.name],
    )
    return APIResponse(
        ok=True,
        project_url=f"/{p.name}",
        commit=commit,
        message=f"Created project-{req.slug}.html with {len(snapshots)} snapshot(s).",
    )


@app.post("/api/projects/add-snapshot", response_model=APIResponse)
def add_snapshot(req: AddSnapshotRequest):
    state = load_state(req.slug)
    if not state:
        raise HTTPException(404, f"Project '{req.slug}' not found.")
    f = REPO / req.deliverable_file
    if not f.exists():
        raise HTTPException(404, f"Deliverable '{req.deliverable_file}' not found.")
    if any(e.get("file") == req.deliverable_file for e in state.get("timeline", [])):
        return APIResponse(ok=True, project_url=f"/project-{req.slug}.html",
                           message="Already in timeline (no-op).")

    import re
    m = re.search(r"(\d{4}-\d{2}-\d{2})", req.deliverable_file)
    date = m.group(1) if m else today_iso()
    title = req.title or req.deliverable_file.replace(".html", "").replace("-", " ").title()

    state.setdefault("timeline", []).append({
        "file": req.deliverable_file,
        "date": date,
        "title": title,
        "kind": "snapshot",
        "body": req.body or "",
    })
    if req.summary:
        state["latest_summary"] = req.summary
    p = write_project(state)
    commit = git_commit_and_push(
        f"Add {req.deliverable_file} to project {req.slug}",
        [p.name],
    )
    return APIResponse(ok=True, project_url=f"/{p.name}", commit=commit,
                       message=f"Added to {req.slug}.")


@app.post("/api/projects/append", response_model=APIResponse)
def append(req: AppendRequest):
    state = load_state(req.slug)
    if not state:
        raise HTTPException(404, f"Project '{req.slug}' not found.")
    state.setdefault("timeline", []).append({
        "date": today_iso(),
        "title": req.note[:80] + ("…" if len(req.note) > 80 else ""),
        "kind": "update",
        "body": req.note,
    })
    p = write_project(state)
    commit = git_commit_and_push(
        f"Update note: {req.slug}",
        [p.name],
    )
    return APIResponse(ok=True, project_url=f"/{p.name}", commit=commit,
                       message="Update note appended.")


@app.post("/api/projects/rename", response_model=APIResponse)
def rename(req: RenameRequest):
    state = load_state(req.old_slug)
    if not state:
        raise HTTPException(404, f"Project '{req.old_slug}' not found.")
    if load_state(req.new_slug):
        raise HTTPException(409, f"Project '{req.new_slug}' already exists.")
    state["slug"] = req.new_slug
    new_path = write_project(state)
    old_path = REPO / f"project-{req.old_slug}.html"
    if old_path.exists():
        old_path.unlink()
    # Update related back-references in other projects
    touched = [new_path.name, old_path.name]
    for other in list_projects():
        if other["slug"] == req.new_slug:
            continue
        s = load_state(other["slug"])
        if s and req.old_slug in s.get("related", []):
            s["related"] = [req.new_slug if r == req.old_slug else r for r in s["related"]]
            write_project(s)
            touched.append(f"project-{other['slug']}.html")

    # Stage deletion of old file
    git("add", "-A", str(old_path.name))
    commit = git_commit_and_push(
        f"Rename project: {req.old_slug} → {req.new_slug}",
        list(set(touched)),
    )
    return APIResponse(ok=True, project_url=f"/{new_path.name}", commit=commit,
                       message=f"Renamed {req.old_slug} → {req.new_slug}.")


@app.post("/api/projects/set-status", response_model=APIResponse)
def set_status(req: StatusRequest):
    state = load_state(req.slug)
    if not state:
        raise HTTPException(404, f"Project '{req.slug}' not found.")
    state["status"] = req.status
    p = write_project(state)
    commit = git_commit_and_push(
        f"Set {req.slug} status: {req.status}",
        [p.name],
    )
    return APIResponse(ok=True, project_url=f"/{p.name}", commit=commit,
                       message=f"Status set to {req.status}.")
