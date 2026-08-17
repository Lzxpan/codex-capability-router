"""Phase 3 固定十二個 fixture-registry routing scenarios。

修改紀錄（2026-08-17，Steve Peng）
原始內容：12 個 scenario 同時維護於 Python SCENARIOS 與 fixture registry 測試程式。
修改原因：Phase 5R 要求單一 canonical routing_scenarios.json，避免 benchmark source of truth 分叉。
修改日期：2026-08-17。
修改後功能：測試只從 routing_scenarios.json 載入既有 12 個場景，不新增或執行任何真實 capability。
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from codex_capability_router.models import CapabilityRecord, CapabilityStatus
from codex_capability_router.routing import RouterInput, route
from codex_capability_router.validation import record_from_mapping


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_PATH = REPOSITORY_ROOT / "tests" / "fixtures" / "routing_registry.json"



def _load_fixture_registry() -> tuple[CapabilityRecord, ...]:
    """讀取並驗證固定 fixture registry；不掃描路徑、不執行 capability。"""

    payload = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    return tuple(record_from_mapping(item) for item in payload)


def _load_scenarios() -> list[dict[str, str]]:
    """讀取唯一 canonical scenario fixture，避免 Python/JSON 雙重維護。"""

    payload = json.loads(
        (REPOSITORY_ROOT / "tests" / "fixtures" / "routing_scenarios.json").read_text(encoding="utf-8")
    )
    if not isinstance(payload, list):
        raise ValueError("routing_scenarios.json must be a JSON array")
    return payload


def _ids(records: tuple[CapabilityRecord, ...]) -> tuple[str, ...]:
    """將 immutable capability records 轉成穩定 id tuple 供測試比對。"""

    return tuple(record.id for record in records)


class Phase3RoutingScenarioTests(unittest.TestCase):
    """驗證恰好 12 個 routing scenarios 的共同安全與選擇邊界。"""

    @classmethod
    def setUpClass(cls) -> None:
        """一次載入 fixture registry，避免測試自行建立第二份 registry。"""

        cls.registry = _load_fixture_registry()
        cls.scenarios = _load_scenarios()

    def test_exactly_six_bilingual_scenarios_route_with_bounds_and_category(self) -> None:
        """六類任務各有中英文場景，且每個結果符合選擇上限與類別。"""

        self.assertEqual(len(self.scenarios), 12)
        self.assertEqual(sum(item["language"] == "zh-TW" for item in self.scenarios), 6)
        self.assertEqual(sum(item["language"] == "en" for item in self.scenarios), 6)
        self.assertEqual(
            {item["id"].removeprefix("zh-").removeprefix("en-") for item in self.scenarios},
            {
                "firmware-debugging",
                "react-ui-bug",
                "pr-code-review",
                "research-document-search",
                "spreadsheet-data-analysis",
                "ui-ux-design",
            },
        )

        for scenario in self.scenarios:
            with self.subTest(scenario=scenario["id"]):
                result = route(
                    RouterInput(
                        user_task=scenario["task"],
                        capability_registry=self.registry,
                        requested_output_language=scenario["language"],
                    )
                )
                selected = result.selected_primary + result.selected_optional
                self.assertLessEqual(len(result.selected_primary), 3)
                self.assertLessEqual(len(result.selected_optional), 2)
                self.assertTrue(selected, result.rationale)
                self.assertTrue(
                    any(scenario["category"] in record.categories for record in selected),
                    result.rationale,
                )
                self.assertNotIn("codex-capability-router", _ids(selected))
                self.assertNotIn(
                    CapabilityStatus.UNAVAILABLE,
                    tuple(record.status for record in result.selected_primary),
                )
                self.assertTrue(result.rationale)

    def test_unavailable_is_rejected_and_missing_installed_tool_is_optional_only(self) -> None:
        """Unavailable 不得進入 primary；只有 available 時只能形成 recommendation。"""

        firmware = next(item for item in self.scenarios if item["id"] == "en-firmware-debugging")
        firmware_result = route(RouterInput(firmware["task"], self.registry, firmware["language"]))
        self.assertNotIn("offline-firmware-debugger", _ids(firmware_result.selected_primary))
        self.assertIn("offline-firmware-debugger", _ids(firmware_result.rejected_candidates))

        research = next(item for item in self.scenarios if item["id"] == "zh-research-document-search")
        research_result = route(RouterInput(research["task"], self.registry, research["language"]))
        self.assertEqual(research_result.selected_primary, ())
        self.assertTrue(research_result.selected_optional)
        self.assertTrue(
            all(record.status != CapabilityStatus.INSTALLED for record in research_result.selected_optional)
        )

    def test_ui_ux_overlap_group_selects_preferred_one_and_rejects_redundant_candidates(self) -> None:
        """同一 final UI/UX design overlap group 只選最少集合並拒絕冗餘候選。"""

        scenario = next(item for item in self.scenarios if item["id"] == "en-ui-ux-design")
        result = route(RouterInput(scenario["task"], self.registry, scenario["language"]))
        self.assertEqual(_ids(result.selected_primary), ("figma",))
        self.assertIn("ux-pilot", _ids(result.rejected_candidates))
        self.assertIn("visily", _ids(result.rejected_candidates))

    def test_routing_is_deterministic_for_all_twelve_scenarios(self) -> None:
        """相同 fixture input 重跑時，selected 與 rejected 結果必須一致。"""

        for scenario in self.scenarios:
            with self.subTest(scenario=scenario["id"]):
                request = RouterInput(scenario["task"], self.registry, scenario["language"])
                first = route(request)
                second = route(request)
                self.assertEqual(
                    (_ids(first.selected_primary), _ids(first.selected_optional), _ids(first.rejected_candidates), first.rationale),
                    (_ids(second.selected_primary), _ids(second.selected_optional), _ids(second.rejected_candidates), second.rationale),
                )


if __name__ == "__main__":
    unittest.main()
