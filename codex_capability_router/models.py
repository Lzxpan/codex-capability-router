"""Codex Capability Router 的 canonical registry 與 Phase 3 routing model。"""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import Enum


# 修改紀錄（2026-08-17，Steve Peng）
# 原始內容：Phase 1 只有版本 metadata，沒有 capability record。
# 修改原因：建立 Phase 2 所需的固定欄位與可預測輸出邊界。
# 修改後功能：提供 immutable enum、record、diagnostic 與 deterministic registry result。
# 修改紀錄（2026-08-18，Steve Peng）
# 原始內容：RecommendationResult 沒有 selected capability 的結構化路由證據，record 也沒有雙語 Function metadata。
# 修改原因：Phase 5D 需要可稽核的 selected explanation，且不允許 renderer 以 category 猜測功能。
# 修改後功能：新增 optional function metadata 與 SelectionEvidence；既有 record 欄位與 route result positional 順序保持相容。


class CapabilityKind(str, Enum):
    """Capability 的受支援類型。"""

    SKILL = "skill"
    PLUGIN = "plugin"
    TOOL = "tool"
    APP = "app"
    MCP = "mcp"
    UNKNOWN = "unknown"


class CapabilityStatus(str, Enum):
    """Capability 的可用狀態；缺少可靠 runtime 資訊時使用 UNKNOWN。"""

    INSTALLED = "installed"
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class SelectionEvidence:
    """單一 capability 的 deterministic selection evidence，不包含隱藏推理。"""

    capability_id: str
    selection_level: str
    reason_codes: tuple[str, ...] = ()
    matched_triggers: tuple[str, ...] = ()
    matched_requirements: tuple[str, ...] = ()


@dataclass(frozen=True)
class RouterInput:
    """Router 輸入：使用者任務、fixture/runtime registry 與可選輸出語言。"""

    user_task: str
    capability_registry: tuple["CapabilityRecord", ...]
    requested_output_language: str | None = None

    def __post_init__(self) -> None:
        """驗證信任邊界並固定 registry 順序容器，避免 route 改寫呼叫者資料。"""

        if not isinstance(self.user_task, str) or not self.user_task.strip():
            raise ValueError("user_task must be a non-empty string")
        if not isinstance(self.capability_registry, tuple):
            object.__setattr__(self, "capability_registry", tuple(self.capability_registry))
        if self.requested_output_language is not None and (
            not isinstance(self.requested_output_language, str)
            or not self.requested_output_language.strip()
        ):
            raise ValueError("requested_output_language must be a non-empty string or null")


@dataclass(frozen=True)
class RejectedCandidate:
    """被 availability、self-routing、overlap 或 selection limit 排除的候選。"""

    id: str
    reason: str
    status: CapabilityStatus
    source: str | None = None
    provenance: tuple[str, ...] = ()
    confidence: float | None = None
    conflicts: tuple[str, ...] = ()

    @property
    def capability_identifier(self) -> str:
        """提供較明確的輸出別名，保留簡短 id 欄位供 fixture assertions 使用。"""

        return self.id


@dataclass(frozen=True)
class RecommendationResult:
    """Phase 3 advisory routing result；只含建議資料，不含 execution action。"""

    selected_primary: tuple["CapabilityRecord", ...]
    selected_optional: tuple["CapabilityRecord", ...]
    rejected_candidates: tuple[RejectedCandidate, ...]
    rationale: str
    recommendation_only: tuple["CapabilityRecord", ...] = ()
    selection_evidence: tuple[SelectionEvidence, ...] = ()

    def __post_init__(self) -> None:
        """在資料邊界再次保護 hard selection limits，避免呼叫端傳出超額結果。"""

        if len(self.selected_primary) > 3:
            raise ValueError("selected_primary cannot contain more than 3 capabilities")
        if len(self.selected_optional) > 2:
            raise ValueError("selected_optional cannot contain more than 2 capabilities")


@dataclass(frozen=True)
class CapabilityRecord:
    """Canonical capability record；所有集合欄位使用 tuple 保持 immutable。"""

    id: str
    name: str
    kind: CapabilityKind
    status: CapabilityStatus
    categories: tuple[str, ...]
    triggers: tuple[str, ...]
    priority: int
    overlap_group: str | None
    preferred_for: tuple[str, ...]
    requires: tuple[str, ...]
    source: str
    last_verified: str | None
    # 修改紀錄（2026-08-17，Steve Peng）
    # 原始內容：record 只有單一 source 與 last_verified，無法保留 merge provenance/conflict。
    # 修改原因：Phase 5R 要求 runtime authority、信心、證據與衝突不可靜默遺失。
    # 修改後功能：保留可追溯來源、confidence、conflicts、evidence 與 recommendation-only 標記；
    # 這些欄位均為 optional default，不破壞既有 canonical fixture。
    version: str | None = None
    limitations: tuple[str, ...] = ()
    provenance: tuple[str, ...] = ()
    confidence: float | None = None
    conflicts: tuple[str, ...] = ()
    evidence: tuple[str, ...] = ()
    recommendation_only: bool = False
    function_en: str | None = None
    function_zh_tw: str | None = None

    def __post_init__(self) -> None:
        """在 model boundary 驗證 confidence 與 recommendation-only 型別。"""

        if self.confidence is not None and not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be between 0.0 and 1.0")
        if not isinstance(self.recommendation_only, bool):
            raise ValueError("recommendation_only must be a boolean")

    def to_mapping(self) -> dict[str, object]:
        """將 record 轉成完整 canonical mapping，供 JSON registry 輸出。"""

        payload: dict[str, object] = {
            "id": self.id,
            "name": self.name,
            "kind": self.kind.value,
            "status": self.status.value,
            "categories": list(self.categories),
            "triggers": list(self.triggers),
            "priority": self.priority,
            "overlap_group": self.overlap_group,
            "preferred_for": list(self.preferred_for),
            "requires": list(self.requires),
            "source": self.source,
            "last_verified": self.last_verified,
            "version": self.version,
            "limitations": list(self.limitations),
            "provenance": list(self.provenance),
            "confidence": self.confidence,
            "conflicts": list(self.conflicts),
            "evidence": list(self.evidence),
            "recommendation_only": self.recommendation_only,
        }
        if self.function_en is not None or self.function_zh_tw is not None:
            payload["function"] = {"en": self.function_en, "zh-TW": self.function_zh_tw}
        return payload

    def function_for(self, locale: str) -> str | None:
        """依 requested locale 讀取 canonical Function metadata；缺少時回傳 None。"""

        return self.function_zh_tw if locale == "zh-TW" else self.function_en


@dataclass(frozen=True)
class DiscoveryDiagnostic:
    """不影響其他 entry 的 bounded discovery 診斷。"""

    code: str
    message: str
    source: str


@dataclass(frozen=True)
class DiscoveryResult:
    """Discovery record 與安全診斷的 immutable 結果集合。"""

    records: tuple[CapabilityRecord, ...] = ()
    diagnostics: tuple[DiscoveryDiagnostic, ...] = ()
    partial: bool = False

    def to_registry_json(self) -> str:
        """輸出固定 key、固定 record ordering 的 registry JSON。"""

        payload = [record.to_mapping() for record in self.records]
        return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
