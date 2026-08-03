"""Resolve recurring Polymarket event families to their current event page.

Gamma exposes recurring-event metadata on an event response under
``series[].recurrence`` and exposes sibling event slugs from ``/series/{id}``.
This module keeps the configured logical source identity stable while allowing
the live event instance to roll from one week/month to the next.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable


EventFetcher = Callable[[str], dict[str, Any]]
SeriesFetcher = Callable[[str], dict[str, Any]]


def parse_datetime(value: object) -> datetime | None:
    """Parse Gamma's ISO timestamps as timezone-aware UTC datetimes."""
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def event_slug(url: str) -> str:
    return str(url).rstrip("/").split("/")[-1]


def event_url(slug: str) -> str:
    return f"https://polymarket.com/event/{slug}"


def _series_metadata(event: dict[str, Any], config: dict[str, Any]) -> dict[str, Any] | None:
    recurrence = config.get("recurrence")
    if not isinstance(recurrence, dict) or not recurrence.get("series_id"):
        return None
    expected_id = str(recurrence["series_id"])
    for series in event.get("series") or []:
        if str(series.get("id") or "") == expected_id:
            return series
    return None


def _future_siblings(
    series: dict[str, Any], *, as_of: datetime, recurrence: dict[str, Any]
) -> list[dict[str, Any]]:
    expected = str(recurrence.get("frequency") or "").strip().lower()
    actual = str(series.get("recurrence") or "").strip().lower()
    if expected and actual and expected != actual:
        raise ValueError(
            f"Gamma recurrence mismatch for series {series.get('id')}: "
            f"catalog={expected!r}, API={actual!r}"
        )
    candidates: list[dict[str, Any]] = []
    for candidate in series.get("events") or []:
        if not isinstance(candidate, dict):
            continue
        if candidate.get("archived") or candidate.get("closed"):
            continue
        end_date = parse_datetime(candidate.get("endDate"))
        if end_date is None or end_date < as_of:
            continue
        candidates.append(candidate)
    candidates.sort(key=lambda item: parse_datetime(item.get("endDate")) or as_of)
    return candidates


def resolve_event_instances(
    catalog: dict[str, Any],
    *,
    as_of: datetime,
    fetch_event: EventFetcher,
    fetch_series: SeriesFetcher,
) -> list[dict[str, Any]]:
    """Return live Gamma event payloads for the configured catalog.

    Each result retains the stable ``event_id`` from the catalog and adds
    ``source_state`` plus ``configured_url`` so a rollover is visible in the
    dashboard and durable record.  ``historical_only`` entries remain in the
    catalog for auditability but are not fetched as live source events.
    """
    resolved: list[dict[str, Any]] = []
    seen_instances: set[str] = set()
    for event_id, configured in catalog.get("events", {}).items():
        if configured.get("historical_only"):
            continue
        configured_url = str(configured["url"])
        configured_slug = event_slug(configured_url)
        base_event = fetch_event(configured_slug)
        recurrence = configured.get("recurrence")
        candidates: list[dict[str, Any]] = []
        source_state = "configured"
        series = _series_metadata(base_event, configured)
        if isinstance(recurrence, dict) and recurrence.get("selection") == "next_event":
            if series is not None:
                series_payload = fetch_series(str(recurrence["series_id"]))
                candidates = _future_siblings(
                    series_payload, as_of=as_of, recurrence=recurrence
                )[:1]
            if candidates:
                source_state = "recurring-next"
            else:
                source_state = "configured-fallback-no-future-sibling"
        elif isinstance(recurrence, dict) and recurrence.get("selection") == "container":
            source_state = "recurring-container"

        if not candidates:
            candidates = [
                {
                    "slug": configured_slug,
                    "id": base_event.get("id"),
                    "title": base_event.get("title"),
                }
            ]

        for candidate in candidates:
            slug = event_slug(str(candidate.get("slug") or configured_slug))
            instance_key = str(candidate.get("id") or slug)
            if instance_key in seen_instances:
                continue
            event = base_event if slug == configured_slug else fetch_event(slug)
            seen_instances.add(instance_key)
            resolved.append(
                {
                    "event_id": event_id,
                    "configured": configured,
                    "event": event,
                    "configured_url": configured_url,
                    "url": event_url(slug),
                    "source_state": source_state,
                    "configured_slug": configured_slug,
                    "resolved_slug": slug,
                    "series_id": str((recurrence or {}).get("series_id") or ""),
                    "recurrence": str((recurrence or {}).get("frequency") or ""),
                }
            )
    return resolved
