# Prospective forecast records

Store one JSON file per forecast in this directory. Copy
`forecast_records/forecast_record_template.json`, assign a stable ID, and keep the
record as `draft` until every field required for an `open` record is complete.

Rules:

- The initial forecast is immutable after publication.
- New information is appended to `updates`; do not replace the original estimate.
- A resolved record must contain the mechanical outcome and resolution timestamp.
- Draft records are excluded from accuracy statistics.
- Invalid open or resolved records fail CI and are excluded from reports.
- This research repository never authorizes real-money trading.

No live forecast is created automatically because a probability, benchmark, cutoff,
and resolution rule must be supplied prospectively rather than inferred after the
fact.
