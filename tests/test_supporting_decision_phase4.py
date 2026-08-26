"""Phase 4 Supporting decision、status 與 route finalization focused tests。"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import tempfile
import unittest

from codex_capability_router.route_context import (
    ValidatedDecisionPayloads,
    ValidatedSkillSelection,
    prepare_route_context,
    validate_decision_payloads,
)
from codex_capability_router.routing import SelectionReceipt, SelectionRouteInput, route
from codex_capability_router.supporting_context import (
    ExecutionNeed,
    ReadinessEvidenceCertificate,
    SupportingCapabilitySelection,
    SupportingFinalSelection,
    SupportingProviderDeclaration,
    SupportingToolDeclaration,
    SupportingRouteContext,
    UnmetExecutionNeed,
    prepare_supporting_context,
    validate_supporting_decision,
)
from codex_capability_router.task_analysis import validate_task_analysis


def _analysis(summary: str = "完成受限的 source verification 工作。"):
    """建立 strict TaskAnalysis fixture，不含 semantic provider mapping。"""

    return validate_task_analysis(
        {
            "task_summary": summary,
            "work_items": ["分析 source"],
            "deliverables": ["verification findings"],
            "constraints": ["read-only"],
            "quality_expectations": ["evidence traceable"],
        }
    )


def _write_skill(root: Path, skill_id: str = "phase4-skill") -> None:
    """建立可用 Skill fixture。"""

    directory = root / skill_id
    directory.mkdir(parents=True)
    (directory / "SKILL.md").write_text(
        "\n".join(
            [
                "---",
                f"id: {skill_id}",
                f"name: {skill_id}",
                "description: A Phase 4 Skill fixture.",
                "status: available",
                "---",
                "Private full handoff instructions.",
                "",
            ]
        ),
        encoding="utf-8",
    )


def _tool(tool_id: str = "js", *, schema: dict[str, object] | None = None) -> SupportingToolDeclaration:
    """建立 bounded Host callable declaration。"""

    return SupportingToolDeclaration.from_mapping(
        {
            "id": tool_id,
            "description": "Read-only callable tool.",
            "schema": schema or {"type": "object", "properties": {}, "required": []},
            "required_inputs": [],
            "output_description": "Bounded public result.",
            "side_effect": "none",
            "provenance": ["host-registry:phase0-sample"],
        }
    )


def _provider(
    provider_id: str = "node_repl",
    *,
    kind: str = "mcp",
    tool_id: str = "js",
) -> SupportingProviderDeclaration:
    """建立 exact certified provider fixture；不代表 semantic preference。"""

    return SupportingProviderDeclaration(
        provider_id=provider_id,
        kind=kind,
        host_identity="mcp__node_repl__js" if kind == "mcp" else provider_id,
        host_grouping=("mcp__node_repl",) if kind == "mcp" else ("functions",),
        description="Certified read-only provider declaration.",
        callable_tools=(_tool(tool_id),),
        callable_exposure=True,
        provenance=("host-registry:phase0-sample",),
    )


def _certificate(provider: SupportingProviderDeclaration) -> ReadinessEvidenceCertificate:
    """建立 Phase 0 evidence certificate fixture。"""

    return ReadinessEvidenceCertificate(
        provider_id=provider.provider_id,
        kind=provider.kind,
        host_identity=provider.host_identity,
        host_grouping=provider.host_grouping,
        callable_tool_ids=tuple(item.id for item in provider.callable_tools),
        expected_schema_fingerprint=provider.schema_fingerprint,
        expected_declaration_fingerprint=provider.fingerprint,
        provenance=provider.provenance,
    )


def _skill_selection(analysis, *, selected: bool = True) -> ValidatedSkillSelection:
    """建立既有 Skill selection structured output。"""

    return ValidatedSkillSelection(
        task_summary=analysis.task_summary,
        selected_skills=(("phase4-skill", "Codex judged the Skill applicable."),) if selected else (),
        selection_status="selected" if selected else "no_matching_skill",
    )


class Phase4SupportingDecisionTests(unittest.TestCase):
    """驗證 Phase 4 protocol 與唯一 production route finalization。"""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        _write_skill(self.root)
        self.analysis = _analysis()
        self.skill_selection = _skill_selection(self.analysis)
        self.need = ExecutionNeed("read-only runtime inspection", "需要目前 Host callable surface。")
        self.provider = _provider()
        self.evidence = _certificate(self.provider)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def _decision(self, *, skill_selected: bool = True, needs=(), final=None) -> ValidatedDecisionPayloads:
        """建立 v0.2 validated payload。"""

        analysis = self.analysis
        selection = _skill_selection(analysis, selected=skill_selected)
        return ValidatedDecisionPayloads(
            task_analysis=analysis,
            skill_selection=selection,
            execution_needs=tuple(needs),
            final_supporting_decision=final,
        )

    def _route_request(
        self,
        decision: ValidatedDecisionPayloads,
        *,
        provider_declarations=(),
        readiness_evidence=(),
        supporting_selection=None,
        supporting_detail_expansion_used=False,
    ) -> SelectionRouteInput:
        """建立 Phase 4 route input，所有 context 由 deterministic preparation 產生。"""

        skill_context = prepare_route_context(
            decision.task_analysis,
            skill_roots=(self.root,),
            task_summary=decision.task_analysis.task_summary,
        )
        support_context = None
        if decision.execution_needs:
            support_context = prepare_supporting_context(
                decision.execution_needs,
                provider_declarations=provider_declarations,
                readiness_evidence=readiness_evidence,
            )
        return SelectionRouteInput(
            task_summary=decision.task_analysis.task_summary,
            skill_roots=(self.root,),
            preliminary_skill_ids=("phase4-skill",) if decision.skill_selection.selected_skills else (),
            final_selection=decision.skill_selection.to_mapping(),
            validated_decision_payloads=decision,
            skill_context=skill_context,
            supporting_context=support_context,
            supporting_provider_declarations=tuple(provider_declarations),
            supporting_readiness_evidence=tuple(readiness_evidence),
            supporting_selection=supporting_selection,
            supporting_detail_expansion_used=supporting_detail_expansion_used,
        )

    def _final_payload(self, selected=True, unmet=(), unmet_reason="未滿足 execution need"):
        """建立 final_selection protocol mapping。"""

        selected_items = (
            {
                "kind": "mcp",
                "canonical_provider_id": "node_repl",
                "purpose": "Codex selected this available provider for the execution need.",
            },
        ) if selected else ()
        return {
            "request_detail": None,
            "final_selection": {
                "selected_supporting_capabilities": list(selected_items),
                "unmet_execution_needs": [
                    {"need": item.need, "reason": unmet_reason} for item in unmet
                ],
            },
        }

    def test_execution_needs_are_strict_and_empty_needs_forbid_supporting_payload(self) -> None:
        """Execution Need 僅含 need/reason；empty needs 不接受 final Provider decision。"""

        payload = self._decision()
        validated = validate_decision_payloads(payload.to_mapping())
        self.assertEqual(validated.execution_needs, ())
        with self.assertRaises(ValueError):
            validate_decision_payloads(
                {
                    **payload.to_mapping(),
                    "final_supporting_decision": {
                        "selected_supporting_capabilities": [],
                        "unmet_execution_needs": [],
                    },
                }
            )

    def test_empty_needs_route_is_not_required_and_provider_path_not_run(self) -> None:
        """empty execution_needs 由 route deterministic 產生 not_required。"""

        receipt = route(self._route_request(self._decision()))
        self.assertEqual(receipt["supporting_selection_status"], "not_required")
        self.assertEqual(receipt["supporting_metrics"]["run_state"], "not_run")
        self.assertEqual(receipt["supporting_metrics"]["discovered_count"], 0)
        self.assertEqual(receipt["selected_supporting_capabilities"], [])

    def test_empty_needs_with_supporting_context_is_rejected(self) -> None:
        """empty needs 即使帶 not_run context，也不得穿透 Supporting path。"""

        decision = self._decision()
        request = self._route_request(decision)
        with self.assertRaises(ValueError):
            route(replace(request, supporting_context=prepare_supporting_context(())))

    def test_valid_selected_node_repl_finalizes_with_receipt(self) -> None:
        """exact hard-eligible node_repl 可被 Codex final selection 選取。"""

        need = (self.need,)
        final = SupportingFinalSelection(
            (SupportingCapabilitySelection("mcp", "node_repl", "Codex selected this available provider for the execution need."),),
            (),
        )
        decision = self._decision(needs=need, final=final)
        receipt = route(
            self._route_request(
                decision,
                provider_declarations=(self.provider,),
                readiness_evidence=(self.evidence,),
                supporting_selection=self._final_payload(),
            )
        )
        self.assertIsInstance(receipt, SelectionReceipt)
        self.assertEqual(receipt["supporting_selection_status"], "selected")
        self.assertEqual(receipt["selected_supporting_capabilities"][0]["canonical_provider_id"], "node_repl")
        self.assertEqual(receipt["selection_state"], "FINALIZED")

    def test_valid_selected_functions_exec_command_is_exact_builtin_scope(self) -> None:
        """Phase 0 certified builtin Tool instance 可被 final selection 選取。"""

        provider = _provider(
            "functions.exec_command",
            kind="builtin_tool",
            tool_id="functions.exec_command",
        )
        evidence = _certificate(provider)
        final = SupportingFinalSelection(
            (
                SupportingCapabilitySelection(
                    "builtin_tool",
                    "functions.exec_command",
                    "Codex selected this available provider for the execution need.",
                ),
            ),
            (),
        )
        decision = self._decision(needs=(self.need,), final=final)
        payload = {
            "request_detail": None,
            "final_selection": final.to_mapping(),
        }
        receipt = route(
            self._route_request(
                decision,
                provider_declarations=(provider,),
                readiness_evidence=(evidence,),
                supporting_selection=payload,
            )
        )
        self.assertEqual(receipt["selected_supporting_capabilities"][0]["canonical_provider_id"], "functions.exec_command")
        self.assertEqual(receipt["selected_provider_readiness"][0]["readiness"]["connection"], "not_required")

    def test_other_mcp_or_builtin_certificate_does_not_expand_scope(self) -> None:
        """其他 MCP/builtin 即使有同形 certificate 也不自動成為正式候選。"""

        other_mcp = _provider("other_mcp", kind="mcp", tool_id="read")
        other_builtin = _provider("functions.other", kind="builtin_tool", tool_id="functions.other")
        context = prepare_supporting_context(
            (self.need,),
            provider_declarations=(other_mcp, other_builtin),
            readiness_evidence=(_certificate(other_mcp), _certificate(other_builtin)),
        )
        self.assertEqual(context.metrics.hard_eligible_count, 0)

    def test_partial_unmet_stays_selected(self) -> None:
        """至少一個 Provider selected 時，即使仍有 unmet，status 仍為 selected。"""

        final = SupportingFinalSelection(
            (SupportingCapabilitySelection("mcp", "node_repl", "Codex selected this available provider for the execution need."),),
            (UnmetExecutionNeed(self.need.need, "另一個部分需求仍未滿足。"),),
        )
        decision = self._decision(needs=(self.need,), final=final)
        receipt = route(
            self._route_request(
                decision,
                provider_declarations=(self.provider,),
                readiness_evidence=(self.evidence,),
                supporting_selection=self._final_payload(
                    unmet=(self.need,), unmet_reason="另一個部分需求仍未滿足。"
                ),
            )
        )
        self.assertEqual(receipt["supporting_selection_status"], "selected")
        self.assertEqual(len(receipt["unmet_execution_needs"]), 1)

    def test_zero_provider_lists_all_needs_as_unmet(self) -> None:
        """非空 needs 且零 Provider 時 status/no-match 與 unmet 完整一致。"""

        final = SupportingFinalSelection((), (UnmetExecutionNeed(self.need.need, "沒有 hard-eligible provider。"),))
        decision = self._decision(needs=(self.need,), final=final)
        receipt = route(
            self._route_request(
                decision,
                provider_declarations=(),
                readiness_evidence=(),
                supporting_selection=self._final_payload(
                    selected=False, unmet=(self.need,), unmet_reason="沒有 hard-eligible provider。"
                ),
            )
        )
        self.assertEqual(receipt["supporting_selection_status"], "no_matching_supporting_capability")
        self.assertEqual(receipt["unmet_execution_needs"][0]["need"], self.need.need)

    def test_request_detail_is_bounded_and_route_rejects_unresolved_payload(self) -> None:
        """request_detail 只能引用 hard-eligible exact tool，route 不接受 unresolved phase。"""

        context = prepare_supporting_context(
            (self.need,), provider_declarations=(self.provider,), readiness_evidence=(self.evidence,)
        )
        request_detail = {"request_detail": {"requests": [{"provider_id": "node_repl", "tool_ids": ["js"]}]}, "final_selection": None}
        validated = validate_supporting_decision(request_detail, (self.need,), context)
        self.assertIsNotNone(validated.request_detail)
        decision = self._decision(needs=(self.need,))
        with self.assertRaises(ValueError):
            route(
                self._route_request(
                    decision,
                    provider_declarations=(self.provider,),
                    readiness_evidence=(self.evidence,),
                    supporting_selection=request_detail,
                )
            )
        with self.assertRaises(ValueError):
            validate_supporting_decision(
                request_detail,
                (self.need,),
                context,
                detail_expansion_used=True,
            )
        with self.assertRaises(ValueError):
            validate_supporting_decision(
                {
                    "request_detail": request_detail["request_detail"],
                    "final_selection": self._final_payload()["final_selection"],
                },
                (self.need,),
                context,
            )

    def test_unverified_provider_and_kind_mismatch_are_rejected(self) -> None:
        """Python 只驗證 hard eligibility/kind，不替 Codex 改選其他 Provider。"""

        context = prepare_supporting_context((self.need,), provider_declarations=(self.provider,), readiness_evidence=())
        payload = self._final_payload()
        with self.assertRaises(ValueError):
            validate_supporting_decision(payload, (self.need,), context)
        wrong_kind = {
            "request_detail": None,
            "final_selection": {
                "selected_supporting_capabilities": [{
                    "kind": "builtin_tool",
                    "canonical_provider_id": "node_repl",
                    "purpose": "wrong kind",
                }],
                "unmet_execution_needs": [],
            },
        }
        with self.assertRaises(ValueError):
            validate_supporting_decision(wrong_kind, (self.need,), context)

    def test_no_matching_skill_and_supporting_selected_are_independent(self) -> None:
        """Skill no-match 不改寫 Supporting selected。"""

        decision = self._decision(
            skill_selected=False,
            needs=(self.need,),
            final=SupportingFinalSelection(
                (SupportingCapabilitySelection("mcp", "node_repl", "Codex selected this available provider for the execution need."),),
                (),
            ),
        )
        receipt = route(
            self._route_request(
                decision,
                provider_declarations=(self.provider,),
                readiness_evidence=(self.evidence,),
                supporting_selection=self._final_payload(),
            )
        )
        self.assertEqual(receipt["selection_status"], "no_matching_skill")
        self.assertEqual(receipt["supporting_selection_status"], "selected")

    def test_stale_supporting_context_rejects_finalize(self) -> None:
        """Provider digest/readiness/context fingerprint 改變時拒絕 finalize。"""

        changed = replace(self.provider, description="Changed Host declaration.")
        final = SupportingFinalSelection(
            (SupportingCapabilitySelection("mcp", "node_repl", "Codex selected this available provider for the execution need."),),
            (),
        )
        decision = self._decision(needs=(self.need,), final=final)
        with self.assertRaises(ValueError):
            route(
                self._route_request(
                    decision,
                    provider_declarations=(changed,),
                    readiness_evidence=(self.evidence,),
                    supporting_selection=self._final_payload(),
                )
            )

    def test_stale_skill_context_rejects_finalize(self) -> None:
        """Skill context fingerprint 改變時，正式 route 不猜替代 context。"""

        decision = self._decision()
        request = self._route_request(decision)
        skill_file = self.root / "phase4-skill" / "SKILL.md"
        skill_file.write_text(
            skill_file.read_text(encoding="utf-8").replace("Private full handoff", "Changed handoff"),
            encoding="utf-8",
        )
        with self.assertRaises(ValueError):
            route(request)

    def test_receipt_privacy_and_finalized_immutability(self) -> None:
        """Receipt 只保存 public IDs/reasons，不保存 prompt、schema 或 full handoff。"""

        receipt = route(self._route_request(self._decision()))
        rendered = str(receipt.to_mapping())
        self.assertNotIn("Private full handoff", rendered)
        self.assertNotIn(str(self.root), rendered)
        with self.assertRaises(Exception):
            receipt.selection_state = "OPEN"  # type: ignore[misc]


if __name__ == "__main__":
    unittest.main()
