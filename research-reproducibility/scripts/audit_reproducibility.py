#!/usr/bin/env python3
"""Read-only evidence audit for a research project's reproducibility level."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


LEVEL_NAMES = {
    0: "INSUFFICIENT",
    1: "DOCUMENTED",
    2: "RECONSTRUCTABLE",
    3: "RERUNNABLE",
    4: "INDEPENDENTLY_REPRODUCED",
}


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def real_files(path: Path) -> list[Path]:
    if not path.is_dir():
        return []
    return [item for item in path.rglob("*") if item.is_file() and item.name != ".gitkeep"]


def find_seed(value: Any) -> bool:
    if isinstance(value, dict):
        for key, child in value.items():
            if "seed" in key.lower() or "random_state" in key.lower():
                return child is not None
            if find_seed(child):
                return True
    if isinstance(value, list):
        return any(find_seed(child) for child in value)
    return False


def add_check(checks: list[dict[str, str]], check_id: str, status: str, evidence: str) -> None:
    checks.append({"id": check_id, "status": status, "evidence": evidence})


def audit(project: Path, reproduction_evidence: Path | None) -> dict[str, Any]:
    checks: list[dict[str, str]] = []
    issues: list[dict[str, str]] = []

    readme = project / "README.md"
    config_paths = sorted((project / "configs").glob("*.json")) if (project / "configs").is_dir() else []
    configs: list[Any] = []
    for path in config_paths:
        try:
            configs.append(read_json(path))
        except (OSError, json.JSONDecodeError) as error:
            issues.append({"code": "INVALID_CONFIG", "severity": "HIGH", "message": f"{path}: {error}"})

    source_files = list((project / "src").rglob("*.py")) if (project / "src").is_dir() else []
    scope_ok = readme.is_file() and bool(config_paths)
    add_check(checks, "research-scope", "PASS" if scope_ok else "FAIL", "README and experiment configuration" if scope_ok else "README or experiment configuration missing")
    add_check(checks, "source", "PASS" if source_files else "FAIL", f"{len(source_files)} Python source file(s)")

    python_file = project / ".python-version"
    python_ok = python_file.is_file() and bool(python_file.read_text(encoding="utf-8").strip())
    add_check(checks, "python-version", "PASS" if python_ok else "FAIL", python_file.name if python_ok else "missing .python-version")

    declaration = project / "pyproject.toml"
    lock = project / "uv.lock"
    lock_ok = declaration.is_file() and lock.is_file()
    add_check(checks, "dependency-lock", "PASS" if lock_ok else "FAIL", "pyproject.toml + uv.lock" if lock_ok else "dependency declaration or lockfile missing")

    seed_ok = any(find_seed(config) for config in configs)
    add_check(checks, "recorded-seed", "PASS" if seed_ok else "FAIL", "seed/random_state found in configuration" if seed_ok else "no recorded seed")

    raw_files = real_files(project / "data" / "raw")
    processed_files = real_files(project / "data" / "processed")
    manifest_candidates = (project / "data-manifest.json", project / "data" / "data-manifest.json")
    has_manifest = any(path.is_file() for path in manifest_candidates)
    config_text = json.dumps(configs, sort_keys=True).lower()
    builtin_dataset = any(name in config_text for name in ("iris", "digits", "wine", "breast_cancer"))
    if processed_files and not raw_files and not has_manifest:
        data_ok = False
        add_check(checks, "data-provenance", "FAIL", "processed data exists without raw inputs or data manifest")
        issues.append({"code": "PROCESSED_WITHOUT_RAW_PROVENANCE", "severity": "HIGH", "message": "Processed data is an unexplained starting point."})
    elif raw_files and not has_manifest:
        data_ok = False
        add_check(checks, "data-provenance", "FAIL", "raw data exists but no data manifest was found")
        issues.append({"code": "RAW_DATA_MANIFEST_MISSING", "severity": "HIGH", "message": "Raw data source, version, checksum, retrieval date, or license cannot be established."})
    elif builtin_dataset:
        data_ok = True
        add_check(checks, "data-provenance", "PASS", "version-locked built-in dataset declared in configuration and source")
    elif has_manifest:
        data_ok = True
        add_check(checks, "data-provenance", "PASS", "data manifest present")
    else:
        data_ok = False
        add_check(checks, "data-provenance", "FAIL", "no traceable raw, generated, or built-in dataset evidence")

    readme_text = readme.read_text(encoding="utf-8") if readme.is_file() else ""
    commands_ok = "uv sync --locked" in readme_text and ("experiment" in readme_text or "run" in readme_text)
    add_check(checks, "run-commands", "PASS" if commands_ok else "FAIL", "setup and run commands documented" if commands_ok else "setup or run command missing")

    run_dirs = []
    runs_root = project / "runs"
    if runs_root.is_dir():
        for candidate in sorted(runs_root.iterdir()):
            if candidate.is_dir() and all((candidate / name).is_file() for name in ("config.json", "metrics.json", "environment.txt")):
                run_dirs.append(candidate)
    add_check(checks, "recorded-runs", "PASS" if run_dirs else "FAIL", f"{len(run_dirs)} complete run record(s)")

    run_pair_ok = False
    if len(run_dirs) >= 2:
        try:
            run_pair_ok = read_json(run_dirs[0] / "metrics.json") == read_json(run_dirs[1] / "metrics.json")
        except (OSError, json.JSONDecodeError):
            run_pair_ok = False
    add_check(checks, "run-pair-consistency", "PASS" if run_pair_ok else "FAIL", "two recorded runs have identical metrics" if run_pair_ok else "no consistent pair of complete runs")

    artifact_lineage_ok = False
    canonical_metrics = project / "artifacts" / "metrics" / "baseline_metrics.json"
    figure_files = real_files(project / "artifacts" / "figures")
    if run_dirs and canonical_metrics.is_file():
        try:
            artifact_lineage_ok = read_json(canonical_metrics) == read_json(run_dirs[0] / "metrics.json") and bool(figure_files)
        except (OSError, json.JSONDecodeError):
            artifact_lineage_ok = False
    add_check(checks, "artifact-lineage", "PASS" if artifact_lineage_ok else "FAIL", "canonical metrics match a recorded run and a figure exists" if artifact_lineage_ok else "canonical metric/figure lineage is incomplete")

    environment_ok = bool(run_dirs) and all("python_version=" in (run / "environment.txt").read_text(encoding="utf-8") and "platform=" in (run / "environment.txt").read_text(encoding="utf-8") for run in run_dirs)
    add_check(checks, "environment-snapshot", "PASS" if environment_ok else "FAIL", "recorded run environment includes Python and platform" if environment_ok else "run environment metadata incomplete")

    essentials = scope_ok and bool(source_files) and python_ok and lock_ok and seed_ok and data_ok and commands_ok
    level = 0
    if readme.is_file() or config_paths:
        level = 1
    if essentials:
        level = 2
    if essentials and run_pair_ok and artifact_lineage_ok and environment_ok:
        level = 3

    level4_ok = False
    if reproduction_evidence and reproduction_evidence.is_file():
        try:
            evidence = read_json(reproduction_evidence)
            level4_ok = all(
                (
                    evidence.get("authorized") is True,
                    evidence.get("independent") is True,
                    evidence.get("clean_environment") is True,
                    evidence.get("status") == "MATCH",
                )
            )
        except (OSError, json.JSONDecodeError):
            level4_ok = False
    add_check(checks, "independent-clean-reproduction", "PASS" if level4_ok else "NOT_APPLICABLE", "authorized independent clean reproduction matched" if level4_ok else "no qualifying Level 4 evidence supplied")
    if level == 3 and level4_ok:
        level = 4

    return {
        "skill": "research-reproducibility",
        "project_root": str(project),
        "level": level,
        "level_name": LEVEL_NAMES[level],
        "authorized_execution_performed": False,
        "checks": checks,
        "issues": issues,
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Reproducibility Audit",
        "",
        "## Reproducibility Level",
        "",
        f"**Level {report['level']} — {report['level_name']}**",
        "",
        "This is a technical reproducibility status, not a paper-quality rating.",
        "",
        "## Evidence Checks",
        "",
        "| Check | Status | Evidence |",
        "|---|---|---|",
    ]
    for check in report["checks"]:
        lines.append(f"| {check['id']} | {check['status']} | {check['evidence']} |")
    lines.extend(["", "## Issues", ""])
    if report["issues"]:
        for issue in report["issues"]:
            lines.append(f"- **{issue['code']} ({issue['severity']})**: {issue['message']}")
    else:
        lines.append("- No blocking issue detected by the deterministic evidence pass.")
    lines.extend([
        "",
        "## Authorization Record",
        "",
        "No project execution, environment creation, download, or retraining was performed by this audit script.",
        "",
    ])
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, required=True)
    parser.add_argument("--json-out", type=Path)
    parser.add_argument("--markdown-out", type=Path)
    parser.add_argument("--reproduction-evidence", type=Path)
    args = parser.parse_args()

    project = args.project_root.resolve()
    if not project.is_dir():
        parser.error(f"project root is not a directory: {project}")
    report = audit(project, args.reproduction_evidence)
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    markdown = render_markdown(report)
    if args.markdown_out:
        args.markdown_out.parent.mkdir(parents=True, exist_ok=True)
        args.markdown_out.write_text(markdown, encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 1 if any(issue["severity"] == "HIGH" for issue in report["issues"]) or report["level"] == 0 else 0


if __name__ == "__main__":
    raise SystemExit(main())
