from __future__ import annotations

import csv
import os
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = (
    ROOT
    / "research-result-verification"
    / "scripts"
    / "verify_results.py"
)
TEMPLATE_ENV = os.environ.get("RESEARCH_TEMPLATE_PATH")
TEMPLATE = Path(TEMPLATE_ENV).resolve() if TEMPLATE_ENV else None
FIXTURES = ROOT / "tests" / "fixtures"


def run_verification(project: Path, ledger: Path) -> tuple[subprocess.CompletedProcess[str], list[dict[str, str]], str, str]:
    with tempfile.TemporaryDirectory() as temporary:
        output = Path(temporary)
        completed = subprocess.run(
            [
                "python3",
                str(SCRIPT),
                "--project-root",
                str(project),
                "--ledger",
                str(ledger),
                "--output-dir",
                str(output),
            ],
            text=True,
            capture_output=True,
            check=False,
        )
        result_path = output / "result-ledger.csv"
        if result_path.exists():
            with result_path.open(encoding="utf-8", newline="") as handle:
                rows = list(csv.DictReader(handle))
        else:
            rows = []
        claim_map = (output / "claim-result-map.md").read_text(encoding="utf-8") if (output / "claim-result-map.md").exists() else ""
        report = (output / "verification-report.md").read_text(encoding="utf-8") if (output / "verification-report.md").exists() else ""
        return completed, rows, claim_map, report


class ResultVerificationTests(unittest.TestCase):
    def test_existing_template_results_are_consistent(self) -> None:
        if TEMPLATE is None:
            self.skipTest("set RESEARCH_TEMPLATE_PATH to run the optional template integration test")
        self.assertTrue(TEMPLATE.is_dir(), f"RESEARCH_TEMPLATE_PATH is not a directory: {TEMPLATE}")
        completed, rows, claim_map, report = run_verification(
            TEMPLATE, FIXTURES / "template-result-ledger.csv"
        )
        self.assertEqual(0, completed.returncode, completed.stderr)
        self.assertEqual(9, len(rows))
        self.assertEqual({"VERIFIED"}, {row["status"] for row in rows})
        self.assertIn("baseline-run-01", claim_map)
        self.assertIn("baseline-run-02", claim_map)
        self.assertIn("baseline_metrics.json", claim_map)
        self.assertIn("VERIFIED: 9", report)

    def test_negative_fixtures_receive_only_allowed_statuses(self) -> None:
        cases = (
            ("mismatch", "MISMATCH", ""),
            ("missing-raw-output", "UNVERIFIED", ""),
            ("paper-number-only", "UNVERIFIED", ""),
            ("undisclosed-best-seed", "UNVERIFIED", "UNDISCLOSED_SELECTION_RISK"),
        )
        allowed = {"VERIFIED", "MISMATCH", "UNVERIFIED", "NOT_APPLICABLE"}
        for fixture_name, expected, risk in cases:
            fixture = FIXTURES / fixture_name
            with self.subTest(fixture=fixture_name):
                completed, rows, _, report = run_verification(fixture, fixture / "ledger.csv")
                self.assertEqual(1, completed.returncode)
                self.assertEqual(1, len(rows))
                self.assertIn(rows[0]["status"], allowed)
                self.assertEqual(expected, rows[0]["status"])
                if risk:
                    self.assertIn(risk, report)


if __name__ == "__main__":
    unittest.main()
