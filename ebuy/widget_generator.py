#!/usr/bin/env python3
"""Generate a compact 'Last 24h eBuy' widget snippet for embedding on portal.html."""
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path
from collections import Counter
import html as html_lib

HERE = Path(__file__).parent
HISTORY_PATH = HERE / 'ebuy_history.jsonl'
OUTPUT_PATH = HERE.parent / 'ebuy-portal-widget.html'

ET = timezone(timedelta(hours=-4))
NOW = datetime.now(ET)

def esc(s): return html_lib.escape(str(s or ''))

events = []
with HISTORY_PATH.open() as f:
    for ln in f:
        ln = ln.strip()
        if ln: events.append(json.loads(ln))

cutoff = NOW - timedelta(hours=24)
recent = []
for e in events:
    try:
        ed = datetime.fromisoformat(e['email_date'].replace('Z', '+00:00')).astimezone(ET)
        if ed >= cutoff:
            recent.append((ed, e))
    except Exception:
        pass
recent.sort(key=lambda t: t[0], reverse=True)

status_counts = Counter(e['status'] for _, e in recent)
total24 = len(recent)
new_ct = status_counts.get('NEW REQUEST', 0)
amend_ct = status_counts.get('AMENDED', 0)
qa_ct = status_counts.get('Q&A ADDED', 0)

rows = []
for ed, e in recent[:10]:
    when = ed.strftime('%b %d %I:%M %p ET')
    status = e['status']
    badge_color = {'NEW REQUEST':'#2D7D4A','AMENDED':'#D97D2A','Q&A ADDED':'#1F4D78'}.get(status,'#666666')
    rows.append(f"""
    <li class="ebuy-row">
      <span class="ebuy-badge" style="background:{badge_color};">{esc(status)}</span>
      <code class="ebuy-id">{esc(e['request_id'])}</code>
      <span class="ebuy-title">{esc(e.get('title') or '(not parsed)')}</span>
      <span class="ebuy-when">{esc(when)}</span>
    </li>""")
rows_html = ''.join(rows) if rows else '<li class="ebuy-empty">No notices in the last 24h.</li>'

snippet = f"""<!-- ============================================================ -->
<!-- BEGIN: eBuy Last-24h Widget (VM2 eBuy Ledger) -->
<!-- Drop this block into portal.html. Update by re-running          -->
<!-- /home/user/workspace/ebuy_widget_generator.py                    -->
<!-- ============================================================ -->
<style>
.ebuy-widget {{
  background:#FFFFFF; border:1px solid #D4D1CA; border-radius:8px;
  padding:16px 18px; margin:16px 0; font-family:Georgia, serif;
  box-shadow:0 1px 3px rgba(0,0,0,0.06);
}}
[data-theme="dark"] .ebuy-widget {{ background:#1a1d25; border-color:#333740; color:#d8d8d8; }}
.ebuy-widget-header {{
  display:flex; justify-content:space-between; align-items:center;
  font-family:Calibri,Arial,sans-serif; margin-bottom:10px;
}}
.ebuy-widget-title {{
  font-size:13px; font-weight:700; text-transform:uppercase;
  letter-spacing:0.08em; color:#1B2A4A;
}}
[data-theme="dark"] .ebuy-widget-title {{ color:#e2e2e2; }}
.ebuy-widget-link {{ font-size:12px; color:#0563C1; text-decoration:none; font-weight:600; }}
.ebuy-widget-link:hover {{ text-decoration:underline; }}
.ebuy-stats {{
  display:flex; gap:18px; font-family:system-ui,sans-serif;
  font-size:12px; color:#666666; margin-bottom:10px;
  padding-bottom:8px; border-bottom:1px solid #eee;
}}
.ebuy-stats strong {{ color:#1B2A4A; font-size:16px; font-weight:700; display:block; }}
[data-theme="dark"] .ebuy-stats strong {{ color:#e2e2e2; }}
.ebuy-list {{ list-style:none; padding:0; margin:0; }}
.ebuy-row {{
  display:flex; align-items:center; gap:10px;
  padding:6px 0; border-bottom:1px dotted #eee;
  font-family:system-ui,sans-serif; font-size:12.5px;
}}
.ebuy-row:last-child {{ border-bottom:none; }}
.ebuy-badge {{
  display:inline-block; color:#fff; font-size:9.5px;
  font-weight:700; text-transform:uppercase; letter-spacing:0.04em;
  padding:2px 6px; border-radius:3px; min-width:90px; text-align:center;
  white-space:nowrap;
}}
.ebuy-id {{
  font-family:'Consolas',monospace; font-size:11px;
  background:rgba(0,0,0,0.04); padding:1px 5px; border-radius:3px;
  white-space:nowrap;
}}
[data-theme="dark"] .ebuy-id {{ background:rgba(255,255,255,0.08); }}
.ebuy-title {{ flex:1; font-weight:600; color:#333; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }}
[data-theme="dark"] .ebuy-title {{ color:#ccc; }}
.ebuy-when {{ color:#888; font-size:11px; white-space:nowrap; }}
.ebuy-empty {{ color:#888; font-style:italic; padding:10px 0; }}
</style>

<section class="ebuy-widget" id="ebuy-widget">
  <div class="ebuy-widget-header">
    <div class="ebuy-widget-title">📋 eBuy · Last 24 Hours</div>
    <a class="ebuy-widget-link" href="ebuy-ledger.html">Open full ledger →</a>
  </div>
  <div class="ebuy-stats">
    <div><strong>{total24}</strong> Total</div>
    <div><strong>{new_ct}</strong> New Requests</div>
    <div><strong>{amend_ct}</strong> Amended</div>
    <div><strong>{qa_ct}</strong> Q&amp;A Added</div>
  </div>
  <ul class="ebuy-list">{rows_html}
  </ul>
</section>
<!-- END: eBuy Last-24h Widget -->
"""

OUTPUT_PATH.write_text(snippet, encoding='utf-8')
print(f'Wrote {OUTPUT_PATH} ({OUTPUT_PATH.stat().st_size:,} bytes)')
print(f'24h: {total24} total · {new_ct} new · {amend_ct} amended · {qa_ct} Q&A')
