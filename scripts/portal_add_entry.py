#!/usr/bin/env python3
"""
portal_add_entry.py — The ONE TRUE WAY to add a deliverable row to portal.html.

Why this exists:
  Multiple cron task instructions were freeform-editing portal.html and accidentally
  prepending raw <li><a> tags instead of inserting a proper <tr> row into <tbody>.
  This caused unstyled links above the topbar and a stray bullet list mid-table.

Usage (CLI):
  python3 scripts/portal_add_entry.py \\
      --file vm2-auto-helper-2026-04-30.html \\
      --title "VM2 Auto-Helper" \\
      --type "Auto-Helper" \\
      --date 2026-04-30

  # Optional flags:
  #   --updated YYYY-MM-DD   (defaults to --date)
  #   --portal portal.html   (defaults to portal.html in cwd)
  #   --dry-run              (print what would be inserted, don't write)

Cron task instructions should call this script instead of editing portal.html directly.

Type → badge mapping (case-insensitive):
  Daily Brief, Recurring Brief, Policy Brief        → badge-brief
  Auto-Helper, Monitoring, SAM Scan, Compliance     → badge-monitoring
  Research Brief, Deep Dive, Architecture, Tech     → badge-research
  Strategy, BD & Capture, HR, Operations, Marketing → badge-writing
  Travel Research, Calendar                         → badge-travel
  Daily Habit, Birthday                             → badge-birthday
"""
import argparse
import re
import sys
from pathlib import Path

# Map normalized type to (display_label, badge_class)
TYPE_MAP = {
    "daily brief":      ("Daily Brief",      "badge-brief"),
    "recurring brief":  ("Recurring Brief",  "badge-brief"),
    "policy brief":     ("Policy Brief",     "badge-brief"),
    "auto-helper":      ("Auto-Helper",      "badge-monitoring"),
    "monitoring":       ("Monitoring",       "badge-monitoring"),
    "sam scan":         ("SAM Scan",         "badge-monitoring"),
    "compliance":       ("Compliance",       "badge-monitoring"),
    "research brief":   ("Research Brief",   "badge-research"),
    "deep dive":        ("Deep Dive",        "badge-research"),
    "architecture":     ("Architecture",     "badge-research"),
    "tech":             ("Tech",             "badge-research"),
    "strategy":         ("Strategy",         "badge-writing"),
    "bd & capture":     ("BD & Capture",     "badge-writing"),
    "hr":               ("HR",               "badge-writing"),
    "operations":       ("Operations",       "badge-writing"),
    "marketing":        ("Marketing",        "badge-writing"),
    "travel research":  ("Travel Research",  "badge-travel"),
    "calendar":         ("Calendar",         "badge-travel"),
    "daily habit":      ("Daily Habit",      "badge-birthday"),
    "birthday":         ("Birthday",         "badge-birthday"),
    "digest":           ("Digest",           "badge-research"),
}

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
TBODY_MARKER = '<tbody id="tableBody">'


def html_escape(s: str) -> str:
    return (
        s.replace("&", "&amp;")
         .replace("<", "&lt;")
         .replace(">", "&gt;")
         .replace('"', "&quot;")
    )


def lookup_type(type_str: str) -> tuple[str, str]:
    key = type_str.strip().lower()
    if key in TYPE_MAP:
        return TYPE_MAP[key]
    # Fallback: keep label as-is, generic research badge
    return (type_str.strip(), "badge-research")


def build_row(file: str, title: str, type_str: str, date: str, updated: str) -> str:
    label, badge = lookup_type(type_str)
    file_e = html_escape(file)
    title_e = html_escape(title)
    return (
        f'<tr data-date="{date}" data-type="{html_escape(label)}" data-updated="{updated}">\n'
        f'<td class="col-date">{date}</td>\n'
        f'<td class="col-title"><a href="{file_e}">{title_e}</a></td>\n'
        f'<td class="col-type"><span class="badge {badge}">{html_escape(label)}</span></td>\n'
        f'<td class="col-updated">{updated}</td>\n'
        f'<td class="col-link"><a class="link-icon" href="{file_e}" title="Open">↗</a></td>\n'
        f'</tr>\n'
    )


def insert_row(portal_path: Path, row_html: str, dedupe_file: str) -> bool:
    """Insert row right after <tbody id=\"tableBody\">. Returns True if inserted."""
    content = portal_path.read_text(encoding="utf-8")

    # Sanity: must start with DOCTYPE
    if not content.lstrip().startswith("<!DOCTYPE"):
        raise RuntimeError(
            f"{portal_path} does not start with <!DOCTYPE>. Refusing to write — "
            "file is corrupted. Clean it before running this script."
        )

    if TBODY_MARKER not in content:
        raise RuntimeError(f"Could not find {TBODY_MARKER!r} in {portal_path}")

    # Dedupe: skip if this filename already has a <tr> with href to it
    href_pattern = re.compile(
        rf'<tr[^>]*>\s*<td class="col-date">[^<]*</td>\s*'
        rf'<td class="col-title"><a href="{re.escape(dedupe_file)}">'
    )
    if href_pattern.search(content):
        print(f"[skip] {dedupe_file} already has a row in portal.html")
        return False

    # Insert immediately after the tbody opening tag
    new_content = content.replace(
        TBODY_MARKER + "\n",
        TBODY_MARKER + "\n" + row_html,
        1,
    )
    if new_content == content:
        # Marker had no trailing newline; try without
        new_content = content.replace(TBODY_MARKER, TBODY_MARKER + "\n" + row_html, 1)

    portal_path.write_text(new_content, encoding="utf-8")
    return True


def main():
    p = argparse.ArgumentParser(description="Add a deliverable row to portal.html (the safe way).")
    p.add_argument("--file", required=True, help="Deliverable filename (e.g. foo-2026-04-30.html)")
    p.add_argument("--title", required=True, help="Display title (e.g. 'Daily Executive Agenda')")
    p.add_argument("--type", required=True, help="Type label (e.g. 'Daily Brief', 'Auto-Helper')")
    p.add_argument("--date", required=True, help="Created date YYYY-MM-DD")
    p.add_argument("--updated", default=None, help="Updated date YYYY-MM-DD (defaults to --date)")
    p.add_argument("--portal", default="portal.html", help="Path to portal.html")
    p.add_argument("--dry-run", action="store_true", help="Print row, don't write")
    args = p.parse_args()

    if not DATE_RE.match(args.date):
        sys.exit(f"--date must be YYYY-MM-DD, got: {args.date}")
    updated = args.updated or args.date
    if not DATE_RE.match(updated):
        sys.exit(f"--updated must be YYYY-MM-DD, got: {updated}")
    if "/" in args.file or "\\" in args.file:
        sys.exit(f"--file must be a bare filename, no path separators: {args.file}")

    row_html = build_row(args.file, args.title, args.type, args.date, updated)

    if args.dry_run:
        print("Would insert:\n" + row_html)
        return

    portal_path = Path(args.portal)
    if not portal_path.exists():
        sys.exit(f"Portal file not found: {portal_path}")

    inserted = insert_row(portal_path, row_html, args.file)
    if inserted:
        print(f"[ok] Inserted row for {args.file} into {portal_path}")
    else:
        print(f"[noop] {args.file} already present; portal not modified")


if __name__ == "__main__":
    main()
