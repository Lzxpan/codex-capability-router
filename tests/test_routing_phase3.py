"""Phase 4 migration tests for canonical scenarios and new selection schema。"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from codex_capability_router.selection import validate_selection


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_PATH = REPOSITORY_ROOT / "tests" / "fixtures" / "routing_scenarios.json"


def _load_scenarios() -> list[dict[str, str]]:
    """讀取唯一 canonical scenario fixture，不建立固定 Skill ID mapping。"""

    payload = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError("routing_scenarios.json must be an array")
    return payload


class Phase3RoutingScenarioTests(unittest.TestCase):
    """保留 fixture 數量與 bounded input，移除舊 final ranking assertions。"""

    @classmethod
    def setUpClass(cls) -> None:
        """載入 canonical scenarios。"""

        cls.scenarios = _load_scenarios()

    def test_exactly_six_bilingual_scenarios_remain_bounded(self) -> None:
        """canonical fixture 維持恰好 6 個 zh-TW 與 6 個 en。"""

        self.assertEqual(len(self.scenarios), 12)
        self.assertEqual(sum(item["language"] == "zh-TW" for item in self.scenarios), 6)
        self.assertEqual(sum(item["language"] == "en" for item in self.scenarios), 6)

    def test_scenarios_prepare_only_task_and_category_context(self) -> None:
        """scenario 可作 task understanding input，但不宣稱 Codex final selection。"""

        for scenario in self.scenarios:
            with self.subTest(scenario=scenario["id"]):
                self.assertTrue(scenario["task"].strip())
                self.assertTrue(scenario["category"].strip())
                self.assertNotIn("skill_id", scenario)
                self.assertNotIn("selected_skills", scenario)

    def test_no_matching_schema_is_deterministic_for_all_scenarios(self) -> None:
        """Python 只驗證合法 empty output，不模擬語意匹配結果。"""

        for scenario in self.scenarios:
            payload = {
                "task_summary": scenario["task"],
                "selected_skills": [],
                "selection_status": "no_matching_skill",
            }
            self.assertEqual(validate_selection(payload), payload)

    def test_new_schema_has_no_legacy_output_fields(self) -> None:
        """新版 output 不包含 PRIMARY/OPTIONAL、舊 outcome 或固定數量欄位。"""

        payload = {
            "task_summary": "bounded task",
            "selected_skills": [{"id": "fixture-skill", "reason": "Codex selected it."}],
            "selection_status": "selected",
        }
        validated = validate_selection(payload)
        for field in ("selected_primary", "selected_optional", "outcome", "selection_level"):
            self.assertNotIn(field, validated)


if __name__ == "__main__":
    unittest.main()
