import json, os, sys, time
from datetime import datetime, timedelta, timezone
import requests

STATE_PATH = "/home/user/workspace/cron_tracking/8f2a4ac1/state.json"
OUT_DIR = "/home/user/workspace/cron_tracking/sam_monitor"
LOG_PATH = "/home/user/workspace/cron_tracking/8f2a4ac1/run_log.ndjson"

PRIORITY_NAICS = [
    "541511", "541512", "541513", "541519", "541611",
    "518210", "541330", "541690", "541715", "561110", "611430"
]

SEARCH_API = "https://sam.gov/api/prod/sgs/v1/search/"
DETAIL_API = "https://sam.gov/api/prod/opps/v2/opportunities/{noticeId}"

RAG_URL = "https://changeis-bd-rag-production.up.railway.app/match"
RAG_API_KEY = "a3-nFpt4YJHCXpsTHS7ZAikNllzrPtCORKBoSN8tAAE"


def load_state():
    if os.path.exists(STATE_PATH):
        with open(STATE_PATH, "r") as f:
            return json.load(f)
    return {"last_run_utc": None, "seen_notice_ids": [], "last_output_files": []}

def save_state(state):
    max_seen = 8000
    if len(state.get("seen_notice_ids", [])) > max_seen:
        state["seen_notice_ids"] = state["seen_notice_ids"][-max_seen:]
    with open(STATE_PATH, "w") as f:
        json.dump(state, f, indent=2, sort_keys=True)

def log(event):
    event["ts_utc"] = datetime.now(timezone.utc).isoformat()
    with open(LOG_PATH, "a") as f:
        f.write(json.dumps(event) + "\n")

def rag_score(text):
    headers = {"x-api-key": RAG_API_KEY, "Content-Type": "application/json"}
    payload = {"query": text, "top_n": 50}
    r = requests.post(RAG_URL, headers=headers, json=payload, timeout=30)
    r.raise_for_status()
    data = r.json()
    scores = []
    arr = None
    if isinstance(data, dict):
        arr = data.get("results") or data.get("matches")
    if isinstance(arr, list):
        for it in arr:
            if isinstance(it, dict) and isinstance(it.get("score"), (int, float)):
                scores.append(float(it["score"]))
    best = max(scores) if scores else 0.0
    best_match = None
    if isinstance(arr, list) and arr:
        arr2 = [x for x in arr if isinstance(x, dict) and isinstance(x.get("score"), (int, float))]
        if arr2:
            best_item = max(arr2, key=lambda x: x.get("score", 0))
            best_match = {
                "score": float(best_item.get("score", 0.0)),
                "title": best_item.get("title") or best_item.get("name"),
                "client": best_item.get("client"),
                "id": best_item.get("id")
            }
    return best, best_match

def tier(score):
    if score >= 0.65:
        return "STRONG"
    if score >= 0.50:
        return "MODERATE"
    if score >= 0.45:
        return "RELEVANT"
    return "LOW"

def search_naics(naics, size=25):
    params = {
        "index": "opp",
        "q": naics,
        "page": 0,
        "sort": "-modifiedDate",
        "size": size,
        "mode": "search",
        "is_active": "true"
    }
    r = requests.get(SEARCH_API, params=params, timeout=40)
    r.raise_for_status()
    return r.json()

def extract_hits(search_json):
    # Expected: {"_embedded": {"results": [...]}} or {"_embedded": {"results": {"items": [...]}}}
    emb = search_json.get("_embedded") if isinstance(search_json, dict) else None
    if not isinstance(emb, dict):
        return []
    res = emb.get("results")
    if isinstance(res, list):
        return res
    if isinstance(res, dict) and isinstance(res.get("items"), list):
        return res["items"]
    return []

def get_detail(notice_id):
    url = DETAIL_API.format(noticeId=notice_id)
    r = requests.get(url, timeout=40)
    r.raise_for_status()
    return r.json()

def pick(d, *keys):
    cur = d
    for k in keys:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(k)
    return cur

def normalize(detail, search_naics_code=None):
    notice_id = detail.get("noticeId") or detail.get("id")
    title = detail.get("title") or detail.get("opportunityTitle")
    agency = pick(detail, "organization", "fullPath") or detail.get("fullParentPathName")
    posted = detail.get("postedDate") or detail.get("posted_date")
    resp = detail.get("responseDeadLine") or detail.get("responseDeadline") or detail.get("responseDate")
    naics = detail.get("naicsCode") or pick(detail, "naics", "code")
    # description fields vary
    desc = detail.get("description") or detail.get("descriptionText") or pick(detail, "data", "description")
    if isinstance(desc, dict):
        desc = desc.get("description") or desc.get("text")
    # sometimes in "fullDescription"
    if not desc:
        desc = detail.get("fullDescription")
    # url
    sam_url = detail.get("uiLink") or detail.get("url")
    return {
        "noticeId": notice_id,
        "title": (title or "").strip(),
        "agency": agency,
        "postedDate": posted,
        "responseDeadLine": resp,
        "naicsCode": naics,
        "search_naics": search_naics_code,
        "sam_url": sam_url,
        "description": desc,
        "raw": detail
    }

def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    state = load_state()
    seen = set(state.get("seen_notice_ids", []))

    now_utc = datetime.now(timezone.utc)
    log({"event": "run_start", "naics_count": len(PRIORITY_NAICS)})

    candidates = {}
    for naics in PRIORITY_NAICS:
        try:
            sj = search_naics(naics)
            hits = extract_hits(sj)
        except Exception as e:
            log({"event": "search_error", "naics": naics, "error": str(e)})
            continue
        for h in hits:
            # try multiple id fields
            nid = h.get("noticeId") or h.get("id") or pick(h, "_source", "noticeId") or pick(h, "_source", "id")
            if not nid or nid in seen:
                continue
            candidates[nid] = {"noticeId": nid, "search_naics": naics, "search_hit": h}

    new_ids = list(candidates.keys())

    scored = []
    for nid in new_ids:
        meta = candidates[nid]
        try:
            detail = get_detail(nid)
        except Exception as e:
            log({"event": "detail_error", "noticeId": nid, "error": str(e)})
            continue
        rec = normalize(detail, meta.get("search_naics"))
        query_text = "\n".join([x for x in [rec.get("title"), rec.get("agency"), rec.get("description")] if x])
        query_text = query_text[:15000]
        score = 0.0
        best_match = None
        try:
            score, best_match = rag_score(query_text)
        except Exception as e:
            log({"event": "rag_error", "noticeId": nid, "error": str(e)})
        rec["rag_score"] = round(float(score), 4)
        rec["rag_tier"] = tier(score)
        rec["best_match"] = best_match
        # excerpt
        desc = rec.get("description")
        if isinstance(desc, str):
            rec["description_excerpt"] = desc[:800]
        else:
            rec["description_excerpt"] = None
        # shrink raw
        rec["raw"] = None
        scored.append(rec)
        time.sleep(0.1)

    tier_rank = {"STRONG": 0, "MODERATE": 1, "RELEVANT": 2, "LOW": 3}
    scored.sort(key=lambda r: (tier_rank.get(r.get("rag_tier"), 9), -r.get("rag_score", 0.0)))

    run_id = now_utc.strftime("%Y%m%dT%H%M%SZ")
    out_json = os.path.join(OUT_DIR, f"sam_daily_{run_id}.json")
    with open(out_json, "w") as f:
        json.dump({
            "run_id": run_id,
            "priority_naics": PRIORITY_NAICS,
            "new_count": len(scored),
            "opportunities": scored
        }, f, indent=2)

    for rec in scored:
        seen.add(rec.get("noticeId"))
    state["seen_notice_ids"] = list(seen)
    state["last_run_utc"] = now_utc.isoformat()
    state["last_output_files"] = [out_json]
    save_state(state)

    log({"event": "run_complete", "new_count": len(scored), "out_json": out_json})
    print(out_json)

if __name__ == "__main__":
    main()
