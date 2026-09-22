from __future__ import annotations

import re
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILL_NAMES = (
    "research-experiment-design",
    "research-literature-review",
    "research-paper-audit",
    "research-reproducibility",
    "research-result-verification",
)
SKILLS = tuple(ROOT / name for name in SKILL_NAMES)


class PortabilityTests(unittest.TestCase):
    def test_root_delivery_files_exist(self) -> None:
        for name in ("README.md", "WINDOWS_WSL_MIGRATION.md", ".gitignore", ".gitattributes"):
            with self.subTest(name=name):
                self.assertTrue((ROOT / name).is_file(), f"missing {name}")

    def test_skill_command_examples_use_python3(self) -> None:
        for skill in SKILLS:
            text = (skill / "SKILL.md").read_text(encoding="utf-8")
            with self.subTest(skill=skill.name):
                self.assertIsNone(
                    re.search(r"(?m)^python(?:\s|$)", text),
                    "WSL may not provide a python alias; use python3",
                )

    def test_each_skill_documents_portable_execution(self) -> None:
        for skill in SKILLS:
            text = (skill / "SKILL.md").read_text(encoding="utf-8")
            with self.subTest(skill=skill.name):
                self.assertIn("## Portable execution", text)
                self.assertIn("Python 3.10+", text)
                self.assertIn("directory containing this `SKILL.md`", text)

    def test_paper_audit_labels_agent_specific_policy(self) -> None:
        text = (ROOT / "research-paper-audit" / "SKILL.md").read_text(encoding="utf-8")
        for label in ("Portable", "Codex only", "OpenCode only", "Claude Code policy"):
            with self.subTest(label=label):
                self.assertIn(label, text)

    def test_relative_markdown_links_resolve(self) -> None:
        link_pattern = re.compile(r"\[[^]]+\]\(([^)]+)\)")
        for skill in SKILLS:
            for document in skill.rglob("*.md"):
                for target in link_pattern.findall(document.read_text(encoding="utf-8")):
                    if target.startswith(("http://", "https://", "#")):
                        continue
                    with self.subTest(document=document, target=target):
                        self.assertTrue((document.parent / target).exists())

    def test_tree_has_no_machine_specific_paths_or_macos_commands(self) -> None:
        forbidden = (
            b"/Users/",
            b"/Applications/",
            b"/opt/homebrew/",
            b"chenankang",
            b"pbcopy",
            b"pbpaste",
            b"osascript",
            b"launchctl",
            b"mdfind",
        )
        for path in ROOT.rglob("*"):
            if not path.is_file() or ".git" in path.parts or "tests" in path.parts:
                continue
            data = path.read_bytes()
            for token in forbidden:
                with self.subTest(path=path, token=token):
                    self.assertNotIn(token, data)

    def test_text_files_use_lf_without_bom(self) -> None:
        suffixes = {".md", ".py", ".csv", ".json"}
        for path in ROOT.rglob("*"):
            if not path.is_file() or ".git" in path.parts or path.suffix not in suffixes:
                continue
            data = path.read_bytes()
            with self.subTest(path=path):
                self.assertNotIn(b"\r\n", data)
                self.assertFalse(data.startswith(b"\xef\xbb\xbf"))
                data.decode("utf-8")

    def test_git_tracked_tree_contains_no_caches_or_symlinks(self) -> None:
        tracked = subprocess.run(
            ["git", "ls-files", "-z"],
            cwd=ROOT,
            check=True,
            capture_output=True,
        ).stdout.split(b"\0")
        for relative_path in tracked:
            if not relative_path:
                continue
            path = ROOT / os.fsdecode(relative_path)
            with self.subTest(path=path):
                self.assertNotEqual("__pycache__", path.name)
                self.assertNotEqual(".DS_Store", path.name)
                self.assertNotEqual(".pyc", path.suffix)
                self.assertFalse(path.is_symlink())

    def test_all_clis_run_from_an_unrelated_working_directory(self) -> None:
        scripts = tuple(skill / "scripts" for skill in SKILLS)
        with tempfile.TemporaryDirectory() as temporary:
            for scripts_dir in scripts:
                for script in scripts_dir.glob("*.py"):
                    completed = subprocess.run(
                        [sys.executable, str(script), "--help"],
                        cwd=temporary,
                        text=True,
                        capture_output=True,
                        check=False,
                    )
                    with self.subTest(script=script):
                        self.assertEqual(0, completed.returncode, completed.stderr)
                        self.assertIn("usage:", completed.stdout)

    def test_link_verifier_rejects_misdirected_links_and_accepts_master(self) -> None:
        verifier = ROOT / "scripts" / "verify-install-links.sh"
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary)
            master = home / "agent-skills"
            wrong = home / "wrong-master"
            agents = home / ".agents" / "skills"
            claude = home / ".claude" / "skills"
            agents.mkdir(parents=True)
            claude.mkdir(parents=True)
            for skill_name in SKILL_NAMES:
                (master / skill_name).mkdir(parents=True)
                (master / skill_name / "SKILL.md").write_text("---\n", encoding="utf-8")
                (wrong / skill_name).mkdir(parents=True)
                os.symlink(master / skill_name, agents / skill_name)
                os.symlink(master / skill_name, claude / skill_name)

            (agents / SKILL_NAMES[0]).unlink()
            os.symlink(wrong / SKILL_NAMES[0], agents / SKILL_NAMES[0])
            rejected = subprocess.run(
                ["bash", str(verifier), str(master)],
                env={**os.environ, "HOME": str(home)},
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertNotEqual(0, rejected.returncode)
            self.assertIn("wrong target", rejected.stderr)

            (agents / SKILL_NAMES[0]).unlink()
            missing = subprocess.run(
                ["bash", str(verifier), str(master)],
                env={**os.environ, "HOME": str(home)},
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertNotEqual(0, missing.returncode)
            self.assertIn("missing symlink", missing.stderr)

            (agents / SKILL_NAMES[0]).mkdir()
            ordinary_directory = subprocess.run(
                ["bash", str(verifier), str(master)],
                env={**os.environ, "HOME": str(home)},
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertNotEqual(0, ordinary_directory.returncode)
            self.assertIn("not a symlink", ordinary_directory.stderr)

            (agents / SKILL_NAMES[0]).rmdir()
            os.symlink(master / SKILL_NAMES[0], agents / SKILL_NAMES[0])
            accepted = subprocess.run(
                ["bash", str(verifier), str(master)],
                env={**os.environ, "HOME": str(home)},
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(0, accepted.returncode, accepted.stderr)
            self.assertIn("verified 10 links", accepted.stdout)


if __name__ == "__main__":
    unittest.main()
