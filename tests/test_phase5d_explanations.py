"""Phase 5D selected capability explanation 的六個 behavior tests。

修改紀錄（2026-08-18，Steve Peng）
原始內容：Phase 5C 只有 machine-readable recommendation 與 catalog output，沒有 selected explanation。
修改原因：先以 TDD 固定雙語、selection level、Function fallback 與 recommendation-only 邊界。
修改後功能：只驗證本階段指定的六個 user-facing behavior，不新增 routing scenario。
"""

from __future__ import annotations

import unittest

from codex_capability_router.catalog import render_recommendations
from codex_capability_router.models import RouterInput
from codex_capability_router.routing import route
from codex_capability_router.validation import record_from_mapping


def _record(
    *,
    capability_id: str,
    name: str,
    kind: str,
    status: str,
    category: str,
    trigger: str,
    source: str = "fixture:phase5d",
    function_en: str | None = None,
    function_zh_tw: str | None = None,
    recommendation_only: bool = False,
):
    """建立 hand-checked canonical record，讓測試只控制必要 routing evidence。"""

    payload = {
        "id": capability_id,
        "name": name,
        "kind": kind,
        "status": status,
        "categories": [category],
        "triggers": [trigger],
        "priority": 10,
        "overlap_group": None,
        "preferred_for": [category],
        "requires": [],
        "source": source,
        "last_verified": None,
        "recommendation_only": recommendation_only,
    }
    if function_en is not None or function_zh_tw is not None:
        payload["function"] = {"en": function_en, "zh-TW": function_zh_tw}
    try:
        return record_from_mapping(payload)
    except ValueError as error:
        # TDD RED：現有 validator 尚未支援 function metadata 時，轉成可讀的預期失敗。
        raise AssertionError(f"Phase 5D function metadata is not supported yet: {error}") from error


class Phase5DExplanationTests(unittest.TestCase):
    """只固定 selected capability explanation 的六個核心行為。"""

    def test_primary_selected_skill_includes_required_explanation_fields(self) -> None:
        """Name the break: PRIMARY skill explanation must expose identity, function and evidence-based reason."""

        record = _record(
            capability_id="react-ui-debugging",
            name="React UI Debugging",
            kind="skill",
            status="installed",
            category="react ui bug",
            trigger="react",
            function_en="Debugs React UI regressions.",
            function_zh_tw="分析 React 介面回歸問題。",
        )
        result = route(RouterInput("Fix the React component UI bug.", (record,), "en"))
        evidence = result.selection_evidence[0]

        output = render_recommendations(
            result,
            language="en",
            user_request="Fix the React component UI bug.",
        )

        self.assertIn("## Selected Capabilities", output)
        self.assertIn("### Selected Skills", output)
        self.assertIn("Name: React UI Debugging", output)
        self.assertIn("Kind: skill", output)
        self.assertIn("Selection level: PRIMARY", output)
        self.assertIn("Function: Debugs React UI regressions.", output)
        self.assertIn("Why selected:", output)
        self.assertIn("trigger", output)
        self.assertEqual(evidence.selection_level, "PRIMARY")
        self.assertIn("exact_trigger_match", evidence.reason_codes)
        self.assertEqual(evidence.matched_triggers, ("react",))

    def test_optional_selected_skill_is_labeled_optional(self) -> None:
        """Name the break: available skill must remain OPTIONAL in the explanation."""

        record = _record(
            capability_id="research-document-search",
            name="Research Document Search",
            kind="skill",
            status="available",
            category="research document search",
            trigger="research",
            function_en="Searches research documents.",
        )
        result = route(RouterInput("Search the research documents and papers.", (record,), "en"))

        output = render_recommendations(
            result,
            language="en",
            user_request="Search the research documents and papers.",
        )

        self.assertIn("### OPTIONAL", output)
        self.assertIn("Selection level: OPTIONAL", output)
        self.assertIn("Name: Research Document Search", output)

    def test_english_output_renders_selected_skills_and_other_capabilities(self) -> None:
        """Name the break: English output must separate skills from non-skill capabilities."""

        records = (
            _record(
                capability_id="pr-code-review",
                name="PR Code Review",
                kind="skill",
                status="installed",
                category="pr code review",
                trigger="pull request",
                function_en="Reviews pull request changes.",
            ),
            _record(
                capability_id="github",
                name="GitHub",
                kind="plugin",
                status="installed",
                category="pr code review",
                trigger="diff",
                function_en="Provides GitHub repository workflows.",
            ),
        )
        task = "Review the pull request code diff."
        result = route(RouterInput(task, records, "en"))

        output = render_recommendations(result, language="en", user_request=task)

        self.assertIn("## Selected Capabilities", output)
        self.assertIn("### Selected Skills", output)
        self.assertIn("### Other Selected Capabilities", output)
        self.assertIn("Name: GitHub", output)
        self.assertIn("Kind: plugin", output)

    def test_zh_tw_output_renders_localized_selected_headings(self) -> None:
        """Name the break: zh-TW output must localize selected headings and field labels."""

        records = (
            _record(
                capability_id="firmware-debugging",
                name="Firmware Debugging",
                kind="skill",
                status="installed",
                category="firmware debugging",
                trigger="韌體",
                function_en="Analyzes firmware failures.",
                function_zh_tw="分析韌體故障。",
            ),
            _record(
                capability_id="uart-tool",
                name="UART Tool",
                kind="tool",
                status="installed",
                category="firmware debugging",
                trigger="UART",
                function_zh_tw="協助檢查 UART 通訊。",
            ),
        )
        task = "請協助除錯 MCU 韌體的 UART 錯誤。"
        result = route(RouterInput(task, records, "zh-TW"))

        output = render_recommendations(result, language="zh-TW", user_request=task)

        self.assertIn("## 已選能力", output)
        self.assertIn("### 已選技能", output)
        self.assertIn("### 其他已選能力", output)
        self.assertIn("名稱：Firmware Debugging", output)
        self.assertIn("類型：skill", output)
        self.assertIn("功能：分析韌體故障。", output)
        self.assertIn("選用理由：", output)

    def test_missing_function_metadata_uses_unavailable_fallback(self) -> None:
        """Name the break: absent Function metadata must not be invented from category or trigger text."""

        record = _record(
            capability_id="mystery-capability",
            name="Mystery Capability",
            kind="skill",
            status="installed",
            category="mystery task",
            trigger="mystery",
        )
        task = "Solve the mystery task."
        result = route(RouterInput(task, (record,), "en"))

        output = render_recommendations(result, language="en", user_request=task)

        self.assertIn("Function: Function information unavailable.", output)
        self.assertNotIn("Supports mystery task recommendations.", output)

    def test_recommendation_only_is_separate_from_selected_executable_output(self) -> None:
        """Name the break: recommendation-only capability must never appear as selected executable output."""

        record = _record(
            capability_id="manual-suggestion",
            name="Manual Suggestion",
            kind="plugin",
            status="unknown",
            category="firmware debugging",
            trigger="firmware",
            source="manual:inventory",
            function_en="Suggested firmware support.",
            recommendation_only=True,
        )
        task = "Debug the firmware UART error."
        result = route(RouterInput(task, (record,), "en"))

        output = render_recommendations(result, language="en", user_request=task)
        selected_output = output.split("## Recommended but not selected", 1)[0]

        self.assertIn("## Recommended but not selected", output)
        self.assertNotIn("manual-suggestion", selected_output)
        self.assertIn("Not selected as an executable capability.", output)
        self.assertIn("It will not be installed or executed automatically.", output)


if __name__ == "__main__":
    unittest.main()
