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
# 修改紀錄（2026-09-01，Steve Peng）
# 原始內容：package exports 只包含 hard-ready Supporting context 與 readiness evidence。
# 修改原因：Optimistic Supporting Provider Selection Upgrade 需要公開 typed presence/readiness states 與 execution outcome record。
# 修改後功能：公開 Provider state constants、PRESENT_UNVERIFIED digest 與獨立 ExecutionAttempt；不新增 Provider endpoint 或第二套路由。
# 修改紀錄（2026-09-01，Steve Peng）
# 原始內容：package 沒有 Supporting Coverage Check 的 public addition contract。
# 修改原因：multi-Provider selection 需要以 execution need 與 distinct value 保留 bounded 補選證據。
# 修改後功能：公開 SupportingCoverageAddition 與 validator；不新增 semantic provider ranking 或 execution。

# 修改紀錄（2026-09-02，Steve Peng）
# 原始內容：__version__ = "0.2.0-beta.1"。
# 修改原因：v0.2.0-beta.2 修正 discovery source semantics 與 blind inventory integrity。
# 修改後功能：公開 v0.2.0-beta.2 development version；保留 beta.1 historical references。
# 修改紀錄（2026-09-02，Steve Peng）
# 原始內容：__version__ = "0.2.0-beta.2"。
# 修改原因：beta.3 修正 live discovery schema、Plugin identity contract 與 existence-only consideration。
# 修改後功能：公開 v0.2.0-beta.3 development version；保留 beta.1/beta.2 historical references。
# 修改紀錄（2026-09-02，Steve Peng）
# 原始內容：__version__ = "0.2.0-beta.3"。
# 修改原因：beta.4 將 unknown Host hierarchy 轉為可 consideration 的 host_tool fallback。
# 修改後功能：公開 v0.2.0-beta.4 development version；保留 beta.1/beta.2/beta.3 historical references。
# 修改紀錄（2026-09-03，Steve Peng）
# 原始內容：__version__ = "0.2.0-beta.4"。
# 修改原因：beta.5 收斂 authoritative-path discovery 與 declared-capability retention。
# 修改後功能：公開 v0.2.0-beta.5 development version；保留 beta.1/beta.2/beta.3/beta.4 historical references。
# 修改紀錄（2026-09-03，Steve Peng）
# 原始內容：__version__ = "0.2.0-beta.5"。
# 修改原因：beta.6 補上 logical Plugin 到官方 PluginStore root 的 bounded resolution。
# 修改後功能：公開 v0.2.0-beta.6 development version；保留 beta.1-beta.5 historical references。
# 修改紀錄（2026-09-03，Steve Peng）
# 原始內容：__version__ = "0.2.0-beta.7"。
# 修改原因：beta.8 清理 Skill semantic selection 的保守 redundancy/materiality wording。
# 修改後功能：公開 v0.2.0-beta.8 development version；Host/App/MCP/Provider semantics 不變。
# 修改紀錄（2026-09-04，Codex）
# 修改原因：beta.9 修正 canonical Skill 多 physical source 的 handoff freshness 綁定。
# 修改後功能：公開 v0.2.0-beta.9 version；selection/discovery semantics 不變。
__version__ = "0.2.0-beta.9"

from .registry import classify_capability, deduplicate_registry
from .host_exposure import (
    HostExposureError,
    HostSkillExposureAdapter,
    HostSkillExposureEnvelope,
    HostSkillExposureRecord,
    canonicalize_host_path,
    revalidate_host_exposure,
)
from .route_context import (
    ValidatedDecisionPayloads,
    prepare_route_context,
    validate_decision_payloads,
)
from .host_snapshot import (
    HOST_SNAPSHOT_CONTRACT_VERSION,
    HOST_SNAPSHOT_PROVENANCE,
    HOST_SNAPSHOT_TRUST_MARKER,
    HostCapability,
    HostCapabilitySnapshot,
    prepare_host_capability_snapshot,
)
from .existence import ExistenceEvidence, ExistenceEvidenceState, MetadataQuality, classify_metadata_quality
from .selection import prepare_high_recall_selection
from .routing import SelectionRouteInput, prepare_route_input_from_controller_registry, route
from .supporting_context import (
    FORMAL_SUPPORTING_PROVIDER_KINDS,
    EXECUTION_OUTCOMES,
    PROVIDER_METADATA_STATES,
    DISCOVERY_EVIDENCE_STATES,
    PROVIDER_PRESENCE_STATES,
    PROVIDER_READINESS_STATES,
    AppReadinessEvidence,
    ExecutionAttempt,
    ExecutionNeed,
    McpReadinessEvidence,
    ProviderDigest,
    ProviderDetailReference,
    ReadinessEvidenceCertificate,
    SupportingCapabilitySelection,
    SupportingCoverageAddition,
    SupportingDecisionPayload,
    SupportingDetailRequest,
    SupportingFinalSelection,
    SupportingProviderDeclaration,
    SupportingRouteContext,
    SupportingToolDeclaration,
    SupportingToolSummary,
    canonicalize_external_identity,
    UnmetExecutionNeed,
    normalize_execution_needs,
    prepare_supporting_context,
    supporting_selection_status,
    validate_supporting_decision,
    validate_supporting_coverage_additions,
    validate_supporting_final_selection_payload,
)
from .provider_adapters import (
    APP_INSTALLED_METHOD,
    APP_LIST_METHOD,
    APP_READ_METHOD,
    MCP_STATUS_DETAIL,
    MCP_STATUS_LIST_METHOD,
    ProviderAdapterInventory,
    adapt_official_app_inventory,
    adapt_official_mcp_inventory,
    adapt_codex_mcp_cli_inventory,
    build_official_provider_requests,
    HOST_NATIVE_REGISTRY_SOURCE,
    ProviderDiscoveryInventory,
    discover_active_plugin_children,
    discover_host_capability_snapshot_inventory,
    discover_host_native_provider_inventory,
    discover_provider_inventory,
)
from .inventory_sweep import (
    DEFAULT_SWEEP_BYTE_LIMIT,
    DEFAULT_SWEEP_ITEM_LIMIT,
    InventorySweep,
    build_inventory_sweep,
)
from .discovery import (
    DiscoveryRootPlan,
    discover_plugin_skill_declarations,
    discover_plugin_skill_root_specs,
    discover_plugin_skill_roots,
)
from .skill_plan import (
    KNOWN_SYSTEM_CHILD,
    ROOT_KIND_FIXED_GLOBAL,
    ROOT_KIND_FIXED_PROJECT,
    ROOT_KIND_PLUGIN_DECLARED,
    ROOT_KIND_RUNTIME_EXTRA,
    RootPlanSnapshot,
    SkillRootSpec,
    build_skill_root_plan,
)
from .inventory import (
    SelectedSkillRefreshResult,
    SkillInventoryCache,
    SkillInventorySnapshot,
    SkillSourceBinding,
    refresh_selected_skill_snapshot,
    refresh_skill_inventory_snapshot,
)
from .plugin_store import (
    PLUGIN_MANIFEST_RELATIVE_PATH,
    PLUGIN_STORE_RELATIVE_ROOT,
    PluginIdentity,
    PluginRootResolution,
    PluginStoreInventory,
    PluginStoreMetrics,
    resolve_plugin_store_inventory,
)
from .reconciliation import (
    CurrentUiInventoryReference,
    CurrentUiInventoryReconciliation,
    UiInventoryCategory,
    reconcile_current_ui_inventory,
)
from .task_analysis import TaskAnalysis, validate_task_analysis

__all__ = [
    "__version__",
    "classify_capability",
    "deduplicate_registry",
    "HostExposureError",
    "HostSkillExposureAdapter",
    "HostSkillExposureEnvelope",
    "HostSkillExposureRecord",
    "canonicalize_host_path",
    "revalidate_host_exposure",
    "SelectionRouteInput",
    "route",
    "prepare_route_input_from_controller_registry",
    "TaskAnalysis",
    "validate_task_analysis",
    "ValidatedDecisionPayloads",
    "prepare_route_context",
    "validate_decision_payloads",
    "prepare_high_recall_selection",
    "HostCapability",
    "HostCapabilitySnapshot",
    "prepare_host_capability_snapshot",
    "HOST_SNAPSHOT_CONTRACT_VERSION",
    "HOST_SNAPSHOT_PROVENANCE",
    "HOST_SNAPSHOT_TRUST_MARKER",
    "ExistenceEvidence",
    "ExistenceEvidenceState",
    "MetadataQuality",
    "classify_metadata_quality",
    "canonicalize_external_identity",
    "ExecutionNeed",
    "ExecutionAttempt",
    "FORMAL_SUPPORTING_PROVIDER_KINDS",
    "PROVIDER_PRESENCE_STATES",
    "PROVIDER_READINESS_STATES",
    "PROVIDER_METADATA_STATES",
    "DISCOVERY_EVIDENCE_STATES",
    "EXECUTION_OUTCOMES",
    "AppReadinessEvidence",
    "McpReadinessEvidence",
    "SupportingCapabilitySelection",
    "SupportingCoverageAddition",
    "UnmetExecutionNeed",
    "SupportingFinalSelection",
    "SupportingDetailRequest",
    "SupportingDecisionPayload",
    "SupportingToolDeclaration",
    "SupportingToolSummary",
    "SupportingProviderDeclaration",
    "ReadinessEvidenceCertificate",
    "ProviderDigest",
    "ProviderDetailReference",
    "SupportingRouteContext",
    "prepare_supporting_context",
    "normalize_execution_needs",
    "validate_supporting_decision",
    "validate_supporting_coverage_additions",
    "validate_supporting_final_selection_payload",
    "supporting_selection_status",
    "APP_LIST_METHOD",
    "APP_INSTALLED_METHOD",
    "APP_READ_METHOD",
    "MCP_STATUS_LIST_METHOD",
    "MCP_STATUS_DETAIL",
    "ProviderAdapterInventory",
    "adapt_official_app_inventory",
    "adapt_official_mcp_inventory",
    "adapt_codex_mcp_cli_inventory",
    "build_official_provider_requests",
    "HOST_NATIVE_REGISTRY_SOURCE",
    "ProviderDiscoveryInventory",
    "discover_active_plugin_children",
    "discover_host_capability_snapshot_inventory",
    "discover_host_native_provider_inventory",
    "discover_provider_inventory",
    "DEFAULT_SWEEP_BYTE_LIMIT",
    "DEFAULT_SWEEP_ITEM_LIMIT",
    "InventorySweep",
    "build_inventory_sweep",
    "CurrentUiInventoryReference",
    "CurrentUiInventoryReconciliation",
    "UiInventoryCategory",
    "discover_plugin_skill_roots",
    "discover_plugin_skill_root_specs",
    "discover_plugin_skill_declarations",
    "DiscoveryRootPlan",
    "SkillRootSpec",
    "RootPlanSnapshot",
    "build_skill_root_plan",
    "KNOWN_SYSTEM_CHILD",
    "ROOT_KIND_FIXED_GLOBAL",
    "ROOT_KIND_FIXED_PROJECT",
    "ROOT_KIND_RUNTIME_EXTRA",
    "ROOT_KIND_PLUGIN_DECLARED",
    "SkillInventorySnapshot",
    "SkillInventoryCache",
    "SkillSourceBinding",
    "SelectedSkillRefreshResult",
    "refresh_selected_skill_snapshot",
    "refresh_skill_inventory_snapshot",
    "reconcile_current_ui_inventory",
    "PLUGIN_MANIFEST_RELATIVE_PATH",
    "PLUGIN_STORE_RELATIVE_ROOT",
    "PluginIdentity",
    "PluginRootResolution",
    "PluginStoreInventory",
    "PluginStoreMetrics",
    "resolve_plugin_store_inventory",
]
