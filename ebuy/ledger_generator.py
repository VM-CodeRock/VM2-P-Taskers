#!/usr/bin/env python3
"""
Generates the Changeis-branded eBuy Ledger HTML from ebuy_history.jsonl.
"""
import json
import html as html_lib
from datetime import datetime, timezone, timedelta
from pathlib import Path
from collections import Counter

HERE = Path(__file__).parent
HISTORY_PATH = HERE / 'ebuy_history.jsonl'
# Output to repo root (one level up from ebuy/)
OUTPUT_PATH = HERE.parent / 'ebuy-ledger.html'
ANALYST_EMAIL_PLACEHOLDER = 'TBD@changeis.com'   # User will provide later

# Friendly names for contract vehicles (per Varun, 5/19/2026)
VEHICLE_NAMES = {
    '47QTCA18D0078': 'GSA MAS',
    '47QTCB22D0075': 'STARS III',
    '47QRCA25DS260': 'OASIS+ SB',
    '47QRCA25DU072': 'OASIS+ UR',
    '47QRCA25DS139': 'Agile OASIS+ SB',
    '47QRCA25DA423': 'ArchZen OASIS+ SB',
}


ET = timezone(timedelta(hours=-4))  # EDT in May
NOW = datetime.now(ET)
TODAY = NOW.date()

STATUS_BADGE_COLORS = {
    'NEW REQUEST': ('#2D7D4A', '#FFFFFF'),   # green
    'AMENDED':     ('#D97D2A', '#FFFFFF'),   # orange
    'Q&A ADDED':   ('#1F4D78', '#FFFFFF'),   # blue
    'CANCELED':    ('#B22222', '#FFFFFF'),   # red
    'CANCELLED':   ('#B22222', '#FFFFFF'),
    'WITHDRAWN':   ('#B22222', '#FFFFFF'),
    'CLOSED':      ('#666666', '#FFFFFF'),
}


def load_events():
    events = []
    with HISTORY_PATH.open() as f:
        for line in f:
            line = line.strip()
            if line:
                events.append(json.loads(line))
    return events


def parse_ebuy_dt(s):
    """Parse '04/06/2026 06:10 PM EDT' -> datetime in ET."""
    if not s:
        return None
    try:
        # Strip the timezone abbreviation
        clean = s.replace(' EDT', '').replace(' EST', '').strip()
        return datetime.strptime(clean, '%m/%d/%Y %I:%M %p').replace(tzinfo=ET)
    except Exception:
        return None


def fmt_dt(s):
    """Pretty short date+time."""
    dt = parse_ebuy_dt(s)
    if not dt:
        return s or ''
    return dt.strftime('%b %d, %Y %I:%M %p ET')


def fmt_date(s):
    dt = parse_ebuy_dt(s)
    if not dt:
        return s or ''
    return dt.strftime('%b %d, %Y')


def days_until_due(due_str):
    dt = parse_ebuy_dt(due_str)
    if not dt:
        return None
    delta = dt - NOW
    return delta.days


def escape(s):
    if s is None:
        return ''
    return html_lib.escape(str(s))


def status_badge(status):
    bg, fg = STATUS_BADGE_COLORS.get(status, ('#666666', '#FFFFFF'))
    return f'<span class="status-badge" style="background:{bg};color:{fg};">{escape(status)}</span>'


def mailto_link(ev):
    subj = f"eBuy Download Request - {ev['request_id']} - {(ev.get('title') or '')[:80]}"
    vehicle_code = ev.get('vehicle') or ''
    vehicle_name = VEHICLE_NAMES.get(vehicle_code, '')
    vehicle_str = f'{vehicle_name} ({vehicle_code})' if vehicle_name else (vehicle_code or 'unknown')
    body_lines = [
        "Request to download all materials for the following request:",
        "",
        f"eBuy Request ID: {ev['request_id']}",
        f"Title: {ev.get('title') or '(not parsed)'}",
        f"Buyer: {ev.get('buyer') or '(not parsed)'}",
        f"Posted: {ev.get('posted_date') or '(unknown)'}",
        f"Due By: {ev.get('due_by') or '(unknown)'}",
        f"Contract Vehicle: {vehicle_str}",
        "",
        "Save attachments to: Dropbox and attach to email",
        "",
        "Thanks,",
        "Varun"
    ]
    body = '\n'.join(body_lines)
    # urlencode minimally
    import urllib.parse
    return f"mailto:{ANALYST_EMAIL_PLACEHOLDER}?subject={urllib.parse.quote(subj)}&body={urllib.parse.quote(body)}"


def build_row(ev, is_today=False):
    posted_dt = parse_ebuy_dt(ev.get('posted_date'))
    due_dt = parse_ebuy_dt(ev.get('due_by'))
    dtu = days_until_due(ev.get('due_by'))

    due_class = ''
    due_label = ''
    if dtu is not None:
        if dtu < 0:
            due_class = 'due-past'
            due_label = f'Closed ({abs(dtu)}d ago)'
        elif dtu <= 3:
            due_class = 'due-urgent'
            due_label = f'{dtu}d left'
        elif dtu <= 7:
            due_class = 'due-soon'
            due_label = f'{dtu}d left'
        else:
            due_class = 'due-ok'
            due_label = f'{dtu}d left'

    today_class = ' is-today' if is_today else ''
    posted_iso = posted_dt.isoformat() if posted_dt else ''
    due_iso = due_dt.isoformat() if due_dt else ''

    title = ev.get('title') or '(not parsed)'
    buyer = ev.get('buyer') or '(not parsed)'

    return f"""
<tr class="row{today_class}"
    data-status="{escape(ev['status'])}"
    data-vehicle="{escape(ev.get('vehicle') or '')}"
    data-posted="{posted_iso}"
    data-due="{due_iso}"
    data-reqid="{escape(ev['request_id'])}"
    data-title="{escape(title)}"
    data-buyer="{escape(buyer)}">
  <td class="col-status">{status_badge(ev['status'])}</td>
  <td class="col-reqid"><code>{escape(ev['request_id'])}</code></td>
  <td class="col-title">{escape(title)}</td>
  <td class="col-buyer">{escape(buyer)}</td>
  <td class="col-vehicle"><div class="vehicle-name">{escape(VEHICLE_NAMES.get(ev.get('vehicle') or '', ''))}</div><code class="vehicle-code">{escape(ev.get('vehicle') or '')}</code></td>
  <td class="col-posted">{fmt_dt(ev.get('posted_date'))}</td>
  <td class="col-due"><div>{fmt_dt(ev.get('due_by'))}</div><div class="due-pill {due_class}">{due_label}</div></td>
  <td class="col-action"><a class="btn-request" href="{mailto_link(ev)}">Request Analyst Download</a></td>
</tr>"""


def main():
    events = load_events()
    # Sort newest first by email_date
    events.sort(key=lambda e: e.get('email_date') or '', reverse=True)

    # Stats
    total = len(events)
    unique_reqs = len(set(e['request_id'] for e in events))
    status_counts = Counter(e['status'] for e in events)
    vehicle_counts = Counter(e['vehicle'] for e in events)

    # Today's review = events whose email_date is today in ET
    today_events = []
    for e in events:
        try:
            ed = datetime.fromisoformat(e['email_date'].replace('Z', '+00:00')).astimezone(ET).date()
            if ed == TODAY:
                today_events.append(e)
        except Exception:
            pass

    # 24h section
    cutoff_24h = NOW - timedelta(hours=24)
    last24h_events = []
    for e in events:
        try:
            ed = datetime.fromisoformat(e['email_date'].replace('Z', '+00:00')).astimezone(ET)
            if ed >= cutoff_24h:
                last24h_events.append(e)
        except Exception:
            pass

    # Build today's pinned rows
    today_rows = '\n'.join(build_row(e, is_today=True) for e in today_events) if today_events else ''
    if not today_rows:
        today_rows = '<tr><td colspan="8" class="empty-state">No new notices today.</td></tr>'

    # Build full table rows
    full_rows = '\n'.join(build_row(e, is_today=False) for e in events)

    # Generation time
    gen_time = NOW.strftime('%b %d, %Y %I:%M %p ET')
    date_range_lo = min((e.get('email_date') or '') for e in events) if events else ''
    date_range_hi = max((e.get('email_date') or '') for e in events) if events else ''
    try:
        lo_label = datetime.fromisoformat(date_range_lo.replace('Z', '+00:00')).strftime('%b %d, %Y')
        hi_label = datetime.fromisoformat(date_range_hi.replace('Z', '+00:00')).strftime('%b %d, %Y')
        range_label = f'{lo_label} — {hi_label}'
    except Exception:
        range_label = 'Backfill'

    # Build status badges for filter
    status_filter_opts = ''.join(
        f'<option value="{escape(s)}">{escape(s)} ({c})</option>'
        for s, c in status_counts.most_common()
    )
    vehicle_filter_opts = ''.join(
        f'<option value="{escape(v)}">{escape(VEHICLE_NAMES.get(v, v))} · {escape(v)} ({c})</option>'
        for v, c in vehicle_counts.most_common()
    )

    # Context slug for VM2 deliverable
    context_data = {
        "deliverable": "ebuy_ledger",
        "version": "1.0-backfill",
        "generated_at": NOW.isoformat(),
        "date_range": range_label,
        "stats": {
            "total_events": total,
            "unique_requests": unique_reqs,
            "status_breakdown": dict(status_counts),
            "vehicle_breakdown": dict(vehicle_counts),
            "events_today": len(today_events),
            "events_24h": len(last24h_events),
        },
        "data_sources": {
            "history_file": str(HISTORY_PATH),
            "raw_emails_file": "/home/user/workspace/ebuy_emails_raw.json",
            "source_mailbox": "varun@changeis.com (Outlook)",
            "source_sender": "ebuy_admin@gsa.gov",
        },
        "analyst_email_placeholder": ANALYST_EMAIL_PLACEHOLDER,
        "cron_cadence": {
            "weekdays": "9 AM and 4 PM ET",
            "weekends": "12 PM ET only",
            "utc_cron_edt": "0 13,20 * * 1-5 + 0 16 * * 0,6 + 0 0 * * 1 (reconcile)",
            "cron_ids": {
                "weekday_9am": "b98dfb95",
                "weekday_4pm": "3bc6d0fa",
                "weekend_noon": "6c80e6a2",
                "weekly_reconcile": "ce5ef3a6"
            },
        },
        "cost_estimate": {
            "model": "claude-sonnet-4.5",
            "pricing": {"input_per_mtok_usd": 3.00, "output_per_mtok_usd": 15.00},
            "tokens": {"input": 80000, "output": 12000},
            "conservative_usd": 0.42,
            "ceiling_usd": 0.85
        },
        "prior_versions": []
    }
    context_json = json.dumps(context_data, indent=2)

    html_out = f"""<!DOCTYPE html>
<html lang="en" data-theme="light">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Changeis eBuy Ledger — {range_label}</title>
<style>
:root {{
  --navy: #1B2A4A;
  --deep-navy: #002060;
  --brand-blue: #2E6DA4;
  --section-blue: #1F4D78;
  --teal: #008B8B;
  --green: #2D7D4A;
  --orange: #D97D2A;
  --purple: #6B4C9A;
  --red: #B22222;
  --bg: #FAFAF8;
  --surface: #FFFFFF;
  --surface-alt: #F2F6FA;
  --border: #D4D1CA;
  --text: #222222;
  --text-std: #333333;
  --text-muted: #666666;
  --text-faint: #888888;
  --callout-bg: #E8F4F8;
  --row-alt: #F2F6FA;
  --row-today: #FFF8E1;
  --link: #0563C1;
}}
[data-theme="dark"] {{
  --bg:#111318; --surface:#1a1d25; --surface-alt:#22252e;
  --border:#333740; --text:#d8d8d8; --text-std:#ccc;
  --text-muted:#8a8e96; --text-faint:#666;
  --callout-bg:#1e2a2e; --row-alt:#1e2129; --row-today:#3a3424;
  --link:#7eb3e0;
}}
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{
  font-family: Georgia, 'Times New Roman', serif;
  background:var(--bg); color:var(--text);
  line-height:1.5; font-size:14px;
}}
.topbar {{
  position:sticky; top:0; z-index:100;
  background:var(--navy); color:#fff;
  font-family:system-ui,-apple-system,sans-serif;
  font-size:13px; font-weight:600;
  padding:10px 24px; display:flex;
  align-items:center; justify-content:space-between;
  box-shadow:0 2px 8px rgba(0,0,0,0.15);
}}
.topbar-left {{ display:flex; align-items:center; gap:8px; }}
.topbar-dot {{ color:var(--orange); font-size:18px; }}
.theme-toggle {{
  background:rgba(255,255,255,0.12); border:1px solid rgba(255,255,255,0.2);
  color:#fff; border-radius:6px; padding:4px 10px;
  font-size:12px; cursor:pointer; font-family:system-ui,sans-serif;
}}
.theme-toggle:hover {{ background:rgba(255,255,255,0.22); }}
.container {{ max-width:1600px; margin:0 auto; padding:0 24px; }}
.hero {{
  text-align:center; padding:32px 0 20px;
  border-bottom:2px solid var(--border); margin-bottom:24px;
}}
.hero-badge {{
  display:inline-block; font-family:system-ui,sans-serif;
  font-size:11px; font-weight:700; text-transform:uppercase;
  letter-spacing:0.1em; background:var(--navy); color:#fff;
  padding:3px 14px; border-radius:3px; margin-bottom:10px;
}}
.hero h1 {{ font-family:Calibri,Arial,sans-serif; font-size:26px; font-weight:700; color:var(--navy); margin-bottom:4px; }}
[data-theme="dark"] .hero h1 {{ color:#e2e2e2; }}
.hero-sub {{ font-size:14px; color:var(--text-muted); font-style:italic; margin-bottom:4px; }}
.hero-date {{ font-family:system-ui,sans-serif; font-size:12px; color:var(--text-faint); }}

.section {{ margin-bottom:28px; }}
.section-header {{
  font-family:Calibri,Arial,sans-serif;
  font-size:13px; font-weight:700;
  text-transform:uppercase; letter-spacing:0.08em;
  color:var(--navy); border-bottom:2px solid var(--navy);
  padding-bottom:5px; margin-bottom:12px;
}}
[data-theme="dark"] .section-header {{ color:#e2e2e2; border-color:#e2e2e2; }}

.dash-row {{ display:grid; grid-template-columns:repeat(4,1fr); gap:12px; }}
@media (max-width:900px) {{ .dash-row {{ grid-template-columns:repeat(2,1fr); }} }}
.stat-card {{
  background:var(--surface); border:1px solid var(--border);
  border-radius:8px; padding:14px; text-align:center;
  box-shadow:0 1px 3px rgba(0,0,0,0.06);
}}
.stat-num {{
  font-family:Calibri,Arial,sans-serif; font-size:30px; font-weight:700;
  color:var(--navy); line-height:1;
}}
[data-theme="dark"] .stat-num {{ color:#e2e2e2; }}
.stat-label {{
  font-family:system-ui,sans-serif; font-size:11px;
  font-weight:600; text-transform:uppercase; letter-spacing:0.05em;
  color:var(--text-muted); margin-top:6px;
}}

.callout {{
  background:var(--callout-bg); border-left:3px solid var(--teal);
  padding:12px 16px; border-radius:4px; margin:12px 0;
  font-size:13px; color:var(--text-std);
}}
.callout strong {{ color:var(--navy); }}
[data-theme="dark"] .callout strong {{ color:#e2e2e2; }}

.controls {{
  display:flex; gap:10px; flex-wrap:wrap; margin-bottom:12px;
  font-family:system-ui,sans-serif; font-size:13px;
  align-items:center;
}}
.controls input, .controls select {{
  background:var(--surface); color:var(--text);
  border:1px solid var(--border); border-radius:6px;
  padding:6px 10px; font-size:13px;
}}
.controls input[type="text"] {{ min-width:240px; }}
.controls label {{ color:var(--text-muted); font-weight:600; font-size:12px; }}
.controls .filter-clear {{
  background:var(--navy); color:#fff; border:none; cursor:pointer;
  padding:6px 12px; border-radius:6px; font-size:12px; font-weight:600;
}}

.table-wrap {{
  background:var(--surface); border:1px solid var(--border);
  border-radius:8px; overflow:auto;
  box-shadow:0 1px 3px rgba(0,0,0,0.06);
  max-height:75vh;
}}
table.ledger {{
  width:100%; border-collapse:collapse; font-size:13px;
  table-layout:auto;
}}
table.ledger thead th {{
  position:sticky; top:0; z-index:2;
  background:var(--navy); color:#fff;
  font-family:Calibri,Arial,sans-serif; font-weight:700;
  font-size:12px; text-transform:uppercase; letter-spacing:0.04em;
  padding:10px 8px; text-align:left;
  border-bottom:2px solid var(--navy);
  cursor:pointer; user-select:none;
  white-space:nowrap;
}}
table.ledger thead th .sort-arrow {{ font-size:10px; margin-left:4px; opacity:0.6; }}
table.ledger tbody td {{
  padding:8px; vertical-align:top;
  border-bottom:1px solid var(--border);
  color:var(--text);
}}
table.ledger tbody tr:nth-child(even) {{ background:var(--row-alt); }}
table.ledger tbody tr.is-today {{ background:var(--row-today) !important; }}
table.ledger tbody tr.is-today td:first-child {{ border-left:3px solid var(--orange); }}

.col-status {{ width:120px; white-space:nowrap; }}
.col-reqid {{ width:120px; white-space:nowrap; font-family:'Consolas',monospace; }}
.col-title {{ min-width:240px; max-width:340px; font-weight:600; color:var(--text-std); }}
.col-buyer {{ min-width:180px; max-width:240px; color:var(--text-muted); font-size:12px; }}
.col-vehicle {{ width:155px; white-space:nowrap; }}
.vehicle-name {{ font-family:Calibri,Arial,sans-serif; font-weight:700; font-size:12px; color:var(--navy); line-height:1.2; }}
[data-theme="dark"] .vehicle-name {{ color:#e2e2e2; }}
.vehicle-code {{ font-family:'Consolas',monospace; font-size:10px; color:var(--text-muted); display:inline-block; margin-top:2px; }}
.col-posted {{ width:160px; white-space:nowrap; color:var(--text-muted); font-size:12px; }}
.col-due {{ width:180px; white-space:nowrap; }}
.col-action {{ width:180px; min-width:180px; white-space:nowrap; text-align:right; padding-right:14px !important; }}

.status-badge {{
  display:inline-block; font-family:system-ui,sans-serif;
  font-size:10px; font-weight:700;
  text-transform:uppercase; letter-spacing:0.04em;
  padding:3px 8px; border-radius:3px; white-space:nowrap;
}}

.due-pill {{
  display:inline-block; font-family:system-ui,sans-serif;
  font-size:11px; font-weight:700; margin-top:3px;
  padding:1px 7px; border-radius:8px; color:#fff;
}}
.due-urgent {{ background:var(--red); }}
.due-soon {{ background:var(--orange); }}
.due-ok {{ background:var(--green); }}
.due-past {{ background:var(--text-faint); }}

.btn-request {{
  display:inline-block; font-family:system-ui,sans-serif;
  background:var(--teal); color:#fff !important;
  text-decoration:none; padding:6px 10px;
  font-size:10.5px; font-weight:700; border-radius:4px;
  border:1px solid var(--teal);
  white-space:nowrap; transition:background 0.15s;
  letter-spacing:0.02em;
}}
.btn-request:hover {{ background:#006b6b; }}
[data-theme="dark"] .btn-request {{ background:#0a9999; border-color:#0a9999; }}

code {{
  font-family:'Consolas','Menlo',monospace;
  background:rgba(0,0,0,0.04); padding:1px 5px; border-radius:3px;
  font-size:12px;
}}
[data-theme="dark"] code {{ background:rgba(255,255,255,0.08); }}

.empty-state {{ text-align:center; padding:20px; color:var(--text-muted); font-style:italic; }}

footer {{
  margin:32px 0 16px; padding:14px 0;
  border-top:1px solid var(--border);
  text-align:center;
  font-family:Calibri,Arial,sans-serif; font-size:11px;
  color:var(--text-faint); font-style:italic;
}}

/* Context panel */
.context-panel {{
  background:var(--surface-alt); border:1px solid var(--border);
  border-radius:8px; padding:14px 18px; margin-top:24px;
  font-family:system-ui,sans-serif; font-size:12px;
}}
.context-panel h3 {{
  font-family:Calibri,Arial,sans-serif; font-size:13px;
  color:var(--navy); margin-bottom:8px;
  text-transform:uppercase; letter-spacing:0.06em;
}}
[data-theme="dark"] .context-panel h3 {{ color:#e2e2e2; }}
.context-panel dt {{ font-weight:700; color:var(--text-std); display:inline-block; min-width:160px; }}
.context-panel dl {{ margin-top:4px; }}
.context-panel dd {{ display:inline; color:var(--text-muted); }}
.context-panel dl > div {{ margin-bottom:3px; }}
</style>
</head>
<body>
<div class="topbar">
  <div class="topbar-left">
    <span class="topbar-dot">●</span>
    <span>Changeis eBuy Ledger</span>
    <span style="opacity:0.7;">· {range_label}</span>
  </div>
  <button class="theme-toggle" onclick="toggleTheme()">Toggle theme</button>
</div>

<div class="container">

<div class="hero">
  <div class="hero-badge">VM2 · eBuy Notification Capture</div>
  <h1>GSA eBuy Consolidated Notice Ledger</h1>
  <div class="hero-sub">Notification capture from <code>ebuy_admin@gsa.gov</code> · varun@changeis.com (Outlook)</div>
  <div class="hero-date">Generated {gen_time} · Backfill window: {range_label}</div>
</div>

<div class="section">
  <div class="section-header">Snapshot</div>
  <div class="dash-row">
    <div class="stat-card"><div class="stat-num">{total}</div><div class="stat-label">Total Events</div></div>
    <div class="stat-card"><div class="stat-num">{unique_reqs}</div><div class="stat-label">Unique Requests</div></div>
    <div class="stat-card"><div class="stat-num">{len(today_events)}</div><div class="stat-label">Today</div></div>
    <div class="stat-card"><div class="stat-num">{len(last24h_events)}</div><div class="stat-label">Last 24h</div></div>
  </div>
  <div class="callout">
    <strong>How this works:</strong> Every consolidated notice from <code>ebuy_admin@gsa.gov</code> is captured here as a separate event. Each amendment, Q&amp;A, and status change is recorded as its own row — nothing is overwritten. The actual solicitation materials live behind the GSA eBuy password wall, so use the <strong>Request Analyst Download</strong> button on any row to draft an email asking the analyst to log in and download the package.
    <br><br>
    <strong>Analyst email:</strong> currently a placeholder (<code>{ANALYST_EMAIL_PLACEHOLDER}</code>) — provide the real address when ready and the buttons will be regenerated.
  </div>
</div>

<div class="section">
  <div class="section-header">Today's Review ({TODAY.strftime('%b %d, %Y')})</div>
  <div class="table-wrap" style="max-height:none;">
    <table class="ledger">
      <thead>
        <tr>
          <th>Status</th>
          <th>Request ID</th>
          <th>Title</th>
          <th>Buyer</th>
          <th>Vehicle</th>
          <th>Posted</th>
          <th>Due By</th>
          <th></th>
        </tr>
      </thead>
      <tbody>{today_rows}</tbody>
    </table>
  </div>
</div>

<div class="section">
  <div class="section-header">Full Ledger ({total} events)</div>
  <div class="controls">
    <input type="text" id="search" placeholder="Search title, request ID, buyer…">
    <label>Status:</label>
    <select id="filter-status"><option value="">All</option>{status_filter_opts}</select>
    <label>Vehicle:</label>
    <select id="filter-vehicle"><option value="">All</option>{vehicle_filter_opts}</select>
    <button class="filter-clear" onclick="clearFilters()">Clear</button>
    <span id="row-count" style="margin-left:auto; color:var(--text-muted); font-size:12px;"></span>
  </div>
  <div class="table-wrap">
    <table class="ledger" id="full-table">
      <thead>
        <tr>
          <th data-sort="status">Status<span class="sort-arrow">↕</span></th>
          <th data-sort="reqid">Request ID<span class="sort-arrow">↕</span></th>
          <th data-sort="title">Title<span class="sort-arrow">↕</span></th>
          <th data-sort="buyer">Buyer<span class="sort-arrow">↕</span></th>
          <th data-sort="vehicle">Vehicle<span class="sort-arrow">↕</span></th>
          <th data-sort="posted">Posted<span class="sort-arrow">↕</span></th>
          <th data-sort="due">Due By<span class="sort-arrow">↕</span></th>
          <th></th>
        </tr>
      </thead>
      <tbody>{full_rows}</tbody>
    </table>
  </div>
</div>

<div class="context-panel">
  <h3>Session Context</h3>
  <dl>
    <div><dt>Deliverable:</dt> <dd>eBuy Ledger (v1.0 backfill)</dd></div>
    <div><dt>Source mailbox:</dt> <dd>varun@changeis.com · Outlook</dd></div>
    <div><dt>Source sender:</dt> <dd>ebuy_admin@gsa.gov</dd></div>
    <div><dt>History file:</dt> <dd><code>cron_tracking/ebuy_monitor/ebuy_history.jsonl</code></dd></div>
    <div><dt>Dedupe key:</dt> <dd>sha1(request_id + status + posted_date)</dd></div>
    <div><dt>Cron cadence:</dt> <dd>Weekdays 9 AM &amp; 4 PM ET · Weekends 12 PM ET · Weekly reconciliation Sun 8 PM ET</dd></div>
    <div><dt>Analyst email:</dt> <dd><code>{ANALYST_EMAIL_PLACEHOLDER}</code> — placeholder pending</dd></div>
  </dl>
</div>

<script type="application/json" id="vm2-context-data">
{context_json}
</script>

<footer>
  Changeis Confidential — VM2 eBuy Ledger — Generated {gen_time}
</footer>

</div>

<script>
function toggleTheme() {{
  const cur = document.documentElement.getAttribute('data-theme');
  const next = (cur === 'dark') ? 'light' : 'dark';
  document.documentElement.setAttribute('data-theme', next);
  try {{ localStorage.setItem('vm2-theme', next); }} catch(e) {{}}
}}
(function() {{
  try {{
    const saved = localStorage.getItem('vm2-theme');
    if (saved) document.documentElement.setAttribute('data-theme', saved);
  }} catch(e) {{}}
}})();

const tbody = document.querySelector('#full-table tbody');
const allRows = Array.from(tbody.querySelectorAll('tr.row'));
const searchEl = document.getElementById('search');
const statusEl = document.getElementById('filter-status');
const vehicleEl = document.getElementById('filter-vehicle');
const rowCountEl = document.getElementById('row-count');

function applyFilters() {{
  const q = (searchEl.value || '').toLowerCase().trim();
  const st = statusEl.value;
  const ve = vehicleEl.value;
  let shown = 0;
  allRows.forEach(r => {{
    const reqid = (r.dataset.reqid || '').toLowerCase();
    const title = (r.dataset.title || '').toLowerCase();
    const buyer = (r.dataset.buyer || '').toLowerCase();
    let match = true;
    if (q && !(reqid.includes(q) || title.includes(q) || buyer.includes(q))) match = false;
    if (st && r.dataset.status !== st) match = false;
    if (ve && r.dataset.vehicle !== ve) match = false;
    r.style.display = match ? '' : 'none';
    if (match) shown++;
  }});
  rowCountEl.textContent = `Showing ${{shown}} of ${{allRows.length}}`;
}}
searchEl.addEventListener('input', applyFilters);
statusEl.addEventListener('change', applyFilters);
vehicleEl.addEventListener('change', applyFilters);
function clearFilters() {{
  searchEl.value = ''; statusEl.value = ''; vehicleEl.value = '';
  applyFilters();
}}
applyFilters();

// Sorting
let sortState = {{ col: 'posted', dir: -1 }};
document.querySelectorAll('#full-table thead th[data-sort]').forEach(th => {{
  th.addEventListener('click', () => {{
    const col = th.dataset.sort;
    if (sortState.col === col) sortState.dir = -sortState.dir;
    else {{ sortState.col = col; sortState.dir = 1; }}
    const rows = Array.from(tbody.querySelectorAll('tr.row'));
    rows.sort((a, b) => {{
      let av, bv;
      if (col === 'posted' || col === 'due') {{
        av = a.dataset[col] || ''; bv = b.dataset[col] || '';
      }} else {{
        av = (a.dataset[col] || '').toLowerCase();
        bv = (b.dataset[col] || '').toLowerCase();
      }}
      if (av < bv) return -1 * sortState.dir;
      if (av > bv) return 1 * sortState.dir;
      return 0;
    }});
    rows.forEach(r => tbody.appendChild(r));
  }});
}});
</script>

</body>
</html>
"""

    OUTPUT_PATH.write_text(html_out, encoding='utf-8')
    print(f'Wrote {OUTPUT_PATH} ({OUTPUT_PATH.stat().st_size:,} bytes)')
    print(f'Events: {total} · Unique: {unique_reqs} · Today: {len(today_events)} · 24h: {len(last24h_events)}')

if __name__ == '__main__':
    main()
