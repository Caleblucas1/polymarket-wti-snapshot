import unittest
from datetime import datetime, timezone

from recurring_events import resolve_event_instances


AS_OF = datetime(2026, 8, 3, 12, tzinfo=timezone.utc)


class RecurringEventResolverTests(unittest.TestCase):
    def test_selects_next_future_sibling_and_preserves_logical_id(self):
        calls = []

        events = {
            "old": {"id": "old-id", "title": "July", "series": [{"id": "42", "recurrence": "weekly"}]},
            "next": {"id": "next-id", "title": "August", "markets": []},
        }

        def fetch_event(slug):
            calls.append(("event", slug))
            return events[slug]

        def fetch_series(series_id):
            calls.append(("series", series_id))
            return {
                "id": series_id,
                "recurrence": "weekly",
                "events": [
                    {"id": "expired", "slug": "expired", "closed": False, "endDate": "2026-08-02T23:59:00Z"},
                    {"id": "next-id", "slug": "next", "closed": False, "endDate": "2026-08-09T23:59:00Z"},
                ],
            }

        catalog = {
            "events": {
                "hormuz_transit": {
                    "label": "Hormuz transit",
                    "url": "https://polymarket.com/event/old",
                    "recurrence": {"series_id": "42", "frequency": "weekly", "selection": "next_event"},
                }
            }
        }
        resolved = resolve_event_instances(
            catalog, as_of=AS_OF, fetch_event=fetch_event, fetch_series=fetch_series
        )

        self.assertEqual(len(resolved), 1)
        self.assertEqual(resolved[0]["event_id"], "hormuz_transit")
        self.assertEqual(resolved[0]["resolved_slug"], "next")
        self.assertEqual(resolved[0]["source_state"], "recurring-next")
        self.assertIn(("series", "42"), calls)

    def test_falls_back_when_series_has_not_published_next_instance(self):
        def fetch_event(slug):
            return {"id": "old-id", "title": "July", "series": [{"id": "42", "recurrence": "monthly"}]}

        def fetch_series(series_id):
            return {
                "id": series_id,
                "recurrence": "monthly",
                "events": [
                    {"id": "old-id", "slug": "old", "closed": False, "endDate": "2026-07-31T23:59:00Z"}
                ],
            }

        catalog = {
            "events": {
                "peace_talks": {
                    "label": "Peace talks",
                    "url": "https://polymarket.com/event/old",
                    "recurrence": {"series_id": "42", "frequency": "monthly", "selection": "next_event"},
                }
            }
        }
        resolved = resolve_event_instances(
            catalog, as_of=AS_OF, fetch_event=fetch_event, fetch_series=fetch_series
        )

        self.assertEqual(resolved[0]["resolved_slug"], "old")
        self.assertEqual(resolved[0]["source_state"], "configured-fallback-no-future-sibling")

    def test_historical_only_entries_are_not_live_sources(self):
        catalog = {
            "events": {
                "current": {"label": "Current", "url": "https://polymarket.com/event/current"},
                "old": {"label": "Old", "url": "https://polymarket.com/event/old", "historical_only": True},
            }
        }

        resolved = resolve_event_instances(
            catalog,
            as_of=AS_OF,
            fetch_event=lambda slug: {"id": slug, "title": slug, "markets": []},
            fetch_series=lambda series_id: {},
        )

        self.assertEqual([item["event_id"] for item in resolved], ["current"])


if __name__ == "__main__":
    unittest.main()
