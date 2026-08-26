"""Codex Capability Router 的 package metadata 與新版 selection exports。"""

# 修改紀錄（2026-08-17，Steve Peng）
# 原始內容：package 尚不存在，後續版本為 0.1.0。
# 修改原因：公開 release 目標改為 v0.1.0-beta.1，package metadata 必須與 beta tag 一致。
# 修改後功能：公開 beta.1 版本與唯一新版 Skill selection entry point，不進行 capability execution。
# 修改紀錄（2026-08-21，Steve Peng）
# 原始內容：__version__ = "0.1.0-beta.1"。
# 修改原因：beta.3 release preparation 必須讓 package metadata 與待發布版本一致。
# 修改後功能：公開 v0.1.0-beta.3 版本識別；不改變 Router production behavior。
# 修改紀錄（2026-08-25，Steve Peng）
# 原始內容：__version__ = "0.1.0-beta.3"。
# 修改原因：beta.4 release preparation 必須讓 package metadata 與待發布版本一致。
# 修改後功能：公開 v0.1.0-beta.4 版本識別；不改變 Router production behavior。
# 修改紀錄（2026-08-26，Steve Peng）
# 原始內容：package 只公開 beta.4 route 與 registry helpers，沒有 v0.2 Skill-side context API。
# 修改原因：Phase 2 需要讓正式 TaskAnalysis、prepare_route_context 與 validated decision payload foundation 可被明確呼叫。
# 修改後功能：公開 Skill-only context contract；不建立第二條 production route，也不執行 Provider selection。
# 修改紀錄（2026-08-26，Steve Peng）
# 原始內容：package 沒有 lazy Supporting context 或 Phase 0 readiness evidence contract。
# 修改原因：Phase 3 需要只讀 Host declaration，且只接受已 certification 的 exact provider instances。
# 修改後功能：公開 prepare_supporting_context 與 deterministic digest/evidence types；不呼叫 Provider endpoint、不建立第二條 route。
# 修改紀錄（2026-08-26，Steve Peng）
# 原始內容：package 未公開 Phase 4 Supporting decision structured contracts。
# 修改原因：正式 route/focused tests 必須共用同一 immutable protocol foundation。
# 修改後功能：公開 decision/detail/final selection validators；不新增 Provider execution 或 workflow state。
# 修改紀錄（2026-08-26，Steve Peng）
# 原始內容：__version__ = "0.1.0-beta.4"。
# 修改原因：v0.2.0-beta.1 release preparation 必須與 pyproject 公開版本一致。
# 修改後功能：公開 v0.2.0-beta.1 版本識別；保留 beta.4 compatibility contract。

__version__ = "0.2.0-beta.1"

from .registry import classify_capability, deduplicate_registry
from .route_context import (
    ValidatedDecisionPayloads,
    prepare_route_context,
    validate_decision_payloads,
)
from .routing import SelectionRouteInput, route
from .supporting_context import (
    ExecutionNeed,
    ProviderDigest,
    ProviderDetailReference,
    ReadinessEvidenceCertificate,
    SupportingCapabilitySelection,
    SupportingDecisionPayload,
    SupportingDetailRequest,
    SupportingFinalSelection,
    SupportingProviderDeclaration,
    SupportingRouteContext,
    SupportingToolDeclaration,
    UnmetExecutionNeed,
    normalize_execution_needs,
    prepare_supporting_context,
    supporting_selection_status,
    validate_supporting_decision,
    validate_supporting_final_selection_payload,
)
from .task_analysis import TaskAnalysis, validate_task_analysis

__all__ = [
    "__version__",
    "classify_capability",
    "deduplicate_registry",
    "SelectionRouteInput",
    "route",
    "TaskAnalysis",
    "validate_task_analysis",
    "ValidatedDecisionPayloads",
    "prepare_route_context",
    "validate_decision_payloads",
    "ExecutionNeed",
    "SupportingCapabilitySelection",
    "UnmetExecutionNeed",
    "SupportingFinalSelection",
    "SupportingDetailRequest",
    "SupportingDecisionPayload",
    "SupportingToolDeclaration",
    "SupportingProviderDeclaration",
    "ReadinessEvidenceCertificate",
    "ProviderDigest",
    "ProviderDetailReference",
    "SupportingRouteContext",
    "prepare_supporting_context",
    "normalize_execution_needs",
    "validate_supporting_decision",
    "validate_supporting_final_selection_payload",
    "supporting_selection_status",
]
