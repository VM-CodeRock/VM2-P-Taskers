#!/usr/bin/env python3
"""
portal_lint.py — Guard against portal.html corruption.

Checks (any failure → exit 1):
  1. File starts with <!DOCTYPE html>          (no garbage prepended)
  2. No <li>...</li> outside a <ul>/<ol>       (no stray bullet lists)
  3. <tbody id="tableBody"> exists             (table body intact)
  4. No <li> tag immediately follows </td>     (catches mid-row corruption)
  5. Every <tr data-date=...> has 5 <td>s      (column integrity)

Run from repo root:
  python3 scripts/portal_lint.py [portal.html]
"""
import re
import sys
from pathlib import Path


def lint(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    errors = []

    # 1. DOCTYPE first
    if not text.lstrip().startswith("<!DOCTYPE html>"):
        first = text[:200].replace("\n", "\\n")
        errors.append(f"File does not start with <!DOCTYPE html>. First 200 chars: {first!r}")

    # 2. Stray top-level <li>
    # Find every <li> position and check that an unclosed <ul> or <ol> precedes it.
    for m in re.finditer(r"<li\b", text):
        before = text[: m.start()]
        # Count open vs close of ul/ol
        opens = len(re.findall(r"<(?:ul|ol)\b", before))
        closes = len(re.findall(r"</(?:ul|ol)>", before))
        if opens <= closes:
            line = before.count("\n") + 1
            errors.append(f"Stray <li> outside any <ul>/<ol> at line ~{line}")
            if len(errors) > 5:
                break  # avoid spam

    # 3. tbody marker
    if '<tbody id="tableBody">' not in text:
        errors.append('Missing <tbody id="tableBody">')

    # 4. <li> right after </td> (the mid-row corruption pattern)
    bad = re.findall(r"</td>\s*\n?\s*<li\b", text)
    if bad:
        errors.append(f"Found {len(bad)} <li> tag(s) immediately after </td> (table corruption)")

    # 5. Column count per <tr data-date>
    rows = re.findall(r"<tr\s+data-date=[^>]*>(.*?)</tr>", text, re.DOTALL)
    for i, row in enumerate(rows):
        td_count = len(re.findall(r"<td\b", row))
        if td_count != 5:
            errors.append(f"Row #{i+1} has {td_count} <td> cells (expected 5)")
            if len([e for e in errors if "Row #" in e]) > 3:
                break

    return errors


def main():
    path = Path(sys.argv[1] if len(sys.argv) > 1 else "portal.html")
    if not path.exists():
        sys.exit(f"File not found: {path}")
    errors = lint(path)
    if errors:
        print(f"❌ {path} has {len(errors)} issue(s):")
        for e in errors:
            print(f"  - {e}")
        sys.exit(1)
    print(f"✅ {path} is clean")


if __name__ == "__main__":
    main()
