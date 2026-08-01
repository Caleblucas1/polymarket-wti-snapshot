#!/usr/bin/env python3
"""Validation, scoring, and calibration reporting for forecast records.

The module deliberately uses only the Python standard library so it can run in
GitHub Actions and local research environments without adding dependencies.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

ALLOWED_PROJECTS = {"signals", "polymarket"}
ALLOWED_STATUSES = {"draft", "open", "resolved", "void"}
ALLOWED_FORECAST_TYPES = {"binary_probability", "numeric"}
ALLOWED_EFFECTS = {"up", "down", "flat", "mixed"}
BINARY_METRICS = {"brier"}
NUMERIC_METRICS = {"absolute_error", "squared_error"}
REQUIRED_TOP_LEVEL = {
    "schema_version",
    "forecast_id",
    "project",
    "status",
    "question",
    "target",
    "resolution",
    "initial_forecast",
    "outside_view",
    "decomposition",
    "evidence",
    "applicability",
    "updates",
    "polymarket_comparison",
    "scoring",
    "postmortem",
    "audit",
}


@dataclass(frozen=True)
class ValidationIssue:
    severity: str
    path: str
    message: str

    def as_dict(self) -> dict[str, str]:
        return {"severity": self.severity, "path": self.path, "message": self.message}


class RecordValidationError(ValueError):
    """Raised when scoring is requested for an invalid record."""


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _probability(value: Any) -> bool:
    return _is_number(value) and 0.0 <= float(value) <= 1.0


def _nonempty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _parse_utc(value: Any) -> datetime | None:
    if not _nonempty_string(value):
        return None
    text = str(value).strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        return None
    return parsed.astimezone(timezone.utc)


def _get(record: Mapping[str, Any], *keys: str, default: Any = None) -> Any:
    current: Any = record
    for key in keys:
        if not isinstance(current, Mapping) or key not in current:
            return default
        current = current[key]
    return current


def _add(issues: list[ValidationIssue], severity: str, path: str, message: str) -> None:
    issues.append(ValidationIssue(severity, path, message))


def _require_mapping(record: Mapping[str, Any], key: str, issues: list[ValidationIssue]) -> Mapping[str, Any]:
    value = record.get(key)
    if not isinstance(value, Mapping):
        _add(issues, "error", key, "must be an object")
        return {}
    return value


def _require_list(record: Mapping[str, Any], key: str, issues: list[ValidationIssue]) -> list[Any]:
    value = record.get(key)
    if not isinstance(value, list):
        _add(issues, "error", key, "must be an array")
        return []
    return value


def validate_record(record: Mapping[str, Any]) -> list[ValidationIssue]:
    """Validate one forecast record with structural and forecasting rules."""

    issues: list[ValidationIssue] = []
    missing = sorted(REQUIRED_TOP_LEVEL - set(record))
    for key in missing:
        _add(issues, "error", key, "required top-level field is missing")

    if record.get("schema_version") != 1:
        _add(issues, "error", "schema_version", "must equal 1")

    forecast_id = record.get("forecast_id")
    if not _nonempty_string(forecast_id):
        _add(issues, "error", "forecast_id", "must be a non-empty stable identifier")

    project = record.get("project")
    if project not in ALLOWED_PROJECTS:
        _add(issues, "error", "project", f"must be one of {sorted(ALLOWED_PROJECTS)}")

    status = record.get("status")
    if status not in ALLOWED_STATUSES:
        _add(issues, "error", "status", f"must be one of {sorted(ALLOWED_STATUSES)}")
    strict = status in {"open", "resolved", "void"}

    if strict and not _nonempty_string(record.get("question")):
        _add(issues, "error", "question", "must be precise and externally resolvable")

    target = _require_mapping(record, "target", issues)
    resolution = _require_mapping(record, "resolution", issues)
    initial = _require_mapping(record, "initial_forecast", issues)
    outside = _require_mapping(record, "outside_view", issues)
    evidence = _require_mapping(record, "evidence", issues)
    applicability = _require_mapping(record, "applicability", issues)
    comparison = _require_mapping(record, "polymarket_comparison", issues)
    scoring = _require_mapping(record, "scoring", issues)
    postmortem = _require_mapping(record, "postmortem", issues)
    audit = _require_mapping(record, "audit", issues)
    decomposition = _require_list(record, "decomposition", issues)
    updates = _require_list(record, "updates", issues)

    forecast_type = target.get("forecast_type")
    if forecast_type not in ALLOWED_FORECAST_TYPES:
        _add(issues, "error", "target.forecast_type", f"must be one of {sorted(ALLOWED_FORECAST_TYPES)}")

    if strict and not _nonempty_string(target.get("event_or_asset")):
        _add(issues, "error", "target.event_or_asset", "must identify the forecasted event or asset")

    timestamps: dict[str, datetime | None] = {}
    for path, value in (
        ("target.horizon_start_utc", target.get("horizon_start_utc")),
        ("target.horizon_end_utc", target.get("horizon_end_utc")),
        ("target.information_cutoff_utc", target.get("information_cutoff_utc")),
        ("initial_forecast.created_at_utc", initial.get("created_at_utc")),
    ):
        parsed = _parse_utc(value)
        timestamps[path] = parsed
        if strict and parsed is None:
            _add(issues, "error", path, "must be a valid timezone-aware UTC ISO-8601 timestamp")

    start = timestamps.get("target.horizon_start_utc")
    end = timestamps.get("target.horizon_end_utc")
    cutoff = timestamps.get("target.information_cutoff_utc")
    created = timestamps.get("initial_forecast.created_at_utc")
    if start and end and start >= end:
        _add(issues, "error", "target.horizon_end_utc", "must be later than horizon_start_utc")
    if cutoff and created and created < cutoff:
        _add(issues, "error", "initial_forecast.created_at_utc", "cannot precede the information cutoff")

    if strict and not _nonempty_string(resolution.get("source")):
        _add(issues, "error", "resolution.source", "must identify an external resolution source")
    if strict and not _nonempty_string(resolution.get("rule")):
        _add(issues, "error", "resolution.rule", "must state a mechanical resolution rule")

    resolved_at = None
    if resolution.get("resolved_at_utc") is not None:
        resolved_at = _parse_utc(resolution.get("resolved_at_utc"))
        if resolved_at is None:
            _add(issues, "error", "resolution.resolved_at_utc", "must be a valid UTC timestamp or null")
    if status == "resolved" and resolved_at is None:
        _add(issues, "error", "resolution.resolved_at_utc", "is required when status is resolved")
    if resolved_at and start and resolved_at < start:
        _add(issues, "error", "resolution.resolved_at_utc", "cannot precede the forecast horizon")

    primary_metric = scoring.get("primary_metric")
    if forecast_type == "binary_probability":
        if strict and not _probability(initial.get("probability")):
            _add(issues, "error", "initial_forecast.probability", "must be between 0 and 1")
        if initial.get("numeric_value") is not None:
            _add(issues, "warning", "initial_forecast.numeric_value", "is ignored for binary forecasts")
        if strict and not _probability(initial.get("benchmark_value")):
            _add(issues, "error", "initial_forecast.benchmark_value", "must be a probability between 0 and 1")
        if strict and primary_metric not in BINARY_METRICS:
            _add(issues, "error", "scoring.primary_metric", "binary forecasts must use brier")
        outcome = resolution.get("outcome")
        if status == "resolved" and outcome not in {0, 1, 0.0, 1.0, False, True}:
            _add(issues, "error", "resolution.outcome", "resolved binary outcome must be 0 or 1")
    elif forecast_type == "numeric":
        if strict and not _is_number(initial.get("numeric_value")):
            _add(issues, "error", "initial_forecast.numeric_value", "must be a finite number")
        if strict and not _is_number(initial.get("benchmark_value")):
            _add(issues, "error", "initial_forecast.benchmark_value", "must be a finite number")
        if strict and primary_metric not in NUMERIC_METRICS:
            _add(issues, "error", "scoring.primary_metric", f"must be one of {sorted(NUMERIC_METRICS)}")
        if status == "resolved" and not _is_number(resolution.get("outcome")):
            _add(issues, "error", "resolution.outcome", "resolved numeric outcome must be a finite number")

    if strict and not _nonempty_string(initial.get("benchmark_name")):
        _add(issues, "error", "initial_forecast.benchmark_name", "must identify the frozen benchmark")

    if strict and not _nonempty_string(outside.get("reference_class")):
        _add(issues, "error", "outside_view.reference_class", "must state a relevant reference class")
    if strict and outside.get("base_rate") is None:
        _add(issues, "error", "outside_view.base_rate", "must record the outside-view base rate or baseline value")
    elif forecast_type == "binary_probability" and outside.get("base_rate") is not None and not _probability(outside.get("base_rate")):
        _add(issues, "error", "outside_view.base_rate", "binary base rate must be between 0 and 1")
    elif forecast_type == "numeric" and outside.get("base_rate") is not None and not _is_number(outside.get("base_rate")):
        _add(issues, "error", "outside_view.base_rate", "numeric baseline must be a finite number")
    if strict and not _nonempty_string(outside.get("source_notes")):
        _add(issues, "error", "outside_view.source_notes", "must explain the reference-class source")

    valid_drivers = 0
    for index, driver in enumerate(decomposition):
        path = f"decomposition[{index}]"
        if not isinstance(driver, Mapping):
            _add(issues, "error", path, "must be an object")
            continue
        if _nonempty_string(driver.get("driver")) and _nonempty_string(driver.get("estimated_state")):
            valid_drivers += 1
        else:
            _add(issues, "error", path, "driver and estimated_state must be non-empty")
        if driver.get("effect_on_forecast") not in ALLOWED_EFFECTS:
            _add(issues, "error", f"{path}.effect_on_forecast", f"must be one of {sorted(ALLOWED_EFFECTS)}")
        weight = driver.get("weight_or_probability")
        if weight is not None and not _is_number(weight):
            _add(issues, "error", f"{path}.weight_or_probability", "must be a finite number or null")
    if strict and valid_drivers == 0:
        _add(issues, "error", "decomposition", "must contain at least one valid driver")

    for key in ("supporting", "disconfirming", "alternative_scenarios"):
        items = evidence.get(key)
        if not isinstance(items, list):
            _add(issues, "error", f"evidence.{key}", "must be an array")
        elif strict and not any(_nonempty_string(item) for item in items):
            _add(issues, "error", f"evidence.{key}", "must contain at least one substantive entry")

    for key in ("market_regime", "asset_classes", "invalidating_conditions"):
        items = applicability.get(key)
        if not isinstance(items, list):
            _add(issues, "error", f"applicability.{key}", "must be an array")
        elif strict and not any(_nonempty_string(item) for item in items):
            _add(issues, "error", f"applicability.{key}", "must contain at least one substantive entry")

    prior_probability = initial.get("probability")
    prior_numeric = initial.get("numeric_value")
    prior_timestamp = created
    for index, update in enumerate(updates):
        path = f"updates[{index}]"
        if not isinstance(update, Mapping):
            _add(issues, "error", path, "must be an object")
            continue
        timestamp = _parse_utc(update.get("timestamp_utc"))
        if timestamp is None:
            _add(issues, "error", f"{path}.timestamp_utc", "must be a valid UTC timestamp")
        else:
            if prior_timestamp and timestamp <= prior_timestamp:
                _add(issues, "error", f"{path}.timestamp_utc", "updates must be strictly chronological")
            if resolved_at and timestamp > resolved_at:
                _add(issues, "error", f"{path}.timestamp_utc", "cannot occur after resolution")
            prior_timestamp = timestamp
        if not _nonempty_string(update.get("new_evidence")):
            _add(issues, "error", f"{path}.new_evidence", "must explain the evidence behind the update")
        if not isinstance(update.get("evidence_was_expected"), bool):
            _add(issues, "error", f"{path}.evidence_was_expected", "must be boolean")
        if not isinstance(update.get("regime_changed"), bool):
            _add(issues, "error", f"{path}.regime_changed", "must be boolean")
        if update.get("market_moved_first") is not None and not isinstance(update.get("market_moved_first"), bool):
            _add(issues, "error", f"{path}.market_moved_first", "must be boolean or null")

        if forecast_type == "binary_probability":
            old_value = update.get("old_probability")
            new_value = update.get("new_probability")
            if not _probability(old_value) or not _probability(new_value):
                _add(issues, "error", path, "binary updates require old_probability and new_probability in [0, 1]")
            elif _probability(prior_probability) and not math.isclose(float(old_value), float(prior_probability), abs_tol=1e-12):
                _add(issues, "error", f"{path}.old_probability", "must equal the prior recorded probability")
            prior_probability = new_value
        elif forecast_type == "numeric":
            old_value = update.get("old_numeric_value")
            new_value = update.get("new_numeric_value")
            if not _is_number(old_value) or not _is_number(new_value):
                _add(issues, "error", path, "numeric updates require finite old_numeric_value and new_numeric_value")
            elif _is_number(prior_numeric) and not math.isclose(float(old_value), float(prior_numeric), abs_tol=1e-12):
                _add(issues, "error", f"{path}.old_numeric_value", "must equal the prior recorded numeric value")
            prior_numeric = new_value

    market_probability = comparison.get("market_probability_at_cutoff")
    if market_probability is not None and not _probability(market_probability):
        _add(issues, "error", "polymarket_comparison.market_probability_at_cutoff", "must be between 0 and 1 or null")
    divergence = comparison.get("project_minus_market_probability")
    if divergence is not None and not _is_number(divergence):
        _add(issues, "error", "polymarket_comparison.project_minus_market_probability", "must be numeric or null")
    if forecast_type == "binary_probability" and _probability(initial.get("probability")) and _probability(market_probability):
        expected = float(initial["probability"]) - float(market_probability)
        if divergence is None or not math.isclose(float(divergence), expected, abs_tol=1e-12):
            _add(issues, "error", "polymarket_comparison.project_minus_market_probability", "must equal initial project probability minus market probability")
    if project == "polymarket" and strict:
        if not _nonempty_string(comparison.get("market_slug")):
            _add(issues, "error", "polymarket_comparison.market_slug", "is required for Polymarket forecasts")
        if not _probability(market_probability):
            _add(issues, "error", "polymarket_comparison.market_probability_at_cutoff", "is required for Polymarket forecasts")

    if not isinstance(scoring.get("out_of_sample"), bool):
        _add(issues, "error", "scoring.out_of_sample", "must be boolean")

    if not isinstance(postmortem.get("completed"), bool):
        _add(issues, "error", "postmortem.completed", "must be boolean")
    if status == "resolved" and postmortem.get("completed") is not True:
        _add(issues, "warning", "postmortem.completed", "resolved forecast still needs a postmortem")

    if audit.get("immutable_original_preserved") is not True:
        _add(issues, "error", "audit.immutable_original_preserved", "must remain true")
    if audit.get("real_money_trading_authorized") is not False:
        _add(issues, "error", "audit.real_money_trading_authorized", "must remain false in this research repository")

    return issues


def discover_records(path: Path) -> list[Path]:
    if path.is_file():
        return [path]
    if not path.exists():
        return []
    return sorted(candidate for candidate in path.rglob("*.json") if candidate.is_file())


def load_record(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RecordValidationError(f"{path}: cannot load JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise RecordValidationError(f"{path}: forecast record must be a JSON object")
    return data


def effective_forecast(record: Mapping[str, Any]) -> float:
    forecast_type = _get(record, "target", "forecast_type")
    if forecast_type == "binary_probability":
        value = _get(record, "initial_forecast", "probability")
        for update in record.get("updates", []):
            value = update.get("new_probability")
    else:
        value = _get(record, "initial_forecast", "numeric_value")
        for update in record.get("updates", []):
            value = update.get("new_numeric_value")
    if not _is_number(value):
        raise RecordValidationError("effective forecast is not numeric")
    return float(value)


def _score_error(metric: str, forecast: float, outcome: float) -> float:
    error = forecast - outcome
    if metric in {"brier", "squared_error"}:
        return error * error
    if metric == "absolute_error":
        return abs(error)
    raise RecordValidationError(f"unsupported scoring metric: {metric}")


def score_record(record: Mapping[str, Any]) -> dict[str, Any]:
    issues = validate_record(record)
    errors = [issue for issue in issues if issue.severity == "error"]
    if errors:
        summary = "; ".join(f"{issue.path}: {issue.message}" for issue in errors[:5])
        raise RecordValidationError(summary)
    if record.get("status") != "resolved":
        raise RecordValidationError("only resolved forecasts can be scored")

    metric = str(_get(record, "scoring", "primary_metric"))
    forecast = effective_forecast(record)
    outcome = float(_get(record, "resolution", "outcome"))
    benchmark = float(_get(record, "initial_forecast", "benchmark_value"))
    project_score = _score_error(metric, forecast, outcome)
    benchmark_score = _score_error(metric, benchmark, outcome)
    relative_improvement = None
    if benchmark_score > 0:
        relative_improvement = (benchmark_score - project_score) / benchmark_score

    result: dict[str, Any] = {
        "forecast_id": record["forecast_id"],
        "project": record["project"],
        "forecast_type": _get(record, "target", "forecast_type"),
        "metric": metric,
        "effective_forecast": forecast,
        "outcome": outcome,
        "project_score": project_score,
        "benchmark_name": _get(record, "initial_forecast", "benchmark_name"),
        "benchmark_value": benchmark,
        "benchmark_score": benchmark_score,
        "relative_improvement": relative_improvement,
        "out_of_sample": bool(_get(record, "scoring", "out_of_sample")),
    }

    market_probability = _get(record, "polymarket_comparison", "market_probability_at_cutoff")
    if metric == "brier" and _probability(market_probability):
        market_score = _score_error(metric, float(market_probability), outcome)
        market_improvement = None
        if market_score > 0:
            market_improvement = (market_score - project_score) / market_score
        result.update(
            {
                "market_probability_at_cutoff": float(market_probability),
                "market_score": market_score,
                "relative_improvement_vs_market": market_improvement,
            }
        )
    return result


def _mean(values: Sequence[float]) -> float | None:
    return sum(values) / len(values) if values else None


def _relative_improvement(project_score: float | None, benchmark_score: float | None) -> float | None:
    if project_score is None or benchmark_score is None or benchmark_score <= 0:
        return None
    return (benchmark_score - project_score) / benchmark_score


def _score_summary(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    if not rows:
        return {"n": 0, "project_score": None, "benchmark_score": None, "relative_improvement": None}
    project = _mean([float(row["project_score"]) for row in rows])
    benchmark = _mean([float(row["benchmark_score"]) for row in rows])
    return {
        "n": len(rows),
        "project_score": project,
        "benchmark_score": benchmark,
        "relative_improvement": _relative_improvement(project, benchmark),
    }


def _calibration(rows: Sequence[Mapping[str, Any]], bucket_width: float = 0.1) -> list[dict[str, Any]]:
    buckets: list[dict[str, Any]] = []
    count = int(round(1.0 / bucket_width))
    for index in range(count):
        lower = index * bucket_width
        upper = 1.0 if index == count - 1 else (index + 1) * bucket_width
        selected = [
            row
            for row in rows
            if lower <= float(row["effective_forecast"]) <= upper
            if index == count - 1 or float(row["effective_forecast"]) < upper
        ]
        if not selected:
            continue
        mean_forecast = _mean([float(row["effective_forecast"]) for row in selected])
        observed_rate = _mean([float(row["outcome"]) for row in selected])
        buckets.append(
            {
                "lower": lower,
                "upper": upper,
                "n": len(selected),
                "mean_forecast": mean_forecast,
                "observed_rate": observed_rate,
                "calibration_gap": None if mean_forecast is None or observed_rate is None else mean_forecast - observed_rate,
                "mean_brier": _mean([float(row["project_score"]) for row in selected]),
            }
        )
    return buckets


def _compliance(record: Mapping[str, Any]) -> dict[str, bool]:
    evidence = record.get("evidence", {})
    applicability = record.get("applicability", {})
    return {
        "valid_resolution_rule": _nonempty_string(_get(record, "resolution", "source")) and _nonempty_string(_get(record, "resolution", "rule")),
        "explicit_base_rate": _get(record, "outside_view", "base_rate") is not None and _nonempty_string(_get(record, "outside_view", "reference_class")),
        "driver_decomposition": bool(record.get("decomposition")),
        "contrary_evidence": bool(evidence.get("disconfirming")),
        "alternative_scenarios": bool(evidence.get("alternative_scenarios")),
        "invalidating_conditions": bool(applicability.get("invalidating_conditions")),
        "immutable_history": _get(record, "audit", "immutable_original_preserved") is True,
        "benchmark_defined": _nonempty_string(_get(record, "initial_forecast", "benchmark_name")) and _get(record, "initial_forecast", "benchmark_value") is not None,
        "postmortem_complete_if_resolved": record.get("status") != "resolved" or _get(record, "postmortem", "completed") is True,
    }


def build_report(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    statuses = Counter(str(record.get("status")) for record in records)
    projects = Counter(str(record.get("project")) for record in records)
    validation_rows = []
    valid_records: list[Mapping[str, Any]] = []
    for record in records:
        issues = validate_record(record)
        errors = [issue for issue in issues if issue.severity == "error"]
        warnings = [issue for issue in issues if issue.severity == "warning"]
        validation_rows.append(
            {
                "forecast_id": record.get("forecast_id"),
                "errors": [issue.as_dict() for issue in errors],
                "warnings": [issue.as_dict() for issue in warnings],
            }
        )
        if not errors:
            valid_records.append(record)

    scored: list[dict[str, Any]] = []
    for record in valid_records:
        if record.get("status") == "resolved":
            scored.append(score_record(record))

    binary = [row for row in scored if row["forecast_type"] == "binary_probability"]
    numeric = [row for row in scored if row["forecast_type"] == "numeric"]
    market_rows = [row for row in binary if "market_score" in row]

    by_project: dict[str, Any] = {}
    for project in sorted(ALLOWED_PROJECTS):
        subset = [row for row in scored if row["project"] == project]
        by_project[project] = _score_summary(subset)

    breakdown: dict[str, dict[str, Any]] = {"market_regime": {}, "asset_class": {}}
    record_by_id = {record.get("forecast_id"): record for record in valid_records}
    for dimension, key in (("market_regime", "market_regime"), ("asset_class", "asset_classes")):
        grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in scored:
            record = record_by_id.get(row["forecast_id"], {})
            for value in _get(record, "applicability", key, default=[]) or []:
                if _nonempty_string(value):
                    grouped[str(value)].append(row)
        breakdown[dimension] = {name: _score_summary(rows) for name, rows in sorted(grouped.items())}

    process_records = [record for record in valid_records if record.get("status") != "draft"]
    compliance_counts: dict[str, list[bool]] = defaultdict(list)
    for record in process_records:
        for key, value in _compliance(record).items():
            compliance_counts[key].append(value)
    process_compliance = {
        key: {"n": len(values), "passing": sum(values), "share": _mean([1.0 if value else 0.0 for value in values])}
        for key, values in sorted(compliance_counts.items())
    }

    market_project_score = _mean([float(row["project_score"]) for row in market_rows])
    market_score = _mean([float(row["market_score"]) for row in market_rows])

    return {
        "report_version": 1,
        "record_count": len(records),
        "valid_record_count": len(valid_records),
        "invalid_record_count": len(records) - len(valid_records),
        "status_counts": dict(sorted(statuses.items())),
        "project_counts": dict(sorted(projects.items())),
        "validation": validation_rows,
        "scoring": {
            "resolved_scored_count": len(scored),
            "binary": _score_summary(binary),
            "numeric": _score_summary(numeric),
            "by_project": by_project,
            "by_regime_and_asset_class": breakdown,
            "project_vs_polymarket": {
                "n": len(market_rows),
                "project_brier": market_project_score,
                "market_brier": market_score,
                "relative_improvement_vs_market": _relative_improvement(market_project_score, market_score),
            },
        },
        "calibration": {
            "project_probability_buckets": _calibration(binary),
            "polymarket_probability_buckets": _calibration(
                [
                    {
                        **row,
                        "effective_forecast": row["market_probability_at_cutoff"],
                        "project_score": row["market_score"],
                    }
                    for row in market_rows
                ]
            ),
        },
        "process_compliance": process_compliance,
        "scores": scored,
    }


def _format_number(value: Any, digits: int = 6) -> str:
    return "—" if value is None else f"{float(value):.{digits}f}"


def _format_percent(value: Any) -> str:
    return "—" if value is None else f"{float(value):.2%}"


def render_markdown(report: Mapping[str, Any]) -> str:
    lines = [
        "# Forecast accuracy and calibration report",
        "",
        f"- Records discovered: **{report['record_count']}**",
        f"- Valid records: **{report['valid_record_count']}**",
        f"- Invalid records: **{report['invalid_record_count']}**",
        f"- Resolved records scored: **{report['scoring']['resolved_scored_count']}**",
        "",
        "## Score summary",
        "",
        "| Group | N | Project score | Benchmark score | Relative improvement |",
        "|---|---:|---:|---:|---:|",
    ]
    groups = {
        "Binary": report["scoring"]["binary"],
        "Numeric": report["scoring"]["numeric"],
        "Signals": report["scoring"]["by_project"]["signals"],
        "Polymarket": report["scoring"]["by_project"]["polymarket"],
    }
    for name, row in groups.items():
        lines.append(
            f"| {name} | {row['n']} | {_format_number(row['project_score'])} | "
            f"{_format_number(row['benchmark_score'])} | {_format_number(row['relative_improvement'])} |"
        )

    market = report["scoring"]["project_vs_polymarket"]
    lines.extend(
        [
            "",
            "## Project versus Polymarket",
            "",
            f"Comparable resolved binary forecasts: **{market['n']}**",
            f"- Project Brier: **{_format_number(market['project_brier'])}**",
            f"- Market Brier: **{_format_number(market['market_brier'])}**",
            f"- Relative improvement: **{_format_percent(market['relative_improvement_vs_market'])}**",
            "",
            "## Project calibration",
            "",
            "| Probability bucket | N | Mean forecast | Observed rate | Gap | Mean Brier |",
            "|---|---:|---:|---:|---:|---:|",
        ]
    )
    for bucket in report["calibration"]["project_probability_buckets"]:
        lines.append(
            "| "
            f"{bucket['lower']:.0%}–{bucket['upper']:.0%} | {bucket['n']} | "
            f"{bucket['mean_forecast']:.3f} | {bucket['observed_rate']:.3f} | "
            f"{bucket['calibration_gap']:.3f} | {bucket['mean_brier']:.6f} |"
        )
    if not report["calibration"]["project_probability_buckets"]:
        lines.append("| No resolved binary forecasts yet | 0 | — | — | — | — |")

    lines.extend(["", "## Process compliance", "", "| Requirement | Passing | N | Share |", "|---|---:|---:|---:|"])
    for name, row in report["process_compliance"].items():
        share = "—" if row["share"] is None else f"{row['share']:.1%}"
        lines.append(f"| {name} | {row['passing']} | {row['n']} | {share} |")
    if not report["process_compliance"]:
        lines.append("| No countable forecasts yet | 0 | 0 | — |")

    invalid = [row for row in report["validation"] if row["errors"]]
    lines.extend(["", "## Validation", ""])
    if not invalid:
        lines.append("All discovered forecast records passed validation.")
    else:
        for row in invalid:
            lines.append(f"### {row['forecast_id'] or 'unknown forecast'}")
            for issue in row["errors"]:
                lines.append(f"- `{issue['path']}`: {issue['message']}")
    lines.append("")
    return "\n".join(lines)


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _load_many(path: Path) -> tuple[list[dict[str, Any]], list[tuple[Path, str]]]:
    records: list[dict[str, Any]] = []
    failures: list[tuple[Path, str]] = []
    for record_path in discover_records(path):
        try:
            records.append(load_record(record_path))
        except RecordValidationError as exc:
            failures.append((record_path, str(exc)))
    return records, failures


def command_validate(args: argparse.Namespace) -> int:
    records, load_failures = _load_many(Path(args.records))
    failures = 0
    for path, message in load_failures:
        failures += 1
        print(f"ERROR {path}: {message}")
    for record in records:
        issues = validate_record(record)
        for issue in issues:
            print(f"{issue.severity.upper()} {record.get('forecast_id', '<unknown>')} {issue.path}: {issue.message}")
            if issue.severity == "error":
                failures += 1
    print(f"Validated {len(records)} forecast record(s); {failures} error(s).")
    return 1 if failures else 0


def command_score(args: argparse.Namespace) -> int:
    records, load_failures = _load_many(Path(args.records))
    if load_failures:
        for path, message in load_failures:
            print(f"ERROR {path}: {message}", file=sys.stderr)
        return 1
    rows: list[dict[str, Any]] = []
    failures = 0
    for record in records:
        if record.get("status") != "resolved":
            continue
        try:
            rows.append(score_record(record))
        except RecordValidationError as exc:
            failures += 1
            print(f"ERROR {record.get('forecast_id', '<unknown>')}: {exc}", file=sys.stderr)
    output = {"score_version": 1, "scores": rows}
    if args.output:
        _write_json(Path(args.output), output)
    else:
        print(json.dumps(output, indent=2, sort_keys=True))
    return 1 if failures else 0


def command_report(args: argparse.Namespace) -> int:
    records, load_failures = _load_many(Path(args.records))
    if load_failures:
        for path, message in load_failures:
            print(f"ERROR {path}: {message}", file=sys.stderr)
        return 1
    report = build_report(records)
    if args.json_output:
        _write_json(Path(args.json_output), report)
    if args.markdown_output:
        _write_text(Path(args.markdown_output), render_markdown(report))
    if not args.json_output and not args.markdown_output:
        print(json.dumps(report, indent=2, sort_keys=True))
    return 1 if report["invalid_record_count"] else 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate = subparsers.add_parser("validate", help="validate all forecast records")
    validate.add_argument("--records", required=True, help="record JSON file or directory")
    validate.set_defaults(func=command_validate)

    score = subparsers.add_parser("score", help="score resolved valid forecasts")
    score.add_argument("--records", required=True, help="record JSON file or directory")
    score.add_argument("--output", help="optional JSON output path")
    score.set_defaults(func=command_score)

    report = subparsers.add_parser("report", help="generate score, calibration, and process reports")
    report.add_argument("--records", required=True, help="record JSON file or directory")
    report.add_argument("--json-output", help="JSON report output path")
    report.add_argument("--markdown-output", help="Markdown report output path")
    report.set_defaults(func=command_report)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
