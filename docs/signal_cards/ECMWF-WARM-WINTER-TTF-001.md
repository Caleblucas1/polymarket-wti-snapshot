# S-013 — ECMWF warm European winter forecast versus Dutch TTF

## Decision

**Lifecycle:** Hypothesis, blocked for data  
**Operational status:** Ready for data  
**Confidence:** 32/100 — preliminary  
**Capital right:** None  
**Real-money authorization:** False

The source is worth preserving because it links a point-in-time seasonal weather forecast to a liquid European gas instrument through a plausible demand mechanism. The supplied map supports a qualitative warm-Europe reading for DJF 2026/27, but it does not provide the machine-readable regional probability needed to fire a canonical trigger.

## Source-derived observation

The uploaded ECMWF System 5 map is labeled as a probabilistic most-likely-tercile forecast for DJF 2026/27 2m temperature, initialized August 1, 2026. Much of continental Europe and the Mediterranean appear in orange and red upper-tercile categories. The source post describes this as a “hot winter” and connects it to winter TTF trading.

That is evidence for candidacy, not a trade. The map is probabilistic, chart colors are not a reproducible regional statistic, and the screenshot's embedded Polymarket “Super El Niño” claim is a separate statement excluded from this signal.

## Frozen proposed canonical rule

- Forecast: August-initialized ECMWF SEAS5 DJF mean 2m temperature.
- Region: area-weighted box from 35°N–60°N and 10°W–30°E.
- Statistic: probability that DJF temperature is in the model-specific upper tercile.
- Trigger: at least 60%.
- Instrument: equal-weight ICE Endex Dutch TTF December, January and February monthly futures.
- Direction: short only.
- Entry: next official ICE settlement after the verified public release.
- Primary exit: official settlement after five ICE trading sessions.
- Costs: €0.05/MWh round trip.
- Benchmark: matched August five-session returns for the same DJF strip construction, controlled by year and broad supply regime.

The five-session horizon tests the market reaction to forecast information. A 20-session horizon and November 30 exit are diagnostics only and cannot replace the primary horizon after outcomes are known.

## Why the process stops before a backtest result

Three required inputs are absent:

1. The machine-readable August 2026 ECMWF field needed to calculate the fixed-region upper-tercile probability.
2. A point-in-time archive of historical August ECMWF forecast issuances and hindcasts.
3. Point-in-time ICE TTF December, January and February settlement histories with contract identities and roll treatment.

Without those data, a historical return estimate would be invented or contaminated. The deterministic evaluator therefore returns `candidate_accepted_hypothesis_blocked_market_data_unavailable` and records no position.

## Regime controls

The signal is potentially applicable when winter TTF contains a meaningful weather-demand premium and no concurrent event dominates the curve. It is invalid or separately classified during major LNG or pipeline outages, war or sanctions shocks, infrastructure damage, extreme storage conditions, or policy intervention.

## Current state

- Qualitative weather direction: warm Europe.
- Qualitative TTF impulse: bearish weather demand.
- Numeric canonical probability: unavailable.
- Canonical trigger: not evaluable.
- Historical backtest: not executable.
- Shadow position: none.

## Next gate

Retrieve the official machine-readable August release, calculate and archive the fixed-region probability, then acquire historical point-in-time forecast and TTF settlement data. Only after at least ten independent release events can the cost-aware matched benchmark be evaluated.

**Governing rule:** Canonical before enhanced.
