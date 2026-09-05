"""Phase 3 新版 Codex Skill Selection Contract。"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
import json
import re

from .inventory import (
    BasicProfile,
    EnrichedProfile,
    RetrievalBudget,
    SelectedSkillRefreshResult,
    SkillInventory,
    SkillInventorySnapshot,
    fingerprint_profile_content,
    refresh_selected_skill_snapshot,
    retrieve_candidates,
)
from .inventory_sweep import InventorySweep, build_inventory_sweep, skill_digest
from .models import CapabilityKind, CapabilityRecord, CapabilityStatus
from .routing import _is_controller
from .task_analysis import TaskAnalysis

# 修改紀錄（2026-08-31，Steve Peng）
# 原始內容：selection contract 沒有四類 TaskAnalysis supports reference 或 Coverage Check addition schema。
# 修改原因：coverage-first 需要公開 bounded coverage evidence，並讓 additions 經 existing candidate、handoff 與 applicability gates。
# 修改後功能：加入 supports/distinct_value validation 與單輪 additions contract；Python 只驗 schema、ID、reference，不判斷語意。

# 修改紀錄（2026-08-21，Steve Peng）
# 原始內容：Phase 1/2 只有 inventory、profile 與 candidate retrieval，沒有新版 selection contract。
# 修改原因：Phase 3 需要在不改舊 production final selector 的前提下，驗證初選、完整 handoff、budget、correction、final validation 與 render 的順序及安全邊界。
# 修改後功能：提供僅供新版 contract 使用的 prepare/select/handoff/state/validate/render API；不呼叫模型、不執行 Skill，也不改動舊 routing path。
# 修改紀錄（2026-08-25，Steve Peng）
# 原始內容：SelectionState 只有次數上限，route 完成後仍可被當成可變的 OPEN state 使用。
# 修改原因：Integration Hardening 要求 Final Selection 後不可 correction、expanded retrieval 或變更 selected Skill。
# 修改後功能：加入 OPEN/FINALIZED lifecycle 與 finalized selected IDs；封存後所有 selection transition 及不同 final payload 都會被拒絕。
# 修改紀錄（2026-09-02，Steve Peng）
# 原始內容：metadata 不足的 resolved Skill 不會進正式 semantic candidate pool。
# 修改原因：beta.3 將 metadata 降為品質欄位；存在且 identity resolved 即必須被考量。
# 修改後功能：正式 selection pool 保留所有 present、非 controller self、非 routing-support Skill；完整 handoff validation 維持不變。
# 修改紀錄（2026-09-01，Steve Peng）
# 原始內容：正式 route 仍以 bounded relevance retrieval 決定 Skill semantic candidate pool。
# 修改原因：高召回原則要求所有 available、metadata-sufficient Skill 至少被 LLM consideration 一次，避免 top-k/tail starvation。
# 修改後功能：新增 high-recall full digest sweep；既有 retrieval API 保留 compatibility，Python 不做 semantic filtering。

SELECTION_STATUSES = frozenset({"selected", "no_matching_skill"})
SELECTION_LIFECYCLES = frozenset({"OPEN", "FINALIZED"})
_FINGERPRINT = re.compile(r"^[0-9a-f]{64}$")
_CANONICAL_SKILL_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]*$")
_SUPPORT_SECTIONS = frozenset({"work_items", "deliverables", "constraints", "quality_expectations"})


@dataclass(frozen=True)
class FullInstructionHandoff:
    """保存初選 Skill 的暫時完整內容與當時 fingerprint，不寫入 Profile cache。"""

    id: str
    fingerprint: str
    instructions: str

    def __post_init__(self) -> None:
        """在 handoff boundary 驗證 ID、SHA-256 格式與完整文字內容。"""

        _require_skill_id(self.id)
        if not isinstance(self.fingerprint, str) or _FINGERPRINT.fullmatch(self.fingerprint) is None:
            raise ValueError("handoff fingerprint must be a SHA-256 hex digest")
        if not isinstance(self.instructions, str) or not self.instructions.strip():
            raise ValueError("handoff instructions must be non-empty text")


@dataclass(frozen=True)
class PreliminarySelection:
    """表示 Codex 從候選 Profile 提出的初選 ID；不代表 final selection。"""

    skill_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class CoverageAddition:
    """Coverage Check 提出的單一 additional Skill 公開證據。"""

    id: str
    supports: tuple[tuple[str, int], ...]
    distinct_value: str

    def to_mapping(self) -> dict[str, object]:
        """輸出不含 chain-of-thought 的 bounded addition mapping。"""

        return {
            "id": self.id,
            "supports": [{"section": section, "index": index} for section, index in self.supports],
            "distinct_value": self.distinct_value,
        }


@dataclass(frozen=True)
class SelectionState:
    """保存 route 的 bounded transition 與 finalized selection immutable state。"""

    budget: RetrievalBudget = field(default_factory=RetrievalBudget)
    retrieval_rounds: int = 1
    applicability_checks: int = 0
    correction_count: int = 0
    handoffs: tuple[FullInstructionHandoff, ...] = ()
    lifecycle: str = "OPEN"
    final_selected_skill_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        """拒絕超過規劃上限的 route state，避免形成 retrieval/review loop。"""

        if self.retrieval_rounds not in (1, 2):
            raise ValueError("retrieval rounds must be 1 or 2")
        if self.applicability_checks not in (0, 1):
            raise ValueError("applicability check count must be 0 or 1")
        if self.correction_count not in (0, 1):
            raise ValueError("correction count must be 0 or 1")
        if self.lifecycle not in SELECTION_LIFECYCLES:
            raise ValueError("selection lifecycle must be OPEN or FINALIZED")
        if self.lifecycle == "OPEN" and self.final_selected_skill_ids:
            raise ValueError("OPEN selection cannot contain finalized Skill IDs")
        _validated_id_tuple(self.final_selected_skill_ids)

    def start_applicability_check(self) -> "SelectionState":
        """開始唯一一次 Final Applicability Check，不建立第二套 reviewer。"""

        self._require_open()
        if self.applicability_checks == 1:
            raise ValueError("applicability check is already complete")
        return replace(self, applicability_checks=1)

    def consume_expanded_retrieval(self) -> "SelectionState":
        """消耗 route 共用的唯一 expanded retrieval，拒絕第三輪 retrieval。"""

        self._require_open()
        if self.retrieval_rounds == 2:
            raise ValueError("expanded retrieval is already complete")
        return replace(
            self,
            budget=self.budget.consume_expanded(),
            retrieval_rounds=2,
        )

    def finalize(self, selected_skill_ids: Sequence[str]) -> "SelectionState":
        """在 final validation 成功後封存選擇；封存後不可再修改 route state。"""

        self._require_open()
        ids = _validated_id_tuple(selected_skill_ids)
        return replace(
            self,
            lifecycle="FINALIZED",
            final_selected_skill_ids=ids,
        )

    @property
    def is_finalized(self) -> bool:
        """回報此 selection state 是否已完成 immutable finalization。"""

        return self.lifecycle == "FINALIZED"

    def _require_open(self) -> None:
        """拒絕 finalized route 的 expanded、correction 或其他 state transition。"""

        if self.lifecycle != "OPEN":
            raise ValueError("selection is finalized; create a new routing request")


@dataclass(frozen=True)
class SelectionPreparation:
    """prepare 輸出的候選、必要 enriched profile 與 route state。"""

    task_summary: str
    candidates: tuple[BasicProfile, ...]
    enriched_profiles: tuple[EnrichedProfile, ...]
    state: SelectionState
    # 新增欄位置於既有 fields 之後，避免破壞直接建立 preparation 的舊呼叫。
    unknown_profiles: tuple[BasicProfile, ...] = ()
    # 高召回正式 route 使用完整 digest sweep；舊 retrieval API 保持相容。
    inventory_sweep: InventorySweep | None = None
    high_recall: bool = False


def prepare_selection(
    inventory: SkillInventory,
    task_summary: str,
    *,
    work_parts: Sequence[str] = (),
    explicit_skill_ids: Sequence[str] = (),
    known_enriched_profiles: Sequence[EnrichedProfile] = (),
    budget: RetrievalBudget | None = None,
    use_expanded: bool = False,
    task_analysis_items: Sequence[str] = (),
    high_recall: bool = False,
) -> SelectionPreparation:
    """準備新版 contract 的候選資料；不執行 Codex，也不做語意 final selection。

    `high_recall=True` 只供正式 v0.2 route 使用：它以完整 present inventory
    建立 deterministic digest batches，不再用 relevance shortlist 決定哪些能力
    有資格被 LLM 看見。既有預設值保留 Phase 2 retrieval compatibility。
    """

    if high_recall:
        return prepare_high_recall_selection(
            inventory,
            task_summary,
            work_parts=work_parts,
            explicit_skill_ids=explicit_skill_ids,
            known_enriched_profiles=known_enriched_profiles,
            budget=budget,
            use_expanded=use_expanded,
            task_analysis_items=task_analysis_items,
        )

    result = retrieve_candidates(
        inventory,
        task_summary,
        work_parts=work_parts,
        explicit_skill_ids=explicit_skill_ids,
        known_enriched_profiles=known_enriched_profiles,
        budget=budget,
        use_expanded=use_expanded,
        task_analysis_items=task_analysis_items,
    )
    return SelectionPreparation(
        task_summary=task_summary,
        candidates=result.candidates,
        unknown_profiles=result.unknown_profiles,
        enriched_profiles=result.enriched_profiles,
        state=SelectionState(
            budget=result.budget,
            retrieval_rounds=1 + result.budget.expanded_retrievals_used,
        ),
    )


def prepare_high_recall_selection(
    inventory: SkillInventory,
    task_summary: str,
    *,
    work_parts: Sequence[str] = (),
    explicit_skill_ids: Sequence[str] = (),
    known_enriched_profiles: Sequence[EnrichedProfile] = (),
    budget: RetrievalBudget | None = None,
    use_expanded: bool = False,
    task_analysis_items: Sequence[str] = (),
) -> SelectionPreparation:
    """建立完整 Skill semantic consideration pool，避免 top-k/tail starvation。

    Python 只做輸入格式、trusted availability、canonical ordering 與 bounded
    batching；Codex 主模型負責 plausible task relevance，且 semantic overlap
    不會由 Python 轉成 exclusion。Python 不做 semantic ranking 或 pruning。
    """

    _require_selection_text(task_summary, "task_summary")
    for value in (*work_parts, *task_analysis_items):
        _require_selection_text(value, "selection work item")
    for value in explicit_skill_ids:
        _require_skill_id(value)
    for profile in known_enriched_profiles:
        if not isinstance(profile, EnrichedProfile):
            raise TypeError("known_enriched_profiles must contain EnrichedProfile values")

    current_budget = budget or RetrievalBudget()
    if use_expanded:
        current_budget = current_budget.consume_expanded()
    # present scope is the semantic universe; available_records remains the
    # legacy full-instruction handoff scope and may be a smaller subset.
    present_records = inventory.present_records or inventory.available_records
    available_ids = {record.id for record in present_records if _eligible_record(record)}
    candidates = tuple(
        sorted(
            (
                profile
                for profile in inventory.profiles
                if profile.id in available_ids
            ),
            key=lambda profile: (profile.id.casefold(), profile.id),
        )
    )
    sweep = build_inventory_sweep(
        tuple(skill_digest(profile) for profile in candidates),
        identity_field="id",
    )
    return SelectionPreparation(
        task_summary=task_summary,
        candidates=candidates,
        unknown_profiles=tuple(
            sorted(
                (
                    profile
                    for profile in inventory.profiles
                    if profile.status == CapabilityStatus.UNKNOWN and profile.id not in available_ids
                ),
                key=lambda profile: (profile.id.casefold(), profile.id),
            )
        ),
        enriched_profiles=tuple(known_enriched_profiles),
        state=SelectionState(
            budget=current_budget,
            retrieval_rounds=1 + current_budget.expanded_retrievals_used,
        ),
        inventory_sweep=sweep,
        high_recall=True,
    )


def expanded_retrieve(
    inventory: SkillInventory,
    preparation: SelectionPreparation,
    *,
    work_parts: Sequence[str] = (),
    explicit_skill_ids: Sequence[str] = (),
    known_enriched_profiles: Sequence[EnrichedProfile] = (),
    task_analysis_items: Sequence[str] = (),
) -> SelectionPreparation:
    """在既有準備資料上最多擴大一次候選，並沿用同一 route state。"""

    next_state = preparation.state.consume_expanded_retrieval()
    if preparation.high_recall:
        return replace(preparation, state=next_state)
    result = retrieve_candidates(
        inventory,
        preparation.task_summary,
        work_parts=work_parts,
        explicit_skill_ids=explicit_skill_ids,
        known_enriched_profiles=(*preparation.enriched_profiles, *known_enriched_profiles),
        budget=preparation.state.budget,
        use_expanded=True,
        task_analysis_items=task_analysis_items,
    )
    if result.budget != next_state.budget:
        raise ValueError("expanded retrieval budget state mismatch")
    return replace(
        preparation,
        candidates=result.candidates,
        unknown_profiles=result.unknown_profiles,
        enriched_profiles=result.enriched_profiles,
        state=next_state,
    )


def _require_selection_text(value: object, field: str) -> None:
    """驗證 bounded public text，不從文字推導 capability 語意。"""

    if not isinstance(value, str) or not value.strip() or len(value) > 4096:
        raise ValueError(f"{field} must be bounded text")


def _skill_metadata_sufficient(profile: BasicProfile) -> bool:
    """確認 Skill 名片足以交給 LLM，不判斷它是否適用 task。"""

    return bool(profile.name.strip() and profile.description and profile.description.strip())


def preliminary_select(
    preparation: SelectionPreparation,
    skill_ids: Sequence[str],
) -> PreliminarySelection:
    """記錄 Codex 初選的候選 ID；Python 不替 Codex 判斷語意適用性。"""

    ids = _validated_id_tuple(skill_ids)
    candidate_ids = {profile.id for profile in preparation.candidates}
    missing = tuple(skill_id for skill_id in ids if skill_id not in candidate_ids)
    if missing:
        raise ValueError("preliminary selection must contain candidate IDs")
    return PreliminarySelection(skill_ids=ids)


def handoff_full_instructions(
    inventory: SkillInventory,
    preliminary: PreliminarySelection,
) -> tuple[FullInstructionHandoff, ...]:
    """只完整讀取初選 Skill 的 SKILL.md，回傳暫時 handoff 與目前 fingerprint。"""

    profiles = {profile.id: profile for profile in inventory.profiles}
    eligible = {record.id for record in inventory.available_records if _eligible_record(record)}
    handoffs: list[FullInstructionHandoff] = []
    for skill_id in preliminary.skill_ids:
        profile = profiles.get(skill_id)
        binding = inventory.source_binding(skill_id) if profile is not None else None
        skill_path = None if binding is None else binding.path
        if profile is None or skill_id not in eligible or skill_path is None:
            raise ValueError("preliminary Skill is not currently handoff-eligible")
        try:
            raw_instructions = skill_path.read_bytes()
            instructions = raw_instructions.decode("utf-8")
        except (OSError, UnicodeError) as error:
            raise ValueError("selected Skill instructions are unavailable") from error
        if fingerprint_profile_content(profile, raw_instructions) != profile.fingerprint:
            raise SkillHandoffFingerprintMismatch(skill_id)
        handoffs.append(FullInstructionHandoff(skill_id, profile.fingerprint, instructions))
    return tuple(handoffs)


class SkillHandoffFingerprintMismatch(ValueError):
    """表示 selected Skill 的 authoritative bytes 與 snapshot 不一致。"""

    def __init__(self, skill_id: str) -> None:
        _require_skill_id(skill_id)
        self.skill_id = skill_id
        super().__init__("selected Skill changed before full instruction handoff")


@dataclass(frozen=True)
class HandoffRecoveryResult:
    """一次 selected-Skill freshness recovery 的 bounded result。"""

    snapshot: SkillInventorySnapshot
    handoffs: tuple[FullInstructionHandoff, ...]
    refresh: SelectedSkillRefreshResult


def handoff_with_selected_skill_refresh(
    snapshot: SkillInventorySnapshot,
    preliminary: PreliminarySelection,
) -> HandoffRecoveryResult:
    """fingerprint mismatch 時只 refresh selected Skill，最多 retry 一次。"""

    try:
        handoffs = handoff_full_instructions(snapshot.inventory, preliminary)
        return HandoffRecoveryResult(
            snapshot,
            handoffs,
            SelectedSkillRefreshResult(snapshot, "", 0, False),
        )
    except SkillHandoffFingerprintMismatch as error:
        refreshed = refresh_selected_skill_snapshot(snapshot, error.skill_id)
        if refreshed.semantic_digest_changed:
            raise ValueError("SELECTION_REVALIDATION_REQUIRED")
        try:
            handoffs = handoff_full_instructions(refreshed.snapshot.inventory, preliminary)
        except SkillHandoffFingerprintMismatch as error:
            raise ValueError("HANDOFF_REJECTION_AFTER_ONE_REFRESH") from error
        return HandoffRecoveryResult(refreshed.snapshot, handoffs, refreshed)


def apply_correction(
    state: SelectionState,
    replacement_ids: Sequence[str],
    *,
    handoffs: Sequence[FullInstructionHandoff],
) -> SelectionState:
    """套用唯一一次 correction；每個替代 ID 必須已有完整 instruction handoff。"""

    if state.is_finalized:
        raise ValueError("selection is finalized; correction requires a new routing request")
    if state.correction_count == 1:
        raise ValueError("selection correction is already complete")
    ids = _validated_id_tuple(replacement_ids)
    handoff_by_id = _handoff_map(handoffs)
    if any(skill_id not in handoff_by_id for skill_id in ids):
        raise ValueError("replacement Skill must complete full instruction handoff")
    combined = _handoff_map((*state.handoffs, *handoffs))
    return replace(
        state,
        correction_count=1,
        handoffs=tuple(combined.values()),
    )


def validate_selection(
    payload: Mapping[str, object],
    *,
    inventory: SkillInventory | None = None,
    handoffs: Sequence[FullInstructionHandoff] | None = None,
    state: SelectionState | None = None,
    task_analysis: TaskAnalysis | None = None,
) -> dict[str, object]:
    """驗證最小 selection schema、eligibility、handoff fingerprint 與 route limits。"""

    validated = _validate_selection_schema(payload, task_analysis=task_analysis)
    if state is not None and state.budget.expanded_retrievals_used > 1:
        raise ValueError("expanded retrieval budget cannot exceed one")
    if state is not None and state.is_finalized:
        selected_ids = tuple(item["id"] for item in validated["selected_skills"])
        if selected_ids != state.final_selected_skill_ids:
            raise ValueError("selection is finalized and cannot be changed")
    if inventory is None:
        return validated

    active_handoffs = _handoff_map(handoffs if handoffs is not None else (state.handoffs if state else ()))
    profiles = {profile.id: profile for profile in inventory.profiles}
    records = {record.id: record for record in inventory.records}
    for item in validated["selected_skills"]:
        skill_id = item["id"]
        profile = profiles.get(skill_id)
        record = records.get(skill_id)
        handoff = active_handoffs.get(skill_id)
        if profile is None or record is None:
            raise ValueError("selected Skill ID does not exist in current inventory")
        if not _eligible_record(record) or skill_id not in {entry.id for entry in inventory.available_records}:
            raise ValueError("selected Skill is not currently eligible")
        if profile.stale or handoff is None:
            raise ValueError("selected Skill requires current full instruction handoff")
        if handoff.fingerprint != profile.fingerprint:
            raise ValueError("full instruction handoff fingerprint is stale")
        binding = inventory.source_binding(skill_id)
        skill_path = None if binding is None else binding.path
        if skill_path is None:
            raise ValueError("selected Skill instructions are unavailable")
        try:
            current_fingerprint = fingerprint_profile_content(profile, skill_path.read_bytes())
        except (OSError, UnicodeError) as error:
            raise ValueError("selected Skill instructions are unavailable") from error
        if current_fingerprint != handoff.fingerprint:
            raise ValueError("full instruction handoff fingerprint is stale")
    return validated


def render_selection(payload: Mapping[str, object]) -> str:
    """將已通過最小 schema 的新版 selection render 成 deterministic JSON。"""

    return json.dumps(
        _validate_selection_schema(payload),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _validate_selection_schema(
    payload: Mapping[str, object],
    *,
    task_analysis: TaskAnalysis | None = None,
) -> dict[str, object]:
    """驗證 selected/no_matching_skill 的互斥結構，不評估 reason 語意品質。"""

    if not isinstance(payload, Mapping) or set(payload) != {"task_summary", "selected_skills", "selection_status"}:
        raise ValueError("selection output has an invalid schema")
    task_summary = payload["task_summary"]
    if not isinstance(task_summary, str) or not task_summary.strip() or len(task_summary) > 2048:
        raise ValueError("task_summary must be bounded text")
    selected = payload["selected_skills"]
    if not isinstance(selected, list):
        raise ValueError("selected_skills must be a list")
    status = payload["selection_status"]
    if status not in SELECTION_STATUSES:
        raise ValueError("selection_status is not supported")
    normalized: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in selected:
        if not isinstance(item, Mapping) or set(item) not in ({"id", "reason"}, {"id", "reason", "supports"}):
            raise ValueError("selected skill item has an invalid schema")
        skill_id, reason = item["id"], item["reason"]
        _require_skill_id(skill_id)
        if not isinstance(reason, str) or not reason.strip() or len(reason) > 512:
            raise ValueError("selected skill reason must be bounded text")
        if skill_id in seen:
            raise ValueError("selected_skills cannot contain duplicate IDs")
        seen.add(skill_id)
        normalized_item: dict[str, object] = {"id": skill_id, "reason": reason}
        if "supports" in item:
            normalized_item["supports"] = _validate_supports(item["supports"], task_analysis)
        normalized.append(normalized_item)
    if (status == "selected") != bool(normalized):
        raise ValueError("selection_status and selected_skills are inconsistent")
    return {
        "task_summary": task_summary,
        "selected_skills": normalized,
        "selection_status": status,
    }


def validate_coverage_additions(
    payload: object,
    *,
    candidate_ids: Sequence[str],
    selected_ids: Sequence[str] = (),
    task_analysis: TaskAnalysis | None = None,
) -> tuple[CoverageAddition, ...]:
    """驗證一次 Coverage Check additions；rationale 欄位不是 uniqueness gate。"""

    if isinstance(payload, Mapping):
        if set(payload) != {"additions"}:
            raise ValueError("coverage additions wrapper has an invalid schema")
        payload = payload["additions"]
    if not isinstance(payload, Sequence) or isinstance(payload, (str, bytes)):
        raise ValueError("coverage additions must be a list")
    allowed = set(candidate_ids)
    selected = set(selected_ids)
    result: list[CoverageAddition] = []
    seen: set[str] = set()
    for item in payload:
        if not isinstance(item, Mapping) or set(item) != {"id", "supports", "distinct_value"}:
            raise ValueError("coverage addition has an invalid schema")
        skill_id = item["id"]
        _require_skill_id(skill_id)
        if skill_id not in allowed:
            raise ValueError("coverage addition must reference a current candidate")
        if skill_id in selected or skill_id in seen:
            raise ValueError("coverage additions must contain unselected unique IDs")
        supports = _validate_supports(item["supports"], task_analysis)
        if not supports:
            raise ValueError("coverage addition requires at least one supports reference")
        distinct_value = item["distinct_value"]
        if not isinstance(distinct_value, str) or not distinct_value.strip() or len(distinct_value) > 512:
            raise ValueError("coverage addition distinct_value must be bounded text")
        seen.add(skill_id)
        result.append(CoverageAddition(skill_id, tuple((ref["section"], ref["index"]) for ref in supports), distinct_value.strip()))
    return tuple(result)


def _validate_supports(value: object, task_analysis: TaskAnalysis | None) -> list[dict[str, object]]:
    """只驗證四類 indexed TaskAnalysis reference，不做 semantic coverage 判斷。"""

    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise ValueError("supports must be a list")
    result: list[dict[str, object]] = []
    seen: set[tuple[str, int]] = set()
    for reference in value:
        if not isinstance(reference, Mapping) or set(reference) != {"section", "index"}:
            raise ValueError("supports reference has an invalid schema")
        section = reference["section"]
        index = reference["index"]
        if section not in _SUPPORT_SECTIONS or isinstance(index, bool) or not isinstance(index, int) or index < 0:
            raise ValueError("supports reference is invalid")
        if task_analysis is not None and index >= len(getattr(task_analysis, section)):
            raise ValueError("supports reference index is out of range")
        key = (section, index)
        if key in seen:
            raise ValueError("supports references must be unique")
        seen.add(key)
        result.append({"section": section, "index": index})
    return result


def _handoff_map(handoffs: Sequence[FullInstructionHandoff]) -> dict[str, FullInstructionHandoff]:
    """建立 bounded handoff lookup，拒絕重複 ID 避免 validator 歧義。"""

    result: dict[str, FullInstructionHandoff] = {}
    for handoff in handoffs:
        if not isinstance(handoff, FullInstructionHandoff) or handoff.id in result:
            raise ValueError("handoffs must contain unique valid records")
        result[handoff.id] = handoff
    return result


def _validated_id_tuple(skill_ids: Sequence[str]) -> tuple[str, ...]:
    """驗證 bounded canonical Skill IDs，保留 Codex 提供的順序。"""

    if isinstance(skill_ids, (str, bytes)):
        raise ValueError("Skill IDs must be a sequence")
    ids = tuple(skill_ids)
    result: list[str] = []
    for skill_id in ids:
        _require_skill_id(skill_id)
        if skill_id in result:
            raise ValueError("Skill IDs must be unique")
        result.append(skill_id)
    return tuple(result)


def _require_skill_id(skill_id: object) -> None:
    """驗證不含 path 或 SKILL.md 的 canonical Skill ID。"""

    if (
        not isinstance(skill_id, str)
        or _CANONICAL_SKILL_ID.fullmatch(skill_id.strip()) is None
        or len(skill_id) > 128
    ):
        raise ValueError("Skill ID must be a bounded canonical ID")


def _eligible_record(record: CapabilityRecord) -> bool:
    """套用存在性、kind、controller 與 routing-support hard gates。

    Skill readiness status 只保留在 BasicProfile 作為診斷；只要 trusted root
    已讀到實體 `SKILL.md`，inventory 就會把它放入 present pool。這裡不再以
    installed/available/unavailable/disabled/unknown 做 semantic exclusion。
    """

    return (
        record.kind == CapabilityKind.SKILL
        and not _is_controller(record)
        and not record.routing_support
    )
