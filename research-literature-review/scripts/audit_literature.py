#!/usr/bin/env python3
"""Audit a structured, source-agnostic literature-review record."""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


RISK_CODES = (
    "UNVERIFIED_METADATA",
    "INSUFFICIENT_EVIDENCE",
    "DUPLICATE_VERSION",
    "SCREENING_BIAS_RISK",
    "UNSUPPORTED_NOVELTY_CLAIM",
    "SECONDARY_SOURCE_ONLY",
)

MATRIX_FIELDS = (
    "paper_id", "work_id", "title", "authors", "year", "venue", "doi", "url",
    "publication_status", "stable_identifier", "metadata_status", "source_tier", "literature_role",
    "research_question", "proposed_contribution", "task", "dataset", "sample_or_scale", "method", "baseline",
    "metrics", "main_results", "ablations", "limitations", "relevance", "evidence_access",
    "screening_status", "screening_reason", "version_relationship", "notes",
)

READING_DEPTHS = {"METADATA_ONLY", "ABSTRACT_ONLY", "PARTIAL_TEXT", "FULL_TEXT"}
EVIDENCE_TYPES = {"AUTHOR_CLAIM", "DIRECT_EVIDENCE", "REVIEWER_INFERENCE"}
SYNTHESIS_STATUSES = {"CONSISTENT_EVIDENCE", "MIXED_EVIDENCE", "INSUFFICIENT_EVIDENCE"}


def items(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def text(value: Any) -> str:
    if isinstance(value, list):
        return "; ".join(str(item) for item in value)
    if value is None:
        return ""
    return str(value)


def markdown(value: Any) -> str:
    return text(value).replace("|", "\\|").replace("\n", " ").strip()


def add_risk(risks: list[dict[str, str]], code: str, paper_id: str, evidence: str) -> None:
    key = (code, paper_id, evidence)
    if key not in {(risk["code"], risk["paper_id"], risk["evidence"]) for risk in risks}:
        risks.append({"code": code, "paper_id": paper_id, "evidence": evidence})


def metadata_is_verified(paper: dict[str, Any]) -> bool:
    required = ("title", "authors", "year", "venue", "publication_status", "stable_identifier")
    return paper.get("metadata_verification") == "VERIFIED" and all(paper.get(field) for field in required)


def validate_input(specification: dict[str, Any]) -> None:
    """Reject malformed declared containers instead of silently dropping evidence."""
    def object_field(record: dict[str, Any], field: str, path: str) -> dict[str, Any]:
        if field in record and not isinstance(record[field], dict):
            raise ValueError(f"{path} must be an object")
        return record.get(field, {})

    def list_field(record: dict[str, Any], field: str, path: str, *, objects: bool = False) -> list[Any]:
        if field in record and not isinstance(record[field], list):
            raise ValueError(f"{path} must be an array")
        values = record.get(field, [])
        if objects:
            for index, value in enumerate(values):
                if not isinstance(value, dict):
                    raise ValueError(f"{path}[{index}] must be an object")
        return values

    review = object_field(specification, "review", "review")
    scope = object_field(review, "scope", "review.scope")
    for field in ("inclusion_criteria", "exclusion_criteria"):
        list_field(review, field, f"review.{field}")
    for field in ("languages", "publication_types"):
        list_field(scope, field, f"review.scope.{field}")
    for field in ("papers", "query_variants", "searches", "synthesis", "gaps", "novelty_claims"):
        list_field(specification, field, field, objects=True)
    for index, paper in enumerate(specification.get("papers", [])):
        list_field(paper, "extracted_sections", f"papers[{index}].extracted_sections")
        statements = list_field(paper, "evidence_statements", f"papers[{index}].evidence_statements", objects=True)
        for statement_index, statement in enumerate(statements):
            if "statement" in statement and not isinstance(statement["statement"], str):
                raise ValueError(f"papers[{index}].evidence_statements[{statement_index}].statement must be a string")


def assess(specification: dict[str, Any]) -> tuple[list[dict[str, str]], dict[str, str]]:
    risks: list[dict[str, str]] = []
    papers = [paper for paper in items(specification.get("papers")) if isinstance(paper, dict)]
    derived_screening: dict[str, str] = {}
    if not any(text(paper.get("screening_status")).upper() == "INCLUDED" for paper in papers):
        add_risk(risks, "INSUFFICIENT_EVIDENCE", "REVIEW", "No included paper evidence is recorded; empty or pending screening is not synthesis readiness.")

    for paper in papers:
        paper_id = text(paper.get("paper_id")) or "UNKNOWN"
        if not metadata_is_verified(paper):
            add_risk(
                risks,
                "UNVERIFIED_METADATA",
                paper_id,
                "Title, authors, year, venue/publication status, and stable identifier were not all verified against authoritative metadata.",
            )

        access = text(paper.get("evidence_access")).upper()
        requested = text(paper.get("requested_detail_level")).upper()
        sections = {text(section).lower() for section in items(paper.get("extracted_sections"))}
        full_detail_sections = {"method", "experiment setup", "results", "limitations"}
        if access in {"METADATA_ONLY", "ABSTRACT_ONLY"} and (
            requested == "FULL_EXPERIMENT" or bool(sections & full_detail_sections)
        ):
            add_risk(
                risks,
                "INSUFFICIENT_EVIDENCE",
                paper_id,
                f"Reading depth {access or 'UNDECLARED'} cannot support the requested full experimental detail.",
            )

        screening_status = text(paper.get("screening_status")).upper()
        if screening_status == "INCLUDED" and (
            access not in READING_DEPTHS - {"METADATA_ONLY"}
            or not any(text(statement.get("statement")).strip() for statement in items(paper.get("evidence_statements")) if isinstance(statement, dict))
        ):
            add_risk(risks, "INSUFFICIENT_EVIDENCE", paper_id, "Included evidence requires a declared reading depth beyond metadata and at least one recorded evidence statement.")
        reason = text(paper.get("screening_reason")).lower()
        exclusion_basis = text(paper.get("exclusion_basis")).upper()
        outcome_phrases = ("support our hypothesis", "unfavorable result", "negative result", "null result")
        if screening_status == "EXCLUDED" and (
            exclusion_basis == "OUTCOME_DIRECTION" or any(phrase in reason for phrase in outcome_phrases)
        ):
            add_risk(
                risks,
                "SCREENING_BIAS_RISK",
                paper_id,
                "The screening decision depends on result direction rather than predeclared relevance or evidence criteria.",
            )

        if (
            screening_status == "INCLUDED"
            and text(paper.get("source_tier")).upper() == "SECONDARY_DISCUSSION"
            and not paper.get("primary_evidence")
        ):
            add_risk(
                risks,
                "SECONDARY_SOURCE_ONLY",
                paper_id,
                "A secondary discussion was included as formal evidence without a traceable primary scholarly source.",
            )

    work_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for paper in papers:
        work_id = text(paper.get("work_id")).strip()
        if work_id:
            work_groups[work_id].append(paper)
    for work_id, versions in work_groups.items():
        if len(versions) < 2:
            continue
        included = [paper for paper in versions if text(paper.get("screening_status")).upper() == "INCLUDED"]
        if len(included) > 1:
            add_risk(
                risks,
                "DUPLICATE_VERSION",
                ",".join(text(paper.get("paper_id")) for paper in versions),
                f"Multiple versions of work '{work_id}' are counted as independent included evidence.",
            )
            canonical = max(versions, key=publication_priority)
            for paper in versions:
                if paper is not canonical:
                    derived_screening[text(paper.get("paper_id"))] = "DUPLICATE"

    for index, novelty in enumerate(items(specification.get("novelty_claims")), start=1):
        if not isinstance(novelty, dict):
            continue
        claim = text(novelty.get("claim"))
        global_language = re.search(r"\b(first[- ]?ever|first study|no prior|never studied|worldwide|globally first)\b", claim, re.I)
        if global_language and not bool(novelty.get("systematic_coverage")):
            add_risk(
                risks,
                "UNSUPPORTED_NOVELTY_CLAIM",
                f"NOVELTY-{index}",
                f"Global novelty language is unsupported by the declared coverage: {claim}",
            )

    return risks, derived_screening


def publication_priority(paper: dict[str, Any]) -> tuple[int, int]:
    status = text(paper.get("publication_status")).lower()
    rank = 3 if "journal" in status else 2 if "conference" in status else 1 if "preprint" in status else 0
    try:
        year = int(paper.get("year", 0))
    except (TypeError, ValueError):
        year = 0
    return rank, year


def write_search_log(specification: dict[str, Any], output: Path) -> None:
    review = specification.get("review", {}) if isinstance(specification.get("review"), dict) else {}
    scope = review.get("scope", {}) if isinstance(review.get("scope"), dict) else {}
    mode = text(review.get("review_mode")).upper() or "EXPLORATORY"
    lines = [
        "# Search log",
        "",
        f"- Research topic: {review.get('topic', '')}",
        f"- Research question: {review.get('research_question', '')}",
        f"- Review mode: `{mode}`",
        f"- Target task: {scope.get('target_task', '')}",
        f"- Population/domain: {scope.get('population_or_domain', '')}",
        f"- Method family: {scope.get('method_family', '')}",
        f"- Dataset/domain: {scope.get('dataset_or_domain', '')}",
        f"- Publication window: {scope.get('publication_window', '')}",
        f"- Language constraints: {text(scope.get('languages'))}",
        f"- Publication types: {text(scope.get('publication_types'))}",
        "",
    ]
    if mode == "EXPLORATORY":
        lines.extend(["> EXPLORATORY search: this log does not establish exhaustive coverage.", ""])
    lines.extend(["## Query variants", "", "| Category | Query |", "|---|---|"])
    for variant in items(specification.get("query_variants")):
        if isinstance(variant, dict):
            lines.append(f"| {markdown(variant.get('category'))} | {markdown(variant.get('query'))} |")
    lines.extend(
        [
            "",
            "## Executed searches",
            "",
            "| Source/database | Date | Exact query | Filters | Results count |",
            "|---|---|---|---|---:|",
        ]
    )
    for search in items(specification.get("searches")):
        if isinstance(search, dict):
            lines.append(
                "| {source} | {date} | {query} | {filters} | {count} |".format(
                    source=markdown(search.get("source")),
                    date=markdown(search.get("date")),
                    query=markdown(search.get("query")),
                    filters=markdown(search.get("filters")),
                    count=markdown(search.get("results_count")),
                )
            )
    (output / "search-log.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_matrix(specification: dict[str, Any], output: Path, derived_screening: dict[str, str]) -> None:
    with (output / "literature-matrix.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=MATRIX_FIELDS)
        writer.writeheader()
        for paper in items(specification.get("papers")):
            if not isinstance(paper, dict):
                continue
            paper_id = text(paper.get("paper_id"))
            row = {field: text(paper.get(field)) for field in MATRIX_FIELDS}
            row["authors"] = text(paper.get("authors"))
            row["metadata_status"] = "VERIFIED" if metadata_is_verified(paper) else "UNVERIFIED_METADATA"
            row["evidence_access"] = text(paper.get("evidence_access")).upper() or "METADATA_ONLY"
            row["screening_status"] = derived_screening.get(paper_id, text(paper.get("screening_status")).upper() or "PENDING")
            writer.writerow(row)


def write_review_notes(specification: dict[str, Any], output: Path, risks: list[dict[str, str]], derived_screening: dict[str, str]) -> None:
    review = specification.get("review", {}) if isinstance(specification.get("review"), dict) else {}
    papers = [paper for paper in items(specification.get("papers")) if isinstance(paper, dict)]
    statuses = Counter(
        derived_screening.get(text(paper.get("paper_id")), text(paper.get("screening_status")).upper() or "PENDING")
        for paper in papers
    )
    lines = [
        "# Review notes",
        "",
        "## Screening protocol",
        "",
        "### Inclusion criteria",
        "",
    ]
    lines.extend(f"- {criterion}" for criterion in items(review.get("inclusion_criteria")))
    lines.extend(["", "### Exclusion criteria", ""])
    lines.extend(f"- {criterion}" for criterion in items(review.get("exclusion_criteria")))
    lines.extend(["", "### Screening counts", ""])
    lines.extend(f"- {status}: {count}" for status, count in sorted(statuses.items()))
    lines.extend(["", "## Structured paper reading", ""])

    for paper in papers:
        paper_id = text(paper.get("paper_id")) or "UNKNOWN"
        access = text(paper.get("evidence_access")).upper() or "METADATA_ONLY"
        if access not in READING_DEPTHS:
            access = "METADATA_ONLY"
        lines.extend(
            [
                f"### {paper_id} — {paper.get('title', '')}",
                "",
                f"- Source tier: `{paper.get('source_tier', '')}`",
                f"- Reading depth: `{access}`",
                f"- Inspected sections: {text(paper.get('extracted_sections')) or 'not recorded'}",
                f"- Research problem: {paper.get('research_question', '')}",
                f"- Proposed contribution: {paper.get('proposed_contribution', '')}",
                f"- Method: {paper.get('method', '')}",
                f"- Dataset/scale: {paper.get('dataset', '')}; {paper.get('sample_or_scale', '')}",
                f"- Baselines: {paper.get('baseline', '')}",
                f"- Metrics: {paper.get('metrics', '')}",
                f"- Main results: {paper.get('main_results', '')}",
                f"- Ablations: {paper.get('ablations', '')}",
                f"- Limitations: {paper.get('limitations', '')}",
                f"- Relevance: {paper.get('relevance', '')}",
                "- Evidence statements:",
            ]
        )
        statements = [statement for statement in items(paper.get("evidence_statements")) if isinstance(statement, dict)]
        if not statements:
            lines.append("  - None recorded.")
        for statement in statements:
            kind = text(statement.get("type")).upper()
            kind = kind if kind in EVIDENCE_TYPES else "REVIEWER_INFERENCE"
            lines.append(f"  - `{kind}`: {statement.get('statement', '')}")
        lines.append("")

    lines.extend(["## Evidence synthesis", ""])
    syntheses = [item for item in items(specification.get("synthesis")) if isinstance(item, dict)]
    if not syntheses:
        lines.append("- `INSUFFICIENT_EVIDENCE`: no synthesis unit was recorded.")
    for synthesis in syntheses:
        status = text(synthesis.get("status")).upper()
        status = status if status in SYNTHESIS_STATUSES else "INSUFFICIENT_EVIDENCE"
        lines.extend(
            [
                f"### {synthesis.get('theme', 'Untitled theme')} — `{status}`",
                "",
                f"- Agreement: {synthesis.get('agreement', '')}",
                f"- Disagreement: {synthesis.get('disagreement', '')}",
                f"- Method families: {synthesis.get('method_families', '')}",
                f"- Dataset differences: {synthesis.get('dataset_differences', '')}",
                f"- Evaluation differences: {synthesis.get('evaluation_differences', '')}",
                f"- Limitations: {synthesis.get('limitations', '')}",
                "",
            ]
        )
    lines.extend(["## Blocking evidence risks", ""])
    if risks:
        lines.extend(f"- `{risk['code']}` ({risk['paper_id']}): {risk['evidence']}" for risk in risks)
    else:
        lines.append("- None detected by the deterministic audit. Human source review is still required.")
    (output / "review-notes.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_evidence_gaps(specification: dict[str, Any], output: Path, risks: list[dict[str, str]]) -> None:
    lines = [
        "# Evidence gaps",
        "",
        "> Gap statements are bounded to the declared search and included evidence. They are not global novelty claims.",
        "",
    ]
    gaps = [gap for gap in items(specification.get("gaps")) if isinstance(gap, dict)]
    if not gaps:
        lines.append("No evidence gap is supportable from the current record.")
    for index, gap in enumerate(gaps, start=1):
        lines.extend(
            [
                f"## Gap {index}",
                "",
                f"- Observed evidence: {gap.get('observed_evidence', '')}",
                f"- Scope: {gap.get('scope', '')}",
                f"- Limitations: {gap.get('limitations', '')}",
                f"- Confidence: {gap.get('confidence', '')}",
                "",
            ]
        )
    novelty_risks = [risk for risk in risks if risk["code"] == "UNSUPPORTED_NOVELTY_CLAIM"]
    if novelty_risks:
        lines.extend(["## Unsupported novelty claims", ""])
        lines.extend(f"- `UNSUPPORTED_NOVELTY_CLAIM`: {risk['evidence']}" for risk in novelty_risks)
    (output / "evidence-gaps.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_citation_check(specification: dict[str, Any], output: Path, risks: list[dict[str, str]]) -> None:
    lines = [
        "# Citation and source check",
        "",
        "| Paper | Metadata | Source tier | Stable identifier | Reading depth |",
        "|---|---|---|---|---|",
    ]
    for paper in items(specification.get("papers")):
        if not isinstance(paper, dict):
            continue
        status = "VERIFIED" if metadata_is_verified(paper) else "UNVERIFIED_METADATA"
        lines.append(
            f"| {markdown(paper.get('paper_id'))} | {status} | {markdown(paper.get('source_tier'))} | "
            f"{markdown(paper.get('stable_identifier'))} | {markdown(paper.get('evidence_access'))} |"
        )
    lines.extend(["", "## Risks", ""])
    if risks:
        lines.extend(f"- `{risk['code']}` ({risk['paper_id']}): {risk['evidence']}" for risk in risks)
    else:
        lines.append("- None detected by the deterministic audit.")
    (output / "citation-check.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True, help="structured literature-review JSON")
    parser.add_argument("--output-dir", type=Path, required=True, help="directory for generated evidence artifacts")
    args = parser.parse_args()

    try:
        specification = json.loads(args.input.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        print(json.dumps({"status": "INVALID_INPUT", "error": str(error)}))
        return 2
    if not isinstance(specification, dict):
        print(json.dumps({"status": "INVALID_INPUT", "error": "top-level JSON must be an object"}))
        return 2
    try:
        validate_input(specification)
    except ValueError as error:
        print(json.dumps({"status": "INVALID_INPUT", "error": str(error)}))
        return 2

    args.output_dir.mkdir(parents=True, exist_ok=True)
    risks, derived_screening = assess(specification)
    write_search_log(specification, args.output_dir)
    write_matrix(specification, args.output_dir, derived_screening)
    write_review_notes(specification, args.output_dir, risks, derived_screening)
    write_evidence_gaps(specification, args.output_dir, risks)
    write_citation_check(specification, args.output_dir, risks)

    blocking = sorted({risk["code"] for risk in risks}, key=RISK_CODES.index)
    status = "NEEDS_REVISION" if blocking else "READY_FOR_SYNTHESIS"
    print(
        json.dumps(
            {
                "status": status,
                "blocking_risks": blocking,
                "paper_count": len(items(specification.get("papers"))),
                "output_dir": str(args.output_dir),
                "generated_files": sorted(path.name for path in args.output_dir.iterdir() if path.is_file()),
            },
            indent=2,
        )
    )
    return 1 if blocking else 0


if __name__ == "__main__":
    sys.exit(main())
