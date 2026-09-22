# Result Ledger Schema

Each CSV row is one independently verifiable link between a reported result and a frozen source.

| Column | Required | Meaning |
|---|---:|---|
| `claim_id` | yes | Stable local identifier for the claim-result link. |
| `artifact` | yes | Table, figure, caption, manuscript section, or named result. |
| `source_path` | yes for verification | Project-relative frozen source file. Blank or missing paths produce `UNVERIFIED`. |
| `json_path` | yes for JSON sources | Dot-separated field path such as `metrics.accuracy`. |
| `reported_value` | yes unless not applicable | Literal number, string, boolean, list, or object. JSON literals are supported. |
| `aggregation` | yes | `single`, `mean`, `median`, `best`, `max`, `min`, or a documented method. |
| `run_count` | yes | Number of runs considered for the reported result. |
| `selection_policy` | required for selection | Predeclared rule for choosing runs/checkpoints. |

The verifier adds:

- `observed_value`
- `status`
- `evidence`
- `risk_flag`

## Interpretation Rules

- Compare against frozen source values, not values copied from the paper.
- A missing file, field, raw output, or selection policy is `UNVERIFIED`.
- A source value that differs beyond the declared tolerance is `MISMATCH`.
- Best/max/min selection across multiple runs without a declared policy is `UNVERIFIED` with `UNDISCLOSED_SELECTION_RISK`, even when the chosen number exists.
- Rounding is acceptable only when the rule and precision are declared or obvious from the presentation contract.
- Preserve excluded runs and reasons. Never delete or ignore a seed because it weakens the headline result.

For non-JSON sources, use an inspectable notebook or script to create a frozen intermediate ledger, record that transformation, and then verify the ledger. Do not transcribe values without provenance.
