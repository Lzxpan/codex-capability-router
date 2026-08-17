"""Phase 5R canonical routing fixture 的最小 bounded validation。

修改紀錄（2026-08-17，Steve Peng）
原始內容：repository 沒有獨立 bounded validation test。
修改原因：固定 canonical 12-scenario fixture、選擇上限與 unsafe status assertions。
修改後功能：直接讀取 routing_scenarios.json，驗證數量、語言、determinism 與安全排除。
"""

from __future__ import annotations

import json
from pathlib import Path
import unittest

from codex_capability_router.models import CapabilityStatus, RouterInput
from codex_capability_router.routing import route
from codex_capability_router.validation import record_from_mapping


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_PATH = REPOSITORY_ROOT / "tests" / "fixtures" / "routing_scenarios.json"
REGISTRY_PATH = REPOSITORY_ROOT / "tests" / "fixtures" / "routing_registry.json"


class BoundedValidationTests(unittest.TestCase):
    """先固定唯一 12-scenario source of truth，再擴充 runtime assertions。"""

    def test_canonical_fixture_has_exactly_six_scenarios_per_language(self) -> None:
        """Name the break: 缺少 canonical fixture 或 locale 數量錯誤會放寬 benchmark 邊界。"""

        self.assertTrue(FIXTURE_PATH.is_file(), "canonical routing scenario fixture is required")
        scenarios = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))

        self.assertIsInstance(scenarios, list)
        self.assertEqual(len(scenarios), 12)
        self.assertEqual(sum(item["language"] == "zh-TW" for item in scenarios), 6)
        self.assertEqual(sum(item["language"] == "en" for item in scenarios), 6)

    def test_all_scenarios_are_bounded_and_deterministic(self) -> None:
        """Name the break: routing may exceed limits or vary for identical fixture input."""

        registry = tuple(
            record_from_mapping(item)
            for item in json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
        )
        scenarios = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))

        for scenario in scenarios:
            with self.subTest(scenario=scenario["id"]):
                request = RouterInput(scenario["task"], registry, scenario["language"])
                first = route(request)
                second = route(request)
                self.assertLessEqual(len(first.selected_primary), 3)
                self.assertLessEqual(len(first.selected_optional), 2)
                self.assertNotIn(
                    "codex-capability-router",
                    {record.id for record in first.selected_primary + first.selected_optional},
                )
                self.assertEqual(first, second)

    def test_unavailable_and_unknown_capabilities_are_not_selected(self) -> None:
        """Name the break: status unknown must not be treated as optional availability."""

        registry = tuple(
            record_from_mapping(item)
            for item in json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
        )
        unknown = record_from_mapping(
            {
                "id": "unknown-firmware-helper",
                "name": "Unknown Firmware Helper",
                "kind": "tool",
                "status": "unknown",
                "categories": ["firmware debugging"],
                "triggers": ["firmware", "uart"],
                "priority": 100,
                "overlap_group": None,
                "preferred_for": ["firmware debugging"],
                "requires": [],
                "source": "manual:test",
                "last_verified": None,
            }
        )
        scenario = next(item for item in json.loads(FIXTURE_PATH.read_text(encoding="utf-8")) if item["id"] == "en-firmware-debugging")

        result = route(RouterInput(scenario["task"], registry + (unknown,), "en"))

        selected = result.selected_primary + result.selected_optional
        self.assertNotIn("offline-firmware-debugger", {record.id for record in selected})
        self.assertNotIn("unknown-firmware-helper", {record.id for record in selected})
        self.assertEqual(result.recommendation_only, ())
        self.assertIn(
            "unknown-firmware-helper",
            {candidate.id for candidate in result.rejected_candidates},
        )


if __name__ == "__main__":
    unittest.main()
