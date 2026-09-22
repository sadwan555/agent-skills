---
name: research-result-verification
description: Use when checking whether reported research numbers, metrics, tables, figures, or manuscript claims trace to and agree with raw experiment outputs; not for environment reconstruction, ordinary code review, or general dataset profiling.
---

# Research Result Verification

Trace each reported result through its evidence chain and assign an evidence status. Missing evidence is `UNVERIFIED`, never inferred as a match.

## Portable execution

- **Portable:** The deterministic helper requires Python 3.10+ and only the Python standard library.
- Resolve `scripts/`, `references/`, and `assets/` from the directory containing this `SKILL.md`, not from the caller's current project directory.
- Before running the helper, set `SKILL_ROOT` to that resolved directory and invoke `python3 "$SKILL_ROOT/scripts/verify_results.py" --project-root PROJECT --ledger INPUT_LEDGER --output-dir AUDIT_OUTPUT`.
- Data-quality, analysis-validation, testing, debugging, and code-review workflows are optional host capabilities. Use available equivalents without changing the frozen-evidence contract; otherwise report the unavailable companion check.

## Boundaries

- Use this skill for raw output → processed result → metric → aggregation → table/figure → claim reconciliation.
- Use reproducibility when the question is whether the project can be reconstructed and rerun.
- Use data-quality, analysis-validation, testing, debugging, or code-review workflows for their ordinary scopes.

Work read-only against source evidence and frozen artifacts. Never edit raw outputs, delete unfavorable seeds, change splits, substitute metrics, alter claims, forge citations, or regenerate a result merely to make the paper agree. Report the issue. Scientific changes require explicit user authorization and a new evidence lineage.

## Workflow

1. Freeze the scope: identify the exact claims, tables, figures, metrics, runs, and artifact versions under review.
2. Build `result-ledger.csv` using [references/ledger-schema.md](references/ledger-schema.md). One row represents one independently checkable claim-result link.
3. Trace source files and metric definitions. Verify population, split, denominator, units, preprocessing, and rounding when material.
4. Verify multiple runs, aggregation, uncertainty, run exclusions, and selection policy. Treat undisclosed best-seed or best-checkpoint selection as a selection/cherry-picking risk.
5. Reconcile canonical metrics, tables, figures, captions, and manuscript wording with frozen sources.
6. Produce `claim-result-map.md` and `verification-report.md`, preserving every gap and mismatch.

For deterministic JSON-backed comparisons, run:

```bash
python3 "$SKILL_ROOT/scripts/verify_results.py" \
  --project-root PROJECT \
  --ledger INPUT_LEDGER \
  --output-dir AUDIT_OUTPUT
```

The script writes separate audit artifacts and does not modify research outputs.

## Status Contract

Use only:

- `VERIFIED`: traceable source evidence matches.
- `MISMATCH`: traceable source evidence materially disagrees.
- `UNVERIFIED`: evidence is missing, ambiguous, malformed, or selection policy is undisclosed.
- `NOT_APPLICABLE`: the declared check genuinely does not apply.

Do not soften `MISMATCH` into a caveat or upgrade `UNVERIFIED` from contextual inference.

## Required Outputs

- `result-ledger.csv`: row-level source, observed value, status, evidence, and risk flag.
- `claim-result-map.md`: readable claim-to-source mapping.
- `verification-report.md`: scope, counts, blockers, mismatches, selection risks, and limitations.

Start from [assets/result-ledger-template.csv](assets/result-ledger-template.csv) when no ledger exists.
