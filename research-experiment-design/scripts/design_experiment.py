#!/usr/bin/env python3
"""Create a portable experiment-design package from a JSON specification."""

from __future__ import annotations

import argparse
import csv
import json
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

    compute = nested(spec, "compute", default={})
    if isinstance(compute, dict):
        memory = float(compute.get("per_run_memory_gb", 0) or 0)
        memory_limit = float(compute.get("available_memory_gb", 0) or 0)
        total_hours = float(compute.get("per_run_hours", 0) or 0) * int(compute.get("number_of_runs", 0) or 0)
        hour_limit = float(compute.get("max_compute_hours", 0) or 0)
        total_storage = float(compute.get("storage_per_run_gb", 0) or 0) * int(compute.get("number_of_runs", 0) or 0)
        storage_limit = float(compute.get("max_storage_gb", 0) or 0)
        overruns: list[str] = []
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
    dataset = nested(spec, "dataset", default={})
    split = nested(spec, "split", default={})
    baseline = nested(spec, "baseline", "primary", default={})
    proposed = nested(spec, "proposed_method", default={})
    randomness = nested(spec, "randomness", default={})
    statistics = nested(spec, "statistical_plan", default={})
    compute = nested(spec, "compute", default={})
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
    seeds = as_list(nested(spec, "randomness", "seeds", default=[])) or [0]
    models = (
        ("baseline", nested(spec, "baseline", "primary", "name")),
        ("proposed", nested(spec, "proposed_method", "name")),
    )
    with (output / "experiment-matrix.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        count = 1
        for role, model in models:
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
        spec = json.loads(args.spec.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        print(json.dumps({"status": "INVALID_SPEC", "error": str(error)}))
        return 2
    if not isinstance(spec, dict):
        print(json.dumps({"status": "INVALID_SPEC", "error": "top-level JSON must be an object"}))
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
