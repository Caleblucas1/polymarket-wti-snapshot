# Policy evidence stance and contradiction preservation

## Purpose

Every article, filing, official document, market-data source and research item used in the historical legislative benchmark must be stored as an individual evidence record. Sources may not be hidden inside an unstructured list of links.

The goal is to make supporting and contradictory evidence equally visible and auditable.

## Required stance

Each evidence record must use exactly one stance:

- `supports` — materially supports one or more sealed claims;
- `contradicts` — materially challenges one or more sealed claims;
- `mixed` — supports some claims while challenging others;
- `neutral_context` — provides context without materially supporting or contradicting a claim.

Supporting, contradicting and mixed records must name the affected claims. Examples include:

- operative text or legal mechanism;
- beneficiary or loser mapping;
- expected direction;
- materiality;
- implementation timing;
- benchmark selection;
- attribution;
- whether the effect was already priced.

## Required source record

Every source stores:

```json
{
  "evidence_id": "POLICY-CASE-0001-EVID-001",
  "source_url": "https://example.com/article",
  "title": "Article title",
  "publisher": "Publisher",
  "published_at_utc": "2020-01-01T12:00:00Z",
  "accessed_at_utc": "2026-08-01T00:00:00Z",
  "source_type": "niche_news",
  "evidence_stance": "contradicts",
  "affected_claims": [
    "beneficiary mapping",
    "implementation timing"
  ],
  "temporal_role": "post_outcome_reveal",
  "available_before_memo_seal": false,
  "reliability": "high",
  "summary": "The article reports that implementation benefited a supplier rather than the company named in the sealed memo.",
  "archive_reference": "sha256:...",
  "notes": ""
}
```

The record is append-only. A correction creates a new record that supersedes the old one; it does not erase the original evidence ID.

## Temporal role

Sources are separated into two evidence collections.

### Pre-cutoff input evidence

`pre_cutoff_evidence_records` contains only information available by the declared information cutoff and before the policy-impact memo was sealed.

At least one authenticated `official_text` record is required. Post-cutoff articles, later prices, later earnings and retrospective explanations are prohibited.

### Post-outcome evidence

`post_outcome_evidence_records` contains later disclosures, articles, trade-publication reporting, niche reporting, academic work and other evidence used to understand what actually happened.

A post-outcome source may reveal that relevant information had already existed before the memo was sealed but was missed. Such a source must set:

```json
"available_before_memo_seal": true
```

It must also be listed in `late_discovered_pre_cutoff_evidence_ids`. This turns the omission into a visible research error rather than allowing the source to be quietly absorbed into the retrospective explanation.

## Mandatory contradiction review

Every revealed outcome packet must contain:

```json
{
  "review_completed_at_utc": "...",
  "search_scope": [
    "mainstream reporting",
    "trade publications",
    "niche industry reporting",
    "company disclosures"
  ],
  "contradictory_evidence_ids": [],
  "mixed_evidence_ids": [],
  "late_discovered_pre_cutoff_evidence_ids": [],
  "no_contradictory_evidence_found": true,
  "reviewer_notes": "..."
}
```

The review must either cite contradictory or mixed evidence IDs, or explicitly state that no contradictory evidence was found after a documented search. It cannot do both.

Every cited ID must exist, and its stored stance must match the review list. A source tagged `supports` cannot be cited as contradictory evidence without correcting the source record through an append-only superseding entry.

## Why this matters

A system can appear accurate if it preserves only evidence that confirms its original story. The benchmark therefore treats contradiction handling as part of interpretation quality.

Examples of valuable contradictory evidence include:

- a company filing showing the expected benefit was immaterial;
- an agency rule delaying implementation;
- a trade publication showing the benefit accrued to a supplier or competitor;
- earnings evidence showing no expected profitability effect;
- market evidence indicating the policy was already priced;
- a niche article showing that the legal mechanism operated differently in practice;
- reporting that an unrelated company event or macro shock explains the stock move better.

Contradictory evidence is not a nuisance to be removed. It is one of the principal inputs for improving later framework versions.

## Enforcement

The validator rejects:

- raw strings or unstructured source lists;
- missing stance, timing, reliability, claim or archive fields;
- contradicting or mixed evidence with no affected claims;
- post-cutoff material placed in the blinded input packet;
- contradiction reviews that do not cite the sources they found;
- stance mismatches between a source and the contradiction review;
- pre-cutoff evidence discovered later but omitted from the late-discovery list;
- any attempt to authorize real-money trading.

The relevant implementation is:

```text
signal_research/policy_historical_benchmark.json
signal_research/policy_benchmark.py
tests/test_signal_policy_historical_benchmark.py
```
