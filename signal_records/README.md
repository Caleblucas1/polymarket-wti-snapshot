# Durable signal records

The daily signal dashboard writes one append-only JSONL observation to
`observations.jsonl` in this directory. Each record contains the exact
five-contract evidence used by the dashboard, the definition version, and a
catalog fingerprint.

The write is duplicate-safe by `observation_id`, which is the Eastern cutoff
timestamp. Re-running a report for the same cutoff does not add a second
observation. User ratings and notes are annotations on the observation and do
not rewrite its raw probabilities or rule definitions.

The generated HTML dashboard and its synthetic rendered data are separate
scratch artifacts; they do not belong in this directory.
