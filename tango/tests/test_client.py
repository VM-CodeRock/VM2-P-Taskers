"""Unit tests for tango.client — uses a FakeSession, no real HTTP."""

from __future__ import annotations

import json
import os
import unittest
from typing import Any, Dict, List, Optional
from unittest import mock

from tango.client import (
    TangoAPIError,
    TangoAuthError,
    TangoClient,
    TangoRateLimitError,
    _clean_params,
    _extract_results,
    _join_multi,
)


class FakeResponse:
    def __init__(self, status_code: int = 200, payload: Any = None, headers: Optional[Dict[str, str]] = None, text: str = ""):
        self.status_code = status_code
        self._payload = payload
        self.headers = headers or {}
        self.text = text or (json.dumps(payload) if payload is not None else "")

    def json(self) -> Any:
        if self._payload is None:
            raise ValueError("no json")
        return self._payload


class FakeSession:
    """Session double that returns queued responses and records calls."""

    def __init__(self, queue: List[FakeResponse]):
        self.queue = list(queue)
        self.calls: List[Dict[str, Any]] = []

    def get(self, url: str, params: Optional[Dict[str, Any]] = None, headers: Optional[Dict[str, str]] = None, timeout: int = 0):
        self.calls.append({"url": url, "params": params or {}, "headers": headers or {}, "timeout": timeout})
        if not self.queue:
            raise AssertionError(f"unexpected extra request to {url}")
        return self.queue.pop(0)


class ClientHelperTests(unittest.TestCase):
    def test_join_multi_pipe_separates_values(self):
        self.assertEqual(_join_multi(["541511", "541512"]), "541511|541512")
        self.assertEqual(_join_multi(None), None)
        self.assertEqual(_join_multi([]), None)
        self.assertEqual(_join_multi("already_a_string"), "already_a_string")

    def test_clean_params_drops_none_and_empty(self):
        self.assertEqual(_clean_params({"a": 1, "b": None, "c": ""}), {"a": 1})

    def test_extract_results_handles_multiple_shapes(self):
        self.assertEqual(_extract_results({"results": [1, 2]}), [1, 2])
        self.assertEqual(_extract_results({"data": [3]}), [3])
        self.assertEqual(_extract_results([10, 11]), [10, 11])
        self.assertEqual(_extract_results("garbage"), [])


class ClientAuthTests(unittest.TestCase):
    def test_raises_when_no_api_key(self):
        session = FakeSession([])
        c = TangoClient(api_key=None, session=session)
        with self.assertRaises(TangoAuthError):
            c.get("api/opportunities/")

    def test_sends_x_api_key_header(self):
        session = FakeSession([FakeResponse(200, {"results": []})])
        c = TangoClient(api_key="secret", session=session)
        c.get("api/opportunities/")
        self.assertEqual(session.calls[0]["headers"].get("X-API-KEY"), "secret")

    def test_custom_auth_header(self):
        session = FakeSession([FakeResponse(200, {"results": []})])
        c = TangoClient(api_key="secret", auth_header="Authorization", session=session)
        c.get("api/opportunities/")
        headers = session.calls[0]["headers"]
        self.assertEqual(headers.get("Authorization"), "secret")
        self.assertNotIn("X-API-KEY", headers)

    def test_401_raises_auth_error(self):
        session = FakeSession([FakeResponse(401, {"detail": "bad key"})])
        c = TangoClient(api_key="bad", session=session)
        with self.assertRaises(TangoAuthError):
            c.get("api/opportunities/")


class RetryTests(unittest.TestCase):
    def setUp(self) -> None:
        # No real sleeping during retries
        self._sleep_patch = mock.patch("tango.client.time.sleep", lambda *_: None)
        self._sleep_patch.start()
        self.addCleanup(self._sleep_patch.stop)

    def test_retries_on_429_then_succeeds(self):
        session = FakeSession([
            FakeResponse(429, headers={"Retry-After": "0"}),
            FakeResponse(200, {"results": [{"id": 1}]}),
        ])
        c = TangoClient(api_key="k", session=session, max_retries=3)
        data = c.get("api/opportunities/")
        self.assertEqual(data, {"results": [{"id": 1}]})
        self.assertEqual(len(session.calls), 2)

    def test_retries_on_5xx_then_raises(self):
        session = FakeSession([FakeResponse(503) for _ in range(4)])
        c = TangoClient(api_key="k", session=session, max_retries=3)
        with self.assertRaises(TangoAPIError):
            c.get("api/opportunities/")
        # max_retries=3 means we should see 3 attempts
        self.assertEqual(len(session.calls), 3)

    def test_429_exhausted_raises_rate_limit(self):
        session = FakeSession([FakeResponse(429) for _ in range(4)])
        c = TangoClient(api_key="k", session=session, max_retries=2)
        with self.assertRaises(TangoRateLimitError):
            c.get("api/opportunities/")

    def test_4xx_non_retryable(self):
        session = FakeSession([FakeResponse(400, {"detail": "bad query"})])
        c = TangoClient(api_key="k", session=session, max_retries=3)
        with self.assertRaises(TangoAPIError):
            c.get("api/opportunities/")
        self.assertEqual(len(session.calls), 1)


class PaginationTests(unittest.TestCase):
    def test_follows_next_url_until_exhausted(self):
        page1 = {"results": [{"id": 1}, {"id": 2}], "next": "https://t/api/opportunities/?page=2"}
        page2 = {"results": [{"id": 3}], "next": None}
        session = FakeSession([FakeResponse(200, page1), FakeResponse(200, page2)])
        c = TangoClient(api_key="k", session=session)
        rows = list(c.paginate("api/opportunities/"))
        self.assertEqual([r["id"] for r in rows], [1, 2, 3])
        # page 2 should have been called with params=None (next URL already carries them)
        self.assertEqual(session.calls[1]["params"], {})

    def test_respects_max_results(self):
        page1 = {"results": [{"id": i} for i in range(10)], "next": "https://t/api/opportunities/?page=2"}
        session = FakeSession([FakeResponse(200, page1)])
        c = TangoClient(api_key="k", session=session)
        rows = list(c.paginate("api/opportunities/", max_results=3))
        self.assertEqual(len(rows), 3)

    def test_respects_max_pages(self):
        session = FakeSession([
            FakeResponse(200, {"results": [{"id": 1}], "next": "next-url"}),
            FakeResponse(200, {"results": [{"id": 2}], "next": "next-url"}),
        ])
        c = TangoClient(api_key="k", session=session)
        rows = list(c.paginate("api/opportunities/", max_pages=2))
        self.assertEqual(len(rows), 2)


class EndpointTests(unittest.TestCase):
    def test_opportunities_builds_expected_params(self):
        session = FakeSession([FakeResponse(200, {"results": []})])
        c = TangoClient(api_key="k", session=session)
        c.opportunities(naics=["541511", "541512"], agency=["DOD"], search="AI", limit=10, max_pages=1)
        params = session.calls[0]["params"]
        self.assertEqual(params["naics"], "541511|541512")
        self.assertEqual(params["agency"], "DOD")
        self.assertEqual(params["search"], "AI")
        self.assertEqual(params["active"], "true")
        self.assertEqual(params["limit"], 10)

    def test_contracts_passes_expiring_window(self):
        session = FakeSession([FakeResponse(200, {"results": []})])
        c = TangoClient(api_key="k", session=session)
        c.contracts(
            awarding_agency=["VA"],
            naics=["541512"],
            expiring_gte="2026-04-24",
            expiring_lte="2027-04-24",
            max_pages=1,
        )
        params = session.calls[0]["params"]
        self.assertEqual(params["expiring_gte"], "2026-04-24")
        self.assertEqual(params["expiring_lte"], "2027-04-24")
        self.assertEqual(params["awarding_agency"], "VA")

    def test_attachment_search_sends_query(self):
        session = FakeSession([FakeResponse(200, {"results": []})])
        c = TangoClient(api_key="k", session=session)
        c.attachment_search(query="large language model", naics=["541512"], max_pages=1)
        params = session.calls[0]["params"]
        self.assertEqual(params["q"], "large language model")

    def test_shape_parameter_passed_through(self):
        session = FakeSession([FakeResponse(200, {"results": []})])
        c = TangoClient(api_key="k", session=session)
        c.opportunities(shape="detail", max_pages=1)
        self.assertEqual(session.calls[0]["params"]["shape"], "detail")


if __name__ == "__main__":
    unittest.main()
