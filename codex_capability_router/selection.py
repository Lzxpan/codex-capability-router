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
    SkillInventory,
    fingerprint_profile_content,
    retrieve_candidates,
)
from .models import CapabilityKind, CapabilityRecord, CapabilityStatus
from .routing import _is_controller


# 修改紀錄（2026-08-21，Steve Peng）
# 原始內容：Phase 1/2 只有 inventory、profile 與 candidate retrieval，沒有新版 selection contract。
# 修改原因：Phase 3 需要在不改舊 production final selector 的前提下，驗證初選、完整 handoff、budget、correction、final validation 與 render 的順序及安全邊界。
# 修改後功能：提供僅供新版 contract 使用的 prepare/select/handoff/state/validate/render API；不呼叫模型、不執行 Skill，也不改動舊 routing path。
# 修改紀錄（2026-08-25，Steve Peng）
# 原始內容：SelectionState 只有次數上限，route 完成後仍可被當成可變的 OPEN state 使用。
# 修改原因：Integration Hardening 要求 Final Selection 後不可 correction、expanded retrieval 或變更 selected Skill。
# 修改後功能：加入 OPEN/FINALIZED lifecycle 與 finalized selected IDs；封存後所有 selection transition 及不同 final payload 都會被拒絕。

SELECTION_STATUSES = frozenset({"selected", "no_matching_skill"})
SELECTION_LIFECYCLES = frozenset({"OPEN", "FINALIZED"})
_AVAILABLE_STATUSES = frozenset({CapabilityStatus.INSTALLED, CapabilityStatus.AVAILABLE})
_FINGERPRINT = re.compile(r"^[0-9a-f]{64}$")
_CANONICAL_SKILL_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]*$")


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


def prepare_selection(
    inventory: SkillInventory,
    task_summary: str,
    *,
    work_parts: Sequence[str] = (),
    explicit_skill_ids: Sequence[str] = (),
    known_enriched_profiles: Sequence[EnrichedProfile] = (),
    budget: RetrievalBudget | None = None,
    use_expanded: bool = False,
) -> SelectionPreparation:
    """準備新版 contract 的候選資料；不執行 Codex，也不做語意 final selection。"""

    result = retrieve_candidates(
        inventory,
        task_summary,
        work_parts=work_parts,
        explicit_skill_ids=explicit_skill_ids,
        known_enriched_profiles=known_enriched_profiles,
        budget=budget,
        use_expanded=use_expanded,
    )
    return SelectionPreparation(
        task_summary=task_summary,
        candidates=result.candidates,
        enriched_profiles=result.enriched_profiles,
        state=SelectionState(
            budget=result.budget,
            retrieval_rounds=1 + result.budget.expanded_retrievals_used,
        ),
    )


def expanded_retrieve(
    inventory: SkillInventory,
    preparation: SelectionPreparation,
    *,
    work_parts: Sequence[str] = (),
    explicit_skill_ids: Sequence[str] = (),
    known_enriched_profiles: Sequence[EnrichedProfile] = (),
) -> SelectionPreparation:
    """在既有準備資料上最多擴大一次候選，並沿用同一 route state。"""

    next_state = preparation.state.consume_expanded_retrieval()
    result = retrieve_candidates(
        inventory,
        preparation.task_summary,
        work_parts=work_parts,
        explicit_skill_ids=explicit_skill_ids,
        known_enriched_profiles=(*preparation.enriched_profiles, *known_enriched_profiles),
        budget=preparation.state.budget,
        use_expanded=True,
    )
    if result.budget != next_state.budget:
        raise ValueError("expanded retrieval budget state mismatch")
    return replace(
        preparation,
        candidates=result.candidates,
        enriched_profiles=result.enriched_profiles,
        state=next_state,
    )


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
        skill_path = inventory._skill_paths.get(skill_id)
        if profile is None or skill_id not in eligible or skill_path is None:
            raise ValueError("preliminary Skill is not currently handoff-eligible")
        try:
            raw_instructions = skill_path.read_bytes()
            instructions = raw_instructions.decode("utf-8")
        except (OSError, UnicodeError) as error:
            raise ValueError("selected Skill instructions are unavailable") from error
        if fingerprint_profile_content(profile, raw_instructions) != profile.fingerprint:
            raise ValueError("selected Skill changed before full instruction handoff")
        handoffs.append(FullInstructionHandoff(skill_id, profile.fingerprint, instructions))
    return tuple(handoffs)


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
) -> dict[str, object]:
    """驗證最小 selection schema、eligibility、handoff fingerprint 與 route limits。"""

    validated = _validate_selection_schema(payload)
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
        skill_path = inventory._skill_paths.get(skill_id)
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


def _validate_selection_schema(payload: Mapping[str, object]) -> dict[str, object]:
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
        if not isinstance(item, Mapping) or set(item) != {"id", "reason"}:
            raise ValueError("selected skill item has an invalid schema")
        skill_id, reason = item["id"], item["reason"]
        _require_skill_id(skill_id)
        if not isinstance(reason, str) or not reason.strip() or len(reason) > 512:
            raise ValueError("selected skill reason must be bounded text")
        if skill_id in seen:
            raise ValueError("selected_skills cannot contain duplicate IDs")
        seen.add(skill_id)
        normalized.append({"id": skill_id, "reason": reason})
    if (status == "selected") != bool(normalized):
        raise ValueError("selection_status and selected_skills are inconsistent")
    return {
        "task_summary": task_summary,
        "selected_skills": normalized,
        "selection_status": status,
    }


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
    """套用既有 availability、kind、controller 與 routing-support hard gates。"""

    return (
        record.kind == CapabilityKind.SKILL
        and record.status in _AVAILABLE_STATUSES
        and not _is_controller(record)
        and not record.routing_support
    )
