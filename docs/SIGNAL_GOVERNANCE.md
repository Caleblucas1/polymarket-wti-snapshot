# Signal governance and capital-rights standard

## Governing question

> **Can this signal earn and keep the right to influence capital allocation?**

That question governs the Signals project. An interesting chart, intuitive story,
high correlation, popular author, or successful recent example may justify
research. None of those facts authorizes capital.

GitHub is the durable source of truth. Chat discussions, screenshots and model
memory are inputs; they become project policy or evidence only after they are
recorded here.

## The signal operating system

The durable flow is:

```text
Evidence
  -> Signal Registry
  -> Signal Families
  -> Confidence Engine
  -> Regime Engine
  -> Asset Scoring
  -> Portfolio Allocation
  -> Performance Attribution
  -> Confidence and status updates
```

This repository currently implements the first enforceable layer: definitions,
evidence, confidence history, live status, performance-history structure,
promotion gates and validation tests. Family and asset summaries are research
views, not automatic portfolio orders.

## Four linked objects

Every signal has four linked objects keyed by `registry_id`.

1. **Signal definition** — stable identity, falsifiable rule, assets, horizon,
   mechanism, regimes, benchmark, data source, decay and deactivation rule.
2. **Evidence ledger** — append-only supporting and contradictory evidence,
   including source claims, charts, papers, backtests and live observations.
3. **Performance history** — every scored observation, including losses,
   ambiguity, exclusions, costs, benchmark return and out-of-sample status.
4. **Live status** — operational state, whether the relevant regime is active,
   and the maximum capital right currently permitted.

A confidence number without these linked records is not auditable and must not
be used for sizing.

## Lifecycle

1. **Candidate** — source captured; no capital influence.
2. **Hypothesis** — predictor, target, timing, direction, exit and invalidation
   are frozen; no capital influence.
3. **Backtest** — reproducible evaluation with costs, controls, regime splits and
   an untouched sample; paper influence only.
4. **Production** — all promotion gates pass; limited live influence is allowed.
5. **Retired** — historical record remains, but current capital influence is zero.

Lifecycle and operational status are separate. A historically strong signal can
be `dormant` because its regime is absent, `degraded` because live behavior
changed, or `retired` because the edge ended.

## Capital rights

| State | Maximum right |
|---|---|
| Candidate or Hypothesis | Research only |
| Backtest or Paper trading | Paper only |
| Production with every gate passing | Capped live influence |
| Rejected, Degraded, Dormant or Retired | None |

Confidence is never direct position size. Portfolio limits, signal dependence,
liquidity and aggregate risk remain separate controls.

## Production gate

A signal cannot enter or remain in Production unless all are true:

- confidence score is at least 60;
- the rule is executable and frozen;
- a validated data source exists;
- transaction costs, slippage, financing and borrow are modeled where relevant;
- applicable and invalid regimes are defined;
- untouched out-of-sample evidence exists;
- a look-ahead and data-leakage review passed;
- a mechanical deactivation rule exists.

The validator rejects an invalid Production record. CI runs the validator on
every relevant pull request.

## Confidence

The transparent registry score has seven capped components:

| Component | Maximum |
|---|---:|
| Statistical evidence | 25 |
| Out-of-sample evidence | 20 |
| Economic mechanism | 15 |
| Regime clarity | 10 |
| Execution quality | 10 |
| Robustness | 10 |
| Current relevance | 10 |

Bands are Speculative (0–19), Preliminary (20–39), Promising (40–59),
Validated (60–74), Strong (75–89) and Exceptional (90–100).

The score measures confidence that a real, usable and currently relevant edge
exists. It is **not** the probability that the next trade wins. Each update is
append-only in `signal_records/confidence_history.jsonl`.

## Regimes and asset classes

Performance must be measured as:

```text
E[asset return | signal, regime, asset class]
minus
E[asset return | regime, asset class]
```

A signal that only works in one regime is still valuable if the regime is
observable before entry. Regime selection cannot be revised after seeing the
outcome. The registry records both applicable and invalid regimes.

## Signal families and aggregation

Thematic `registry_id` values replace discovery-order IDs as the durable key,
for example `FLOW-MON-BTC-001`, `TECH-MVWAP-BTC-001` and
`MICRO-ASIA-SNDK-001`. Legacy `S-###` identifiers remain as aliases for
continuity.

Family health can be summarized, but family or asset scores must not blindly add
correlated signals. Before aggregate evidence affects capital, the system must:

- identify duplicated inputs and common causal factors;
- cap family contribution;
- adjust for correlation and shared failure modes;
- preserve each component's attribution;
- prevent a family with many near-duplicates from overpowering independent evidence.

## Audit rules

- Preserve the first-public timestamp and source URL.
- Use only information available at the decision timestamp.
- Freeze canonical rules before testing.
- Keep all observations, including losses and ambiguous cases.
- Record exclusions with reasons.
- Separate in-sample discovery from untouched out-of-sample evaluation.
- Store contradictory evidence; never overwrite it.
- Treat screenshots as evidence only after their quantitative claims are
  transcribed into the ledger.
- Never promote based only on correlation, a visual overlay or one month.
- Never raise confidence because a narrative sounds convincing.

## Current registry

`signal_candidates.json` is schema version 2. It includes the supplied bookmark
candidates and preserves aliases when a signal's true scope becomes clearer:

- legacy `S-001` is the durable `POLICY-US-LEGISLATION-001` legislative
  policy-alpha signal; `POLICY-SEMIS-001` remains an alias because the
  semiconductor policy example was the signal's original working label;
- legacy `S-009` remains the crypto-versus-equity rebound candidate;
- BTC month-end deleveraging is the durable `FLOW-MON-BTC-001` record with
  legacy sequential ID `S-010`;
- `SALSA-MONTH-END` and `MONTH-END-BTC` are accepted aliases.

The legislative signal's canonical version begins with just-passed bills. Its
about-to-pass extension remains blocked as an enhanced variant until passage
probability, amendment risk, text finality and entry timing can be measured
prospectively. This is an explicit application of canonical before enhanced.

No current signal has live capital rights.

## Commands

```bash
python signal_cli.py list
python signal_cli.py show POLICY-US-LEGISLATION-001
python signal_cli.py hypothesis POLICY-SEMIS-001
python signal_cli.py gate FLOW-MON-BTC-001
python signal_cli.py families
python signal_cli.py validate
python -m unittest discover -s tests -p 'test_signal_*.py' -v
```

## Change control

Changes to a hypothesis, timing rule, benchmark, cost model or regime definition
create a new definition version or a new signal. They do not silently rewrite
historical results. A confidence or status change must append a reasoned record.
