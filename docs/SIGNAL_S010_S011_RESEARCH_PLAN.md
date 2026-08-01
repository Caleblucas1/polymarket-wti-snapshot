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

Forward horizons: 1, 2, 4, 8, 12, 24, 48, 96 and 168 hours.

For each entry-hour × horizon cell report sample size, mean and median gross return, mean after the frozen 14-basis-point round-trip assumption, directional hit rate, standard error, confidence interval and hour rank.

Additional exploratory questions include strong and weak hour/horizon combinations, weekday effects, regional-session effects and whether 20:00→00:00 differs from 20:00→22:00.

### Data and causality

Use Binance public spot BTCUSDT one-hour klines normalized to UTC. A scheduled entry at an hourly boundary uses that bar's open. The local-low proximity calculation uses future data only as a diagnostic and never as an entry input.

Binance archive timestamps changed scale during the sample. Older files use milliseconds and newer files use microseconds. The parser normalizes timestamp magnitude before date filtering. An earlier 8,784-bar output therefore covered only 2024 and is superseded. The corrected January 2024 through June 2026 sample contains 21,888 consecutive hourly bars with no gaps.

### Corrected full-sample result

20:00 UTC is not a persistent local-bottom hour. Its median position in the surrounding 24-hour high-low range is approximately 50%, and about 15.9% of observations lie in the bottom quartile. The 1–48-hour returns remain negative after the frozen cost assumption. The hour ranks relatively well at 2–12 hours, but absolute profitability is not established.

### Recent-regime windows

The separate recent-regime analysis evaluates windows ending at the latest finalized bar: 7, 14, 21, 30, 60 and 90 days.

Support requires more than positive BTC drift. The 20:00 UTC entry must outperform the cross-hour mean after costs, rank in the top six of 24 hours and show local-low concentration across adjacent windows.

The latest 7-, 14-, 21- and 30-day windows show a distinct short-horizon effect: 20:00 UTC ranks near the top for 1–12-hour returns and outperforms the cross-hour average. The effect weakens in 60- and 90-day windows. The local-low diagnostic remains weak in every window, with median range positions around 35%–53% and bottom-quartile shares around 10%–17%.

The current evidence therefore supports a possible recent short-horizon timing regime, not the stronger claim that 20:00 UTC is generally the day's local bottom. New patterns discovered in the all-hour matrix require a later untouched sample and must not rewrite the frozen claim.

Research only; no real-money authorization.
