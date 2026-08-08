"""Normalize Tango API records into the VM2-OPP opportunity shape.

The VM2-OPP SAM monitor (see ``backups/scripts/run_sam_monitor.py``) emits
records with these fields:

    solicitation_number, title, agency, department, naics, posted_date,
    modified_date, response_deadline, type, sam_link, description, is_canceled

Downstream consumers (Changeis RAG scorer, Todoist deep-dive queue, combined
daily brief) rely on that shape. The normalizer below maps Tango opportunity,
forecast, and contract payloads into compatible dicts, with an additional
``source`` discriminator so the daily brief can route them appropriately.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional


def _clean_html(s: Optional[str]) -> str:
    if not s:
        return ""
    return re.sub(r"<[^>]+>", "", s).strip()


def _first(*values: Any) -> Any:
    for v in values:
        if v not in (None, "", [], {}):
            return v
    return None


def _date10(v: Any) -> str:
    if not v:
        return ""
    s = str(v)
    return s[:10]


def _agency_fields(record: Dict[str, Any]) -> Dict[str, str]:
    """Extract department + agency strings from many possible Tango shapes."""
    dept = ""
    agency = ""

    # Common shapes observed across DRF APIs
    dept = _first(
        record.get("department"),
        record.get("department_name"),
        (record.get("awarding_agency") or {}).get("department") if isinstance(record.get("awarding_agency"), dict) else None,
        (record.get("agency") or {}).get("department") if isinstance(record.get("agency"), dict) else None,
    ) or ""

    agency_obj = record.get("agency") or record.get("awarding_agency") or record.get("funding_agency")
    if isinstance(agency_obj, dict):
        agency = _first(agency_obj.get("name"), agency_obj.get("code"), agency_obj.get("abbreviation")) or ""
    elif isinstance(agency_obj, str):
        agency = agency_obj
    agency = agency or _first(record.get("agency_name"), record.get("agency_code"), "") or ""
    if not dept:
        dept = agency
    return {"department": str(dept or ""), "agency": str(agency or dept or "")}


def _naics_str(record: Dict[str, Any]) -> str:
    n = record.get("naics") or record.get("naics_code") or record.get("primary_naics")
    if isinstance(n, list):
        # prefer the first non-empty code
        for item in n:
            if isinstance(item, dict):
                code = item.get("code") or item.get("naics")
                if code:
                    return str(code)
            elif item:
                return str(item)
        return ""
    if isinstance(n, dict):
        return str(n.get("code") or n.get("naics") or "")
    return str(n or "")


def _psc_str(record: Dict[str, Any]) -> str:
    p = record.get("psc") or record.get("psc_code")
    if isinstance(p, list):
        for item in p:
            if isinstance(item, dict):
                code = item.get("code") or item.get("psc")
                if code:
                    return str(code)
            elif item:
                return str(item)
        return ""
    if isinstance(p, dict):
        return str(p.get("code") or p.get("psc") or "")
    return str(p or "")


def _tango_url(record: Dict[str, Any], kind: str) -> str:
    direct = _first(record.get("url"), record.get("tango_url"), record.get("link"))
    if direct:
        return str(direct)
    ident = _first(record.get("id"), record.get("uuid"), record.get("pk"))
    if not ident:
        return ""
    base = {
        "opportunity": "https://tango.makegov.com/opportunities/",
        "forecast": "https://tango.makegov.com/forecasts/",
        "contract": "https://tango.makegov.com/contracts/",
    }.get(kind, "https://tango.makegov.com/")
    return f"{base}{ident}/"


def normalize_opportunity(record: Dict[str, Any]) -> Dict[str, Any]:
    """Map a Tango opportunity row to the VM2-OPP shape."""
    sol_num = str(
        _first(
            record.get("solicitation_number"),
            record.get("solicitation_identifier"),
            record.get("notice_id"),
            record.get("id"),
            "",
        )
    ).strip()
    title = str(record.get("title") or record.get("subject") or "").strip()
    descr = _clean_html(
        _first(
            record.get("description"),
            record.get("summary"),
            record.get("synopsis"),
            "",
        )
    )[:500]

    agency = _agency_fields(record)
    normalized = {
        "source": "tango.opportunity",
        "solicitation_number": sol_num,
        "title": title,
        "agency": agency["agency"],
        "department": agency["department"],
        "naics": _naics_str(record),
        "psc": _psc_str(record),
        "posted_date": _date10(_first(record.get("first_notice_date"), record.get("posted_date"), record.get("publish_date"))),
        "modified_date": _date10(_first(record.get("last_notice_date"), record.get("modified_date"), record.get("updated_at"))),
        "response_deadline": _date10(_first(record.get("response_deadline"), record.get("response_date"))),
        "type": str(_first(record.get("notice_type"), record.get("type"), "") or ""),
        "set_aside": str(_first(record.get("set_aside"), record.get("setaside"), "") or ""),
        "place_of_performance": str(_first(record.get("place_of_performance"), "") or ""),
        "sam_link": str(_first(record.get("sam_url"), record.get("sam_link"), "") or ""),
        "tango_link": _tango_url(record, "opportunity"),
        "description": descr,
        "is_canceled": bool(record.get("is_canceled") or record.get("cancelled") or False),
        "attachments_count": _attachments_count(record),
        "raw_id": _first(record.get("id"), record.get("uuid")),
    }
    return normalized


def normalize_forecast(record: Dict[str, Any]) -> Dict[str, Any]:
    """Map a Tango forecast row into the VM2-OPP shape (with source=tango.forecast)."""
    ident = str(_first(record.get("id"), record.get("forecast_id"), record.get("uuid"), "") or "")
    title = str(record.get("title") or record.get("requirement") or "").strip()
    descr = _clean_html(_first(record.get("description"), record.get("summary"), "") or "")[:500]

    agency = _agency_fields(record)
    return {
        "source": "tango.forecast",
        "solicitation_number": ident,  # forecasts rarely have a sol number; use id
        "title": title,
        "agency": agency["agency"],
        "department": agency["department"],
        "naics": _naics_str(record),
        "psc": _psc_str(record),
        "posted_date": _date10(_first(record.get("posted_date"), record.get("created_at"))),
        "modified_date": _date10(_first(record.get("modified_date"), record.get("updated_at"))),
        "response_deadline": _date10(_first(record.get("estimated_solicitation_date"), record.get("expected_award_date"))),
        "fiscal_year": str(_first(record.get("fy"), record.get("fiscal_year"), "") or ""),
        "estimated_value": _first(record.get("estimated_value"), record.get("value")),
        "type": "Forecast",
        "set_aside": str(_first(record.get("set_aside"), "") or ""),
        "sam_link": "",
        "tango_link": _tango_url(record, "forecast"),
        "description": descr,
        "is_canceled": False,
        "raw_id": _first(record.get("id"), record.get("uuid")),
    }


def normalize_contract(record: Dict[str, Any]) -> Dict[str, Any]:
    """Map a Tango contract row. Used for incumbent/recompete enrichment."""
    piid = str(_first(record.get("piid"), record.get("contract_id"), "") or "")
    sol_id = str(_first(record.get("solicitation_identifier"), record.get("solicitation_number"), "") or "")
    recipient = _first(record.get("recipient"), record.get("recipient_name"))
    if isinstance(recipient, dict):
        recipient = _first(recipient.get("name"), recipient.get("legal_business_name"))
    uei = str(_first(record.get("uei"), record.get("recipient_uei"), "") or "")

    agency = _agency_fields(record)
    return {
        "source": "tango.contract",
        "piid": piid,
        "solicitation_identifier": sol_id,
        "title": str(record.get("title") or record.get("description_of_requirement") or "")[:200],
        "recipient": str(recipient or ""),
        "uei": uei,
        "awarding_agency": agency["agency"],
        "department": agency["department"],
        "naics": _naics_str(record),
        "psc": _psc_str(record),
        "action_date": _date10(_first(record.get("action_date"), record.get("awarded_at"))),
        "period_of_performance_start": _date10(record.get("period_of_performance_start")),
        "period_of_performance_end": _date10(_first(record.get("period_of_performance_end"), record.get("ultimate_completion_date"))),
        "obligated_amount": _first(record.get("obligated_amount"), record.get("obligation")),
        "base_and_all_options_value": _first(record.get("base_and_all_options_value"), record.get("total_value")),
        "set_aside": str(_first(record.get("set_aside"), "") or ""),
        "tango_link": _tango_url(record, "contract"),
        "raw_id": _first(record.get("id"), record.get("uuid"), piid),
    }


def _attachments_count(record: Dict[str, Any]) -> int:
    a = record.get("attachments")
    if isinstance(a, list):
        return len(a)
    if isinstance(a, int):
        return a
    return int(record.get("attachments_count") or 0)


def attachment_snippets(record: Dict[str, Any], max_chars: int = 240) -> List[Dict[str, Any]]:
    """Extract snippet/hit metadata from an attachment-search response row."""
    snippets: List[Dict[str, Any]] = []
    # Tango attachment search typically returns rows with an attachment + opportunity context
    hits = record.get("highlights") or record.get("snippets") or record.get("hits") or []
    if isinstance(hits, dict):
        hits = [hits]
    for h in hits:
        if isinstance(h, str):
            snippets.append({"text": h[:max_chars]})
        elif isinstance(h, dict):
            text = _first(h.get("text"), h.get("snippet"), h.get("excerpt"), "")
            snippets.append(
                {
                    "text": str(text or "")[:max_chars],
                    "page": h.get("page"),
                    "score": h.get("score"),
                }
            )
    if not snippets:
        # Fall back to a direct content/snippet field
        text = _first(record.get("snippet"), record.get("excerpt"), record.get("content"))
        if text:
            snippets.append({"text": str(text)[:max_chars]})
    return snippets
