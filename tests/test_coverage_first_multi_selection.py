"""Coverage-first multi-Skill/multi-Provider selection regression tests。"""

from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from codex_capability_router.route_context import (
    ValidatedDecisionPayloads,
    ValidatedSkillSelection,
    prepare_route_context,
)
from codex_capability_router.routing import SelectionRouteInput, route
from codex_capability_router.selection import validate_selection
from codex_capability_router.supporting_context import (
    ExecutionNeed,
    SupportingCapabilitySelection,
    SupportingFinalSelection,
    SupportingProviderDeclaration,
    SupportingToolSummary,
    prepare_supporting_context,
    validate_supporting_coverage_additions,
    validate_supporting_decision,
)
from codex_capability_router.task_analysis import TaskAnalysis


# 修改紀錄（2026-09-01，Steve Peng）
# 原始內容：deterministic suite 沒有 coverage-first multi-Provider、minimum metadata 或 addition route tests。
# 修改原因：驗證「合理但不確定仍選取」與 generic fallback 不壓掉 specialized capability 的正式 contract。
# 修改後功能：覆蓋多選、PRESENT_UNVERIFIED、metadata gate、一次 Supporting Coverage Check、Plugin boundary 與 FINALIZED Receipt。


def _tool_summary(tool_id: str, *, title: str | None = "Tool summary") -> SupportingToolSummary:
    """建立只含 public summary 的 Host tool fixture，不提供猜測 schema。"""

    return SupportingToolSummary(
        id=tool_id,
        title=title,
        description="A meaningful capability summary.",
        is_enabled=True,
        disabled_reason=None,
        is_read_only=True,
        provenance=("test:coverage-first",),
    )


def _provider(
    provider_id: str,
    *,
    description: str | None = "A provider with a meaningful public capability description.",
    tools: tuple[SupportingToolSummary, ...] = (),
    kind: str = "mcp",
) -> SupportingProviderDeclaration:
    """建立 trusted-present fixture；readiness intentionally remains unverified without evidence。"""

    return SupportingProviderDeclaration(
        provider_id=provider_id,
        kind=kind,
        host_identity=provider_id,
        host_grouping=("test",),
        description=description,
        callable_tools=tools,
        callable_exposure=False,
        provenance=("test:coverage-first",),
        display_name=provider_id,
    )


class CoverageFirstMultiSelectionTests(unittest.TestCase):
    """確認 selection coverage 擴大時仍維持 bounded safety contract。"""

    def test_skill_selection_has_no_fixed_count(self) -> None:
        """四個互補 Skill 可通過 public schema，不被固定數量截斷。"""

        payload = {
            "task_summary": "complete a multi-method task",
            "selected_skills": [
                {"id": f"method-{index}", "reason": "plausibly material and distinct"}
                for index in range(4)
            ],
            "selection_status": "selected",
        }
        self.assertEqual(len(validate_selection(payload)["selected_skills"]), 4)

    def test_multiple_present_providers_are_selectable_without_fixed_maximum(self) -> None:
        """多個 PRESENT Provider 可同時進入 semantic selection。"""

        needs = (
            ExecutionNeed("create image", "The task needs visual creation."),
            ExecutionNeed("render diagram", "The task needs diagram output."),
            ExecutionNeed("verify repository", "The task needs repository validation."),
        )
        providers = tuple(_provider(f"provider-{index}") for index in range(4))
        context = prepare_supporting_context(needs, provider_declarations=providers)

        self.assertEqual(context.metrics.present_count, 4)
        self.assertEqual(context.metrics.selectable_count, 4)
        self.assertEqual(context.metrics.present_unverified_count, 4)
        self.assertEqual(len(context.provider_digests), 4)
        final = SupportingFinalSelection(
            tuple(
                SupportingCapabilitySelection("mcp", provider.provider_id, "A distinct execution contribution.")
                for provider in providers
            ),
            (),
        )
        validated = validate_supporting_decision(
            {"request_detail": None, "final_selection": final.to_mapping()},
            needs,
            context,
        )
        self.assertEqual(len(validated.final_selection.selected_supporting_capabilities), 4)

    def test_provider_description_is_enough_without_tool_detail(self) -> None:
        """有 meaningful Provider description 時，不要求完整 tool detail 或 callable flag。"""

        provider = _provider("description-only", tools=())
        context = prepare_supporting_context(
            (ExecutionNeed("create image", "A visual capability is material."),),
            provider_declarations=(provider,),
        )
        self.assertEqual(len(context.provider_digests), 1)
        self.assertEqual(context.provider_digests[0].readiness_state, "PRESENT_UNVERIFIED")
        self.assertEqual(context.metrics.metadata_insufficient_count, 0)

    def test_tool_summary_is_enough_without_provider_description(self) -> None:
        """Provider description 缺席時，tool title/summary 可提供最低語意。"""

        provider = _provider("summary-only", description=None, tools=(_tool_summary("render"),))
        context = prepare_supporting_context(
            (ExecutionNeed("render diagram", "A diagram capability is material."),),
            provider_declarations=(provider,),
        )
        self.assertEqual(len(context.provider_digests), 1)
        self.assertEqual(context.metrics.metadata_insufficient_count, 0)

    def test_completely_missing_metadata_is_still_considered(self) -> None:
        """沒有 description 或 tool summary 時仍保留給 LLM consideration。"""

        provider = _provider("empty-metadata", description=None, tools=())
        context = prepare_supporting_context(
            (ExecutionNeed("create image", "A visual capability is material."),),
            provider_declarations=(provider,),
        )
        self.assertEqual(len(context.provider_digests), 1)
        self.assertEqual(context.provider_digests[0].metadata_quality.value, "OPAQUE")
        self.assertEqual(context.metrics.selectable_count, 1)
        self.assertEqual(context.metrics.metadata_insufficient_count, 1)

    def test_generic_fallback_does_not_suppress_specialized_provider(self) -> None:
        """generic execution 與 specialized image Provider 保留不同 candidate value。"""

        providers = (
            _provider("generic-exec", description="Runs bounded local repository commands."),
            _provider("image-specialist", description="Generates original visual assets."),
        )
        context = prepare_supporting_context(
            (ExecutionNeed("create image", "The specialized visual capability is material."),),
            provider_declarations=providers,
        )
        self.assertEqual([item.provider_id for item in context.provider_digests], ["generic-exec", "image-specialist"])

    def test_supporting_coverage_addition_requires_need_and_distinct_value(self) -> None:
        """Supporting addition 必須引用 original need 且具備 public distinct value。"""

        needs = (
            ExecutionNeed("create image", "The task needs an image."),
            ExecutionNeed("render diagram", "The task needs a diagram."),
        )
        additions = validate_supporting_coverage_additions(
            {
                "additions": [
                    {
                        "provider_id": "image-provider",
                        "execution_need": "create image",
                        "distinct_value": "Provides specialized image generation beyond generic execution.",
                    }
                ]
            },
            candidate_ids=("base-provider", "image-provider"),
            selected_ids=("base-provider",),
            execution_needs=needs,
        )
        self.assertEqual(additions[0].provider_id, "image-provider")
        with self.assertRaises(ValueError):
            validate_supporting_coverage_additions(
                {"additions": [{"provider_id": "image-provider", "execution_need": "create image"}]},
                candidate_ids=("image-provider",),
                execution_needs=needs,
            )

    def test_supporting_coverage_is_finalized_once_with_multiple_providers(self) -> None:
        """production route 保存 base selection、一次 addition 與多 Provider final selection。"""

        with tempfile.TemporaryDirectory() as value:
            root = Path(value)
            skill_dir = root / "coverage-skill"
            skill_dir.mkdir()
            (skill_dir / "SKILL.md").write_text(
                "---\nid: coverage-skill\nname: coverage-skill\ndescription: Coverage fixture.\nstatus: available\n---\nmethod\n",
                encoding="utf-8",
            )
            analysis = TaskAnalysis(
                "complete a visual repository task",
                ("create image", "render diagram", "verify repository"),
                ("visual asset", "diagram", "verification result"),
                ("preserve Provider boundary",),
                ("material coverage",),
            )
            skill = ValidatedSkillSelection(
                analysis.task_summary,
                (("coverage-skill", "The fixture method is applicable."),),
                "selected",
            )
            needs = (
                ExecutionNeed("create image", "The task needs image creation."),
                ExecutionNeed("render diagram", "The task needs diagram rendering."),
            )
            providers = (_provider("base-provider"), _provider("image-provider"), _provider("unused-provider"))
            context = prepare_supporting_context(needs, provider_declarations=providers)
            final = SupportingFinalSelection(
                (
                    SupportingCapabilitySelection("mcp", "base-provider", "Provides repository execution."),
                    SupportingCapabilitySelection("mcp", "image-provider", "Provides specialized image creation."),
                ),
                (),
            )
            decision = ValidatedDecisionPayloads(analysis, skill, needs, final)
            skill_context = prepare_route_context(analysis, skill_roots=(root,))
            receipt = route(
                SelectionRouteInput(
                    task_summary=analysis.task_summary,
                    skill_roots=(root,),
                    preliminary_skill_ids=("coverage-skill",),
                    final_selection=skill.to_mapping(),
                    validated_decision_payloads=decision,
                    skill_context=skill_context,
                    supporting_context=context,
                    supporting_provider_declarations=providers,
                    supporting_selection={"request_detail": None, "final_selection": final.to_mapping()},
                    supporting_preliminary_provider_ids=("base-provider",),
                    supporting_coverage_check_used=True,
                    supporting_coverage_additions=(
                        {
                            "provider_id": "image-provider",
                            "execution_need": "create image",
                            "distinct_value": "Specialized image creation is distinct from repository execution.",
                        },
                    ),
                )
            )
            self.assertEqual(receipt["selection_state"], "FINALIZED")
            self.assertEqual(receipt["supporting_preliminary_provider_ids"], ["base-provider"])
            self.assertEqual(receipt["supporting_coverage_check_used"], True)
            self.assertEqual(receipt["supporting_coverage_additions"][0]["provider_id"], "image-provider")
            self.assertEqual(len(receipt["selected_supporting_capabilities"]), 2)
            self.assertEqual(receipt["supporting_metrics"]["selected_count"], 2)

    def test_supporting_coverage_fields_are_bounded_and_plugin_is_not_formal(self) -> None:
        """沒有 addition flag 不得穿透；Plugin 仍不是 formal Provider。"""

        with self.assertRaises(ValueError):
            SelectionRouteInput(
                task_summary="coverage",
                skill_roots=(Path("."),),
                preliminary_skill_ids=(),
                final_selection={
                    "task_summary": "coverage",
                    "selected_skills": [{"id": "skill", "reason": "material"}],
                    "selection_status": "selected",
                },
                supporting_coverage_additions=(
                    {"provider_id": "p", "execution_need": "need", "distinct_value": "distinct"},
                ),
            )

        context = prepare_supporting_context(
            (ExecutionNeed("need", "A need."),),
            provider_declarations=(_provider("provider"),),
        )
        plugin = {
            "request_detail": None,
            "final_selection": {
                "selected_supporting_capabilities": [
                    {"kind": "plugin", "canonical_provider_id": "provider", "purpose": "legacy"}
                ],
                "unmet_execution_needs": [],
            },
        }
        with self.assertRaises(ValueError):
            validate_supporting_decision(
                plugin,
                (ExecutionNeed("need", "A need."),),
                context,
            )


if __name__ == "__main__":
    unittest.main()
