import json, os, re, subprocess, time
from datetime import datetime, timezone

BASE_DIR = "/home/user/workspace/cron_tracking/f7adf3cd"
RAW_PATH = os.path.join(BASE_DIR, "apfs_current_raw.json")
FILTERED_PATH = os.path.join(BASE_DIR, "apfs_current_filtered.json")
PREV_PATH = os.path.join(BASE_DIR, "apfs_previous.json")
CHANGES_PATH = os.path.join(BASE_DIR, "apfs_changes.json")
RAG_PATH = os.path.join(BASE_DIR, "apfs_rag_results.json")
NAICS_VALIDATION_PATH = os.path.join(BASE_DIR, "apfs_naics_validation.json")
RUN_SUMMARY_PATH = os.path.join(BASE_DIR, "run_summary.json")

NAICS_ALLOW = {
    "541110","541120","541191","541199","541211","541213","541214","541219","541310","541320","541330","541340",
    "541350","541360","541370","541380","541410","541420","541430","541490","541511","541512","541513","541519",
    "541611","541612","541613","541614","541618","541620","541690","541710","541715","541720","541810","541820",
    "541830","541840","541850","541860","541870","541890","541910","541921","541922","541930","541940","541990"
}


def load_json(path, default=None):
    if not os.path.exists(path):
        return default
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path, obj):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def extract_naics_code(naics_field):
    if not naics_field:
        return None
    m = re.search(r"\b(\d{6})\b", str(naics_field))
    return m.group(1) if m else None


def normalize_record(rec):
    # pass-through plus derived
    naics_code = extract_naics_code(rec.get("naics"))
    out = dict(rec)
    out["naics_code"] = naics_code
    return out


def filter_records(records):
    filtered = []
    for r in records:
        nr = normalize_record(r)
        if nr.get("naics_code") in NAICS_ALLOW:
            filtered.append(nr)
    return filtered


def index_by_apfs(records):
    idx = {}
    for r in records:
        k = r.get("apfs_number")
        if k:
            idx[str(k)] = r
    return idx


def detect_changes(current, previous):
    prev_idx = index_by_apfs(previous or [])
    new_recs, updated_recs = [], []
    for r in current:
        k = str(r.get("apfs_number"))
        if k not in prev_idx:
            new_recs.append(r)
        else:
            pr = prev_idx[k]
            if (r.get("last_updated_date") != pr.get("last_updated_date")) or (r.get("published_date") != pr.get("published_date")):
                updated_recs.append(r)
    return new_recs, updated_recs


def call_rag(query_text, max_retries=3):
    """Call Changeis BD RAG Engine with retry logic."""
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


def summarize_excerpt(text, n=200):
    if not text:
        return ""
    t = re.sub(r"\s+", " ", str(text)).strip()
    return t[:n]


def tier_from_score(score):
    if score is None:
        return "LOW"
    if score >= 0.65:
        return "STRONG"
    if 0.50 <= score <= 0.64:
        return "MODERATE"
    return "LOW"


def safe_float(x):
    try:
        return float(x)
    except Exception:
        return None


def main():
    run_ts = datetime.now(timezone.utc)
    run_date = run_ts.strftime("%Y-%m-%d")

    raw = load_json(RAW_PATH)
    if isinstance(raw, dict) and "results" in raw:
        records = raw.get("results") or []
    elif isinstance(raw, list):
        records = raw
    else:
        records = []

    filtered = filter_records(records)
    save_json(FILTERED_PATH, filtered)

    prev = load_json(PREV_PATH, default=[])
    new_recs, updated_recs = detect_changes(filtered, prev)

    changes = {
        "run_date": run_date,
        "run_timestamp_utc": run_ts.isoformat().replace("+00:00", "Z"),
        "total_filtered": len(filtered),
        "new_count": len(new_recs),
        "updated_count": len(updated_recs),
        "new": new_recs,
        "updated": updated_recs
    }
    save_json(CHANGES_PATH, changes)

    opportunities_out = []
    naics_scores = {}

    for change_type, recs in [("NEW", new_recs), ("UPDATED", updated_recs)]:
        for r in recs:
            title = r.get("title") or ""
            req = r.get("requirement_description") or ""
            query = f"{title}. {req}".strip()
            rag = call_rag(query)

            matches = []
            top_score = None
            if isinstance(rag, dict) and isinstance(rag.get("matches"), list):
                for m in rag.get("matches")[:3]:
                    score = safe_float(m.get("composite_score"))
                    if top_score is None or (score is not None and score > top_score):
                        top_score = score
                    matches.append({
                        "task_order": m.get("task_order"),
                        "composite_score": score,
                        "end_client": m.get("end_client"),
                        "excerpt_summary": summarize_excerpt(m.get("text") or m.get("excerpt") or "")
                    })
            rag_tier = tier_from_score(top_score)

            naics_code = r.get("naics_code")
            if naics_code:
                ns = naics_scores.setdefault(naics_code, {"count": 0, "scores": [], "tier_distribution": {"STRONG": 0, "MODERATE": 0, "LOW": 0}})
                ns["count"] += 1
                if top_score is not None:
                    ns["scores"].append(top_score)
                ns["tier_distribution"][rag_tier] = ns["tier_distribution"].get(rag_tier, 0) + 1

            opportunities_out.append({
                "apfs_number": r.get("apfs_number"),
                "title": title,
                "organization": r.get("organization"),
                "naics": r.get("naics"),
                "naics_code": naics_code,
                "dollar_range": r.get("dollar_range"),
                "contract_vehicle": r.get("contract_vehicle"),
                "contract_type": r.get("contract_type"),
                "published_date": r.get("published_date"),
                "est_solicitation_release": r.get("est_solicitation_release"),
                "requirement_description": r.get("requirement_description"),
                "change_type": change_type,
                "rag_tier": rag_tier,
                "rag_top_score": top_score,
                "rag_matches": matches,
            })

    # finalize naics validation
    naics_validation = {"run_date": run_date, "naics_scores": {}}
    for code, v in naics_scores.items():
        scores = v.get("scores") or []
        avg = sum(scores) / len(scores) if scores else None
        mx = max(scores) if scores else None
        naics_validation["naics_scores"][code] = {
            "count": v.get("count", 0),
            "avg_score": avg,
            "max_score": mx,
            "tier_distribution": v.get("tier_distribution", {})
        }

    rag_results = {
        "run_date": run_date,
        "run_timestamp_utc": run_ts.isoformat().replace("+00:00", "Z"),
        "source": "APFS",
        "total_filtered": len(filtered),
        "new_count": len(new_recs),
        "updated_count": len(updated_recs),
        "opportunities": opportunities_out
    }

    save_json(RAG_PATH, rag_results)
    save_json(NAICS_VALIDATION_PATH, naics_validation)

    # update baseline
    save_json(PREV_PATH, filtered)

    run_summary = {
        "run_date": run_date,
        "run_timestamp_utc": run_ts.isoformat().replace("+00:00", "Z"),
        "total_filtered": len(filtered),
        "new_count": len(new_recs),
        "updated_count": len(updated_recs)
    }
    save_json(RUN_SUMMARY_PATH, run_summary)


if __name__ == "__main__":
    main()
