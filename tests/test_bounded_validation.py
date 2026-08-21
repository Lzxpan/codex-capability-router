"""Phase 4 canonical fixture 的 bounded contract validation。"""

from __future__ import annotations

import json
from pathlib import Path
import unittest

from codex_capability_router.selection import validate_selection


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_PATH = REPOSITORY_ROOT / "tests" / "fixtures" / "routing_scenarios.json"


class BoundedValidationTests(unittest.TestCase):
    """只驗證 12 個 fixture 的邊界與新版 schema，不模擬 Codex final semantics。"""

    @classmethod
    def setUpClass(cls) -> None:
        """載入唯一 canonical scenario fixture。"""

        cls.scenarios = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))

    def test_canonical_fixture_has_exactly_six_scenarios_per_language(self) -> None:
        """canonical fixture 必須維持 6 個 zh-TW 與 6 個 en。"""

        self.assertIsInstance(self.scenarios, list)
        self.assertEqual(len(self.scenarios), 12)
        self.assertEqual(sum(item["language"] == "zh-TW" for item in self.scenarios), 6)
        self.assertEqual(sum(item["language"] == "en" for item in self.scenarios), 6)

    def test_all_scenarios_are_bounded_and_schema_deterministic(self) -> None:
        """fixture task 可進 bounded schema，重複驗證結果必須一致。"""

        for scenario in self.scenarios:
            with self.subTest(scenario=scenario["id"]):
                payload = {
                    "task_summary": scenario["task"],
                    "selected_skills": [],
                    "selection_status": "no_matching_skill",
                }
                self.assertEqual(validate_selection(payload), validate_selection(payload))
                self.assertLessEqual(len(scenario["task"]), 2048)
                self.assertTrue(scenario["category"])

    def test_fixture_does_not_define_final_skill_ids(self) -> None:
        """canonical scenarios 只提供 task/category，不建立 keyword 到 Skill ID mapping。"""

        for scenario in self.scenarios:
            self.assertNotIn("skill_id", scenario)
            self.assertNotIn("selected_skills", scenario)


if __name__ == "__main__":
    unittest.main()
