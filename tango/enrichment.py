"""Incumbent / recompete enrichment for Tango opportunities.

Given a normalized Tango opportunity, we try to locate the prior contract by:

1. Exact match on ``solicitation_identifier`` when present.
2. Agency + NAICS + a forward-looking ``expiring`` window.

This is best-effort and never fails the caller: if Tango is unreachable or
nothing matches, we return an empty enrichment dict.
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Any, Dict, List, Optional

from .client import TangoAPIError, TangoClient
from .config import RECOMPETE_WINDOW_DAYS
from .normalizer import normalize_contract

log = logging.getLogger(__name__)


def enrich_opportunity_with_incumbent(
    client: TangoClient,
    opportunity: Dict[str, Any],
    *,
    window_days: int = RECOMPETE_WINDOW_DAYS,
    max_candidates: int = 5,
) -> Dict[str, Any]:
    """Look up incumbent/recompete candidates for a normalized opportunity.

    Returns a dict with keys:
        matched_by: "solicitation_identifier" | "agency_naics_window" | None
        candidates: list[normalized contract dict]
    """
    result: Dict[str, Any] = {"matched_by": None, "candidates": []}
    sol_id = opportunity.get("solicitation_number") or ""

    if sol_id:
        try:
            rows = client.contracts(
                solicitation_identifier=sol_id,
                limit=max_candidates,
                max_pages=1,
                max_results=max_candidates,
            )
        except TangoAPIError as exc:
            log.warning("contracts lookup by sol_id failed: %s", exc)
            rows = []
        if rows:
            result["matched_by"] = "solicitation_identifier"
            result["candidates"] = [normalize_contract(r) for r in rows]
            return result

    agency = opportunity.get("agency") or opportunity.get("department")
    naics = opportunity.get("naics")
    if not (agency and naics):
        return result

    today = date.today()
    window_start = today.isoformat()
    window_end = (today + timedelta(days=window_days)).isoformat()
    try:
        rows = client.contracts(
            awarding_agency=[agency],
            naics=[naics],
            expiring_gte=window_start,
            expiring_lte=window_end,
            ordering="-action_date",
            limit=max_candidates,
            max_pages=1,
            max_results=max_candidates,
        )
    except TangoAPIError as exc:
        log.warning("contracts lookup by agency+naics failed: %s", exc)
        rows = []

    if rows:
        result["matched_by"] = "agency_naics_window"
        result["candidates"] = [normalize_contract(r) for r in rows]
    return result


def batch_enrich(
    client: TangoClient,
    opportunities: List[Dict[str, Any]],
    *,
    max_enrichments: int = 25,
    window_days: int = RECOMPETE_WINDOW_DAYS,
) -> List[Dict[str, Any]]:
    """Return a parallel list of enrichment results (same order, bounded count)."""
    out: List[Dict[str, Any]] = []
    for i, opp in enumerate(opportunities):
        if i >= max_enrichments:
            out.append({"matched_by": None, "candidates": [], "skipped": True})
            continue
        out.append(enrich_opportunity_with_incumbent(client, opp, window_days=window_days))
    return out
