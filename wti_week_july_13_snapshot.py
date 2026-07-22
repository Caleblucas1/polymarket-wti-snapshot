#!/usr/bin/env python3
"""Compatibility command for the weekly WTI tracker."""

from track_market import main_for_event


if __name__ == "__main__":
    raise SystemExit(main_for_event("wti-week-july-13"))
