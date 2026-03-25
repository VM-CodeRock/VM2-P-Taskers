#!/usr/bin/env python3
"""
Generate Changeis Daily BD Brief HTML with Todoist 'Request Deep Dive' buttons.
Reads APFS and SAM.gov RAG results, builds branded HTML email.
"""
import json
import os
from datetime import datetime, timezone
from urllib.parse import quote

# ── Paths ──
APFS_RAG = "/home/user/workspace/cron_tracking/f7adf3cd/apfs_rag_results.json"
SAM_RAG = "/home/user/workspace/cron_tracking/30af1ae5/sam_rag_results.json"
APFS_NAICS = "/home/user/workspace/cron_tracking/f7adf3cd/apfs_naics_validation.json"
SAM_NAICS = "/home/user/workspace/cron_tracking/30af1ae5/sam_naics_validation.json"
OUTPUT_HTML = "/home/user/workspace/cron_tracking/daily_email.html"

# ── Changeis Brand Colors ──
NAVY = "#1B2A4A"
DEEP_NAVY = "#002060"
DARK_GRAY = "#333333"
SECTION_BLUE = "#1F4D78"
TEAL = "#008B8B"
GREEN = "#2D7D4A"
ORANGE = "#D97D2A"
PURPLE = "#6B4C9A"
ALT_ROW_LIGHT = "#F2F6FA"
CALLOUT_BG = "#E8F4F8"

# ── NAICS Code Descriptions ──
NAICS_DESCRIPTIONS = {
    "541110": "Offices of Lawyers",
    "541120": "Offices of Notaries",
    "541191": "Title Abstract & Settlement Offices",
    "541199": "Other Legal Services",
    "541211": "Offices of CPAs",
    "541213": "Tax Preparation Services",
    "541214": "Payroll Services",
    "541219": "Other Accounting Services",
    "541310": "Architectural Services",
    "541320": "Landscape Architectural Services",
    "541330": "Engineering Services",
    "541340": "Drafting Services",
    "541350": "Building Inspection Services",
    "541360": "Geophysical Surveying & Mapping",
    "541370": "Surveying & Mapping Services",
    "541380": "Testing Laboratories",
    "541410": "Interior Design Services",
    "541420": "Industrial Design Services",
    "541430": "Graphic Design Services",
    "541490": "Other Specialized Design Services",
    "541511": "Custom Computer Programming",
    "541512": "Computer Systems Design Services",
    "541513": "Computer Facilities Management",
    "541519": "Other Computer Related Services",
    "541611": "Admin Management Consulting",
    "541612": "Human Resources Consulting",
    "541613": "Marketing Consulting",
    "541614": "Process/Physical Distribution Consulting",
    "541618": "Other Management Consulting",
    "541620": "Environmental Consulting",
    "541690": "Other Scientific & Technical Consulting",
    "541710": "R&D in Physical/Engineering/Life Sciences",
    "541715": "R&D in Physical/Engineering Sciences (excl. Nanotech)",
    "541720": "R&D in Social Sciences & Humanities",
    "541810": "Advertising Agencies",
    "541820": "Public Relations Agencies",
    "541830": "Media Buying Agencies",
    "541840": "Media Representatives",
    "541850": "Outdoor Advertising",
    "541860": "Direct Mail Advertising",
    "541870": "Advertising Material Distribution",
    "541890": "Other Services Related to Advertising",
    "541910": "Marketing Research & Public Opinion Polling",
    "541921": "Photography Studios",
    "541922": "Commercial Photography",
    "541930": "Translation & Interpretation Services",
    "541940": "Veterinary Services",
    "541990": "All Other Professional/Scientific/Technical Services",
}


def load_json(path):
    """Load JSON file, return None if missing or error."""
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return None


def todoist_url(title):
    """Build a Todoist Quick Add URL that pre-fills title + @vm2-opp label."""
    content = f"{title} @vm2-opp"
    return f"https://todoist.com/add?content={quote(content)}"


def todoist_button_html(title):
    """Generate the Todoist 'Request Deep Dive' button HTML."""
    url = todoist_url(title)
    return f'''<a href="{url}" target="_blank" rel="noopener" style="display:inline-flex;align-items:center;gap:6px;margin-top:10px;padding:8px 16px;background:{TEAL};color:#fff;font-weight:700;font-size:12px;letter-spacing:.4px;text-transform:uppercase;text-decoration:none;border-radius:6px;white-space:nowrap">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="16"/><line x1="8" y1="12" x2="16" y2="12"/></svg>
        Request Deep Dive
      </a>'''


def opp_link(opp, source):
    """Get the opportunity link."""
    if source == "SAM.gov":
        return opp.get("sam_link", "")
    return ""


def opp_title(opp):
    """Get opportunity title."""
    return opp.get("title", "(Untitled)") or "(Untitled)"


def opp_agency(opp, source):
    """Get agency/org."""
    if source == "APFS":
        return opp.get("organization", "—")
    return opp.get("agency", "—")


def opp_naics(opp):
    """Get NAICS code."""
    if "naics_code" in opp:
        return opp["naics_code"]
    return opp.get("naics", "—")


def opp_value(opp, source):
    """Get dollar range or value info."""
    if source == "APFS":
        dr = opp.get("dollar_range")
        if isinstance(dr, dict):
            return dr.get("display_name", "—")
        return dr or "—"
    return "—"


def opp_dates_html(opp, source):
    """Build key dates HTML."""
    parts = []
    if source == "APFS":
        if opp.get("published_date"):
            parts.append(f"Published: {opp['published_date']}")
        if opp.get("est_solicitation_release"):
            parts.append(f"Est. solicitation: {opp['est_solicitation_release']}")
    else:
        if opp.get("posted_date"):
            parts.append(f"Posted: {opp['posted_date']}")
        if opp.get("modified_date"):
            parts.append(f"Modified: {opp['modified_date']}")
        if opp.get("response_deadline"):
            parts.append(f"Response deadline: {opp['response_deadline']}")
    return "<br/>".join(parts) if parts else "—"


def opp_identifier(opp, source):
    """Get the solicitation/APFS number."""
    if source == "APFS":
        return opp.get("apfs_number", "")
    return opp.get("solicitation_number", "")


def best_match_html(opp):
    """Build best matching past performance HTML."""
    matches = opp.get("rag_matches", [])
    if not matches:
        return "<i>(No past performance match data)</i>"
    m = matches[0]
    to = m.get("task_order", "—")
    ec = m.get("end_client", "—")
    sc = m.get("composite_score", 0)
    excerpt = m.get("excerpt_summary", "")
    html = f"<b>{to}</b> at {ec} ({sc:.2f})"
    if excerpt and excerpt.strip():
        html += f"<br/><i style='color:#666;font-size:12px'>{excerpt[:200]}</i>"
    else:
        html += "<br/><i style='color:#999;font-size:12px'>(No excerpt available)</i>"
    return html


def render_card(opp, source, tier_color):
    """Render an opportunity card."""
    title = opp_title(opp)
    link = opp_link(opp, source)
    agency = opp_agency(opp, source)
    naics = opp_naics(opp)
    value = opp_value(opp, source)
    score = opp.get("rag_top_score", 0)
    tier = opp.get("rag_tier", "LOW")
    change = opp.get("change_type", "—")
    ident = opp_identifier(opp, source)

    # Source badge color
    src_bg = SECTION_BLUE if source == "SAM.gov" else PURPLE

    # Title with link
    if link:
        title_html = f"<a href='{link}' style='color:{DEEP_NAVY};text-decoration:none' target='_blank'><b>{title}</b></a>"
    else:
        title_html = f"<b>{title}</b>"

    return f'''
    <div style="border:1px solid #D8E2EE;border-left:6px solid {tier_color};border-radius:10px;padding:14px 16px;margin:12px 0;background:#fff;box-shadow:0 1px 2px rgba(0,0,0,.04)">
      <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap">
        <span style='display:inline-block;background:{src_bg};color:#fff;font-weight:700;font-size:11px;letter-spacing:.3px;padding:4px 8px;border-radius:999px'>{source}</span>
        <span style='display:inline-block;background:{tier_color};color:#fff;font-weight:700;font-size:11px;letter-spacing:.3px;padding:4px 8px;border-radius:999px'>{tier}</span>
        <span style="color:#6b778c;font-size:12px">{change}</span>
        {f"<span style='color:#999;font-size:11px;margin-left:auto'>{ident}</span>" if ident else ""}
      </div>
      <div style="margin-top:10px;font-size:16px;color:{DEEP_NAVY};line-height:1.25">{title_html}</div>
      <div style="margin-top:6px;color:{DARK_GRAY};font-size:13px"><b>Agency/Org:</b> {agency} &nbsp; | &nbsp; <b>NAICS:</b> {naics}</div>
      <div style='margin-top:6px;color:{DARK_GRAY};font-size:13px'><b>Value/Set-aside:</b> {value}</div>
      <div style="margin-top:6px;color:{DARK_GRAY};font-size:13px"><b>RAG Score:</b> {score:.2f} — {tier}</div>
      <div style="margin-top:6px;color:{DARK_GRAY};font-size:13px"><b>Best matching past performance:</b> {best_match_html(opp)}</div>
      <div style="margin-top:10px;color:{DARK_GRAY};font-size:13px"><b>Key dates:</b><br/>{opp_dates_html(opp, source)}</div>
      {todoist_button_html(title)}
    </div>
    '''


def render_low_table(opps_with_source):
    """Render LOW-tier opportunities as a compact table."""
    if not opps_with_source:
        return "<div style='color:#999;font-size:13px;padding:8px'>No LOW-tier matches.</div>"

    rows = ""
    for i, (opp, source) in enumerate(opps_with_source):
        bg = ALT_ROW_LIGHT if i % 2 == 0 else "#fff"
        title = opp_title(opp)
        agency = opp_agency(opp, source)
        naics = opp_naics(opp)
        score = opp.get("rag_top_score", 0)
        rows += f'''<tr style="background:{bg}">
          <td style="padding:6px 8px;font-size:12px;color:{SECTION_BLUE};font-weight:600">{source}</td>
          <td style="padding:6px 8px;font-size:12px">{title[:60]}{'...' if len(title)>60 else ''}</td>
          <td style="padding:6px 8px;font-size:12px">{agency[:30]}</td>
          <td style="padding:6px 8px;font-size:12px">{naics}</td>
          <td style="padding:6px 8px;font-size:12px;text-align:center">{score:.2f}</td>
        </tr>'''

    return f'''
    <table style="width:100%;border-collapse:collapse;margin:10px 0;font-size:13px">
      <thead>
        <tr style="background:{NAVY};color:#fff">
          <th style="padding:8px;text-align:left;font-size:11px;letter-spacing:.3px">SOURCE</th>
          <th style="padding:8px;text-align:left;font-size:11px;letter-spacing:.3px">TITLE</th>
          <th style="padding:8px;text-align:left;font-size:11px;letter-spacing:.3px">AGENCY</th>
          <th style="padding:8px;text-align:left;font-size:11px;letter-spacing:.3px">NAICS</th>
          <th style="padding:8px;text-align:center;font-size:11px;letter-spacing:.3px">SCORE</th>
        </tr>
      </thead>
      <tbody>{rows}</tbody>
    </table>
    '''


def render_naics_dashboard(apfs_naics, sam_naics):
    """Render the NAICS validation dashboard."""
    merged = {}
    for data in [apfs_naics, sam_naics]:
        if not data or "naics_scores" not in data:
            continue
        for code, stats in data["naics_scores"].items():
            if code not in merged:
                merged[code] = {"count": 0, "total_score": 0, "max_score": 0, "tiers": {}}
            merged[code]["count"] += stats.get("count", 0)
            merged[code]["total_score"] += stats.get("avg_score", 0) * stats.get("count", 0)
            merged[code]["max_score"] = max(merged[code]["max_score"], stats.get("max_score", 0))
            for tier, cnt in stats.get("tier_distribution", {}).items():
                merged[code]["tiers"][tier] = merged[code]["tiers"].get(tier, 0) + cnt

    if not merged:
        return "<div style='color:#999;font-size:13px;padding:8px'>No NAICS validation data available.</div>"

    rows = ""
    for i, (code, m) in enumerate(sorted(merged.items(), key=lambda x: -x[1]["max_score"])):
        bg = ALT_ROW_LIGHT if i % 2 == 0 else "#fff"
        avg = m["total_score"] / m["count"] if m["count"] > 0 else 0
        desc = NAICS_DESCRIPTIONS.get(code, "—")
        if avg >= 0.50 or m["max_score"] >= 0.65:
            rec = "RETAIN"
            rec_color = GREEN
        elif avg >= 0.30:
            rec = "MONITOR"
            rec_color = ORANGE
        else:
            rec = "REVIEW"
            rec_color = "#999"
        rows += f'''<tr style="background:{bg}">
          <td style="padding:6px 8px;font-size:12px;font-weight:600">{code}</td>
          <td style="padding:6px 8px;font-size:12px">{desc[:40]}</td>
          <td style="padding:6px 8px;font-size:12px;text-align:center">{m['count']}</td>
          <td style="padding:6px 8px;font-size:12px;text-align:center">{avg:.2f}</td>
          <td style="padding:6px 8px;font-size:12px;text-align:center">{m['max_score']:.2f}</td>
          <td style="padding:6px 8px;font-size:12px;text-align:center;color:{rec_color};font-weight:700">{rec}</td>
        </tr>'''

    return f'''
    <table style="width:100%;border-collapse:collapse;margin:10px 0;font-size:13px">
      <thead>
        <tr style="background:{NAVY};color:#fff">
          <th style="padding:8px;text-align:left;font-size:11px;letter-spacing:.3px">NAICS</th>
          <th style="padding:8px;text-align:left;font-size:11px;letter-spacing:.3px">DESCRIPTION</th>
          <th style="padding:8px;text-align:center;font-size:11px;letter-spacing:.3px">COUNT</th>
          <th style="padding:8px;text-align:center;font-size:11px;letter-spacing:.3px">AVG SCORE</th>
          <th style="padding:8px;text-align:center;font-size:11px;letter-spacing:.3px">MAX SCORE</th>
          <th style="padding:8px;text-align:center;font-size:11px;letter-spacing:.3px">REC</th>
        </tr>
      </thead>
      <tbody>{rows}</tbody>
    </table>
    '''


def main():
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    today_display = datetime.now(timezone.utc).strftime("%B %d, %Y")

    # Load data
    apfs = load_json(APFS_RAG)
    sam = load_json(SAM_RAG)
    apfs_naics = load_json(APFS_NAICS)
    sam_naics = load_json(SAM_NAICS)

    # Collect all opportunities with source label
    all_opps = []
    apfs_new = apfs_upd = sam_new = sam_upd = 0
    if apfs and "error" not in apfs:
        apfs_new = apfs.get("new_count", 0)
        apfs_upd = apfs.get("updated_count", 0)
        for o in apfs.get("opportunities", []):
            all_opps.append((o, "APFS"))
    if sam and "error" not in sam:
        sam_new = sam.get("new_count", 0)
        sam_upd = sam.get("updated_count", 0)
        for o in sam.get("opportunities", []):
            all_opps.append((o, "SAM.gov"))

    # Categorize by tier
    strong = [(o, s) for o, s in all_opps if o.get("rag_tier") == "STRONG"]
    moderate = [(o, s) for o, s in all_opps if o.get("rag_tier") == "MODERATE"]
    low = [(o, s) for o, s in all_opps if o.get("rag_tier") == "LOW"]

    # Sort each by score descending
    strong.sort(key=lambda x: -x[0].get("rag_top_score", 0))
    moderate.sort(key=lambda x: -x[0].get("rag_top_score", 0))
    low.sort(key=lambda x: -x[0].get("rag_top_score", 0))

    # ── Build HTML ──
    html = f'''
    <html>
    <head>
      <meta charset='utf-8' />
      <meta name='viewport' content='width=device-width, initial-scale=1' />
      <title>Changeis Daily BD Brief — {today_display}</title>
    </head>
    <body style='margin:0;background:#F6F8FB;font-family:-apple-system,BlinkMacSystemFont,Segoe UI,Roboto,Arial,sans-serif;color:{DARK_GRAY}'>
      <div style='background:{NAVY};color:#fff;padding:22px 20px'>
        <div style='max-width:980px;margin:0 auto'>
          <div style='font-size:22px;font-weight:900;letter-spacing:.2px'>Changeis Daily BD Brief</div>
          <div style='margin-top:6px;font-size:14px;opacity:.9'>{today_display}</div>
        </div>
      </div>

      <div style='max-width:980px;margin:0 auto;padding:18px 16px'>
        '''

    # ── Executive Summary ──
    html += f'''
    <div style='background:{CALLOUT_BG};border:1px solid #CFE6EF;border-radius:12px;padding:14px 16px;margin-top:16px'>
      <div style='display:flex;flex-wrap:wrap;gap:16px;justify-content:space-between'>
        <div style='min-width:240px'>
          <div style='font-weight:800;color:{DEEP_NAVY};margin-bottom:6px'>Executive Summary</div>
          <div style='color:{DARK_GRAY};font-size:13.5px'>
            <b>APFS:</b> {apfs_new} new, {apfs_upd} updated &nbsp; | &nbsp; <b>SAM.gov:</b> {sam_new} new, {sam_upd} updated
          </div>
          <div style='color:{DARK_GRAY};font-size:13.5px;margin-top:6px'>
            <b>Total STRONG matches:</b> {len(strong)} &nbsp; | &nbsp; <b>MODERATE:</b> {len(moderate)} &nbsp; | &nbsp; <b>LOW:</b> {len(low)}
          </div>
        </div>
        <div style='min-width:260px'>
          <div style='font-weight:800;color:{DEEP_NAVY};margin-bottom:6px'>Action</div>
          <div style='color:{DARK_GRAY};font-size:13.5px'>Click <b style="color:{TEAL}">Request Deep Dive</b> on any opportunity below to queue a full analysis brief via Todoist.</div>
        </div>
      </div>
    </div>
    '''

    # ── STRONG Matches ──
    html += f'''
        <div style='margin-top:22px'>
          <div style='border-left:6px solid {GREEN};padding:8px 12px;background:#fff;border-radius:10px'>
            <div style='font-size:18px;color:{DEEP_NAVY};font-weight:800'>STRONG Matches <span style="font-size:13px;color:{GREEN};font-weight:600">({len(strong)})</span></div>
          </div>
        </div>
        '''
    if strong:
        for opp, src in strong:
            html += render_card(opp, src, GREEN)
    else:
        html += "<div style='color:#999;font-size:13px;padding:12px'>No STRONG matches today.</div>"

    # ── MODERATE Matches ──
    html += f'''
        <div style='margin-top:22px'>
          <div style='border-left:6px solid {ORANGE};padding:8px 12px;background:#fff;border-radius:10px'>
            <div style='font-size:18px;color:{DEEP_NAVY};font-weight:800'>MODERATE Matches <span style="font-size:13px;color:{ORANGE};font-weight:600">({len(moderate)})</span></div>
          </div>
        </div>
        '''
    if moderate:
        for opp, src in moderate:
            html += render_card(opp, src, ORANGE)
    else:
        html += "<div style='color:#999;font-size:13px;padding:12px'>No MODERATE matches today.</div>"

    # ── LOW / Awareness ──
    html += f'''
        <div style='margin-top:22px'>
          <div style='border-left:6px solid #999;padding:8px 12px;background:#fff;border-radius:10px'>
            <div style='font-size:18px;color:{DEEP_NAVY};font-weight:800'>LOW / Awareness <span style="font-size:13px;color:#999;font-weight:600">({len(low)})</span></div>
          </div>
        </div>
        '''
    html += render_low_table(low)

    # ── NAICS Validation Dashboard ──
    html += f'''
        <div style='margin-top:22px'>
          <div style='border-left:6px solid {TEAL};padding:8px 12px;background:#fff;border-radius:10px'>
            <div style='font-size:18px;color:{DEEP_NAVY};font-weight:800'>NAICS Validation Dashboard</div>
          </div>
        </div>
        '''
    html += render_naics_dashboard(apfs_naics, sam_naics)

    # ── Footer ──
    html += f'''
      </div>

      <div style='background:{NAVY};color:#fff;padding:18px 20px;margin-top:24px;text-align:center;font-size:12px'>
        <div style='max-width:980px;margin:0 auto'>
          <div style='opacity:.85'>Changeis Confidential — Daily BD Brief — {datetime.now(timezone.utc).strftime("%B %Y")}</div>
          <div style='opacity:.65;margin-top:4px'>Powered by Changeis BD RAG Engine</div>
          <div style='margin-top:10px;opacity:.85'>
            To request a deep-dive analysis: click the <b>Request Deep Dive</b> button on any opportunity card above, or create a Todoist task with label <b>vm2-opp</b> and the opportunity title.
          </div>
        </div>
      </div>
    </body>
    </html>
    '''

    # Write output
    os.makedirs(os.path.dirname(OUTPUT_HTML), exist_ok=True)
    with open(OUTPUT_HTML, "w") as f:
        f.write(html)

    # Return summary for callers
    return {
        "date": today,
        "apfs_new": apfs_new,
        "apfs_updated": apfs_upd,
        "sam_new": sam_new,
        "sam_updated": sam_upd,
        "strong": len(strong),
        "moderate": len(moderate),
        "low": len(low),
        "total_opps": len(all_opps),
    }


if __name__ == "__main__":
    result = main()
    print(json.dumps(result, indent=2))
