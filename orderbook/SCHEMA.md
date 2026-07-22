# Order-book and market-lifecycle schema

This directory is intentionally separate from the daily 9:00 AM probability snapshot and
intraday-range files.

## Files

- `market_instances.csv`: one row per physical Polymarket condition/token instance. A logical
  market may have multiple instances when Polymarket replaces a contract.
- `market_lifecycle_events.csv`: append-only detections for appearances, disappearances,
  replacements, closure, order acceptance, and order-book availability transitions.
- `orderbook_depth_snapshots.csv`: append-only Yes-token book snapshots. Depth is stored at
  1¢, 2¢, 5¢, and 10¢ from the best quote, in both shares and price-weighted notional. Each
  observation also records its Eastern hour and mutually exclusive Asia, Europe, U.S., or
  evening session.
- `logical_market_summary.csv`: one row per stable logical contract with cumulative volume
  across genuine replacement instances.
- `orderbook_depth_report.html`: interactive current-depth chart plus complete depth and
  lifecycle tables. Its primary views rank markets by five-point move cost, compare spread
  with executable two-sided depth, and aggregate liquidity by trading session.

## Identity rules

`Logical Market ID = configured event + normalized full market label`.

`Threshold Family ID = configured event + numeric price threshold` when a price threshold is
present. The family is for related-market comparison only.

`Condition ID` is Polymarket's identifier for one physical contract instance. `Related
Condition ID` is a typed link whose meaning depends on `Event Type`:

- for `replaced`, it identifies the previous physical condition for the same logical market;
  these instances are stitched into one logical lifetime;
- for `related-threshold-appeared`, it identifies a comparison contract in the same numeric
  threshold family, such as WTI `↓ $80` versus `↑ $80`; these are not stitched.

The current baseline contains confirmed comparison links for WTI `$70` and `$80`. It does not
yet contain an observed true replacement; the replacement rule will apply when one appears.

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

`Weak Side Notional 5c` is the smaller of bid and ask notional within five cents of the
corresponding best quote. It is used as an approximate market-resilience measure: a smaller
value means one side of the displayed probability is cheaper to move. This is not guaranteed
execution because orders may cancel and new or hidden liquidity may appear.

Share depth and dollar depth are different measures. Shares count resting outcome tokens.
Notional is `price × shares`, summed across the included levels. A very large share count at a
low probability can therefore represent modest economic depth. `Instance Volume` is the
Gamma-reported traded volume for one physical condition. `Logical Lifetime Volume` sums that
volume across true replacement instances of the same event and normalized market label.

The full lifecycle file remains append-only. The update command's JSON output contains only
the lifecycle events detected during that run under `new_lifecycle_events`, so routine reports
do not repeat the historical inventory.

Session analysis requires repeated intraday collection. The public current-book endpoint does
not provide historical order-book states, so the Asia/Europe/U.S. comparison becomes reliable
only after the tracker has accumulated observations across those windows.
