# Portable Research Agent Skills

This repository is the single master copy for five evidence-first research Agent Skills shared by Codex, Claude Code, and OpenCode.

## Included Skills

| Skill | Purpose |
|---|---|
| `research-literature-review` | Traceable scholarly discovery, screening, citation verification, reading, and evidence synthesis |
| `research-experiment-design` | Controlled, falsifiable pre-execution research protocols |
| `research-reproducibility` | Reconstruction, environment, input, command, seed, and artifact-lineage audits |
| `research-result-verification` | Raw-output-to-number, table, figure, and claim reconciliation |
| `research-paper-audit` | Final manuscript-level integration audit and routing to the four upstream Skills |

Every Skill retains its complete `SKILL.md`, `scripts/`, `references/`, and `assets/` resources. The deterministic helpers preserve their valid-input output contracts while rejecting malformed or insufficient evidence conservatively.

## Repository Layout

```text
agent-skills/
├── research-experiment-design/
├── research-literature-review/
├── research-paper-audit/
├── research-reproducibility/
├── research-result-verification/
├── scripts/
│   └── verify-install-links.sh
├── tests/
├── .gitattributes
├── .gitignore
├── README.md
└── WINDOWS_WSL_MIGRATION.md
```

## Runtime Dependencies

Required:

- Python 3.10 or newer
- Python standard library only
- Git for cloning, history, and updates
- Bash for the optional installation-link verifier; Bash is included with Ubuntu under WSL
- A POSIX-compatible filesystem with symlink support for the recommended installation model

Not required by these Skills:

- Node.js or npm
- pip-installed packages
- uv
- curl, jq, or ripgrep

Web search, scholarly databases, PDF/document handling, spreadsheets, data analysis, code review, and debugging are optional Agent capabilities used only when a workflow calls for them.

### Per-Skill dependency classification

| Skill | Mandatory | Optional | Mac-only | WSL installation |
|---|---|---|---|---|
| `research-experiment-design` | Python 3.10+, writable output directory | Data-analysis capability for inspecting existing data | None | Python 3 and Git |
| `research-literature-review` | Python 3.10+, writable output directory | Web/scholarly search, PDF/document, spreadsheet, and data-analysis capabilities | None | Python 3 and Git |
| `research-paper-audit` | Python 3.10+, writable output directory | PDF/document handling; OpenCode + DeepSeek first pass; Codex final gate | None | Python 3 and Git |
| `research-reproducibility` | Python 3.10+; readable project evidence | Git, uv, hardware/accelerator tooling only when the audited project declares them | None | Python 3 and Git; project-specific tools remain optional |
| `research-result-verification` | Python 3.10+; readable JSON/CSV evidence; writable output directory | Data-quality and analysis-validation capabilities | None | Python 3 and Git |

References to Git, uv, model frameworks, accelerators, or research environments inside an audit describe the target project's evidence. They are not dependencies of the Skill helper scripts.

## Portable Script Invocation

An Agent may be running from an unrelated project directory. It must resolve paths from the directory containing the active Skill's `SKILL.md`:

```bash
SKILL_ROOT="<directory-containing-the-active-SKILL.md>"
python3 "$SKILL_ROOT/scripts/<script>.py" --help
```

Do not assume that the caller's current directory contains `scripts/`, `references/`, or `assets/`.

## Agent Compatibility

| Capability | Status |
|---|---|
| Core Skill instructions, evidence contracts, resources, and Python helpers | Portable |
| Discovery through `$HOME/.agents/skills` | Codex and OpenCode |
| Discovery through `$HOME/.claude/skills` | Claude Code |
| High-throughput first-pass paper inventory | OpenCode only policy in `research-paper-audit` |
| Final paper-audit severity and scientific gate | Codex only policy in `research-paper-audit` |
| Paper-audit use from Claude Code | Requires explicit user authorization |

Agent-specific policy is retained and labeled; it is not part of the portable core and has not been removed.

## Install

Keep this repository as the only master. Expose each Skill with directory symlinks; do not copy Skill contents into host-specific discovery directories.

See [WINDOWS_WSL_MIGRATION.md](WINDOWS_WSL_MIGRATION.md) for complete WSL preparation, linking, validation, update, and troubleshooting instructions.

## Validate

From the repository root:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -v
```

The two optional integration tests that exercise a separate research project template run only when `RESEARCH_TEMPLATE_PATH` points to that template. All remaining tests are self-contained.

Validate each Skill's frontmatter with the Skill validator supplied by the Agent environment when available. The repository tests independently check open frontmatter fields, relative resources, LF line endings, portable commands, CLI startup, and deterministic research contracts.

## Update Policy

1. Change only this master repository.
2. Add or update a failing behavioral test before changing deterministic scripts.
3. Keep host discovery paths as symlinks to these directories.
4. Run the complete test suite and Skill validators.
5. Review the Git diff and commit only a clean, validated state.

The canonical remote is the private GitHub repository
`https://github.com/sadwan555/agent-skills`. Access requires authorization to
that repository.
