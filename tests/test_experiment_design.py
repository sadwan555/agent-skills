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
