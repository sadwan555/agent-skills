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


def run_audit(project: Path) -> tuple[subprocess.CompletedProcess[str], dict[str, object], str]:
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
            ],
            text=True,
            capture_output=True,
            check=False,
        )
        report = json.loads(json_path.read_text(encoding="utf-8")) if json_path.exists() else {}
        markdown = markdown_path.read_text(encoding="utf-8") if markdown_path.exists() else ""
        return completed, report, markdown


class ReproducibilityTests(unittest.TestCase):
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
