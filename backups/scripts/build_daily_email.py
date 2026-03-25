import json, os, datetime, math
from collections import defaultdict

# Changeis brand colors
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

TODAY_UTC = datetime.datetime.utcnow().date()
DATE_STR = TODAY_UTC.strftime("%B %d, %Y")
DATE_YMD = TODAY_UTC.strftime("%Y-%m-%d")

APFS_PATH = "/home/user/workspace/cron_tracking/f7adf3cd/apfs_rag_results.json"
SAM_PATH = "/home/user/workspace/cron_tracking/30af1ae5/sam_rag_results.json"
APFS_NAICS_PATH = "/home/user/workspace/cron_tracking/f7adf3cd/apfs_naics_validation.json"
SAM_NAICS_PATH = "/home/user/workspace/cron_tracking/30af1ae5/sam_naics_validation.json"

OUT_HTML = "/home/user/workspace/cron_tracking/daily_email.html"
OUT_TEXT = "/home/user/workspace/cron_tracking/daily_email_plaintext.txt"

# Minimal NAICS descriptions for codes in our runs (can be extended)
NAICS_DESC = {
  "541511": "Custom Computer Programming Services",
  "541512": "Computer Systems Design Services",
  "541513": "Computer Facilities Management Services",
  "541519": "Other Computer Related Services",
  "541611": "Administrative Management and General Management Consulting Services",
  "541612": "Human Resources Consulting Services",
  "541613": "Marketing Consulting Services",
  "541614": "Process, Physical Distribution, and Logistics Consulting Services",
  "541618": "Other Management Consulting Services",
  "541715": "Research and Development in the Physical, Engineering, and Life Sciences",
  "541990": "All Other Professional, Scientific, and Technical Services",
}


def load_json(path):
    if not os.path.exists(path):
        return None, f"missing: {path}"
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f), None
    except Exception as e:
        return None, f"error reading {path}: {e}"


def is_fresh(run_date):
    try:
        d = datetime.date.fromisoformat(run_date)
        return d == TODAY_UTC
    except Exception:
        return False


def normalize_end_client(end_client):
    if isinstance(end_client, list):
        return "/".join([str(x) for x in end_client if x])
    if end_client is None:
        return ""
    return str(end_client)


def opp_to_common(source, opp):
    # returns a normalized dict
    if source == "APFS":
        title = (opp.get("title") or "").strip() or f"APFS Forecast {opp.get('apfs_number','').strip()}"
        agency = (opp.get("organization") or "Unknown").strip()
        naics_code = (opp.get("naics_code") or "").strip() or (opp.get("naics") or "").split("-")[0].strip()
        naics = naics_code
        naics_full = opp.get("naics")
        dollar = ""
        dr = opp.get("dollar_range")
        if isinstance(dr, dict):
            dollar = dr.get("display_name") or ""
        set_aside = ""
        release = opp.get("est_solicitation_release") or ""
        deadline = ""
        link = ""
        change_type = opp.get("change_type") or ""
    else:
        title = (opp.get("title") or "").strip() or f"SAM Opportunity {opp.get('solicitation_number','').strip()}"
        agency = (opp.get("agency") or "Unknown").strip()
        naics = (opp.get("naics") or "").strip()
        naics_code = naics
        naics_full = naics
        dollar = (opp.get("set_aside") or "")
        set_aside = (opp.get("set_aside") or "")
        release = opp.get("posted_date") or ""
        deadline = opp.get("response_deadline") or ""
        link = opp.get("sam_link") or ""
        change_type = opp.get("change_type") or ""

    rag_tier = (opp.get("rag_tier") or "LOW").strip().upper()
    score = float(opp.get("rag_top_score") or 0.0)

    matches = opp.get("rag_matches") or []
    best = matches[0] if matches else {}
    best_to = best.get("task_order") or ""
    best_client = normalize_end_client(best.get("end_client"))
    best_score = float(best.get("composite_score") or 0.0) if best else 0.0
    excerpt = (best.get("excerpt_summary") or opp.get("excerpt_summary") or "").strip()

    return {
        "source": source,
        "id": opp.get("apfs_number") if source=="APFS" else opp.get("solicitation_number"),
        "title": title,
        "agency": agency,
        "naics": naics_code,
        "naics_full": naics_full,
        "dollar_or_setaside": dollar or set_aside,
        "rag_tier": rag_tier,
        "score": score,
        "best_task_order": best_to,
        "best_end_client": best_client,
        "best_score": best_score,
        "excerpt": excerpt,
        "release_date": release,
        "deadline": deadline,
        "link": link,
        "change_type": change_type,
    }


def tier_color(tier):
    if tier == "STRONG":
        return GREEN
    if tier == "MODERATE":
        return ORANGE
    return "#666666"


def badge_html(text, bg):
    return f"<span style='display:inline-block;background:{bg};color:#fff;font-weight:700;font-size:11px;letter-spacing:.3px;padding:4px 8px;border-radius:999px'>{text}</span>"


def card_html(o, accent):
    dollar_line = f"<div style='margin-top:6px;color:{DARK_GRAY};font-size:13px'><b>Value/Set-aside:</b> {o['dollar_or_setaside'] or '—'}</div>"
    if o['source']=="SAM.gov" and o.get('link'):
        title_html = f"<a href='{o['link']}' style='color:{DEEP_NAVY};text-decoration:none'><b>{o['title']}</b></a>"
    else:
        title_html = f"<b>{o['title']}</b>"

    excerpt = o['excerpt'] or "(No excerpt available from match context.)"

    key_dates = []
    if o['release_date']:
        key_dates.append(f"Solicitation release/posted: {o['release_date']}")
    if o['deadline']:
        key_dates.append(f"Response deadline: {o['deadline']}")
    key_dates_html = "<br/>".join(key_dates) if key_dates else "—"

    return f"""
    <div style="border:1px solid #D8E2EE;border-left:6px solid {accent};border-radius:10px;padding:14px 16px;margin:12px 0;background:#fff;box-shadow:0 1px 2px rgba(0,0,0,.04)">
      <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap">
        {badge_html(o['source'], SECTION_BLUE if o['source']=="SAM.gov" else TEAL)}
        {badge_html(o['rag_tier'], accent)}
        <span style="color:#6b778c;font-size:12px">{o.get('change_type','')}</span>
      </div>
      <div style="margin-top:10px;font-size:16px;color:{DEEP_NAVY};line-height:1.25">{title_html}</div>
      <div style="margin-top:6px;color:{DARK_GRAY};font-size:13px"><b>Agency/Org:</b> {o['agency']} &nbsp; | &nbsp; <b>NAICS:</b> {o['naics'] or '—'}</div>
      {dollar_line}
      <div style="margin-top:6px;color:{DARK_GRAY};font-size:13px"><b>RAG Score:</b> {o['score']:.2f} — {o['rag_tier']}</div>
      <div style="margin-top:6px;color:{DARK_GRAY};font-size:13px"><b>Best matching past performance:</b> {o['best_task_order'] or '—'}{' at ' + o['best_end_client'] if o['best_end_client'] else ''} ({o['best_score']:.2f})</div>
      <div style="margin-top:8px;color:{DARK_GRAY};font-size:13px"><i>{excerpt}</i></div>
      <div style="margin-top:10px;color:{DARK_GRAY};font-size:13px"><b>Key dates:</b><br/>{key_dates_html}</div>
      <div style="margin-top:12px;background:{CALLOUT_BG};padding:10px 12px;border-radius:8px;color:{DARK_GRAY};font-size:12.5px">
        <b>Deep-dive instructions:</b> To request a deep dive, add a Todoist task with label <b>vm2-opp</b> and the opportunity title.
      </div>
    </div>
    """


def build_low_table(rows):
    header = f"""
    <table style="width:100%;border-collapse:collapse;font-size:13px">
      <thead>
        <tr style="background:{ALT_ROW_LIGHT};color:{DEEP_NAVY}">
          <th style="text-align:left;padding:10px;border-bottom:1px solid #D8E2EE">Source</th>
          <th style="text-align:left;padding:10px;border-bottom:1px solid #D8E2EE">Title</th>
          <th style="text-align:left;padding:10px;border-bottom:1px solid #D8E2EE">Agency</th>
          <th style="text-align:left;padding:10px;border-bottom:1px solid #D8E2EE">NAICS</th>
          <th style="text-align:right;padding:10px;border-bottom:1px solid #D8E2EE">Score</th>
          <th style="text-align:left;padding:10px;border-bottom:1px solid #D8E2EE">Tier</th>
        </tr>
      </thead>
      <tbody>
    """
    body = []
    for i,o in enumerate(rows):
        bg = "#fff" if i%2==0 else ALT_ROW_LIGHT
        title = o['title']
        if o['source']=="SAM.gov" and o.get('link'):
            title = f"<a href='{o['link']}' style='color:{DEEP_NAVY};text-decoration:none'>{o['title']}</a>"
        body.append(
            f"<tr style='background:{bg}'>"
            f"<td style='padding:10px;border-bottom:1px solid #E6EEF6'>{o['source']}</td>"
            f"<td style='padding:10px;border-bottom:1px solid #E6EEF6'>{title}</td>"
            f"<td style='padding:10px;border-bottom:1px solid #E6EEF6'>{o['agency']}</td>"
            f"<td style='padding:10px;border-bottom:1px solid #E6EEF6'>{o['naics'] or '—'}</td>"
            f"<td style='padding:10px;border-bottom:1px solid #E6EEF6;text-align:right'>{o['score']:.2f}</td>"
            f"<td style='padding:10px;border-bottom:1px solid #E6EEF6'>{o['rag_tier']}</td>"
            f"</tr>"
        )
    footer = "</tbody></table>"
    return header + "\n".join(body) + footer


def naics_dashboard(apfs_data, sam_data):
    # Build from opp lists, not from sam_naics_validation (which lacks scores)
    per = defaultdict(lambda: {"count":0, "sum":0.0, "max":0.0})
    for o in apfs_data + sam_data:
        code = (o.get("naics") or "").strip()
        if not code:
            continue
        per[code]["count"] += 1
        per[code]["sum"] += float(o.get("score") or 0.0)
        per[code]["max"] = max(per[code]["max"], float(o.get("score") or 0.0))

    rows = []
    for code,stats in per.items():
        avg = stats["sum"]/stats["count"] if stats["count"] else 0.0
        mx = stats["max"]
        if avg >= 0.50 or mx >= 0.65:
            rec = "RETAIN"
        elif 0.30 <= avg <= 0.49:
            rec = "MONITOR"
        else:
            rec = "REVIEW"
        rows.append((code, avg, mx, stats["count"], rec))

    rows.sort(key=lambda x: (-x[3], -x[2], -x[1], x[0]))

    html = [
        f"<table style='width:100%;border-collapse:collapse;font-size:13px'>",
        f"<thead><tr style='background:{ALT_ROW_LIGHT};color:{DEEP_NAVY}'>",
        "<th style='text-align:left;padding:10px;border-bottom:1px solid #D8E2EE'>NAICS Code</th>",
        "<th style='text-align:left;padding:10px;border-bottom:1px solid #D8E2EE'>Description</th>",
        "<th style='text-align:right;padding:10px;border-bottom:1px solid #D8E2EE'>Opportunity Count</th>",
        "<th style='text-align:right;padding:10px;border-bottom:1px solid #D8E2EE'>Avg RAG Score</th>",
        "<th style='text-align:right;padding:10px;border-bottom:1px solid #D8E2EE'>Max Score</th>",
        "<th style='text-align:left;padding:10px;border-bottom:1px solid #D8E2EE'>Recommendation</th>",
        "</tr></thead><tbody>"
    ]
    for i,(code,avg,mx,cnt,rec) in enumerate(rows):
        bg = "#fff" if i%2==0 else ALT_ROW_LIGHT
        html.append(
            f"<tr style='background:{bg}'>"
            f"<td style='padding:10px;border-bottom:1px solid #E6EEF6'>{code}</td>"
            f"<td style='padding:10px;border-bottom:1px solid #E6EEF6'>{NAICS_DESC.get(code,'')}</td>"
            f"<td style='padding:10px;border-bottom:1px solid #E6EEF6;text-align:right'>{cnt}</td>"
            f"<td style='padding:10px;border-bottom:1px solid #E6EEF6;text-align:right'>{avg:.2f}</td>"
            f"<td style='padding:10px;border-bottom:1px solid #E6EEF6;text-align:right'>{mx:.2f}</td>"
            f"<td style='padding:10px;border-bottom:1px solid #E6EEF6'>{rec}</td>"
            f"</tr>"
        )
    html.append("</tbody></table>")
    return "\n".join(html)


def build_plaintext(strong, moderate, low, apfs_new, apfs_upd, sam_new, sam_upd):
    def card(o, tier_label):
        title = o['title']
        agency = o['agency']
        naics = o['naics'] or '—'
        score = f"{o['score']:.2f}"
        best = f"{o['best_task_order'] or '—'} at {o['best_end_client'] or '—'} ({o['best_score']:.2f})"
        deadline = o['deadline'] or '—'
        src = o['source']
        return "\n".join([
            f"  ┌─ {title}",
            f"  │  Agency: {agency} | NAICS: {naics}",
            f"  │  Score: {score} — {tier_label}",
            f"  │  Best Match: {best}",
            f"  │  Deadline: {deadline}",
            f"  └─ Source: {src}",
        ])

    lines = []
    lines.append("CHANGEIS OPPORTUNITY INTELLIGENCE — DAILY BRIEF")
    lines.append(DATE_STR)
    lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    lines.append("")
    lines.append("EXECUTIVE SUMMARY")
    lines.append(f"  APFS (DHS): {apfs_new} new, {apfs_upd} updated")
    lines.append(f"  SAM.gov:    {sam_new} new, {sam_upd} updated")
    lines.append(f"  STRONG: {len(strong)} | MODERATE: {len(moderate)} | LOW: {len(low)}")
    lines.append("")

    lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    lines.append("STRONG MATCHES (0.65+)")
    lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    lines.append("")
    if strong:
        for o in strong[:20]:
            lines.append(card(o, "STRONG"))
            lines.append("")
    else:
        lines.append("  (No STRONG matches today.)")
        lines.append("")

    lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    lines.append("MODERATE MATCHES (0.50–0.64)")
    lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    lines.append("")
    if moderate:
        for o in moderate[:20]:
            lines.append(card(o, "MODERATE"))
            lines.append("")
    else:
        lines.append("  (No MODERATE matches today.)")
        lines.append("")

    lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    lines.append("LOW / AWARENESS")
    lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    lines.append("")
    if low:
        for o in low[:40]:
            t = o['title']
            a = o['agency']
            n = o['naics'] or '—'
            s = f"{o['score']:.2f}"
            lines.append(f"  {t} | {a} | {n} | {s}")
    else:
        lines.append("  (No LOW items today.)")

    lines.append("")
    lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    lines.append(f"Full branded HTML report: https://vm-coderock.github.io/VM2-P-Taskers/changeis-daily-brief-{DATE_YMD}.html")
    lines.append("")
    lines.append('TO REQUEST A DEEP DIVE: Create a Todoist task with label "vm2-opp" and the opportunity title as the task name. The system will produce a full analysis brief within the hour.')
    lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    lines.append("Changeis Confidential — Opportunity Intelligence")

    return "\n".join(lines)


def main():
    apfs, apfs_err = load_json(APFS_PATH)
    sam, sam_err = load_json(SAM_PATH)

    # freshness checks
    apfs_ok = apfs is not None and is_fresh(apfs.get("run_date",""))
    sam_ok = sam is not None and is_fresh(sam.get("run_date",""))

    if not apfs_ok and not sam_ok:
        # Write minimal artifacts so caller can decide to notify
        meta = {
            "date_utc": DATE_YMD,
            "apfs_status": "stale_or_missing" if apfs is None else "stale",
            "apfs_error": apfs_err,
            "sam_status": "stale_or_missing" if sam is None else "stale",
            "sam_error": sam_err,
        }
        with open(OUT_TEXT, "w", encoding="utf-8") as f:
            f.write("No opportunity data available today — both APFS and SAM.gov runs may not have completed")
        with open(OUT_HTML, "w", encoding="utf-8") as f:
            f.write("<html><body><p>No opportunity data available today — both APFS and SAM.gov runs may not have completed</p></body></html>")
        print(json.dumps(meta))
        return

    apfs_opps = []
    sam_opps = []

    apfs_new = apfs.get("new_count",0) if apfs_ok else 0
    apfs_upd = apfs.get("updated_count",0) if apfs_ok else 0
    sam_new = sam.get("new_count",0) if sam_ok else 0
    sam_upd = sam.get("updated_count",0) if sam_ok else 0

    if apfs_ok:
        apfs_opps = [opp_to_common("APFS", o) for o in (apfs.get("opportunities") or [])]
    if sam_ok:
        sam_opps = [opp_to_common("SAM.gov", o) for o in (sam.get("opportunities") or [])]

    all_opps = apfs_opps + sam_opps

    strong = [o for o in all_opps if o["rag_tier"]=="STRONG" or o["score"]>=0.65]
    moderate = [o for o in all_opps if o not in strong and (o["rag_tier"]=="MODERATE" or 0.50<=o["score"]<0.65)]
    low = [o for o in all_opps if o not in strong and o not in moderate]

    strong.sort(key=lambda x: -x["score"])
    moderate.sort(key=lambda x: -x["score"])
    low.sort(key=lambda x: -x["score"])

    naics_html = naics_dashboard(apfs_opps, sam_opps)

    def section(title, accent):
        return f"""
        <div style='margin-top:22px'>
          <div style='border-left:6px solid {accent};padding:8px 12px;background:#fff;border-radius:10px'>
            <div style='font-size:18px;color:{DEEP_NAVY};font-weight:800'>{title}</div>
          </div>
        </div>
        """

    strong_cards = "\n".join([card_html(o, GREEN) for o in strong]) or "<div style='color:#666;padding:10px 0'>No STRONG matches today.</div>"
    moderate_cards = "\n".join([card_html(o, ORANGE) for o in moderate]) or "<div style='color:#666;padding:10px 0'>No MODERATE matches today.</div>"
    low_table = build_low_table(low) if low else "<div style='color:#666;padding:10px 0'>No LOW items today.</div>"

    executive = f"""
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
          <div style='color:{DARK_GRAY};font-size:13.5px'>To request a deep dive: create a Todoist task labeled <b>vm2-opp</b> with the opportunity title.</div>
        </div>
      </div>
    </div>
    """

    html = f"""
    <html>
    <head>
      <meta charset='utf-8' />
      <meta name='viewport' content='width=device-width, initial-scale=1' />
      <title>Changeis Opportunity Intelligence — Daily Brief</title>
    </head>
    <body style='margin:0;background:#F6F8FB;font-family:-apple-system,BlinkMacSystemFont,Segoe UI,Roboto,Arial,sans-serif;color:{DARK_GRAY}'>
      <div style='background:{NAVY};color:#fff;padding:22px 20px'>
        <div style='max-width:980px;margin:0 auto'>
          <div style='font-size:22px;font-weight:900;letter-spacing:.2px'>Changeis Opportunity Intelligence — Daily Brief</div>
          <div style='margin-top:6px;font-size:14px;opacity:.9'>{DATE_STR}</div>
        </div>
      </div>

      <div style='max-width:980px;margin:0 auto;padding:18px 16px'>
        {executive}

        {section('STRONG Matches', GREEN)}
        {strong_cards}

        {section('MODERATE Matches', ORANGE)}
        {moderate_cards}

        {section('LOW / Awareness', '#666666')}
        {low_table}

        {section('NAICS Validation Dashboard', PURPLE)}
        <div style='margin-top:10px'>
          {naics_html}
        </div>

        <div style='margin-top:28px;border-top:1px solid #D8E2EE;padding-top:16px;color:#566'>
          <div style='font-size:12.5px'><b>Changeis Confidential</b> — Opportunity Intelligence — {TODAY_UTC.strftime('%B %Y')}</div>
          <div style='font-size:12.5px;margin-top:4px'>Powered by Changeis BD RAG Engine</div>
          <div style='font-size:12.5px;margin-top:8px'>To request a deep-dive analysis: create a Todoist task with label <b>vm2-opp</b> and the opportunity title as the task name</div>
        </div>
      </div>
    </body>
    </html>
    """

    with open(OUT_HTML, "w", encoding="utf-8") as f:
        f.write(html)

    text = build_plaintext(strong, moderate, low, apfs_new, apfs_upd, sam_new, sam_upd)
    with open(OUT_TEXT, "w", encoding="utf-8") as f:
        f.write(text)

    meta = {
        "date_utc": DATE_YMD,
        "apfs_ok": apfs_ok,
        "sam_ok": sam_ok,
        "apfs_new": apfs_new,
        "apfs_updated": apfs_upd,
        "sam_new": sam_new,
        "sam_updated": sam_upd,
        "apfs_opportunities": len(apfs_opps),
        "sam_opportunities": len(sam_opps),
        "strong_matches": len(strong),
        "moderate_matches": len(moderate),
        "low_matches": len(low),
    }
    print(json.dumps(meta))


if __name__ == "__main__":
    main()
