# Order-book and market-lifecycle schema

This directory is intentionally separate from the daily 9:00 AM probability snapshot and
intraday-range files.

## Files

- `market_instances.csv`: one row per physical Polymarket condition/token instance. A logical
  market may have multiple instances when Polymarket replaces a contract.
- `market_lifecycle_events.csv`: append-only detections for appearances, disappearances,
  replacements, closure, order acceptance, and order-book availability transitions.
- `orderbook_depth_snapshots.csv`: append-only Yes-token book snapshots. Depth is stored at
  1¢, 5¢, and 10¢ from the best quote, in both shares and price-weighted notional.
- `logical_market_summary.csv`: one row per stable logical contract with cumulative volume
  across genuine replacement instances.
- `orderbook_depth_report.html`: interactive current-depth chart plus complete depth and
  lifecycle tables.

## Identity rules

`Logical Market ID = configured event + normalized full market label`.

`Threshold Family ID = configured event + numeric price threshold` when a price threshold is
present. The family is for related-market comparison only.

The direction is part of logical identity. For example, WTI `↑ $80` and WTI `↓ $80` belong to
the same `$80` threshold family but remain different logical contracts because they resolve on
opposite price moves. Their probabilities and volume are never stitched together.

When a new condition ID appears with the same logical identity, its physical instance number
increments, `Replaces Condition ID` points to the prior instance, and logical lifetime volume
continues across both instances.

## Depth definition

For a band of N cents, bid depth includes bid levels from the best bid down through
`best bid - N`; ask depth includes ask levels from the best ask up through `best ask + N`.
Closed, disabled, non-accepting, and unavailable books are retained with an explicit status.
