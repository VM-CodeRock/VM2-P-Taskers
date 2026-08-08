"""Unit tests for tango.enrichment — uses MockTangoClient."""

from __future__ import annotations

import unittest
from unittest import mock

from tango.enrichment import batch_enrich, enrich_opportunity_with_incumbent
from tango.mock import MockTangoClient


class EnrichmentTests(unittest.TestCase):
    def test_matches_by_solicitation_identifier(self):
        client = MockTangoClient()
        opp = {"solicitation_number": "W911NF-26-R-0042", "agency": "Department of the Army", "naics": "541512"}
        result = enrich_opportunity_with_incumbent(client, opp)
        self.assertEqual(result["matched_by"], "solicitation_identifier")
        self.assertEqual(len(result["candidates"]), 1)
        self.assertEqual(result["candidates"][0]["recipient"], "Acme Federal Solutions LLC")

    def test_empty_when_no_match(self):
        client = MockTangoClient()
        opp = {"solicitation_number": "", "agency": "", "naics": ""}
        result = enrich_opportunity_with_incumbent(client, opp)
        self.assertIsNone(result["matched_by"])
        self.assertEqual(result["candidates"], [])

    def test_batch_respects_max_enrichments(self):
        client = MockTangoClient()
        opps = [{"solicitation_number": f"S-{i}", "agency": "A", "naics": "541512"} for i in range(30)]
        out = batch_enrich(client, opps, max_enrichments=5)
        self.assertEqual(len(out), 30)
        self.assertEqual(sum(1 for e in out if e.get("skipped")), 25)

    def test_error_path_returns_empty_not_raise(self):
        client = MockTangoClient()
        with mock.patch.object(client, "contracts", side_effect=Exception("boom")):
            # Uses generic Exception — enrichment catches TangoAPIError but a bare
            # Exception should still propagate; we wrap with a specific patch to TangoAPIError.
            pass
        # Re-test with the type enrichment catches:
        from tango.client import TangoAPIError
        with mock.patch.object(client, "contracts", side_effect=TangoAPIError("boom")):
            result = enrich_opportunity_with_incumbent(
                client,
                {"solicitation_number": "X", "agency": "A", "naics": "541512"},
            )
            self.assertEqual(result["candidates"], [])


if __name__ == "__main__":
    unittest.main()
