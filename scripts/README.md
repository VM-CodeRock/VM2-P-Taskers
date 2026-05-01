# Portal Scripts — How To Update `portal.html` Safely

## TL;DR for cron task instructions

When a cron creates a new deliverable HTML file, **do not edit `portal.html` by hand**. Run:

```bash
python3 scripts/portal_add_entry.py \
    --file <deliverable-filename.html> \
    --title "Display Title" \
    --type "Daily Brief" \
    --date 2026-04-30
```

That's it. The script:
- Inserts a properly-formatted `<tr>` row into `<tbody id="tableBody">`
- Picks the correct badge class for the type
- Skips silently if the file already has a row (idempotent)
- Refuses to write if `portal.html` is corrupted

## Why this exists

Between Apr 8 and Apr 27, 2026, ten different cron commits accidentally appended raw `<li><a href=...></a></li>` markup to `portal.html` instead of inserting `<tr>` table rows. Some entries even landed *before* `<!DOCTYPE html>`, rendering as unstyled underlined links above the topbar. This script eliminates the freeform-edit failure mode.

## Bad — never do this in cron task instructions

```bash
# WRONG: prepending raw <li> markup
echo '<li><a href="foo.html">Foo</a></li>' | cat - portal.html > tmp && mv tmp portal.html

# WRONG: sed insert with manual HTML
sed -i '/<tbody/a <li><a href="foo.html">Foo</a></li>' portal.html
```

## Good — always use the helper

```bash
python3 scripts/portal_add_entry.py --file foo-2026-04-30.html --title "Foo Report" --type "Daily Brief" --date 2026-04-30
```

## Verifying integrity

After any commit that touches `portal.html`, run the linter:

```bash
python3 scripts/portal_lint.py
```

Returns exit 1 with details if it finds:
- Garbage before `<!DOCTYPE html>`
- Stray `<li>` outside any `<ul>`/`<ol>`
- Missing `<tbody id="tableBody">`
- `<li>` immediately following `</td>` (mid-row corruption)
- Any `<tr data-date>` row with ≠5 `<td>` cells

The nightly `vm2-wrapup` compliance audit should run this and fail loudly on errors.

## Type → badge mapping

| Type input (case-insensitive) | Badge class |
|---|---|
| Daily Brief, Recurring Brief, Policy Brief | `badge-brief` (amber) |
| Auto-Helper, Monitoring, SAM Scan, Compliance | `badge-monitoring` (green) |
| Research Brief, Deep Dive, Architecture, Tech, Digest | `badge-research` (blue) |
| Strategy, BD & Capture, HR, Operations, Marketing | `badge-writing` (purple) |
| Travel Research, Calendar | `badge-travel` (pink) |
| Daily Habit, Birthday | `badge-birthday` (rose) |

Unknown types fall back to `badge-research`. Add new mappings in `portal_add_entry.py`.
