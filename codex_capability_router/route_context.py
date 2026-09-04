"""v0.2 Skill-side route context 與 validated decision payload contract。"""

# 修改紀錄（2026-08-26，Steve Peng）
# 原始內容：validated decision payload foundation 僅包含 TaskAnalysis 與 Skill selection。
# 修改原因：Phase 4 需要以同一 immutable payload 承載 Execution Needs 與 final Supporting decision。
# 修改後功能：新增 strict Execution Needs/final decision projection；empty needs 拒絕 Provider decision/context，未新增 semantic selection。

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
from typing import TYPE_CHECKING

from .models import CapabilityRecord, DiscoveryResult
if TYPE_CHECKING:
    from .host_exposure import HostSkillExposureEnvelope
from .inventory import (
    BasicProfile,
    EnrichedProfile,
    ProfileCache,
    SkillInventorySnapshot,
    refresh_skill_inventory_snapshot,
    refresh_skill_inventory,
)
from .skill_plan import RootPlanSnapshot
from .routing import _is_controller
from .selection import prepare_selection, validate_selection
from .supporting_context import (
    ExecutionNeed,
    SupportingFinalSelection,
    normalize_execution_needs,
    prepare_supporting_context,
    validate_supporting_final_selection_payload,
)
from .task_analysis import TaskAnalysis, validate_task_analysis

# 修改紀錄（2026-08-31，Steve Peng）
# 原始內容：Skill context 只有 available/candidate/selected legacy metrics，selection item 也沒有 TaskAnalysis supports reference。
# 修改原因：v0.2 coverage upgrade 需要保留 structured coverage evidence，同時維持 context read-only、stateless 與既有 compatibility projection。
# 修改後功能：加入 supports、Host exposed/Router available 及 Skill-layer reference metrics；不進行 semantic coverage 判斷。
# 修改紀錄（2026-09-02，Steve Peng）
# 原始內容：Skill profile projection 沒有公開 metadata quality，存在但描述稀疏的 Skill 無法被診斷。
# 修改原因：beta.3 讓 metadata 只影響品質標示，不影響 semantic consideration。
# 修改後功能：route context 保留 SUFFICIENT/SPARSE/OPAQUE quality；full handoff validation 不變。
# 修改紀錄（2026-09-01，Steve Peng）
# 原始內容：正式 Skill context 的 candidate 仍可能來自 top-k relevance retrieval。
# 修改原因：高召回 acceptance 要求 discovered available Skill 全部進 deterministic semantic consideration pool。
# 修改後功能：v0.2 context 使用完整 digest sweep metrics 與 zero-never-considered invariant；不執行 Skill。


ROUTE_CONTEXT_CONTRACT_VERSION = "v0.2-skill-route-context-v1"
DECISION_PAYLOAD_CONTRACT_VERSION = "v0.2-validated-decision-payloads-v1"
_CANONICAL_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]*$")
_FINGERPRINT = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class ValidatedSkillSelection:
    """既有 Skill selection output 的 immutable、public structured projection。"""

    task_summary: str
    selected_skills: tuple[tuple[str, str], ...]
    selection_status: str
    supports: tuple[tuple[tuple[str, int], ...], ...] = ()

    def __post_init__(self) -> None:
        """重用既有 selection validator，避免建立第二套 Skill semantics。"""

        if self.supports and len(self.supports) != len(self.selected_skills):
            raise ValueError("supports must align with selected_skills")
        payload = self.to_mapping()
        validated = validate_selection(payload)
        object.__setattr__(self, "task_summary", validated["task_summary"])
        object.__setattr__(
            self,
            "selected_skills",
            tuple((item["id"], item["reason"]) for item in validated["selected_skills"]),
        )
        parsed_supports = tuple(
            tuple((reference["section"], reference["index"]) for reference in item.get("supports", ()))
            for item in validated["selected_skills"]
        )
        object.__setattr__(self, "supports", parsed_supports if any(parsed_supports) else ())
        object.__setattr__(self, "selection_status", validated["selection_status"])

    def to_mapping(self) -> dict[str, object]:
        """輸出新的 selection mapping/list 副本。"""

        items: list[dict[str, object]] = []
        for index, (skill_id, reason) in enumerate(self.selected_skills):
            item: dict[str, object] = {"id": skill_id, "reason": reason}
            if self.supports:
                item["supports"] = [
                    {"section": section, "index": item_index}
                    for section, item_index in self.supports[index]
                ]
            items.append(item)
        return {
            "task_summary": self.task_summary,
            "selected_skills": items,
            "selection_status": self.selection_status,
        }


@dataclass(frozen=True)
class ValidatedDecisionPayloads:
    """v0.2 immutable structured decision payload；Provider 只保留 final decision。"""

    task_analysis: TaskAnalysis
    skill_selection: ValidatedSkillSelection | None = None
    execution_needs: tuple[ExecutionNeed, ...] = ()
    final_supporting_decision: SupportingFinalSelection | None = None
    contract_version: str = DECISION_PAYLOAD_CONTRACT_VERSION

    def __post_init__(self) -> None:
        """固定 payload contract，拒絕 Provider 欄位與 TaskAnalysis mismatch。"""

        if not isinstance(self.task_analysis, TaskAnalysis):
            raise TypeError("validated decision payloads require TaskAnalysis")
        if self.skill_selection is not None and not isinstance(self.skill_selection, ValidatedSkillSelection):
            raise TypeError("skill_selection must be a ValidatedSkillSelection or null")
        if self.skill_selection is not None and self.skill_selection.task_summary != self.task_analysis.task_summary:
            raise ValueError("skill selection task_summary does not match TaskAnalysis")
        if self.skill_selection is not None:
            validate_selection(self.skill_selection.to_mapping(), task_analysis=self.task_analysis)
        object.__setattr__(self, "execution_needs", normalize_execution_needs(self.execution_needs))
        if self.final_supporting_decision is not None and not isinstance(
            self.final_supporting_decision, SupportingFinalSelection
        ):
            raise TypeError("final_supporting_decision must be a SupportingFinalSelection or null")
        if not self.execution_needs and self.final_supporting_decision is not None:
            raise ValueError("supporting decision is forbidden when execution_needs is empty")
        if self.contract_version != DECISION_PAYLOAD_CONTRACT_VERSION:
            raise ValueError("unsupported validated decision payload contract version")

    def to_mapping(self) -> dict[str, object]:
        """輸出只含 public structured results 的 payload mapping。"""

        result = {
            "contract_version": self.contract_version,
            "task_analysis": self.task_analysis.to_mapping(),
            "skill_selection": None if self.skill_selection is None else self.skill_selection.to_mapping(),
            "execution_needs": [item.to_mapping() for item in self.execution_needs],
        }
        if self.execution_needs:
            result["final_supporting_decision"] = (
                None
                if self.final_supporting_decision is None
                else self.final_supporting_decision.to_mapping()
            )
        return result


def validate_decision_payloads(payload: Mapping[str, object]) -> ValidatedDecisionPayloads:
    """驗證 v0.2 structured decision payload，不接受 raw Provider/context payload。"""

    legacy_keys = {"contract_version", "task_analysis", "skill_selection"}
    current_base_keys = legacy_keys | {"execution_needs"}
    current_keys = current_base_keys | {"final_supporting_decision"}
    if not isinstance(payload, Mapping) or set(payload) not in (legacy_keys, current_base_keys, current_keys):
        raise ValueError("validated decision payloads have an invalid schema")
    if payload["contract_version"] != DECISION_PAYLOAD_CONTRACT_VERSION:
        raise ValueError("validated decision payloads have an unsupported version")
    task_analysis = _coerce_task_analysis(payload["task_analysis"])
    selection_payload = payload["skill_selection"]
    selection = None
    if selection_payload is not None:
        if not isinstance(selection_payload, Mapping):
            raise ValueError("skill_selection must be an object or null")
        validated = validate_selection(selection_payload, task_analysis=task_analysis)
        selection = ValidatedSkillSelection(
            task_summary=validated["task_summary"],
            selected_skills=tuple((item["id"], item["reason"]) for item in validated["selected_skills"]),
            selection_status=validated["selection_status"],
            supports=tuple(
                tuple((reference["section"], reference["index"]) for reference in item.get("supports", ()))
                for item in validated["selected_skills"]
            ),
        )
    execution_needs = normalize_execution_needs(payload.get("execution_needs", ()))
    final_supporting_decision = validate_supporting_final_selection_payload(
        payload.get("final_supporting_decision")
    )
    return ValidatedDecisionPayloads(
        task_analysis=task_analysis,
        skill_selection=selection,
        execution_needs=execution_needs,
        final_supporting_decision=final_supporting_decision,
    )


@dataclass(frozen=True)
class SkillContextMetrics:
    """Skill candidate reduction observation，不代表 semantic selection 結果。"""

    available_count: int
    candidate_count: int
    selected_count: int = 0
    candidate_reduction_ratio: float | None = None
    discovered_skill_count: int | None = None
    host_exposed_skill_count: int | None = None
    router_available_skill_count: int | None = None
    task_analysis_indexed_item_count: int = 0
    skill_supported_item_count: int = 0
    skill_unreferenced_item_count: int = 0
    possibly_relevant_unavailable_count: int = 0
    coverage_check_used: bool = False
    # 新增欄位置於既有欄位之後，保留既有 positional compatibility。
    trusted_root_skill_count: int | None = None
    semantically_considered_count: int = 0
    plausible_count: int = 0
    never_considered_count: int = 0
    sweep_batch_count: int = 0
    sweep_fingerprint: str | None = None

    def __post_init__(self) -> None:
        """驗證 bounded counts，並在 available=0 時固定 ratio=null。"""

        # 舊版直接建立 metrics 的呼叫沒有 sweep 欄位；視為其候選已進入
        # 舊 contract 的 consideration，避免相容性 constructor 產生假違規。
        if (
            self.candidate_count
            and self.semantically_considered_count == 0
            and self.plausible_count == 0
            and self.never_considered_count == 0
            and self.sweep_fingerprint is None
        ):
            object.__setattr__(self, "semantically_considered_count", self.candidate_count)

        for field_name in ("available_count", "candidate_count", "selected_count"):
            value = getattr(self, field_name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{field_name} must be a non-negative integer")
        for field_name in (
            "discovered_skill_count",
            "trusted_root_skill_count",
            "host_exposed_skill_count",
            "router_available_skill_count",
            "task_analysis_indexed_item_count",
            "skill_supported_item_count",
            "skill_unreferenced_item_count",
            "possibly_relevant_unavailable_count",
            "semantically_considered_count",
            "plausible_count",
            "never_considered_count",
            "sweep_batch_count",
        ):
            value = getattr(self, field_name)
            if value is not None and (isinstance(value, bool) or not isinstance(value, int) or value < 0):
                raise ValueError(f"{field_name} must be a non-negative integer or null")
        if not isinstance(self.coverage_check_used, bool):
            raise ValueError("coverage_check_used must be boolean")
        if self.skill_supported_item_count + self.skill_unreferenced_item_count > self.task_analysis_indexed_item_count:
            raise ValueError("Skill reference counts exceed indexed TaskAnalysis items")
        if self.discovered_skill_count is not None and self.router_available_skill_count is not None:
            if self.router_available_skill_count > self.discovered_skill_count:
                raise ValueError("router_available_skill_count cannot exceed discovered_skill_count")
        # package/runtime existence union 可以包含沒有 filesystem handoff root 的
        # record，因此不可再要求 semantic available count <= trusted roots。
        # trusted_root_skill_count 僅作來源觀測；handoff safety 仍由 selection
        # validator 對 available_records 個別驗證。
        if self.candidate_count > self.available_count:
            raise ValueError("candidate_count cannot exceed available_count")
        if self.selected_count > self.candidate_count:
            raise ValueError("selected_count cannot exceed candidate_count")
        if self.semantically_considered_count > self.candidate_count:
            raise ValueError("semantically_considered_count cannot exceed candidate_count")
        if self.plausible_count > self.semantically_considered_count:
            raise ValueError("plausible_count cannot exceed semantically_considered_count")
        if self.never_considered_count > self.candidate_count:
            raise ValueError("never_considered_count cannot exceed candidate_count")
        if self.semantically_considered_count + self.never_considered_count != self.candidate_count:
            raise ValueError("Skill sweep counts must account for every candidate")
        if self.sweep_fingerprint is not None and _FINGERPRINT.fullmatch(self.sweep_fingerprint) is None:
            raise ValueError("sweep_fingerprint must be a SHA-256 digest or null")
        expected = (
            None
            if self.available_count == 0
            else (self.available_count - self.candidate_count) / self.available_count
        )
        if self.candidate_reduction_ratio is not None and self.candidate_reduction_ratio != expected:
            raise ValueError("candidate_reduction_ratio is inconsistent with counts")
        object.__setattr__(self, "candidate_reduction_ratio", expected)

    def to_mapping(self) -> dict[str, object]:
        """輸出 deterministic metrics mapping。"""

        return {
            "available_count": self.available_count,
            "candidate_count": self.candidate_count,
            "selected_count": self.selected_count,
            "candidate_reduction_ratio": self.candidate_reduction_ratio,
            "discovered_skill_count": self.discovered_skill_count,
            "trusted_root_skill_count": self.trusted_root_skill_count,
            "host_exposed_skill_count": self.host_exposed_skill_count,
            "router_available_skill_count": (
                self.available_count if self.router_available_skill_count is None else self.router_available_skill_count
            ),
            "candidate_skill_count": self.candidate_count,
            "selected_skill_count": self.selected_count,
            "task_analysis_indexed_item_count": self.task_analysis_indexed_item_count,
            "skill_supported_item_count": self.skill_supported_item_count,
            "skill_unreferenced_item_count": self.skill_unreferenced_item_count,
            "possibly_relevant_unavailable_count": self.possibly_relevant_unavailable_count,
            "coverage_check_used": self.coverage_check_used,
            "skill_discovered_total": self.discovered_skill_count,
            "skill_trusted_total": self.trusted_root_skill_count,
            "skill_available_total": self.available_count,
            "skill_semantically_considered_total": self.semantically_considered_count,
            "skill_plausible_total": self.plausible_count,
            "skill_selected_total": self.selected_count,
            "skill_never_considered_total": self.never_considered_count,
            "sweep_batch_count": self.sweep_batch_count,
            "sweep_fingerprint": self.sweep_fingerprint,
        }


@dataclass(frozen=True)
class SkillEligibility:
    """單一 canonical Skill 的 deterministic hard eligibility facts。"""

    id: str
    status: str
    eligible: bool
    controller: bool
    routing_support: bool
    source: str
    provenance: tuple[str, ...]
    record_fingerprint: str

    def __post_init__(self) -> None:
        """驗證 canonical ID、status 與 record digest 格式。"""

        if not isinstance(self.id, str) or _CANONICAL_ID.fullmatch(self.id) is None:
            raise ValueError("Skill eligibility requires a canonical ID")
        if not isinstance(self.status, str) or not self.status:
            raise ValueError("Skill eligibility requires a status")
        if not isinstance(self.eligible, bool) or not isinstance(self.controller, bool) or not isinstance(self.routing_support, bool):
            raise ValueError("Skill eligibility flags must be boolean")
        if not isinstance(self.source, str) or not self.source.strip():
            raise ValueError("Skill eligibility requires a source")
        if _FINGERPRINT.fullmatch(self.record_fingerprint) is None:
            raise ValueError("Skill eligibility requires a record fingerprint")
        object.__setattr__(self, "provenance", tuple(self.provenance))

    def to_mapping(self) -> dict[str, object]:
        """輸出不含 private path 的 eligibility facts。"""

        return {
            "id": self.id,
            "status": self.status,
            "eligible": self.eligible,
            "controller": self.controller,
            "routing_support": self.routing_support,
            "source": self.source,
            "provenance": list(self.provenance),
            "record_fingerprint": self.record_fingerprint,
        }


@dataclass(frozen=True)
class SkillHandoffReference:
    """Candidate-scoped handoff reference；不保存完整 SKILL.md 或 filesystem path。"""

    id: str
    fingerprint: str

    def __post_init__(self) -> None:
        """驗證 handoff reference 只含 canonical ID 與 SHA-256 fingerprint。"""

        if not isinstance(self.id, str) or _CANONICAL_ID.fullmatch(self.id) is None:
            raise ValueError("handoff reference requires a canonical ID")
        if not isinstance(self.fingerprint, str) or _FINGERPRINT.fullmatch(self.fingerprint) is None:
            raise ValueError("handoff reference requires a SHA-256 fingerprint")

    def to_mapping(self) -> dict[str, str]:
        """輸出 public handoff reference。"""

        return {"id": self.id, "fingerprint": self.fingerprint}


@dataclass(frozen=True)
class SkillRouteContext:
    """read-only、stateless、Skill-only 的 v0.2 prepared context。"""

    validated_decision_payloads: ValidatedDecisionPayloads
    candidates: tuple[BasicProfile, ...]
    enriched_profiles: tuple[EnrichedProfile, ...]
    skill_eligibility: tuple[SkillEligibility, ...]
    handoff_references: tuple[SkillHandoffReference, ...]
    skill_fingerprints: tuple[tuple[str, str], ...]
    provenance: tuple[tuple[str, tuple[str, ...]], ...]
    metrics: SkillContextMetrics
    retrieval_rounds: int
    expanded_retrieval: bool
    context_fingerprint: str
    # Host snapshot 僅供 observation/audit，不參與 formal Skill eligibility。
    host_exposure_fingerprint: str | None = None
    # beta.7 cache identity；只保存 digest，不保存 root path 或 SKILL.md body。
    root_plan_fingerprint: str | None = None
    skill_inventory_fingerprint: str | None = None

    @property
    def task_analysis(self) -> TaskAnalysis:
        """取得正式 TaskAnalysis reference。"""

        return self.validated_decision_payloads.task_analysis

    @property
    def task_summary(self) -> str:
        """取得舊 task_summary 的唯讀相容 projection。"""

        return self.task_analysis.task_summary

    def to_mapping(self) -> dict[str, object]:
        """輸出 deterministic、privacy-bounded Skill-side context。"""

        return {
            "contract_version": ROUTE_CONTEXT_CONTRACT_VERSION,
            "validated_decision_payloads": self.validated_decision_payloads.to_mapping(),
            "candidates": [_profile_mapping(profile) for profile in self.candidates],
            "enriched_profiles": [_enriched_mapping(profile) for profile in self.enriched_profiles],
            "skill_eligibility": [item.to_mapping() for item in self.skill_eligibility],
            "handoff_references": [item.to_mapping() for item in self.handoff_references],
            "skill_fingerprints": [
                {"id": skill_id, "fingerprint": fingerprint}
                for skill_id, fingerprint in self.skill_fingerprints
            ],
            "provenance": [
                {"id": skill_id, "sources": list(sources)}
                for skill_id, sources in self.provenance
            ],
            "metrics": self.metrics.to_mapping(),
            "retrieval_rounds": self.retrieval_rounds,
            "expanded_retrieval": self.expanded_retrieval,
            "context_fingerprint": self.context_fingerprint,
            "host_exposure_fingerprint": self.host_exposure_fingerprint,
            "root_plan_fingerprint": self.root_plan_fingerprint,
            "skill_inventory_fingerprint": self.skill_inventory_fingerprint,
        }

    def __post_init__(self) -> None:
        """驗證 immutable context 邊界，不保存 inventory 或 provider state。"""

        if not isinstance(self.validated_decision_payloads, ValidatedDecisionPayloads):
            raise TypeError("route context requires validated decision payloads")
        if self.retrieval_rounds not in (1, 2):
            raise ValueError("retrieval_rounds must be 1 or 2")
        if not isinstance(self.expanded_retrieval, bool):
            raise ValueError("expanded_retrieval must be boolean")
        if _FINGERPRINT.fullmatch(self.context_fingerprint) is None:
            raise ValueError("route context requires a SHA-256 context fingerprint")
        if self.host_exposure_fingerprint is not None and _FINGERPRINT.fullmatch(self.host_exposure_fingerprint) is None:
            raise ValueError("host exposure fingerprint must be a SHA-256 digest or null")
        for name, value in (
            ("root plan fingerprint", self.root_plan_fingerprint),
            ("Skill inventory fingerprint", self.skill_inventory_fingerprint),
        ):
            if value is not None and _FINGERPRINT.fullmatch(value) is None:
                raise ValueError(f"{name} must be a SHA-256 digest or null")
        object.__setattr__(self, "candidates", tuple(self.candidates))
        object.__setattr__(self, "enriched_profiles", tuple(self.enriched_profiles))
        object.__setattr__(self, "skill_eligibility", tuple(self.skill_eligibility))
        object.__setattr__(self, "handoff_references", tuple(self.handoff_references))
        object.__setattr__(self, "skill_fingerprints", tuple(self.skill_fingerprints))
        object.__setattr__(self, "provenance", tuple((skill_id, tuple(sources)) for skill_id, sources in self.provenance))
        expected = _context_fingerprint(
            decision_payloads=self.validated_decision_payloads,
            candidates=self.candidates,
            enriched_profiles=self.enriched_profiles,
            eligibility=self.skill_eligibility,
            handoff_references=self.handoff_references,
            skill_fingerprints=self.skill_fingerprints,
            provenance=self.provenance,
            metrics=self.metrics,
            retrieval_rounds=self.retrieval_rounds,
            expanded_retrieval=self.expanded_retrieval,
            host_exposure_fingerprint=self.host_exposure_fingerprint,
            root_plan_fingerprint=self.root_plan_fingerprint,
            skill_inventory_fingerprint=self.skill_inventory_fingerprint,
        )
        if self.context_fingerprint != expected:
            raise ValueError("route context fingerprint does not match its contents")


def prepare_route_context(
    task_analysis: TaskAnalysis | Mapping[str, object] | None = None,
    *,
    skill_roots: Sequence[Path],
    task_summary: str | None = None,
    work_parts: Sequence[str] = (),
    explicit_skill_ids: Sequence[str] = (),
    known_enriched_profiles: Sequence[EnrichedProfile] = (),
    expanded_retrieval: bool = False,
    runtime: DiscoveryResult | None = None,
    cli: DiscoveryResult | None = None,
    manual: DiscoveryResult | None = None,
    host_exposure: HostSkillExposureEnvelope | None = None,
    plugin_manifests: Sequence[Mapping[str, object]] = (),
    skill_root_plan: RootPlanSnapshot | None = None,
    skill_inventory_snapshot: SkillInventorySnapshot | None = None,
) -> SkillRouteContext:
    """準備 v0.2 Skill-only context；不呼叫 LLM、不建 Receipt、不接觸 Provider。"""

    analysis = _coerce_task_analysis(task_analysis)
    if task_summary is not None:
        if not isinstance(task_summary, str) or task_summary != analysis.task_summary:
            raise ValueError("task_summary compatibility projection does not match TaskAnalysis")
    if not isinstance(expanded_retrieval, bool):
        raise ValueError("expanded_retrieval must be boolean")
    roots = tuple(skill_roots)
    if any(not isinstance(root, Path) for root in roots):
        raise ValueError("skill_roots must contain explicit Path values")

    if skill_root_plan is not None and not isinstance(skill_root_plan, RootPlanSnapshot):
        raise TypeError("skill_root_plan must be a RootPlanSnapshot")
    if skill_inventory_snapshot is not None and not isinstance(skill_inventory_snapshot, SkillInventorySnapshot):
        raise TypeError("skill_inventory_snapshot must be a SkillInventorySnapshot")
    if skill_inventory_snapshot is not None and skill_root_plan is not None:
        if skill_inventory_snapshot.root_plan_fingerprint != skill_root_plan.fingerprint:
            raise ValueError("Skill inventory snapshot does not match root plan")
    # 正式 v0.2 route 使用完整 digest sweep；不在此處新增 Python semantic selection。
    if skill_inventory_snapshot is not None:
        inventory = skill_inventory_snapshot.inventory
    elif skill_root_plan is not None:
        inventory = refresh_skill_inventory_snapshot(
            skill_root_plan,
            runtime=runtime,
            cli=cli,
            manual=manual,
            host_exposure=host_exposure,
            plugin_manifests=plugin_manifests,
        ).inventory
    else:
        inventory = refresh_skill_inventory(
            roots,
            cache=ProfileCache(),
            runtime=runtime,
            cli=cli,
            manual=manual,
            host_exposure=host_exposure,
            plugin_manifests=plugin_manifests,
        )
    preparation = prepare_selection(
        inventory,
        analysis.task_summary,
        work_parts=work_parts,
        task_analysis_items=analysis.retrieval_items(),
        explicit_skill_ids=explicit_skill_ids,
        known_enriched_profiles=known_enriched_profiles,
        use_expanded=expanded_retrieval,
        high_recall=True,
    )
    candidates = tuple(preparation.candidates)
    present_records = inventory.present_records or inventory.available_records
    present_ids = {
        record.id
        for record in present_records
        if not record.routing_support and not _is_controller(record)
    }
    eligibility = tuple(
        _eligibility(record, record.id in present_ids)
        for record in sorted(inventory.records, key=lambda item: (item.id.casefold(), item.id, item.source))
    )
    handoff_references = tuple(
        SkillHandoffReference(profile.id, profile.fingerprint)
        for profile in sorted(candidates, key=lambda item: (item.id.casefold(), item.id))
    )
    skill_fingerprints = tuple((reference.id, reference.fingerprint) for reference in handoff_references)
    provenance = tuple(
        (
            profile.id,
            tuple(profile.provenance) if profile.provenance else (profile.source,),
        )
        for profile in sorted(candidates, key=lambda item: (item.id.casefold(), item.id))
    )
    metrics = SkillContextMetrics(
        available_count=len(present_records),
        candidate_count=len(candidates),
        selected_count=0,
        discovered_skill_count=len(inventory.profiles),
        trusted_root_skill_count=len(inventory.trusted_root_skill_ids),
        host_exposed_skill_count=(
            None if host_exposure is None else len(inventory.host_exposed_skill_ids)
        ),
        router_available_skill_count=len(present_records),
        task_analysis_indexed_item_count=len(analysis.indexed_items()),
        skill_supported_item_count=0,
        skill_unreferenced_item_count=len(analysis.indexed_items()),
        semantically_considered_count=(
            0 if preparation.inventory_sweep is None else len(preparation.inventory_sweep.considered_ids)
        ),
        plausible_count=0,
        never_considered_count=(
            0 if preparation.inventory_sweep is None else len(preparation.inventory_sweep.never_considered_ids)
        ),
        sweep_batch_count=(0 if preparation.inventory_sweep is None else preparation.inventory_sweep.batch_count),
        sweep_fingerprint=(None if preparation.inventory_sweep is None else preparation.inventory_sweep.fingerprint),
    )
    decision_payloads = ValidatedDecisionPayloads(task_analysis=analysis)
    retrieval_rounds = preparation.state.retrieval_rounds
    expanded_used = preparation.state.budget.expanded_retrievals_used == 1
    fingerprint = _context_fingerprint(
        decision_payloads=decision_payloads,
        candidates=candidates,
        enriched_profiles=preparation.enriched_profiles,
        eligibility=eligibility,
        handoff_references=handoff_references,
        skill_fingerprints=skill_fingerprints,
        provenance=provenance,
        metrics=metrics,
        retrieval_rounds=retrieval_rounds,
        expanded_retrieval=expanded_used,
        host_exposure_fingerprint=(
            None if host_exposure is None else host_exposure.snapshot_fingerprint
        ),
        root_plan_fingerprint=(
            None
            if skill_inventory_snapshot is None and skill_root_plan is None
            else (
                skill_inventory_snapshot.root_plan_fingerprint
                if skill_inventory_snapshot is not None
                else skill_root_plan.fingerprint
            )
        ),
        skill_inventory_fingerprint=(
            None if skill_inventory_snapshot is None else skill_inventory_snapshot.inventory_fingerprint
        ),
    )
    return SkillRouteContext(
        validated_decision_payloads=decision_payloads,
        candidates=candidates,
        enriched_profiles=preparation.enriched_profiles,
        skill_eligibility=eligibility,
        handoff_references=handoff_references,
        skill_fingerprints=skill_fingerprints,
        provenance=provenance,
        metrics=metrics,
        retrieval_rounds=retrieval_rounds,
        expanded_retrieval=expanded_used,
        context_fingerprint=fingerprint,
        host_exposure_fingerprint=(
            None if host_exposure is None else host_exposure.snapshot_fingerprint
        ),
        root_plan_fingerprint=(
            None
            if skill_inventory_snapshot is None and skill_root_plan is None
            else (
                skill_inventory_snapshot.root_plan_fingerprint
                if skill_inventory_snapshot is not None
                else skill_root_plan.fingerprint
            )
        ),
        skill_inventory_fingerprint=(
            None if skill_inventory_snapshot is None else skill_inventory_snapshot.inventory_fingerprint
        ),
    )


def _coerce_task_analysis(value: TaskAnalysis | Mapping[str, object] | None) -> TaskAnalysis:
    """只接受正式 TaskAnalysis 或可驗證的 structured mapping，不從 task_summary 猜測。"""

    if isinstance(value, TaskAnalysis):
        return value
    if isinstance(value, Mapping):
        return validate_task_analysis(value)
    raise ValueError("TaskAnalysis is mandatory for v0.2 route context")


def _eligibility(record: CapabilityRecord, eligible: bool) -> SkillEligibility:
    """將既有 Skill hard gate facts 正規化，不執行 semantic relevance 判斷。"""

    return SkillEligibility(
        id=record.id,
        status=record.status.value,
        eligible=eligible,
        controller=_is_controller(record),
        routing_support=record.routing_support,
        source=record.source,
        provenance=tuple(record.provenance) if record.provenance else (record.source,),
        record_fingerprint=_record_fingerprint(record),
    )


def _record_fingerprint(record: CapabilityRecord) -> str:
    """以 canonical public record mapping 計算 deterministic eligibility digest。"""

    return _sha256(record.to_mapping())


def _context_fingerprint(
    *,
    decision_payloads: ValidatedDecisionPayloads,
    candidates: Sequence[BasicProfile],
    enriched_profiles: Sequence[EnrichedProfile],
    eligibility: Sequence[SkillEligibility],
    handoff_references: Sequence[SkillHandoffReference],
    skill_fingerprints: Sequence[tuple[str, str]],
    provenance: Sequence[tuple[str, tuple[str, ...]]],
    metrics: SkillContextMetrics,
    retrieval_rounds: int,
    expanded_retrieval: bool,
    host_exposure_fingerprint: str | None = None,
    root_plan_fingerprint: str | None = None,
    skill_inventory_fingerprint: str | None = None,
) -> str:
    """固定正式 context input，排除 root path、完整 prompt、SKILL body 與 Provider。"""

    metrics_mapping = metrics.to_mapping()
    # Host exposure 僅是 optional observation；排除其 count 於 formal context
    # identity，避免 Host snapshot 成為 Skill routing gate。
    metrics_mapping["host_exposed_skill_count"] = None
    payload = {
        "contract_version": ROUTE_CONTEXT_CONTRACT_VERSION,
        "validated_decision_payloads": decision_payloads.to_mapping(),
        "candidates": [_profile_mapping(profile) for profile in candidates],
        "enriched_profiles": [_enriched_mapping(profile) for profile in enriched_profiles],
        "skill_eligibility": [item.to_mapping() for item in eligibility],
        "handoff_references": [item.to_mapping() for item in handoff_references],
        "skill_fingerprints": [
            {"id": skill_id, "fingerprint": fingerprint}
            for skill_id, fingerprint in skill_fingerprints
        ],
        "provenance": [
            {"id": skill_id, "sources": list(sources)}
            for skill_id, sources in provenance
        ],
        "metrics": metrics_mapping,
        "retrieval_rounds": retrieval_rounds,
        "expanded_retrieval": expanded_retrieval,
        "root_plan_fingerprint": root_plan_fingerprint,
        "skill_inventory_fingerprint": skill_inventory_fingerprint,
        # Host exposure 僅是 optional observation；snapshot 改變或缺失時，
        # 不得使 formal Skill context 失效。
    }
    return _sha256(payload)


def _profile_mapping(profile: BasicProfile) -> dict[str, object]:
    """將 Basic Profile 轉成不含 path/content 的 public mapping。"""

    return {
        "id": profile.id,
        "name": profile.name,
        "description": profile.description,
        "version": profile.version,
        "status": profile.status.value,
        "source": profile.source,
        "provenance": list(profile.provenance),
        "fingerprint": profile.fingerprint,
        "stale": profile.stale,
        "metadata_quality": profile.metadata_quality.value,
    }


def _enriched_mapping(profile: EnrichedProfile) -> dict[str, object]:
    """將 Enriched Profile 轉成 bounded public mapping。"""

    return {
        "id": profile.id,
        "summary": profile.summary,
        "limitations": list(profile.limitations),
        "requirements": list(profile.requirements),
    }


def _sha256(payload: Mapping[str, object]) -> str:
    """以 canonical JSON 產生 deterministic SHA-256 digest。"""

    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
