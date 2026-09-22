---
name: research-literature-review
description: Use when a defined research question requires systematic discovery, screening, citation verification, structured reading, evidence synthesis, or an evidence-based research-gap assessment across multiple scholarly sources. Do not use for summarizing one supplied paper, choosing a research topic, designing experiments, writing research code, verifying project results, rerunning experiments, or auditing a final manuscript.
---

# Research Literature Review

Build a traceable evidence base around a declared research question. Never invent citations, infer unread details, or present an exploratory search as exhaustive.

## Portable execution

- **Portable:** The deterministic helper requires Python 3.10+ and only the Python standard library.
- Resolve `scripts/`, `references/`, and `assets/` from the directory containing this `SKILL.md`, not from the caller's current project directory.
- Before running the helper, set `SKILL_ROOT` to that resolved directory and invoke `python3 "$SKILL_ROOT/scripts/audit_literature.py" --input REVIEW.json --output-dir OUTPUT`.
- Web search, PDF reading, document handling, data analysis, and spreadsheet features are optional host capabilities. Use available equivalents without changing the evidence contract; otherwise report the unavailable acquisition or handling step.

## Workflow

1. Record the topic, research question, target task, population or domain, method family, dataset or domain, publication window, language, and publication-type constraints. Mark open-ended work `EXPLORATORY`; do not imply exhaustive coverage.
2. Generate query variants covering exact terms, synonyms, historical terms, acronym/full-name forms, broader method families, and task-specific terminology.
3. Log every search source, date, exact query, filters, and result count when available in `search-log.md`. Search providers are interchangeable; do not make one service the workflow's logic.
4. Define inclusion and exclusion criteria before screening. Assign each record `INCLUDED`, `EXCLUDED`, `PENDING`, or `DUPLICATE` with a reason. Never exclude evidence because its outcome is unfavorable.
5. Verify title, authors, year, venue/publication status, and a stable identifier against primary scholarly or official metadata. Mark unresolved records `UNVERIFIED_METADATA`; do not guess missing fields.
6. Track source tier, publication versions, reading depth, and `SEMINAL`, `FOUNDATIONAL`, or `RECENT` role when justified. A search snippet is not a read paper, and an abstract cannot support full experimental details. Do not discard important older work to satisfy a recency quota.
7. Populate `literature-matrix.csv`. Label statements as `AUTHOR_CLAIM`, `DIRECT_EVIDENCE`, or `REVIEWER_INFERENCE`.
8. Synthesize by agreement, disagreement, method families, datasets, evaluation differences, and limitations. Use `CONSISTENT_EVIDENCE`, `MIXED_EVIDENCE`, or `INSUFFICIENT_EVIDENCE`.
9. Record evidence gaps with observed evidence, review scope, limitations, and confidence. Prefer “within the declared search...” over global novelty claims.

Read [references/review-protocol.md](references/review-protocol.md) for the source hierarchy, status contract, reading-depth rules, version handling, and matrix schema. Use the portable command above to audit a structured local record without querying external services.

## Required outputs

- `search-log.md`
- `literature-matrix.csv`
- `review-notes.md`
- `evidence-gaps.md`

Add `screening-log.csv`, `paper-notes/`, or `citation-check.md` only when useful. Do not automatically write a complete Related Work section.

## Boundaries

- Use PDF/Documents for focused reading or summarization of one supplied paper.
- Use research-experiment-design for deciding how to test the user's research question.
- Use research-reproducibility for reconstructing and rerunning existing work.
- Use research-result-verification for checking reported project results against raw outputs.
- Use data-analysis or spreadsheet workflows for dataset inspection.
- Final paper-wide consistency review belongs to a separate future audit workflow.
