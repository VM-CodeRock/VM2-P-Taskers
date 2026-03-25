#!/usr/bin/env python3
"""
Upgrade existing daily brief HTML files to use the new API-powered deep-dive buttons.

Replaces old todoist.com/add links with the new <button> elements that include
structured metadata data-* attributes and call the Todoist REST API directly.

Also adds the JS module and toast styles to the page.
"""

import re
import os
import sys
import json

REPO_DIR = '/home/user/workspace/VM2-P-Taskers'


def extract_metadata_from_card(card_html):
    """Extract opportunity metadata from an existing card's HTML."""
    metadata = {}
    
    # Title: inside <b> inside the title <a>
    title_match = re.search(r"<a href='(https://sam\.gov/[^']+)'[^>]*><b>([^<]+)</b></a>", card_html)
    if title_match:
        metadata['sam_url'] = title_match.group(1)
        metadata['title'] = title_match.group(2)
    
    # Agency
    agency_match = re.search(r'<b>Agency/Org:</b>\s*([^&<]+)', card_html)
    if agency_match:
        metadata['agency'] = agency_match.group(1).strip()
    
    # NAICS
    naics_match = re.search(r'<b>NAICS:</b>\s*(\d+)', card_html)
    if naics_match:
        metadata['naics'] = naics_match.group(1)
    
    # RAG Score
    rag_match = re.search(r'<b>RAG Score:</b>\s*([\d.]+)\s*—\s*(\w+)', card_html)
    if rag_match:
        metadata['rag_score'] = rag_match.group(1)
        metadata['rag_tier'] = rag_match.group(2)
    
    # Solicitation number (in the top-right corner span)
    sol_match = re.search(r"margin-left:auto'>([^<]+)</span>", card_html)
    if sol_match:
        metadata['solicitation_number'] = sol_match.group(1).strip()
    
    # Source badge
    if 'APFS' in card_html[:200]:
        metadata['source'] = 'APFS'
    else:
        metadata['source'] = 'SAM.gov'
    
    # Posted date
    posted_match = re.search(r'Posted:\s*(\d{4}-\d{2}-\d{2})', card_html)
    if posted_match:
        metadata['posted_date'] = posted_match.group(1)
    
    # Response deadline
    deadline_match = re.search(r'Response deadline:\s*(\d{4}-\d{2}-\d{2})', card_html)
    if deadline_match:
        metadata['response_deadline'] = deadline_match.group(1)
    
    # Best match
    match_match = re.search(r'<b>Best matching past performance:</b>\s*<b>([^<]+)</b>\s*at\s*([^(]+)\(([^)]+)\)', card_html)
    if match_match:
        metadata['best_match'] = f"{match_match.group(1)} at {match_match.group(2).strip()} ({match_match.group(3)})"
    
    # Value range (APFS)
    value_match = re.search(r'<b>Value/Set-aside:</b>\s*([^<]+)', card_html)
    if value_match:
        val = value_match.group(1).strip()
        if val and val != '—':
            metadata['value_range'] = val
    
    return metadata


def generate_new_button(metadata):
    """Generate the new API-powered button HTML."""
    import html as html_module
    
    def esc(val):
        return html_module.escape(str(val)) if val else ''
    
    title = metadata.get('title', '')
    sol_num = metadata.get('solicitation_number', '')
    
    data_attrs = ' '.join([
        f'data-title="{esc(title)}"',
        f'data-sol-num="{esc(sol_num)}"',
        f'data-notice-id="{esc(metadata.get("notice_id", ""))}"',
        f'data-agency="{esc(metadata.get("agency", ""))}"',
        f'data-naics="{esc(metadata.get("naics", ""))}"',
        f'data-rag-score="{esc(metadata.get("rag_score", ""))}"',
        f'data-sam-url="{esc(metadata.get("sam_url", ""))}"',
        f'data-source="{esc(metadata.get("source", "SAM.gov"))}"',
        f'data-posted-date="{esc(metadata.get("posted_date", ""))}"',
        f'data-response-deadline="{esc(metadata.get("response_deadline", ""))}"',
        f'data-best-match="{esc(metadata.get("best_match", ""))}"',
        f'data-value-range="{esc(metadata.get("value_range", ""))}"',
    ])
    
    task_title = f"{title} — {sol_num}" if sol_num else title
    import urllib.parse
    fallback_url = 'https://todoist.com/add?content=' + urllib.parse.quote(task_title + ' @vm2-opp')
    
    icon_svg = (
        '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
        'stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">'
        '<circle cx="12" cy="12" r="10"/>'
        '<line x1="12" y1="8" x2="12" y2="16"/>'
        '<line x1="8" y1="12" x2="16" y2="12"/>'
        '</svg>'
    )
    
    return (
        f'<button class="vm2-deep-dive-btn" '
        f'style="display:inline-flex;align-items:center;gap:6px;margin-top:10px;'
        f'padding:8px 16px;background:#008B8B;color:#fff;font-weight:700;'
        f'font-size:12px;letter-spacing:.4px;text-transform:uppercase;'
        f'text-decoration:none;border-radius:6px;white-space:nowrap;'
        f'cursor:pointer;border:none;font-family:system-ui,sans-serif;'
        f'transition:background .2s,transform .1s" '
        f'{data_attrs} '
        f'data-fallback-url="{esc(fallback_url)}" '
        f'onmouseover="this.style.background=\'#006E6E\';this.style.transform=\'translateY(-1px)\'" '
        f'onmouseout="this.style.background=this.dataset.queued?\'#2D7D4A\':\'#008B8B\';this.style.transform=\'none\'">'
        f'\n        {icon_svg}\n        Request Deep Dive\n      </button>'
    )


def get_js_module():
    """Read the deep-dive-button.js module."""
    js_path = os.path.join(os.path.dirname(__file__), 'deep-dive-button.js')
    with open(js_path, 'r') as f:
        return f.read()


def upgrade_daily_brief(filepath, todoist_token=''):
    """Upgrade a daily brief HTML file with new buttons and JS module."""
    with open(filepath, 'r') as f:
        content = f.read()
    
    # Find all old button/link patterns (the todoist.com/add links)
    old_button_pattern = re.compile(
        r'<a href="https://todoist\.com/add\?content=[^"]*"[^>]*>[\s\S]*?Request Deep Dive[\s\S]*?</a>',
        re.MULTILINE
    )
    
    # Find each old button and its surrounding card context to extract metadata
    matches = list(old_button_pattern.finditer(content))
    
    if not matches:
        print(f"  No old buttons found in {os.path.basename(filepath)}")
        return False
    
    print(f"  Found {len(matches)} buttons to upgrade in {os.path.basename(filepath)}")
    
    # Process in reverse to maintain positions
    for match in reversed(matches):
        # Get the card context (everything from the previous card start to after this button)
        card_start = content.rfind('<div style="border:1px solid', 0, match.start())
        if card_start == -1:
            card_start = max(0, match.start() - 2000)
        card_html = content[card_start:match.end()]
        
        # Extract metadata from the card
        metadata = extract_metadata_from_card(card_html)
        
        if metadata.get('title'):
            new_button = generate_new_button(metadata)
            content = content[:match.start()] + new_button + content[match.end():]
    
    # Add the JS module and styles before </body>
    js_block = f'''
    <style>
      @keyframes vm2SlideIn {{
        from {{ transform: translateY(20px); opacity: 0; }}
        to {{ transform: translateY(0); opacity: 1; }}
      }}
      .vm2-deep-dive-btn:active {{ transform: scale(0.97) !important; }}
    </style>
    <script>
    window.__VM2_TODOIST_TOKEN = '{todoist_token}';
    </script>
    <script>
    {get_js_module()}
    </script>
'''
    
    # Insert before </body>
    if '</body>' in content and 'vm2-deep-dive-btn' not in content.split('</body>')[0].split('<script>')[-1] if '<script>' in content else True:
        # Remove any existing script blocks we might have added
        content = re.sub(r'\n\s*<style>\s*@keyframes vm2SlideIn[\s\S]*?</script>\s*\n', '\n', content)
        content = content.replace('</body>', js_block + '\n    </body>')
    
    with open(filepath, 'w') as f:
        f.write(content)
    
    print(f"  Upgraded {os.path.basename(filepath)} — {len(matches)} buttons replaced")
    return True


if __name__ == '__main__':
    token = sys.argv[1] if len(sys.argv) > 1 else os.environ.get('VM2_TODOIST_TOKEN', '')
    
    # Find all daily brief files
    briefs = sorted([
        f for f in os.listdir(REPO_DIR)
        if f.startswith('changeis-daily-brief-') and f.endswith('.html')
    ])
    
    if not briefs:
        print("No daily brief files found.")
        sys.exit(1)
    
    print(f"Found {len(briefs)} daily brief files to upgrade:")
    for brief in briefs:
        filepath = os.path.join(REPO_DIR, brief)
        upgrade_daily_brief(filepath, token)
    
    print("\nDone. All buttons upgraded to API-powered deep-dive system.")
