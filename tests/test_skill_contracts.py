from __future__ import annotations

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILLS = (
    ROOT / "research-reproducibility",
    ROOT / "research-result-verification",
    ROOT / "research-experiment-design",
    ROOT / "research-literature-review",
    ROOT / "research-paper-audit",
)


def parse_frontmatter(path: Path) -> dict[str, str]:
    text = path.read_text(encoding="utf-8")
    match = re.match(r"\A---\n(.*?)\n---\n", text, flags=re.DOTALL)
    if not match:
        raise AssertionError(f"missing YAML frontmatter: {path}")
    fields: dict[str, str] = {}
    for line in match.group(1).splitlines():
        key, value = line.split(":", 1)
        fields[key.strip()] = value.strip()
    return fields


class SkillContractTests(unittest.TestCase):
    def test_shared_frontmatter_has_only_open_standard_fields(self) -> None:
        for skill in SKILLS:
            with self.subTest(skill=skill.name):
                fields = parse_frontmatter(skill / "SKILL.md")
                self.assertEqual({"name", "description"}, set(fields))
                self.assertEqual(skill.name, fields["name"])
                self.assertTrue(fields["description"].startswith("Use when"))

    def test_shared_core_has_no_platform_or_machine_specific_content(self) -> None:
        forbidden = (
            "allowed-tools:",
            "context:",
            "agent:",
            "disable-model-invocation:",
            "agents/openai.yaml",
            "provider routing",
            "model requirement",
            "/Users/",
            "chenankang",
            "!`",
        )
        for skill in SKILLS:
            for path in skill.rglob("*"):
                if not path.is_file():
                    continue
                text = path.read_text(encoding="utf-8", errors="ignore")
                for token in forbidden:
                    with self.subTest(skill=skill.name, path=path.name, token=token):
                        self.assertNotIn(token, text)

    def test_required_portable_directories_exist(self) -> None:
        for skill in SKILLS:
            with self.subTest(skill=skill.name):
                for name in ("references", "scripts", "assets"):
                    self.assertTrue((skill / name).is_dir(), f"missing {skill / name}")


if __name__ == "__main__":
    unittest.main()
