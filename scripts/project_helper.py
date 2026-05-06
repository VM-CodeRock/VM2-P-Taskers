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

CATEGORY_LABELS = {
    "bd": ("BD", "#c53a3a"),
    "internal": ("Internal", "#1f4d78"),
    "personal": ("Personal", "#2d7d4a"),
    "strategy": ("Strategy", "#6b4c9a"),
    "": ("Project", "#b9b6ad"),
}
MONTH_NAMES = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
               "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def html_escape(s) -> str:
    if s is None:
        return ""
    s = str(s)
    return (s.replace("&", "&amp;")
             .replace("<", "&lt;").replace(">", "&gt;")
             .replace('"', "&quot;"))


def relative_time(date_str: str) -> str:
    """Convert YYYY-MM-DD to relative human-readable time."""
    if not date_str:
        return "—"
    try:
        d = datetime.strptime(date_str[:10], "%Y-%m-%d")
    except ValueError:
        return date_str
    today = datetime.now(timezone.utc).replace(tzinfo=None)
    delta = (today - d).days
    if delta < 0:
        return f"in {-delta}d"
    if delta == 0:
        return "today"
    if delta == 1:
        return "yesterday"
    if delta < 7:
        return f"{delta}d ago"
    if delta < 30:
        weeks = delta // 7
        return f"{weeks}w ago"
    if delta < 365:
        months = delta // 30
        return f"{months}mo ago"
    years = delta // 365
    return f"{years}y ago"


def days_until(date_str: str) -> int | None:
    """Return days until date_str. Negative = overdue. None = invalid date."""
    if not date_str:
        return None
    try:
        d = datetime.strptime(date_str[:10], "%Y-%m-%d")
    except ValueError:
        return None
    return (d - datetime.now(timezone.utc).replace(tzinfo=None)).days


def format_human_date(date_str: str) -> str:
    """YYYY-MM-DD -> 'May 5, 2026'."""
    if not date_str:
        return "—"
    try:
        d = datetime.strptime(date_str[:10], "%Y-%m-%d")
        return d.strftime("%b %-d, %Y")
    except (ValueError, AttributeError):
        return date_str


def format_short_date(date_str: str) -> str:
    """YYYY-MM-DD -> 'May 15'."""
    if not date_str:
        return "—"
    try:
        d = datetime.strptime(date_str[:10], "%Y-%m-%d")
        return d.strftime("%b %-d")
    except (ValueError, AttributeError):
        return date_str


def build_beat_chart(timeline: list, months: int = 8) -> tuple[str, str]:
    """Build the activity beat chart (last N months). Returns (bars_html, labels_html)."""
    today = datetime.now(timezone.utc).replace(tzinfo=None)
    # Build buckets keyed by (year, month)
    buckets: dict[tuple[int, int], int] = {}
    for entry in timeline:
        ds = entry.get("date", "")
        try:
            d = datetime.strptime(ds[:10], "%Y-%m-%d")
        except ValueError:
            continue
        key = (d.year, d.month)
        buckets[key] = buckets.get(key, 0) + 1

    # Generate the last N months
    cells = []
    cur_year, cur_month = today.year, today.month
    for i in range(months - 1, -1, -1):
        m = cur_month - i
        y = cur_year
        while m <= 0:
            m += 12
            y -= 1
        cells.append((y, m))

    max_count = max(buckets.values()) if buckets else 1
    bars = []
    labels = []
    for i, (y, m) in enumerate(cells):
        count = buckets.get((y, m), 0)
        is_now = (i == len(cells) - 1)
        if count == 0:
            cls = ""
            height = 4
        else:
            ratio = count / max_count
            cls = "active" if ratio > 0.4 else "dim"
            height = max(6, int(28 * ratio))
        bars.append(
            f'          <div class="month"><div class="bar {cls}" style="height:{height}px;" '
            f'title="{MONTH_NAMES[m-1]} {y}: {count}"></div></div>'
        )
        label_class = "label-cell now" if is_now else "label-cell"
        labels.append(f'          <span class="{label_class}">{MONTH_NAMES[m-1]}</span>')
    return ("\n".join(bars), "\n".join(labels))


def build_grouped_timeline(timeline: list) -> str:
    """Group timeline entries by year-month and render with collapsible sections."""
    if not timeline:
        return '    <p class="empty-line" style="font-style:italic;color:var(--text-faint);">No timeline entries yet.</p>'

    # Sort reverse-chrono
    sorted_entries = sorted(
        timeline,
        key=lambda e: (e.get("date", "0000-00-00"), e.get("kind", "")),
        reverse=True,
    )
    # Group by (year, month)
    groups: dict[tuple[int, int], list] = {}
    for e in sorted_entries:
        try:
            d = datetime.strptime(e.get("date", "")[:10], "%Y-%m-%d")
        except ValueError:
            continue
        key = (d.year, d.month)
        groups.setdefault(key, []).append(e)

    today = datetime.now(timezone.utc).replace(tzinfo=None)
    out = []
    for i, (key, entries) in enumerate(groups.items()):
        y, m = key
        # Collapse if more than 1 month older than today
        is_current = (y == today.year and m == today.month) or i == 0
        collapsed = "" if is_current else " collapsed"
        chevron = "▾" if is_current else "▸"
        month_label = f"{MONTH_NAMES[m-1]} {y}"
        out.append(f'      <div class="timeline-month{collapsed}">')
        out.append(
            f'        <div class="timeline-month-head{collapsed}">'
            f'<span class="chevron">{chevron}</span> {month_label} '
            f'<span class="count">· {len(entries)}</span></div>'
        )
        out.append('        <div class="timeline-entries">')
        for e in entries:
            kind = e.get("kind", "snapshot")
            kind_class = "update" if kind == "update" else ""
            kind_label = "Update" if kind == "update" else "Snapshot"
            try:
                d = datetime.strptime(e.get("date", "")[:10], "%Y-%m-%d")
                short_date = d.strftime("%b %-d")
            except ValueError:
                short_date = e.get("date", "")
            title = html_escape(e.get("title", ""))
            file_ = e.get("file", "")
            body = html_escape(e.get("body", ""))
            title_html = f'<a href="{html_escape(file_)}">{title}</a>' if file_ else title
            body_html = f'\n            <div class="body">{body}</div>' if body else ""
            out.append(
                f'          <div class="timeline-entry {kind_class}">\n'
                f'            <div class="timeline-entry-head">'
                f'<span class="date">{short_date}</span>'
                f'<span class="kind {kind_class}">{kind_label}</span></div>\n'
                f'            <div class="title">{title_html}</div>'
                f'{body_html}\n'
                f'          </div>'
            )
        out.append('        </div>')
        out.append('      </div>')
    return "\n".join(out)


def build_open_items_html(items: list) -> str:
    """Render open items with due-date badges."""
    if not items:
        return '      <p class="empty-line" style="padding:14px 18px;color:var(--text-faint);font-style:italic;">No open items.</p>'
    out = ['      <ul class="open-items">']
    for item in items:
        text = html_escape(item.get("text", ""))
        done = item.get("done", False)
        due = item.get("due_date", "") or ""
        if done:
            done_date = item.get("done_date", "")
            badge = f'<span class="due-badge done">Done{" " + format_short_date(done_date) if done_date else ""}</span>'
            li_cls = "done"
        elif due:
            days = days_until(due)
            if days is None:
                badge = f'<span class="due-badge none">No date</span>'
            elif days < 0:
                badge = f'<span class="due-badge overdue">Overdue · {-days}d</span>'
            elif days <= 7:
                badge = f'<span class="due-badge soon">Due {format_short_date(due)}</span>'
            else:
                badge = f'<span class="due-badge">{format_short_date(due)}</span>'
            li_cls = ""
        else:
            badge = '<span class="due-badge none">No date</span>'
            li_cls = ""
        out.append(
            f'        <li class="{li_cls}"><span class="check"></span>'
            f'<span class="text">{text}</span>{badge}</li>'
        )
    out.append('      </ul>')
    return "\n".join(out)


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
    """Render state → project-<slug>.html using the v3 redesigned template."""
    import json as _json

    slug = state["slug"]
    p = project_path(slug)

    status = state.get("status", "active")
    status_label = status.upper()
    status_class = status

    # Category
    cat = (state.get("category") or "").strip().lower()
    cat_label, cat_color = CATEGORY_LABELS.get(cat, CATEGORY_LABELS[""])
    cat_class = cat or "default"

    # Stage chunk for crumb header
    stage = (state.get("stage") or "").strip()
    stage_chunk = f" · {html_escape(stage)}" if stage else ""

    # Identifier (e.g. RFP number) — if first timeline entry has it in title we'd surface it,
    # but for now we just keep slug. Optional 'identifier' field surfaces if set.
    identifier = (state.get("identifier") or "").strip()
    identifier_chunk = f" · {html_escape(identifier)}" if identifier else ""

    timeline = state.get("timeline", [])
    snapshot_count = sum(1 for e in timeline if e.get("kind", "snapshot") == "snapshot")

    open_items = state.get("open_items", [])
    open_count = sum(1 for i in open_items if not i.get("done"))
    due_soon_count = 0
    for i in open_items:
        if i.get("done"): continue
        days = days_until(i.get("due_date", ""))
        if days is not None and days <= 7:
            due_soon_count += 1
    due_soon_class = "warning" if due_soon_count > 0 else ""

    # Project age
    created = state.get("created", today_iso())
    age_days = days_until(created)
    age_days = -age_days if age_days is not None else 0
    if age_days < 30:
        project_age = f"{age_days}d"
    elif age_days < 365:
        project_age = f"{age_days // 30}mo"
    else:
        project_age = f"{age_days // 365}y"

    # Last activity
    last_activity = "never"
    if timeline:
        latest_date = max((e.get("date", "") for e in timeline), default="")
        last_activity = relative_time(latest_date) if latest_date else "never"

    # Latest summary
    summary = (state.get("latest_summary", "") or "").strip()
    if summary:
        paras = [f"        <p>{html_escape(s.strip())}</p>" for s in summary.split("\n\n") if s.strip()]
        latest_summary_html = "\n".join(paras)
        summary_source = "Auto-extracted from latest snapshot" if state.get("auto_summary", True) else "Manual"
    else:
        latest_summary_html = '        <p class="empty">No summary yet. Click Refresh to extract from latest snapshot, or Edit to write one.</p>'
        summary_source = "—"

    # Beat chart
    bars_html, labels_html = build_beat_chart(timeline)

    # Timeline grouped by month
    timeline_html = build_grouped_timeline(timeline)

    # Open items
    open_items_html = build_open_items_html(open_items)

    # Tags
    tags = state.get("tags", [])
    if tags:
        tag_chunks = " ".join(f'<span class="sidebar-tag">{html_escape(t)}</span>' for t in tags)
        tags_html = (
            '      <div style="margin-top: 10px;">\n'
            '        <div style="font-size:11px;color:var(--text-faint);text-transform:uppercase;'
            'letter-spacing:0.6px;margin-bottom:6px;">Tags</div>\n'
            f'        <div class="sidebar-tags">{tag_chunks}</div>\n'
            '      </div>'
        )
    else:
        tags_html = (
            '      <div style="margin-top: 10px;">\n'
            '        <div style="font-size:11px;color:var(--text-faint);text-transform:uppercase;'
            'letter-spacing:0.6px;margin-bottom:6px;">Tags</div>\n'
            '        <div class="empty-line">No tags yet.</div>\n'
            '      </div>'
        )

    # Key dates
    key_dates = state.get("key_dates", [])
    if key_dates:
        kd_lines = []
        for kd in key_dates:
            label = html_escape(kd.get("label", ""))
            date = kd.get("date", "")
            days = days_until(date)
            cls = ""
            if days is not None:
                if days < 0: cls = "overdue"
                elif days <= 14: cls = "urgent"
            kd_lines.append(
                f'      <div class="key-date {cls}">'
                f'<span class="label">{label}</span>'
                f'<span class="when">{format_short_date(date)}</span>'
                f'</div>'
            )
        key_dates_html = "\n".join(kd_lines)
    else:
        key_dates_html = '      <div class="empty-line">No key dates set.</div>'

    # Related projects
    related = state.get("related", [])
    if related:
        rel_lines = ['      <ul class="sidebar-list">']
        for r_slug in related:
            r_state = load_state(r_slug)
            r_label = r_state["title"] if r_state else r_slug
            r_updated = r_state.get("updated", "") if r_state else ""
            r_meta = relative_time(r_updated) if r_updated else ""
            rel_lines.append(
                f'        <li><a href="project-{r_slug}.html">{html_escape(r_label)}</a>'
                f'<span class="meta">{r_meta}</span></li>'
            )
        rel_lines.append('      </ul>')
        related_html = "\n".join(rel_lines)
    else:
        related_html = '      <div class="empty-line">No related projects yet.</div>'

    # Auto-summary label
    auto_summary_label = "On" if state.get("auto_summary", True) else "Off"

    # Render
    rendered = PROJECT_HTML_TEMPLATE.format(
        slug=html_escape(slug),
        slug_json=_json.dumps(slug),
        title=html_escape(state.get("title", slug)),
        title_json=_json.dumps(state.get("title", slug)),
        status_label=status_label,
        status_class=status_class,
        owner=html_escape(state.get("owner", "Varun")),
        created=html_escape(created),
        created_human=format_human_date(created),
        updated=today_iso(),
        last_activity=last_activity,
        deliverable_count=snapshot_count,
        open_count=open_count,
        due_soon_count=due_soon_count,
        due_soon_class=due_soon_class,
        project_age=project_age,
        cat_class=cat_class,
        cat_color=cat_color,
        category_label=cat_label,
        stage_chunk=stage_chunk,
        identifier_chunk=identifier_chunk,
        latest_summary_html=latest_summary_html,
        summary_source=summary_source,
        beat_chart_bars=bars_html,
        beat_chart_labels=labels_html,
        timeline_html=timeline_html,
        open_items_html=open_items_html,
        tags_html=tags_html,
        key_dates_html=key_dates_html,
        related_html=related_html,
        auto_summary_label=auto_summary_label,
    )

    state["updated"] = today_iso()
    state_block = f"\n{STATE_BEGIN}\n{_json.dumps(state, indent=2)}\n{STATE_END}\n"
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
        "category": getattr(args, "category", "") or "",  # bd | internal | personal | strategy
        "stage": getattr(args, "stage", "") or "",          # free-text stage label
        "tags": [],
        "key_dates": [],   # [{label, date}]
        "auto_summary": True,
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
