#!/usr/bin/env python3
"""Verify a result ledger against frozen JSON experiment outputs."""

from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
from collections import Counter
from fractions import Fraction
from pathlib import Path
from typing import Any


ALLOWED_STATUSES = {"VERIFIED", "MISMATCH", "UNVERIFIED", "NOT_APPLICABLE"}
SELECTION_AGGREGATIONS = {"best", "max", "min", "maximum", "minimum"}
SUPPORTED_AGGREGATIONS = {"single", "mean", "median", "max", "min", "maximum", "minimum"}
INPUT_FIELDS = (
    "claim_id",
    "artifact",
    "source_path",
    "json_path",
    "reported_value",
    "aggregation",
    "run_count",
    "selection_policy",
)
OUTPUT_FIELDS = (*INPUT_FIELDS, "observed_value", "status", "evidence", "risk_flag")


def parse_literal(value: str) -> Any:
    stripped = value.strip()
    if not stripped:
        return ""
    try:
        return load_json(stripped)
    except json.JSONDecodeError:
        return stripped


def _reject_json_constant(value: str) -> Any:
    """Reject non-standard JSON constants such as NaN and Infinity."""
    raise ValueError(f"non-finite JSON constant is not allowed: {value}")


def _finite_float(value: str) -> float:
    parsed = float(value)
    if not math.isfinite(parsed):
        raise ValueError(f"JSON number exceeds the finite numeric range: {value}")
    return parsed


def load_json(value: str) -> Any:
    return json.loads(value, parse_constant=_reject_json_constant, parse_float=_finite_float)


def json_path_get(value: Any, path: str) -> Any:
    current = value
    if not path.strip():
        return current
    for part in path.split("."):
        if isinstance(current, dict) and part in current:
            current = current[part]
        elif isinstance(current, list) and part.isdigit() and int(part) < len(current):
            current = current[int(part)]
        else:
            raise KeyError(part)
    return current


def equivalent(reported: Any, observed: Any, relative_tolerance: float) -> bool:
    if isinstance(reported, bool) or isinstance(observed, bool):
        return isinstance(reported, bool) and isinstance(observed, bool) and reported is observed
    if isinstance(reported, (int, float)) and isinstance(observed, (int, float)):
        if any(isinstance(value, float) and not math.isfinite(value) for value in (reported, observed)):
            return False
        # Preserve large integers and avoid float conversion or subtraction overflow.
        left, right = Fraction(reported), Fraction(observed)
        tolerance = Fraction(relative_tolerance)
        return abs(left - right) <= max(tolerance, tolerance * max(abs(left), abs(right)))
    if isinstance(reported, list) and isinstance(observed, list):
        return len(reported) == len(observed) and all(
            equivalent(left, right, relative_tolerance) for left, right in zip(reported, observed)
        )
    if isinstance(reported, dict) and isinstance(observed, dict):
        return reported.keys() == observed.keys() and all(
            equivalent(reported[key], observed[key], relative_tolerance) for key in reported
        )
    return type(reported) is type(observed) and reported == observed


def aggregate_value(value: Any, aggregation: str, run_count: int) -> Any:
    if aggregation == "single":
        return value
    if not isinstance(value, list) or len(value) != run_count:
        raise ValueError("Aggregation requires a per-run list with exactly run_count values; a summary scalar is insufficient.")
    if not all(type(item) in (int, float) for item in value):
        raise ValueError("Aggregation requires numeric per-run values, excluding booleans, strings, and nulls.")
    if aggregation == "mean":
        result = statistics.mean(value)
    elif aggregation == "median":
        ordered = sorted(value)
        midpoint = len(ordered) // 2
        result = ordered[midpoint] if len(ordered) % 2 else statistics.mean(ordered[midpoint - 1:midpoint + 1])
    elif aggregation in {"max", "maximum"}:
        result = max(value)
    else:
        result = min(value)
    if isinstance(result, float) and not math.isfinite(result):
        raise ValueError("The aggregate is not a finite numeric value.")
    return result


def inside_project(project: Path, source: Path) -> bool:
    try:
        source.relative_to(project)
        return True
    except ValueError:
        return False


def verify_row(row: dict[str, Any], project: Path, relative_tolerance: float) -> dict[str, str]:
    result = {field: row[field] if isinstance(row.get(field), str) else "" for field in INPUT_FIELDS}
    result.update({"observed_value": "", "status": "UNVERIFIED", "evidence": "", "risk_flag": ""})
    if None in row or any(not isinstance(row.get(field), str) for field in INPUT_FIELDS):
        result.update(evidence="Malformed ledger row: missing or extra CSV cells.")
        return result
    if not result["claim_id"].strip() or not result["artifact"].strip():
        result.update(evidence="claim_id and artifact are required to identify the reported result.")
        return result

    aggregation = result["aggregation"].strip().lower()
    if aggregation in {"not-applicable", "not_applicable", "n/a"}:
        result.update(status="NOT_APPLICABLE", evidence="Ledger declares this check not applicable.")
        return result

    try:
        run_count = int(result["run_count"] or "0")
    except ValueError:
        result.update(evidence="run_count is not an integer.")
        return result
    if run_count < 1:
        result.update(evidence="run_count must be a positive integer.")
        return result

    selection_policy = result["selection_policy"].strip().lower().replace("_", "-")
    if aggregation in SELECTION_AGGREGATIONS and run_count > 1 and selection_policy in {"", "none", "n/a", "na", "not-applicable", "not applicable"}:
        result.update(
            evidence="Multiple-run best-value selection has no disclosed selection policy.",
            risk_flag="UNDISCLOSED_SELECTION_RISK",
        )
        return result
    if aggregation not in SUPPORTED_AGGREGATIONS:
        result.update(evidence="Unsupported or ambiguous aggregation; use single, mean, median, min, or max with traceable run values.")
        return result
    if aggregation == "single" and run_count != 1:
        result.update(evidence="A single-value check requires run_count=1; it cannot verify a multiple-run summary.")
        return result

    source_text = result["source_path"].strip()
    if not source_text:
        result.update(evidence="No source artifact was supplied.")
        return result
    source = (project / source_text).resolve()
    if not inside_project(project, source):
        result.update(evidence="Source path escapes the project root.")
        return result
    if not source.is_file():
        result.update(evidence=f"Source artifact is missing: {source_text}")
        return result
    if source.suffix.lower() != ".json":
        result.update(evidence="Deterministic verifier supports frozen JSON sources; create a provenance-preserving intermediate ledger for other formats.")
        return result
    if not result["json_path"].strip():
        result.update(evidence="No JSON path was supplied for the frozen source value.")
        return result

    try:
        observed = json_path_get(
            load_json(source.read_text(encoding="utf-8")),
            result["json_path"],
        )
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError, KeyError, IndexError) as error:
        result.update(evidence=f"Could not read requested source value: {error}")
        return result

    try:
        reported = parse_literal(result["reported_value"])
        observed = aggregate_value(observed, aggregation, run_count)
    except (ValueError, OverflowError) as error:
        result.update(evidence=f"Could not verify the reported value or aggregation: {error}")
        return result
    if reported is None or observed is None:
        result.update(evidence="Null values cannot establish a reported result.")
        return result
    result["observed_value"] = json.dumps(observed, separators=(",", ":"), sort_keys=True, allow_nan=False)
    operation = "Reported value" if aggregation == "single" else f"Reported {aggregation} recomputed from {run_count} runs"
    if equivalent(reported, observed, relative_tolerance):
        result.update(status="VERIFIED", evidence=f"{operation} matches {source_text}:{result['json_path']}.")
    else:
        result.update(status="MISMATCH", evidence=f"{operation} differs from {source_text}:{result['json_path']}.")
    return result


def write_outputs(rows: list[dict[str, str]], output: Path) -> None:
    output.mkdir(parents=True, exist_ok=True)
    with (output / "result-ledger.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=OUTPUT_FIELDS)
        writer.writeheader()
        writer.writerows(rows)

    map_lines = [
        "# Claim-Result Map",
        "",
        "| Claim ID | Artifact | Source | Status | Evidence |",
        "|---|---|---|---|---|",
    ]
    for row in rows:
        evidence = row["evidence"].replace("|", "\\|")
        map_lines.append(f"| {row['claim_id']} | {row['artifact']} | {row['source_path']} | {row['status']} | {evidence} |")
    (output / "claim-result-map.md").write_text("\n".join(map_lines) + "\n", encoding="utf-8")

    counts = Counter(row["status"] for row in rows)
    report_lines = [
        "# Verification Report",
        "",
        "## Status Counts",
        "",
        *[f"- {status}: {counts.get(status, 0)}" for status in ("VERIFIED", "MISMATCH", "UNVERIFIED", "NOT_APPLICABLE")],
        "",
        "## Findings",
        "",
    ]
    findings = [row for row in rows if row["status"] not in {"VERIFIED", "NOT_APPLICABLE"} or row["risk_flag"]]
    if findings:
        for row in findings:
            risk = f" [{row['risk_flag']}]" if row["risk_flag"] else ""
            report_lines.append(f"- **{row['claim_id']} — {row['status']}**{risk}: {row['evidence']}")
    else:
        report_lines.append("- All scoped ledger rows are verified or not applicable.")
    report_lines.extend([
        "",
        "## Integrity Statement",
        "",
        "The verifier read source evidence and wrote separate audit outputs. It did not modify experimental results or manuscript claims.",
        "",
    ])
    (output / "verification-report.md").write_text("\n".join(report_lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, required=True)
    parser.add_argument("--ledger", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--relative-tolerance", type=float, default=1e-12)
    args = parser.parse_args()

    project = args.project_root.resolve()
    if not project.is_dir():
        parser.error(f"project root is not a directory: {project}")
    if not args.ledger.is_file():
        parser.error(f"ledger does not exist: {args.ledger}")
    if not math.isfinite(args.relative_tolerance) or args.relative_tolerance < 0:
        parser.error("relative tolerance must be a finite non-negative number")

    try:
        with args.ledger.open(encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            missing = set(INPUT_FIELDS) - set(reader.fieldnames or [])
            if missing:
                parser.error(f"ledger is missing required columns: {', '.join(sorted(missing))}")
            rows = [verify_row(row, project, args.relative_tolerance) for row in reader]
    except (OSError, UnicodeError, csv.Error) as error:
        parser.error(f"could not read ledger: {error}")
    if not rows:
        parser.error("ledger contains no data rows; no verification was performed")

    if any(row["status"] not in ALLOWED_STATUSES for row in rows):
        raise RuntimeError("internal error: unsupported status generated")
    write_outputs(rows, args.output_dir)
    counts = Counter(row["status"] for row in rows)
    print(json.dumps({"rows": len(rows), "status_counts": counts}, indent=2, sort_keys=True))
    return 1 if counts["MISMATCH"] or counts["UNVERIFIED"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
