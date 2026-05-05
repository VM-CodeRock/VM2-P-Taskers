#!/usr/bin/env python3
"""
project_helper.py — Manage long-lived project pages in VM2-P-Taskers.

Subcommands:
  list                                    — List all existing projects
  promote --slug X --title "..."          — Create project, pull all matching snapshots
  add-snapshot --slug X --file F          — Add a deliverable to existing project's timeline
  append --slug X --note "..."            — Append a timestamped update note (no new file)
  link --a X --b Y                        — Bidirectionally link two projects
  rename --old X --new Y                  — Rename slug, update all back-references

Each project lives at project-<slug>.html. State stored as JSON inside an
HTML comment block (so the file is self-contained, no separate DB).

Usage from cron task or FastAPI sidecar:
    python3 scripts/project_helper.py promote --slug army-maps \\
        --title "Army MAPS Recompete (W15P7T-26-R-A006)" --status active
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

# Allow running from repo root or scripts/
HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(HERE))

from project_template import PROJECT_HTML_TEMPLATE  # noqa: E402

STATE_BEGIN = "<!-- PROJECT_STATE_JSON_BEGIN"
STATE_END = "PROJECT_STATE_JSON_END -->"
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]*[a-z0-9]$")


def html_escape(s: str) -> str:
    return (s.replace("&", "&amp;")
             .replace("<", "&lt;").replace(">", "&gt;")
             .replace('"', "&quot;"))


def today_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def project_path(slug: str) -> Path:
    return REPO / f"project-{slug}.html"


def load_state(slug: str) -> dict | None:
    """Load state JSON from project-<slug>.html. Returns None if not found."""
    p = project_path(slug)
    if not p.exists():
        return None
    text = p.read_text(encoding="utf-8")
    if STATE_BEGIN not in text or STATE_END not in text:
        return None
    body = text.split(STATE_BEGIN, 1)[1].split(STATE_END, 1)[0]
    return json.loads(body.strip())


def write_project(state: dict) -> Path:
    """Render state → project-<slug>.html. Returns file path."""
    slug = state["slug"]
    p = project_path(slug)

    status = state.get("status", "active")
    status_label = status.upper()
    status_class = status

    # Latest summary
    summary = state.get("latest_summary", "").strip()
    if summary:
        # Convert blank-line-separated paragraphs to <p>
        paras = [f"      <p>{html_escape(s.strip())}</p>" for s in summary.split("\n\n") if s.strip()]
        latest_summary_html = "\n".join(paras)
    else:
        latest_summary_html = '      <p class="empty">No summary yet. Add one with: project_helper.py refresh-summary</p>'

    # Open items
    items = state.get("open_items", [])
    if items:
        lines = []
        for item in items:
            text = html_escape(item.get("text", ""))
            done = "done" if item.get("done") else ""
            lines.append(f'      <li class="{done}"><span class="check"></span><span class="text">{text}</span></li>')
        open_items_html = '    <ul class="open-items">\n' + "\n".join(lines) + "\n    </ul>"
    else:
        open_items_html = '    <p class="empty">No open items.</p>'

    # Related projects
    related = state.get("related", [])
    if related:
        rel_lines = []
        for r_slug in related:
            r_state = load_state(r_slug)
            r_label = r_state["title"] if r_state else r_slug
            rel_lines.append(f'      <a href="project-{r_slug}.html">{html_escape(r_label)}</a>')
        related_html = "\n".join(rel_lines)
    else:
        related_html = '      <span class="none">No related projects yet.</span>'

    # Timeline (reverse chronological)
    timeline = sorted(state.get("timeline", []), key=lambda e: e.get("date", ""), reverse=True)
    if timeline:
        tl_lines = []
        for entry in timeline:
            date = html_escape(entry.get("date", ""))
            kind = entry.get("kind", "snapshot")  # snapshot | update
            kind_class = "update" if kind == "update" else ""
            kind_label = "Update" if kind == "update" else "Snapshot"
            title = html_escape(entry.get("title", ""))
            file_ = entry.get("file")
            body = html_escape(entry.get("body", ""))
            if file_:
                title_html = f'<a href="{html_escape(file_)}">{title}</a>'
            else:
                title_html = title
            tl_lines.append(
                f'      <li class="timeline-entry {kind_class}">\n'
                f'        <div class="timeline-date">{date}<span class="timeline-kind {kind_class}">{kind_label}</span></div>\n'
                f'        <div class="timeline-title">{title_html}</div>\n'
                f'        <div class="timeline-body">{body}</div>\n'
                f'      </li>'
            )
        timeline_html = "\n".join(tl_lines)
    else:
        timeline_html = '      <li class="empty">No entries yet.</li>'

    deliverable_count = sum(1 for e in timeline if e.get("kind", "snapshot") == "snapshot")

    rendered = PROJECT_HTML_TEMPLATE.format(
        slug=html_escape(slug),
        title=html_escape(state.get("title", slug)),
        status_label=status_label,
        status_class=status_class,
        owner=html_escape(state.get("owner", "Varun")),
        created=html_escape(state.get("created", today_iso())),
        updated=today_iso(),
        deliverable_count=deliverable_count,
        deliverable_plural="" if deliverable_count == 1 else "s",
        latest_summary_html=latest_summary_html,
        open_items_html=open_items_html,
        related_html=related_html,
        timeline_html=timeline_html,
    )

    # Append state JSON in HTML comment for round-tripping
    state["updated"] = today_iso()
    state_block = f"\n{STATE_BEGIN}\n{json.dumps(state, indent=2)}\n{STATE_END}\n"
    rendered = rendered.rstrip() + state_block

    p.write_text(rendered, encoding="utf-8")
    return p


def discover_snapshots(slug: str) -> list[dict]:
    """Find all <slug>-YYYY-MM-DD.html files (slug prefix match), exclude project page itself."""
    pattern = re.compile(rf"^{re.escape(slug)}-(.+)?(\d{{4}}-\d{{2}}-\d{{2}})\.html$")
    snapshots = []
    for f in REPO.glob(f"{slug}*.html"):
        if f.name.startswith("project-"):
            continue
        m = pattern.match(f.name)
        if m:
            date = m.group(2)
            # Friendly title from filename
            stem = f.stem
            # Strip date and slug prefix
            title_part = stem[len(slug):].rstrip("-")
            title_part = re.sub(rf"-?{date}$", "", title_part).strip("-")
            title = title_part.replace("-", " ").title() if title_part else slug.replace("-", " ").title()
            snapshots.append({
                "file": f.name,
                "date": date,
                "title": title,
                "kind": "snapshot",
                "body": "",
            })
    snapshots.sort(key=lambda e: e["date"])
    return snapshots


def list_projects() -> list[dict]:
    """Return all project pages with their state."""
    projects = []
    for f in REPO.glob("project-*.html"):
        slug = f.stem.replace("project-", "", 1)
        state = load_state(slug)
        if state:
            timeline = state.get("timeline", [])
            snap_count = sum(1 for e in timeline if e.get("kind", "snapshot") == "snapshot")
            projects.append({
                "slug": slug,
                "title": state.get("title", slug),
                "status": state.get("status", "active"),
                "deliverable_count": snap_count,
                "updated": state.get("updated", ""),
            })
    projects.sort(key=lambda p: p.get("updated", ""), reverse=True)
    return projects


# ─────────── Subcommands ───────────

def cmd_list(args):
    projects = list_projects()
    if args.json:
        print(json.dumps(projects, indent=2))
        return
    if not projects:
        print("No projects yet.")
        return
    print(f"{len(projects)} project(s):\n")
    for p in projects:
        print(f"  {p['slug']:32} {p['status']:8} {p['deliverable_count']:>3}d  {p['title']}")


def cmd_promote(args):
    slug = args.slug
    if not SLUG_RE.match(slug):
        sys.exit(f"Invalid slug: {slug!r}. Lowercase, hyphens, alphanumeric only.")
    if load_state(slug):
        sys.exit(f"Project '{slug}' already exists. Use add-snapshot or rename.")

    snapshots = discover_snapshots(slug)
    print(f"Found {len(snapshots)} matching snapshot(s) for slug '{slug}'")
    for s in snapshots:
        print(f"  • {s['date']}  {s['file']}")

    state = {
        "slug": slug,
        "title": args.title or slug.replace("-", " ").title(),
        "status": args.status,
        "owner": args.owner,
        "created": today_iso(),
        "updated": today_iso(),
        "latest_summary": args.summary or "",
        "open_items": [],
        "related": [],
        "timeline": snapshots,
    }
    p = write_project(state)
    print(f"\n[ok] Created {p.name}")
    print(f"     Title: {state['title']}")
    print(f"     Status: {state['status']}")
    print(f"     {len(snapshots)} snapshot(s) in timeline")


def cmd_add_snapshot(args):
    state = load_state(args.slug)
    if not state:
        sys.exit(f"Project '{args.slug}' not found. Use 'promote' first.")

    file_path = REPO / args.file
    if not file_path.exists():
        sys.exit(f"Deliverable file not found: {args.file}")

    # Skip if already in timeline
    if any(e.get("file") == args.file for e in state.get("timeline", [])):
        print(f"[noop] {args.file} already in {args.slug} timeline")
        return

    m = re.search(r"(\d{4}-\d{2}-\d{2})", args.file)
    date = m.group(1) if m else today_iso()
    title = args.title or args.file.replace(".html", "").replace("-", " ").title()

    state.setdefault("timeline", []).append({
        "file": args.file,
        "date": date,
        "title": title,
        "kind": "snapshot",
        "body": args.body or "",
    })
    if args.summary:
        state["latest_summary"] = args.summary
    p = write_project(state)
    print(f"[ok] Added {args.file} to {args.slug} timeline → {p.name}")


def cmd_append(args):
    state = load_state(args.slug)
    if not state:
        sys.exit(f"Project '{args.slug}' not found.")
    state.setdefault("timeline", []).append({
        "date": today_iso(),
        "title": args.note[:80] + ("…" if len(args.note) > 80 else ""),
        "kind": "update",
        "body": args.note,
    })
    p = write_project(state)
    print(f"[ok] Appended update note to {args.slug} → {p.name}")


def cmd_link(args):
    a_state = load_state(args.a)
    b_state = load_state(args.b)
    if not a_state:
        sys.exit(f"Project '{args.a}' not found.")
    if not b_state:
        sys.exit(f"Project '{args.b}' not found.")
    a_state.setdefault("related", [])
    b_state.setdefault("related", [])
    if args.b not in a_state["related"]:
        a_state["related"].append(args.b)
    if args.a not in b_state["related"]:
        b_state["related"].append(args.a)
    write_project(a_state)
    write_project(b_state)
    print(f"[ok] Linked {args.a} ↔ {args.b}")


def cmd_rename(args):
    old, new = args.old, args.new
    if not SLUG_RE.match(new):
        sys.exit(f"Invalid new slug: {new!r}")
    state = load_state(old)
    if not state:
        sys.exit(f"Project '{old}' not found.")
    if load_state(new):
        sys.exit(f"Project '{new}' already exists.")
    state["slug"] = new
    write_project(state)
    project_path(old).unlink()
    # Update related back-references
    for other in list_projects():
        s = load_state(other["slug"])
        if s and old in s.get("related", []):
            s["related"] = [new if r == old else r for r in s["related"]]
            write_project(s)
    print(f"[ok] Renamed {old} → {new}")


def cmd_set_status(args):
    state = load_state(args.slug)
    if not state:
        sys.exit(f"Project '{args.slug}' not found.")
    state["status"] = args.status
    write_project(state)
    print(f"[ok] Set {args.slug} status → {args.status}")


def cmd_set_summary(args):
    state = load_state(args.slug)
    if not state:
        sys.exit(f"Project '{args.slug}' not found.")
    state["latest_summary"] = args.text
    write_project(state)
    print(f"[ok] Updated latest summary for {args.slug}")


def main():
    p = argparse.ArgumentParser(description="Manage VM2 project pages.")
    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("list")
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_list)

    sp = sub.add_parser("promote", help="Create a new project from a slug")
    sp.add_argument("--slug", required=True)
    sp.add_argument("--title", default=None)
    sp.add_argument("--status", default="active", choices=["active", "watching", "closed"])
    sp.add_argument("--owner", default="Varun")
    sp.add_argument("--summary", default=None)
    sp.set_defaults(func=cmd_promote)

    sp = sub.add_parser("add-snapshot", help="Add a deliverable file to an existing project")
    sp.add_argument("--slug", required=True)
    sp.add_argument("--file", required=True)
    sp.add_argument("--title", default=None)
    sp.add_argument("--body", default=None)
    sp.add_argument("--summary", default=None, help="If provided, replaces project's Latest Summary")
    sp.set_defaults(func=cmd_add_snapshot)

    sp = sub.add_parser("append", help="Append a timestamped update note")
    sp.add_argument("--slug", required=True)
    sp.add_argument("--note", required=True)
    sp.set_defaults(func=cmd_append)

    sp = sub.add_parser("link")
    sp.add_argument("--a", required=True)
    sp.add_argument("--b", required=True)
    sp.set_defaults(func=cmd_link)

    sp = sub.add_parser("rename")
    sp.add_argument("--old", required=True)
    sp.add_argument("--new", required=True)
    sp.set_defaults(func=cmd_rename)

    sp = sub.add_parser("set-status")
    sp.add_argument("--slug", required=True)
    sp.add_argument("--status", required=True, choices=["active", "watching", "closed"])
    sp.set_defaults(func=cmd_set_status)

    sp = sub.add_parser("set-summary")
    sp.add_argument("--slug", required=True)
    sp.add_argument("--text", required=True)
    sp.set_defaults(func=cmd_set_summary)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
