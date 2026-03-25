import subprocess, json, time, os, re
from datetime import datetime, timezone

NAICS_CODES = ["541511", "541512", "541513", "541519", "541611", "541612", "541613", "541614", "541618", "541715", "541990"]

TRACKING_DIR = "/home/user/workspace/cron_tracking/30af1ae5"
os.makedirs(TRACKING_DIR, exist_ok=True)

CURRENT_PATH = os.path.join(TRACKING_DIR, "sam_current.json")
PREVIOUS_PATH = os.path.join(TRACKING_DIR, "sam_previous.json")
CHANGES_PATH = os.path.join(TRACKING_DIR, "sam_changes.json")
RAG_RESULTS_PATH = os.path.join(TRACKING_DIR, "sam_rag_results.json")
NAICS_VALIDATION_PATH = os.path.join(TRACKING_DIR, "sam_naics_validation.json")


def fetch_sam_page(naics, page=0, size=25, max_retries=3):
    url = f"https://sam.gov/api/prod/sgs/v1/search/?index=opp&page={page}&sort=-modifiedDate&size={size}&mode=search&is_active=true&q={naics}"
    last_err = None
    for attempt in range(max_retries):
        try:
            result = subprocess.run(
                ["curl", "-sf", "--max-time", "30", url],
                capture_output=True, text=True, timeout=45
            )
            if result.returncode == 0 and result.stdout.strip():
                return json.loads(result.stdout)
            last_err = (result.stderr or result.stdout or "").strip()[:300]
        except Exception as e:
            last_err = str(e)[:300]
        time.sleep(5 * (attempt + 1))
    return {"error": "fetch_failed", "naics": naics, "page": page, "detail": last_err}


def call_rag(query_text, max_retries=3):
    for attempt in range(max_retries):
        try:
            payload = json.dumps({"query": query_text, "top_n": 3})
            result = subprocess.run(
                ["curl", "-sf", "--max-time", "30",
                 "-X", "POST", "https://changeis-bd-rag-production.up.railway.app/match",
                 "-H", "Content-Type: application/json",
                 "-H", "X-API-Key: a3-nFpt4YJHCXpsTHS7ZAikNllzrPtCORKBoSN8tAAE",
                 "-d", payload],
                capture_output=True, text=True, timeout=45
            )
            if result.returncode == 0 and result.stdout.strip():
                return json.loads(result.stdout)
        except Exception:
            pass
        time.sleep(5 * (attempt + 1))
    return {"error": "RAG call failed after retries", "query": query_text[:100]}


def clean_html(s):
    if not s:
        return ""
    return re.sub(r"<[^>]+>", "", s).strip()


def tier(score):
    if score is None:
        return "LOW"
    if score >= 0.65:
        return "STRONG"
    if score >= 0.50:
        return "MODERATE"
    return "LOW"


def main():
    run_ts = datetime.now(timezone.utc)
    run_date = run_ts.date().isoformat()

    all_opportunities = {}
    validation = {
        "run_date": run_date,
        "run_timestamp_utc": run_ts.isoformat(),
        "naics_codes": NAICS_CODES,
        "per_naics": {},
        "errors": []
    }

    for naics in NAICS_CODES:
        validation["per_naics"][naics] = {"pages_fetched": 0, "results_seen": 0}
        for page in range(2):
            data = fetch_sam_page(naics, page=page)
            if not data or isinstance(data, dict) and data.get("error") == "fetch_failed":
                validation["errors"].append(data)
                break
            embedded = data.get("_embedded") or {}
            results = embedded.get("results", [])
            if not results:
                break
            validation["per_naics"][naics]["pages_fetched"] += 1
            validation["per_naics"][naics]["results_seen"] += len(results)

            for r in results:
                sol_num = (r.get("solicitationNumber") or "").strip()
                if not sol_num or sol_num in all_opportunities:
                    continue

                org = r.get("organizationHierarchy", []) or []
                dept = org[0]["name"] if org else "Unknown"
                agency = org[1]["name"] if len(org) > 1 else dept

                desc = ""
                descs = r.get("descriptions", []) or []
                if descs:
                    desc = clean_html(descs[0].get("content") or "")[:500]

                all_opportunities[sol_num] = {
                    "solicitation_number": sol_num,
                    "title": r.get("title", "") or "",
                    "agency": agency,
                    "department": dept,
                    "naics": naics,
                    "posted_date": (r.get("publishDate") or "")[:10],
                    "modified_date": (r.get("modifiedDate") or "")[:10],
                    "response_deadline": (r.get("responseDate") or "")[:10],
                    "type": (r.get("type") or {}).get("value", "") or "",
                    "sam_link": f"https://sam.gov/opp/{r.get('_id', '')}/view",
                    "description": desc,
                    "is_canceled": bool(r.get("isCanceled", False))
                }

    current_list = list(all_opportunities.values())
    current_payload = {
        "run_date": run_date,
        "run_timestamp_utc": run_ts.isoformat(),
        "total_unique": len(current_list),
        "opportunities": current_list
    }
    with open(CURRENT_PATH, "w") as f:
        json.dump(current_payload, f, indent=2)

    prev_by_sol = {}
    if os.path.exists(PREVIOUS_PATH):
        with open(PREVIOUS_PATH, "r") as f:
            prev = json.load(f)
        for o in prev.get("opportunities", []):
            prev_by_sol[o.get("solicitation_number")] = o

    new_ops = []
    updated_ops = []
    for o in current_list:
        sol = o["solicitation_number"]
        if sol not in prev_by_sol:
            new_ops.append(o)
        else:
            if (o.get("modified_date") or "") != (prev_by_sol[sol].get("modified_date") or ""):
                updated_ops.append(o)

    changes = {
        "run_date": run_date,
        "run_timestamp_utc": run_ts.isoformat(),
        "total_unique": len(current_list),
        "new_count": len(new_ops),
        "updated_count": len(updated_ops),
        "new": [{"solicitation_number": o["solicitation_number"], "modified_date": o.get("modified_date"), "title": o.get("title"), "sam_link": o.get("sam_link")} for o in new_ops],
        "updated": [{"solicitation_number": o["solicitation_number"], "modified_date": o.get("modified_date"), "title": o.get("title"), "sam_link": o.get("sam_link")} for o in updated_ops]
    }
    with open(CHANGES_PATH, "w") as f:
        json.dump(changes, f, indent=2)

    # RAG on new + updated
    rag_opps = []
    for o in (new_ops + updated_ops):
        query = f"{o.get('title','')}. {o.get('description','')}".strip()
        rag = call_rag(query)
        matches = []
        top_score = None
        if isinstance(rag, dict):
            raw_matches = rag.get("matches") or rag.get("results") or []
            for m in raw_matches[:3]:
                comp = m.get("composite_score")
                if comp is None:
                    comp = m.get("score")
                try:
                    comp_f = float(comp) if comp is not None else None
                except Exception:
                    comp_f = None
                if top_score is None and comp_f is not None:
                    top_score = comp_f
                elif comp_f is not None and top_score is not None:
                    top_score = max(top_score, comp_f)

                text = m.get("text") or m.get("excerpt") or ""
                excerpt = (text or "")[:200]
                matches.append({
                    "task_order": m.get("task_order") or m.get("taskOrder") or m.get("id") or "",
                    "composite_score": comp_f,
                    "end_client": m.get("end_client") or m.get("client") or "",
                    "excerpt_summary": excerpt
                })

        rag_opps.append({
            **o,
            "change_type": "NEW" if o in new_ops else "UPDATED",
            "rag_tier": tier(top_score),
            "rag_top_score": top_score if top_score is not None else 0.0,
            "rag_matches": matches
        })

    rag_results = {
        "run_date": run_date,
        "run_timestamp_utc": run_ts.isoformat(),
        "source": "SAM.gov",
        "total_browsed": len(current_list),
        "new_count": len(new_ops),
        "updated_count": len(updated_ops),
        "opportunities": rag_opps
    }
    with open(RAG_RESULTS_PATH, "w") as f:
        json.dump(rag_results, f, indent=2)

    with open(NAICS_VALIDATION_PATH, "w") as f:
        json.dump(validation, f, indent=2)

    # Update baseline
    with open(PREVIOUS_PATH, "w") as f:
        json.dump(current_payload, f, indent=2)


if __name__ == "__main__":
    main()
