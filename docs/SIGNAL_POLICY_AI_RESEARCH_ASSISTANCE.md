# AI-assisted policy research workflow

## Purpose

Google NotebookLM, Google Gemini and similar research assistants may be useful for organizing a large article set, comparing source claims, finding contradictions, summarizing long documents and tracing second-order effects.

They are permitted as research-assistance tools. They are not evidence sources, legal authorities, market-data sources or substitutes for the original documents.

The governing standards remain:

> **Can this signal earn and keep the right to influence capital allocation?**

> **Canonical before enhanced.** A simple, source-grounded process must work before AI-assisted synthesis is allowed to add complexity.

This workflow is research-only and does not authorize real-money trading.

## Appropriate uses

NotebookLM, Gemini or another disclosed assistant may help with:

- organizing official text, filings, articles and research by topic;
- comparing how several sources describe the same legal mechanism;
- identifying apparent contradictions or missing perspectives;
- extracting candidate beneficiaries, harmed exposures and implementation dates;
- locating passages that may affect materiality estimates;
- producing a source map or question list for human review;
- comparing mainstream and niche reporting;
- generating a preliminary chronology from already registered sources.

These tools may also help during the post-outcome review to compare the sealed memo with later reporting and company disclosures.

## Prohibited uses

AI assistance may not:

- replace the original article, law, filing, dataset or official source in an evidence record;
- create a citation that is not traceable to a registered original source;
- introduce post-cutoff information into a blinded pre-cutoff packet;
- silently add web knowledge or sources outside the registered evidence set;
- rewrite a sealed memo after the outcome is known;
- resolve a contradiction merely by choosing the most convenient source;
- turn an unverified generated statement into a scored claim;
- receive or store credentials, access tokens or private share secrets in the repository;
- authorize a trade or capital allocation.

## Required research-assistance record

Every use included in a locked case packet must be disclosed:

```json
{
  "assistance_id": "POLICY-CASE-0001-AI-001",
  "tool_family": "google_notebooklm",
  "tool_name": "Google NotebookLM",
  "model_or_version": "unknown_not_exposed",
  "workspace_reference": "notebooklm:policy-case-0001",
  "used_at_utc": "2026-08-01T12:00:00Z",
  "temporal_role": "pre_cutoff_research",
  "task": "Compare the registered official text and contemporaneous reporting for beneficiary and implementation claims.",
  "input_evidence_ids": [
    "POLICY-CASE-0001-EVID-001",
    "POLICY-CASE-0001-EVID-002"
  ],
  "output_artifact_reference": "sha256:replace-with-export-or-notes-hash",
  "extracted_claims": [
    {
      "claim": "The subsidy applies only after agency certification.",
      "source_evidence_ids": [
        "POLICY-CASE-0001-EVID-001"
      ],
      "verification_status": "verified_against_original_sources"
    }
  ],
  "source_grounding_verified": true,
  "human_reviewed": true,
  "verification_notes": "Each accepted claim was checked against the cited source passage.",
  "notes": ""
}
```

## Tool families

The initial allowed values are:

- `google_notebooklm`
- `google_gemini`
- `other`

The exact product name belongs in `tool_name`. Record the model or version when exposed. When the interface does not disclose it, use a clear value such as `unknown_not_exposed` rather than guessing.

## Source-set boundary

Every assistance record must list `input_evidence_ids`.

For `pre_cutoff_research`, every referenced source must already be part of the blinded pre-cutoff evidence packet. This prevents the assistant from leaking later reporting, prices, earnings or retrospective explanations into the memo.

For `post_outcome_research`, the assistant may use registered pre-cutoff and post-outcome evidence. It may not modify the original sealed memo.

A tool output that introduces an unregistered source must not be treated as evidence. The original source must first receive a complete evidence record with author, publisher, timing, stance, reliability and archive reference.

## Claim verification

Each extracted claim uses one status:

- `verified_against_original_sources`
- `rejected`
- `unresolved`

A locked packet may not contain an unresolved AI-generated claim. Rejected claims remain useful audit information because they show where the assistant produced an unsupported or misleading interpretation.

`source_grounding_verified` and `human_reviewed` must both be true for any assistance record included in a locked packet.

## Notebook and output preservation

The repository stores a stable, non-secret `workspace_reference` and an `output_artifact_reference`. The latter should point to an archived export, notes file or deterministic content hash when practical.

Private notebook URLs, credentials and access tokens must not be committed. The reference should be sufficient to connect the case record to the preserved research artifact without exposing secrets.

## Relationship to evidence stance

AI assistance may help identify that a source supports, contradicts or partly challenges a claim. The final stance belongs to the original evidence record and must be reviewed against the source itself.

The assistant output is never cited in place of the source. For example:

```text
Incorrect evidence attribution:
  "Gemini says the implementation was delayed."

Correct evidence attribution:
  "The agency guidance dated X reports the delay; Gemini was used to locate and compare the relevant passages."
```

## Repository enforcement

The validator rejects:

- missing disclosure for a required research-assistance record;
- unknown or unregistered input evidence IDs;
- pre-cutoff assistance that references post-outcome evidence;
- claims whose cited source IDs were not supplied to the tool;
- unresolved claims in a locked packet;
- records without completed source-grounding verification;
- records without human review;
- missing tool, model/version, workspace or output references;
- treating AI output as original evidence;
- any real-money authorization.

The machine-readable rules are stored in:

```text
signal_research/policy_historical_benchmark.json
```

The validator is implemented in:

```text
signal_research/policy_benchmark.py
```
