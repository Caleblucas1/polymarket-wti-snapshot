import json
import tempfile
import unittest
from pathlib import Path

from publish_market_charts import publish_all_charts


class PublishMarketChartsTests(unittest.TestCase):
    def registry(self):
        return {
            "market": {
                "output": "snapshot.csv",
                "chart_output": "chart.html",
            }
        }

    def test_publishes_content_addressed_chart_and_manifest(self):
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            (root / "snapshot.csv").write_text(
                "Market,2026-07-21,2026-07-22\nA,1,2\n", encoding="utf-8"
            )
            (root / "chart.html").write_text(
                "<html>2026-07-21 2026-07-22</html>", encoding="utf-8"
            )
            manifest_path, entries = publish_all_charts(root, registry=self.registry())
            published = Path(entries[0]["published_chart"])
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

            self.assertTrue(published.exists())
            self.assertIn("2026-07-22", published.name)
            self.assertIn(entries[0]["sha256"][:12], published.name)
            self.assertEqual(manifest["charts"][0]["published_chart"], str(published))

    def test_refuses_chart_missing_latest_snapshot_date(self):
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            (root / "snapshot.csv").write_text(
                "Market,2026-07-21,2026-07-22\nA,1,2\n", encoding="utf-8"
            )
            (root / "chart.html").write_text(
                "<html>2026-07-21</html>", encoding="utf-8"
            )
            with self.assertRaisesRegex(ValueError, "Refusing to publish stale chart"):
                publish_all_charts(root, registry=self.registry())

    def test_changed_chart_gets_new_immutable_filename(self):
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            (root / "snapshot.csv").write_text(
                "Market,2026-07-22\nA,1\n", encoding="utf-8"
            )
            chart = root / "chart.html"
            chart.write_text("<html>first 2026-07-22</html>", encoding="utf-8")
            _, first = publish_all_charts(root, registry=self.registry())
            chart.write_text("<html>second 2026-07-22</html>", encoding="utf-8")
            _, second = publish_all_charts(root, registry=self.registry())

            self.assertNotEqual(first[0]["published_chart"], second[0]["published_chart"])
            self.assertTrue(Path(first[0]["published_chart"]).exists())
            self.assertTrue(Path(second[0]["published_chart"]).exists())


if __name__ == "__main__":
    unittest.main()
