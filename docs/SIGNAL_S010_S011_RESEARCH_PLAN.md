# S-010 BTC time-of-day effect and S-011 volatility-acceleration tail-risk control

## S-011 — intraday volatility acceleration as short-book tail-risk control

Source implementation reference: `OctopusTakopi/squeeze-tail-risk-benchmark`.

Canonical research question:

> Does a causal, short-horizon increase in idiosyncratic realized volatility improve the after-cost protection and utility of a diversified short book in Binance USD-M perpetual futures relative to a once-daily volatility-sizing baseline?

The source repository studies a fast-versus-slow RMS volatility ratio on BTC-residualized five-minute returns, next-bar execution, a threshold baseline, explicit recovery logic, and tail-risk objectives. Our candidate is separate from S-010 and must be independently reproduced before any conclusion is adopted.

Required comparisons:

- unprotected once-daily baseline;
- simple hysteretic threshold overlay;
- optional optimizer variants only after the threshold version is reproduced;
- protection, execution cost, net utility, turnover and drawdown;
- broad held-out windows and separately labeled incident stress cases;
- sensitivity to fast/slow windows, residualization method and recovery policy.

No source result is treated as our independent validation. The repository is evidence and implementation inspiration, not inherited proof.

## S-010 — BTC 20:00 UTC local-bottom and return-window effect

Canonical confirmatory claim:

> A scheduled BTC long entered at 20:00 UTC has unusually favorable after-cost forward returns, and is unusually close to a surrounding local low, relative to entries at other UTC hours.

### Frozen historical diagnostics

Entry hours: every UTC hour, with 20:00 UTC confirmatory and 19:00/21:00 robustness checks.

Forward horizons:

- 1, 2, 4, 8, 12 and 24 hours;
- 48 hours (2 days);
- 96 hours (4 days);
- 168 hours (7 days).

For each entry-hour × horizon cell report:

- sample size;
- mean and median gross return;
- mean return after a frozen round-trip cost assumption;
- directional hit rate;
- standard error and confidence interval;
- maximum adverse and favorable excursion where available.

Additional exploratory questions:

- Which hour/horizon combinations are persistently strongest or weakest?
- Is 20:00→00:00 profitable while 20:00→22:00 is weak?
- Are poor intervals concentrated by weekday, weekend or regional session?
- Does the effect align with the U.S. cash close and change under daylight-saving time?
- Does the result survive rolling 7, 14, 21, 30, 60, 90, 180 and 365-day windows?

The all-hour and weekday matrices are exploratory. New patterns discovered there must be tested on a later untouched sample and must not rewrite the frozen 20:00 UTC claim.

### Data and causality

Use Binance public spot BTCUSDT one-hour klines normalized to UTC. A scheduled entry at an hourly boundary uses that bar's open. The 20:00 UTC rule contains no price-derived trigger, so the scheduled boundary is known in advance. Local-low proximity uses future data only as a diagnostic and never as an entry input.

The first implementation should preserve downloaded archive hashes, source URLs, date coverage and missing-hour checks. Research only; no real-money authorization.
