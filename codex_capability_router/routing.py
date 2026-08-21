"""Phase 4 唯一 production Skill selection entry point。"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
from pathlib import Path
import unicodedata

from .models import DiscoveryResult


# 修改紀錄（2026-08-21，Steve Peng）
# 原始內容：route() 依固定 task aliases、category/trigger/provides ranking、overlap winner 與 PRIMARY/OPTIONAL limits 直接決定 final result。
# 修改原因：v2.1 Phase 4 要讓 Phase 1～3 Selection Contract 成為唯一 production path，語意 final selection 必須由 Codex 提供，Python 只負責準備與驗證。
# 修改後功能：route() 僅 orchestration inventory、candidate preparation、Codex preliminary IDs、full handoff、state limits 與 final validation；不保留 legacy selector 或 silent fallback。

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


def route(request: SelectionRouteInput) -> dict[str, object]:
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

    return validate_selection(
        request.final_selection,
        inventory=inventory,
        handoffs=handoffs,
        state=state,
    )


def _is_controller(record) -> bool:
    """沿用既有 controller/alias hard gate，不參與任務 relevance 或 final ranking。"""

    if record.controller:
        return True
    identifiers = (record.id, record.name, *record.aliases)
    return any(_normalize(value) in _CONTROLLER_ALIASES for value in identifiers)


def _normalize(value: str) -> str:
    """以 Unicode NFKC 與 casefold 固定 controller identifier 比對。"""

    return unicodedata.normalize("NFKC", value).casefold().strip()
