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
SCRIPT = (
    ROOT
    / "research-experiment-design"
    / "scripts"
    / "design_experiment.py"
)
FIXTURES = ROOT / "tests" / "fixtures" / "experiment-design"


def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = deep_merge(merged[key], value)
        else:
            merged[key] = deepcopy(value)
    return merged


def run_design(fixture: str) -> tuple[subprocess.CompletedProcess[str], dict[str, Any], Path, tempfile.TemporaryDirectory[str]]:
    base = json.loads((FIXTURES / "controlled-sklearn.json").read_text(encoding="utf-8"))
    if fixture == "controlled-sklearn":
        spec = base
    elif fixture == "recommender-temporal":
        spec = json.loads((FIXTURES / "recommender-temporal.json").read_text(encoding="utf-8"))
    else:
        override = json.loads((FIXTURES / f"{fixture}.json").read_text(encoding="utf-8"))
        spec = deep_merge(base, override)

    temporary = tempfile.TemporaryDirectory()
    root = Path(temporary.name)
    spec_path = root / "spec.json"
    spec_path.write_text(json.dumps(spec), encoding="utf-8")
    output = root / "output"
    completed = subprocess.run(
        ["python3", str(SCRIPT), "--spec", str(spec_path), "--output-dir", str(output)],
        text=True,
        capture_output=True,
        check=False,
    )
    summary = json.loads(completed.stdout) if completed.stdout.strip().startswith("{") else {}
    return completed, summary, output, temporary


class ExperimentDesignTests(unittest.TestCase):
    def run_spec(self, spec: dict[str, Any], raw_json: str | None = None) -> tuple[subprocess.CompletedProcess[str], dict[str, Any], Path]:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        spec_path = root / "spec.json"
        spec_path.write_text(raw_json if raw_json is not None else json.dumps(spec), encoding="utf-8")
        output = root / "output"
        completed = subprocess.run(
            ["python3", str(SCRIPT), "--spec", str(spec_path), "--output-dir", str(output)],
            text=True, capture_output=True, check=False,
        )
        summary = json.loads(completed.stdout) if completed.stdout.strip().startswith("{") else {}
        return completed, summary, output

    def assert_invalid_spec(self, spec: dict[str, Any], raw_json: str | None = None) -> None:
        completed, summary, output = self.run_spec(spec, raw_json)
        self.assertEqual(2, completed.returncode, completed.stdout + completed.stderr)
        self.assertEqual("INVALID_SPEC", summary.get("status"))
        self.assertNotIn("Traceback", completed.stderr)
        self.assertFalse(output.exists(), "invalid input must not generate planning artifacts")

    def test_empty_or_incomplete_plans_cannot_be_execution_ready(self) -> None:
        self.assert_invalid_spec({})
        for field in ("research_question", "hypothesis", "falsification_condition", "claim_target", "stopping_rule"):
            spec = json.loads((FIXTURES / "controlled-sklearn.json").read_text(encoding="utf-8"))
            spec[field] = "  "
            with self.subTest(field=field):
                self.assert_invalid_spec(spec)
        for section, field in (("dataset", "name"), ("split", "method"), ("proposed_method", "name"), ("randomness", "seeds"), ("metrics", "primary")):
            spec = json.loads((FIXTURES / "controlled-sklearn.json").read_text(encoding="utf-8"))
            del spec[section][field]
            with self.subTest(section=section, field=field):
                self.assert_invalid_spec(spec)

    def test_explicit_null_sections_cannot_be_silently_defaulted(self) -> None:
        for section in ("dataset", "split", "baseline", "proposed_method", "randomness", "metrics", "compute", "variables", "statistical_plan", "ablation"):
            spec = json.loads((FIXTURES / "controlled-sklearn.json").read_text(encoding="utf-8"))
            spec[section] = None
            with self.subTest(section=section):
                self.assert_invalid_spec(spec)
        spec = json.loads((FIXTURES / "controlled-sklearn.json").read_text(encoding="utf-8"))
        spec["baseline"]["primary"] = None
        self.assert_invalid_spec(spec)

    def test_huge_compute_values_fail_cleanly_without_overflow(self) -> None:
        for field in ("number_of_runs", "per_run_hours"):
            spec = json.loads((FIXTURES / "controlled-sklearn.json").read_text(encoding="utf-8"))
            spec["compute"][field] = 10 ** 400
            with self.subTest(field=field):
                self.assert_invalid_spec(spec)

    def test_nonfinite_json_is_rejected_even_outside_compute(self) -> None:
        spec = json.loads((FIXTURES / "controlled-sklearn.json").read_text(encoding="utf-8"))
        for token in ("NaN", "Infinity", "-Infinity", "1e400"):
            raw = json.dumps(spec)[:-1] + ', "extra": {"estimate": ' + token + "}}"
            with self.subTest(token=token):
                self.assert_invalid_spec(spec, raw)

    def test_boolean_flags_require_json_booleans(self) -> None:
        for field in ("test_used_for_hyperparameters", "time_order_preserved"):
            for value in ("false", [], 0):
                spec = json.loads((FIXTURES / "controlled-sklearn.json").read_text(encoding="utf-8"))
                spec["split"][field] = value
                with self.subTest(field=field, value=value):
                    self.assert_invalid_spec(spec)

    def test_seed_and_metric_lists_are_checked_before_matrix_generation(self) -> None:
        cases = (
            ("randomness", "seeds", []), ("randomness", "seeds", 42),
            ("randomness", "seeds", [True]), ("randomness", "seeds", [42, 42]),
            ("randomness", "seeds", [1.5]), ("metrics", "primary", []),
            ("metrics", "primary", {"name": "accuracy"}),
            ("metrics", "primary", [True]), ("metrics", "primary", [{}]),
            ("variables", "controlled", "dataset"),
        )
        for section, field, value in cases:
            spec = json.loads((FIXTURES / "controlled-sklearn.json").read_text(encoding="utf-8"))
            spec[section][field] = value
            with self.subTest(section=section, field=field, value=value):
                self.assert_invalid_spec(spec)

    def test_declared_repetitions_match_the_seed_list(self) -> None:
        spec = json.loads((FIXTURES / "controlled-sklearn.json").read_text(encoding="utf-8"))
        spec["randomness"]["number_of_runs"] = 2
        self.assert_invalid_spec(spec)

    def test_randomness_run_count_is_required(self) -> None:
        spec = json.loads((FIXTURES / "controlled-sklearn.json").read_text(encoding="utf-8"))
        del spec["randomness"]["number_of_runs"]
        self.assert_invalid_spec(spec)

    def test_experiment_class_and_statistics_are_explicit(self) -> None:
        for experiment_class in ("", "UNKNOWN", 1, True):
            spec = json.loads((FIXTURES / "controlled-sklearn.json").read_text(encoding="utf-8"))
            spec["experiment_class"] = experiment_class
            with self.subTest(experiment_class=experiment_class):
                self.assert_invalid_spec(spec)
        for field, value in (("summary", []), ("effect_size", ""), ("confidence_interval", "")):
            spec = json.loads((FIXTURES / "controlled-sklearn.json").read_text(encoding="utf-8"))
            spec["statistical_plan"][field] = value
            with self.subTest(field=field):
                self.assert_invalid_spec(spec)

    def test_compute_cannot_budget_fewer_runs_than_generated_matrix(self) -> None:
        spec = json.loads((FIXTURES / "controlled-sklearn.json").read_text(encoding="utf-8"))
        spec["compute"]["number_of_runs"] = 1
        completed, summary, output = self.run_spec(spec)
        self.assertEqual(1, completed.returncode, completed.stderr)
        self.assertIn("COMPUTE_BUDGET_RISK", summary["blocking_risks"])
        with (output / "experiment-matrix.csv").open(encoding="utf-8", newline="") as handle:
            self.assertEqual(10, len(list(csv.DictReader(handle))))

    def test_declared_single_fit_baseline_runs_once(self) -> None:
        spec = json.loads((FIXTURES / "recommender-temporal.json").read_text(encoding="utf-8"))
        completed, summary, output = self.run_spec(spec)
        self.assertEqual(0, completed.returncode, completed.stderr)
        self.assertEqual("READY_FOR_EXECUTION", summary["status"])
        with (output / "experiment-matrix.csv").open(encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
        self.assertEqual(4, len(rows))
        self.assertEqual(1, sum(row["baseline"] == "True" for row in rows))

    def test_malformed_sections_return_structured_invalid_spec(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        spec_path = root / "spec.json"
        spec_path.write_text(json.dumps({"dataset": []}), encoding="utf-8")
        completed = subprocess.run(
            ["python3", str(SCRIPT), "--spec", str(spec_path), "--output-dir", str(root / "output")],
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(2, completed.returncode)
        self.assertEqual({"status", "errors"}, set(json.loads(completed.stdout)))
        self.assertIn("dataset must be an object", json.loads(completed.stdout)["errors"])
        self.assertNotIn("Traceback", completed.stderr)

    def test_non_numeric_compute_budget_returns_structured_invalid_spec(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        spec = json.loads((FIXTURES / "controlled-sklearn.json").read_text(encoding="utf-8"))
        spec["compute"]["per_run_hours"] = "unknown"
        spec_path = root / "spec.json"
        spec_path.write_text(json.dumps(spec), encoding="utf-8")
        completed = subprocess.run(
            ["python3", str(SCRIPT), "--spec", str(spec_path), "--output-dir", str(root / "output")],
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(2, completed.returncode)
        self.assertIn("compute.per_run_hours must be numeric", json.loads(completed.stdout)["errors"])

    def test_invalid_compute_values_are_rejected(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        spec = json.loads((FIXTURES / "controlled-sklearn.json").read_text(encoding="utf-8"))
        spec["compute"]["number_of_runs"] = "NaN"
        spec_path = root / "spec.json"
        spec_path.write_text(json.dumps(spec), encoding="utf-8")
        completed = subprocess.run(
            ["python3", str(SCRIPT), "--spec", str(spec_path), "--output-dir", str(root / "output")],
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(2, completed.returncode)
        self.assertIn("compute.number_of_runs must be a finite non-negative number", json.loads(completed.stdout)["errors"])

    def test_controlled_sklearn_plan_generates_required_outputs(self) -> None:
        completed, summary, output, temporary = run_design("controlled-sklearn")
        self.addCleanup(temporary.cleanup)
        self.assertEqual(0, completed.returncode, completed.stderr)
        self.assertEqual("READY_FOR_EXECUTION", summary["status"])
        self.assertEqual([], summary["blocking_risks"])
        required = (
            "experiment-plan.md",
            "experiment-matrix.csv",
            "risk-register.md",
            "run-schema.json",
        )
        self.assertTrue(all((output / name).is_file() for name in required))
        self.assertFalse((output / "ablation-matrix.csv").exists())
        with (output / "experiment-matrix.csv").open(encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
        self.assertEqual(10, len(rows))
        self.assertEqual({"CONFIRMATORY"}, {row["status"] for row in rows})
        self.assertEqual({"42", "43", "44", "45", "46"}, {row["seed"] for row in rows})

    def test_recommender_plan_preserves_temporal_semantics(self) -> None:
        completed, summary, output, temporary = run_design("recommender-temporal")
        self.addCleanup(temporary.cleanup)
        self.assertEqual(0, completed.returncode, completed.stderr)
        self.assertEqual([], summary["blocking_risks"])
        plan = (output / "experiment-plan.md").read_text(encoding="utf-8")
        self.assertIn("temporal", plan.lower())
        self.assertIn("Recall@10", plan)
        self.assertIn("NDCG@10", plan)

    def test_multiple_components_generate_one_at_a_time_ablation(self) -> None:
        completed, summary, output, temporary = run_design("with-ablation")
        self.addCleanup(temporary.cleanup)
        self.assertEqual(0, completed.returncode, completed.stderr)
        self.assertEqual([], summary["blocking_risks"])
        with (output / "ablation-matrix.csv").open(encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
        variants = {row["variant"] for row in rows}
        self.assertEqual(
            {"full-model", "without-mixed-batch-sampler", "without-occlusion-consistency"},
            variants,
        )

    def test_negative_design_fixtures_detect_required_risks(self) -> None:
        cases = (
            ("unfair-comparison", "UNFAIR_COMPARISON"),
            ("confounded-experiment", "CONFOUNDED_EXPERIMENT"),
            ("test-set-tuning", "TEST_SET_TUNING"),
            ("best-seed-selection", "SELECTION_BIAS_RISK"),
            ("split-mismatch", "SPLIT_MISMATCH_RISK"),
            ("compute-budget", "COMPUTE_BUDGET_RISK"),
        )
        for fixture, expected in cases:
            with self.subTest(fixture=fixture):
                completed, summary, output, temporary = run_design(fixture)
                self.addCleanup(temporary.cleanup)
                self.assertEqual(1, completed.returncode)
                self.assertIn(expected, summary["blocking_risks"])
                register = (output / "risk-register.md").read_text(encoding="utf-8")
                self.assertIn(expected, register)


if __name__ == "__main__":
    unittest.main()
