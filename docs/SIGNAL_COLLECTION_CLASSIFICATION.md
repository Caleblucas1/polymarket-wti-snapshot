# Signal collection classification

The collection-level oil label is recomputed from the current exact-contract
probabilities on every observation. A previously reported label is retained only
for auditability and is never treated as authoritative for the next run.

## Evidence domains

Exact contracts are first grouped by logical event and then by independent
evidence domain. This prevents a recurring market with many correlated dated
contracts from acting like dozens of independent votes.

The main domains are:

- political normalization: diplomacy, ceasefire, nuclear-deal, and formal blockade-policy markets;
- Hormuz physical flow and security risk;
- Bab el-Mandeb physical flow and security risk;
- direct conflict;
- oil-price distribution and tail-risk confirmation.

## Cross-chokepoint inference

U.S.-Iran diplomacy, blockade policy, and Hormuz developments may update the
prior for Bab el-Mandeb conditions, but the system must not automatically assume
the same traffic outcome. Bab el-Mandeb flow remains separately confirmable
through its own transit, closure, and Houthi-shipping markets.

Likewise, a diplomatic meeting or a formal announcement that a blockade has
ended is indirect political evidence. It does not, by itself, prove that actual
ship traffic has normalized in either chokepoint.

## Dynamic labels

The classifier supports four current-state labels:

- `oil-bullish confirmation`: at least two independent evidence domains confirm an oil-bullish move;
- `oil-bearish confirmation`: at least two independent evidence domains confirm an oil-bearish move;
- `mixed/caution`: meaningful independent domains point in opposing directions;
- `limited confirmation`: evidence lacks broad independent confirmation.

A concentrated physical-risk pulse alongside broader normalization or WTI
 downside evidence must be labeled `mixed/caution`, not broad oil-bullish
 confirmation.
