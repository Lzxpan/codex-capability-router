"""V1.1.0 正式輸出的選用、覆蓋與 Host 執行回報界線。"""

from dataclasses import replace
import unittest

from codex_capability_router.catalog import render_recommendations, render_selection_payload
from codex_capability_router.routing import SelectionRouteInput, route
from codex_capability_router.supporting_context import ExecutionAttempt, SupportingFinalSelection, UnmetExecutionNeed
from tests import test_supporting_decision_phase4 as phase4
from tests.test_beta10_decision_coverage import _responses


class RenderingV11Tests(unittest.TestCase):
    """沿用既有 fixture，由正式 route 產生每份受測 Receipt。"""

    def setUp(self) -> None:
        self.fixture = phase4.Phase4SupportingDecisionTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.tearDown)
        # 2026-10-12 Steve Peng：已選項必須有證據，改用真正尚待細節的未選候選測試 PARTIAL。
        phase4._write_skill(self.fixture.root, "pending-skill")
        pending_provider = phase4._provider("pending-provider")
        final = phase4.SupportingFinalSelection(
            (phase4.SupportingCapabilitySelection("mcp", "node_repl", "Inspect source"),), ()
        )
        self.request = self.fixture._route_request(
            self.fixture._decision(needs=(self.fixture.need,), final=final),
            provider_declarations=(self.fixture.provider, pending_provider),
            readiness_evidence=(self.fixture.evidence,),
        )
        task = self.request.skill_context.context_fingerprint
        skills = _responses(self.request.skill_context.inventory_sweep, task, ("phase4-skill",))
        providers = _responses(self.request.supporting_context.inventory_sweep, task, ("node_repl",))
        skills[0]["dispositions"]["pending-skill"] = "needs_detail"
        providers[0]["dispositions"]["pending-provider"] = "needs_detail"
        self.request = replace(self.request, skill_batch_decisions=skills, supporting_batch_decisions=providers)
        self.receipt = route(self.request)

    def _attempt(self, **changes) -> ExecutionAttempt:
        """建立有原始 Receipt 綁定的 Host 回報，允許測試單一錯配欄位。"""

        attempt = ExecutionAttempt(
            selection_receipt_fingerprint=self.receipt.receipt_fingerprint,
            execution_need=self.fixture.need.need,
            provider_kind="mcp",
            provider_id="node_repl",
            readiness_state="PRESENT_UNVERIFIED",
            outcome="CALL_FAILED",
            error_category="timeout",
            actual_server="node_repl",
            actual_tool="js",
        )
        return replace(attempt, **changes)

    def test_legacy_call_and_low_level_payload_keep_core_output(self) -> None:
        low_level = render_selection_payload(self.receipt.selection_payload(), language="en")
        output = render_recommendations(self.receipt, language="en")
        self.assertTrue(output.startswith(low_level))
        self.assertEqual(render_recommendations(payload=self.receipt, language="en"), output)
        self.assertNotIn("FINALIZED", low_level)
        self.assertNotIn("Provider", low_level)
        with self.assertRaises(TypeError):
            render_recommendations(self.receipt.to_mapping(), execution_attempts=())

    def test_selected_provider_and_partial_coverage_are_visible_in_both_languages(self) -> None:
        for language, providers, coverage, boundary in (
            ("en", "## Selected Providers", "## Decision Coverage", "does not prove coverage completion or execution"),
            ("zh-TW", "## 已選 Providers", "## 判斷覆蓋狀況", "不代表覆蓋完整或已執行"),
        ):
            with self.subTest(language=language):
                output = render_recommendations(self.receipt, language=language)
                self.assertIn(providers, output)
                self.assertIn("`node_repl` (`mcp`) — Inspect source", output)
                self.assertIn(coverage, output)
                self.assertIn("Skill", output)
                self.assertIn("Provider", output)
                self.assertEqual(output.count("`PARTIAL`"), 2)
                self.assertIn("1/2", output)
                self.assertIn(boundary, output)
                self.assertNotIn("`SUCCESS`", output)

    def test_provider_selection_state_is_separate_from_missing_or_partial_coverage(self) -> None:
        """2026-10-08 Steve Peng：由正式 route 區分未需要、已選與需求未滿足。"""
        not_required = route(self.fixture._route_request(self.fixture._decision()))
        absent = route(self.fixture._route_request(self.fixture._decision(
            needs=(self.fixture.need,),
            final=SupportingFinalSelection((), (UnmetExecutionNeed(self.fixture.need.need, "No provider exposed"),)),
        )))
        unmatched_request = self.fixture._route_request(self.fixture._decision(
            needs=(self.fixture.need,),
            final=SupportingFinalSelection((), (
                UnmetExecutionNeed(self.fixture.need.need, "No suitable provider selected"),
            )),
        ), provider_declarations=(self.fixture.provider,), readiness_evidence=(self.fixture.evidence,))
        unmatched = route(replace(unmatched_request, supporting_batch_decisions=()))
        for receipt, status, coverage in (
            (not_required, "not_required", "未提供"),
            (self.receipt, "selected", "PARTIAL"),
            (unmatched, "no_matching_supporting_capability", "PARTIAL"),
            (absent, "no_present_supporting_provider", "COMPLETE"),
        ):
            for language, label in (("en", "Provider selection status:"), ("zh-TW", "Provider 選用狀態：")):
                with self.subTest(status=status, language=language):
                    before = receipt.receipt_fingerprint
                    output = render_recommendations(receipt, language=language)
                    self.assertIn(f"{label} `{status}`" if language == "en" else f"{label}`{status}`", output)
                    expected = coverage if language == "zh-TW" else ("not provided" if coverage == "未提供" else coverage)
                    provider_label = "Provider：" if language == "zh-TW" else "Provider: "
                    self.assertIn(f"{provider_label}`{expected}`", output)
                    skill_label = "Skill：" if language == "zh-TW" else "Skill: "
                    skill_coverage = "PARTIAL" if receipt is self.receipt else "COMPLETE"
                    self.assertIn(f"{skill_label}`{skill_coverage}`", output)
                    self.assertEqual(receipt.receipt_fingerprint, before)

    def test_complete_coverage_requires_observed_decisions_for_each_inventory(self) -> None:
        task = self.request.skill_context.context_fingerprint
        completed = replace(
            self.request,
            skill_batch_decisions=_responses(self.request.skill_context.inventory_sweep, task, ("phase4-skill",)),
            supporting_batch_decisions=_responses(self.request.supporting_context.inventory_sweep, task, ("node_repl",)),
        )
        for language in ("en", "zh-TW"):
            with self.subTest(language=language):
                output = render_recommendations(route(completed), language=language)
                self.assertEqual(output.count("`COMPLETE`"), 2)
                self.assertEqual(output.count("2/2"), 2)
                self.assertNotIn("`SUCCESS`", output)

    def test_legacy_missing_metrics_remain_unreported(self) -> None:
        receipt = route(SelectionRouteInput(
            task_summary=self.fixture.analysis.task_summary,
            skill_roots=(self.fixture.root,),
            preliminary_skill_ids=("phase4-skill",),
            final_selection=self.fixture.skill_selection.to_mapping(),
        ))
        for language, missing in (("en", "not provided"), ("zh-TW", "未提供")):
            with self.subTest(language=language):
                output = render_recommendations(receipt, language=language)
                self.assertIn(f"Skill: `{missing}`" if language == "en" else f"Skill：`{missing}`", output)
                self.assertIn(f"Provider: `{missing}`" if language == "en" else f"Provider：`{missing}`", output)
                self.assertNotIn("`COMPLETE`", output)
                self.assertNotIn("0/0", output)

    def test_empty_attempts_are_unreported_not_execution_success_or_not_attempted(self) -> None:
        for language, section, missing in (
            ("en", "## Execution Results (Host-reported)", "No execution results reported by Host"),
            ("zh-TW", "## 執行結果（Host 回報）", "Host 未回報執行結果"),
        ):
            with self.subTest(language=language):
                output = render_recommendations(self.receipt, language=language, execution_attempts=())
                self.assertIn(section, output)
                self.assertIn(missing, output)
                self.assertNotIn("NOT_ATTEMPTED", output)
                self.assertNotIn("SUCCESS", output)
                self.assertNotIn("VERIFIED_READY", output)

    def test_provider_metrics_without_decision_coverage_are_not_complete(self) -> None:
        receipt = route(self.fixture._route_request(self.fixture._decision()))
        self.assertEqual(receipt.supporting_metrics["run_state"], "not_run")
        output = render_recommendations(receipt, language="zh-TW")
        self.assertIn("Provider：`未提供`。", output)
        self.assertNotIn("Provider：`COMPLETE`", output)
        self.assertNotIn("## 已選 Providers", output)

    def test_explicit_not_attempted_remains_a_host_report(self) -> None:
        output = render_recommendations(
            self.receipt,
            execution_attempts=(self._attempt(outcome="NOT_ATTEMPTED", error_category=None),),
        )
        self.assertIn("## Execution Results (Host-reported)", output)
        self.assertIn("`NOT_ATTEMPTED`", output)
        self.assertNotIn("No execution results reported", output)

    def test_execution_reports_preserve_failure_and_retry_in_host_order(self) -> None:
        failed = self._attempt()
        success = self._attempt(outcome="SUCCESS", error_category=None, readiness_state="VERIFIED_READY")
        original_fingerprint = self.receipt.receipt_fingerprint
        for language in ("en", "zh-TW"):
            with self.subTest(language=language):
                output = render_recommendations(self.receipt, language=language, execution_attempts=(failed, success))
                self.assertLess(output.index("`CALL_FAILED`"), output.index("`SUCCESS`"))
                self.assertIn("`timeout`", output)
                self.assertIn("`PRESENT_UNVERIFIED`", output)
                self.assertIn("`VERIFIED_READY`", output)
                self.assertIn(self.fixture.need.need, output)
                self.assertIn("`js`", output)
        self.assertEqual(self.receipt.receipt_fingerprint, original_fingerprint)

    def test_execution_report_requires_typed_attempt(self) -> None:
        for attempt in (self._attempt().to_mapping(), "SUCCESS", None):
            with self.subTest(attempt=attempt), self.assertRaisesRegex(TypeError, "ExecutionAttempt"):
                render_recommendations(self.receipt, execution_attempts=(attempt,))

    def test_optional_host_text_cannot_create_markdown_headings(self) -> None:
        attempt = self._attempt(
            error_category="timeout`\r\n## fabricated heading\n`",
            actual_server="server``\r## forged server\nend",
            app_context="`panel```\n## forged App\r`",
        )
        original = attempt.to_mapping()
        for language in ("en", "zh-TW"):
            with self.subTest(language=language):
                expected_headings = [
                    line for line in render_recommendations(self.receipt, language=language).splitlines()
                    if line.startswith("#")
                ]
                output = render_recommendations(self.receipt, language=language, execution_attempts=(attempt,))
                self.assertEqual([line for line in output.splitlines() if line.startswith("#")], expected_headings)
                self.assertNotIn("\r", output)
                self.assertIn("`` timeout`\\r\\n## fabricated heading\\n` ``", output)
                self.assertIn("``` server``\\r## forged server\\nend ```", output)
                self.assertIn("```` `panel```\\n## forged App\\r` ````", output)
        self.assertEqual(attempt.to_mapping(), original)

    def test_execution_report_rejects_mismatched_receipt_provider_kind_id_or_need(self) -> None:
        for changes in (
            {"selection_receipt_fingerprint": "0" * 64},
            {"provider_kind": "host_tool"},
            {"provider_id": "different_provider"},
            {"execution_need": "different execution need"},
        ):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                render_recommendations(self.receipt, execution_attempts=(self._attempt(**changes),))

    def test_auto_language_applies_to_new_sections(self) -> None:
        output = render_recommendations(self.receipt, language="auto", user_request="請列出執行結果")
        self.assertIn("## 已選 Providers", output)
        self.assertIn("## 執行結果（Host 回報）", output)


if __name__ == "__main__":
    unittest.main()
