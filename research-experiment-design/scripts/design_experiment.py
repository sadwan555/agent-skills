#!/usr/bin/env python3
"""Create a portable experiment-design package from a JSON specification."""

from __future__ import annotations

import argparse
import csv
import json
import math
import re
import sys
from pathlib import Path
from typing import Any


BLOCKING_RISKS = (
    "UNFAIR_COMPARISON",
    "CONFOUNDED_EXPERIMENT",
    "TEST_SET_TUNING",
    "SELECTION_BIAS_RISK",
    "SPLIT_MISMATCH_RISK",
    "COMPUTE_BUDGET_RISK",
)

RISK_MITIGATIONS = {
    "UNFAIR_COMPARISON": "Use identical data, split, preprocessing, and evaluation protocol for the compared methods.",
    "CONFOUNDED_EXPERIMENT": "Change one claim-relevant factor at a time or redesign as a factorial experiment.",
    "TEST_SET_TUNING": "Freeze the test set and use training or validation data for every tuning decision.",
    "SELECTION_BIAS_RISK": "Report every declared seed using the predeclared aggregation policy.",
    "SPLIT_MISMATCH_RISK": "Choose a split whose grouping and temporal semantics match deployment.",
    "COMPUTE_BUDGET_RISK": "Reduce the mandatory matrix or secure sufficient memory, time, and storage before execution.",
}


def nested(spec: dict[str, Any], *keys: str, default: Any = "") -> Any:
    value: Any = spec
    for key in keys:
        if not isinstance(value, dict) or key not in value:
            return default
        value = value[key]
    return value


def as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if value in (None, ""):
        return []
    return [value]


def mapping(value: Any) -> dict[str, Any]:
    """Return a mapping section or an empty mapping for optional sections."""
    return value if isinstance(value, dict) else {}


def finite_json_number(value: str) -> float:
    parsed = float(value)
    if not math.isfinite(parsed):
        raise ValueError("JSON numbers must be finite")
    return parsed


def validate_spec(spec: dict[str, Any]) -> list[str]:
    """Validate the shape needed by the renderer before any files are written."""
    errors: list[str] = []
    mapping_sections = (
        "dataset", "split", "baseline", "proposed_method", "randomness",
        "metrics", "statistical_plan", "compute", "variables", "ablation",
    )
    for section in mapping_sections:
        value = spec.get(section)
        required = section != "ablation"
        if (required or section in spec) and not isinstance(value, dict):
            errors.append(f"{section} must be an object")

    baseline = spec.get("baseline")
    if isinstance(baseline, dict) and not isinstance(baseline.get("primary"), dict):
        errors.append("baseline.primary must be an object")

    required_text = (
        "research_question", "hypothesis", "falsification_condition", "claim_target", "task_type", "stopping_rule",
        "dataset.name", "dataset.version", "dataset.source", "dataset.task_definition",
        "split.method", "baseline.primary.name", "proposed_method.name", "randomness.report_policy",
    )
    for field in required_text:
        value = nested(spec, *field.split("."))
        if not isinstance(value, str) or not value.strip():
            errors.append(f"{field} must be a non-empty string")

    experiment_class = spec.get("experiment_class")
    if experiment_class not in {"PLANNED", "EXPLORATORY", "CONFIRMATORY"}:
        errors.append("experiment_class must be PLANNED, EXPLORATORY, or CONFIRMATORY")

    for field in ("time_order_preserved", "test_used_for_hyperparameters"):
        if not isinstance(nested(spec, "split", field, default=None), bool):
            errors.append(f"split.{field} must be a boolean")

    for field in ("changed_factors", "execution_plan", "variables.independent", "variables.controlled", "variables.dependent"):
        value = nested(spec, *field.split("."), default=None)
        if not isinstance(value, list) or not value or any(not isinstance(item, str) or not item.strip() for item in value):
            errors.append(f"{field} must be a non-empty array of strings")

    for field in ("split.leakage_controls", "statistical_plan.summary", "ablation.components"):
        value = nested(spec, *field.split("."), default=[])
        if not isinstance(value, list) or (field == "statistical_plan.summary" and not value) or any(not isinstance(item, str) or not item.strip() for item in value):
            errors.append(f"{field} must be an array of strings")

    for field in ("statistical_plan.effect_size", "statistical_plan.confidence_interval"):
        value = nested(spec, *field.split("."), default=None)
        if not isinstance(value, str) or not value.strip():
            errors.append(f"{field} must be a non-empty string")

    seeds = nested(spec, "randomness", "seeds", default=None)
    valid_seeds = isinstance(seeds, list) and bool(seeds) and all(type(seed) is int for seed in seeds)
    if not valid_seeds or len(set(seeds)) != len(seeds):
        errors.append("randomness.seeds must be a non-empty array of distinct integers")
    repetitions = nested(spec, "randomness", "number_of_runs", default=None)
    if type(repetitions) is not int or repetitions <= 0 or (valid_seeds and repetitions != len(seeds)):
        errors.append("randomness.number_of_runs must equal the number of declared seeds")

    for section in ("primary", "secondary"):
        metrics = nested(spec, "metrics", section, default=[])
        if not isinstance(metrics, list) or (section == "primary" and not metrics):
            errors.append(f"metrics.{section} must be an array of metric objects" + (" with at least one metric" if section == "primary" else ""))
        elif any(not isinstance(item, dict) or not isinstance(item.get("name"), str) or not item["name"].strip() for item in metrics):
            errors.append(f"metrics.{section} entries must be objects with a non-empty name")

    compute = spec.get("compute")
    if isinstance(compute, dict):
        for field in ("per_run_memory_gb", "available_memory_gb", "per_run_hours", "number_of_runs", "max_compute_hours", "storage_per_run_gb", "max_storage_gb"):
            value = compute.get(field)
            if field not in compute and field != "number_of_runs":
                continue
            if isinstance(value, bool):
                errors.append(f"compute.{field} must be numeric")
                continue
            try:
                parsed = float(value)
            except (TypeError, ValueError, OverflowError):
                errors.append(f"compute.{field} must be numeric")
                continue
            if not math.isfinite(parsed) or parsed < 0:
                errors.append(f"compute.{field} must be a finite non-negative number")
            if field == "number_of_runs" and (not parsed.is_integer() or parsed <= 0):
                errors.append("compute.number_of_runs must be a positive integer")
    return errors


def matrix_models(spec: dict[str, Any]) -> tuple[tuple[str, str, list[int]], ...]:
    """Use a single baseline fit only when the input explicitly declares it."""
    seeds = spec["randomness"]["seeds"]
    baseline = spec["baseline"]["primary"]
    baseline_seeds = seeds[:1] if comparable_text(baseline.get("training_budget")) == "single deterministic fit" else seeds
    return (
        ("baseline", baseline["name"], baseline_seeds),
        ("proposed", spec["proposed_method"]["name"], seeds),
    )


def comparable_text(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value).strip().lower()).strip()


def slug(value: Any) -> str:
    text = re.sub(r"[^a-z0-9]+", "-", comparable_text(value)).strip("-")
    return text or "component"


def add_risk(risks: list[dict[str, str]], code: str, evidence: str) -> None:
    if code not in {risk["code"] for risk in risks}:
        risks.append(
            {
                "code": code,
                "severity": "BLOCKING",
                "evidence": evidence,
                "mitigation": RISK_MITIGATIONS[code],
            }
        )


def assess_risks(spec: dict[str, Any]) -> list[dict[str, str]]:
    risks: list[dict[str, str]] = []

    baseline = nested(spec, "baseline", "primary", default={})
    proposed = nested(spec, "proposed_method", default={})
    mismatches: list[str] = []
    for field in ("dataset", "split", "preprocessing"):
        left = comparable_text(baseline.get(field, "")) if isinstance(baseline, dict) else ""
        right = comparable_text(proposed.get(field, "")) if isinstance(proposed, dict) else ""
        if left and right and left != right:
            mismatches.append(field)
    if mismatches:
        add_risk(
            risks,
            "UNFAIR_COMPARISON",
            "Baseline and proposed method differ on controlled fields: " + ", ".join(mismatches) + ".",
        )

    changed = [comparable_text(item) for item in as_list(spec.get("changed_factors")) if comparable_text(item)]
    target = comparable_text(spec.get("claim_target"))
    target_matches = any(target in factor or factor in target for factor in changed) if target else True
    if len(changed) > 1 or (changed and not target_matches):
        add_risk(
            risks,
            "CONFOUNDED_EXPERIMENT",
            "The comparison changes factors beyond the single declared claim target: " + ", ".join(changed) + ".",
        )

    if bool(nested(spec, "split", "test_used_for_hyperparameters", default=False)):
        add_risk(risks, "TEST_SET_TUNING", "The specification allows the test set to influence hyperparameters.")

    report_policy = comparable_text(nested(spec, "randomness", "report_policy"))
    if report_policy in {"best", "best_seed", "max", "maximum", "min", "minimum"}:
        add_risk(
            risks,
            "SELECTION_BIAS_RISK",
            f"The declared report policy is '{report_policy}', which selects a favorable run.",
        )

    task_type = comparable_text(spec.get("task_type"))
    method = comparable_text(nested(spec, "split", "method"))
    preserves_time = bool(nested(spec, "split", "time_order_preserved", default=False))
    temporal_task = task_type in {"time series", "forecasting", "recommendation", "recommender", "continual learning"}
    temporal_method = any(term in method for term in ("temporal", "time", "rolling", "forward"))
    if temporal_task and (not preserves_time or not temporal_method):
        add_risk(
            risks,
            "SPLIT_MISMATCH_RISK",
            f"Task '{task_type}' uses split '{method}' without explicit temporal preservation.",
        )

    compute = mapping(nested(spec, "compute", default={}))
    if isinstance(compute, dict):
        memory = float(compute.get("per_run_memory_gb", 0) or 0)
        memory_limit = float(compute.get("available_memory_gb", 0) or 0)
        total_hours = float(compute.get("per_run_hours", 0) or 0) * int(float(compute.get("number_of_runs", 0) or 0))
        hour_limit = float(compute.get("max_compute_hours", 0) or 0)
        total_storage = float(compute.get("storage_per_run_gb", 0) or 0) * int(float(compute.get("number_of_runs", 0) or 0))
        storage_limit = float(compute.get("max_storage_gb", 0) or 0)
        overruns: list[str] = []
        matrix_runs = sum(len(seeds) for _, _, seeds in matrix_models(spec))
        declared_runs = int(float(compute["number_of_runs"]))
        if declared_runs < matrix_runs:
            overruns.append(f"run count {declared_runs} is below the {matrix_runs} generated experiment-matrix rows")
        if memory_limit and memory > memory_limit:
            overruns.append(f"memory {memory:g}>{memory_limit:g} GB")
        if hour_limit and total_hours > hour_limit:
            overruns.append(f"time {total_hours:g}>{hour_limit:g} hours")
        if storage_limit and total_storage > storage_limit:
            overruns.append(f"storage {total_storage:g}>{storage_limit:g} GB")
        if overruns:
            add_risk(risks, "COMPUTE_BUDGET_RISK", "Declared mandatory matrix exceeds budget: " + "; ".join(overruns) + ".")

    return risks


def metric_names(spec: dict[str, Any]) -> list[str]:
    metrics: list[str] = []
    for section in ("primary", "secondary"):
        for item in as_list(nested(spec, "metrics", section, default=[])):
            if isinstance(item, dict) and item.get("name"):
                metrics.append(str(item["name"]))
    return metrics


def write_plan(spec: dict[str, Any], output: Path, risks: list[dict[str, str]]) -> None:
    status = "NEEDS_REVISION" if risks else "READY_FOR_EXECUTION"
    dataset = mapping(nested(spec, "dataset", default={}))
    split = mapping(nested(spec, "split", default={}))
    baseline = mapping(nested(spec, "baseline", "primary", default={}))
    proposed = mapping(nested(spec, "proposed_method", default={}))
    randomness = mapping(nested(spec, "randomness", default={}))
    statistics = mapping(nested(spec, "statistical_plan", default={}))
    compute = mapping(nested(spec, "compute", default={}))
    primary_metrics = as_list(nested(spec, "metrics", "primary", default=[]))
    secondary_metrics = as_list(nested(spec, "metrics", "secondary", default=[]))

    def metric_lines(items: list[Any]) -> str:
        lines = []
        for item in items:
            if isinstance(item, dict):
                lines.append(f"- {item.get('name', '')}: {item.get('rationale', '')}")
        return "\n".join(lines) or "- Not declared"

    lines = [
        f"# {spec.get('project_title', 'Experiment plan')}",
        "",
        f"**Readiness:** `{status}`  ",
        f"**Experiment class:** `{spec.get('experiment_class', 'PLANNED')}`",
        "",
        "## Research question → hypothesis → falsification",
        "",
        f"- Research question: {spec.get('research_question', '')}",
        f"- Hypothesis: {spec.get('hypothesis', '')}",
        f"- Falsification condition: {spec.get('falsification_condition', '')}",
        f"- Claim target: {spec.get('claim_target', '')}",
        "",
        "## Dataset → split",
        "",
        f"- Dataset: {dataset.get('name', '')} ({dataset.get('version', '')})",
        f"- Source: {dataset.get('source', '')}",
        f"- Task: {dataset.get('task_definition', '')}",
        f"- Split method: {split.get('method', '')}",
        f"- Train/validation/test: {split.get('train', '')} / {split.get('validation', '')} / {split.get('test', '')}",
        f"- Group key: {split.get('group_key', '') or 'none'}",
        f"- Time order preserved: {bool(split.get('time_order_preserved', False))}",
        f"- Leakage controls: {', '.join(map(str, as_list(split.get('leakage_controls'))))}",
        "",
        "## Baseline → variables → controls",
        "",
        f"- Baseline: {baseline.get('name', '')}",
        f"- Proposed method: {proposed.get('name', '')}",
        f"- Independent variables: {', '.join(map(str, as_list(nested(spec, 'variables', 'independent', default=[]))))}",
        f"- Controlled variables: {', '.join(map(str, as_list(nested(spec, 'variables', 'controlled', default=[]))))}",
        f"- Dependent variables: {', '.join(map(str, as_list(nested(spec, 'variables', 'dependent', default=[]))))}",
        "",
        "## Metrics",
        "",
        "### Primary",
        metric_lines(primary_metrics),
        "",
        "### Secondary",
        metric_lines(secondary_metrics),
        "",
        "## Seeds → matrix → statistics",
        "",
        f"- Seeds: {', '.join(map(str, as_list(randomness.get('seeds'))))}",
        f"- Report policy: {randomness.get('report_policy', '')}",
        f"- Summary: {', '.join(map(str, as_list(statistics.get('summary'))))}",
        f"- Confidence interval: {statistics.get('confidence_interval', '')}",
        f"- Effect size: {statistics.get('effect_size', '')}",
        "",
        "## Ablation",
        "",
        f"- Components: {', '.join(map(str, as_list(nested(spec, 'ablation', 'components', default=[])))) or 'not applicable'}",
        "",
        "## Compute → stopping rule → execution",
        "",
        f"- Hardware: {compute.get('hardware', '')}",
        f"- Mandatory runs: {compute.get('number_of_runs', '')}",
        f"- Per-run estimate: {compute.get('per_run_hours', '')} hours, {compute.get('per_run_memory_gb', '')} GB memory, {compute.get('storage_per_run_gb', '')} GB storage",
        f"- Stopping rule: {spec.get('stopping_rule', '')}",
        "- Execution plan:",
    ]
    lines.extend(f"  {index}. {step}" for index, step in enumerate(as_list(spec.get("execution_plan")), start=1))
    lines.extend(["", "## Blocking risks", ""])
    if risks:
        lines.extend(f"- `{risk['code']}`: {risk['evidence']}" for risk in risks)
    else:
        lines.append("- None detected by the deterministic checks. Human scientific review is still required before execution.")
    lines.extend(["", "> This document is a plan. It does not claim that any experiment was executed.", ""])
    (output / "experiment-plan.md").write_text("\n".join(lines), encoding="utf-8")


def write_experiment_matrix(spec: dict[str, Any], output: Path) -> None:
    fields = [
        "experiment_id", "research_question", "dataset", "split", "model", "baseline",
        "independent_variable", "controlled_variables", "seed", "metrics", "expected_output", "status",
    ]
    with (output / "experiment-matrix.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        count = 1
        for role, model, seeds in matrix_models(spec):
            for seed in seeds:
                writer.writerow(
                    {
                        "experiment_id": f"exp-{count:03d}",
                        "research_question": spec.get("research_question", ""),
                        "dataset": nested(spec, "dataset", "name"),
                        "split": nested(spec, "split", "method"),
                        "model": model,
                        "baseline": role == "baseline",
                        "independent_variable": "; ".join(map(str, as_list(nested(spec, "variables", "independent", default=[])))),
                        "controlled_variables": "; ".join(map(str, as_list(nested(spec, "variables", "controlled", default=[])))),
                        "seed": seed,
                        "metrics": "; ".join(metric_names(spec)),
                        "expected_output": "run record conforming to run-schema.json",
                        "status": spec.get("experiment_class", "PLANNED"),
                    }
                )
                count += 1


def write_ablation_matrix(spec: dict[str, Any], output: Path) -> None:
    components = [str(item) for item in as_list(nested(spec, "ablation", "components", default=[]))]
    if len(components) < 2:
        return
    fields = ["ablation_id", "variant", "removed_component", "controlled_variables", "seeds", "metrics", "status"]
    variants = [("full-model", "")] + [(f"without-{slug(component)}", component) for component in components]
    with (output / "ablation-matrix.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for index, (variant, removed) in enumerate(variants, start=1):
            writer.writerow(
                {
                    "ablation_id": f"abl-{index:03d}",
                    "variant": variant,
                    "removed_component": removed,
                    "controlled_variables": "; ".join(map(str, as_list(nested(spec, "variables", "controlled", default=[])))),
                    "seeds": "; ".join(map(str, as_list(nested(spec, "randomness", "seeds", default=[])))),
                    "metrics": "; ".join(metric_names(spec)),
                    "status": spec.get("experiment_class", "PLANNED"),
                }
            )


def write_risk_register(output: Path, risks: list[dict[str, str]]) -> None:
    detected = {risk["code"]: risk for risk in risks}
    lines = [
        "# Experiment design risk register",
        "",
        "| Risk code | Status | Evidence | Mitigation |",
        "|---|---|---|---|",
    ]
    for code in BLOCKING_RISKS:
        risk = detected.get(code)
        evidence = risk["evidence"] if risk else "No deterministic indicator was detected in the supplied specification."
        status = "BLOCKING" if risk else "NOT_DETECTED"
        lines.append(f"| `{code}` | {status} | {evidence} | {RISK_MITIGATIONS[code]} |")
    lines.extend(
        [
            "",
            "## Additional human-review risks",
            "",
            "- Data leakage: inspect feature construction, duplicates, group boundaries, and train-only fitting.",
            "- Insufficient seeds: justify run count using expected variance and decision stakes.",
            "- Metric misuse: confirm the primary metric measures the stated claim and cannot be swapped post hoc.",
            "- Missing provenance: verify source, version, license, transformations, and checksums before execution.",
            "- Implementation confound: ensure both paths share the same evaluation and preprocessing code.",
            "",
        ]
    )
    (output / "risk-register.md").write_text("\n".join(lines), encoding="utf-8")


def write_run_schema(output: Path) -> None:
    schema = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": "Research experiment run record",
        "type": "object",
        "additionalProperties": True,
        "required": ["experiment_id", "seed", "config", "environment", "metrics", "artifacts", "status"],
        "properties": {
            "experiment_id": {"type": "string"},
            "seed": {"type": "integer"},
            "config": {"type": "object"},
            "environment": {"type": "object"},
            "metrics": {"type": "object"},
            "artifacts": {"type": "array", "items": {"type": "string"}},
            "status": {"enum": ["PLANNED", "RUNNING", "SUCCEEDED", "FAILED", "EXCLUDED"]},
        },
    }
    (output / "run-schema.json").write_text(json.dumps(schema, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", type=Path, required=True, help="JSON experiment specification")
    parser.add_argument("--output-dir", type=Path, required=True, help="directory for generated planning artifacts")
    args = parser.parse_args()

    try:
        spec = json.loads(args.spec.read_text(encoding="utf-8"), parse_float=finite_json_number, parse_constant=finite_json_number)
    except (OSError, ValueError) as error:
        print(json.dumps({"status": "INVALID_SPEC", "error": str(error)}))
        return 2
    if not isinstance(spec, dict):
        print(json.dumps({"status": "INVALID_SPEC", "error": "top-level JSON must be an object"}))
        return 2

    validation_errors = validate_spec(spec)
    if validation_errors:
        print(json.dumps({"status": "INVALID_SPEC", "errors": validation_errors}, indent=2))
        return 2

    args.output_dir.mkdir(parents=True, exist_ok=True)
    risks = assess_risks(spec)
    write_plan(spec, args.output_dir, risks)
    write_experiment_matrix(spec, args.output_dir)
    write_ablation_matrix(spec, args.output_dir)
    write_risk_register(args.output_dir, risks)
    write_run_schema(args.output_dir)

    blocking = [risk["code"] for risk in risks]
    status = "NEEDS_REVISION" if blocking else "READY_FOR_EXECUTION"
    print(
        json.dumps(
            {
                "status": status,
                "blocking_risks": blocking,
                "output_dir": str(args.output_dir),
                "generated_files": sorted(path.name for path in args.output_dir.iterdir() if path.is_file()),
            },
            indent=2,
        )
    )
    return 1 if blocking else 0


if __name__ == "__main__":
    sys.exit(main())
