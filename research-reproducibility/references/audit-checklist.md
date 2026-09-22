# Reproducibility Evidence Checklist

## Scope

- Name the target result and acceptance criteria.
- Distinguish exploratory outputs from final reported results.
- Record exclusions and unavailable evidence.

## Environment

- Exact Python/runtime version.
- Direct dependency declaration and resolved lockfile.
- Reconstruction command tested from a clean directory when authorized.
- Operating system, architecture, relevant CPU/GPU/accelerator, and material driver/runtime versions.

## Data provenance

For each raw dataset record source, version or immutable identifier, retrieval date, checksum, and license when relevant. Identify the code and parameters for each raw-to-interim-to-processed transition. A processed file without a traceable raw source is a reproducibility blocker.

Built-in or generated datasets may be treated as traceable only when the generator/library, version, parameters, and seed are locked.

## Configuration and randomness

- Versioned experiment and preprocessing configuration.
- Dataset split logic and exact split identifiers when applicable.
- All material seeds and deterministic settings.
- Model, optimizer, scheduler, stopping, and selection parameters.

## Execution and lineage

- Exact setup and run commands.
- Source revision or immutable source snapshot.
- Write-once run ID with config, environment, metrics, and logs.
- Artifact mapping from run output to canonical metrics, tables, figures, and checkpoints.
- Checksums for frozen or externally transferred artifacts when material.

## Level 4 evidence

Level 4 requires a reproduction record showing all of the following:

- execution was explicitly authorized;
- the environment was created independently from declared inputs;
- the target result and tolerance were declared before comparison;
- the reproduction ran from the clean environment;
- observed results met the acceptance criteria;
- failures and deviations were preserved, not edited away.

Automated tests, a successful import, or two runs inside one existing environment support lower levels only.
