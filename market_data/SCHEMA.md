# Unified market-data schema

This directory groups identities, lifecycle events, hourly prices, order-book liquidity, and
reports under one namespace. The established root-level 9:00 AM snapshot and range CSVs remain
the authoritative daily compatibility outputs; `datasets.json` and `catalog/events.csv` make
their paths, grain, and relationship to the hourly data explicit without duplicating them.

## Files

- `catalog/events.csv`: one row per configured event, including the exact daily snapshot,
  range, and chart paths.
- `catalog/market_instances.csv`: one row per physical Polymarket condition/token instance. A logical
  market may have multiple instances when Polymarket replaces a contract.
- `lifecycle/market_lifecycle_events.csv`: append-only detections for appearances, disappearances,
  replacements, closure, order acceptance, and order-book availability transitions.
- `hourly/market_observations_baseline.csv`: the append-only pre-partition baseline.
- `hourly/market_observations_YYYY-MM.csv`: append-only hourly Yes-token price and book observations,
  partitioned monthly. Depth is stored at 1¢, 2¢, 5¢, and 10¢ from the best quote, in both
  shares and price-weighted notional. Each observation also records its Eastern hour and
  mutually exclusive Asia, Europe, U.S., or evening session.
- `catalog/logical_market_summary.csv`: one row per stable logical contract with cumulative volume
  across genuine replacement instances.
- `reports/market_liquidity_report.html`: interactive current-depth chart plus complete depth and
  lifecycle tables. Its primary views rank markets by distance-weighted effective depth, compare spread
  with executable two-sided depth, and aggregate liquidity by trading session.
- `datasets.json`: machine-readable declaration of which file is authoritative for each grain
  and how derived values are calculated.

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

The report's default **effective depth** avoids the hard five-cent boundary. Each resting
order's price-weighted notional receives an exponential weight based on distance from the best
quote, with a one-probability-point half-life: an order one point away counts 50%, two points
away 25%, and five points away 3.125%. Raw five-point dollars and shares remain available.

Share depth and dollar depth are different measures. Shares count resting outcome tokens.
Notional is `price × shares`, summed across the included levels. A very large share count at a
low probability can therefore represent modest economic depth. **Current Listing Volume**
covers one physical condition; **Continuous Market Volume** sums true replacement
instances of the same event and normalized market label.

## Price grains and sources

Hourly prices and liquidity share one observation row, so there is no competing hourly price
file. `Book Midpoint Probability` is the midpoint of a currently two-sided Yes-token book.
`Gamma Last Trade Probability` is Polymarket's event metadata and may be older than the
observation. `Reference Probability` prefers the book midpoint and falls back to the Gamma
last-trade value; `Reference Price Source` records which source was used.

The daily snapshot is deliberately different: it uses the latest five-minute CLOB
price-history sample at or before 9:00 AM Eastern. Its companion range is the observed minimum
and maximum of those five-minute samples during the trailing 24 hours ending at 9:00 AM.
Hourly observations do not determine the range because they could miss a short intrahour high
or low. They are retained for session analysis, auditability, and higher-frequency charts.

New hourly observations are partitioned by month under `market_data/hourly/`.
The pre-partition baseline is read together with every monthly file. The daily 9:00 AM
snapshot, range, and resolution-status files keep their established schemas and paths. Monthly hourly
partitions are intentionally local-only so hourly commits do not inflate Git history; lifecycle
changes can still be synchronized when detected.

The full lifecycle file remains append-only. The update command's JSON output contains only
the lifecycle events detected during that run under `new_lifecycle_events`, so routine reports
do not repeat the historical inventory.

Session analysis requires repeated intraday collection. The public current-book endpoint does
not provide historical order-book states, so the Asia/Europe/U.S. comparison becomes reliable
only after the tracker has accumulated observations across those windows.
