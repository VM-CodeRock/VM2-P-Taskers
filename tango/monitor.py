"""Read-only Tango monitor and dry-run command.

Pulls priority opportunities and forecasts for Changeis-relevant NAICS,
agency, and keyword filters; performs attachment keyword searches; enriches
with incumbent/recompete candidates from /api/contracts/; writes local
JSON + Markdown + HTML dry-run artifacts. Does NOT create Todoist tasks
unless ``--push-todoist`` is explicitly passed (placeholder — not wired
until the operator confirms). The existing VM2-OPP cron/Todoist workflow
is untouched.

Usage (typical):

    python -m tango.monitor --mock --output-dir /tmp/tango-dry
    TANGO_API_KEY=... python -m tango.monitor --output-dir /tmp/tango-dry

See tango/docs/README.md for the full rollout plan.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import datetime, timezone
from html import escape
from typing import Any, Dict, List, Optional

from .client import TangoAPIError, TangoClient
from .config import KEYWORD_CLUSTERS, PRIORITY_AGENCIES, PRIORITY_NAICS, RECOMPETE_WINDOW_DAYS
from .enrichment import batch_enrich
from .normalizer import (
    attachment_snippets,
    normalize_forecast,
    normalize_opportunity,
)

log = logging.getLogger("tango.monitor")


def build_client(mock: bool) -> TangoClient:
    if mock:
        from .mock import MockTangoClient
        return MockTangoClient()
    return TangoClient()


def run(
    *,
    mock: bool = False,
    naics: Optional[List[str]] = None,
    agencies: Optional[List[str]] = None,
    keyword_clusters: Optional[Dict[str, str]] = None,
    output_dir: str = ".",
    max_opportunities: int = 200,
    max_forecasts: int = 100,
    max_attachment_hits_per_cluster: int = 25,
    enrich: bool = True,
    recompete_window_days: int = RECOMPETE_WINDOW_DAYS,
    push_todoist: bool = False,
) -> Dict[str, Any]:
    """Execute one monitor pass and write dry-run artifacts. Returns the summary dict."""
    os.makedirs(output_dir, exist_ok=True)
    run_ts = datetime.now(timezone.utc)
    run_date = run_ts.date().isoformat()

    client = build_client(mock)
    naics_list = naics or PRIORITY_NAICS
    agency_list = agencies or PRIORITY_AGENCIES
    clusters = keyword_clusters or KEYWORD_CLUSTERS

    errors: List[Dict[str, Any]] = []

    # 1. Opportunities
    raw_opps: List[Dict[str, Any]] = []
    try:
        raw_opps = client.opportunities(
            naics=naics_list,
            agency=agency_list,
            active=True,
            ordering="-first_notice_date",
            limit=50,
            max_pages=max(1, max_opportunities // 50 + 1),
            max_results=max_opportunities,
        )
    except TangoAPIError as exc:
        errors.append({"stage": "opportunities", "error": str(exc), "status": exc.status_code})

    opportunities = [normalize_opportunity(r) for r in raw_opps]

    # 2. Forecasts
    raw_fcs: List[Dict[str, Any]] = []
    try:
        raw_fcs = client.forecasts(
            naics=naics_list,
            agency=agency_list,
            limit=50,
            max_pages=max(1, max_forecasts // 50 + 1),
            max_results=max_forecasts,
        )
    except TangoAPIError as exc:
        errors.append({"stage": "forecasts", "error": str(exc), "status": exc.status_code})

    forecasts = [normalize_forecast(r) for r in raw_fcs]

    # 3. Attachment keyword clusters
    attachment_hits: Dict[str, List[Dict[str, Any]]] = {}
    for cluster_name, query in clusters.items():
        try:
            rows = client.attachment_search(
                query=query,
                naics=naics_list,
                limit=25,
                max_pages=1,
                max_results=max_attachment_hits_per_cluster,
            )
        except TangoAPIError as exc:
            errors.append({"stage": f"attachment_search:{cluster_name}", "error": str(exc), "status": exc.status_code})
            rows = []
        attachment_hits[cluster_name] = [
            {
                "cluster": cluster_name,
                "query": query,
                "opportunity_id": r.get("opportunity_id") or r.get("id"),
                "solicitation_number": r.get("solicitation_number"),
                "title": r.get("title"),
                "attachment_filename": r.get("attachment_filename") or r.get("filename"),
                "snippets": attachment_snippets(r),
            }
            for r in rows
        ]

    # Attach cluster hits back onto opportunities when sol number matches
    opp_by_sol = {o["solicitation_number"]: o for o in opportunities if o.get("solicitation_number")}
    for cluster_name, hits in attachment_hits.items():
        for h in hits:
            sol = h.get("solicitation_number")
            if sol and sol in opp_by_sol:
                opp_by_sol[sol].setdefault("attachment_hits", []).append(
                    {"cluster": cluster_name, "filename": h.get("attachment_filename"), "snippets": h["snippets"]}
                )

    # 4. Incumbent / recompete enrichment
    enrichments: List[Dict[str, Any]] = []
    if enrich and opportunities:
        try:
            enrichments = batch_enrich(client, opportunities, window_days=recompete_window_days)
            for opp, enr in zip(opportunities, enrichments):
                if enr.get("candidates"):
                    opp["incumbent_candidates"] = enr["candidates"]
                    opp["incumbent_matched_by"] = enr["matched_by"]
        except TangoAPIError as exc:
            errors.append({"stage": "enrichment", "error": str(exc), "status": exc.status_code})

    summary = {
        "run_date": run_date,
        "run_timestamp_utc": run_ts.isoformat(),
        "source": "Tango / MakeGov",
        "mock": mock,
        "filters": {
            "naics": naics_list,
            "agencies": agency_list,
            "keyword_clusters": clusters,
            "recompete_window_days": recompete_window_days,
        },
        "counts": {
            "opportunities": len(opportunities),
            "forecasts": len(forecasts),
            "attachment_clusters": len(attachment_hits),
            "attachment_hits_total": sum(len(v) for v in attachment_hits.values()),
            "enrichments": sum(1 for e in enrichments if e.get("candidates")),
        },
        "opportunities": opportunities,
        "forecasts": forecasts,
        "attachment_hits": attachment_hits,
        "errors": errors,
        "push_todoist": bool(push_todoist),
    }

    json_path = os.path.join(output_dir, f"tango-dry-run-{run_date}.json")
    md_path = os.path.join(output_dir, f"tango-dry-run-{run_date}.md")
    html_path = os.path.join(output_dir, f"tango-dry-run-{run_date}.html")

    with open(json_path, "w") as f:
        json.dump(summary, f, indent=2, default=str)
    with open(md_path, "w") as f:
        f.write(_render_markdown(summary))
    with open(html_path, "w") as f:
        f.write(_render_html(summary))

    summary["artifacts"] = {"json": json_path, "markdown": md_path, "html": html_path}

    if push_todoist:
        log.warning(
            "--push-todoist was set but Todoist push is intentionally not wired yet. "
            "Dry-run artifacts are the source of truth until the operator enables production push."
        )

    return summary


# ---- rendering --------------------------------------------------------


def _render_markdown(summary: Dict[str, Any]) -> str:
    lines: List[str] = []
    lines.append(f"# Tango Dry Run — {summary['run_date']}")
    lines.append("")
    lines.append(f"_Source: {summary['source']} (mock={summary['mock']})_")
    lines.append("")
    c = summary["counts"]
    lines.append("## Counts")
    lines.append(f"- Opportunities: {c['opportunities']}")
    lines.append(f"- Forecasts: {c['forecasts']}")
    lines.append(f"- Attachment clusters: {c['attachment_clusters']} ({c['attachment_hits_total']} hits)")
    lines.append(f"- Opportunities with incumbent matches: {c['enrichments']}")
    lines.append("")

    if summary["errors"]:
        lines.append("## Errors")
        for e in summary["errors"]:
            lines.append(f"- `{e.get('stage')}` (status={e.get('status')}): {e.get('error')}")
        lines.append("")

    lines.append("## Priority Opportunities")
    if not summary["opportunities"]:
        lines.append("_none_")
    for o in summary["opportunities"][:50]:
        lines.append(
            f"- **{o.get('title','(no title)')}** — {o.get('agency','')} "
            f"| NAICS {o.get('naics','')} | sol `{o.get('solicitation_number','')}` "
            f"| due {o.get('response_deadline','')}"
        )
        if o.get("tango_link"):
            lines.append(f"  - Tango: {o['tango_link']}")
        if o.get("sam_link"):
            lines.append(f"  - SAM: {o['sam_link']}")
        hits = o.get("attachment_hits") or []
        for h in hits[:3]:
            for s in (h.get("snippets") or [])[:2]:
                lines.append(f"  - _[{h.get('cluster')}]_ {s.get('text','')}")
        inc = o.get("incumbent_candidates") or []
        for cand in inc[:2]:
            lines.append(
                f"  - _incumbent_: {cand.get('recipient','')} "
                f"(PIID {cand.get('piid','')}, ends {cand.get('period_of_performance_end','')})"
            )
    lines.append("")

    lines.append("## Forecasts")
    if not summary["forecasts"]:
        lines.append("_none_")
    for f in summary["forecasts"][:50]:
        lines.append(
            f"- **{f.get('title','(no title)')}** — {f.get('agency','')} "
            f"| NAICS {f.get('naics','')} | FY {f.get('fiscal_year','')} "
            f"| est. solicit {f.get('response_deadline','')}"
        )
    lines.append("")
    return "\n".join(lines)


def _render_html(summary: Dict[str, Any]) -> str:
    """Minimal HTML view compatible with the VM2-OPP daily brief styling."""
    c = summary["counts"]
    parts: List[str] = []
    parts.append("<!doctype html><meta charset='utf-8'>")
    parts.append("<style>body{font-family:Calibri,Arial,sans-serif;max-width:900px;margin:24px auto;color:#1B2A4A}")
    parts.append("h1{color:#1B2A4A}h2{border-bottom:2px solid #1B2A4A;padding-bottom:4px}")
    parts.append(".opp{margin:10px 0;padding:10px;border:1px solid #D0D0D0;border-radius:6px}")
    parts.append(".meta{color:#5A6A7A;font-size:12px}.hit{background:#F2F2F2;padding:4px 6px;border-radius:4px;margin:4px 0}")
    parts.append("</style>")
    parts.append(f"<h1>Tango Dry Run — {escape(summary['run_date'])}</h1>")
    parts.append(
        f"<p class='meta'>Source: {escape(summary['source'])} · mock={summary['mock']} · "
        f"{c['opportunities']} opportunities · {c['forecasts']} forecasts · "
        f"{c['attachment_hits_total']} attachment hits · {c['enrichments']} incumbent matches</p>"
    )
    if summary["errors"]:
        parts.append("<h2>Errors</h2><ul>")
        for e in summary["errors"]:
            parts.append(f"<li><code>{escape(str(e.get('stage','')))}</code>: {escape(str(e.get('error','')))}</li>")
        parts.append("</ul>")

    parts.append("<h2>Priority Opportunities</h2>")
    for o in summary["opportunities"][:50]:
        parts.append("<div class='opp'>")
        parts.append(f"<strong>{escape(str(o.get('title','(no title)')))}</strong><br>")
        parts.append(
            f"<span class='meta'>{escape(str(o.get('agency','')))} · NAICS {escape(str(o.get('naics','')))} "
            f"· sol {escape(str(o.get('solicitation_number','')))} · due {escape(str(o.get('response_deadline','')))}</span>"
        )
        if o.get("tango_link"):
            parts.append(f"<br><a href='{escape(str(o['tango_link']))}'>Tango</a>")
        if o.get("sam_link"):
            parts.append(f" · <a href='{escape(str(o['sam_link']))}'>SAM</a>")
        for h in (o.get("attachment_hits") or [])[:3]:
            for s in (h.get("snippets") or [])[:2]:
                parts.append(
                    f"<div class='hit'><em>[{escape(str(h.get('cluster','')))}"
                    f" / {escape(str(h.get('filename','')))}]</em> {escape(str(s.get('text','')))}</div>"
                )
        for cand in (o.get("incumbent_candidates") or [])[:2]:
            parts.append(
                f"<div class='hit'><em>incumbent:</em> {escape(str(cand.get('recipient','')))} "
                f"(PIID {escape(str(cand.get('piid','')))}, ends {escape(str(cand.get('period_of_performance_end','')))})</div>"
            )
        parts.append("</div>")

    parts.append("<h2>Forecasts</h2>")
    for f in summary["forecasts"][:50]:
        parts.append("<div class='opp'>")
        parts.append(f"<strong>{escape(str(f.get('title','(no title)')))}</strong><br>")
        parts.append(
            f"<span class='meta'>{escape(str(f.get('agency','')))} · NAICS {escape(str(f.get('naics','')))} "
            f"· FY {escape(str(f.get('fiscal_year','')))}</span>"
        )
        parts.append("</div>")
    return "".join(parts)


# ---- CLI --------------------------------------------------------------


def _parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Read-only Tango / MakeGov monitor for VM2-OPP.")
    p.add_argument("--mock", action="store_true", help="Use fixture data (no network, no API key required).")
    p.add_argument("--output-dir", default="tango/output", help="Where to write JSON/MD/HTML dry-run artifacts.")
    p.add_argument("--naics", action="append", help="NAICS code (repeatable). Defaults to Changeis priority set.")
    p.add_argument("--agency", action="append", help="Agency name (repeatable). Defaults to Changeis priority set.")
    p.add_argument(
        "--keyword-cluster",
        action="append",
        metavar="name=query",
        help="Override/extend attachment-search clusters. Format: name=query string (repeatable).",
    )
    p.add_argument("--max-opportunities", type=int, default=200)
    p.add_argument("--max-forecasts", type=int, default=100)
    p.add_argument("--recompete-window-days", type=int, default=RECOMPETE_WINDOW_DAYS)
    p.add_argument("--no-enrich", action="store_true", help="Skip incumbent/recompete contract lookups.")
    p.add_argument(
        "--push-todoist",
        action="store_true",
        help="(not yet wired) Would push high-score opportunities to the vm2-opp Todoist queue. "
             "Current behavior is to log a warning and do nothing so production cron is preserved.",
    )
    p.add_argument("--verbose", action="store_true")
    return p.parse_args(argv)


def _parse_clusters(raw: Optional[List[str]]) -> Optional[Dict[str, str]]:
    if not raw:
        return None
    out: Dict[str, str] = {}
    for item in raw:
        if "=" not in item:
            raise ValueError(f"--keyword-cluster must be name=query, got: {item!r}")
        name, query = item.split("=", 1)
        out[name.strip()] = query.strip()
    return out or None


def main(argv: Optional[List[str]] = None) -> int:
    args = _parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    try:
        summary = run(
            mock=args.mock,
            naics=args.naics,
            agencies=args.agency,
            keyword_clusters=_parse_clusters(args.keyword_cluster),
            output_dir=args.output_dir,
            max_opportunities=args.max_opportunities,
            max_forecasts=args.max_forecasts,
            recompete_window_days=args.recompete_window_days,
            enrich=not args.no_enrich,
            push_todoist=args.push_todoist,
        )
    except TangoAPIError as exc:
        log.error("Tango API error: %s (status=%s)", exc, exc.status_code)
        return 2

    c = summary["counts"]
    print(
        f"[tango] {summary['run_date']} mock={summary['mock']} "
        f"opps={c['opportunities']} forecasts={c['forecasts']} "
        f"attachment_hits={c['attachment_hits_total']} incumbent_matches={c['enrichments']} "
        f"errors={len(summary['errors'])}"
    )
    print(f"[tango] artifacts: {summary['artifacts']}")
    return 0 if not summary["errors"] else 1


if __name__ == "__main__":
    sys.exit(main())
