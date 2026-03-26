"""
VM2-OPP Button HTML Generator

Generates the HTML for a deep-dive button with embedded metadata.
Used by the daily brief cron and individual opportunity page generator.

Two modes:
  1. API mode (with Todoist token): Button calls API directly from browser
  2. Fallback mode: Button uses todoist.com/add quick-add link

The token is read from environment variable VM2_TODOIST_TOKEN.
"""

import json
import os
import urllib.parse
import html as html_module


def generate_button_html(opp, mode='api'):
    """
    Generate the deep-dive button HTML for an opportunity card.
    
    Args:
        opp: dict with keys: title, solicitation_number, notice_id, agency, naics,
             rag_score, sam_url, source, posted_date, response_deadline, best_match, value_range
        mode: 'api' for direct Todoist API calls, 'fallback' for todoist.com/add links
    
    Returns: HTML string for the button
    """
    title = opp.get('title', '')
    sol_num = opp.get('solicitation_number', '')
    
    # Escape for HTML attributes
    def esc(val):
        return html_module.escape(str(val)) if val else ''
    
    # Data attributes for the JS handler
    data_attrs = ' '.join([
        f'data-title="{esc(title)}"',
        f'data-sol-num="{esc(sol_num)}"',
        f'data-notice-id="{esc(opp.get("notice_id", ""))}"',
        f'data-agency="{esc(opp.get("agency", ""))}"',
        f'data-naics="{esc(opp.get("naics", ""))}"',
        f'data-rag-score="{esc(opp.get("rag_score", ""))}"',
        f'data-sam-url="{esc(opp.get("sam_url", ""))}"',
        f'data-source="{esc(opp.get("source", "SAM.gov"))}"',
        f'data-posted-date="{esc(opp.get("posted_date", ""))}"',
        f'data-response-deadline="{esc(opp.get("response_deadline", ""))}"',
        f'data-best-match="{esc(opp.get("best_match", ""))}"',
        f'data-value-range="{esc(opp.get("value_range", ""))}"',
    ])
    
    # Fallback URL (todoist.com/add)
    task_title = f"{title} — {sol_num}" if sol_num else title
    fallback_url = 'https://todoist.com/add?content=' + urllib.parse.quote(task_title + ' @vm2-opp')
    
    # Button styles
    btn_style = (
        'display:inline-flex;align-items:center;gap:6px;margin-top:10px;'
        'padding:8px 16px;background:#008B8B;color:#fff;font-weight:700;'
        'font-size:12px;letter-spacing:.4px;text-transform:uppercase;'
        'text-decoration:none;border-radius:6px;white-space:nowrap;'
        'cursor:pointer;border:none;font-family:system-ui,sans-serif;'
        'transition:background .2s,transform .1s;'
    )
    
    icon_svg = (
        '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
        'stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">'
        '<circle cx="12" cy="12" r="10"/>'
        '<line x1="12" y1="8" x2="12" y2="16"/>'
        '<line x1="8" y1="12" x2="16" y2="12"/>'
        '</svg>'
    )
    
    check_svg = (
        '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
        'stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">'
        '<path d="M20 6L9 17l-5-5"/>'
        '</svg>'
    )
    
    return f'''<button class="vm2-deep-dive-btn" style="{btn_style}" {data_attrs}
      data-fallback-url="{esc(fallback_url)}"
      onmouseover="this.style.background='#006E6E';this.style.transform='translateY(-1px)'"
      onmouseout="this.style.background=this.dataset.queued?'#2D7D4A':'#008B8B';this.style.transform='none'">
      {icon_svg}
      Request Deep Dive
    </button>'''


def generate_auto_dive_badge():
    """Badge shown on STRONG matches that were auto-queued."""
    return (
        '<span style="display:inline-flex;align-items:center;gap:4px;margin-left:8px;'
        'padding:3px 8px;background:#2D7D4A;color:#fff;font-size:10px;font-weight:700;'
        'letter-spacing:.3px;border-radius:999px;text-transform:uppercase">'
        '<svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
        'stroke-width="3" stroke-linecap="round" stroke-linejoin="round">'
        '<path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z"/></svg>'
        'Auto Deep Dive Queued'
        '</span>'
    )


def generate_deep_dive_ready_badge(deliverable_url):
    """Badge shown when a deep dive has been completed."""
    return (
        f'<a href="{html_module.escape(deliverable_url)}" target="_blank" '
        'style="display:inline-flex;align-items:center;gap:4px;margin-left:8px;'
        'padding:3px 8px;background:#1B2A4A;color:#fff;font-size:10px;font-weight:700;'
        'letter-spacing:.3px;border-radius:999px;text-transform:uppercase;text-decoration:none">'
        '<svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
        'stroke-width="3" stroke-linecap="round" stroke-linejoin="round">'
        '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>'
        '<polyline points="14 2 14 8 20 8"/></svg>'
        'Deep Dive Ready'
        '</a>'
    )


def generate_page_script(todoist_token=None):
    """Generate the <script> block to embed at the bottom of the page.
    
    Token resolution order:
    1. Explicit todoist_token argument
    2. VM2_TODOIST_TOKEN environment variable
    3. Empty string (falls back to todoist.com/add Quick Add links)
    """
    token = todoist_token or os.environ.get('VM2_TODOIST_TOKEN', '')
    return f'''
<script>
window.__VM2_TODOIST_TOKEN = '{token}';
</script>
<script>
{open(os.path.join(os.path.dirname(__file__), 'deep-dive-button.js')).read()}
</script>
'''


def generate_toast_styles():
    """CSS for toast notifications."""
    return '''
<style>
  @keyframes vm2SlideIn {
    from { transform: translateY(20px); opacity: 0; }
    to { transform: translateY(0); opacity: 1; }
  }
  .vm2-deep-dive-btn:active { transform: scale(0.97) !important; }
</style>
'''


if __name__ == '__main__':
    # Test
    test_opp = {
        'title': 'Logistical Support',
        'solicitation_number': 'bdc7112e',
        'agency': 'FEDERAL TRANSIT ADMINISTRATION',
        'naics': '541611',
        'rag_score': 0.70,
        'sam_url': 'https://sam.gov/opp/59b4c6430b1045968ce6b8c4eb172d83/view',
        'source': 'SAM.gov',
        'posted_date': '2026-03-24',
        'response_deadline': '2026-04-06',
        'best_match': 'V3272007 at DOT/FAA/FTA/Volpe (0.70)',
    }
    print(generate_button_html(test_opp))
    print()
    print(generate_auto_dive_badge())
