from __future__ import annotations

import csv
import json
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


def run_verification(project: Path, ledger: Path, *extra_args: str) -> tuple[subprocess.CompletedProcess[str], list[dict[str, str]], str, str]:
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
                *extra_args,
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
    def verify_value(self, source_json: str, reported: str, *, extra_args: tuple[str, ...] = (), **overrides: str) -> tuple[subprocess.CompletedProcess[str], list[dict[str, str]], str, str]:
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary)
            (project / "source.json").write_text(source_json, encoding="utf-8")
            row = {
                "claim_id": "claim-1", "artifact": "Table 1", "source_path": "source.json",
                "json_path": "value", "reported_value": reported, "aggregation": "single",
                "run_count": "1", "selection_policy": "not-applicable",
                **overrides,
            }
            ledger = project / "ledger.csv"
            with ledger.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=tuple(row))
                writer.writeheader()
                writer.writerow(row)
            return run_verification(project, ledger, *extra_args)

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

    def test_invalid_run_count_is_reported_without_traceback(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary)
            source = project / "source.json"
            source.write_text(json.dumps({"accuracy": 0.9}), encoding="utf-8")
            ledger = project / "ledger.csv"
            ledger.write_text(
                "claim_id,artifact,source_path,json_path,reported_value,aggregation,run_count,selection_policy\n"
                "bad-count,Table,source.json,accuracy,0.9,single,zero,not-applicable\n",
                encoding="utf-8",
            )
            completed, rows, _, report = run_verification(project, ledger)
            self.assertEqual(1, completed.returncode)
            self.assertEqual("UNVERIFIED", rows[0]["status"])
            self.assertIn("run_count is not an integer", report)
            self.assertNotIn("Traceback", completed.stderr)

    def test_non_finite_json_is_not_treated_as_verified(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary)
            source = project / "source.json"
            source.write_text('{"accuracy": NaN}', encoding="utf-8")
            ledger = project / "ledger.csv"
            ledger.write_text(
                "claim_id,artifact,source_path,json_path,reported_value,aggregation,run_count,selection_policy\n"
                "nan,Table,source.json,accuracy,NaN,single,1,not-applicable\n",
                encoding="utf-8",
            )
            completed, rows, _, report = run_verification(project, ledger)
            self.assertEqual(1, completed.returncode)
            self.assertEqual("UNVERIFIED", rows[0]["status"])
            self.assertIn("Could not read requested source value", report)

    def test_truncated_row_does_not_abort_other_ledger_rows(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary)
            (project / "source.json").write_text('{"accuracy": 0.9}', encoding="utf-8")
            ledger = project / "ledger.csv"
            ledger.write_text(
                "claim_id,artifact,source_path,json_path,reported_value,aggregation,run_count,selection_policy\n"
                "truncated,Table\n"
                "complete,Table,source.json,accuracy,0.9,single,1,not-applicable\n",
                encoding="utf-8",
            )
            completed, rows, _, _ = run_verification(project, ledger)
            self.assertNotIn("Traceback", completed.stderr)
            self.assertEqual(1, completed.returncode)
            self.assertEqual(["UNVERIFIED", "VERIFIED"], [row["status"] for row in rows])

    def test_header_only_ledger_does_not_produce_a_clean_report(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary)
            ledger = project / "ledger.csv"
            ledger.write_text(
                "claim_id,artifact,source_path,json_path,reported_value,aggregation,run_count,selection_policy\n",
                encoding="utf-8",
            )
            completed, rows, _, report = run_verification(project, ledger)
            self.assertEqual(2, completed.returncode)
            self.assertEqual([], rows)
            self.assertNotIn("All scoped ledger rows", report)
            self.assertNotIn("Traceback", completed.stderr)

    def test_boolean_and_number_values_are_distinct_at_every_depth(self) -> None:
        cases = (("true", "1"), ("1", "true"), ("[true]", "[1]"), ('{"flag":1}', '{"flag":true}'))
        for observed, reported in cases:
            with self.subTest(observed=observed, reported=reported):
                completed, rows, _, _ = self.verify_value('{"value":' + observed + '}', reported)
                self.assertEqual(1, completed.returncode)
                self.assertEqual("MISMATCH", rows[0]["status"])

    def test_large_integers_do_not_overflow_numeric_comparison(self) -> None:
        huge = 10 ** 400
        for reported, expected in ((str(huge), "VERIFIED"), (str(huge + 1), "MISMATCH")):
            with self.subTest(expected=expected):
                completed, rows, _, _ = self.verify_value(
                    '{"value":' + str(huge) + '}', reported,
                    extra_args=("--relative-tolerance", "0"),
                )
                self.assertNotIn("Traceback", completed.stderr)
                self.assertEqual(expected, rows[0]["status"])

    def test_nested_numeric_overflow_is_unverified(self) -> None:
        cases = (
            ('{"value":{"scores":[1e999]}}', '{"scores":[1e999]}'),
            ('{"value":{"scores":[1]}}', '{"scores":[1e999]}'),
        )
        for observed, reported in cases:
            with self.subTest(source=observed):
                completed, rows, _, _ = self.verify_value(observed, reported)
                self.assertEqual(1, completed.returncode)
                self.assertEqual("UNVERIFIED", rows[0]["status"])
                self.assertNotIn("Traceback", completed.stderr)

    def test_reported_numeric_overflow_is_unverified(self) -> None:
        completed, rows, _, _ = self.verify_value('{"value":1}', "1e999")
        self.assertEqual(1, completed.returncode)
        self.assertEqual("UNVERIFIED", rows[0]["status"])

    def test_run_count_is_explicit_and_positive(self) -> None:
        for run_count in ("", "0", "-1", "1.5"):
            with self.subTest(run_count=run_count):
                completed, rows, _, _ = self.verify_value('{"value":0.9}', "0.9", run_count=run_count)
                self.assertEqual(1, completed.returncode)
                self.assertEqual("UNVERIFIED", rows[0]["status"])

    def test_supported_aggregates_are_recomputed_from_run_values(self) -> None:
        cases = (
            ("mean", "[0.1,0.2,0.3]", "3", "0.2"),
            ("median", "[4,1,2,3]", "4", "2.5"),
            ("max", "[0.1,0.2,0.3]", "3", "0.3"),
            ("minimum", "[0.1,0.2,0.3]", "3", "0.1"),
            ("mean", "[1e308,1e308]", "2", "1e308"),
        )
        for aggregation, values, count, reported in cases:
            with self.subTest(aggregation=aggregation, values=values):
                completed, rows, _, _ = self.verify_value(
                    '{"value":' + values + '}', reported,
                    aggregation=aggregation, run_count=count, selection_policy="predeclared extrema",
                )
                self.assertEqual(0, completed.returncode, completed.stderr)
                self.assertEqual("VERIFIED", rows[0]["status"])

    def test_wrong_reported_aggregate_is_mismatch(self) -> None:
        completed, rows, _, _ = self.verify_value(
            '{"value":[0.2,0.4]}', "0.5", aggregation="mean", run_count="2",
        )
        self.assertEqual(1, completed.returncode)
        self.assertEqual("MISMATCH", rows[0]["status"])
        self.assertAlmostEqual(0.3, float(rows[0]["observed_value"]))

    def test_aggregation_cannot_be_verified_from_a_summary_scalar(self) -> None:
        completed, rows, _, _ = self.verify_value(
            '{"value":0.9}', "0.9", aggregation="mean", run_count="3",
        )
        self.assertEqual(1, completed.returncode)
        self.assertEqual("UNVERIFIED", rows[0]["status"])

    def test_aggregate_requires_all_declared_runs(self) -> None:
        completed, rows, _, _ = self.verify_value(
            '{"value":[0.2,0.4]}', "0.3", aggregation="mean", run_count="3",
        )
        self.assertEqual(1, completed.returncode)
        self.assertEqual("UNVERIFIED", rows[0]["status"])

    def test_single_does_not_verify_a_multiple_run_summary(self) -> None:
        completed, rows, _, _ = self.verify_value('{"value":0.9}', "0.9", run_count="3")
        self.assertEqual(1, completed.returncode)
        self.assertEqual("UNVERIFIED", rows[0]["status"])

    def test_unsupported_aggregation_is_unverified_even_if_values_match(self) -> None:
        for aggregation in ("", "custom-weighted-mean", "best"):
            with self.subTest(aggregation=aggregation):
                completed, rows, _, _ = self.verify_value(
                    '{"value":0.9}', "0.9", aggregation=aggregation,
                    selection_policy="declared but not machine-verifiable",
                )
                self.assertEqual(1, completed.returncode)
                self.assertEqual("UNVERIFIED", rows[0]["status"])

    def test_empty_json_path_is_unverified(self) -> None:
        completed, rows, _, _ = self.verify_value(
            '{"value":{"accuracy":0.9}}', '{"value":{"accuracy":0.9}}', json_path="",
        )
        self.assertEqual(1, completed.returncode)
        self.assertEqual("UNVERIFIED", rows[0]["status"])

    def test_missing_claim_identity_is_unverified(self) -> None:
        for field in ("claim_id", "artifact"):
            with self.subTest(field=field):
                completed, rows, _, _ = self.verify_value(
                    '{"value":0.9}', "0.9", **{field: ""},
                )
                self.assertEqual(1, completed.returncode)
                self.assertEqual("UNVERIFIED", rows[0]["status"])

    def test_null_result_values_are_unverified(self) -> None:
        completed, rows, _, _ = self.verify_value('{"value":null}', "null")
        self.assertEqual(1, completed.returncode)
        self.assertEqual("UNVERIFIED", rows[0]["status"])

    def test_aggregates_reject_nonnumeric_run_values(self) -> None:
        for values in ('[true,1]', '["0.2",0.4]', '[null,0.4]'):
            with self.subTest(values=values):
                completed, rows, _, _ = self.verify_value(
                    '{"value":' + values + '}', "0.3", aggregation="mean", run_count="2",
                )
                self.assertEqual(1, completed.returncode)
                self.assertEqual("UNVERIFIED", rows[0]["status"])

    def test_not_applicable_is_not_a_disclosed_selection_policy(self) -> None:
        completed, rows, _, _ = self.verify_value(
            '{"value":0.9}', "0.9", aggregation="max", run_count="3",
            selection_policy="not-applicable",
        )
        self.assertEqual(1, completed.returncode)
        self.assertEqual("UNDISCLOSED_SELECTION_RISK", rows[0]["risk_flag"])


if __name__ == "__main__":
    unittest.main()
