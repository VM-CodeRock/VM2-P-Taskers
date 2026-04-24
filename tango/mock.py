"""File-backed mock Tango client for offline dry-runs and tests."""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional

from .client import TangoClient

FIXTURE_DIR = os.path.join(os.path.dirname(__file__), "fixtures")


def _load(name: str) -> Dict[str, Any]:
    with open(os.path.join(FIXTURE_DIR, name), "r") as f:
        return json.load(f)


class MockTangoClient(TangoClient):
    """Drop-in replacement that returns canned fixture data.

    Bypasses HTTP entirely so callers can exercise the pipeline without a
    ``TANGO_API_KEY`` set. Useful for CI and for the ``--mock`` CLI flag.
    """

    def __init__(self) -> None:
        # Skip network setup; we override every caller.
        self.api_key = "mock-key"
        self.base_url = "https://mock.tango.local/"
        self.auth_header = "X-API-KEY"
        self.timeout = 1
        self.max_retries = 1
        self.user_agent = "tango-mock"
        self.session = None

    def opportunities(self, **kwargs) -> List[Dict[str, Any]]:  # type: ignore[override]
        return _load("opportunities.json")["results"]

    def forecasts(self, **kwargs) -> List[Dict[str, Any]]:  # type: ignore[override]
        return _load("forecasts.json")["results"]

    def contracts(self, **kwargs) -> List[Dict[str, Any]]:  # type: ignore[override]
        rows = _load("contracts.json")["results"]
        sol = kwargs.get("solicitation_identifier")
        if sol:
            rows = [r for r in rows if r.get("solicitation_identifier") == sol]
        return rows

    def attachment_search(self, **kwargs) -> List[Dict[str, Any]]:  # type: ignore[override]
        return _load("attachment_search.json")["results"]
