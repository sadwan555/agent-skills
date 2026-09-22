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
SCRIPT = ROOT / "research-literature-review" / "scripts" / "audit_literature.py"
FIXTURES = ROOT / "tests" / "fixtures" / "literature-review"


def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = deep_merge(merged[key], value)
        else:
            merged[key] = deepcopy(value)
    return merged


def run_audit(fixture: str | dict[str, Any]) -> tuple[subprocess.CompletedProcess[str], dict[str, Any], Path, tempfile.TemporaryDirectory[str]]:
    base = json.loads((FIXTURES / "valid-review.json").read_text(encoding="utf-8"))
    if isinstance(fixture, dict):
        specification = fixture
    elif fixture == "valid-review":
        specification = base
    else:
        override = json.loads((FIXTURES / f"{fixture}.json").read_text(encoding="utf-8"))
        specification = deep_merge(base, override)

    temporary = tempfile.TemporaryDirectory()
    root = Path(temporary.name)
    input_path = root / "review.json"
    input_path.write_text(json.dumps(specification), encoding="utf-8")
    output = root / "output"
    completed = subprocess.run(
        ["python3", str(SCRIPT), "--input", str(input_path), "--output-dir", str(output)],
        text=True,
        capture_output=True,
        check=False,
    )
    summary = json.loads(completed.stdout) if completed.stdout.strip().startswith("{") else {}
    return completed, summary, output, temporary


class LiteratureReviewTests(unittest.TestCase):
    def test_empty_or_unscreened_evidence_cannot_be_ready_for_synthesis(self) -> None:
        base = json.loads((FIXTURES / "valid-review.json").read_text(encoding="utf-8"))
        pending = deepcopy(base)
        for paper in pending["papers"]:
            paper["screening_status"] = "PENDING"
        for specification in ({}, {"papers": []}, pending):
            with self.subTest(specification=specification):
                completed, summary, _, temporary = run_audit(specification)
                self.addCleanup(temporary.cleanup)
                self.assertEqual(1, completed.returncode, completed.stderr)
                self.assertIn("INSUFFICIENT_EVIDENCE", summary["blocking_risks"])
                self.assertNotEqual("READY_FOR_SYNTHESIS", summary["status"])

    def test_included_paper_without_reading_evidence_is_not_ready(self) -> None:
        specification = json.loads((FIXTURES / "valid-review.json").read_text(encoding="utf-8"))
        specification["papers"][0]["evidence_statements"] = []
        completed, summary, _, temporary = run_audit(specification)
        self.addCleanup(temporary.cleanup)
        self.assertEqual(1, completed.returncode, completed.stderr)
        self.assertIn("INSUFFICIENT_EVIDENCE", summary["blocking_risks"])

    def test_malformed_nested_records_are_invalid_instead_of_silently_dropped(self) -> None:
        for specification, path in (
            ({"papers": {}}, "papers"),
            ({"papers": [None]}, "papers[0]"),
            ({"review": {"scope": []}}, "review.scope"),
            ({"papers": [{"evidence_statements": ["unsupported"]}]}, "papers[0].evidence_statements[0]"),
        ):
            with self.subTest(path=path):
                completed, summary, output, temporary = run_audit(specification)
                self.addCleanup(temporary.cleanup)
                self.assertEqual(2, completed.returncode, completed.stderr)
                self.assertEqual("INVALID_INPUT", summary["status"])
                self.assertIn(path, summary["error"])
                self.assertNotIn("Traceback", completed.stderr)
                self.assertFalse(output.exists())

    def test_valid_review_generates_traceable_evidence_base(self) -> None:
        completed, summary, output, temporary = run_audit("valid-review")
        self.addCleanup(temporary.cleanup)
        self.assertEqual(0, completed.returncode, completed.stderr)
        self.assertEqual("READY_FOR_SYNTHESIS", summary["status"])
        self.assertEqual([], summary["blocking_risks"])
        for name in ("search-log.md", "literature-matrix.csv", "review-notes.md", "evidence-gaps.md"):
            self.assertTrue((output / name).is_file(), name)

        search_log = (output / "search-log.md").read_text(encoding="utf-8")
        for value in ("DBLP", "2026-09-16", "continual learning recommender systems", "publication year: 2020-2026"):
            self.assertIn(value, search_log)

        with (output / "literature-matrix.csv").open(encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
        self.assertEqual(2, len(rows))
        self.assertEqual({"INCLUDED"}, {row["screening_status"] for row in rows})
        self.assertEqual({"VERIFIED"}, {row["metadata_status"] for row in rows})
        self.assertEqual({"FOUNDATIONAL", "RECENT"}, {row["literature_role"] for row in rows})
        notes = (output / "review-notes.md").read_text(encoding="utf-8")
        self.assertIn("Proposed contribution", notes)
        self.assertIn("Ablations", notes)

    def test_query_strategy_covers_required_variant_types(self) -> None:
        completed, _, output, temporary = run_audit("valid-review")
        self.addCleanup(temporary.cleanup)
        self.assertEqual(0, completed.returncode, completed.stderr)
        log = (output / "search-log.md").read_text(encoding="utf-8")
        for category in ("EXACT_TERMINOLOGY", "SYNONYM", "HISTORICAL_TERMINOLOGY", "ACRONYM_FULL_NAME", "BROADER_METHOD_FAMILY", "TASK_SPECIFIC"):
            self.assertIn(category, log)

    def test_negative_evidence_fixtures_raise_required_risks(self) -> None:
        cases = (
            ("fictitious-doi", "UNVERIFIED_METADATA"),
            ("abstract-overreach", "INSUFFICIENT_EVIDENCE"),
            ("duplicate-version", "DUPLICATE_VERSION"),
            ("outcome-biased-screening", "SCREENING_BIAS_RISK"),
            ("unsupported-novelty", "UNSUPPORTED_NOVELTY_CLAIM"),
            ("blog-only", "SECONDARY_SOURCE_ONLY"),
        )
        for fixture, expected in cases:
            with self.subTest(fixture=fixture):
                completed, summary, output, temporary = run_audit(fixture)
                self.addCleanup(temporary.cleanup)
                self.assertEqual(1, completed.returncode)
                self.assertIn(expected, summary["blocking_risks"])
                combined = "\n".join(
                    path.read_text(encoding="utf-8", errors="replace")
                    for path in output.iterdir()
                    if path.is_file()
                )
                self.assertIn(expected, combined)

    def test_duplicate_versions_are_not_counted_as_independent_evidence(self) -> None:
        completed, _, output, temporary = run_audit("duplicate-version")
        self.addCleanup(temporary.cleanup)
        self.assertEqual(1, completed.returncode)
        with (output / "literature-matrix.csv").open(encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
        same_work = [row for row in rows if row["work_id"] == "work-delta"]
        self.assertEqual(2, len(same_work))
        self.assertIn("DUPLICATE", {row["screening_status"] for row in same_work})
        self.assertTrue(all(row["version_relationship"] for row in same_work))


if __name__ == "__main__":
    unittest.main()
