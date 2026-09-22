#!/usr/bin/env python3
"""Read-only evidence audit for a research project's reproducibility level."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import math
import re
from itertools import combinations
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
    value = json.loads(path.read_text(encoding="utf-8"))
    def finite(item: Any) -> bool:
        if isinstance(item, float):
            return math.isfinite(item)
        if isinstance(item, dict):
            return all(finite(child) for child in item.values())
        if isinstance(item, list):
            return all(finite(child) for child in item)
        return True
    if not finite(value):
        raise ValueError("non-finite JSON value")
    return value


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return ""


def check_manifest(path: Path, project: Path, raw_files: list[Path]) -> tuple[str, str]:
    """Check recorded provenance and local bytes, without downloading data."""
    try:
        manifest = read_json(path)
        records = manifest.get("datasets") if isinstance(manifest, dict) else None
        if not isinstance(records, list) or not records:
            return "UNVERIFIED", "data manifest needs a non-empty datasets list"
        covered: set[Path] = set()
        for record in records:
            required = ("path", "source", "version", "retrieved_at", "license", "sha256")
            if not isinstance(record, dict) or any(not isinstance(record.get(key), str) or not record[key].strip() for key in required):
                return "UNVERIFIED", "a dataset record lacks path/source/version/retrieved_at/license/sha256"
            relative = Path(record["path"])
            source = (project / relative).resolve()
            if relative.is_absolute() or not source.is_relative_to(project.resolve()) or not source.is_file():
                return "UNVERIFIED", "dataset path must name an existing project-relative file"
            if not re.fullmatch(r"[a-fA-F0-9]{64}", record["sha256"]):
                return "UNVERIFIED", "dataset sha256 is not a 64-digit hexadecimal digest"
            digest = hashlib.sha256()
            with source.open("rb") as handle:
                for block in iter(lambda: handle.read(1024 * 1024), b""):
                    digest.update(block)
            if digest.hexdigest() != record["sha256"].lower():
                return "FAIL", f"dataset checksum mismatch: {record['path']}"
            covered.add(source)
        if not {file.resolve() for file in raw_files}.issubset(covered):
            return "UNVERIFIED", "data manifest does not cover every local raw file"
        return "PASS", f"{len(records)} dataset record(s): required metadata present and local SHA-256 matched; external provenance not authenticated"
    except (OSError, UnicodeError, ValueError) as error:
        return "UNVERIFIED", f"could not inspect data manifest: {error}"


def builtin_evidence(configs: list[Any], sources: list[Path], lock: Path) -> bool:
    """Recognize the supported sklearn layout; arbitrary name mentions do not count."""
    datasets = {"iris", "digits", "wine", "breast_cancer"}
    names = [config.get("dataset") for config in configs]
    if not names or any(not isinstance(name, str) or name not in datasets for name in names):
        return False
    locked = any(re.search(r'(?m)^name\s*=\s*"scikit-learn"\s*$', block) and re.search(r'(?m)^version\s*=\s*"[^"\n]+"', block) for block in read_text(lock).split("[[package]]")[1:])
    if not locked:
        return False
    called = set()
    for source in sources:
        try:
            tree = ast.parse(read_text(source))
        except SyntaxError:
            continue
        loaders = {alias.asname or alias.name: alias.name for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.module == "sklearn.datasets" for alias in node.names}
        called.update(loaders.get(node.func.id) for node in ast.walk(tree) if isinstance(node, ast.Call) and isinstance(node.func, ast.Name))
    return all(f"load_{name}" in called for name in names)


def real_files(path: Path) -> list[Path]:
    if not path.is_dir():
        return []
    return [item for item in path.rglob("*") if item.is_file() and item.name != ".gitkeep"]


def find_seed(value: Any) -> bool:
    if isinstance(value, dict):
        for key, child in value.items():
            if key.lower() in {"seed", "seeds", "random_seed", "random_state"}:
                if type(child) is int or (isinstance(child, list) and child and all(type(seed) is int for seed in child)):
                    return True
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
            config = read_json(path)
            if not isinstance(config, dict) or not config:
                raise ValueError("configuration must be a non-empty object")
            configs.append(config)
        except (OSError, UnicodeError, ValueError) as error:
            issues.append({"code": "INVALID_CONFIG", "severity": "HIGH", "message": f"{path}: {error}"})

    source_files = list((project / "src").rglob("*.py")) if (project / "src").is_dir() else []
    scope_ok = bool(read_text(readme).strip()) and bool(configs) and len(configs) == len(config_paths)
    add_check(checks, "research-scope", "PASS" if scope_ok else "FAIL", "README and experiment configuration" if scope_ok else "README or experiment configuration missing")
    add_check(checks, "source", "PASS" if source_files else "FAIL", f"{len(source_files)} Python source file(s)")

    python_file = project / ".python-version"
    python_ok = bool(read_text(python_file).strip())
    add_check(checks, "python-version", "PASS" if python_ok else "FAIL", python_file.name if python_ok else "missing .python-version")

    declaration = project / "pyproject.toml"
    lock = project / "uv.lock"
    lock_ok = bool(read_text(declaration).strip()) and bool(read_text(lock).strip())
    add_check(checks, "dependency-lock", "PASS" if lock_ok else "FAIL", "pyproject.toml + uv.lock" if lock_ok else "dependency declaration or lockfile missing")

    seed_ok = bool(configs) and all(find_seed(config) for config in configs)
    add_check(checks, "recorded-seed", "PASS" if seed_ok else "FAIL", "seed/random_state found in configuration" if seed_ok else "no recorded seed")

    raw_files = real_files(project / "data" / "raw")
    processed_files = real_files(project / "data" / "processed")
    manifest_candidates = (project / "data-manifest.json", project / "data" / "data-manifest.json")
    has_manifest = any(path.is_file() for path in manifest_candidates)
    builtin_dataset = builtin_evidence(configs, source_files, lock)
    if processed_files and not raw_files and not has_manifest:
        data_ok = False
        add_check(checks, "data-provenance", "FAIL", "processed data exists without raw inputs or data manifest")
        issues.append({"code": "PROCESSED_WITHOUT_RAW_PROVENANCE", "severity": "HIGH", "message": "Processed data is an unexplained starting point."})
    elif raw_files and not has_manifest:
        data_ok = False
        add_check(checks, "data-provenance", "FAIL", "raw data exists but no data manifest was found")
        issues.append({"code": "RAW_DATA_MANIFEST_MISSING", "severity": "HIGH", "message": "Raw data source, version, checksum, retrieval date, or license cannot be established."})
    elif has_manifest:
        status, evidence = check_manifest(next(path for path in manifest_candidates if path.is_file()), project, raw_files)
        data_ok = status == "PASS"
        add_check(checks, "data-provenance", status, evidence)
        if not data_ok:
            issues.append({"code": "DATA_PROVENANCE_UNVERIFIED" if status == "UNVERIFIED" else "DATA_CHECKSUM_MISMATCH", "severity": "HIGH", "message": evidence})
    elif builtin_dataset:
        data_ok = True
        add_check(checks, "data-provenance", "PASS", "explicit sklearn dataset, versioned lock entry, and loader call found; runtime use not executed")
    else:
        data_ok = False
        add_check(checks, "data-provenance", "FAIL", "no traceable raw, generated, or built-in dataset evidence")

    readme_text = read_text(readme)
    commands_ok = "uv sync --locked" in readme_text and ("experiment" in readme_text or "run" in readme_text)
    add_check(checks, "run-commands", "PASS" if commands_ok else "FAIL", "setup and run commands documented" if commands_ok else "setup or run command missing")

    run_dirs = []
    runs_root = project / "runs"
    if runs_root.is_dir():
        for candidate in sorted(runs_root.iterdir()):
            if candidate.is_dir() and all((candidate / name).is_file() for name in ("config.json", "metrics.json", "environment.txt")):
                run_dirs.append(candidate)
    add_check(checks, "recorded-runs", "PASS" if run_dirs else "FAIL", f"{len(run_dirs)} complete run record(s)")

    run_records = []
    for run in run_dirs:
        try:
            metrics, config = read_json(run / "metrics.json"), read_json(run / "config.json")
            if isinstance(metrics, dict) and metrics and isinstance(config, dict) and config:
                run_records.append((run, config, metrics))
        except (OSError, UnicodeError, ValueError) as error:
            issues.append({"code": "INVALID_RUN_RECORD", "severity": "HIGH", "message": f"{run.name}: {error}"})
    run_pair_ok = any(left[1:] == right[1:] for left, right in combinations(run_records, 2))
    add_check(checks, "run-pair-consistency", "PASS" if run_pair_ok else "UNVERIFIED", "two recorded runs have identical non-empty configuration and metrics" if run_pair_ok else "no matching pair of valid configuration and metric records")

    artifact_lineage_ok = False
    canonical_metrics = project / "artifacts" / "metrics" / "baseline_metrics.json"
    figure_files = real_files(project / "artifacts" / "figures")
    if run_records and canonical_metrics.is_file():
        try:
            artifact_lineage_ok = any(read_json(canonical_metrics) == record[2] for record in run_records) and bool(figure_files)
        except (OSError, UnicodeError, ValueError):
            artifact_lineage_ok = False
    add_check(checks, "artifact-lineage", "PASS" if artifact_lineage_ok else "FAIL", "canonical metrics match a recorded run and a figure exists" if artifact_lineage_ok else "canonical metric/figure lineage is incomplete")

    environment_ok = bool(run_dirs) and all(re.search(r"(?m)^python_version=\S+", read_text(run / "environment.txt")) and re.search(r"(?m)^platform=\S+", read_text(run / "environment.txt")) for run in run_dirs)
    add_check(checks, "environment-snapshot", "PASS" if environment_ok else "FAIL", "recorded run environment includes Python and platform" if environment_ok else "run environment metadata incomplete")

    essentials = scope_ok and bool(source_files) and python_ok and lock_ok and seed_ok and data_ok and commands_ok
    level = 0
    if readme.is_file() or config_paths:
        level = 1
    if essentials:
        level = 2
    if essentials and run_pair_ok and artifact_lineage_ok and environment_ok:
        level = 3

    independent_note = "no independent reproduction record supplied"
    if reproduction_evidence:
        try:
            evidence = read_json(reproduction_evidence)
            if not isinstance(evidence, dict) or not evidence:
                raise ValueError("reproduction evidence must be a non-empty object")
            independent_note = "record supplied; authorization, independence, target, acceptance criteria, logs and result lineage require reviewer validation"
        except (OSError, UnicodeError, ValueError) as error:
            independent_note = f"could not inspect reproduction evidence: {error}"
            issues.append({"code": "INVALID_REPRODUCTION_EVIDENCE", "severity": "HIGH", "message": independent_note})
    add_check(checks, "independent-clean-reproduction", "UNVERIFIED", independent_note)

    return {
        "skill": "research-reproducibility",
        "project_root": str(project),
        "level": level,
        "level_name": LEVEL_NAMES[level],
        "authorized_execution_performed": False,
        "assessment_scope": "STRUCTURAL_EVIDENCE_ONLY",
        "limitations": ["Levels are provisional evidence classifications for the supported Python/uv layout.", "File presence and matching metrics do not authenticate execution, dependency resolution, source revision, or figure derivation.", "The helper never awards Level 4; a reviewer must validate the independent reproduction record."],
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
        "This is a provisional structural evidence assessment, not proof of reproducibility or a paper-quality rating.",
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
    lines.extend(["", "## Limits of This Pass", ""])
    lines.extend(f"- {item}" for item in report["limitations"])
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
