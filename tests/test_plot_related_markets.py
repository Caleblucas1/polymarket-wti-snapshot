import csv
import json
import tempfile
import unittest
from pathlib import Path

from plot_related_markets import (
    RelatedPair,
    aligned_pair_series,
    load_pair_config,
    write_related_market_chart,
)


def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as output_file:
        writer = csv.DictWriter(output_file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


class RelatedMarketChartTests(unittest.TestCase):
    def test_pair_config_validation(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "pairs.json"
            path.write_text(
                json.dumps(
                    [
                        {
                            "id": "pair",
                            "title": "Pair",
                            "relationship": "related",
                            "left_event": "left",
                            "left_label": "July 31",
                            "right_event": "right",
                            "right_label": "July 31",
                        }
                    ]
                ),
                encoding="utf-8",
            )
            pairs = load_pair_config(path)

        self.assertEqual(len(pairs), 1)
        self.assertEqual(pairs[0].left_label, "July 31")

    def test_aligned_pair_series_uses_common_dates_and_ranges(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir)
            write_csv(
                data_dir / "left.csv",
                ["Deadline", "2026-07-17", "2026-07-18"],
                [{"Deadline": "July 31", "2026-07-17": "43", "2026-07-18": "28"}],
            )
            write_csv(
                data_dir / "right.csv",
                ["Deadline", "2026-07-16", "2026-07-17", "2026-07-18"],
                [
                    {
                        "Deadline": "July 31",
                        "2026-07-16": "52.5",
                        "2026-07-17": "33.5",
                        "2026-07-18": "29",
                    }
                ],
            )
            write_csv(
                data_dir / "left_ranges.csv",
                ["Deadline", "Date", "Low", "High"],
                [
                    {
                        "Deadline": "July 31",
                        "Date": "2026-07-18",
                        "Low": "27",
                        "High": "49.5",
                    }
                ],
            )
            write_csv(
                data_dir / "right_ranges.csv",
                ["Deadline", "Date", "Low", "High"],
                [
                    {
                        "Deadline": "July 31",
                        "Date": "2026-07-18",
                        "Low": "25.5",
                        "High": "34.5",
                    }
                ],
            )
            registry = {
                "left": {"output": "left.csv", "range_output": "left_ranges.csv"},
                "right": {"output": "right.csv", "range_output": "right_ranges.csv"},
            }
            series = aligned_pair_series(
                RelatedPair(
                    id="pair",
                    title="Pair",
                    relationship="related",
                    left_event="left",
                    left_label="July 31",
                    right_event="right",
                    right_label="July 31",
                ),
                registry=registry,
                data_dir=data_dir,
                days=7,
            )

        self.assertEqual(series.dates, ["2026-07-17", "2026-07-18"])
        self.assertEqual(series.spreads, [9.5, -1.0])
        self.assertEqual(series.left_ranges[-1], (27.0, 49.5))
        self.assertEqual(series.right_ranges[-1], (25.5, 34.5))

    def test_write_related_market_chart_from_repository_data(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "related.html"
            count = write_related_market_chart(data_dir=Path("."), output=output, days=7)
            self.assertEqual(count, 2)
            self.assertTrue(output.exists())
            html = output.read_text(encoding="utf-8")
            self.assertIn("Related Houthi escalation market comparison", html)
            self.assertIn("not as an arbitrage label", html)


if __name__ == "__main__":
    unittest.main()
