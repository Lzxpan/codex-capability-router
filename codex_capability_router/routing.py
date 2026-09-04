"""Phase 4 唯一 production Skill selection entry point。"""

from __future__ import annotations

from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass, field, replace
import hashlib
import json
from pathlib import Path
import re
import unicodedata

from .models import DiscoveryResult
from .supporting_context import FORMAL_SUPPORTING_PROVIDER_KINDS

# 修改紀錄（2026-08-31，Steve Peng）
# 原始內容：唯一 production route 沒有 Host exposure observability、coverage additions 或 possible-relevance diagnostics。
# 修改原因：Skill availability 改由 trusted-root discovery/handoff safety 決定，Host exposure 不得再成為 formal availability gate。
# 修改後功能：route() 整合 optional typed Host observation、Coverage Check additions handoff、Skill-layer metrics 與 profile-level diagnostics；Router 仍 stateless。

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
# 修改紀錄（2026-09-01，Steve Peng）
# 原始內容：Supporting Receipt 只接受 hard-eligible Provider，selected item 沒有 presence/readiness state，且 unknown provider 會被混入 no-match。
# 修改原因：Optimistic Supporting Provider Selection Upgrade 要保存 PRESENT_UNVERIFIED selection evidence，並讓 no-match 只表示 semantic no-match。
# 修改後功能：route() 接受 selectable Provider digest、輸出 selected readiness state，並保留獨立 execution outcome contract；不執行 Provider endpoint。
# 修改紀錄（2026-09-01，Steve Peng）
# 原始內容：Supporting final selection 沒有 multi-Provider base selection 與 bounded coverage addition evidence。
# 修改原因：coverage-first Provider policy 必須能補回不同 Execution Need 的合理 Provider，且不以 generic fallback 壓掉 specialized capability。
# 修改後功能：route() 保存 Supporting Coverage Check、base Provider IDs 與 additions；不增加 semantic ranking、retry 或 execution loop。
# 修改紀錄（2026-09-01，Steve Peng）
# 原始內容：唯一 route 的 Skill preparation 仍可能只使用 relevance shortlist，Host discovery envelope 也無法進 Supporting context。
# 修改原因：高召回架構需要全 inventory consideration，並讓可信 Host-native/Plugin child discovery 沿用同一條 FINALIZED route。
# 修改後功能：route() 使用 high-recall Skill pool、傳遞 optional discovery envelope，仍不執行 Provider 或改寫 execution safety。
# 修改紀錄（2026-09-01，Steve Peng）
# 原始內容：route() 的 Host discovery input 仍是可由一般 caller 建立的 raw mapping，沒有 session snapshot trust boundary。
# 修改原因：Host Capability Snapshot Bridge 必須由 controller-owned typed envelope 進入 production route，且保留 snapshot audit metrics。
# 修改後功能：新增 HostCapabilitySnapshot typed input validation 與 Supporting context 傳遞；legacy raw adapter 僅保留相容測試，不改 selection 或 execution。

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
_RECEIPT_FINGERPRINT = re.compile(r"^[0-9a-f]{64}$")


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
    _selected_supports: tuple[tuple[tuple[str, int], ...], ...] = field(default=(), repr=False, compare=False)
    _token: object = field(default=None, repr=False, compare=False)
    _task_analysis: str | None = field(default=None, repr=False, compare=False)
    _execution_needs: tuple[tuple[str, str], ...] = field(default=(), repr=False, compare=False)
    supporting_selection_status: str = "not_required"
    _selected_supporting_capabilities: tuple[tuple[str, str, str], ...] = field(default=(), repr=False, compare=False)
    _selected_supporting_provider_evidence: tuple[Mapping[str, object], ...] = field(default=(), repr=False, compare=False)
    _unmet_execution_needs: tuple[tuple[str, str], ...] = field(default=(), repr=False, compare=False)
    skill_context_fingerprint: str | None = None
    supporting_context_fingerprint: str | None = None
    supporting_digest_fingerprints: tuple[tuple[str, str], ...] = ()
    selected_provider_readiness: tuple[tuple[str, str, str, str, str, str, bool, tuple[str, ...]], ...] = ()
    selected_provider_readiness_evidence: tuple[Mapping[str, object], ...] = ()
    supporting_detail_expansion_used: bool = False
    expanded_provider_tool_ids: tuple[tuple[str, tuple[str, ...]], ...] = ()
    skill_metrics: Mapping[str, object] | None = None
    supporting_metrics: Mapping[str, object] | None = None
    possible_relevance_diagnostics: tuple[Mapping[str, str], ...] = ()
    possible_relevance_status: str = "not_requested"
    coverage_additions: tuple[Mapping[str, object], ...] = ()
    coverage_check_used: bool = False
    supporting_preliminary_provider_ids: tuple[str, ...] = ()
    supporting_coverage_additions: tuple[Mapping[str, object], ...] = ()
    supporting_coverage_check_used: bool = False

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
        selected_supporting_provider_evidence: tuple[Mapping[str, object], ...] = (),
        unmet_execution_needs: tuple[Mapping[str, str], ...] = (),
        skill_context_fingerprint: str | None = None,
        supporting_context_fingerprint: str | None = None,
        supporting_digest_fingerprints: tuple[tuple[str, str], ...] = (),
        selected_provider_readiness: tuple[tuple[str, str, str, str, str, str, bool, tuple[str, ...]], ...] = (),
        selected_provider_readiness_evidence: tuple[Mapping[str, object], ...] = (),
        supporting_detail_expansion_used: bool = False,
        expanded_provider_tool_ids: tuple[tuple[str, tuple[str, ...]], ...] = (),
        skill_metrics: Mapping[str, object] | None = None,
        supporting_metrics: Mapping[str, object] | None = None,
        possible_relevance_diagnostics: tuple[Mapping[str, str], ...] = (),
        possible_relevance_status: str = "not_requested",
        coverage_additions: tuple[Mapping[str, object], ...] = (),
        coverage_check_used: bool = False,
        supporting_preliminary_provider_ids: tuple[str, ...] = (),
        supporting_coverage_additions: tuple[Mapping[str, object], ...] = (),
        supporting_coverage_check_used: bool = False,
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
            _selected_supports=tuple(
                tuple((reference["section"], reference["index"]) for reference in item.get("supports", ()))
                for item in selected_skills
            ) if any("supports" in item for item in selected_skills) else (),
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
            _selected_supporting_provider_evidence=tuple(
                dict(item) for item in selected_supporting_provider_evidence
            ),
            _unmet_execution_needs=tuple((item["need"], item["reason"]) for item in unmet_execution_needs),
            skill_context_fingerprint=skill_context_fingerprint,
            supporting_context_fingerprint=supporting_context_fingerprint,
            supporting_digest_fingerprints=tuple(supporting_digest_fingerprints),
            selected_provider_readiness=tuple(selected_provider_readiness),
            selected_provider_readiness_evidence=tuple(dict(item) for item in selected_provider_readiness_evidence),
            supporting_detail_expansion_used=supporting_detail_expansion_used,
            expanded_provider_tool_ids=tuple(expanded_provider_tool_ids),
            skill_metrics=None if skill_metrics is None else dict(skill_metrics),
            supporting_metrics=None if supporting_metrics is None else dict(supporting_metrics),
            possible_relevance_diagnostics=tuple(dict(item) for item in possible_relevance_diagnostics),
            possible_relevance_status=possible_relevance_status,
            coverage_additions=tuple(dict(item) for item in coverage_additions),
            coverage_check_used=coverage_check_used,
            supporting_preliminary_provider_ids=tuple(supporting_preliminary_provider_ids),
            supporting_coverage_additions=tuple(dict(item) for item in supporting_coverage_additions),
            supporting_coverage_check_used=supporting_coverage_check_used,
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
        if self.supporting_selection_status not in {
            "not_required",
            "selected",
            "no_matching_supporting_capability",
            "no_present_supporting_provider",
            "insufficient_capability_metadata",
            "explicit_negative_exclusion",
        }:
            raise ValueError("receipt has unsupported supporting selection status")
        if self.possible_relevance_status not in {"not_requested", "produced", "skipped_context_budget"}:
            raise ValueError("receipt has unsupported possible relevance status")
        for diagnostic in self.possible_relevance_diagnostics:
            if set(diagnostic) != {"id", "availability_state", "possible_relevance_reason", "exclusion_reason"}:
                raise ValueError("possible relevance diagnostic has an invalid schema")
            _require_receipt_skill_id(diagnostic["id"])
            if diagnostic["availability_state"] != "unknown":
                raise ValueError("possible relevance diagnostic must remain unknown")
            _require_receipt_text(diagnostic["possible_relevance_reason"], "possible relevance reason")
            _require_receipt_text(diagnostic["exclusion_reason"], "possible relevance exclusion reason")
        if not isinstance(self.coverage_check_used, bool):
            raise ValueError("coverage_check_used must be boolean")
        if not isinstance(self.supporting_coverage_check_used, bool):
            raise ValueError("supporting_coverage_check_used must be boolean")
        if len(set(self.supporting_preliminary_provider_ids)) != len(self.supporting_preliminary_provider_ids):
            raise ValueError("supporting preliminary provider IDs must be unique")
        for provider_id in self.supporting_preliminary_provider_ids:
            _require_receipt_skill_id(provider_id)
        if self.supporting_coverage_additions and not self.supporting_coverage_check_used:
            raise ValueError("supporting coverage additions require supporting_coverage_check_used=true")
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
        if self._selected_supports and len(self._selected_supports) != len(selected_ids):
            raise ValueError("receipt supports must align with selected skills")
        for references in self._selected_supports:
            for section, index in references:
                if section not in {"work_items", "deliverables", "constraints", "quality_expectations"}:
                    raise ValueError("receipt support section is invalid")
                if isinstance(index, bool) or not isinstance(index, int) or index < 0:
                    raise ValueError("receipt support index is invalid")
        if len(set(selected_ids)) != len(selected_ids):
            raise ValueError("receipt selected IDs must be unique")
        if not set(selected_ids).issubset(self.full_handoff_skills):
            raise ValueError("receipt selected IDs require full handoff")
        if (self.selection_status == "selected") != bool(selected_ids):
            raise ValueError("receipt status and selected skills are inconsistent")
        for addition in self.coverage_additions:
            if set(addition) != {"id", "supports", "distinct_value"}:
                raise ValueError("coverage addition has an invalid receipt schema")
            _require_receipt_skill_id(addition["id"])
            _require_receipt_text(addition["distinct_value"], "coverage distinct value")
            if addition["id"] not in selected_ids:
                raise ValueError("coverage additions require final selected IDs")
            references = addition["supports"]
            if not isinstance(references, list):
                raise ValueError("coverage addition supports must be a list")
            for reference in references:
                if (
                    not isinstance(reference, Mapping)
                    or set(reference) != {"section", "index"}
                    or reference["section"] not in {"work_items", "deliverables", "constraints", "quality_expectations"}
                    or isinstance(reference["index"], bool)
                    or not isinstance(reference["index"], int)
                    or reference["index"] < 0
                ):
                    raise ValueError("coverage addition support reference is invalid")
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
        if self._selected_supporting_provider_evidence and len(self._selected_supporting_provider_evidence) != len(
            self._selected_supporting_capabilities
        ):
            raise ValueError("selected Provider evidence must align with selected providers")
        provider_ids = []
        for kind, provider_id, purpose in self._selected_supporting_capabilities:
            if kind not in FORMAL_SUPPORTING_PROVIDER_KINDS:
                raise ValueError("receipt has unsupported provider kind")
            _require_receipt_skill_id(provider_id)
            _require_receipt_text(purpose, "supporting purpose")
            provider_ids.append(provider_id)
        if len(set(provider_ids)) != len(provider_ids):
            raise ValueError("receipt selected provider IDs must be unique")
        if not set(self.supporting_preliminary_provider_ids).issubset(provider_ids):
            raise ValueError("supporting preliminary providers must be final selected providers")
        execution_need_ids = {need for need, _ in self._execution_needs}
        if self.supporting_coverage_check_used and not execution_need_ids:
            raise ValueError("supporting coverage check requires execution needs")
        addition_provider_ids = []
        for addition in self.supporting_coverage_additions:
            if set(addition) != {"provider_id", "execution_need", "distinct_value"}:
                raise ValueError("supporting coverage addition has an invalid receipt schema")
            provider_id = addition["provider_id"]
            _require_receipt_skill_id(provider_id)
            _require_receipt_text(addition["execution_need"], "supporting coverage execution need")
            _require_receipt_text(addition["distinct_value"], "supporting coverage distinct value")
            if provider_id not in provider_ids:
                raise ValueError("supporting coverage additions require final selected providers")
            if provider_id in self.supporting_preliminary_provider_ids:
                raise ValueError("supporting coverage additions must not duplicate base providers")
            if addition["execution_need"] not in execution_need_ids:
                raise ValueError("supporting coverage addition need must originate from execution needs")
            addition_provider_ids.append(provider_id)
        if len(set(addition_provider_ids)) != len(addition_provider_ids):
            raise ValueError("supporting coverage addition providers must be unique")
        for evidence in self._selected_supporting_provider_evidence:
            legacy_evidence_keys = {
                "kind",
                "canonical_provider_id",
                "presence_state",
                "readiness_state",
                "provenance",
                "digest_fingerprint",
            }
            extended_evidence_keys = legacy_evidence_keys | {
                "hierarchy_state",
                "existence_evidence_state",
                "metadata_quality",
                "raw_external_identity",
            }
            if set(evidence) not in (legacy_evidence_keys, extended_evidence_keys):
                raise ValueError("selected Provider evidence has an invalid schema")
            if evidence["kind"] not in FORMAL_SUPPORTING_PROVIDER_KINDS:
                raise ValueError("selected Provider evidence must use a formal Provider kind")
            _require_receipt_skill_id(evidence["canonical_provider_id"])
            if evidence["presence_state"] not in {"PRESENT", "ABSENT", "EXPLICITLY_BLOCKED"}:
                raise ValueError("selected Provider evidence has an invalid presence state")
            if evidence["readiness_state"] not in {
                "VERIFIED_READY",
                "PRESENT_UNVERIFIED",
                "KNOWN_UNAVAILABLE",
            }:
                raise ValueError("selected Provider evidence has an invalid readiness state")
            if evidence["presence_state"] != "PRESENT" or evidence["readiness_state"] == "KNOWN_UNAVAILABLE":
                raise ValueError("selected Provider evidence is not selectable")
            if "hierarchy_state" in evidence and evidence["hierarchy_state"] not in {None, "KNOWN", "UNKNOWN"}:
                raise ValueError("selected Provider evidence has an invalid hierarchy state")
            if "existence_evidence_state" in evidence and not isinstance(evidence["existence_evidence_state"], str):
                raise ValueError("selected Provider evidence has an invalid existence evidence state")
            if "metadata_quality" in evidence and evidence["metadata_quality"] not in {
                "SUFFICIENT",
                "SPARSE",
                "OPAQUE",
                "INSUFFICIENT_CAPABILITY_METADATA",
            }:
                raise ValueError("selected Provider evidence has an invalid metadata quality")
            if "raw_external_identity" in evidence:
                _require_receipt_text(evidence["raw_external_identity"], "raw Host identity")
            if not isinstance(evidence["provenance"], list):
                raise ValueError("selected Provider provenance must be a list")
            for item in evidence["provenance"]:
                _require_receipt_text(item, "selected Provider provenance")
            if not isinstance(evidence["digest_fingerprint"], str) or _RECEIPT_FINGERPRINT.fullmatch(
                evidence["digest_fingerprint"]
            ) is None:
                raise ValueError("selected Provider digest fingerprint is invalid")
        if self._selected_supporting_provider_evidence:
            for selected, evidence in zip(self._selected_supporting_capabilities, self._selected_supporting_provider_evidence):
                if selected[0] != evidence["kind"] or selected[1] != evidence["canonical_provider_id"]:
                    raise ValueError("selected Provider evidence identity does not match selection")
        for provider_id, tool_ids in self.expanded_provider_tool_ids:
            _require_receipt_skill_id(provider_id)
            for tool_id in tool_ids:
                _require_receipt_skill_id(tool_id)
        for evidence in self.selected_provider_readiness_evidence:
            _validate_provider_readiness_evidence(evidence)

    @property
    def selected_skills(self) -> tuple[dict[str, object], ...]:
        """回傳不含 private instruction 的公開 selected ID/reason。"""

        result: list[dict[str, object]] = []
        for index, (skill_id, reason) in enumerate(self._selected_skills):
            item: dict[str, object] = {"id": skill_id, "reason": reason}
            if self._selected_supports:
                item["supports"] = [
                    {"section": section, "index": item_index}
                    for section, item_index in self._selected_supports[index]
                ]
            result.append(item)
        return tuple(result)

    def selection_payload(self) -> dict[str, object]:
        """取得 renderer 可用的核心 selection payload，不暴露 receipt 私有欄位。"""

        return {
            "task_summary": self.task_summary,
            "selected_skills": list(self.selected_skills),
            "selection_status": self.selection_status,
        }

    @property
    def receipt_fingerprint(self) -> str:
        """回傳可供 ExecutionAttempt 綁定的 finalized Receipt fingerprint。"""

        payload = self.to_mapping(include_fingerprint=False)
        encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def to_mapping(self, *, include_fingerprint: bool = True) -> dict[str, object]:
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
                    self._selected_supporting_mapping(index, kind, provider_id, purpose)
                    for index, (kind, provider_id, purpose) in enumerate(self._selected_supporting_capabilities)
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
                "selected_provider_readiness_evidence": [
                    dict(item) for item in self.selected_provider_readiness_evidence
                ],
                "supporting_detail_expansion_used": self.supporting_detail_expansion_used,
                "expanded_provider_tool_ids": [
                    {"provider_id": provider_id, "tool_ids": list(tool_ids)}
                    for provider_id, tool_ids in self.expanded_provider_tool_ids
                ],
                "skill_metrics": None if self.skill_metrics is None else dict(self.skill_metrics),
                "supporting_metrics": None if self.supporting_metrics is None else dict(self.supporting_metrics),
                "possible_relevance_diagnostics": [dict(item) for item in self.possible_relevance_diagnostics],
                "possible_relevance_status": self.possible_relevance_status,
                "coverage_additions": [dict(item) for item in self.coverage_additions],
                "coverage_check_used": self.coverage_check_used,
                "supporting_preliminary_provider_ids": list(self.supporting_preliminary_provider_ids),
                "supporting_coverage_additions": [
                    dict(item) for item in self.supporting_coverage_additions
                ],
                "supporting_coverage_check_used": self.supporting_coverage_check_used,
            }
        )
        if include_fingerprint:
            result["receipt_fingerprint"] = self.receipt_fingerprint
        return result

    def _selected_supporting_mapping(
        self,
        index: int,
        kind: str,
        provider_id: str,
        purpose: str,
    ) -> dict[str, object]:
        """合併 selected Provider 與 Router readiness evidence，不改寫 LLM decision payload。"""

        result: dict[str, object] = {
            "kind": kind,
            "canonical_provider_id": provider_id,
            "purpose": purpose,
        }
        if self._selected_supporting_provider_evidence:
            evidence = self._selected_supporting_provider_evidence[index]
            result.update(
                {
                    "presence_state": evidence["presence_state"],
                    "readiness_state": evidence["readiness_state"],
                    "provenance": list(evidence["provenance"]),
                    "digest_fingerprint": evidence["digest_fingerprint"],
                }
            )
            for field_name in (
                "hierarchy_state",
                "existence_evidence_state",
                "metadata_quality",
                "raw_external_identity",
            ):
                if field_name in evidence:
                    result[field_name] = evidence[field_name]
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
    # Host availability evidence is an internal typed channel; arbitrary mappings are rejected.
    host_exposure: object | None = None
    finalize_host_exposure: object | None = None
    possible_relevance_reasons: Mapping[str, str] | None = None
    possible_relevance_serialized_budget_bytes: int | None = None
    coverage_additions: object = ()
    coverage_check_used: bool = False
    # v0.2 Phase 4 structured decision/finalization inputs；前四個欄位維持 beta.4 positional contract。
    validated_decision_payloads: object | None = None
    skill_context: object | None = None
    supporting_context: object | None = None
    supporting_provider_declarations: tuple[object, ...] = ()
    supporting_readiness_evidence: tuple[object, ...] = ()
    supporting_selection: Mapping[str, object] | None = None
    supporting_detail_expansion_used: bool = False
    supporting_expanded_provider_tool_ids: tuple[tuple[str, tuple[str, ...]], ...] = ()
    supporting_preliminary_provider_ids: tuple[str, ...] = ()
    supporting_coverage_additions: object = ()
    supporting_coverage_check_used: bool = False
    # Host discovery envelopes are optional; they are never queried or executed by route().
    host_capability_snapshot: object | None = None
    host_native_provider_registry: object = ()
    plugin_manifests: tuple[object, ...] = ()
    # beta.7 Skill plan/snapshot 由 controller/session lifecycle 建立；route 只重用 immutable snapshot。
    skill_root_plan: object | None = None
    skill_inventory_snapshot: object | None = None

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
        if self.host_exposure is not None:
            from .host_exposure import HostSkillExposureEnvelope

            if not isinstance(self.host_exposure, HostSkillExposureEnvelope):
                raise TypeError("host_exposure must be a trusted HostSkillExposureEnvelope")
        if self.finalize_host_exposure is not None:
            from .host_exposure import HostSkillExposureEnvelope

            if not isinstance(self.finalize_host_exposure, HostSkillExposureEnvelope):
                raise TypeError("finalize_host_exposure must be a trusted HostSkillExposureEnvelope")
        if self.finalize_host_exposure is not None and self.host_exposure is None:
            raise ValueError("finalize Host observation requires a prepare observation")
        if self.possible_relevance_reasons is not None:
            if not isinstance(self.possible_relevance_reasons, Mapping):
                raise ValueError("possible relevance reasons must be a mapping")
            object.__setattr__(self, "possible_relevance_reasons", dict(self.possible_relevance_reasons))
        if self.possible_relevance_serialized_budget_bytes is not None:
            if isinstance(self.possible_relevance_serialized_budget_bytes, bool) or not isinstance(self.possible_relevance_serialized_budget_bytes, int) or self.possible_relevance_serialized_budget_bytes < 0:
                raise ValueError("possible relevance budget must be a non-negative integer or null")
            from .inventory import DEFAULT_POSSIBLE_RELEVANCE_SERIALIZED_BUDGET_BYTES

            if self.possible_relevance_serialized_budget_bytes != DEFAULT_POSSIBLE_RELEVANCE_SERIALIZED_BUDGET_BYTES:
                raise ValueError("possible relevance budget is a fixed internal value")
        if not isinstance(self.coverage_check_used, bool):
            raise ValueError("coverage_check_used must be boolean")
        if isinstance(self.coverage_additions, (str, bytes)) or not isinstance(self.coverage_additions, (tuple, list)):
            raise ValueError("coverage_additions must be a sequence")
        object.__setattr__(self, "coverage_additions", tuple(self.coverage_additions))
        if self.coverage_additions and not self.coverage_check_used:
            raise ValueError("coverage additions require coverage_check_used=true")
        if self.host_capability_snapshot is not None:
            from .host_snapshot import HostCapabilitySnapshot

            if not isinstance(self.host_capability_snapshot, HostCapabilitySnapshot):
                raise TypeError("host_capability_snapshot must be a trusted HostCapabilitySnapshot")
        if self.skill_root_plan is not None:
            from .skill_plan import RootPlanSnapshot

            if not isinstance(self.skill_root_plan, RootPlanSnapshot):
                raise TypeError("skill_root_plan must be a RootPlanSnapshot")
        if self.skill_inventory_snapshot is not None:
            from .inventory import SkillInventorySnapshot

            if not isinstance(self.skill_inventory_snapshot, SkillInventorySnapshot):
                raise TypeError("skill_inventory_snapshot must be a SkillInventorySnapshot")
            if self.skill_root_plan is not None and (
                self.skill_inventory_snapshot.root_plan_fingerprint != self.skill_root_plan.fingerprint
            ):
                raise ValueError("skill inventory snapshot does not match skill root plan")
        if isinstance(self.host_native_provider_registry, (str, bytes)) or not isinstance(
            self.host_native_provider_registry, (tuple, list, Mapping)
        ):
            raise ValueError("host_native_provider_registry must be a trusted sequence or mapping")
        if not isinstance(self.plugin_manifests, tuple):
            object.__setattr__(self, "plugin_manifests", tuple(self.plugin_manifests))
        if any(not isinstance(item, Mapping) for item in self.plugin_manifests):
            raise ValueError("plugin_manifests must contain mappings")
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
        if not isinstance(self.supporting_preliminary_provider_ids, tuple):
            object.__setattr__(self, "supporting_preliminary_provider_ids", tuple(self.supporting_preliminary_provider_ids))
        if any(not isinstance(item, str) or not item.strip() for item in self.supporting_preliminary_provider_ids):
            raise ValueError("supporting preliminary provider IDs must be non-empty strings")
        if len(set(self.supporting_preliminary_provider_ids)) != len(self.supporting_preliminary_provider_ids):
            raise ValueError("supporting preliminary provider IDs must be unique")
        if not isinstance(self.supporting_coverage_check_used, bool):
            raise ValueError("supporting_coverage_check_used must be a boolean")
        if isinstance(self.supporting_coverage_additions, (str, bytes)) or not isinstance(
            self.supporting_coverage_additions, (tuple, list)
        ):
            raise ValueError("supporting_coverage_additions must be a sequence")
        object.__setattr__(self, "supporting_coverage_additions", tuple(self.supporting_coverage_additions))
        if self.supporting_coverage_additions and not self.supporting_coverage_check_used:
            raise ValueError("supporting coverage additions require supporting_coverage_check_used=true")


def prepare_route_input_from_controller_registry(
    request: SelectionRouteInput,
    controller_registry: Sequence[Mapping[str, object]],
    *,
    snapshot_id: str,
    session_scope: str,
    source: str = "controller-session-registry",
    provenance: Sequence[str] = (),
) -> SelectionRouteInput:
    """將 controller-owned current-session registry 接到同一條 production route。

    參數：`request` 是尚未附加 Host snapshot 的 immutable route input，
    `controller_registry` 是 controller 已完成 trust boundary 的 public definitions。
    回傳值會把 typed `HostCapabilitySnapshot` 放入 `host_capability_snapshot`；不接受
    task summary、work items 或 keywords，避免 snapshot membership 依任務改變。本函式
    只準備既有 `route()` 的輸入，不建立第二套路由、不呼叫 Host tool。
    """

    if not isinstance(request, SelectionRouteInput):
        raise TypeError("request must be a SelectionRouteInput")
    if request.host_capability_snapshot is not None:
        raise ValueError("request already contains a Host capability snapshot")
    from .host_snapshot import prepare_host_capability_snapshot

    snapshot = prepare_host_capability_snapshot(
        controller_registry,
        snapshot_id=snapshot_id,
        session_scope=session_scope,
        source=source,
        provenance=provenance or ("host-controller-registry",),
    )
    return replace(request, host_capability_snapshot=snapshot)


def route(request: SelectionRouteInput) -> SelectionReceipt:
    """執行唯一 production contract，回傳已通過 Python validation 的新版 output。"""

    if not isinstance(request, SelectionRouteInput):
        raise TypeError("legacy RouterInput is not a production selection path")

    # 延遲 import 避免 inventory/selection 的既有 controller hard gate 形成循環依賴。
    from .inventory import ProfileCache, refresh_skill_inventory, refresh_skill_inventory_snapshot
    from .selection import (
        apply_correction,
        expanded_retrieve,
        handoff_full_instructions,
        handoff_with_selected_skill_refresh,
        prepare_selection,
        preliminary_select,
        validate_coverage_additions,
        validate_selection,
    )
    from .inventory import (
        DEFAULT_POSSIBLE_RELEVANCE_SERIALIZED_BUDGET_BYTES,
        build_possible_relevance_diagnostics,
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
        validate_supporting_coverage_additions,
        validate_supporting_decision,
    )

    decision_payloads: ValidatedDecisionPayloads | None = None
    task_summary = request.task_summary
    skill_snapshot = request.skill_inventory_snapshot
    if skill_snapshot is None and request.skill_root_plan is not None:
        skill_snapshot = refresh_skill_inventory_snapshot(
            request.skill_root_plan,
            runtime=request.runtime,
            cli=request.cli,
            manual=request.manual,
            host_exposure=request.host_exposure,
            plugin_manifests=request.plugin_manifests,
        )
    phase4 = request.validated_decision_payloads is not None
    if not phase4 and (
        request.coverage_additions
        or request.coverage_check_used
        or request.possible_relevance_reasons is not None
        or request.possible_relevance_serialized_budget_bytes is not None
        or request.supporting_preliminary_provider_ids
        or request.supporting_coverage_additions
        or request.supporting_coverage_check_used
    ):
        raise ValueError("v0.2 coverage evidence requires validated TaskAnalysis payloads")
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
            host_exposure=request.host_exposure,
            plugin_manifests=request.plugin_manifests,
            skill_root_plan=request.skill_root_plan,
            skill_inventory_snapshot=skill_snapshot,
        )
        if current_skill_context.context_fingerprint != request.skill_context.context_fingerprint:
            raise ValueError("Skill context fingerprint is stale")

    if skill_snapshot is not None:
        inventory = skill_snapshot.inventory
    else:
        inventory = refresh_skill_inventory(
            request.skill_roots,
            cache=ProfileCache(),
            runtime=request.runtime,
            cli=request.cli,
            manual=request.manual,
            host_exposure=request.host_exposure,
            plugin_manifests=request.plugin_manifests,
        )
    task_analysis_items = () if decision_payloads is None else decision_payloads.task_analysis.retrieval_items()
    preparation = prepare_selection(
        inventory,
        task_summary,
        work_parts=request.work_parts,
        explicit_skill_ids=request.explicit_skill_ids,
        known_enriched_profiles=request.known_enriched_profiles,
        task_analysis_items=task_analysis_items,
        high_recall=True,
    )

    preliminary = preliminary_select(preparation, request.preliminary_skill_ids)

    def handoff(selected: object) -> tuple[object, ...]:
        nonlocal inventory, skill_snapshot
        if skill_snapshot is None:
            return handoff_full_instructions(inventory, selected)  # type: ignore[arg-type]
        recovered = handoff_with_selected_skill_refresh(skill_snapshot, selected)  # type: ignore[arg-type]
        skill_snapshot = recovered.snapshot
        inventory = recovered.snapshot.inventory
        return recovered.handoffs

    handoffs = handoff(preliminary)

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
            task_analysis_items=task_analysis_items,
        )

    state = working_preparation.state.start_applicability_check()
    if request.correction_skill_ids:
        correction = preliminary_select(working_preparation, request.correction_skill_ids)
        correction_handoffs = handoff(correction)
        handoffs = (*handoffs, *correction_handoffs)
        state = apply_correction(state, correction.skill_ids, handoffs=handoffs)
    else:
        state = replace(state, handoffs=handoffs)

    schema_validated = validate_selection(
        request.final_selection,
        task_analysis=None if decision_payloads is None else decision_payloads.task_analysis,
    )
    coverage_additions = validate_coverage_additions(
        request.coverage_additions,
        candidate_ids=tuple(profile.id for profile in working_preparation.candidates),
        selected_ids=(*request.preliminary_skill_ids, *request.correction_skill_ids),
        task_analysis=None if decision_payloads is None else decision_payloads.task_analysis,
    )
    addition_ids = tuple(item.id for item in coverage_additions)
    selected_schema_ids = {item["id"] for item in schema_validated["selected_skills"]}
    if not set(addition_ids).issubset(selected_schema_ids):
        raise ValueError("coverage additions require additions applicability confirmation in final selection")
    if addition_ids:
        addition_preliminary = preliminary_select(working_preparation, addition_ids)
        handoffs = (*handoffs, *handoff(addition_preliminary))
        # 修改紀錄（2026-08-31，Steve Peng）
        # 原始內容：Coverage Check additions 的 handoff 只傳給 final validator，route state 未同步。
        # 修改原因：FINALIZED state 必須完整記錄所有 selected Skill 的 handoff，避免 additions 成為 state 外的旁路。
        # 修改後功能：將一次 Coverage Check additions handoff 納入同一 immutable route state。
        state = replace(state, handoffs=handoffs)

    validated = validate_selection(
        request.final_selection,
        inventory=inventory,
        handoffs=handoffs,
        state=state,
        task_analysis=None if decision_payloads is None else decision_payloads.task_analysis,
    )
    supporting_context = None
    supporting_decision = None
    supporting_status = "not_required"
    selected_supporting = ()
    unmet_execution_needs = ()
    supporting_coverage_additions = ()
    if phase4:
        assert decision_payloads is not None
        needs = decision_payloads.execution_needs
        if not needs:
            if any(
                value is not None
                for value in (request.supporting_context, request.supporting_selection)
            ) or request.supporting_provider_declarations or request.supporting_readiness_evidence or request.host_capability_snapshot is not None or request.host_native_provider_registry or request.plugin_manifests or request.supporting_detail_expansion_used or request.supporting_expanded_provider_tool_ids:
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
                host_capability_snapshot=request.host_capability_snapshot,
                host_native_registry=request.host_native_provider_registry,
                plugin_manifests=request.plugin_manifests,
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
            supporting_status = supporting_selection_status(needs, supporting_decision.final_selection, supporting_context)
            selected_supporting = tuple(
                item.to_mapping() for item in supporting_decision.final_selection.selected_supporting_capabilities
            )
            unmet_execution_needs = tuple(
                item.to_mapping() for item in supporting_decision.final_selection.unmet_execution_needs
            )
            supporting_coverage_additions = validate_supporting_coverage_additions(
                request.supporting_coverage_additions,
                candidate_ids=tuple(item.provider_id for item in supporting_context.provider_digests),
                selected_ids=request.supporting_preliminary_provider_ids,
                execution_needs=needs,
            )
            selected_provider_ids = {
                item["canonical_provider_id"] for item in selected_supporting
            }
            if not set(request.supporting_preliminary_provider_ids).issubset(selected_provider_ids):
                raise ValueError("supporting preliminary providers must be final selected providers")
            if not {
                item.provider_id for item in supporting_coverage_additions
            }.issubset(selected_provider_ids):
                raise ValueError("supporting coverage additions require final selected providers")

    selected_final_ids = tuple(item["id"] for item in validated["selected_skills"])
    # Host exposure 僅是 optional observability；formal FINALIZE 仍依賴 trusted-root
    # discovery、full handoff、applicability 與 content fingerprint gates。
    finalized_state = state.finalize(selected_final_ids)

    task_analysis_mapping = None if decision_payloads is None else decision_payloads.task_analysis.to_mapping()
    execution_needs = () if decision_payloads is None else tuple(item.to_mapping() for item in decision_payloads.execution_needs)
    supporting_digest_fingerprints = ()
    selected_provider_readiness = ()
    selected_provider_readiness_evidence = ()
    selected_supporting_provider_evidence = ()
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
                "present_count": 0,
                "selectable_count": 0,
                "verified_ready_count": 0,
                "present_unverified_count": 0,
                "metadata_insufficient_count": 0,
                "explicit_negative_count": 0,
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
            if evidence.provider_id in selected_ids and hasattr(evidence, "presence")
        )
        selected_provider_readiness_evidence = tuple(
            evidence.to_mapping()
            for evidence in supporting_context.readiness_evidence
            if evidence.provider_id in selected_ids and not hasattr(evidence, "presence")
        )
        digest_by_id = {item.provider_id: item for item in supporting_context.provider_digests}
        selected_supporting_provider_evidence = tuple(
            {
                "kind": item["kind"],
                "canonical_provider_id": item["canonical_provider_id"],
                "presence_state": digest_by_id[item["canonical_provider_id"]].presence_state,
                "readiness_state": digest_by_id[item["canonical_provider_id"]].readiness_state,
                "provenance": list(digest_by_id[item["canonical_provider_id"]].provenance),
                "digest_fingerprint": digest_by_id[item["canonical_provider_id"]].fingerprint,
                "hierarchy_state": digest_by_id[item["canonical_provider_id"]].hierarchy_state,
                "existence_evidence_state": digest_by_id[item["canonical_provider_id"]].existence_evidence_state.value,
                "metadata_quality": digest_by_id[item["canonical_provider_id"]].metadata_quality.value,
                "raw_external_identity": (
                    digest_by_id[item["canonical_provider_id"]].raw_external_identity
                    or digest_by_id[item["canonical_provider_id"]].provider_id
                ),
            }
            for item in selected_supporting
        )
        supporting_metrics["selected_count"] = len(selected_supporting)
        supporting_metrics["plausible_count"] = len(selected_supporting)
        supporting_metrics["provider_plausible_total"] = len(selected_supporting)
    skill_metrics = None
    possible_relevance_diagnostics = ()
    possible_relevance_status = "not_requested"
    if phase4:
        present_records = inventory.present_records or inventory.available_records
        available_count = len(present_records)
        candidate_count = len(working_preparation.candidates)
        analysis = decision_payloads.task_analysis if decision_payloads is not None else None
        indexed_count = 0 if analysis is None else len(analysis.indexed_items())
        supported_refs = _skill_support_references(validated, analysis)
        supported_count = len(supported_refs)
        unknown_profiles = working_preparation.unknown_profiles
        if request.possible_relevance_reasons is not None:
            possible_relevance_diagnostics, possible_relevance_status = build_possible_relevance_diagnostics(
                unknown_profiles,
                request.possible_relevance_reasons,
                budget_bytes=DEFAULT_POSSIBLE_RELEVANCE_SERIALIZED_BUDGET_BYTES,
            )
        skill_metrics = {
            "discovered_skill_count": len(inventory.profiles),
            "trusted_root_skill_count": len(inventory.trusted_root_skill_ids),
            "host_exposed_skill_count": (
                None if request.host_exposure is None else len(inventory.host_exposed_skill_ids)
            ),
            "router_available_skill_count": len(present_records),
            "candidate_skill_count": candidate_count,
            "selected_skill_count": len(validated["selected_skills"]),
            "task_analysis_indexed_item_count": indexed_count,
            "skill_supported_item_count": supported_count,
            "skill_unreferenced_item_count": max(indexed_count - supported_count, 0),
            "possibly_relevant_unavailable_count": len(possible_relevance_diagnostics),
            "coverage_check_used": request.coverage_check_used,
            "skill_discovered_total": len(inventory.profiles),
            "skill_trusted_total": len(inventory.trusted_root_skill_ids),
            "skill_available_total": candidate_count,
            "skill_semantically_considered_total": (
                0
                if working_preparation.inventory_sweep is None
                else len(working_preparation.inventory_sweep.considered_ids)
            ),
            "skill_plausible_total": len(validated["selected_skills"]),
            "skill_selected_total": len(validated["selected_skills"]),
            "skill_never_considered_total": (
                0
                if working_preparation.inventory_sweep is None
                else len(working_preparation.inventory_sweep.never_considered_ids)
            ),
            "skill_sweep_batch_count": (
                0
                if working_preparation.inventory_sweep is None
                else working_preparation.inventory_sweep.batch_count
            ),
            "skill_sweep_fingerprint": (
                None
                if working_preparation.inventory_sweep is None
                else working_preparation.inventory_sweep.fingerprint
            ),
            # beta.4 aliases retained for read compatibility.
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
        selected_supporting_provider_evidence=selected_supporting_provider_evidence,
        unmet_execution_needs=unmet_execution_needs,
        skill_context_fingerprint=(
            None if request.skill_context is None else request.skill_context.context_fingerprint
        ),
        supporting_context_fingerprint=supporting_context_fingerprint,
        supporting_digest_fingerprints=supporting_digest_fingerprints,
        selected_provider_readiness=selected_provider_readiness,
        selected_provider_readiness_evidence=selected_provider_readiness_evidence,
        supporting_detail_expansion_used=request.supporting_detail_expansion_used,
        expanded_provider_tool_ids=request.supporting_expanded_provider_tool_ids,
        skill_metrics=skill_metrics,
        possible_relevance_diagnostics=tuple(item.to_mapping() for item in possible_relevance_diagnostics),
        possible_relevance_status=possible_relevance_status,
        coverage_additions=tuple(item.to_mapping() for item in coverage_additions),
        coverage_check_used=request.coverage_check_used,
        supporting_preliminary_provider_ids=request.supporting_preliminary_provider_ids,
        supporting_coverage_additions=tuple(item.to_mapping() for item in supporting_coverage_additions),
        supporting_coverage_check_used=request.supporting_coverage_check_used,
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


def _skill_support_references(
    validated: Mapping[str, object],
    task_analysis: object,
) -> set[tuple[str, int]]:
    """只依 structured supports 計算 reference facts，不判斷語意 coverage。"""

    if task_analysis is None:
        return set()
    references: set[tuple[str, int]] = set()
    for item in validated.get("selected_skills", []):
        if not isinstance(item, Mapping):
            continue
        for reference in item.get("supports", []):
            if isinstance(reference, Mapping):
                references.add((reference["section"], reference["index"]))
    return references


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


def _validate_provider_readiness_evidence(value: Mapping[str, object]) -> None:
    """Validate typed App/MCP evidence without backfilling generic auth fields."""

    if not isinstance(value, Mapping):
        raise ValueError("provider readiness evidence must be a mapping")
    kind = value.get("kind")
    common = {"kind", "provider_id", "readiness_source", "provenance", "fingerprint"}
    if kind == "app":
        expected = common | {
            "accessible",
            "configured_enabled",
            "runtime_enabled",
            "callable",
            "metadata_readable",
            "runtime_name",
            "runtime_evidence_available",
            "presence_state",
            "readiness_state",
        }
        if set(value) != expected:
            raise ValueError("App readiness evidence has an invalid schema")
        for field_name in (
            "accessible",
            "configured_enabled",
            "runtime_enabled",
            "callable",
            "metadata_readable",
            "runtime_evidence_available",
        ):
            if not isinstance(value[field_name], bool):
                raise ValueError("App readiness evidence boolean is invalid")
        if value["presence_state"] != "PRESENT":
            raise ValueError("App readiness evidence must describe a present instance")
        if value["readiness_state"] not in {"VERIFIED_READY", "PRESENT_UNVERIFIED", "KNOWN_UNAVAILABLE"}:
            raise ValueError("App readiness evidence has an invalid readiness state")
        if value["runtime_name"] is not None:
            _require_receipt_text(value["runtime_name"], "App runtime name")
    elif kind == "mcp":
        expected = common | {
            "runtime_status",
            "auth_status",
            "callable_tool_ids",
            "plugin_id",
            "presence_state",
            "readiness_state",
        }
        if set(value) != expected:
            raise ValueError("MCP readiness evidence has an invalid schema")
        if value["runtime_status"] is not None:
            _require_receipt_text(value["runtime_status"], "MCP runtime status")
        _require_receipt_text(value["auth_status"], "MCP auth status")
        tool_ids = value["callable_tool_ids"]
        if not isinstance(tool_ids, list):
            raise ValueError("MCP readiness evidence tool IDs must be a list")
        for tool_id in tool_ids:
            _require_receipt_skill_id(tool_id)
        if value["plugin_id"] is not None:
            _require_receipt_skill_id(value["plugin_id"])
        if value["presence_state"] != "PRESENT":
            raise ValueError("MCP readiness evidence must describe a present instance")
        if value["readiness_state"] not in {"VERIFIED_READY", "PRESENT_UNVERIFIED", "KNOWN_UNAVAILABLE"}:
            raise ValueError("MCP readiness evidence has an invalid readiness state")
    else:
        raise ValueError("provider readiness evidence kind is not formal")
    _require_receipt_skill_id(value["provider_id"])
    if value["readiness_source"] not in {"app/installed", "mcpServerStatus/list"}:
        raise ValueError("provider readiness source is not an official Host method")
    provenance = value["provenance"]
    if not isinstance(provenance, list):
        raise ValueError("provider readiness provenance must be a list")
    for item in provenance:
        _require_receipt_text(item, "provider readiness provenance")
    if not isinstance(value["fingerprint"], str) or _RECEIPT_FINGERPRINT.fullmatch(value["fingerprint"]) is None:
        raise ValueError("provider readiness fingerprint is invalid")


def _is_controller(record) -> bool:
    """沿用既有 controller/alias hard gate，不參與任務 relevance 或 final ranking。"""

    if record.controller:
        return True
    identifiers = (record.id, record.name, *record.aliases)
    return any(_normalize(value) in _CONTROLLER_ALIASES for value in identifiers)


def _normalize(value: str) -> str:
    """以 Unicode NFKC 與 casefold 固定 controller identifier 比對。"""

    return unicodedata.normalize("NFKC", value).casefold().strip()
