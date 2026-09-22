from __future__ import annotations

import csv
import json
import subprocess
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "research-paper-audit" / "scripts" / "audit_paper.py"
FIXTURES = ROOT / "tests" / "fixtures" / "paper-audit"


def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = deep_merge(merged[key], value)
        else:
            merged[key] = deepcopy(value)
    return merged


def run_audit(fixture: str) -> tuple[subprocess.CompletedProcess[str], dict[str, Any], Path, tempfile.TemporaryDirectory[str]]:
    base = json.loads((FIXTURES / "valid-manuscript.json").read_text(encoding="utf-8"))
    if fixture == "valid-manuscript":
        manuscript = base
    else:
        override = json.loads((FIXTURES / f"{fixture}.json").read_text(encoding="utf-8"))
        manuscript = deep_merge(base, override)

    temporary = tempfile.TemporaryDirectory()
    root = Path(temporary.name)
    input_path = root / "manuscript.json"
    input_path.write_text(json.dumps(manuscript), encoding="utf-8")
    output = root / "output"
    completed = subprocess.run(
        ["python3", str(SCRIPT), "--input", str(input_path), "--output-dir", str(output)],
        text=True,
        capture_output=True,
        check=False,
    )
    summary = json.loads(completed.stdout) if completed.stdout.strip().startswith("{") else {}
    return completed, summary, output, temporary


class PaperAuditTests(unittest.TestCase):
    def test_valid_manuscript_generates_required_audit_artifacts(self) -> None:
        completed, summary, output, temporary = run_audit("valid-manuscript")
        self.addCleanup(temporary.cleanup)
        self.assertEqual(0, completed.returncode, completed.stderr)
        self.assertEqual("NO_BLOCKING_ISSUES_DETECTED", summary["status"])
        self.assertEqual([], summary["issue_codes"])
        for name in (
            "paper-audit.md",
            "claim-evidence-matrix.csv",
            "blocking-issues.md",
            "consistency-map.md",
            "reference-consistency.csv",
            "figure-table-audit.csv",
        ):
            self.assertTrue((output / name).is_file(), name)

        with (output / "claim-evidence-matrix.csv").open(encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
        self.assertEqual(3, len(rows))
        self.assertEqual({"SUPPORTED"}, {row["status"] for row in rows})

    def test_requested_negative_fixtures_emit_exact_issue_codes(self) -> None:
        cases = (
            ("internal-result-mismatch", "INTERNAL_RESULT_MISMATCH", "BLOCKER"),
            ("conclusion-overreach", "CONCLUSION_OVERREACH", "MAJOR"),
            ("seed-count-mismatch", "SEED_COUNT_MISMATCH", "MAJOR"),
            ("missing-reference-entry", "MISSING_REFERENCE_ENTRY", "MAJOR"),
            ("uncited-reference", "UNCITED_REFERENCE", "MINOR"),
            ("figure-caption-mismatch", "FIGURE_CAPTION_MISMATCH", "MAJOR"),
            ("percentage-interpretation-risk", "PERCENTAGE_INTERPRETATION_RISK", "MAJOR"),
            ("unsupported-statistical-language", "UNSUPPORTED_STATISTICAL_LANGUAGE", "MAJOR"),
            ("result-verification-required", "RESULT_VERIFICATION_REQUIRED", "BLOCKER"),
            ("literature-verification-required", "LITERATURE_VERIFICATION_REQUIRED", "MAJOR"),
        )
        for fixture, expected_code, expected_severity in cases:
            with self.subTest(fixture=fixture):
                completed, summary, output, temporary = run_audit(fixture)
                self.addCleanup(temporary.cleanup)
                self.assertEqual(1, completed.returncode)
                self.assertIn(expected_code, summary["issue_codes"])
                report = (output / "paper-audit.md").read_text(encoding="utf-8")
                self.assertIn(expected_code, report)
                self.assertIn(expected_severity, report)

    def test_escalation_routes_are_explicit_and_narrow(self) -> None:
        cases = (
            ("result-verification-required", "research-result-verification"),
            ("literature-verification-required", "research-literature-review"),
            ("conclusion-overreach", "research-experiment-design"),
            ("seed-count-mismatch", "research-result-verification"),
        )
        for fixture, expected_skill in cases:
            with self.subTest(fixture=fixture):
                _, _, output, temporary = run_audit(fixture)
                self.addCleanup(temporary.cleanup)
                report = (output / "paper-audit.md").read_text(encoding="utf-8")
                self.assertIn(expected_skill, report)

    def test_claim_status_contract_is_closed(self) -> None:
        _, _, output, temporary = run_audit("result-verification-required")
        self.addCleanup(temporary.cleanup)
        allowed = {"SUPPORTED", "PARTIALLY_SUPPORTED", "UNSUPPORTED", "UNVERIFIED", "CONTRADICTED"}
        with (output / "claim-evidence-matrix.csv").open(encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
        self.assertTrue(rows)
        self.assertLessEqual({row["status"] for row in rows}, allowed)
        self.assertIn("UNVERIFIED", {row["status"] for row in rows})

    def test_derived_issues_update_claim_status_and_route(self) -> None:
        cases = (
            ("internal-result-mismatch", "C1", "CONTRADICTED", "research-result-verification"),
            ("conclusion-overreach", "C3", "PARTIALLY_SUPPORTED", "research-experiment-design"),
        )
        for fixture, claim_id, expected_status, expected_skill in cases:
            with self.subTest(fixture=fixture):
                _, _, output, temporary = run_audit(fixture)
                self.addCleanup(temporary.cleanup)
                with (output / "claim-evidence-matrix.csv").open(encoding="utf-8", newline="") as handle:
                    rows = {row["claim_id"]: row for row in csv.DictReader(handle)}
                self.assertEqual(expected_status, rows[claim_id]["status"])
                self.assertEqual(expected_skill, rows[claim_id]["downstream_skill"])


if __name__ == "__main__":
    unittest.main()
