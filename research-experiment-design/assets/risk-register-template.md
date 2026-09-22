# Risk register

| Risk code | Status | Evidence | Mitigation |
|---|---|---|---|
| UNFAIR_COMPARISON | NOT_DETECTED | | Hold dataset, split, preprocessing, and evaluation protocol constant. |
| CONFOUNDED_EXPERIMENT | NOT_DETECTED | | Change one claim-relevant factor at a time. |
| TEST_SET_TUNING | NOT_DETECTED | | Freeze test data until final evaluation. |
| SELECTION_BIAS_RISK | NOT_DETECTED | | Report all declared seeds using the predeclared aggregation. |
| SPLIT_MISMATCH_RISK | NOT_DETECTED | | Match split semantics to deployment. |
| COMPUTE_BUDGET_RISK | NOT_DETECTED | | Reduce scope or secure adequate resources before execution. |
