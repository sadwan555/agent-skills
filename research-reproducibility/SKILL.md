---
name: research-reproducibility
description: Use when auditing whether a research result can be reconstructed and rerun from original inputs, environment, source, configuration, seeds, commands, and artifact lineage; not for ordinary bugs, PR review, or paper-number reconciliation.
---

# Research Reproducibility

Determine the highest provisional reproducibility level supported by inspectable evidence. Treat technical reproducibility separately from research or paper quality. The helper performs structural evidence checks only; it never awards Level 4, which requires a separately reviewed independent reproduction record.

## Portable execution

- **Portable:** The deterministic helper requires Python 3.10+ and only the Python standard library.
- Resolve `scripts/`, `references/`, and `assets/` from the directory containing this `SKILL.md`, not from the caller's current project directory.
- Before running the helper, set `SKILL_ROOT` to that resolved directory and invoke `python3 "$SKILL_ROOT/scripts/audit_reproducibility.py" --project-root PROJECT`.
- Debugging, testing, code review, and data-quality workflows are optional host capabilities. Use available equivalents without changing the read-only evidence boundary; otherwise report the unavailable companion check.

## Boundaries

- Use this skill for reconstruction and rerun questions.
- Use result verification when the task is to reconcile reported numbers, tables, figures, or claims with experimental outputs.
- Use debugging, testing, code review, or data-quality workflows for their ordinary engineering and dataset scopes.
- Work read-only by default. Ask for explicit authorization before downloads, environment creation, retraining, clean-room execution, expensive computation, or destructive cleanup.

Never edit raw data, formal outputs, seeds, splits, metrics, or claims to make an audit pass. Report gaps and mismatches; scientific changes require separate authorization.

## Workflow

1. Define the exact target: exploratory result, formal run, table, figure, or reported claim. State exclusions.
2. Inspect source and environment declarations. Prefer `pyproject.toml`, `uv.lock`, and an explicit Python version when present. Record relevant hardware and accelerator requirements.
3. Trace data from immutable raw inputs through interim and processed forms. Require source, version, retrieval date, checksum, and license when relevant. Processed data cannot be an unexplained starting point.
4. Trace configuration, preprocessing, model parameters, seeds, split logic, commands, run IDs, environment snapshots, and artifacts.
5. Compare recorded reruns and artifact lineage without modifying them. Use [references/audit-checklist.md](references/audit-checklist.md) for evidence criteria.
6. Assign one level and list the evidence, blockers, and actions needed for the next level.

For a deterministic first pass, run:

```bash
python3 "$SKILL_ROOT/scripts/audit_reproducibility.py" --project-root PROJECT
```

Use `--json-out` and `--markdown-out` to save separate audit artifacts. The script does not execute the research project. Its `PASS` checks mean that declared files and metadata passed structural checks; they do not authenticate that an experiment ran, dependencies resolved, or figures came from the recorded run. Treat `UNVERIFIED` and `FAIL` as evidence gaps requiring review.

## Levels

- **Level 0 — INSUFFICIENT:** essential source, inputs, configuration, or execution evidence is absent.
- **Level 1 — DOCUMENTED:** the target and some execution details are documented, but reconstruction is incomplete.
- **Level 2 — RECONSTRUCTABLE:** environment, inputs, configuration, seeds, and commands are sufficiently specified.
- **Level 3 — RERUNNABLE:** recorded reruns and artifact lineage support repeatability in the controlled setup.
- **Level 4 — INDEPENDENTLY_REPRODUCED:** an explicitly authorized, independent clean environment reproduced the scoped target against declared acceptance criteria.

Passing code, tests, or two same-environment runs does not establish Level 4.

## Output

Produce `REPRODUCIBILITY.md` from [assets/REPRODUCIBILITY-template.md](assets/REPRODUCIBILITY-template.md). Add `data-manifest.json`, `artifact-manifest.json`, or `reproduction-report.md` only when evidence and scope justify them. Mark missing evidence plainly; do not infer success.
