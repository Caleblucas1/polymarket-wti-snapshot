import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from signal_research.reliability import (
    validate_chart_html,
    validate_probability_csv,
    validate_published_manifest,
    validate_signal_records,
)


class ReliabilityTests(unittest.TestCase):
    def write(self, root: Path, name: str, content: str) -> Path:
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path

    def test_current_signal_records_are_internally_consistent(self):
        issues = validate_signal_records(
            "signal_candidates.json",
            "signal_records/evidence_ledger.jsonl",
            "signal_records/confidence_history.jsonl",
            "signal_records/live_status.json",
            "signal_records/performance_history.json",
        )
        self.assertEqual([], issues)

    def test_detects_orphans_score_mismatch_and_unsafe_live_right(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            registry = self.write(root, "registry.json", json.dumps({"signals": [{"registry_id": "A", "aliases": ["S-1"]}]}))
            evidence = self.write(root, "evidence.jsonl", json.dumps({"registry_id": "B", "evidence_id": "e1"}) + "\n")
            confidence = self.write(root, "confidence.jsonl", json.dumps({"registry_id": "A", "score": 50, "components": {"x": 40}}) + "\n")
            live = self.write(root, "live.json", json.dumps({"signals": [{"registry_id": "A", "capital_right": "capped_live", "operational_status": "degraded"}]}))
            performance = self.write(root, "performance.json", json.dumps({"observations": []}))
            codes = {issue.code for issue in validate_signal_records(registry, evidence, confidence, live, performance)}
            self.assertIn("records.orphan_registry_id", codes)
            self.assertIn("confidence.component_mismatch", codes)
            self.assertIn("live_status.unsafe_live_right", codes)

    def test_detects_duplicate_performance_and_bad_net_return(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            registry = self.write(root, "registry.json", json.dumps({"signals": [{"registry_id": "A", "aliases": []}]}))
            evidence = self.write(root, "evidence.jsonl", json.dumps({"registry_id": "A", "evidence_id": "e1"}) + "\n")
            confidence = self.write(root, "confidence.jsonl", json.dumps({"registry_id": "A", "score": 0, "components": {}}) + "\n")
            live = self.write(root, "live.json", json.dumps({"signals": [{"registry_id": "A", "capital_right": "none", "operational_status": "active"}]}))
            row = {"registry_id": "A", "timestamp": "t", "rule_version": 1, "gross_return": 0.1, "cost_return": 0.02, "net_return": 0.5}
            performance = self.write(root, "performance.json", json.dumps({"observations": [row, row]}))
            codes = {issue.code for issue in validate_signal_records(registry, evidence, confidence, live, performance)}
            self.assertIn("performance.duplicate_observation", codes)
            self.assertIn("performance.net_return_mismatch", codes)

    def test_chart_validator_detects_stale_and_non_finite_payloads(self):
        with tempfile.TemporaryDirectory() as directory:
            chart = self.write(Path(directory), "chart.html", "<script>Plotly.newPlot('x', {data: [NaN], layout: {}})</script>")
            codes = {issue.code for issue in validate_chart_html(chart, expected_latest_date="2026-07-31")}
            self.assertIn("chart.stale_latest_date", codes)
            self.assertIn("chart.non_finite_value", codes)

    def test_manifest_verifies_file_hash_and_latest_date(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            chart = self.write(root, "chart.html", "<script>Plotly.newPlot('x', {data: [], layout: {title:'2026-07-31'}})</script>")
            digest = hashlib.sha256(chart.read_bytes()).hexdigest()
            manifest = self.write(root, "latest.json", json.dumps({"charts": [{"filename": "chart.html", "sha256": digest, "latest_date": "2026-07-31"}]}))
            self.assertEqual([], validate_published_manifest(manifest, root))
            chart.write_text("changed", encoding="utf-8")
            codes = {issue.code for issue in validate_published_manifest(manifest, root)}
            self.assertIn("manifest.hash_mismatch", codes)

    def test_probability_csv_detects_range_order_and_duplicates(self):
        with tempfile.TemporaryDirectory() as directory:
            csv_path = self.write(
                Path(directory),
                "snapshot.csv",
                "market,2026-07-31,2026-07-30\nA,101,50\nA,20,not-a-number\n",
            )
            codes = {issue.code for issue in validate_probability_csv(csv_path)}
            self.assertIn("csv.non_monotonic_dates", codes)
            self.assertIn("csv.duplicate_identity", codes)
            self.assertIn("csv.probability_out_of_range", codes)
            self.assertIn("csv.non_numeric_probability", codes)


if __name__ == "__main__":
    unittest.main()
