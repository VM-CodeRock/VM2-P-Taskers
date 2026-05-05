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


class MoveSnapshotRequest(BaseModel):
    deliverable_file: str
    to_slug: Optional[str] = None  # None means "detach from any project"
    from_slug: Optional[str] = None  # If known; otherwise auto-detect


class CreateEmptyRequest(BaseModel):
    slug: str = Field(pattern=r"^[a-z0-9][a-z0-9-]*[a-z0-9]$", min_length=2, max_length=64)
    title: Optional[str] = None
    status: Literal["active", "watching", "closed"] = "active"
    owner: str = "Varun"
    summary: Optional[str] = None


class MergeRequest(BaseModel):
    from_slug: str  # Project to merge IN (will be deleted)
    into_slug: str  # Project to merge INTO (kept)


class DeliverableInfo(BaseModel):
    file: str
    date: str
    title_guess: str
    project_slug: Optional[str] = None  # Which project owns this, if any
    project_title: Optional[str] = None


class AddManyRequest(BaseModel):
    slug: str
    files: list[str] = Field(min_length=1, max_length=100)


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


@app.get("/api/deliverables", response_model=list[DeliverableInfo])
def get_deliverables():
    """List every dated deliverable HTML file in the repo with current project membership.

    Used by the 'Add previous analysis' picker on projects.html so you can
    browse the full archive, multi-select, and bulk-add to a project.
    """
    import re
    DATE_RE = re.compile(r"-(\d{4}-\d{2}-\d{2})\.html$")
    # Build a {filename: (slug, title)} map of current project membership
    membership: dict[str, tuple[str, str]] = {}
    for proj in list_projects():
        state = load_state(proj["slug"])
        if not state:
            continue
        for entry in state.get("timeline", []):
            f = entry.get("file")
            if f:
                membership[f] = (proj["slug"], proj["title"])

    out: list[DeliverableInfo] = []
    for f in sorted(REPO.glob("*.html"), reverse=True):
        name = f.name
        # Skip portal, project pages, redirects, kanban
        if name in ("index.html", "portal.html", "projects.html", "kanban.html"):
            continue
        if name.startswith("project-"):
            continue
        m = DATE_RE.search(name)
        if not m:
            continue
        date = m.group(1)
        # Friendly title from filename
        stem = name[:-5]  # strip .html
        stem = stem[: -len(date) - 1]  # strip -YYYY-MM-DD
        title_guess = stem.replace("-", " ").title()
        slug = membership.get(name, (None, None))[0]
        title = membership.get(name, (None, None))[1]
        out.append(DeliverableInfo(
            file=name, date=date, title_guess=title_guess,
            project_slug=slug, project_title=title,
        ))
    return out


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


def _extract_summary_from_html(file_path) -> str:
    """Best-effort extract first heading + first 2 paragraphs from a deliverable."""
    try:
        text = file_path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return ""
    import re
    # Strip script/style blocks
    text = re.sub(r"<script[\s\S]*?</script>", "", text, flags=re.IGNORECASE)
    text = re.sub(r"<style[\s\S]*?</style>", "", text, flags=re.IGNORECASE)
    # Find first <h1>/<h2>
    h_match = re.search(r"<h[12][^>]*>([\s\S]*?)</h[12]>", text, re.IGNORECASE)
    heading = re.sub(r"<[^>]+>", "", h_match.group(1)).strip() if h_match else ""
    # First 2 paragraphs after the heading
    body_text = text[h_match.end():] if h_match else text
    paras = re.findall(r"<p[^>]*>([\s\S]*?)</p>", body_text, re.IGNORECASE)
    cleaned = []
    for p in paras[:3]:
        plain = re.sub(r"<[^>]+>", " ", p)
        plain = re.sub(r"\s+", " ", plain).strip()
        if len(plain) > 20:
            cleaned.append(plain)
        if len(cleaned) >= 2:
            break
    out = ""
    if heading:
        out = heading + (". " if not heading.endswith(".") else " ")
    out += "\n\n".join(cleaned)
    return out[:1200].strip()


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
    # Auto-extract summary unless user explicitly disabled it (auto_summary=false)
    # or unless they passed an explicit summary.
    if req.summary:
        state["latest_summary"] = req.summary
    elif state.get("auto_summary", True):
        extracted = _extract_summary_from_html(f)
        if extracted:
            state["latest_summary"] = extracted
    p = write_project(state)
    commit = git_commit_and_push(
        f"Add {req.deliverable_file} to project {req.slug}",
        [p.name],
    )
    return APIResponse(ok=True, project_url=f"/{p.name}", commit=commit,
                       message=f"Added to {req.slug}.")


@app.post("/api/projects/add-many", response_model=APIResponse)
def add_many(req: AddManyRequest):
    """Bulk-add multiple deliverables to a single project.

    Used by the 'Add previous analysis' picker. One commit, one push, atomic.
    Skips files already in the project's timeline.
    """
    state = load_state(req.slug)
    if not state:
        raise HTTPException(404, f"Project '{req.slug}' not found.")
    import re
    existing = {e.get("file") for e in state.get("timeline", [])}
    added = []
    for fname in req.files:
        if fname in existing:
            continue
        f = REPO / fname
        if not f.exists():
            continue
        m = re.search(r"(\d{4}-\d{2}-\d{2})", fname)
        date = m.group(1) if m else today_iso()
        title = fname.replace(".html", "").replace("-", " ").title()
        state.setdefault("timeline", []).append({
            "file": fname, "date": date, "title": title,
            "kind": "snapshot", "body": "",
        })
        added.append(fname)
    if not added:
        return APIResponse(ok=True, project_url=f"/project-{req.slug}.html",
                           message="All files were already in the timeline (no-op).")
    p = write_project(state)
    commit = git_commit_and_push(
        f"Add {len(added)} deliverable(s) to {req.slug}",
        [p.name],
    )
    return APIResponse(
        ok=True, project_url=f"/{p.name}", commit=commit,
        message=f"Added {len(added)} file(s) to {req.slug}.",
    )


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


@app.post("/api/projects/move-snapshot", response_model=APIResponse)
def move_snapshot(req: MoveSnapshotRequest):
    """Re-assign a deliverable from one project to another (or detach)."""
    f = REPO / req.deliverable_file
    if not f.exists():
        raise HTTPException(404, f"Deliverable '{req.deliverable_file}' not found.")

    # Find which project currently owns it
    from_slug = req.from_slug
    if not from_slug:
        for proj in list_projects():
            s = load_state(proj["slug"])
            if s and any(e.get("file") == req.deliverable_file for e in s.get("timeline", [])):
                from_slug = proj["slug"]
                break

    touched_files = []

    # Remove from old project
    if from_slug:
        old_state = load_state(from_slug)
        if old_state:
            old_state["timeline"] = [e for e in old_state.get("timeline", [])
                                      if e.get("file") != req.deliverable_file]
            old_path = write_project(old_state)
            touched_files.append(old_path.name)

    # Add to new project (if specified)
    if req.to_slug:
        new_state = load_state(req.to_slug)
        if not new_state:
            raise HTTPException(404, f"Target project '{req.to_slug}' not found.")
        if not any(e.get("file") == req.deliverable_file for e in new_state.get("timeline", [])):
            import re
            m = re.search(r"(\d{4}-\d{2}-\d{2})", req.deliverable_file)
            date = m.group(1) if m else today_iso()
            title = req.deliverable_file.replace(".html", "").replace("-", " ").title()
            new_state.setdefault("timeline", []).append({
                "file": req.deliverable_file, "date": date, "title": title,
                "kind": "snapshot", "body": "",
            })
            if new_state.get("auto_summary", True):
                extracted = _extract_summary_from_html(f)
                if extracted:
                    new_state["latest_summary"] = extracted
            new_path = write_project(new_state)
            touched_files.append(new_path.name)

    if not touched_files:
        return APIResponse(ok=True, message="No-op.")

    msg = f"Move {req.deliverable_file}"
    if from_slug:
        msg += f" from {from_slug}"
    if req.to_slug:
        msg += f" to {req.to_slug}"
    commit = git_commit_and_push(msg, list(set(touched_files)))

    target_url = f"/project-{req.to_slug}.html" if req.to_slug else None
    return APIResponse(ok=True, project_url=target_url, commit=commit, message=msg)


@app.post("/api/projects/create-empty", response_model=APIResponse)
def create_empty(req: CreateEmptyRequest):
    """Create a project with no deliverables yet (used by + New Project on projects.html)."""
    if load_state(req.slug):
        raise HTTPException(409, f"Project '{req.slug}' already exists.")
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
        "timeline": [],
        "auto_summary": True,
    }
    p = write_project(state)
    commit = git_commit_and_push(f"Create empty project: {req.slug}", [p.name])
    return APIResponse(ok=True, project_url=f"/{p.name}", commit=commit,
                       message=f"Created empty project '{req.slug}'.")


@app.post("/api/projects/merge", response_model=APIResponse)
def merge(req: MergeRequest):
    """Merge from_slug into into_slug. from_slug is deleted; its timeline + open
    items are folded into into_slug. Updates back-references in other projects.
    """
    src = load_state(req.from_slug)
    dst = load_state(req.into_slug)
    if not src:
        raise HTTPException(404, f"Source project '{req.from_slug}' not found.")
    if not dst:
        raise HTTPException(404, f"Target project '{req.into_slug}' not found.")
    if req.from_slug == req.into_slug:
        raise HTTPException(400, "Cannot merge a project into itself.")

    # Merge timeline (dedup by file or by date+title for update notes)
    seen_files = {e.get("file") for e in dst.get("timeline", []) if e.get("file")}
    seen_notes = {(e.get("date"), e.get("title")) for e in dst.get("timeline", []) if e.get("kind") == "update"}
    for entry in src.get("timeline", []):
        if entry.get("kind") == "snapshot":
            if entry.get("file") in seen_files:
                continue
            seen_files.add(entry.get("file"))
        else:
            key = (entry.get("date"), entry.get("title"))
            if key in seen_notes:
                continue
            seen_notes.add(key)
        dst.setdefault("timeline", []).append(entry)

    # Merge open items by text
    seen_text = {i.get("text") for i in dst.get("open_items", [])}
    for item in src.get("open_items", []):
        if item.get("text") not in seen_text:
            dst.setdefault("open_items", []).append(item)
            seen_text.add(item.get("text"))

    # Merge related (and remove self-refs)
    related = list(dict.fromkeys(dst.get("related", []) + src.get("related", [])))
    related = [r for r in related if r != req.from_slug and r != req.into_slug]
    dst["related"] = related

    # Add a merge note to the dst timeline
    dst.setdefault("timeline", []).append({
        "date": today_iso(),
        "title": f"Merged {req.from_slug} into this project",
        "kind": "update",
        "body": f"Project '{req.from_slug}' was merged into '{req.into_slug}'. "
                f"Timeline entries and open items were combined.",
    })

    dst_path = write_project(dst)
    src_path = REPO / f"project-{req.from_slug}.html"
    if src_path.exists():
        src_path.unlink()

    # Update back-references in other projects
    touched = [dst_path.name, src_path.name]
    for proj in list_projects():
        if proj["slug"] in (req.from_slug, req.into_slug):
            continue
        s = load_state(proj["slug"])
        if s and req.from_slug in s.get("related", []):
            s["related"] = [req.into_slug if r == req.from_slug else r for r in s["related"]]
            other_path = write_project(s)
            touched.append(other_path.name)

    git("add", "-A", str(src_path.name))
    commit = git_commit_and_push(
        f"Merge project {req.from_slug} into {req.into_slug}",
        list(set(touched)),
    )
    return APIResponse(ok=True, project_url=f"/{dst_path.name}", commit=commit,
                       message=f"Merged {req.from_slug} → {req.into_slug}.")


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
