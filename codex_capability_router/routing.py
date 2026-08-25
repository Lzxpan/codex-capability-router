"""Phase 4 唯一 production Skill selection entry point。"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field, replace
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
    _token: object = field(repr=False, compare=False)

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

        return {
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

    inventory = refresh_skill_inventory(
        request.skill_roots,
        cache=ProfileCache(),
        runtime=request.runtime,
        cli=request.cli,
        manual=request.manual,
    )
    preparation = prepare_selection(
        inventory,
        request.task_summary,
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
