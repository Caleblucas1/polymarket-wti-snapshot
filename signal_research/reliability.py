from __future__ import annotations

import csv
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


@dataclass(frozen=True)
class ReliabilityIssue:
    code: str
    message: str
    path: str = ""


def _load_json(path: str | Path) -> object:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _load_jsonl(path: str | Path) -> list[dict]:
    rows: list[dict] = []
    for number, line in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{path}:{number}: invalid JSONL: {exc}") from exc
        if not isinstance(value, dict):
            raise ValueError(f"{path}:{number}: JSONL row must be an object")
        rows.append(value)
    return rows


def validate_signal_records(
    registry_path: str | Path,
    evidence_path: str | Path,
    confidence_path: str | Path,
    live_status_path: str | Path,
    performance_path: str | Path,
) -> list[ReliabilityIssue]:
    registry = _load_json(registry_path)
    signals = registry.get("signals", []) if isinstance(registry, dict) else []
    ids = {row.get("registry_id") for row in signals if isinstance(row, dict)}
    issues: list[ReliabilityIssue] = []
    if None in ids or not ids:
        issues.append(ReliabilityIssue("registry.empty_or_missing_ids", "Registry has no valid registry IDs", str(registry_path)))
        ids.discard(None)

    aliases: dict[str, str] = {}
    for row in signals:
        if not isinstance(row, dict):
            continue
        rid = row.get("registry_id")
        for alias in row.get("aliases", []):
            previous = aliases.setdefault(alias, rid)
            if previous != rid:
                issues.append(ReliabilityIssue("registry.alias_collision", f"Alias {alias} maps to both {previous} and {rid}", str(registry_path)))

    for path, rows, key in (
        (evidence_path, _load_jsonl(evidence_path), "evidence_id"),
        (confidence_path, _load_jsonl(confidence_path), None),
    ):
        seen: set[str] = set()
        for row in rows:
            rid = row.get("registry_id")
            if rid not in ids:
                issues.append(ReliabilityIssue("records.orphan_registry_id", f"Unknown registry_id {rid}", str(path)))
            if key:
                value = row.get(key)
                if not value or value in seen:
                    issues.append(ReliabilityIssue("records.duplicate_or_missing_id", f"Invalid {key}: {value}", str(path)))
                seen.add(value)
            if path == confidence_path:
                components = row.get("components", {})
                score = row.get("score")
                if isinstance(components, dict) and isinstance(score, (int, float)):
                    total = sum(value for value in components.values() if isinstance(value, (int, float)))
                    if abs(total - score) > 1e-9:
                        issues.append(ReliabilityIssue("confidence.component_mismatch", f"{rid} components total {total}, score is {score}", str(path)))
                if not isinstance(score, (int, float)) or not 0 <= score <= 100:
                    issues.append(ReliabilityIssue("confidence.out_of_range", f"Invalid confidence score {score}", str(path)))

    live = _load_json(live_status_path)
    live_rows = live.get("signals", []) if isinstance(live, dict) else []
    live_ids = {row.get("registry_id") for row in live_rows if isinstance(row, dict)}
    missing_live = ids - live_ids
    extra_live = live_ids - ids
    for rid in sorted(missing_live):
        issues.append(ReliabilityIssue("live_status.missing", f"No live-status row for {rid}", str(live_status_path)))
    for rid in sorted(extra_live):
        issues.append(ReliabilityIssue("live_status.orphan", f"Live-status row references unknown {rid}", str(live_status_path)))
    for row in live_rows:
        if not isinstance(row, dict):
            continue
        if row.get("capital_right") not in {"none", "research_only", "paper_only", "capped_live"}:
            issues.append(ReliabilityIssue("live_status.invalid_capital_right", f"Invalid capital right for {row.get('registry_id')}", str(live_status_path)))
        if row.get("capital_right") == "capped_live" and row.get("operational_status") != "active":
            issues.append(ReliabilityIssue("live_status.unsafe_live_right", f"Non-active signal {row.get('registry_id')} has capped-live rights", str(live_status_path)))

    performance = _load_json(performance_path)
    perf_rows = performance.get("observations", []) if isinstance(performance, dict) else []
    seen_obs: set[tuple] = set()
    for row in perf_rows:
        if not isinstance(row, dict):
            continue
        rid = row.get("registry_id")
        if rid not in ids:
            issues.append(ReliabilityIssue("performance.orphan_registry_id", f"Unknown registry_id {rid}", str(performance_path)))
        key = (rid, row.get("timestamp"), row.get("rule_version"))
        if key in seen_obs:
            issues.append(ReliabilityIssue("performance.duplicate_observation", f"Duplicate performance observation {key}", str(performance_path)))
        seen_obs.add(key)
        gross, costs, net = row.get("gross_return"), row.get("cost_return"), row.get("net_return")
        if all(isinstance(value, (int, float)) for value in (gross, costs, net)) and abs((gross - costs) - net) > 1e-12:
            issues.append(ReliabilityIssue("performance.net_return_mismatch", f"Net return mismatch for {key}", str(performance_path)))
    return issues


def validate_chart_html(path: str | Path, *, expected_latest_date: str | None = None) -> list[ReliabilityIssue]:
    text = Path(path).read_text(encoding="utf-8")
    issues: list[ReliabilityIssue] = []
    if "Plotly.newPlot" not in text and "Plotly.react" not in text:
        issues.append(ReliabilityIssue("chart.missing_plotly_render", "Chart has no Plotly render call", str(path)))
    if "data" not in text or "layout" not in text:
        issues.append(ReliabilityIssue("chart.missing_payload", "Chart appears to lack data or layout payload", str(path)))
    if expected_latest_date and expected_latest_date not in text:
        issues.append(ReliabilityIssue("chart.stale_latest_date", f"Latest source date {expected_latest_date} is absent", str(path)))
    if "NaN" in text or "Infinity" in text:
        issues.append(ReliabilityIssue("chart.non_finite_value", "Chart contains NaN or Infinity", str(path)))
    return issues


def validate_published_manifest(manifest_path: str | Path, root: str | Path) -> list[ReliabilityIssue]:
    manifest = _load_json(manifest_path)
    entries = manifest.get("charts", []) if isinstance(manifest, dict) else []
    issues: list[ReliabilityIssue] = []
    seen: set[str] = set()
    for row in entries:
        filename = row.get("filename")
        if not filename or filename in seen:
            issues.append(ReliabilityIssue("manifest.duplicate_or_missing_filename", f"Invalid filename {filename}", str(manifest_path)))
            continue
        seen.add(filename)
        chart = Path(root) / filename
        if not chart.exists():
            issues.append(ReliabilityIssue("manifest.missing_chart", f"Missing chart {filename}", str(manifest_path)))
            continue
        digest = hashlib.sha256(chart.read_bytes()).hexdigest()
        expected = row.get("sha256")
        if expected and digest != expected:
            issues.append(ReliabilityIssue("manifest.hash_mismatch", f"Hash mismatch for {filename}", str(manifest_path)))
        issues.extend(validate_chart_html(chart, expected_latest_date=row.get("latest_date")))
    return issues


def validate_probability_csv(path: str | Path) -> list[ReliabilityIssue]:
    issues: list[ReliabilityIssue] = []
    with Path(path).open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        return [ReliabilityIssue("csv.empty", "CSV has no rows", str(path))]
    headers = list(rows[0])
    date_headers = [header for header in headers if header[:4].isdigit()]
    if date_headers != sorted(date_headers):
        issues.append(ReliabilityIssue("csv.non_monotonic_dates", "Date columns are not chronological", str(path)))
    identities: set[tuple] = set()
    non_dates = [header for header in headers if header not in date_headers]
    for index, row in enumerate(rows, 2):
        identity = tuple(row.get(header, "") for header in non_dates)
        if identity in identities:
            issues.append(ReliabilityIssue("csv.duplicate_identity", f"Duplicate logical row at line {index}", str(path)))
        identities.add(identity)
        for header in date_headers:
            value = row.get(header, "").strip()
            if not value:
                continue
            try:
                number = float(value)
            except ValueError:
                issues.append(ReliabilityIssue("csv.non_numeric_probability", f"{header} line {index}: {value}", str(path)))
                continue
            if not 0 <= number <= 100:
                issues.append(ReliabilityIssue("csv.probability_out_of_range", f"{header} line {index}: {number}", str(path)))
    return issues
