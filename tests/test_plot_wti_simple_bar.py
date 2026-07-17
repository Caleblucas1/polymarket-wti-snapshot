import unittest

from plot_wti_simple_bar import bar_segments


class SimpleBarTests(unittest.TestCase):
    def test_highlights_only_positive_daily_increases(self):
        bases, increases = bar_segments([10.0, 12.0, 9.0, 9.0, 14.0])
        self.assertEqual(bases, [10.0, 10.0, 9.0, 9.0, 9.0])
        self.assertEqual(increases, [0.0, 2.0, 0.0, 0.0, 5.0])

    def test_missing_day_breaks_comparison(self):
        bases, increases = bar_segments([10.0, None, 12.0])
        self.assertEqual(bases, [10.0, None, 12.0])
        self.assertEqual(increases, [0.0, None, 0.0])


if __name__ == "__main__":
    unittest.main()
