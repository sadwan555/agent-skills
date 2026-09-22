---
name: research-experiment-design
description: Use when a research question must be converted into a controlled, falsifiable experiment plan before implementation or execution, especially for ML, deep learning, recommender systems, ablations, seed plans, statistical evaluation, and compute budgeting. Do not use for writing project code, fixing training bugs, running experiments, literature review, verifying reported numbers, clean-room reproduction, or final paper audit.
---

# Research Experiment Design

Turn a research question into a pre-execution protocol. Preserve the distinction between `PLANNED`, `EXPLORATORY`, and `CONFIRMATORY`; never present an unrun plan as evidence.

## Portable execution

- **Portable:** The deterministic helper requires Python 3.10+ and only the Python standard library.
- Resolve `scripts/`, `references/`, and `assets/` from the directory containing this `SKILL.md`, not from the caller's current project directory.
- Before running the helper, set `SKILL_ROOT` to that resolved directory and invoke `python3 "$SKILL_ROOT/scripts/design_experiment.py" --spec SPEC.json --output-dir OUTPUT_DIR`.
- Capability routes such as brainstorming, implementation planning, or data analysis are optional host integrations. If a host does not provide one, preserve the boundary and state that the companion capability is unavailable.

## Workflow

1. State the research question, hypothesis, falsification condition, and exact claim target.
2. Lock dataset identity, provenance, task definition, and sample unit.
3. Choose a split that matches deployment semantics. For temporal, recommender, grouped, or continual-learning tasks, explicitly protect ordering and group boundaries.
4. Select a defensible baseline. Hold dataset, split, preprocessing, evaluation protocol, and other non-target factors constant wherever scientifically possible.
5. Declare independent, dependent, and controlled variables. If several factors change, separate them or flag a confound.
6. Define primary and secondary metrics with rationales. Do not tune on the test set.
7. Predeclare seeds, run count, aggregation policy, statistical summaries, uncertainty, and effect size.
8. Build the experiment matrix. Add a one-factor-at-a-time ablation matrix only when the proposed method has multiple meaningful components.
9. Estimate memory, time, storage, and total runs. Separate required from optional experiments and define a stopping rule that is independent of favorable results.
10. Produce an execution-ready plan without implementing or running it.

## Required outputs

- `experiment-plan.md`
- `experiment-matrix.csv`
- `risk-register.md`
- `run-schema.json`
- `ablation-matrix.csv` only when meaningful

Use the portable command above for deterministic scaffolding and risk checks. Read [references/design-checklist.md](references/design-checklist.md) before accepting the plan. Use files in `assets/` as portable examples, not as evidence that an experiment ran.

The helper validates the declared structure before writing outputs. Malformed sections, non-finite or negative budgets, duplicate seeds, and inconsistent run counts return structured `INVALID_SPEC` JSON with exit code `2`; no partial plan is emitted.

Blocking risks include `UNFAIR_COMPARISON`, `CONFOUNDED_EXPERIMENT`, `TEST_SET_TUNING`, `SELECTION_BIAS_RISK`, `SPLIT_MISMATCH_RISK`, and `COMPUTE_BUDGET_RISK`. A plan with a blocking risk is `NEEDS_REVISION`, not execution-ready.

## Boundaries

- Use brainstorming for broad product or problem exploration.
- Use writing-plans for implementation plans that build software.
- Use data-analysis capabilities to inspect existing datasets or results.
- Use research-reproducibility to reconstruct and rerun an existing result.
- Use research-result-verification to reconcile reported metrics, tables, figures, or claims with raw outputs.
- Route coding and debugging to the normal development workflow.
