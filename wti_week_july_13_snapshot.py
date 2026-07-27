#!/usr/bin/env python3
"""Archived compatibility command for the Week of July 13 WTI tracker."""


def main() -> int:
    print(
        "The Week of July 13 tracker is archived. Its CSVs remain unchanged; "
        "run wti_week_july_27_snapshot.py for the current weekly market."
    )
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
