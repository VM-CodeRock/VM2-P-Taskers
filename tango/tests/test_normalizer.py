"""Unit tests for tango.normalizer — shape tolerance and VM2-OPP field parity."""

from __future__ import annotations

import json
import os
import unittest

from tango.normalizer import (
    attachment_snippets,
    normalize_contract,
    normalize_forecast,
    normalize_opportunity,
)

FIX_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "fixtures")


def load(name: str):
    with open(os.path.join(FIX_DIR, name), "r") as f:
        return json.load(f)


VM2_OPP_REQUIRED_FIELDS = {
    "solicitation_number", "title", "agency", "department", "naics",
    "posted_date", "modified_date", "response_deadline", "type",
    "sam_link", "description", "is_canceled",
}


class OpportunityNormalizerTests(unittest.TestCase):
    def test_vm2_opp_shape_parity(self):
        """Normalized opportunity must expose every field the VM2-OPP SAM monitor emits."""
        rows = load("opportunities.json")["results"]
        for r in rows:
            n = normalize_opportunity(r)
            missing = VM2_OPP_REQUIRED_FIELDS - set(n.keys())
            self.assertFalse(missing, f"missing fields: {missing}")
            self.assertEqual(n["source"], "tango.opportunity")

    def test_agency_extracted_from_nested_dict(self):
        n = normalize_opportunity({
            "id": "x",
            "agency": {"name": "Department of the Navy", "department": "Department of Defense"},
            "naics": [{"code": "541512"}],
            "solicitation_number": "ABC-1",
            "first_notice_date": "2026-04-01T00:00:00Z",
        })
        self.assertEqual(n["agency"], "Department of the Navy")
        self.assertEqual(n["department"], "Department of Defense")
        self.assertEqual(n["naics"], "541512")
        self.assertEqual(n["posted_date"], "2026-04-01")

    def test_description_is_html_stripped_and_truncated(self):
        long = "<p>" + ("word " * 400) + "</p>"
        n = normalize_opportunity({"id": "x", "description": long})
        self.assertNotIn("<p>", n["description"])
        self.assertLessEqual(len(n["description"]), 500)

    def test_tango_link_built_from_id_when_missing(self):
        n = normalize_opportunity({"id": "opp-123"})
        self.assertEqual(n["tango_link"], "https://tango.makegov.com/opportunities/opp-123/")

    def test_naics_handles_string_and_list_and_dict(self):
        self.assertEqual(normalize_opportunity({"naics": "541611"})["naics"], "541611")
        self.assertEqual(normalize_opportunity({"naics": [{"code": "541611"}]})["naics"], "541611")
        self.assertEqual(normalize_opportunity({"primary_naics": {"code": "541611"}})["naics"], "541611")

    def test_attachments_count(self):
        n = normalize_opportunity({"id": "x", "attachments": [{"filename": "a"}, {"filename": "b"}]})
        self.assertEqual(n["attachments_count"], 2)

    def test_canceled_field_normalized_to_bool(self):
        self.assertTrue(normalize_opportunity({"id": "x", "is_canceled": True})["is_canceled"])
        self.assertTrue(normalize_opportunity({"id": "x", "cancelled": True})["is_canceled"])
        self.assertFalse(normalize_opportunity({"id": "x"})["is_canceled"])


class ForecastNormalizerTests(unittest.TestCase):
    def test_forecast_uses_id_as_solicitation_number(self):
        rows = load("forecasts.json")["results"]
        n = normalize_forecast(rows[0])
        self.assertEqual(n["source"], "tango.forecast")
        self.assertEqual(n["solicitation_number"], "fc-001")
        self.assertEqual(n["type"], "Forecast")
        self.assertEqual(n["fiscal_year"], "FY27")
        self.assertEqual(n["naics"], "541512")


class ContractNormalizerTests(unittest.TestCase):
    def test_contract_captures_incumbent_fields(self):
        rows = load("contracts.json")["results"]
        n = normalize_contract(rows[0])
        self.assertEqual(n["source"], "tango.contract")
        self.assertEqual(n["piid"], "W911NF20D0001")
        self.assertEqual(n["solicitation_identifier"], "W911NF-26-R-0042")
        self.assertEqual(n["recipient"], "Acme Federal Solutions LLC")
        self.assertEqual(n["uei"], "ABC123DEF456")
        self.assertEqual(n["period_of_performance_end"], "2026-09-30")


class AttachmentSnippetTests(unittest.TestCase):
    def test_snippets_from_highlights(self):
        row = load("attachment_search.json")["results"][0]
        snips = attachment_snippets(row)
        self.assertEqual(len(snips), 2)
        self.assertIn("large language model", snips[0]["text"])
        self.assertEqual(snips[0]["page"], 4)

    def test_snippets_handles_missing_highlights(self):
        snips = attachment_snippets({"snippet": "fallback text"})
        self.assertEqual(len(snips), 1)
        self.assertEqual(snips[0]["text"], "fallback text")

    def test_snippets_truncate_long_text(self):
        snips = attachment_snippets({"highlights": ["x" * 1000]}, max_chars=50)
        self.assertEqual(len(snips[0]["text"]), 50)


if __name__ == "__main__":
    unittest.main()
