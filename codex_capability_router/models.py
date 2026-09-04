"""Codex Capability Router 的 canonical registry 與 Phase 3 routing model。"""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import Enum
from pathlib import PurePosixPath, PureWindowsPath


# 修改紀錄（2026-08-17，Steve Peng）
# 原始內容：Phase 1 只有版本 metadata，沒有 capability record。
# 修改原因：建立 Phase 2 所需的固定欄位與可預測輸出邊界。
# 修改後功能：提供 immutable enum、record、diagnostic 與 deterministic registry result。
# 修改紀錄（2026-08-18，Steve Peng）
# 原始內容：RecommendationResult 沒有 selected capability 的結構化路由證據，record 也沒有雙語 Function metadata。
# 修改原因：Phase 5D 需要可稽核的 selected explanation，且不允許 renderer 以 category 猜測功能。
# 修改後功能：新增 optional function metadata 與 SelectionEvidence；既有 record 欄位與 route result positional 順序保持相容。
# 修改紀錄（2026-08-18，Steve Peng）
# 原始內容：route-only request 無法表達 execution permission，record 也無法區分 controller 與 routing support。
# 修改原因：Phase 5E 必須讓 downstream selection 與 execution suppression 分離，並阻止 controller/internal discovery tool 被選取。
# 修改後功能：新增最小 execution_allowed、controller、aliases 與 routing_support metadata；不新增 execution engine。
# 修改紀錄（2026-08-19，Steve Peng）
# 原始內容：非程式 capability 的 description/provides metadata 無法進入 canonical record。
# 修改原因：Phase 5F 發現 document/image/PDF capability 可被 discovery 讀取，但缺少 generic artifact requirement 時無法可靠進入 task selection。
# 修改後功能：保留可供 routing 使用的 description 與 provides；不依 source 猜測 task capability 或 routing support。


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
    # 修改紀錄（2026-08-21，Steve Peng）
    # 原始內容：status 僅有 installed、available、unavailable、unknown。
    # 修改原因：v2.1 Phase 1 要求 runtime 宣告 disabled 時，舊 cache 不得讓 Skill 進入可用 inventory。
    # 修改後功能：以明確 disabled 狀態保留來源資訊，並由 inventory eligibility 排除。
    DISABLED = "disabled"


_ACTION_REQUIREMENTS = frozenset(
    {
        "rewrite_text",
        "generate_text",
        "edit_spreadsheet",
        "compose_image",
        "verify_facts",
        "debug_firmware",
    }
)
_EXECUTION_CONSTRAINTS = frozenset(
    {
        "preserve_original",
        "no_generative_redraw",
        "no_invented_content",
        "no_screen_content_modification",
    }
)
_ROUTING_OUTCOMES = frozenset(
    {
        "downstream_selected",
        "native_model_sufficient",
        "no_safe_match",
    }
)


@dataclass(frozen=True)
class SelectionEvidence:
    """單一 capability 的 deterministic selection evidence，不包含隱藏推理。"""

    capability_id: str
    selection_level: str
    reason_codes: tuple[str, ...] = ()
    matched_triggers: tuple[str, ...] = ()
    matched_requirements: tuple[str, ...] = ()
    constraint_preserved: tuple[str, ...] = ()


@dataclass(frozen=True)
class RouterInput:
    """Deprecated compatibility input；Phase 4 production route 不接受此型別。"""

    user_task: str
    capability_registry: tuple["CapabilityRecord", ...]
    requested_output_language: str | None = None
    execution_allowed: bool = True
    # 修改紀錄（2026-08-19，Steve Peng）
    # 原始內容：RouterInput 只有 task/category context 與 execution permission。
    # 修改原因：Phase 5G-B 需要 bounded explicit request、action requirement 與 execution constraint，
    # 且不得破壞既有四個 positional fields 的呼叫方式。
    # 修改後功能：追加 immutable-friendly structured intent fields，並在信任邊界拒絕 path、raw frontmatter 與 secret-like values。
    explicit_requests: tuple[str, ...] = ()
    action_requirements: tuple[str, ...] = ()
    execution_constraints: tuple[str, ...] = ()

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
        if not isinstance(self.execution_allowed, bool):
            raise ValueError("execution_allowed must be a boolean")
        object.__setattr__(
            self,
            "explicit_requests",
            _bounded_tokens(self.explicit_requests, "explicit_requests"),
        )
        object.__setattr__(
            self,
            "action_requirements",
            _bounded_tokens(self.action_requirements, "action_requirements", _ACTION_REQUIREMENTS),
        )
        object.__setattr__(
            self,
            "execution_constraints",
            _bounded_tokens(self.execution_constraints, "execution_constraints", _EXECUTION_CONSTRAINTS),
        )


@dataclass(frozen=True)
class RejectedCandidate:
    """Deprecated compatibility record for legacy catalog exclusions only。

    v0.2 ``route()`` 不因 semantic overlap 或 selection count 排除 Skill。
    """

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
    """Deprecated compatibility result；不代表 v0.2 production selection output。

    ``selected_primary``/``selected_optional`` limits belong only to this legacy
    presentation shape and are not v0.2 semantic selection limits.
    """

    selected_primary: tuple["CapabilityRecord", ...]
    selected_optional: tuple["CapabilityRecord", ...]
    rejected_candidates: tuple[RejectedCandidate, ...]
    rationale: str
    recommendation_only: tuple["CapabilityRecord", ...] = ()
    selection_evidence: tuple[SelectionEvidence, ...] = ()
    execution_allowed: bool = True
    # 修改紀錄（2026-08-19，Steve Peng）
    # 原始內容：RecommendationResult 只有 selected/rejected/rationale 與 execution permission。
    # 修改原因：Phase 5G-B 必須區分 downstream selected、native model sufficient 與 no safe match，
    # 並保留 constraint 與 Router controller identity 給下游 renderer。
    # 修改後功能：新增 bounded outcome、execution constraints 與獨立 controller presentation metadata；不把 rejected list 當 selected。
    outcome: str = "no_safe_match"
    execution_constraints: tuple[str, ...] = ()
    router_controller_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        """只保護 legacy presentation shape；不限制 v0.2 ``route()`` selection。"""

        if len(self.selected_primary) > 3:
            raise ValueError("selected_primary cannot contain more than 3 capabilities")
        if len(self.selected_optional) > 2:
            raise ValueError("selected_optional cannot contain more than 2 capabilities")
        if not isinstance(self.execution_allowed, bool):
            raise ValueError("execution_allowed must be a boolean")
        if self.outcome not in _ROUTING_OUTCOMES:
            raise ValueError("outcome must be a supported routing outcome")
        object.__setattr__(
            self,
            "execution_constraints",
            _bounded_tokens(self.execution_constraints, "execution_constraints", _EXECUTION_CONSTRAINTS),
        )
        object.__setattr__(
            self,
            "router_controller_ids",
            _bounded_tokens(self.router_controller_ids, "router_controller_ids"),
        )


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
    controller: bool = False
    aliases: tuple[str, ...] = ()
    routing_support: bool = False
    description: str | None = None
    provides: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        """在 model boundary 驗證 confidence、selection metadata 與 recommendation-only 型別。"""

        if self.confidence is not None and not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be between 0.0 and 1.0")
        if not isinstance(self.recommendation_only, bool):
            raise ValueError("recommendation_only must be a boolean")
        if not isinstance(self.controller, bool):
            raise ValueError("controller must be a boolean")
        if not isinstance(self.routing_support, bool):
            raise ValueError("routing_support must be a boolean")

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
        if self.controller:
            payload["controller"] = True
        if self.aliases:
            payload["aliases"] = list(self.aliases)
        if self.routing_support:
            payload["routing_support"] = True
        if self.description is not None:
            payload["description"] = self.description
        if self.provides:
            payload["provides"] = list(self.provides)
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
    # 僅記錄 source-derived discovery 成本；不接受 UI expected count。
    discovery_metrics: tuple[tuple[str, int], ...] = ()

    @property
    def metrics(self) -> dict[str, int]:
        """回傳 deterministic discovery metrics 的讀取副本。"""

        return dict(self.discovery_metrics)

    def to_registry_json(self) -> str:
        """輸出固定 key、固定 record ordering 的 registry JSON。"""

        payload = [record.to_mapping() for record in self.records]
        return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _bounded_tokens(
    value: object,
    field: str,
    allowed: frozenset[str] | None = None,
) -> tuple[str, ...]:
    """驗證並固定 bounded token tuple，拒絕 private path、frontmatter 與 secret-like input。"""

    if isinstance(value, (str, bytes)) or not isinstance(value, (tuple, list)):
        raise ValueError(f"{field} must be a sequence of strings")
    if len(value) > 8:
        raise ValueError(f"{field} cannot contain more than 8 values")

    result: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise ValueError(f"{field} must contain non-empty strings")
        token = item.strip()
        folded = token.casefold()
        if len(token) > 128 or "/" in token or "\\" in token:
            raise ValueError(f"{field} accepts canonical tokens only")
        if "skill.md" in folded or any(marker in folded for marker in ("api_key=", "password=", "secret=", "token=")):
            raise ValueError(f"{field} does not accept sensitive or raw metadata values")
        if PureWindowsPath(token).is_absolute() or PurePosixPath(token).is_absolute():
            raise ValueError(f"{field} does not accept absolute paths")
        if allowed is not None and token not in allowed:
            raise ValueError(f"{field} contains an unsupported canonical token")
        result.append(token)
    return tuple(result)
