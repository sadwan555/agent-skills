# Experiment design acceptance checklist

Accept a plan only when every applicable item is explicit.

## Scientific claim

- Research question identifies population, intervention or method, comparator, and outcome.
- Hypothesis is directional when justified and has a falsification condition.
- Claim target names the single factor the comparison is intended to isolate.
- Experiment class is labeled `PLANNED`, `EXPLORATORY`, or `CONFIRMATORY`.

## Data and split

- Dataset name, version, source, provenance, sample unit, and task definition are recorded.
- Preprocessing is fit on training data only.
- Duplicates, groups, subjects, users, time, and future information cannot cross boundaries improperly.
- Split semantics match the intended deployment claim. Recommender and forecasting evaluations normally preserve time.
- Test data is frozen and excluded from model selection and hyperparameter tuning.

## Comparison and metrics

- Baseline is credible and uses the same dataset, split, preprocessing, and evaluation protocol.
- Only the intended independent variable changes; unavoidable differences are documented.
- Primary metric is declared before execution and tied to the hypothesis.
- Secondary metrics cannot silently replace the primary outcome.
- Seeds, repetitions, aggregation, uncertainty, effect size, and any hypothesis test are predeclared.
- Report every declared seed; never select the best seed for the headline result.

## Ablation and resources

- Ablations remove one component at a time and retain the full model as a reference.
- Interactions are tested separately when scientifically necessary.
- Total run count, wall time, peak memory, storage, and hardware are feasible.
- Required experiments are separated from optional analyses.
- Stopping rules do not depend on obtaining a favorable outcome.

## Handoff

- Experiment matrix is complete enough to assign immutable run identifiers.
- Run schema captures configuration, environment, metrics, artifacts, and status.
- Risk register records evidence and mitigation for every blocking issue.
- Execution begins only after blocking risks are resolved and the plan is frozen.
