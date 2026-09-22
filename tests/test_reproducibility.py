from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "research-reproducibility" / "scripts" / "audit_reproducibility.py"
TEMPLATE_ENV = os.environ.get("RESEARCH_TEMPLATE_PATH")
TEMPLATE = Path(TEMPLATE_ENV).resolve() if TEMPLATE_ENV else None
FIXTURE = ROOT / "tests" / "fixtures" / "processed-without-raw-provenance"


def run_audit(project: Path, evidence: Path | None = None) -> tuple[subprocess.CompletedProcess[str], dict[str, object], str]:
    with tempfile.TemporaryDirectory() as temporary:
        output = Path(temporary)
        json_path = output / "report.json"
        markdown_path = output / "REPRODUCIBILITY.md"
        completed = subprocess.run(
            [
                "python3",
                str(SCRIPT),
                "--project-root",
                str(project),
                "--json-out",
                str(json_path),
                "--markdown-out",
                str(markdown_path),
            ] + (["--reproduction-evidence", str(evidence)] if evidence else []),
            text=True,
            capture_output=True,
            check=False,
        )
        report = json.loads(json_path.read_text(encoding="utf-8")) if json_path.exists() else {}
        markdown = markdown_path.read_text(encoding="utf-8") if markdown_path.exists() else ""
        return completed, report, markdown


class ReproducibilityTests(unittest.TestCase):
    def make_project(self, root: Path) -> Path:
        for directory in ("configs", "src", "data/raw", "runs/a", "runs/b", "artifacts/metrics", "artifacts/figures"):
            (root / directory).mkdir(parents=True, exist_ok=True)
        (root / "README.md").write_text("Target: accuracy.\nuv sync --locked\nuv run experiment\n", encoding="utf-8")
        (root / ".python-version").write_text("3.11\n", encoding="utf-8")
        (root / "pyproject.toml").write_text('[project]\nname = "example"\nversion = "0.1"\n', encoding="utf-8")
        (root / "uv.lock").write_text("version = 1\n", encoding="utf-8")
        (root / "src/train.py").write_text("# frozen source\n", encoding="utf-8")
        (root / "configs/experiment.json").write_text('{"random_state": 42, "dataset": "local"}', encoding="utf-8")
        (root / "data/raw/data.csv").write_text("x,y\n1,0\n", encoding="utf-8")
        import hashlib
        record = {"path": "data/raw/data.csv", "source": "local fixture", "version": "v1", "retrieved_at": "2026-01-01", "license": "CC0", "sha256": hashlib.sha256((root / "data/raw/data.csv").read_bytes()).hexdigest()}
        (root / "data-manifest.json").write_text(json.dumps({"datasets": [record]}), encoding="utf-8")
        for name in ("a", "b"):
            (root / f"runs/{name}/config.json").write_text('{"seed": 42}', encoding="utf-8")
            (root / f"runs/{name}/metrics.json").write_text('{"accuracy": 0.9}', encoding="utf-8")
            (root / f"runs/{name}/environment.txt").write_text("python_version=3.11\nplatform=test\n", encoding="utf-8")
        (root / "artifacts/metrics/baseline_metrics.json").write_text('{"accuracy": 0.9}', encoding="utf-8")
        (root / "artifacts/figures/result.svg").write_text("<svg/>", encoding="utf-8")
        return root

    def test_manifest_presence_alone_does_not_verify_provenance(self) -> None:
        for contents in ("{}", "[]", "{broken", '{"datasets": []}'):
            with self.subTest(contents=contents), tempfile.TemporaryDirectory() as temporary:
                project = self.make_project(Path(temporary))
                (project / "data-manifest.json").write_text(contents, encoding="utf-8")
                completed, report, _ = run_audit(project)
                self.assertNotIn("Traceback", completed.stderr)
                checks = {item["id"]: item["status"] for item in report["checks"]}
                self.assertNotEqual("PASS", checks["data-provenance"])
                self.assertLess(report["level"], 2)

    def test_checksum_disagreement_is_a_provenance_failure(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = self.make_project(Path(temporary))
            (project / "data/raw/data.csv").write_text("changed\n", encoding="utf-8")
            _, report, _ = run_audit(project)
            checks = {item["id"]: item["status"] for item in report["checks"]}
            self.assertEqual("FAIL", checks["data-provenance"])

    def test_matching_metrics_from_different_configs_are_not_a_rerun_pair(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = self.make_project(Path(temporary))
            (project / "runs/b/config.json").write_text('{"seed": 13}', encoding="utf-8")
            _, report, _ = run_audit(project)
            checks = {item["id"]: item["status"] for item in report["checks"]}
            self.assertNotEqual("PASS", checks["run-pair-consistency"])
            self.assertLess(report["level"], 3)

    def test_empty_metrics_are_not_rerun_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = self.make_project(Path(temporary))
            for name in ("a", "b"):
                (project / f"runs/{name}/metrics.json").write_text("{}", encoding="utf-8")
            _, report, _ = run_audit(project)
            checks = {item["id"]: item["status"] for item in report["checks"]}
            self.assertNotEqual("PASS", checks["run-pair-consistency"])

    def test_missing_or_malformed_independent_evidence_is_unverified(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = self.make_project(Path(temporary))
            evidence = project / "reproduction.json"
            for contents in (None, "[]", '{"authorized": true, "independent": true, "clean_environment": true, "status": "MATCH"}'):
                if contents is not None:
                    evidence.write_text(contents, encoding="utf-8")
                with self.subTest(contents=contents):
                    completed, report, _ = run_audit(project, evidence if contents else None)
                    self.assertNotIn("Traceback", completed.stderr)
                    self.assertTrue(report, completed.stderr)
                    checks = {item["id"]: item["status"] for item in report["checks"]}
                    self.assertEqual("UNVERIFIED", checks["independent-clean-reproduction"])
                    self.assertLess(report["level"], 4)

    def test_valid_local_manifest_is_checked_without_executing_project(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = self.make_project(Path(temporary))
            _, report, _ = run_audit(project)
            checks = {item["id"]: item["status"] for item in report["checks"]}
            self.assertEqual("PASS", checks["data-provenance"])
            self.assertFalse(report["authorized_execution_performed"])

    def test_existing_template_is_level_three_not_level_four(self) -> None:
        if TEMPLATE is None:
            self.skipTest("set RESEARCH_TEMPLATE_PATH to run the optional template integration test")
        self.assertTrue(TEMPLATE.is_dir(), f"RESEARCH_TEMPLATE_PATH is not a directory: {TEMPLATE}")
        completed, report, markdown = run_audit(TEMPLATE)
        self.assertEqual(0, completed.returncode, completed.stderr)
        self.assertEqual(3, report["level"])
        self.assertEqual("RERUNNABLE", report["level_name"])
        self.assertFalse(report["authorized_execution_performed"])
        self.assertIn("Level 3", markdown)
        checks = {item["id"]: item["status"] for item in report["checks"]}
        self.assertEqual("PASS", checks["python-version"])
        self.assertEqual("PASS", checks["dependency-lock"])
        self.assertEqual("PASS", checks["recorded-seed"])
        self.assertEqual("PASS", checks["run-pair-consistency"])
        self.assertEqual("PASS", checks["artifact-lineage"])

    def test_processed_data_without_raw_provenance_is_reported(self) -> None:
        completed, report, _ = run_audit(FIXTURE)
        self.assertEqual(1, completed.returncode)
        issue_codes = {item["code"] for item in report["issues"]}
        self.assertIn("PROCESSED_WITHOUT_RAW_PROVENANCE", issue_codes)
        self.assertLessEqual(report["level"], 1)


if __name__ == "__main__":
    unittest.main()
