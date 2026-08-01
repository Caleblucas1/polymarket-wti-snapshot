# CHIPS Act / Intel legislative-policy pilot

## Case identity

- **Case ID:** `POLICY-PILOT-CHIPS-INTC-2022`
- **Law:** CHIPS and Science Act of 2022
- **Legislative vehicle:** H.R. 4346; later Public Law 117-167
- **Primary mapped company:** Intel (`INTC`)
- **Benchmark selected before reveal:** iShares Semiconductor ETF (`SOXX`)
- **Case type:** diffuse or no-trade effect
- **Status:** scored retrospective pipeline pilot
- **Readiness credit:** zero
- **Capital rights:** none

This case is intentionally separated from the readiness-gating historical registry. The broad historical outcome was already culturally familiar when the case was selected, so it cannot honestly count as untouched evidence. Its job is to test the workflow.

## Why this case was selected

The case returns to the semiconductor example that originally motivated the legislative policy-alpha signal. It has:

- final congressional text and a precise final-passage timestamp;
- a direct subsidy and tax-credit mechanism;
- a company that had already announced a large domestic-fab program explicitly dependent on CHIPS funding;
- identifiable second-order equipment and industrial suppliers;
- a major issuer-specific event between passage and the frozen next-open entry.

That final feature made the case especially useful. It tests whether the system will preserve a **no-trade** conclusion instead of forcing a policy story into an invalid stock trade.

## Point-in-time interpretation

The information cutoff was set after the House completed congressional passage on July 28, 2022 and before Intel released its second-quarter results after the market close.

The sealed interpretation concluded:

1. Intel was a direct prospective beneficiary of domestic semiconductor incentives and the Section 48D advanced manufacturing investment credit.
2. The mechanism was economically material because Intel had announced a very large Ohio fab program whose scope and pace depended heavily on CHIPS funding.
3. Applied Materials, Lam Research, Ultra Clean Holdings and Air Products were plausible second-order beneficiaries, but their individual materiality was not quantified tightly enough to support trades.
4. Intel had publicly scheduled earnings for after the passage-day close and before the next regular-session open.
5. The frozen invalid-regime rule therefore required **no canonical INTC trade**.

The memo separated two statements that must not be conflated:

> The policy is fundamentally positive for Intel's U.S. manufacturing capital economics.

> Intel's immediate post-passage stock return is not a clean legislative-policy trade.

## Outcome reveal

### What supported the interpretation

The U.S. Department of Commerce later awarded Intel up to $7.865 billion in direct CHIPS funding. That strongly supports the original direct-beneficiary and materiality mapping.

Congress.gov also records that the measure was signed and became Public Law 117-167 on August 9, 2022.

### What contradicted or qualified it

Intel's second-quarter release, issued after passage and before the next regular-session open, reported sharply lower revenue, a GAAP loss per share, reduced full-year guidance, adverse market conditions and execution problems. This validates the decision not to attribute the next trading session to the law.

Intel later moved planned completion of the first Ohio fab to 2030, with operations expected in 2030–2031. That evidence is mixed:

- it preserves the long-term beneficiary and investment thesis;
- it contradicts the original expectation that policy support and operating realization would progress on a relatively short clock.

## Diagnostic market observations

No trade was executed. The following INTC returns are retained only as diagnostics from the July 29, 2022 open:

| Horizon | Diagnostic return |
|---|---:|
| Same-session close | +1.97% |
| August 5 close | +0.39% |
| August 26 close | -5.37% |
| Approximately 60 sessions, October 21 close | -23.49% |

The available SOXX observations are Friday-close marks rather than exact next-open-to-close intervals. They are explicitly marked as secondary diagnostics and are not treated as production-quality abnormal returns.

## Scores

### Interpretation accuracy: 90/100

The system scored highly on:

- legal mechanism;
- direct beneficiary mapping;
- direction;
- materiality;
- identification of the earnings confound and no-trade condition.

The primary weakness was implementation timing. The final direct award and Ohio operating realization were slower than the memo anticipated.

### Investment usefulness: 50/100

The score remains much lower because:

- no eligible trade was executed;
- approximate market diagnostics do not establish abnormal after-cost alpha;
- the immediate stock path was dominated by issuer-specific earnings information;
- long-run policy benefit did not translate into a clean short-horizon stock signal.

The difference between the two scores is a feature, not a problem. The system can understand the law correctly without proving a profitable trade.

## Lessons carried forward

1. A genuine policy beneficiary is not automatically an immediate stock trade.
2. A scheduled issuer event between legislative passage and entry must override the policy signal.
3. The implementation clock must separately track enactment, preliminary terms, final award, disbursement, construction completion and operating start.
4. Second-order suppliers require their own quantified materiality mapping.
5. Industry-benchmark returns must use exact interval-matched, corporate-action-adjusted data before formal alpha scoring.
6. A correct no-trade decision is a successful governance result, but it is not evidence of investment alpha.

## Repository records

The sealed input and memo are stored in:

```text
signal_records/policy_case_pilots.json
```

The separately revealed outcome, evidence review and scores are stored in:

```text
signal_records/policy_case_pilot_outcomes.json
```

The two-file design preserves the conceptual boundary between the sealed interpretation and the later reveal.

Inspect the case with:

```bash
python signal_cli.py policy-pilot POLICY-PILOT-CHIPS-INTC-2022
python signal_cli.py policy-pilots
python signal_cli.py validate
```

This pilot is research-only, contributes zero readiness cases and does not authorize real-money trading.
