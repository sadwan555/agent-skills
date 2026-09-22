# Manuscript integration audit protocol

## Scope contract

Record the exact document, title, version, date, audit scope, and related artifact version. Use only:

- `FULL_MANUSCRIPT`
- `METHODS_ONLY`
- `EXPERIMENT_SECTION`
- `RESULTS_ONLY`
- `FINAL_SUBMISSION`

An audit can cover a draft. `FINAL_SUBMISSION` describes the requested scope, not proof that the file is the final author-approved version.

## Claim inventory

Required columns:

`claim_id, section, location, claim_text, claim_type, required_evidence, observed_evidence, status, downstream_skill, notes`

Claim types include `BACKGROUND`, `NOVELTY`, `METHOD`, `PERFORMANCE`, `COMPARATIVE`, `CAUSAL`, `GENERALIZATION`, and `LIMITATION`.

Status meanings:

- `SUPPORTED`: the declared scope contains sufficient inspectable evidence.
- `PARTIALLY_SUPPORTED`: some material part is supported, but the wording exceeds or omits evidence.
- `UNSUPPORTED`: required support is absent even though the necessary scope was inspected.
- `UNVERIFIED`: required evidence was unavailable, ambiguous, external, or outside the audit scope.
- `CONTRADICTED`: inspectable evidence directly conflicts with the claim.

`UNVERIFIED` is not false. Plausibility is not support.

## Section checks

### Abstract and contributions

Match problem, method, dataset, evaluation, main result, and conclusion to the body. Flag unsupported strong language such as first, novel, state of the art, significantly improves, robust, or generalizable. Novelty that depends on literature coverage is `LITERATURE_VERIFICATION_REQUIRED`.

### Related work and references

Check placement, internal citation-to-bibliography consistency, duplicate entries, version confusion, and obvious author/year/venue mismatch. Do not claim citation authenticity from the manuscript alone. Route authenticity, coverage, and novelty to `research-literature-review`.

### Method

Check inputs, outputs, architecture, training procedure, loss, parameters, preprocessing, inference/evaluation logic, symbols, acronyms, terminology, equations, and algorithms. Identify the exact location and missing information; do not silently complete it from common practice.

### Dataset, split, and setup

Check dataset identity/version/source, sample counts, distributions when material, exclusions, train/validation/test split, preprocessing, augmentation, hardware, software, framework, optimizer, learning rate, batch size, epochs, seeds, early stopping, checkpoint selection, and baseline settings. Use `MISSING_EXPERIMENT_DETAIL` or a specific mismatch code. Route scientific design questions to `research-experiment-design` and provenance/rerun questions to `research-reproducibility`.

### Results, figures, tables, and statistics

Reconcile numbers across abstract, body, tables, figures, captions, and conclusion. Distinguish percentage points from relative percent. Check mean/std, seed counts, best-run wording, numbering, units, axes, legends, panel labels, error bars, decimal precision, metric direction, footnotes, and best-result highlighting.

Internal agreement is not raw-output verification. Use `RESULT_VERIFICATION_REQUIRED` and route to `research-result-verification` when the evidence chain is needed.

Treat an unsubstantiated “statistically significant” as `UNSUPPORTED_STATISTICAL_LANGUAGE`. For softer words such as substantially or clearly, judge effect-size support without mechanical keyword scoring.

### Conclusion and limitations

Map introduction promises to tested methods/results and then to conclusion claims. Do not extend one dataset, model, setting, population, or correlation into broad generalization or causation. Flag an omitted limitation only when it is material to the claims and evidence.

## Consistency graph and issue codes

Trace:

`Research Question → Contribution → Method → Experiment → Result → Conclusion`

Common codes:

- `INTRODUCTION_PROMISE_NOT_TESTED`
- `METHOD_NOT_EVALUATED`
- `RESULT_WITHOUT_METHOD`
- `CONCLUSION_OVERREACH`
- `INTERNAL_RESULT_MISMATCH`
- `METRIC_MISMATCH`
- `DATASET_COUNT_MISMATCH`
- `SEED_COUNT_MISMATCH`
- `FIGURE_TEXT_MISMATCH`
- `FIGURE_CAPTION_MISMATCH`
- `TABLE_TEXT_MISMATCH`
- `TABLE_HIGHLIGHT_ERROR`
- `MISSING_EXPERIMENT_DETAIL`
- `PERCENTAGE_INTERPRETATION_RISK`
- `UNSUPPORTED_STATISTICAL_LANGUAGE`
- `MISSING_MATERIAL_LIMITATION`
- `MISSING_REFERENCE_ENTRY`
- `UNCITED_REFERENCE`
- `RESULT_VERIFICATION_REQUIRED`
- `LITERATURE_VERIFICATION_REQUIRED`

Label figure/table issues as `CONTENT_ERROR` when scientific meaning is wrong and `PRESENTATION_ERROR` when meaning is intact but readability/formatting is deficient.

## Severity

- `BLOCKER`: may invalidate a central conclusion or leave a serious factual/submission error, including irreconcilable core numbers, likely leakage affecting the main result, direct conclusion contradiction, or absent evidence for a central claimed result.
- `MAJOR`: materially harms scientific credibility or comprehension, including insufficient method detail, unfair comparison, unsupported important claim, missing statistical support, or major figure/table inconsistency.
- `MINOR`: does not change the central conclusion, such as local terminology, caption, formatting, small citation, or rounding issues.
- `OPTIONAL`: clearly separated enhancement, aesthetic improvement, optional appendix, or nonessential additional experiment.

Severity is impact-based, not a count. Do not infer score, acceptance probability, award probability, or venue rank.

## Cross-skill routing

| Evidence need | Downstream Skill |
|---|---|
| Novelty, citation authenticity, or literature coverage | `research-literature-review` |
| Fairness, split/metric design, missing control, or experiment adequacy | `research-experiment-design` |
| Environment, data provenance, commands, or rerun reconstruction | `research-reproducibility` |
| Raw output, aggregation, number, table, or figure lineage | `research-result-verification` |

The paper audit discovers, classifies, and routes. Do not automatically run all downstream Skills. Even a full final audit proceeds in explicit stages.
