"""Phase 4 唯一 production Skill selection entry point。"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field, replace
import json
from pathlib import Path
import re
import unicodedata

from .models import DiscoveryResult


# 修改紀錄（2026-08-21，Steve Peng）
# 原始內容：route() 依固定 task aliases、category/trigger/provides ranking、overlap winner 與 PRIMARY/OPTIONAL limits 直接決定 final result。
# 修改原因：v2.1 Phase 4 要讓 Phase 1～3 Selection Contract 成為唯一 production path，語意 final selection 必須由 Codex 提供，Python 只負責準備與驗證。
# 修改後功能：route() 僅 orchestration inventory、candidate preparation、Codex preliminary IDs、full handoff、state limits 與 final validation；不保留 legacy selector 或 silent fallback。
# 修改紀錄（2026-08-25，Steve Peng）
# 原始內容：route() 成功後回傳普通 selection mapping，外層可自行偽造正式 Router Result，且沒有 finalized receipt。
# 修改原因：Integration Hardening 要求正式結果必須可證明來自 production route，並保留 bounded routing evidence。
# 修改後功能：route() 只有在 final validation 成功後建立 SelectionReceipt；receipt 不保存完整 prompt、SKILL.md 或 private inventory。
# 修改紀錄（2026-08-26，Steve Peng）
# 原始內容：beta.4 route 只保存 Skill selection，沒有 Execution Needs、Supporting final decision 與 context revalidation。
# 修改原因：Phase 4 必須在既有唯一 route() 中完成 Supporting decision validation 與 FINALIZED receipt 擴充。
# 修改後功能：只接受 immutable structured decision、exact hard-eligible Provider 與新鮮 fingerprints；不建立第二條 route 或 workflow/session state。

_CONTROLLER_ALIASES = frozenset(
    {
        "codex-capability-router",
        "codex capability router",
        "codex-router",
        "codex router",
        "capability-router",
        "capability router",
    }
)

SELECTION_RECEIPT_CONTRACT_VERSION = "0.1.0-beta.4"
V02_DECISION_RECEIPT_CONTRACT_VERSION = "v0.2-selection-decision-v1"
_RECEIPT_TOKEN = object()
_CANONICAL_SKILL_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]*$")


@dataclass(frozen=True)
class SelectionReceipt(Mapping[str, object]):
    """只能由 production route 建立的最小、可稽核 Selection Receipt。"""

    router_invoked: bool
    contract_version: str
    task_summary: str
    candidate_skills: tuple[str, ...]
    preliminary_selected_skills: tuple[str, ...]
    full_handoff_skills: tuple[str, ...]
    _selected_skills: tuple[tuple[str, str], ...]
    selection_status: str
    expanded_retrieval: bool
    correction: bool
    selection_state: str
    _token: object = field(default=None, repr=False, compare=False)
    _task_analysis: str | None = field(default=None, repr=False, compare=False)
    _execution_needs: tuple[tuple[str, str], ...] = field(default=(), repr=False, compare=False)
    supporting_selection_status: str = "not_required"
    _selected_supporting_capabilities: tuple[tuple[str, str, str], ...] = field(default=(), repr=False, compare=False)
    _unmet_execution_needs: tuple[tuple[str, str], ...] = field(default=(), repr=False, compare=False)
    skill_context_fingerprint: str | None = None
    supporting_context_fingerprint: str | None = None
    supporting_digest_fingerprints: tuple[tuple[str, str], ...] = ()
    selected_provider_readiness: tuple[tuple[str, str, str, str, str, str, bool, tuple[str, ...]], ...] = ()
    supporting_detail_expansion_used: bool = False
    expanded_provider_tool_ids: tuple[tuple[str, tuple[str, ...]], ...] = ()
    skill_metrics: Mapping[str, object] | None = None
    supporting_metrics: Mapping[str, object] | None = None

    @classmethod
    def _from_route(
        cls,
        *,
        task_summary: str,
        candidate_skills: tuple[str, ...],
        preliminary_selected_skills: tuple[str, ...],
        full_handoff_skills: tuple[str, ...],
        selected_skills: list[dict[str, str]],
        selection_status: str,
        expanded_retrieval: bool,
        correction: bool,
        selection_state: str,
        task_analysis: Mapping[str, object] | None = None,
        execution_needs: tuple[Mapping[str, str], ...] = (),
        supporting_selection_status: str = "not_required",
        selected_supporting_capabilities: tuple[Mapping[str, str], ...] = (),
        unmet_execution_needs: tuple[Mapping[str, str], ...] = (),
        skill_context_fingerprint: str | None = None,
        supporting_context_fingerprint: str | None = None,
        supporting_digest_fingerprints: tuple[tuple[str, str], ...] = (),
        selected_provider_readiness: tuple[tuple[str, str, str, str, str, str, bool, tuple[str, ...]], ...] = (),
        supporting_detail_expansion_used: bool = False,
        expanded_provider_tool_ids: tuple[tuple[str, tuple[str, ...]], ...] = (),
        skill_metrics: Mapping[str, object] | None = None,
        supporting_metrics: Mapping[str, object] | None = None,
    ) -> "SelectionReceipt":
        """建立 route 成功後的 receipt；外層不得直接模擬此 production result。"""

        return cls(
            router_invoked=True,
            contract_version=SELECTION_RECEIPT_CONTRACT_VERSION,
            task_summary=task_summary,
            candidate_skills=tuple(candidate_skills),
            preliminary_selected_skills=tuple(preliminary_selected_skills),
            full_handoff_skills=tuple(full_handoff_skills),
            _selected_skills=tuple((item["id"], item["reason"]) for item in selected_skills),
            selection_status=selection_status,
            expanded_retrieval=expanded_retrieval,
            correction=correction,
            selection_state=selection_state,
            _token=_RECEIPT_TOKEN,
            _task_analysis=(
                None
                if task_analysis is None
                else json.dumps(task_analysis, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            ),
            _execution_needs=tuple((item["need"], item["reason"]) for item in execution_needs),
            supporting_selection_status=supporting_selection_status,
            _selected_supporting_capabilities=tuple(
                (item["kind"], item["canonical_provider_id"], item["purpose"])
                for item in selected_supporting_capabilities
            ),
            _unmet_execution_needs=tuple((item["need"], item["reason"]) for item in unmet_execution_needs),
            skill_context_fingerprint=skill_context_fingerprint,
            supporting_context_fingerprint=supporting_context_fingerprint,
            supporting_digest_fingerprints=tuple(supporting_digest_fingerprints),
            selected_provider_readiness=tuple(selected_provider_readiness),
            supporting_detail_expansion_used=supporting_detail_expansion_used,
            expanded_provider_tool_ids=tuple(expanded_provider_tool_ids),
            skill_metrics=None if skill_metrics is None else dict(skill_metrics),
            supporting_metrics=None if supporting_metrics is None else dict(supporting_metrics),
        )

    def __post_init__(self) -> None:
        """驗證 receipt 不含非 canonical ID、敏感文字或未 finalized 狀態。"""

        if self._token is not _RECEIPT_TOKEN:
            raise TypeError("SelectionReceipt can only be created by production route")
        if self.router_invoked is not True:
            raise ValueError("production receipt must record router_invoked=true")
        if self.contract_version != SELECTION_RECEIPT_CONTRACT_VERSION:
            raise ValueError("unsupported selection receipt contract version")
        _require_receipt_text(self.task_summary, "task_summary")
        if self.selection_status not in {"selected", "no_matching_skill"}:
            raise ValueError("selection receipt has unsupported selection status")
        if self.selection_state != "FINALIZED":
            raise ValueError("selection receipt must be finalized")
        if not isinstance(self.expanded_retrieval, bool) or not isinstance(self.correction, bool):
            raise ValueError("receipt transition flags must be boolean")
        if self.supporting_selection_status not in {"not_required", "selected", "no_matching_supporting_capability"}:
            raise ValueError("receipt has unsupported supporting selection status")
        if not isinstance(self.supporting_detail_expansion_used, bool):
            raise ValueError("supporting detail expansion flag must be boolean")
        if not self.supporting_detail_expansion_used and self.expanded_provider_tool_ids:
            raise ValueError("expanded provider/tool IDs require detail expansion")

        all_ids = (*self.candidate_skills, *self.preliminary_selected_skills, *self.full_handoff_skills)
        for skill_id in all_ids:
            _require_receipt_skill_id(skill_id)
        if len(set(self.candidate_skills)) != len(self.candidate_skills):
            raise ValueError("receipt candidate IDs must be unique")
        if not set(self.preliminary_selected_skills).issubset(self.candidate_skills):
            raise ValueError("receipt preliminary IDs must be candidates")
        if not set(self.full_handoff_skills).issubset(self.candidate_skills):
            raise ValueError("receipt handoff IDs must be candidates")

        selected_ids = []
        for skill_id, reason in self._selected_skills:
            _require_receipt_skill_id(skill_id)
            _require_receipt_text(reason, "selection reason")
            selected_ids.append(skill_id)
        if len(set(selected_ids)) != len(selected_ids):
            raise ValueError("receipt selected IDs must be unique")
        if not set(selected_ids).issubset(self.full_handoff_skills):
            raise ValueError("receipt selected IDs require full handoff")
        if (self.selection_status == "selected") != bool(selected_ids):
            raise ValueError("receipt status and selected skills are inconsistent")
        for need, reason in (*self._execution_needs, *self._unmet_execution_needs):
            _require_receipt_text(need, "execution need")
            _require_receipt_text(reason, "execution need reason")
        if self.supporting_selection_status == "not_required" and (
            self._execution_needs or self._selected_supporting_capabilities or self._unmet_execution_needs
        ):
            raise ValueError("not_required receipt cannot contain supporting decisions")
        if self.supporting_selection_status == "selected" and not self._selected_supporting_capabilities:
            raise ValueError("selected supporting status requires a selected provider")
        if self.supporting_selection_status == "no_matching_supporting_capability" and self._selected_supporting_capabilities:
            raise ValueError("no matching supporting status cannot contain selected providers")
        provider_ids = []
        for kind, provider_id, purpose in self._selected_supporting_capabilities:
            if kind not in {"mcp", "builtin_tool", "app", "plugin"}:
                raise ValueError("receipt has unsupported provider kind")
            _require_receipt_skill_id(provider_id)
            _require_receipt_text(purpose, "supporting purpose")
            provider_ids.append(provider_id)
        if len(set(provider_ids)) != len(provider_ids):
            raise ValueError("receipt selected provider IDs must be unique")
        for provider_id, tool_ids in self.expanded_provider_tool_ids:
            _require_receipt_skill_id(provider_id)
            for tool_id in tool_ids:
                _require_receipt_skill_id(tool_id)

    @property
    def selected_skills(self) -> tuple[dict[str, str], ...]:
        """回傳不含 private instruction 的公開 selected ID/reason。"""

        return tuple({"id": skill_id, "reason": reason} for skill_id, reason in self._selected_skills)

    def selection_payload(self) -> dict[str, object]:
        """取得 renderer 可用的核心 selection payload，不暴露 receipt 私有欄位。"""

        return {
            "task_summary": self.task_summary,
            "selected_skills": list(self.selected_skills),
            "selection_status": self.selection_status,
        }

    def to_mapping(self) -> dict[str, object]:
        """輸出完整 receipt mapping；只包含 bounded routing evidence。"""

        result = {
            "router_invoked": self.router_invoked,
            "contract_version": self.contract_version,
            "task_summary": self.task_summary,
            "candidate_skills": list(self.candidate_skills),
            "preliminary_selected_skills": list(self.preliminary_selected_skills),
            "full_handoff_skills": list(self.full_handoff_skills),
            "selected_skills": list(self.selected_skills),
            "selection_status": self.selection_status,
            "expanded_retrieval": self.expanded_retrieval,
            "correction": self.correction,
            "selection_state": self.selection_state,
        }
        result.update(
            {
                "decision_contract_version": V02_DECISION_RECEIPT_CONTRACT_VERSION,
                "task_analysis": None if self._task_analysis is None else json.loads(self._task_analysis),
                "execution_needs": [
                    {"need": need, "reason": reason} for need, reason in self._execution_needs
                ],
                "supporting_selection_status": self.supporting_selection_status,
                "selected_supporting_capabilities": [
                    {"kind": kind, "canonical_provider_id": provider_id, "purpose": purpose}
                    for kind, provider_id, purpose in self._selected_supporting_capabilities
                ],
                "unmet_execution_needs": [
                    {"need": need, "reason": reason}
                    for need, reason in self._unmet_execution_needs
                ],
                "skill_context_fingerprint": self.skill_context_fingerprint,
                "supporting_context_fingerprint": self.supporting_context_fingerprint,
                "supporting_digest_fingerprints": [
                    {"provider_id": provider_id, "fingerprint": fingerprint}
                    for provider_id, fingerprint in self.supporting_digest_fingerprints
                ],
                "selected_provider_readiness": [
                    {
                        "provider_id": provider_id,
                        "kind": kind,
                        "readiness": {
                            "presence": presence,
                            "availability": availability,
                            "authorization": authorization,
                            "connection": connection,
                            "runtime_callable": runtime_callable,
                        },
                        "provenance": list(provenance),
                    }
                    for provider_id, kind, presence, availability, authorization, connection, runtime_callable, provenance
                    in self.selected_provider_readiness
                ],
                "supporting_detail_expansion_used": self.supporting_detail_expansion_used,
                "expanded_provider_tool_ids": [
                    {"provider_id": provider_id, "tool_ids": list(tool_ids)}
                    for provider_id, tool_ids in self.expanded_provider_tool_ids
                ],
                "skill_metrics": None if self.skill_metrics is None else dict(self.skill_metrics),
                "supporting_metrics": None if self.supporting_metrics is None else dict(self.supporting_metrics),
            }
        )
        return result

    def __getitem__(self, key: str) -> object:
        """保留 Mapping 介面，讓既有 route consumer 可逐步遷移至 receipt。"""

        return self.to_mapping()[key]

    def __iter__(self) -> Iterator[str]:
        """迭代公開 receipt keys，不迭代 private handoff content。"""

        return iter(self.to_mapping())

    def __len__(self) -> int:
        """回傳公開 receipt 欄位數。"""

        return len(self.to_mapping())


@dataclass(frozen=True)
class SelectionRouteInput:
    """production route 的 caller/Codex contract input，不保存 private inventory output。"""

    task_summary: str
    skill_roots: tuple[Path, ...]
    preliminary_skill_ids: tuple[str, ...]
    final_selection: Mapping[str, object]
    work_parts: tuple[str, ...] = ()
    explicit_skill_ids: tuple[str, ...] = ()
    correction_skill_ids: tuple[str, ...] = ()
    expanded_retrieval: bool = False
    known_enriched_profiles: tuple[object, ...] = ()
    runtime: DiscoveryResult | None = None
    cli: DiscoveryResult | None = None
    manual: DiscoveryResult | None = None
    # v0.2 Phase 4 structured decision/finalization inputs；前四個欄位維持 beta.4 positional contract。
    validated_decision_payloads: object | None = None
    skill_context: object | None = None
    supporting_context: object | None = None
    supporting_provider_declarations: tuple[object, ...] = ()
    supporting_readiness_evidence: tuple[object, ...] = ()
    supporting_selection: Mapping[str, object] | None = None
    supporting_detail_expansion_used: bool = False
    supporting_expanded_provider_tool_ids: tuple[tuple[str, tuple[str, ...]], ...] = ()

    def __post_init__(self) -> None:
        """驗證 production input 的 bounded containers 與明確 Skill roots。"""

        if not isinstance(self.task_summary, str) or not self.task_summary.strip():
            raise ValueError("task_summary must be bounded text")
        if not isinstance(self.skill_roots, tuple):
            object.__setattr__(self, "skill_roots", tuple(self.skill_roots))
        if any(not isinstance(root, Path) for root in self.skill_roots):
            raise ValueError("skill_roots must contain explicit Path values")
        for field_name in (
            "preliminary_skill_ids",
            "work_parts",
            "explicit_skill_ids",
            "correction_skill_ids",
            "known_enriched_profiles",
        ):
            value = getattr(self, field_name)
            if not isinstance(value, tuple):
                object.__setattr__(self, field_name, tuple(value))
        if not isinstance(self.final_selection, Mapping):
            raise ValueError("final_selection must be a mapping")
        if not isinstance(self.expanded_retrieval, bool):
            raise ValueError("expanded_retrieval must be a boolean")
        for field_name in (
            "supporting_provider_declarations",
            "supporting_readiness_evidence",
        ):
            value = getattr(self, field_name)
            if not isinstance(value, tuple):
                object.__setattr__(self, field_name, tuple(value))
        if self.supporting_selection is not None and not isinstance(self.supporting_selection, Mapping):
            raise ValueError("supporting_selection must be a mapping or null")
        if not isinstance(self.supporting_detail_expansion_used, bool):
            raise ValueError("supporting_detail_expansion_used must be a boolean")
        if not isinstance(self.supporting_expanded_provider_tool_ids, tuple):
            object.__setattr__(self, "supporting_expanded_provider_tool_ids", tuple(self.supporting_expanded_provider_tool_ids))


def route(request: SelectionRouteInput) -> SelectionReceipt:
    """執行唯一 production contract，回傳已通過 Python validation 的新版 output。"""

    if not isinstance(request, SelectionRouteInput):
        raise TypeError("legacy RouterInput is not a production selection path")

    # 延遲 import 避免 inventory/selection 的既有 controller hard gate 形成循環依賴。
    from .inventory import ProfileCache, refresh_skill_inventory
    from .selection import (
        apply_correction,
        expanded_retrieve,
        handoff_full_instructions,
        prepare_selection,
        preliminary_select,
        validate_selection,
    )
    from .route_context import (
        ValidatedDecisionPayloads,
        SkillRouteContext,
        prepare_route_context,
        validate_decision_payloads,
    )
    from .supporting_context import (
        SupportingRouteContext,
        prepare_supporting_context,
        supporting_selection_status,
        validate_supporting_decision,
    )

    decision_payloads: ValidatedDecisionPayloads | None = None
    task_summary = request.task_summary
    phase4 = request.validated_decision_payloads is not None
    if phase4:
        decision_payloads = (
            request.validated_decision_payloads
            if isinstance(request.validated_decision_payloads, ValidatedDecisionPayloads)
            else validate_decision_payloads(request.validated_decision_payloads)  # type: ignore[arg-type]
        )
        task_summary = decision_payloads.task_analysis.task_summary
        if request.task_summary != task_summary:
            raise ValueError("task_summary compatibility projection does not match TaskAnalysis")
        if decision_payloads.skill_selection is None:
            raise ValueError("v0.2 route requires validated skill_selection")
        if not _public_equal(request.final_selection, decision_payloads.skill_selection.to_mapping()):
            raise ValueError("final_selection does not match validated skill_selection")
        if not isinstance(request.skill_context, SkillRouteContext):
            raise TypeError("v0.2 route requires SkillRouteContext")
        current_skill_context = prepare_route_context(
                decision_payloads.task_analysis,
                skill_roots=request.skill_roots,
                task_summary=task_summary,
                work_parts=request.work_parts,
                explicit_skill_ids=request.explicit_skill_ids,
                known_enriched_profiles=request.known_enriched_profiles,
                expanded_retrieval=request.expanded_retrieval,
                runtime=request.runtime,
                cli=request.cli,
                manual=request.manual,
        )
        if current_skill_context.context_fingerprint != request.skill_context.context_fingerprint:
            raise ValueError("Skill context fingerprint is stale")

    inventory = refresh_skill_inventory(
        request.skill_roots,
        cache=ProfileCache(),
        runtime=request.runtime,
        cli=request.cli,
        manual=request.manual,
    )
    preparation = prepare_selection(
        inventory,
        task_summary,
        work_parts=request.work_parts,
        explicit_skill_ids=request.explicit_skill_ids,
        known_enriched_profiles=request.known_enriched_profiles,
    )

    preliminary = preliminary_select(preparation, request.preliminary_skill_ids)
    handoffs = handoff_full_instructions(inventory, preliminary)

    # expanded retrieval 是 caller/Codex 已判斷需要的 bounded state transition；
    # 它不會替換 final selected IDs，也不會重新進入 keyword ranking。
    working_preparation = preparation
    if request.expanded_retrieval:
        working_preparation = expanded_retrieve(
            inventory,
            preparation,
            work_parts=request.work_parts,
            explicit_skill_ids=request.explicit_skill_ids,
            known_enriched_profiles=request.known_enriched_profiles,
        )

    state = working_preparation.state.start_applicability_check()
    if request.correction_skill_ids:
        correction = preliminary_select(working_preparation, request.correction_skill_ids)
        correction_handoffs = handoff_full_instructions(inventory, correction)
        handoffs = (*handoffs, *correction_handoffs)
        state = apply_correction(state, correction.skill_ids, handoffs=handoffs)
    else:
        state = replace(state, handoffs=handoffs)

    validated = validate_selection(
        request.final_selection,
        inventory=inventory,
        handoffs=handoffs,
        state=state,
    )
    finalized_state = state.finalize(tuple(item["id"] for item in validated["selected_skills"]))

    supporting_context = None
    supporting_decision = None
    supporting_status = "not_required"
    selected_supporting = ()
    unmet_execution_needs = ()
    if phase4:
        assert decision_payloads is not None
        needs = decision_payloads.execution_needs
        if not needs:
            if any(
                value is not None
                for value in (request.supporting_context, request.supporting_selection)
            ) or request.supporting_provider_declarations or request.supporting_readiness_evidence or request.supporting_detail_expansion_used or request.supporting_expanded_provider_tool_ids:
                raise ValueError("Provider context/selection is forbidden when execution_needs is empty")
            if decision_payloads.final_supporting_decision is not None:
                raise ValueError("final supporting decision is forbidden when execution_needs is empty")
        else:
            if decision_payloads.final_supporting_decision is None:
                raise ValueError("v0.2 route requires final supporting decision")
            if not isinstance(request.supporting_context, SupportingRouteContext):
                raise TypeError("non-empty execution_needs require SupportingRouteContext")
            supporting_context = request.supporting_context
            # Rebuild only from supplied Host declarations/evidence; no endpoint is invoked.
            current_supporting_context = prepare_supporting_context(
                needs,
                provider_declarations=request.supporting_provider_declarations,
                readiness_evidence=request.supporting_readiness_evidence,
            )
            if current_supporting_context.context_fingerprint != supporting_context.context_fingerprint:
                raise ValueError("Supporting context fingerprint is stale")
            if request.supporting_detail_expansion_used != bool(request.supporting_expanded_provider_tool_ids):
                raise ValueError("detail expansion flag and expanded IDs are inconsistent")
            if request.supporting_expanded_provider_tool_ids:
                available_details = {
                    item.provider_id: set(item.callable_tool_ids)
                    for item in supporting_context.detail_references
                }
                for provider_id, tool_ids in request.supporting_expanded_provider_tool_ids:
                    if provider_id not in available_details or not set(tool_ids).issubset(available_details[provider_id]):
                        raise ValueError("expanded detail IDs must reference exact prepared tools")
            selection_payload = request.supporting_selection
            if selection_payload is None and decision_payloads.final_supporting_decision is not None:
                selection_payload = {
                    "request_detail": None,
                    "final_selection": decision_payloads.final_supporting_decision.to_mapping(),
                }
            if selection_payload is None:
                raise ValueError("non-empty execution_needs require supporting selection")
            supporting_decision = validate_supporting_decision(
                selection_payload,
                needs,
                supporting_context,
                detail_expansion_used=request.supporting_detail_expansion_used,
                require_final=True,
            )
            if supporting_decision.final_selection is None:
                raise ValueError("route() cannot finalize unresolved request_detail")
            if (
                decision_payloads.final_supporting_decision is not None
                and not _public_equal(
                    decision_payloads.final_supporting_decision.to_mapping(),
                    supporting_decision.final_selection.to_mapping(),
                )
            ):
                raise ValueError("supporting selection does not match validated decision payload")
            supporting_status = supporting_selection_status(needs, supporting_decision.final_selection)
            selected_supporting = tuple(
                item.to_mapping() for item in supporting_decision.final_selection.selected_supporting_capabilities
            )
            unmet_execution_needs = tuple(
                item.to_mapping() for item in supporting_decision.final_selection.unmet_execution_needs
            )

    task_analysis_mapping = None if decision_payloads is None else decision_payloads.task_analysis.to_mapping()
    execution_needs = () if decision_payloads is None else tuple(item.to_mapping() for item in decision_payloads.execution_needs)
    supporting_digest_fingerprints = ()
    selected_provider_readiness = ()
    supporting_metrics = None
    supporting_context_fingerprint = None
    if phase4 and decision_payloads is not None and not decision_payloads.execution_needs:
        supporting_metrics = {
            "run_state": "not_run",
            "discovered_count": 0,
            "hard_eligible_count": 0,
            "selected_count": 0,
            "digest_total_size": 0,
            "detail_expansion_used": False,
        }
    if supporting_context is not None:
        supporting_context_fingerprint = supporting_context.context_fingerprint
        supporting_digest_fingerprints = tuple(
            (item.provider_id, item.fingerprint) for item in supporting_context.provider_digests
        )
        supporting_metrics = supporting_context.metrics.to_mapping()
        selected_ids = {item["canonical_provider_id"] for item in selected_supporting}
        selected_provider_readiness = tuple(
            (
                evidence.provider_id,
                evidence.kind,
                evidence.presence,
                evidence.availability,
                evidence.authorization,
                evidence.connection,
                evidence.runtime_callable,
                evidence.provenance,
            )
            for evidence in supporting_context.readiness_evidence
            if evidence.provider_id in selected_ids
        )
        supporting_metrics["selected_count"] = len(selected_supporting)
    skill_metrics = None
    if phase4:
        available_count = len(inventory.available_records)
        candidate_count = len(working_preparation.candidates)
        skill_metrics = {
            "available_count": available_count,
            "candidate_count": candidate_count,
            "selected_count": len(validated["selected_skills"]),
            "candidate_reduction_ratio": (
                None if available_count == 0 else (available_count - candidate_count) / available_count
            ),
        }
    return SelectionReceipt._from_route(
        task_summary=validated["task_summary"],
        candidate_skills=tuple(profile.id for profile in working_preparation.candidates),
        preliminary_selected_skills=preliminary.skill_ids,
        full_handoff_skills=tuple(handoff.id for handoff in handoffs),
        selected_skills=validated["selected_skills"],
        selection_status=validated["selection_status"],
        expanded_retrieval=working_preparation.state.budget.expanded_retrievals_used == 1,
        correction=bool(request.correction_skill_ids),
        selection_state=finalized_state.lifecycle,
        task_analysis=task_analysis_mapping,
        execution_needs=execution_needs,
        supporting_selection_status=supporting_status,
        selected_supporting_capabilities=selected_supporting,
        unmet_execution_needs=unmet_execution_needs,
        skill_context_fingerprint=(
            None if request.skill_context is None else request.skill_context.context_fingerprint
        ),
        supporting_context_fingerprint=supporting_context_fingerprint,
        supporting_digest_fingerprints=supporting_digest_fingerprints,
        selected_provider_readiness=selected_provider_readiness,
        supporting_detail_expansion_used=request.supporting_detail_expansion_used,
        expanded_provider_tool_ids=request.supporting_expanded_provider_tool_ids,
        skill_metrics=skill_metrics,
        supporting_metrics=supporting_metrics,
    )


def _public_equal(left: object, right: object) -> bool:
    """比較 structured public payload，不引入 semantic interpretation。"""

    return json.dumps(left, ensure_ascii=False, sort_keys=True, separators=(",", ":")) == json.dumps(
        right,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _require_receipt_skill_id(value: object) -> None:
    """驗證 receipt 內只出現 bounded canonical Skill ID。"""

    if not isinstance(value, str) or _CANONICAL_SKILL_ID.fullmatch(value.strip()) is None:
        raise ValueError("receipt Skill IDs must be canonical IDs")


def _require_receipt_text(value: object, field: str) -> None:
    """拒絕 receipt 內的 path、secret-like metadata 與未界定長文字。"""

    if not isinstance(value, str) or not value.strip() or len(value) > 2048:
        raise ValueError(f"receipt {field} must be bounded text")
    folded = value.casefold()
    if "/" in value or "\\" in value or any(marker in folded for marker in ("api_key=", "password=", "secret=", "token=")):
        raise ValueError(f"receipt {field} contains private or sensitive content")


def _is_controller(record) -> bool:
    """沿用既有 controller/alias hard gate，不參與任務 relevance 或 final ranking。"""

    if record.controller:
        return True
    identifiers = (record.id, record.name, *record.aliases)
    return any(_normalize(value) in _CONTROLLER_ALIASES for value in identifiers)


def _normalize(value: str) -> str:
    """以 Unicode NFKC 與 casefold 固定 controller identifier 比對。"""

    return unicodedata.normalize("NFKC", value).casefold().strip()
