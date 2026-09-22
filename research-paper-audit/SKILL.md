---
name: research-paper-audit
description: Use when a final manuscript or research report needs an integration audit across claims, methods, datasets, experiments, numbers, figures, tables, citations, conclusions, and limitations before submission; not for single-paper reading, systematic literature review, experiment design, raw-output verification, reproducibility reconstruction, or prose polishing.
---

# Research Paper Audit

Audit whether a declared manuscript version forms a coherent, supportable, and checkable scientific narrative. This is a manuscript-level integration gate, not a substitute for the four upstream Research Skills.

## Portable execution

- **Portable:** The deterministic helper requires Python 3.10+ and only the Python standard library.
- Resolve `scripts/`, `references/`, and `assets/` from the directory containing this `SKILL.md`, not from the caller's current project directory.
- Before running the helper, set `SKILL_ROOT` to that resolved directory and invoke `python3 "$SKILL_ROOT/scripts/audit_paper.py" --input MANUSCRIPT.json --output-dir AUDIT_OUTPUT`.
- PDF reading, document handling, security review, code review, and prose editing are optional host capabilities. Use available equivalents without changing the audit boundary; otherwise report the unavailable companion check.

## Boundaries

- Use PDF/Documents to read, render, or edit a supplied document; use this skill to judge the integrated research narrative.
- Route novelty and literature-coverage questions to `research-literature-review`.
- Route fairness, split, metric-design, or missing-experiment questions to `research-experiment-design`.
- Route environment, input provenance, and rerun questions to `research-reproducibility`.
- Route raw-output-to-number/table/figure lineage to `research-result-verification`.
- Route code defects, security, ordinary review, and prose polishing to their existing workflows.

Do not rerun experiments, redo a systematic review, redesign the study, rewrite the manuscript, or mark raw-output agreement as verified from internal manuscript consistency alone. Missing evidence is `UNVERIFIED`, not false; use `CONTRADICTED` only when inspectable evidence directly conflicts.

## Workflow

1. Record document, title, version, audit date, related-artifact version, and scope: `FULL_MANUSCRIPT`, `METHODS_ONLY`, `EXPERIMENT_SECTION`, `RESULTS_ONLY`, or `FINAL_SUBMISSION`. Do not call an ambiguous version final.
2. Inventory material claims from the Abstract, Introduction, Contributions, Method, Results, and Conclusion in `claim-evidence-matrix.csv`.
3. Assign each claim one status: `SUPPORTED`, `PARTIALLY_SUPPORTED`, `UNSUPPORTED`, `UNVERIFIED`, or `CONTRADICTED`.
4. Trace Research Question → Contribution → Method → Experiment → Result → Conclusion. Check methods, dataset/split, setup, results, figures, tables, statistical language, citations, conclusion, and material limitations.
5. Classify findings as `BLOCKER`, `MAJOR`, `MINOR`, or `OPTIONAL`. Do not convert issue counts into a paper score, acceptance probability, award prediction, or venue forecast.
6. Keep integration findings here. When a finding requires external evidence or raw artifacts, record exactly one downstream Skill and stop at the handoff boundary.
7. Produce the required audit artifacts and state scope, missing evidence, and unperformed checks.

Before assigning claim types, issue codes, severity, or downstream routes, read [references/audit-protocol.md](references/audit-protocol.md). Use its canonical vocabulary; do not invent synonym codes when a listed code applies.

Protocol invariants:

- Claim types are `BACKGROUND`, `NOVELTY`, `METHOD`, `PERFORMANCE`, `COMPARATIVE`, `CAUSAL`, `GENERALIZATION`, or `LIMITATION`.
- Use `INTERNAL_RESULT_MISMATCH` for conflicting manuscript results, `CONCLUSION_OVERREACH` for evidence-scope expansion, `RESULT_VERIFICATION_REQUIRED` when a reported result lacks raw/frozen lineage, and `LITERATURE_VERIFICATION_REQUIRED` for an unverified strong novelty claim.
- `FINAL_SUBMISSION` is an audit-scope label, not proof of readiness and not an issue code.
- A downstream field contains one of the four Research Skills or is blank. **Codex only:** Codex is the final control gate, not a downstream Skill.
- Missing raw evidence for a reported number routes to `research-result-verification`; route to `research-reproducibility` only when reconstruction, environment/data provenance, commands, or rerun evidence is actually at issue.

For a deterministic first pass over a structured local record, use the portable command above.

The script does not parse arbitrary manuscripts or verify external sources. It generates audit artifacts without modifying the paper or research evidence.

Malformed declared containers return `INVALID_INPUT`. Missing claim/artifact evidence is reported as `INSUFFICIENT_EVIDENCE` or `UNVERIFIED`; deterministic consistency rows marked `INSPECTED` describe only checks actually run and do not certify the manuscript.

## Required outputs

- `paper-audit.md`
- `claim-evidence-matrix.csv`
- `blocking-issues.md`

Add `consistency-map.md`, `reference-consistency.csv`, and `figure-table-audit.csv` when those checks are in scope. Start from `assets/` when working manually.

## Execution model

- **Portable:** All three hosts may use the same evidence vocabulary, deterministic helper, required outputs, and handoff boundaries.
- **OpenCode only:** OpenCode + DeepSeek may perform high-throughput first-pass inventory and consistency extraction.
- **Codex only:** Codex owns final severity, core-claim judgment, cross-skill escalation, and the scientific audit gate.
- **Claude Code policy:** Claude Code is not used for this workflow without explicit user authorization. Authorization permits use of the portable core; it does not silently transfer the Codex-only final-gate responsibility.
