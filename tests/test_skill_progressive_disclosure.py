"""SKILL.md entrypoint 的 progressive-disclosure contract。

修改紀錄（2026-08-17，Steve Peng）
原始內容：SKILL.md 將雙語說明與 operational details 混在 entrypoint。
修改原因：Phase 5R 要求把詳細 registry/discovery/routing/i18n 規格移到 references。
修改後功能：以 executable assertion 固定 entrypoint 精簡且 references 可追蹤。
"""

from __future__ import annotations

from pathlib import Path
import unittest


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


class SkillProgressiveDisclosureTests(unittest.TestCase):
    """防止技能入口重新膨脹或失去詳細規格連結。"""

    def test_skill_entrypoint_is_bounded_and_links_reference_contracts(self) -> None:
        """Name the break: oversized entrypoint increases deferred token cost and hides references."""

        content = (REPOSITORY_ROOT / "SKILL.md").read_text(encoding="utf-8")
        words = [word for word in content.split() if word]

        self.assertLessEqual(len(words), 180)
        for relative_path in (
            "references/discovery-and-provenance.md",
            "references/routing-policy.md",
            "references/i18n-policy.md",
        ):
            self.assertIn(relative_path, content)
            self.assertTrue((REPOSITORY_ROOT / relative_path).is_file())

    def test_skill_entrypoint_states_v02_coverage_boundary(self) -> None:
        """入口契約必須引導 coverage-first，但仍保留 availability hard gate。"""

        content = (REPOSITORY_ROOT / "SKILL.md").read_text(encoding="utf-8")
        for phrase in (
            "recalled",
            "non-redundant",
            "Coverage Check",
            "distinct_value",
            "trusted",
            "unknown profiles are diagnostics only",
        ):
            self.assertIn(phrase, content)


if __name__ == "__main__":
    unittest.main()
