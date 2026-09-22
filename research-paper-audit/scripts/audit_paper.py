#!/usr/bin/env python3
"""Audit a structured manuscript record for cross-section consistency."""

from __future__ import annotations

import argparse
import csv
import json
import math
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any


CLAIM_STATUSES = {"SUPPORTED", "PARTIALLY_SUPPORTED", "UNSUPPORTED", "UNVERIFIED", "CONTRADICTED"}
CLAIM_TYPES = {"BACKGROUND", "NOVELTY", "METHOD", "PERFORMANCE", "COMPARATIVE", "CAUSAL", "GENERALIZATION", "LIMITATION"}
SEVERITY_ORDER = {"BLOCKER": 0, "MAJOR": 1, "MINOR": 2, "OPTIONAL": 3}
ISSUE_RULES = {
    "INTERNAL_RESULT_MISMATCH": ("BLOCKER", "research-result-verification", "Results"),
    "CONCLUSION_OVERREACH": ("MAJOR", "research-experiment-design", "Conclusion"),
    "SEED_COUNT_MISMATCH": ("MAJOR", "research-result-verification", "Experiment Setup"),
    "MISSING_REFERENCE_ENTRY": ("MAJOR", "", "References"),
    "UNCITED_REFERENCE": ("MINOR", "", "References"),
    "FIGURE_CAPTION_MISMATCH": ("MAJOR", "", "Figures"),
    "TABLE_HIGHLIGHT_ERROR": ("MAJOR", "", "Tables"),
    "PERCENTAGE_INTERPRETATION_RISK": ("MAJOR", "research-result-verification", "Results"),
    "UNSUPPORTED_STATISTICAL_LANGUAGE": ("MAJOR", "research-experiment-design", "Statistics"),
    "RESULT_VERIFICATION_REQUIRED": ("BLOCKER", "research-result-verification", "Result Verification Flags"),
    "LITERATURE_VERIFICATION_REQUIRED": ("MAJOR", "research-literature-review", "References"),
}


def as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else ([] if value in (None, "") else [value])


def normalized(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().lower())


def number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        parsed = float(value)
        return parsed if math.isfinite(parsed) else None
    except (TypeError, ValueError, OverflowError):
        return None


def validate_input(manuscript: dict[str, Any]) -> None:
    """Validate fields consumed by checks before conversion or output creation."""
    for field in ("paper", "results", "scope", "seeds", "citations"):
        if field in manuscript and not isinstance(manuscript[field], dict):
            raise ValueError(f"{field} must be an object")
    for field in ("claims", "figures", "tables", "statistics", "novelty"):
        if field not in manuscript:
            continue
        if not isinstance(manuscript[field], list):
            raise ValueError(f"{field} must be an array")
        for index, record in enumerate(manuscript[field]):
            if not isinstance(record, dict):
                raise ValueError(f"{field}[{index}] must be an object")
    for section, fields in (("scope", ("dataset_count",)), ("seeds", ("methods", "table_runs"))):
        for field in fields:
            value = manuscript.get(section, {}).get(field)
            if value is None:
                continue
            parsed = number(value)
            if parsed is None or not parsed.is_integer() or parsed < 0:
                raise ValueError(f"{section}.{field} must be a nonnegative integer")
    results = manuscript.get("results", {})
    for field in ("abstract_accuracy", "table_accuracy", "baseline", "current", "reported_improvement"):
        if results.get(field) is not None and number(results[field]) is None:
            raise ValueError(f"results.{field} must be a finite number")
    if "raw_artifacts_present" in results and not isinstance(results["raw_artifacts_present"], bool):
        raise ValueError("results.raw_artifacts_present must be a boolean")
    for section, fields in (("results", ("raw_artifact_refs",)), ("citations", ("in_text", "bibliography"))):
        for field in fields:
            record = manuscript.get(section, {})
            if field in record and (not isinstance(record[field], list) or any(not isinstance(value, str) for value in record[field])):
                raise ValueError(f"{section}.{field} must be an array of strings")
    for index, claim in enumerate(manuscript.get("claims", [])):
        for field in ("claim_text", "observed_evidence", "required_evidence", "status", "claim_type"):
            if field in claim and not isinstance(claim[field], str):
                raise ValueError(f"claims[{index}].{field} must be a string")
    for section, field in (("tables", "best_marker_correct"), ("statistics", "claims_significance"), ("novelty", "literature_verified")):
        for index, record in enumerate(manuscript.get(section, [])):
            if field in record and not isinstance(record[field], bool):
                raise ValueError(f"{section}[{index}].{field} must be a boolean")
    for index, figure in enumerate(manuscript.get("figures", [])):
        for field in ("caption_metric", "axis_metric"):
            if field in figure and not isinstance(figure[field], str):
                raise ValueError(f"figures[{index}].{field} must be a string")
    for index, statement in enumerate(manuscript.get("statistics", [])):
        for field in ("p_value",):
            if field in statement and statement[field] is not None and number(statement[field]) is None:
                raise ValueError(f"statistics[{index}].{field} must be a finite number")


def missing_evidence(manuscript: dict[str, Any]) -> list[str]:
    missing: list[str] = []
    claims = manuscript.get("claims", [])
    if not claims:
        missing.append("claims: no manuscript claims were recorded")
    for index, claim in enumerate(claims):
        if not normalized(claim.get("claim_text")) or not normalized(claim.get("observed_evidence")):
            missing.append(f"claims[{index}]: claim text or observed evidence is missing")
    for index, figure in enumerate(manuscript.get("figures", [])):
        if not normalized(figure.get("caption_metric")) or not normalized(figure.get("axis_metric")):
            missing.append(f"figures[{index}]: caption or axis metric is missing")
    for index, table in enumerate(manuscript.get("tables", [])):
        if not isinstance(table.get("best_marker_correct"), bool):
            missing.append(f"tables[{index}]: best-marker check is missing")
    return missing


def add_issue(issues: list[dict[str, str]], code: str, location: str, evidence: str, resolution: str) -> None:
    severity, downstream, category = ISSUE_RULES[code]
    key = (code, location, evidence)
    if key in {(item["code"], item["location"], item["evidence"]) for item in issues}:
        return
    issues.append(
        {
            "code": code,
            "severity": severity,
            "category": category,
            "location": location,
            "evidence": evidence,
            "required_resolution": resolution,
            "downstream_skill": downstream,
        }
    )


def assess(manuscript: dict[str, Any]) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    results = manuscript.get("results", {}) if isinstance(manuscript.get("results"), dict) else {}
    abstract_value = number(results.get("abstract_accuracy"))
    table_value = number(results.get("table_accuracy"))
    if abstract_value is not None and table_value is not None and not math.isclose(abstract_value, table_value, abs_tol=0.0005):
        add_issue(
            issues,
            "INTERNAL_RESULT_MISMATCH",
            "Abstract ↔ Results/Table",
            f"Abstract accuracy {abstract_value:g} differs from table accuracy {table_value:g}.",
            "Identify the authoritative result and reconcile every manuscript occurrence; verify lineage before changing a value.",
        )

    scope = manuscript.get("scope", {}) if isinstance(manuscript.get("scope"), dict) else {}
    dataset_count = int(number(scope.get("dataset_count")) or 0)
    conclusion_scope = normalized(scope.get("conclusion_scope"))
    broad_scope = any(term in conclusion_scope for term in ("all dataset", "any dataset", "general", "universal"))
    if dataset_count < 2 and broad_scope:
        add_issue(
            issues,
            "CONCLUSION_OVERREACH",
            "Conclusion",
            f"Conclusion scope is '{scope.get('conclusion_scope', '')}' but only {dataset_count} dataset is declared.",
            "Bound the conclusion to evaluated evidence or route a new multi-dataset design for approval.",
        )

    seeds = manuscript.get("seeds", {}) if isinstance(manuscript.get("seeds"), dict) else {}
    methods_seeds = seeds.get("methods")
    table_runs = seeds.get("table_runs")
    if methods_seeds is not None and table_runs is not None and number(methods_seeds) != number(table_runs):
        add_issue(
            issues,
            "SEED_COUNT_MISMATCH",
            "Methods ↔ Results/Table",
            f"Methods declares {methods_seeds} seeds while the table reports a {table_runs}-run aggregate.",
            "Trace the aggregate to all included runs and disclose any exclusions or selection policy.",
        )

    citations = manuscript.get("citations", {}) if isinstance(manuscript.get("citations"), dict) else {}
    in_text = {str(item) for item in as_list(citations.get("in_text"))}
    bibliography = {str(item) for item in as_list(citations.get("bibliography"))}
    missing = sorted(in_text - bibliography)
    uncited = sorted(bibliography - in_text)
    if missing:
        add_issue(
            issues,
            "MISSING_REFERENCE_ENTRY",
            "In-text citations ↔ bibliography",
            "Cited identifiers missing from the bibliography: " + ", ".join(missing) + ".",
            "Add or correct the bibliography entries after confirming the intended sources.",
        )
    if uncited:
        add_issue(
            issues,
            "UNCITED_REFERENCE",
            "Bibliography ↔ manuscript body",
            "Bibliography identifiers never cited in text: " + ", ".join(uncited) + ".",
            "Cite each relevant source at the supporting statement or remove unintended entries.",
        )

    for figure in as_list(manuscript.get("figures")):
        if not isinstance(figure, dict):
            continue
        caption_metric = normalized(figure.get("caption_metric"))
        axis_metric = normalized(figure.get("axis_metric"))
        if caption_metric and axis_metric and caption_metric != axis_metric:
            add_issue(
                issues,
                "FIGURE_CAPTION_MISMATCH",
                str(figure.get("figure_id", "Figure")),
                f"Caption metric '{figure.get('caption_metric', '')}' differs from axis metric '{figure.get('axis_metric', '')}'.",
                "Inspect the plotted quantity and correct the wrong content label; do not choose by appearance.",
            )

    for table in as_list(manuscript.get("tables")):
        if isinstance(table, dict) and table.get("best_marker_correct") is False:
            add_issue(
                issues,
                "TABLE_HIGHLIGHT_ERROR",
                str(table.get("table_id", "Table")),
                "The highlighted best result does not follow the declared metric direction.",
                "Recompute the best marker from the displayed values and metric direction.",
            )

    baseline = number(results.get("baseline"))
    current = number(results.get("current"))
    reported = number(results.get("reported_improvement"))
    improvement_unit = normalized(results.get("reported_improvement_unit"))
    if baseline is not None and current is not None and reported is not None and improvement_unit in {"percent", "%"}:
        points = (current - baseline) * 100
        relative = ((current - baseline) / baseline * 100) if baseline else float("inf")
        add_issue(
            issues,
            "PERCENTAGE_INTERPRETATION_RISK",
            "Results text",
            f"Reported {reported:g}% for {baseline:g}→{current:g}; this is {points:.2f} percentage points or {relative:.2f}% relative.",
            "State percentage points or relative change explicitly and use the matching calculation.",
        )

    for statement in as_list(manuscript.get("statistics")):
        if not isinstance(statement, dict) or not statement.get("claims_significance"):
            continue
        has_evidence = bool(statement.get("test") or statement.get("p_value") is not None or statement.get("confidence_interval"))
        if not has_evidence:
            add_issue(
                issues,
                "UNSUPPORTED_STATISTICAL_LANGUAGE",
                "Statistical claim",
                f"'{statement.get('statement', '')}' claims significance without a test, p-value, or confidence interval.",
                "Provide appropriate statistical evidence or remove the statistical-significance claim.",
            )

    claim_types = {normalized(item.get("claim_type")) for item in as_list(manuscript.get("claims")) if isinstance(item, dict)}
    needs_result_evidence = bool(claim_types & {"performance", "comparative", "generalization"})
    if needs_result_evidence and not (
        results.get("raw_artifacts_present") is True
        and any(reference.strip() for reference in results.get("raw_artifact_refs", []))
    ):
        add_issue(
            issues,
            "RESULT_VERIFICATION_REQUIRED",
            "Core result evidence",
            "The manuscript contains result claims but no raw/frozen result artifact with a traceable reference is declared.",
            "Use research-result-verification against frozen outputs; do not infer verification from manuscript agreement.",
        )

    for claim in as_list(manuscript.get("novelty")):
        if not isinstance(claim, dict):
            continue
        strength = normalized(claim.get("strength"))
        if strength in {"first", "novel", "state-of-the-art", "sota"} and not bool(claim.get("literature_verified")):
            add_issue(
                issues,
                "LITERATURE_VERIFICATION_REQUIRED",
                "Novelty/contribution claim",
                f"Strong novelty language lacks literature evidence: '{claim.get('statement', '')}'.",
                "Use research-literature-review before accepting or revising the novelty claim.",
            )

    return sorted(issues, key=lambda item: (SEVERITY_ORDER[item["severity"]], item["code"], item["location"]))


def claim_rows(manuscript: dict[str, Any], issues: list[dict[str, str]]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    issue_codes = {item["code"] for item in issues}
    for index, claim in enumerate(as_list(manuscript.get("claims")), start=1):
        if not isinstance(claim, dict):
            continue
        status = str(claim.get("status", "UNVERIFIED")).upper()
        if status not in CLAIM_STATUSES:
            status = "UNVERIFIED"
        if status in {"SUPPORTED", "PARTIALLY_SUPPORTED"} and (
            not normalized(claim.get("claim_text")) or not normalized(claim.get("observed_evidence"))
        ):
            status = "UNVERIFIED"
        claim_type = str(claim.get("claim_type", "BACKGROUND")).upper()
        if claim_type not in CLAIM_TYPES:
            claim_type = "BACKGROUND"
        downstream_skill = str(claim.get("downstream_skill", ""))
        if "INTERNAL_RESULT_MISMATCH" in issue_codes and claim_type in {"PERFORMANCE", "COMPARATIVE"}:
            status = "CONTRADICTED"
            downstream_skill = "research-result-verification"
        elif "RESULT_VERIFICATION_REQUIRED" in issue_codes and claim_type in {"PERFORMANCE", "COMPARATIVE", "GENERALIZATION"}:
            status = "UNVERIFIED"
            downstream_skill = "research-result-verification"
        if "CONCLUSION_OVERREACH" in issue_codes and claim_type == "GENERALIZATION":
            status = "PARTIALLY_SUPPORTED"
            downstream_skill = "research-experiment-design"
        rows.append(
            {
                "claim_id": str(claim.get("claim_id", f"C{index}")),
                "section": str(claim.get("section", "")),
                "location": str(claim.get("location", "")),
                "claim_text": str(claim.get("claim_text", "")),
                "claim_type": claim_type,
                "required_evidence": str(claim.get("required_evidence", "")),
                "observed_evidence": str(claim.get("observed_evidence", "")),
                "status": status,
                "downstream_skill": downstream_skill,
                "notes": str(claim.get("notes", "")),
            }
        )
    return rows


def write_claim_matrix(output: Path, rows: list[dict[str, str]]) -> None:
    fields = [
        "claim_id", "section", "location", "claim_text", "claim_type",
        "required_evidence", "observed_evidence", "status", "downstream_skill", "notes",
    ]
    with (output / "claim-evidence-matrix.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def issue_lines(issues: list[dict[str, str]]) -> list[str]:
    if not issues:
        return ["- No issue detected by the deterministic checks; manual manuscript review is still required."]
    return [
        f"- **{item['severity']} — `{item['code']}`** ({item['location']}): {item['evidence']}"
        + (f" Route: `{item['downstream_skill']}`." if item["downstream_skill"] else "")
        for item in issues
    ]


def write_paper_audit(manuscript: dict[str, Any], output: Path, rows: list[dict[str, str]], issues: list[dict[str, str]], status: str) -> None:
    paper = manuscript.get("paper", {}) if isinstance(manuscript.get("paper"), dict) else {}
    counts = Counter(item["severity"] for item in issues)
    sections = [
        "Methods", "Dataset", "Experiment Setup", "Results", "Figures", "Tables", "Statistics",
        "References", "Conclusion", "Limitations", "Reproducibility Flags", "Result Verification Flags",
    ]
    lines = [
        "# Paper audit", "", "## Audit Scope", "",
        f"- Paper title: {paper.get('title', '')}",
        f"- Document: {paper.get('document', '')}",
        f"- Version: {paper.get('version', '')}",
        f"- Audit date: {paper.get('date', '')}",
        f"- Scope: `{paper.get('audit_scope', '')}`",
        f"- Related artifact version: {paper.get('related_artifact_version', '')}",
        "", "## Executive Findings", "",
        f"- Deterministic status: `{status}`",
        f"- Severity counts: BLOCKER={counts['BLOCKER']}, MAJOR={counts['MAJOR']}, MINOR={counts['MINOR']}, OPTIONAL={counts['OPTIONAL']}",
        "- This status is not a paper score, acceptance prediction, or proof of submission readiness.",
        "", "## Claim Support", "",
        "| Claim | Section | Type | Status | Evidence | Downstream Skill |",
        "|---|---|---|---|---|---|",
    ]
    for row in rows:
        evidence = row["observed_evidence"].replace("|", "\\|")
        lines.append(f"| {row['claim_id']} | {row['section']} | {row['claim_type']} | `{row['status']}` | {evidence} | {row['downstream_skill']} |")
    for section in sections:
        scoped = [item for item in issues if item["category"] == section]
        lines.extend(["", f"## {section}", "", *issue_lines(scoped)])
    lines.extend(["", "## Prioritized Issues", "", *issue_lines(issues), ""])
    (output / "paper-audit.md").write_text("\n".join(lines), encoding="utf-8")


def write_blockers(output: Path, issues: list[dict[str, str]]) -> None:
    blockers = [item for item in issues if item["severity"] == "BLOCKER"]
    lines = [
        "# Blocking issues", "",
        "| Issue code | Location | Evidence | Required resolution | Downstream Skill |",
        "|---|---|---|---|---|",
    ]
    if blockers:
        for item in blockers:
            lines.append(
                f"| `{item['code']}` | {item['location']} | {item['evidence']} | {item['required_resolution']} | {item['downstream_skill']} |"
            )
    else:
        lines.append("| — | — | No BLOCKER detected by deterministic checks. | Complete manual review before any final claim. | — |")
    (output / "blocking-issues.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_consistency_map(manuscript: dict[str, Any], output: Path, issues: list[dict[str, str]]) -> None:
    chain = ("Research Question", "Contribution", "Method", "Experiment", "Result", "Conclusion")
    result_codes = {item["code"] for item in issues}
    results, seeds, scope = (manuscript.get(key, {}) for key in ("results", "seeds", "scope"))
    checked = {
        "Research Question": False,
        "Contribution": any(normalized(item.get("strength")) for item in manuscript.get("novelty", [])),
        "Method": False,
        "Experiment": all(seeds.get(key) is not None for key in ("methods", "table_runs")) or any(item.get("claims_significance") is True for item in manuscript.get("statistics", [])),
        "Result": all(number(results.get(key)) is not None for key in ("abstract_accuracy", "table_accuracy")) or any(normalized(item.get("claim_type")) in {"performance", "comparative", "generalization"} for item in manuscript.get("claims", [])),
        "Conclusion": scope.get("dataset_count") is not None and bool(normalized(scope.get("conclusion_scope"))),
    }
    node_issues = {
        "Contribution": {"LITERATURE_VERIFICATION_REQUIRED"},
        "Experiment": {"SEED_COUNT_MISMATCH", "UNSUPPORTED_STATISTICAL_LANGUAGE"},
        "Result": {"INTERNAL_RESULT_MISMATCH", "RESULT_VERIFICATION_REQUIRED", "PERCENTAGE_INTERPRETATION_RISK"},
        "Conclusion": {"CONCLUSION_OVERREACH"},
    }
    status = {node: "NEEDS_REVIEW" if result_codes & node_issues.get(node, set()) else ("INSPECTED" if checked[node] else "NOT_INSPECTED") for node in chain}
    lines = ["# Manuscript consistency map", "", " → ".join(chain), "", "| Node | Status |", "|---|---|"]
    lines.extend(f"| {node} | `{status[node]}` |" for node in chain)
    lines.extend(["", "INSPECTED refers only to deterministic checks on declared records; it does not certify manuscript or source review."])
    (output / "consistency-map.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_reference_consistency(manuscript: dict[str, Any], output: Path) -> None:
    citations = manuscript.get("citations", {}) if isinstance(manuscript.get("citations"), dict) else {}
    in_text = {str(item) for item in as_list(citations.get("in_text"))}
    bibliography = {str(item) for item in as_list(citations.get("bibliography"))}
    with (output / "reference-consistency.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=("reference_id", "in_text", "in_bibliography", "status"))
        writer.writeheader()
        for reference in sorted(in_text | bibliography):
            status = "MATCHED" if reference in in_text and reference in bibliography else ("MISSING_REFERENCE_ENTRY" if reference in in_text else "UNCITED_REFERENCE")
            writer.writerow({"reference_id": reference, "in_text": reference in in_text, "in_bibliography": reference in bibliography, "status": status})


def write_figure_table_audit(manuscript: dict[str, Any], output: Path) -> None:
    fields = ("artifact_id", "artifact_type", "caption_metric", "content_metric", "status", "issue_code")
    with (output / "figure-table-audit.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for figure in as_list(manuscript.get("figures")):
            if not isinstance(figure, dict):
                continue
            complete = bool(normalized(figure.get("caption_metric")) and normalized(figure.get("axis_metric")))
            mismatch = complete and normalized(figure.get("caption_metric")) != normalized(figure.get("axis_metric"))
            writer.writerow({
                "artifact_id": figure.get("figure_id", ""), "artifact_type": "FIGURE",
                "caption_metric": figure.get("caption_metric", ""), "content_metric": figure.get("axis_metric", ""),
                "status": "CONTENT_ERROR" if mismatch else ("CONSISTENT" if complete else "UNVERIFIED"),
                "issue_code": "FIGURE_CAPTION_MISMATCH" if mismatch else "",
            })
        for table in as_list(manuscript.get("tables")):
            if not isinstance(table, dict):
                continue
            mismatch = table.get("best_marker_correct") is False
            writer.writerow({
                "artifact_id": table.get("table_id", ""), "artifact_type": "TABLE",
                "caption_metric": "", "content_metric": table.get("metric_direction", ""),
                "status": "CONTENT_ERROR" if mismatch else ("CONSISTENT" if table.get("best_marker_correct") is True else "UNVERIFIED"),
                "issue_code": "TABLE_HIGHLIGHT_ERROR" if mismatch else "",
            })


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True, help="structured manuscript JSON")
    parser.add_argument("--output-dir", type=Path, required=True, help="directory for audit artifacts")
    args = parser.parse_args()

    try:
        manuscript = json.loads(args.input.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        print(json.dumps({"status": "INVALID_INPUT", "error": str(error)}))
        return 2
    if not isinstance(manuscript, dict):
        print(json.dumps({"status": "INVALID_INPUT", "error": "top-level JSON must be an object"}))
        return 2
    try:
        validate_input(manuscript)
    except ValueError as error:
        print(json.dumps({"status": "INVALID_INPUT", "error": str(error)}))
        return 2

    args.output_dir.mkdir(parents=True, exist_ok=True)
    issues = assess(manuscript)
    rows = claim_rows(manuscript, issues)
    missing = missing_evidence(manuscript)
    has_blocker = any(item["severity"] == "BLOCKER" for item in issues)
    status = "BLOCKED" if has_blocker else ("NEEDS_REVISION" if issues else ("INSUFFICIENT_EVIDENCE" if missing else "NO_BLOCKING_ISSUES_DETECTED"))
    write_claim_matrix(args.output_dir, rows)
    write_paper_audit(manuscript, args.output_dir, rows, issues, status)
    write_blockers(args.output_dir, issues)
    write_consistency_map(manuscript, args.output_dir, issues)
    write_reference_consistency(manuscript, args.output_dir)
    write_figure_table_audit(manuscript, args.output_dir)

    print(json.dumps({
        "status": status,
        "missing_evidence": missing,
        "issue_codes": [item["code"] for item in issues],
        "severity_counts": dict(Counter(item["severity"] for item in issues)),
        "downstream_skills": sorted({item["downstream_skill"] for item in issues if item["downstream_skill"]}),
        "output_dir": str(args.output_dir),
        "generated_files": sorted(path.name for path in args.output_dir.iterdir() if path.is_file()),
    }, indent=2))
    return 1 if issues or missing else 0


if __name__ == "__main__":
    sys.exit(main())
