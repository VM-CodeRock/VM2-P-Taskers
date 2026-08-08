"""End-to-end monitor dry-run using MockTangoClient (no network, no API key)."""

from __future__ import annotations

import json
import os
import tempfile
import unittest

from tango import monitor


class MonitorDryRunTests(unittest.TestCase):
    def test_mock_run_writes_artifacts(self):
        with tempfile.TemporaryDirectory() as tmp:
            summary = monitor.run(mock=True, output_dir=tmp)
            self.assertTrue(summary["mock"])
            self.assertIn("artifacts", summary)
            for kind in ("json", "markdown", "html"):
                path = summary["artifacts"][kind]
                self.assertTrue(os.path.exists(path), f"{kind} artifact missing")
                self.assertGreater(os.path.getsize(path), 100)

    def test_mock_run_produces_expected_counts(self):
        with tempfile.TemporaryDirectory() as tmp:
            summary = monitor.run(mock=True, output_dir=tmp)
            c = summary["counts"]
            self.assertEqual(c["opportunities"], 2)
            self.assertEqual(c["forecasts"], 1)
            self.assertGreaterEqual(c["attachment_hits_total"], 1)

    def test_attachment_hits_attached_to_matching_opp(self):
        with tempfile.TemporaryDirectory() as tmp:
            summary = monitor.run(mock=True, output_dir=tmp)
            opps_with_hits = [o for o in summary["opportunities"] if o.get("attachment_hits")]
            self.assertTrue(opps_with_hits, "expected at least one opp to have attachment_hits")
            self.assertEqual(opps_with_hits[0]["solicitation_number"], "W911NF-26-R-0042")

    def test_incumbent_match_by_sol_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            summary = monitor.run(mock=True, output_dir=tmp)
            opp = next(o for o in summary["opportunities"] if o["solicitation_number"] == "W911NF-26-R-0042")
            self.assertEqual(opp.get("incumbent_matched_by"), "solicitation_identifier")
            self.assertEqual(len(opp["incumbent_candidates"]), 1)

    def test_push_todoist_flag_does_not_push(self):
        """Safety: --push-todoist must not actually push until operator wires it."""
        with tempfile.TemporaryDirectory() as tmp:
            summary = monitor.run(mock=True, output_dir=tmp, push_todoist=True)
            self.assertTrue(summary["push_todoist"])  # recorded
            # No side effects beyond the dry-run artifacts; flag just logs a warning.

    def test_keyword_cluster_parsing(self):
        parsed = monitor._parse_clusters(["ai=machine learning", "cyber=zero trust"])
        self.assertEqual(parsed, {"ai": "machine learning", "cyber": "zero trust"})

    def test_keyword_cluster_bad_format_raises(self):
        with self.assertRaises(ValueError):
            monitor._parse_clusters(["missing-equals"])

    def test_main_mock_exit_code_zero(self):
        with tempfile.TemporaryDirectory() as tmp:
            rc = monitor.main(["--mock", "--output-dir", tmp])
            self.assertEqual(rc, 0)
            artifacts = [f for f in os.listdir(tmp) if f.startswith("tango-dry-run-")]
            self.assertEqual(len(artifacts), 3)  # json, md, html


if __name__ == "__main__":
    unittest.main()
