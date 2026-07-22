import tempfile
import unittest
from pathlib import Path

from market_data_layout import (
    event_catalog_rows,
    validate_daily_compatibility_files,
    validate_registry,
)
from migrate_market_data_layout import migrate
from track_market import load_registry


class MarketDataLayoutTests(unittest.TestCase):
    def test_catalog_covers_every_tracked_event_without_path_collisions(self):
        registry = load_registry()
        validate_registry(registry)
        rows = event_catalog_rows(registry)
        self.assertEqual(len(rows), len(registry))
        self.assertEqual({row["Event Key"] for row in rows}, set(registry))
        self.assertEqual(len({row["Snapshot Path"] for row in rows}), len(rows))

    def test_current_daily_files_have_valid_grains_and_ranges(self):
        errors = validate_daily_compatibility_files(Path(__file__).parents[1], load_registry())
        self.assertEqual(errors, [])

    def test_registry_rejects_output_path_collision(self):
        registry = {
            "a": {"slug": "a", "engine": "snapshot", "output": "same.csv", "range_output": "a-range.csv", "chart_output": "a.html"},
            "b": {"slug": "b", "engine": "snapshot", "output": "same.csv", "range_output": "b-range.csv", "chart_output": "b.html"},
        }
        with self.assertRaisesRegex(ValueError, "Output path collision"):
            validate_registry(registry)

    def test_legacy_migration_moves_each_file_once_and_preserves_bytes(self):
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            source = root / "orderbook"
            destination = root / "market_data"
            source.mkdir()
            source_file = source / "market_instances.csv"
            source_file.write_bytes(b"Condition ID\nabc\n")
            actions = migrate(source, destination, apply=True)
            target = destination / "catalog" / "market_instances.csv"
            self.assertEqual(len(actions), 1)
            self.assertFalse(source_file.exists())
            self.assertFalse(source.exists())
            self.assertEqual(target.read_bytes(), b"Condition ID\nabc\n")


if __name__ == "__main__":
    unittest.main()
