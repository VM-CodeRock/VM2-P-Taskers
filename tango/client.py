"""Read-only HTTP client for the Tango / MakeGov REST API.

Auth style confirmed from https://tango.makegov.com/docs/getting-started/authentication
as ``X-API-KEY: <key>``. The auth header name can be overridden via the
``auth_header`` constructor argument or ``TANGO_AUTH_HEADER`` env var if Tango
later standardizes on a different header (e.g. ``Authorization: Api-Key ...``).
"""

from __future__ import annotations

import json
import logging
import os
import random
import time
from typing import Any, Dict, Iterable, Iterator, List, Optional
from urllib.parse import urlencode, urljoin

import requests

log = logging.getLogger(__name__)

DEFAULT_BASE_URL = "https://tango.makegov.com"
DEFAULT_AUTH_HEADER = "X-API-KEY"
DEFAULT_TIMEOUT = 30
DEFAULT_MAX_RETRIES = 4
DEFAULT_USER_AGENT = "Changeis-VM2-OPP-Tango/0.1 (+read-only)"


class TangoAPIError(RuntimeError):
    """Generic Tango API failure."""

    def __init__(self, message: str, status_code: Optional[int] = None, body: Any = None):
        super().__init__(message)
        self.status_code = status_code
        self.body = body


class TangoAuthError(TangoAPIError):
    """401/403 from Tango."""


class TangoRateLimitError(TangoAPIError):
    """429 after retries exhausted."""


class TangoClient:
    """Thin read-only wrapper over the Tango REST API.

    The client is deliberately narrow: GET-only, no writes, no webhook
    registration. It supports pagination, shape selection, and bounded
    retry/backoff for 429 and 5xx. Pass ``session`` to inject a mock for
    tests.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: str = DEFAULT_BASE_URL,
        auth_header: Optional[str] = None,
        timeout: int = DEFAULT_TIMEOUT,
        max_retries: int = DEFAULT_MAX_RETRIES,
        session: Optional[requests.Session] = None,
        user_agent: str = DEFAULT_USER_AGENT,
    ) -> None:
        self.api_key = api_key or os.environ.get("TANGO_API_KEY")
        self.base_url = base_url.rstrip("/") + "/"
        self.auth_header = (
            auth_header
            or os.environ.get("TANGO_AUTH_HEADER")
            or DEFAULT_AUTH_HEADER
        )
        self.timeout = timeout
        self.max_retries = max_retries
        self.user_agent = user_agent
        self.session = session or requests.Session()

    # ---- low level ----------------------------------------------------

    def _headers(self) -> Dict[str, str]:
        headers = {
            "Accept": "application/json",
            "User-Agent": self.user_agent,
        }
        if self.api_key:
            headers[self.auth_header] = self.api_key
        return headers

    def _request(self, path_or_url: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        if path_or_url.startswith("http"):
            url = path_or_url
        else:
            url = urljoin(self.base_url, path_or_url.lstrip("/"))

        if not self.api_key:
            raise TangoAuthError(
                "TANGO_API_KEY is not set. Export it or pass api_key=... "
                "(for local development, use --mock to run without an API key)."
            )

        attempt = 0
        while True:
            attempt += 1
            try:
                resp = self.session.get(
                    url,
                    params=_clean_params(params),
                    headers=self._headers(),
                    timeout=self.timeout,
                )
            except requests.RequestException as exc:
                if attempt >= self.max_retries:
                    raise TangoAPIError(f"network error after {attempt} attempts: {exc}") from exc
                _sleep_backoff(attempt)
                continue

            if resp.status_code == 200:
                try:
                    return resp.json()
                except ValueError as exc:
                    raise TangoAPIError(f"non-JSON 200 response from {url}") from exc

            if resp.status_code in (401, 403):
                raise TangoAuthError(
                    f"auth error {resp.status_code} from Tango (check TANGO_API_KEY and header '{self.auth_header}')",
                    status_code=resp.status_code,
                    body=_safe_body(resp),
                )

            if resp.status_code == 429 or 500 <= resp.status_code < 600:
                if attempt >= self.max_retries:
                    cls = TangoRateLimitError if resp.status_code == 429 else TangoAPIError
                    raise cls(
                        f"Tango API {resp.status_code} after {attempt} attempts at {url}",
                        status_code=resp.status_code,
                        body=_safe_body(resp),
                    )
                retry_after = _retry_after_seconds(resp)
                _sleep_backoff(attempt, retry_after=retry_after)
                continue

            # Other 4xx — don't retry.
            raise TangoAPIError(
                f"Tango API {resp.status_code} at {url}",
                status_code=resp.status_code,
                body=_safe_body(resp),
            )

    # ---- pagination ---------------------------------------------------

    def paginate(
        self,
        path: str,
        params: Optional[Dict[str, Any]] = None,
        max_pages: int = 20,
        max_results: Optional[int] = None,
    ) -> Iterator[Dict[str, Any]]:
        """Yield individual records across paginated Tango responses.

        Tango uses DRF-style page-number pagination — response contains
        ``results``, ``next``, ``previous``, ``count``. We follow ``next``
        until exhausted or ``max_pages`` reached.
        """
        yielded = 0
        page_url: Optional[str] = path
        page_params: Optional[Dict[str, Any]] = dict(params or {})
        for page_num in range(1, max_pages + 1):
            data = self._request(page_url, page_params)
            # Once we follow `next`, the URL already has the params baked in.
            page_params = None
            results = _extract_results(data)
            for row in results:
                yield row
                yielded += 1
                if max_results is not None and yielded >= max_results:
                    return
            next_url = data.get("next") if isinstance(data, dict) else None
            if not next_url:
                return
            page_url = next_url

    def get(self, path: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """One-shot GET returning raw JSON (no pagination)."""
        return self._request(path, params)

    # ---- high level endpoints -----------------------------------------

    def opportunities(
        self,
        *,
        naics: Optional[Iterable[str]] = None,
        agency: Optional[Iterable[str]] = None,
        psc: Optional[Iterable[str]] = None,
        search: Optional[str] = None,
        set_aside: Optional[str] = None,
        notice_type: Optional[str] = None,
        solicitation_number: Optional[str] = None,
        first_notice_date_gte: Optional[str] = None,
        first_notice_date_lte: Optional[str] = None,
        response_deadline_gte: Optional[str] = None,
        response_deadline_lte: Optional[str] = None,
        active: Optional[bool] = True,
        ordering: Optional[str] = "-first_notice_date",
        shape: Optional[str] = None,
        limit: int = 50,
        max_pages: int = 10,
        max_results: Optional[int] = None,
        extra: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """Search /api/opportunities/ with Changeis-relevant filters."""
        params: Dict[str, Any] = {
            "naics": _join_multi(naics),
            "agency": _join_multi(agency),
            "psc": _join_multi(psc),
            "search": search,
            "set_aside": set_aside,
            "notice_type": notice_type,
            "solicitation_number": solicitation_number,
            "first_notice_date__gte": first_notice_date_gte,
            "first_notice_date__lte": first_notice_date_lte,
            "response_deadline__gte": response_deadline_gte,
            "response_deadline__lte": response_deadline_lte,
            "active": _bool(active),
            "ordering": ordering,
            "shape": shape,
            "limit": limit,
        }
        if extra:
            params.update(extra)
        return list(self.paginate("api/opportunities/", params, max_pages=max_pages, max_results=max_results))

    def forecasts(
        self,
        *,
        naics: Optional[Iterable[str]] = None,
        agency: Optional[Iterable[str]] = None,
        psc: Optional[Iterable[str]] = None,
        search: Optional[str] = None,
        fy: Optional[str] = None,
        shape: Optional[str] = None,
        limit: int = 50,
        max_pages: int = 10,
        max_results: Optional[int] = None,
        extra: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """Search /api/forecasts/ for planned procurements."""
        params: Dict[str, Any] = {
            "naics": _join_multi(naics),
            "agency": _join_multi(agency),
            "psc": _join_multi(psc),
            "search": search,
            "fy": fy,
            "shape": shape,
            "limit": limit,
        }
        if extra:
            params.update(extra)
        return list(self.paginate("api/forecasts/", params, max_pages=max_pages, max_results=max_results))

    def contracts(
        self,
        *,
        awarding_agency: Optional[Iterable[str]] = None,
        funding_agency: Optional[Iterable[str]] = None,
        naics: Optional[Iterable[str]] = None,
        psc: Optional[Iterable[str]] = None,
        recipient: Optional[str] = None,
        uei: Optional[str] = None,
        piid: Optional[str] = None,
        solicitation_identifier: Optional[str] = None,
        set_aside: Optional[str] = None,
        expiring_gte: Optional[str] = None,
        expiring_lte: Optional[str] = None,
        search: Optional[str] = None,
        ordering: Optional[str] = None,
        shape: Optional[str] = None,
        limit: int = 50,
        max_pages: int = 10,
        max_results: Optional[int] = None,
        extra: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """Search /api/contracts/ for awarded contracts — used for recompete/incumbent enrichment."""
        params: Dict[str, Any] = {
            "awarding_agency": _join_multi(awarding_agency),
            "funding_agency": _join_multi(funding_agency),
            "naics": _join_multi(naics),
            "psc": _join_multi(psc),
            "recipient": recipient,
            "uei": uei,
            "piid": piid,
            "solicitation_identifier": solicitation_identifier,
            "set_aside": set_aside,
            "expiring_gte": expiring_gte,
            "expiring_lte": expiring_lte,
            "search": search,
            "ordering": ordering,
            "shape": shape,
            "limit": limit,
        }
        if extra:
            params.update(extra)
        return list(self.paginate("api/contracts/", params, max_pages=max_pages, max_results=max_results))

    def attachment_search(
        self,
        *,
        query: str,
        naics: Optional[Iterable[str]] = None,
        agency: Optional[Iterable[str]] = None,
        first_notice_date_gte: Optional[str] = None,
        first_notice_date_lte: Optional[str] = None,
        limit: int = 25,
        max_pages: int = 4,
        max_results: Optional[int] = None,
        extra: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """Full-text search across opportunity attachments via /api/opportunities/attachment-search/."""
        params: Dict[str, Any] = {
            "q": query,
            "naics": _join_multi(naics),
            "agency": _join_multi(agency),
            "first_notice_date__gte": first_notice_date_gte,
            "first_notice_date__lte": first_notice_date_lte,
            "limit": limit,
        }
        if extra:
            params.update(extra)
        return list(self.paginate("api/opportunities/attachment-search/", params, max_pages=max_pages, max_results=max_results))


# ---- helpers ----------------------------------------------------------


def _clean_params(params: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not params:
        return {}
    return {k: v for k, v in params.items() if v is not None and v != ""}


def _join_multi(values: Optional[Iterable[Any]]) -> Optional[str]:
    """Tango accepts ``|`` or ``OR`` for multi-value filters."""
    if values is None:
        return None
    if isinstance(values, str):
        return values
    joined = "|".join(str(v).strip() for v in values if str(v).strip())
    return joined or None


def _bool(v: Optional[bool]) -> Optional[str]:
    if v is None:
        return None
    return "true" if v else "false"


def _extract_results(data: Any) -> List[Dict[str, Any]]:
    if isinstance(data, list):
        return data
    if not isinstance(data, dict):
        return []
    for key in ("results", "data", "items", "opportunities", "forecasts", "contracts", "hits"):
        val = data.get(key)
        if isinstance(val, list):
            return val
    return []


def _retry_after_seconds(resp: requests.Response) -> Optional[float]:
    raw = resp.headers.get("Retry-After")
    if not raw:
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def _sleep_backoff(attempt: int, retry_after: Optional[float] = None) -> None:
    if retry_after is not None:
        delay = min(retry_after, 60.0)
    else:
        # exp backoff with jitter: 1s, 2s, 4s, 8s capped at 30
        delay = min(2 ** (attempt - 1), 30) + random.uniform(0, 0.5)
    log.debug("tango backoff sleep %.2fs (attempt %d)", delay, attempt)
    time.sleep(delay)


def _safe_body(resp: requests.Response) -> Any:
    try:
        return resp.json()
    except Exception:
        try:
            return resp.text[:500]
        except Exception:
            return None
