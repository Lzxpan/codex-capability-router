"""Official Codex App Server Provider adapters.

這個模組只把 Host 已取得的 typed protocol response 正規化成 Router
Provider declarations/readiness evidence；不呼叫 RPC、不執行 tool，也不使用
under-development 的 Plugin RPC。
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
import json
from pathlib import Path

from .host_snapshot import HostCapabilitySnapshot
from .existence import ExistenceEvidenceState
from .supporting_context import (
    AppReadinessEvidence,
    McpReadinessEvidence,
    SupportingProviderDeclaration,
    SupportingToolDeclaration,
    SupportingToolSummary,
    FORMAL_SUPPORTING_PROVIDER_KINDS,
    canonicalize_external_identity,
)

# 修改紀錄（2026-09-02，Steve Peng）
# 原始內容：Plugin logical identity 直接放入 canonical host_grouping，`@` identity 會觸發 validator error。
# 修改原因：外部 Plugin identity 與 Router internal grouping key 是不同 contract。
# 修改後功能：保留 raw external identity，使用 deterministic hash key；不放寬 canonical validator。
# 修改紀錄（2026-09-02，Steve Peng）
# 原始內容：metadata insufficient 會降低 adapter selectable count。
# 修改原因：beta.3 要求存在且 identity resolved 的 Provider 全部進 semantic consideration。
# 修改後功能：adapter selectable count 只依 formal present identity，metadata 僅輸出品質診斷。
# 修改紀錄（2026-09-01，Steve Peng）
# 原始內容：官方 App/MCP adapter 只有 hard_eligible count，缺少 presence 與 unverified readiness 統計。
# 修改原因：Optimistic Supporting Provider Selection Upgrade 要讓 readiness unknown 不再阻擋 semantic candidate。
# 修改後功能：官方 adapter 保留 hard-ready evidence，同時回報 present/selectable/unverified；不把 package 或 Plugin state 當 runtime readiness。
# 修改紀錄（2026-09-01，Steve Peng）
# 原始內容：official adapter 的 selectable 統計要求 enabled tool detail，Provider description 不足以進 candidate。
# 修改原因：multi-Provider coverage 需要保留可信 presence 加自然語言 metadata 的 Provider，將 runtime callable 留給 readiness。
# 修改後功能：adapter 以 Provider description 或 tool summary 判斷最低 metadata，無工具 detail 時仍可回報 PRESENT_UNVERIFIED。
# 修改紀錄（2026-09-01，Steve Peng）
# 原始內容：Provider adapter 沒有 generic Host-native registry、Plugin child discovery 或 discovery evidence layer。
# 修改原因：不能因 Plugin package 非 formal Provider，或 Host tool 非既有固定 fixture，而讓 child capability 消失。
# 修改後功能：新增 trusted envelope normalizer；只將 top-level native capability 轉為 builtin_tool，App/MCP child 維持 formal kind，Plugin 本身永不 formal selected。
# 修改紀錄（2026-09-01，Steve Peng）
# 原始內容：Host-native discovery 仍只能接 raw registry mapping，Router 無法接收 controller-owned session snapshot。
# 修改原因：Host 已暴露的 capability 必須透過 typed bridge 進入同一個 Provider inventory 與 sweep。
# 修改後功能：新增 HostCapabilitySnapshot adapter、hierarchy diagnostics、exact evidence merge 與 snapshot metrics；不新增 ID mapping 或 execution。


APP_LIST_METHOD = "app/list"
APP_INSTALLED_METHOD = "app/installed"
APP_READ_METHOD = "app/read"
MCP_STATUS_LIST_METHOD = "mcpServerStatus/list"
MCP_STATUS_DETAIL = "toolsAndAuthOnly"
HOST_NATIVE_REGISTRY_SOURCE = "host-native-registry"


@dataclass(frozen=True)
class ProviderDiscoveryInventory:
    """多個 trusted source 正規化後的 formal Provider inventory。

    Plugin package 只作 provenance；`provider_declarations` 僅包含正式的
    app、mcp、builtin_tool、host_tool。Child tool 不會被提升成 builtin_tool，
    Plugin 本身也不會進入 formal selection。
    """

    provider_declarations: tuple[SupportingProviderDeclaration, ...]
    child_skill_declarations: tuple[Mapping[str, object], ...] = ()
    diagnostics: tuple[str, ...] = ()
    host_snapshot_capability_count: int = 0
    host_snapshot_builtin_count: int = 0
    host_snapshot_app_child_count: int = 0
    host_snapshot_mcp_child_count: int = 0
    host_snapshot_unclassified_count: int = 0
    host_snapshot_control_plane_count: int = 0
    host_snapshot_plugin_child_count: int = 0
    host_snapshot_intentionally_excluded_count: int = 0
    host_snapshot_id: str | None = None
    host_snapshot_fingerprint: str | None = None
    raw_evidence_count: int = 0
    runtime_entity_count: int = 0
    package_declared_count: int = 0
    canonical_unique_count: int = 0
    exact_duplicate_count: int = 0
    metadata_sufficient_count: int = 0
    metadata_sparse_count: int = 0
    metadata_opaque_count: int = 0
    identity_unresolved_count: int = 0
    semantically_considered_count: int = 0
    never_considered_count: int = 0

    def __post_init__(self) -> None:
        """固定 immutable containers 並拒絕 Plugin/child tool formal record。"""

        declarations = tuple(self.provider_declarations)
        if any(item.kind not in FORMAL_SUPPORTING_PROVIDER_KINDS for item in declarations):
            raise ValueError("provider discovery inventory contains a non-formal kind")
        if len({(item.kind, item.provider_id) for item in declarations}) != len(declarations):
            raise ValueError("provider discovery inventory contains duplicate formal identity")
        object.__setattr__(self, "provider_declarations", declarations)
        object.__setattr__(self, "child_skill_declarations", tuple(dict(item) for item in self.child_skill_declarations))
        object.__setattr__(self, "diagnostics", tuple(self.diagnostics))
        # 保留既有直接建構 API：未提供新版 scope metrics 時，以每筆 formal
        # declaration 作為一筆 runtime evidence；正式 adapters 會傳入精確分層值。
        if declarations and all(
            getattr(self, field_name) == 0
            for field_name in (
                "raw_evidence_count",
                "runtime_entity_count",
                "package_declared_count",
                "canonical_unique_count",
                "exact_duplicate_count",
                "metadata_sufficient_count",
                "metadata_sparse_count",
                "metadata_opaque_count",
                "identity_unresolved_count",
                "semantically_considered_count",
                "never_considered_count",
            )
        ):
            object.__setattr__(self, "raw_evidence_count", len(declarations))
            object.__setattr__(self, "runtime_entity_count", len(declarations))
            object.__setattr__(self, "canonical_unique_count", len(declarations))
            object.__setattr__(
                self,
                "metadata_sufficient_count",
                sum(_has_minimum_provider_metadata(item) for item in declarations),
            )
            object.__setattr__(self, "metadata_sparse_count", sum(item.metadata_quality.value == "SPARSE" for item in declarations))
            object.__setattr__(self, "metadata_opaque_count", sum(item.metadata_quality.value == "OPAQUE" for item in declarations))
            object.__setattr__(self, "never_considered_count", len(declarations))
        if declarations:
            object.__setattr__(self, "metadata_sufficient_count", sum(item.metadata_quality.value == "SUFFICIENT" for item in declarations))
            object.__setattr__(self, "metadata_sparse_count", sum(item.metadata_quality.value == "SPARSE" for item in declarations))
            object.__setattr__(self, "metadata_opaque_count", sum(item.metadata_quality.value == "OPAQUE" for item in declarations))
        if declarations and self.semantically_considered_count == 0 and self.never_considered_count == 0:
            object.__setattr__(self, "never_considered_count", len(declarations))
        count_fields = (
            "host_snapshot_capability_count",
            "host_snapshot_builtin_count",
            "host_snapshot_app_child_count",
            "host_snapshot_mcp_child_count",
            "host_snapshot_unclassified_count",
            "host_snapshot_control_plane_count",
            "host_snapshot_plugin_child_count",
            "host_snapshot_intentionally_excluded_count",
        )
        for field_name in count_fields:
            value = getattr(self, field_name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{field_name} must be a non-negative integer")
        if sum(
            (
                self.host_snapshot_builtin_count,
                self.host_snapshot_app_child_count,
                self.host_snapshot_mcp_child_count,
                self.host_snapshot_unclassified_count,
                self.host_snapshot_control_plane_count,
                self.host_snapshot_plugin_child_count,
            )
        ) > self.host_snapshot_capability_count:
            raise ValueError("Host snapshot hierarchy counts exceed capability count")
        if self.host_snapshot_id is not None and not isinstance(self.host_snapshot_id, str):
            raise ValueError("host_snapshot_id must be text or null")
        if self.host_snapshot_fingerprint is not None and not isinstance(self.host_snapshot_fingerprint, str):
            raise ValueError("host_snapshot_fingerprint must be text or null")
        for field_name in (
            "raw_evidence_count",
            "runtime_entity_count",
            "package_declared_count",
            "canonical_unique_count",
            "exact_duplicate_count",
            "metadata_sufficient_count",
            "metadata_sparse_count",
            "metadata_opaque_count",
            "identity_unresolved_count",
            "semantically_considered_count",
            "never_considered_count",
        ):
            value = getattr(self, field_name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{field_name} must be a non-negative integer")
        if self.canonical_unique_count > self.raw_evidence_count:
            raise ValueError("canonical_unique_count cannot exceed raw_evidence_count")
        if self.exact_duplicate_count != self.raw_evidence_count - self.canonical_unique_count:
            raise ValueError("exact_duplicate_count must match raw/canonical counts")
        if self.runtime_entity_count + self.package_declared_count > self.raw_evidence_count:
            raise ValueError("provider evidence scope counts exceed raw evidence")

    @property
    def discovered_count(self) -> int:
        """回傳 formal Provider discovery 數量。"""

        return len(self.provider_declarations)

    def to_mapping(self) -> dict[str, object]:
        """輸出 inventory metrics 與 diagnostics，不輸出 hidden Host data。"""

        return {
            "provider_declarations": [item.to_mapping() for item in self.provider_declarations],
            "child_skill_declarations": [dict(item) for item in self.child_skill_declarations],
            "diagnostics": list(self.diagnostics),
            "host_snapshot_capability_count": self.host_snapshot_capability_count,
            "host_snapshot_builtin_count": self.host_snapshot_builtin_count,
            "host_snapshot_app_child_count": self.host_snapshot_app_child_count,
            "host_snapshot_mcp_child_count": self.host_snapshot_mcp_child_count,
            "host_snapshot_unclassified_count": self.host_snapshot_unclassified_count,
            "host_snapshot_control_plane_count": self.host_snapshot_control_plane_count,
            "host_snapshot_plugin_child_count": self.host_snapshot_plugin_child_count,
            "host_snapshot_intentionally_excluded_count": self.host_snapshot_intentionally_excluded_count,
            "host_snapshot_id": self.host_snapshot_id,
            "host_snapshot_fingerprint": self.host_snapshot_fingerprint,
            "raw_evidence_count": self.raw_evidence_count,
            "runtime_entity_count": self.runtime_entity_count,
            "package_declared_count": self.package_declared_count,
            "canonical_unique_count": self.canonical_unique_count,
            "exact_duplicate_count": self.exact_duplicate_count,
            "metadata_sufficient_count": self.metadata_sufficient_count,
            "metadata_sparse_count": self.metadata_sparse_count,
            "metadata_opaque_count": self.metadata_opaque_count,
            "identity_unresolved_count": self.identity_unresolved_count,
            "semantically_considered_count": self.semantically_considered_count,
            "never_considered_count": self.never_considered_count,
        }

    def blind_metrics(self) -> dict[str, int]:
        """輸出不含 UI expected count 的 Provider source-derived metrics。"""

        return {
            "provider_raw_evidence_count": self.raw_evidence_count,
            "provider_runtime_entity_count": self.runtime_entity_count,
            "provider_package_declared_count": self.package_declared_count,
            "provider_canonical_unique_count": self.canonical_unique_count,
            "provider_exact_duplicate_count": self.exact_duplicate_count,
            "provider_metadata_sufficient_count": self.metadata_sufficient_count,
            "provider_metadata_sparse_count": self.metadata_sparse_count,
            "provider_metadata_opaque_count": self.metadata_opaque_count,
            "provider_identity_unresolved_count": self.identity_unresolved_count,
            "provider_semantically_considered_count": self.semantically_considered_count,
            "provider_never_considered_count": self.never_considered_count,
        }


def discover_host_native_provider_inventory(
    registry: Sequence[Mapping[str, object]] | Mapping[str, object],
    *,
    provenance: Sequence[str] = (HOST_NATIVE_REGISTRY_SOURCE,),
) -> ProviderDiscoveryInventory:
    """從 Host 提供的 top-level registry generic 建立 builtin_tool inventory。

    Registry source 必須已由 Host 證明是 top-level native capability；本函式
    僅驗證 hierarchy/identity/metadata，不呼叫 endpoint，也不以 capability ID
    或名稱做語意 mapping。App/MCP child tool 會保留 boundary diagnostic。
    """

    records = _source_records(registry, "capabilities")
    declarations: list[SupportingProviderDeclaration] = []
    diagnostics: list[str] = []
    for item in records:
        parent_kind = item.get("parent_kind")
        top_level = item.get("top_level", True)
        if parent_kind is not None or top_level is not True:
            diagnostics.append("child_tool_not_formal_builtin")
            continue
        declared_kind = item.get("kind")
        if declared_kind is not None and declared_kind != "builtin_tool":
            diagnostics.append("host_native_kind_mismatch")
            continue
        provider_id = _text(item.get("provider_id"), "host-native provider identity")
        display_name = _text(item.get("name", provider_id), "host-native provider name")
        description = _nullable_text(item.get("description"), "host-native provider description")
        callable_exposure = item.get("callable_exposure", False)
        if not isinstance(callable_exposure, bool):
            raise ValueError("host-native callable_exposure must be boolean")
        declarations.append(
            SupportingProviderDeclaration(
                provider_id=provider_id,
                kind="builtin_tool",
                host_identity=provider_id,
                host_grouping=("host-native",),
                description=description,
                callable_tools=(),
                callable_exposure=callable_exposure,
                provenance=tuple(provenance),
                display_name=display_name,
                discovery_evidence_state="DISCOVERED_TRUSTED",
                existence_evidence_state=ExistenceEvidenceState.HOST_SESSION_EXPOSED,
            )
        )
    return ProviderDiscoveryInventory(
        tuple(declarations),
        diagnostics=tuple(diagnostics),
        raw_evidence_count=len(declarations),
        runtime_entity_count=len(declarations),
        canonical_unique_count=len(declarations),
        metadata_sufficient_count=sum(_has_minimum_provider_metadata(item) for item in declarations),
    )


def discover_host_capability_snapshot_inventory(
    snapshot: HostCapabilitySnapshot,
) -> ProviderDiscoveryInventory:
    """將 controller-owned Host snapshot generic 轉成 formal Provider inventory。

    Host 明確標示的 top-level capability 轉成 `builtin_tool`；App/MCP child
    合併到 parent Provider；未知 hierarchy 轉成 `host_tool`，Plugin child
    與 control-plane 只留下 diagnostics。
    本函式不以 namespace/name 做 semantic 判斷，也不呼叫任何 Host endpoint。
    """

    if not isinstance(snapshot, HostCapabilitySnapshot):
        raise TypeError("Host capability snapshot must be a validated HostCapabilitySnapshot")
    declarations: dict[tuple[str, str], SupportingProviderDeclaration] = {}
    diagnostics: list[str] = []
    for capability in snapshot.capabilities:
        if capability.exposure_state != "EXPOSED":
            diagnostics.append(f"host_snapshot_not_exposed:{capability.canonical_id}")
            continue
        if capability.hierarchy == "host_native":
            declaration = SupportingProviderDeclaration(
                provider_id=capability.canonical_id,
                kind="builtin_tool",
                host_identity=capability.canonical_id,
                host_grouping=("host-session", "builtin-tool"),
                description=capability.description,
                callable_tools=(),
                callable_exposure=True,
                provenance=_merge_labels(snapshot.provenance, capability.provenance),
                display_name=capability.display_name,
                discovery_evidence_state="DISCOVERED_TRUSTED",
                existence_evidence_state=ExistenceEvidenceState.HOST_SESSION_EXPOSED,
                raw_external_identity=capability.canonical_id,
                hierarchy_state="KNOWN",
            )
            _merge_declaration_into(declarations, declaration)
            continue
        if capability.hierarchy in {"app_child", "mcp_child"}:
            assert capability.parent_kind is not None
            assert capability.parent_identity is not None
            if capability.description is None:
                diagnostics.append(f"host_snapshot_metadata_insufficient:{capability.canonical_id}")
                tools: tuple[SupportingToolSummary, ...] = ()
            else:
                tools = (
                    SupportingToolSummary(
                        id=capability.canonical_id,
                        title=capability.display_name,
                        description=capability.description,
                        is_enabled=True,
                        disabled_reason=None,
                        is_read_only=capability.is_read_only,
                        provenance=_merge_labels(snapshot.provenance, capability.provenance),
                    ),
                )
            declaration = SupportingProviderDeclaration(
                provider_id=capability.parent_identity,
                kind=capability.parent_kind,
                host_identity=capability.parent_identity,
                host_grouping=("host-session", capability.parent_kind),
                description=capability.description,
                callable_tools=tools,
                callable_exposure=True,
                provenance=_merge_labels(snapshot.provenance, capability.provenance),
                display_name=capability.parent_identity,
                discovery_evidence_state="DISCOVERED_TRUSTED",
                existence_evidence_state=ExistenceEvidenceState.HOST_SESSION_EXPOSED,
                hierarchy_state="KNOWN",
            )
            _merge_declaration_into(declarations, declaration)
            continue
        if capability.hierarchy == "plugin_child":
            diagnostics.append(f"host_snapshot_plugin_child_not_formal:{capability.canonical_id}")
            continue
        if capability.hierarchy == "control_plane":
            diagnostics.append(f"host_snapshot_control_plane_excluded:{capability.canonical_id}")
            continue
        diagnostics.append(f"DISCOVERED_UNCLASSIFIED_HOST_CAPABILITY:{capability.canonical_id}")
        diagnostics.append(f"host_snapshot_host_tool_fallback:{capability.canonical_id}")
        declaration = SupportingProviderDeclaration(
            provider_id=capability.canonical_id,
            kind="host_tool",
            host_identity=capability.canonical_id,
            host_grouping=("host-session", "host-tool"),
            description=capability.description,
            callable_tools=(),
            callable_exposure=True,
            provenance=_merge_labels(snapshot.provenance, capability.provenance),
            display_name=capability.display_name,
            discovery_evidence_state="DISCOVERED_TRUSTED",
            existence_evidence_state=ExistenceEvidenceState.HOST_SESSION_EXPOSED,
            raw_external_identity=capability.canonical_id,
            canonical_grouping_key=capability.canonical_id,
            hierarchy_state="UNKNOWN",
        )
        _merge_declaration_into(declarations, declaration)
    formal_source_count = sum(
        1
        for capability in snapshot.capabilities
        if capability.exposure_state == "EXPOSED"
        and capability.hierarchy in {"host_native", "app_child", "mcp_child", "unknown"}
    )
    canonical_declarations = tuple(
        sorted(declarations.values(), key=lambda item: (item.provider_id.casefold(), item.provider_id, item.kind))
    )
    return ProviderDiscoveryInventory(
        canonical_declarations,
        diagnostics=tuple(diagnostics),
        host_snapshot_capability_count=len(snapshot.capabilities),
        host_snapshot_builtin_count=snapshot.host_native_count,
        host_snapshot_app_child_count=snapshot.app_child_count,
        host_snapshot_mcp_child_count=snapshot.mcp_child_count,
        host_snapshot_unclassified_count=snapshot.unclassified_count,
        host_snapshot_control_plane_count=snapshot.control_plane_count,
        host_snapshot_plugin_child_count=snapshot.plugin_child_count,
        host_snapshot_intentionally_excluded_count=snapshot.intentionally_excluded_count,
        host_snapshot_id=snapshot.snapshot_id,
        host_snapshot_fingerprint=snapshot.fingerprint,
        raw_evidence_count=formal_source_count,
        runtime_entity_count=formal_source_count,
        canonical_unique_count=len(canonical_declarations),
        exact_duplicate_count=formal_source_count - len(canonical_declarations),
        metadata_sufficient_count=sum(_has_minimum_provider_metadata(item) for item in canonical_declarations),
    )


def discover_active_plugin_children(
    manifests: Sequence[Mapping[str, object]],
    *,
    provenance: Sequence[str] = (),
) -> ProviderDiscoveryInventory:
    """解析 Host 已確認存在且 package 可解析的 Plugin child capabilities。

    僅把宣告的 App/MCP child送入 formal Provider inventory；Skill child保留
    public declaration供對應 trusted Skill root/handoff流程使用。Plugin 的
    enabled/active state 只保留為 compatibility evidence，不是 semantic gate。
    """

    declarations: list[SupportingProviderDeclaration] = []
    child_skills: list[Mapping[str, object]] = []
    diagnostics: list[str] = []
    for manifest in manifests:
        if not isinstance(manifest, Mapping):
            raise TypeError("plugin manifests must contain mappings")
        plugin_id = _text(manifest.get("plugin_id"), "plugin identity")
        present = manifest.get("present")
        if present is None:
            present = manifest.get("package_root") is not None or manifest.get("package_path") is not None
        if not isinstance(present, bool):
            raise ValueError("plugin presence must be boolean")
        if not present and manifest.get("active_installed") is True:
            present = True
        if not present:
            diagnostics.append(f"DECLARED_ONLY:{plugin_id}")
            continue
        children = manifest.get("capabilities", manifest.get("children", ()))
        if not isinstance(children, Sequence) or isinstance(children, (str, bytes)):
            raise ValueError("active Plugin capabilities must be a list")
        normalized_children = list(children)
        normalized_children.extend(
            _read_declared_plugin_children(manifest, "app", ("apps",), diagnostics)
        )
        normalized_children.extend(
            _read_declared_plugin_children(manifest, "mcp", ("mcp", "mcp_servers", "mcpServers"), diagnostics)
        )
        for child in normalized_children:
            if not isinstance(child, Mapping):
                raise ValueError("Plugin child capability must be an object")
            child_kind = child.get("kind")
            child_path = child.get("path", child.get("source_root", child.get("provider_path")))
            if child_path is not None and not _plugin_child_path_is_contained(manifest, child_path):
                diagnostics.append(f"plugin_path_escape:{plugin_id}")
                continue
            if child_kind == "skill":
                child_skills.append(
                    {
                        "plugin_id": plugin_id,
                        "skill_id": _text(child.get("skill_id"), "Plugin Skill identity"),
                        "source_root": child.get("source_root"),
                        "title": _text(child.get("title"), "Plugin Skill title"),
                        "description": _nullable_text(child.get("description"), "Plugin Skill description"),
                    }
                )
                continue
            if child_kind not in {"app", "mcp"}:
                diagnostics.append(f"plugin_child_excluded:{plugin_id}")
                continue
            provider_id = _text(child.get("provider_id"), "Plugin Provider identity")
            plugin_grouping_key = canonicalize_external_identity(plugin_id, "plugin")
            try:
                declarations.append(
                    SupportingProviderDeclaration(
                        provider_id=provider_id,
                        kind=child_kind,
                        host_identity=provider_id,
                        host_grouping=("plugin", plugin_grouping_key, child_kind),
                        description=_nullable_text(child.get("description"), "Plugin Provider description"),
                        callable_tools=(),
                        callable_exposure=False,
                        provenance=tuple(provenance) + (f"plugin:{plugin_id}",),
                        display_name=_text(child.get("name", provider_id), "Plugin Provider name"),
                        discovery_evidence_state="DISCOVERED_DECLARED",
                        existence_evidence_state=ExistenceEvidenceState.PACKAGE_DECLARED_PRESENT,
                        raw_external_identity=plugin_id,
                        canonical_grouping_key=plugin_grouping_key,
                    )
                )
            except (TypeError, ValueError):
                # 宣告存在但 identity 不足時保留 bounded diagnostic，不製造 Provider。
                diagnostics.append(f"plugin_child_identity_unresolved:{plugin_id}")
    merged: dict[tuple[str, str], SupportingProviderDeclaration] = {}
    for declaration in declarations:
        _merge_declaration_into(merged, declaration)
    canonical_declarations = tuple(
        sorted(merged.values(), key=lambda item: (item.provider_id.casefold(), item.provider_id, item.kind))
    )
    return ProviderDiscoveryInventory(
        canonical_declarations,
        tuple(child_skills),
        tuple(diagnostics),
        raw_evidence_count=len(declarations),
        package_declared_count=len(declarations),
        canonical_unique_count=len(canonical_declarations),
        exact_duplicate_count=len(declarations) - len(canonical_declarations),
        metadata_sufficient_count=sum(_has_minimum_provider_metadata(item) for item in canonical_declarations),
    )


def _read_declared_plugin_children(
    manifest: Mapping[str, object],
    child_kind: str,
    field_names: Sequence[str],
    diagnostics: list[str],
) -> tuple[Mapping[str, object], ...]:
    """只讀取 manifest 明確宣告的 inline child 或 exact declaration file。"""

    result: list[Mapping[str, object]] = []
    seen_paths: set[str] = set()
    for field_name in field_names:
        declared = manifest.get(field_name, ())
        if declared is None:
            continue
        if isinstance(declared, (str, Path)):
            package_root_value = manifest.get("package_root", manifest.get("package_path"))
            if package_root_value is None or not _plugin_child_path_is_contained(manifest, declared):
                diagnostics.append(f"plugin_path_escape:{manifest.get('plugin_id', '<unknown>')}")
                continue
            package_root = Path(package_root_value).resolve()
            path = Path(declared)
            if not path.is_absolute():
                path = package_root / path
            path = path.resolve()
            path_key = str(path).casefold()
            if path_key in seen_paths:
                continue
            seen_paths.add(path_key)
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, UnicodeError, json.JSONDecodeError):
                diagnostics.append(f"plugin_declared_{child_kind}_unreadable:{manifest.get('plugin_id', '<unknown>')}")
                continue
            result.extend(_normalize_declared_child_payload(payload, child_kind))
            continue
        if isinstance(declared, Mapping):
            result.extend(_normalize_declared_child_mapping(declared, child_kind))
            continue
        if isinstance(declared, Sequence) and not isinstance(declared, (str, bytes)):
            for item in declared:
                if isinstance(item, Mapping):
                    normalized = dict(item)
                    normalized.setdefault("kind", child_kind)
                    result.append(normalized)
                else:
                    diagnostics.append(f"plugin_declared_{child_kind}_invalid:{manifest.get('plugin_id', '<unknown>')}")
            continue
        diagnostics.append(f"plugin_declared_{child_kind}_invalid:{manifest.get('plugin_id', '<unknown>')}")
    return tuple(result)


def _normalize_declared_child_payload(payload: object, child_kind: str) -> tuple[Mapping[str, object], ...]:
    """將 exact `.app.json`/`.mcp.json` public map 轉成 child declarations。"""

    if not isinstance(payload, Mapping):
        return ()
    keys = ("apps",) if child_kind == "app" else ("mcpServers", "mcp_servers", "mcp")
    children: object = next((payload[key] for key in keys if key in payload), payload)
    if isinstance(children, Mapping):
        return tuple(
            _child_mapping(child_kind, identity, metadata)
            for identity, metadata in children.items()
            if isinstance(identity, str) and identity.strip()
        )
    if isinstance(children, Sequence) and not isinstance(children, (str, bytes)):
        return tuple(
            dict(item, kind=child_kind)
            for item in children
            if isinstance(item, Mapping)
        )
    return ()


def _normalize_declared_child_mapping(
    payload: Mapping[str, object],
    child_kind: str,
) -> tuple[Mapping[str, object], ...]:
    """支援 inline identity→metadata map，同時保留既有 mapping child contract。"""

    if any(key in payload for key in ("provider_id", "id", "name", "description", "kind")):
        normalized = dict(payload)
        normalized.setdefault("kind", child_kind)
        return (normalized,)
    return tuple(
        _child_mapping(child_kind, identity, metadata)
        for identity, metadata in payload.items()
        if isinstance(identity, str) and identity.strip()
    )


def _child_mapping(child_kind: str, identity: str, metadata: object) -> dict[str, object]:
    """只投影 manifest public child identity/name/description，不推導 readiness。"""

    result: dict[str, object] = {"kind": child_kind, "provider_id": identity.strip(), "name": identity.strip()}
    if isinstance(metadata, Mapping):
        result["provider_id"] = metadata.get("provider_id", metadata.get("id", identity.strip()))
        result["name"] = metadata.get("name", metadata.get("title", identity.strip()))
        if "description" in metadata:
            result["description"] = metadata["description"]
        elif "summary" in metadata:
            result["description"] = metadata["summary"]
    elif isinstance(metadata, str) and metadata.strip():
        result["description"] = metadata.strip()
    return result


def discover_provider_inventory(
    *,
    host_capability_snapshot: HostCapabilitySnapshot | None = None,
    host_native_registry: Sequence[Mapping[str, object]] | Mapping[str, object] = (),
    plugin_manifests: Sequence[Mapping[str, object]] = (),
) -> ProviderDiscoveryInventory:
    """合併 Host snapshot、Host-native、Plugin child inventory，僅做 exact identity merge。"""

    snapshot_inventory = (
        ProviderDiscoveryInventory(())
        if host_capability_snapshot is None
        else discover_host_capability_snapshot_inventory(host_capability_snapshot)
    )
    native = (
        ProviderDiscoveryInventory(())
        if not host_native_registry
        else discover_host_native_provider_inventory(host_native_registry)
    )
    plugins = discover_active_plugin_children(plugin_manifests)
    combined: dict[tuple[str, str], SupportingProviderDeclaration] = {}
    diagnostics = list(snapshot_inventory.diagnostics) + list(native.diagnostics) + list(plugins.diagnostics)
    for declaration in (
        *snapshot_inventory.provider_declarations,
        *native.provider_declarations,
        *plugins.provider_declarations,
    ):
        _merge_declaration_with_structural_upgrade(combined, declaration, diagnostics=diagnostics)
    declarations = tuple(sorted(combined.values(), key=lambda item: (item.provider_id.casefold(), item.provider_id, item.kind)))
    raw_evidence_count = (
        snapshot_inventory.raw_evidence_count
        + native.raw_evidence_count
        + plugins.raw_evidence_count
    )
    return ProviderDiscoveryInventory(
        declarations,
        plugins.child_skill_declarations,
        tuple(diagnostics),
        host_snapshot_capability_count=snapshot_inventory.host_snapshot_capability_count,
        host_snapshot_builtin_count=snapshot_inventory.host_snapshot_builtin_count,
        host_snapshot_app_child_count=snapshot_inventory.host_snapshot_app_child_count,
        host_snapshot_mcp_child_count=snapshot_inventory.host_snapshot_mcp_child_count,
        host_snapshot_unclassified_count=snapshot_inventory.host_snapshot_unclassified_count,
        host_snapshot_control_plane_count=snapshot_inventory.host_snapshot_control_plane_count,
        host_snapshot_plugin_child_count=snapshot_inventory.host_snapshot_plugin_child_count,
        host_snapshot_intentionally_excluded_count=snapshot_inventory.host_snapshot_intentionally_excluded_count,
        host_snapshot_id=snapshot_inventory.host_snapshot_id,
        host_snapshot_fingerprint=snapshot_inventory.host_snapshot_fingerprint,
        raw_evidence_count=raw_evidence_count,
        runtime_entity_count=snapshot_inventory.runtime_entity_count + native.runtime_entity_count,
        package_declared_count=plugins.package_declared_count,
        canonical_unique_count=len(declarations),
        exact_duplicate_count=raw_evidence_count - len(declarations),
        metadata_sufficient_count=sum(_has_minimum_provider_metadata(item) for item in declarations),
    )


def _merge_declaration_into(
    target: dict[tuple[str, str], SupportingProviderDeclaration],
    declaration: SupportingProviderDeclaration,
    *,
    diagnostics: list[str] | None = None,
) -> None:
    """依 exact formal identity merge public evidence，不做 semantic ranking。"""

    key = (declaration.kind, declaration.provider_id)
    previous = target.get(key)
    if previous is None:
        target[key] = declaration
        return
    target[key] = _merge_provider_declarations(previous, declaration)
    if diagnostics is not None:
        diagnostics.append(f"exact_identity_merged:{declaration.kind}:{declaration.provider_id}")


def _merge_declaration_with_structural_upgrade(
    target: dict[tuple[str, str], SupportingProviderDeclaration],
    declaration: SupportingProviderDeclaration,
    *,
    diagnostics: list[str] | None = None,
) -> None:
    """合併 exact evidence，並讓 host_tool 升級成可信的精確 Provider kind。

    只有同一個 raw Host capability identity 能和已知 native/App/MCP evidence
    對上時才升級；不做名稱相似度或語意 dedupe。
    """

    key = (declaration.kind, declaration.provider_id)
    if key in target:
        _merge_declaration_into(target, declaration, diagnostics=diagnostics)
        return
    for existing_key, previous in tuple(target.items()):
        if previous.kind == declaration.kind:
            continue
        kinds = {previous.kind, declaration.kind}
        if "host_tool" not in kinds or len(kinds) != 2:
            continue
        if next(iter(kinds - {"host_tool"})) not in {"app", "mcp", "builtin_tool"}:
            continue
        host_tool = previous if previous.kind == "host_tool" else declaration
        precise = declaration if declaration.kind != "host_tool" else previous
        if not _same_raw_host_capability(host_tool, precise):
            continue
        merged = _merge_structural_upgrade(precise, host_tool)
        target.pop(existing_key)
        target[(merged.kind, merged.provider_id)] = merged
        if diagnostics is not None:
            diagnostics.append(
                f"structural_identity_upgraded:{host_tool.provider_id}:{merged.kind}:{merged.provider_id}"
            )
        return
    target[key] = declaration


def _same_raw_host_capability(
    host_tool: SupportingProviderDeclaration,
    precise: SupportingProviderDeclaration,
) -> bool:
    """以 raw identity 或已保存的 child tool identity 做 exact structural match。"""

    raw_identity = host_tool.raw_external_identity or host_tool.host_identity or host_tool.provider_id
    precise_ids = {precise.provider_id, precise.host_identity}
    if precise.raw_external_identity is not None:
        precise_ids.add(precise.raw_external_identity)
    if raw_identity in precise_ids:
        return True
    return any(tool.id == raw_identity for tool in precise.callable_tools)


def _merge_structural_upgrade(
    precise: SupportingProviderDeclaration,
    host_tool: SupportingProviderDeclaration,
) -> SupportingProviderDeclaration:
    """保留精確 Provider kind，同時合併 fallback 的 Host evidence。"""

    bridge = replace(
        host_tool,
        provider_id=precise.provider_id,
        kind=precise.kind,
        host_identity=precise.host_identity,
        host_grouping=precise.host_grouping,
        display_name=precise.display_name,
        raw_external_identity=precise.raw_external_identity or host_tool.raw_external_identity,
        canonical_grouping_key=precise.canonical_grouping_key,
        hierarchy_state=precise.hierarchy_state,
    )
    return _merge_provider_declarations(precise, bridge)


def _merge_provider_declarations(
    left: SupportingProviderDeclaration,
    right: SupportingProviderDeclaration,
) -> SupportingProviderDeclaration:
    """合併同一 Provider 的 presence、metadata、provenance 與 discovery evidence。"""

    if (left.kind, left.provider_id) != (right.kind, right.provider_id):
        raise ValueError("provider declarations can only merge on exact formal identity")
    tools: dict[str, SupportingToolSummary | SupportingToolDeclaration] = {
        item.id: item for item in left.callable_tools
    }
    for tool in right.callable_tools:
        previous = tools.get(tool.id)
        if previous is None:
            tools[tool.id] = tool
        elif _public_json(tool.to_mapping()) < _public_json(previous.to_mapping()):
            tools[tool.id] = tool
    presence_state = (
        "EXPLICITLY_BLOCKED"
        if "EXPLICITLY_BLOCKED" in {left.presence_state, right.presence_state}
        else "PRESENT"
        if "PRESENT" in {left.presence_state, right.presence_state}
        else "ABSENT"
    )
    negative = _merge_text(left.explicit_negative_reason, right.explicit_negative_reason)
    return SupportingProviderDeclaration(
        provider_id=left.provider_id,
        kind=left.kind,
        host_identity=left.host_identity,
        host_grouping=tuple(sorted(set(left.host_grouping + right.host_grouping), key=lambda item: (item.casefold(), item))),
        description=_merge_text(left.description, right.description),
        callable_tools=tuple(tools.values()),
        callable_exposure=left.callable_exposure or right.callable_exposure,
        provenance=_merge_labels(left.provenance, right.provenance),
        display_name=_merge_text(left.display_name, right.display_name),
        presence_state=presence_state,
        explicit_negative_reason=negative,
        discovery_evidence_state=_stronger_discovery_state(
            left.discovery_evidence_state,
            right.discovery_evidence_state,
        ),
        existence_evidence_state=_stronger_existence_state(
            left.existence_evidence_state,
            right.existence_evidence_state,
        ),
        raw_external_identity=_merge_text(left.raw_external_identity, right.raw_external_identity),
        canonical_grouping_key=_merge_text(left.canonical_grouping_key, right.canonical_grouping_key),
        metadata_quality=_stronger_metadata_quality(left.metadata_quality, right.metadata_quality),
        hierarchy_state=left.hierarchy_state or right.hierarchy_state,
    )


def _merge_labels(*values: Sequence[str]) -> tuple[str, ...]:
    """合併 abstract labels 並保持 deterministic 順序。"""

    return tuple(sorted({item for group in values for item in group}, key=lambda item: (item.casefold(), item)))


def _merge_text(left: str | None, right: str | None) -> str | None:
    """保留可用文字；衝突時以 stable public ordering 解決，不判斷語意優先級。"""

    if left is None:
        return right
    if right is None or left == right:
        return left
    return min(left, right, key=lambda item: (item.casefold(), item))


def _stronger_discovery_state(left: str, right: str) -> str:
    """以 discovery evidence 強度合併，不把 readiness 當作 discovery。"""

    strength = {
        "NOT_DISCOVERED": 0,
        "DECLARED_ONLY": 1,
        "DISCOVERED_DECLARED": 2,
        "DISCOVERED_TRUSTED": 3,
    }
    return left if strength[left] >= strength[right] else right


def _stronger_existence_state(
    left: ExistenceEvidenceState,
    right: ExistenceEvidenceState,
) -> ExistenceEvidenceState:
    """合併同一 Provider 的 source scope；只保留較強的可路由存在證據。"""

    strength = {
        ExistenceEvidenceState.DECLARATION_ONLY: 0,
        ExistenceEvidenceState.PACKAGE_DECLARED_PRESENT: 1,
        ExistenceEvidenceState.RUNTIME_ENTITY_PRESENT: 2,
        ExistenceEvidenceState.HOST_SESSION_EXPOSED: 3,
        ExistenceEvidenceState.FILESYSTEM_PRESENT: 1,
    }
    return left if strength[left] >= strength[right] else right


def _stronger_metadata_quality(left, right):
    """合併同一 Provider 的 metadata 品質；不把品質當成存在 gate。"""

    strength = {"OPAQUE": 0, "SPARSE": 1, "SUFFICIENT": 2}
    left_value = left.value
    right_value = right.value
    return left if strength[left_value] >= strength[right_value] else right


def _plugin_child_path_is_contained(
    manifest: Mapping[str, object],
    raw_path: object,
) -> bool:
    """驗證 Plugin App/MCP child path 經 resolve 後仍在 package root。"""

    package_root_value = manifest.get("package_root", manifest.get("package_path"))
    if package_root_value is None or not isinstance(package_root_value, (str, Path)):
        return False
    if not isinstance(raw_path, (str, Path)):
        return False
    package_root = Path(package_root_value).resolve()
    path = Path(raw_path)
    if not path.is_absolute():
        path = package_root / path
    try:
        path.resolve().relative_to(package_root)
    except ValueError:
        return False
    return True


def _public_json(value: object) -> str:
    """建立只含 public metadata 的 deterministic comparison key。"""

    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def build_official_provider_requests(
    app_ids: Sequence[str] = (),
    *,
    thread_id: str | None = None,
) -> tuple[dict[str, object], ...]:
    """建立 prepare/finalize 共用的官方 App/MCP fresh-read request specs。"""

    list_params: dict[str, object] = {"forceRefetch": True}
    installed_params: dict[str, object] = {"forceRefresh": True}
    read_params: dict[str, object] = {"appIds": list(app_ids), "includeTools": True}
    mcp_params: dict[str, object] = {"detail": MCP_STATUS_DETAIL}
    if thread_id is not None:
        list_params["threadId"] = thread_id
        installed_params["threadId"] = thread_id
        read_params["threadId"] = thread_id
        mcp_params["threadId"] = thread_id
    return (
        {"method": APP_LIST_METHOD, "params": list_params},
        {"method": APP_INSTALLED_METHOD, "params": installed_params},
        {"method": APP_READ_METHOD, "params": read_params},
        {"method": MCP_STATUS_LIST_METHOD, "params": mcp_params},
    )


@dataclass(frozen=True)
class ProviderAdapterInventory:
    """一個官方 Host surface 的只讀 Provider inventory。"""

    kind: str
    provider_declarations: tuple[SupportingProviderDeclaration, ...]
    readiness_evidence: tuple[AppReadinessEvidence | McpReadinessEvidence, ...]
    discovered_count: int
    hard_eligible_count: int
    diagnostics: tuple[str, ...] = ()
    detail: str | None = None
    present_count: int | None = None
    selectable_count: int | None = None
    verified_ready_count: int | None = None
    present_unverified_count: int | None = None
    metadata_insufficient_count: int | None = None
    explicit_negative_count: int | None = None
    runtime_entity_count: int | None = None
    package_declared_count: int = 0
    canonical_union_count: int | None = None
    exact_duplicate_count: int = 0
    metadata_sufficient_count: int | None = None
    metadata_sparse_count: int | None = None
    metadata_opaque_count: int | None = None
    identity_unresolved_count: int = 0
    semantically_considered_count: int | None = None
    never_considered_count: int | None = None

    def __post_init__(self) -> None:
        """固定 adapter 結果並防止跨 kind 混入。"""

        if self.kind not in {"app", "mcp"}:
            raise ValueError("unsupported official Provider adapter kind")
        if not isinstance(self.provider_declarations, tuple) or not isinstance(self.readiness_evidence, tuple):
            raise TypeError("adapter inventory records must be tuples")
        if self.discovered_count < 0 or self.hard_eligible_count < 0 or self.hard_eligible_count > self.discovered_count:
            raise ValueError("invalid adapter inventory counts")
        if self.detail is not None and self.detail != MCP_STATUS_DETAIL:
            raise ValueError("unsupported MCP detail")
        defaults = {
            "present_count": self.discovered_count,
            "selectable_count": self.hard_eligible_count,
            "verified_ready_count": self.hard_eligible_count,
            "present_unverified_count": 0,
            "metadata_insufficient_count": 0,
            "explicit_negative_count": 0,
            "runtime_entity_count": self.discovered_count,
            "canonical_union_count": self.discovered_count,
            "metadata_sufficient_count": sum(
                item.metadata_quality.value == "SUFFICIENT" for item in self.provider_declarations
            ),
            "metadata_sparse_count": sum(
                item.metadata_quality.value == "SPARSE" for item in self.provider_declarations
            ),
            "metadata_opaque_count": sum(
                item.metadata_quality.value == "OPAQUE" for item in self.provider_declarations
            ),
            "identity_unresolved_count": 0,
            "semantically_considered_count": 0,
            "never_considered_count": (
                self.selectable_count if self.selectable_count is not None else self.hard_eligible_count
            ),
        }
        for field_name, default in defaults.items():
            value = getattr(self, field_name)
            if value is None:
                object.__setattr__(self, field_name, default)
            elif isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{field_name} must be a non-negative integer or null")
        if self.present_count > self.discovered_count:
            raise ValueError("present_count cannot exceed discovered_count")
        if self.selectable_count > self.present_count:
            raise ValueError("selectable_count cannot exceed present_count")
        if self.verified_ready_count != self.hard_eligible_count:
            raise ValueError("verified_ready_count must match hard_eligible_count")
        if self.verified_ready_count + self.present_unverified_count != self.selectable_count:
            raise ValueError("readiness counts must account for selectable providers")
        for field_name in ("package_declared_count", "exact_duplicate_count"):
            value = getattr(self, field_name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{field_name} must be a non-negative integer")
        for field_name in (
            "metadata_sufficient_count",
            "metadata_sparse_count",
            "metadata_opaque_count",
            "identity_unresolved_count",
            "semantically_considered_count",
            "never_considered_count",
        ):
            value = getattr(self, field_name)
            if value is None:
                object.__setattr__(self, field_name, defaults[field_name])
            elif isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{field_name} must be a non-negative integer or null")
        if self.semantically_considered_count + self.never_considered_count != self.selectable_count:
            raise ValueError("Provider consideration counts must account for selectable providers")
        if self.runtime_entity_count > self.discovered_count:
            raise ValueError("runtime_entity_count cannot exceed discovered_count")
        if self.canonical_union_count < self.runtime_entity_count:
            raise ValueError("canonical_union_count cannot be below runtime_entity_count")
        if self.exact_duplicate_count != self.runtime_entity_count + self.package_declared_count - self.canonical_union_count:
            raise ValueError("exact_duplicate_count must match adapter source counts")

    @property
    def hard_eligible_ids(self) -> tuple[str, ...]:
        """回傳已通過 deterministic hard gate 的 canonical IDs。"""

        evidence = {item.provider_id: item for item in self.readiness_evidence}
        result = []
        for declaration in self.provider_declarations:
            item = evidence.get(declaration.provider_id)
            if item is None:
                continue
            if isinstance(item, AppReadinessEvidence):
                eligible = item.hard_eligible and _app_hard_tool_surface(declaration)
            else:
                eligible = item.hard_eligible and bool(declaration.callable_tools)
            if eligible:
                result.append(declaration.provider_id)
        return tuple(sorted(result, key=lambda value: (value.casefold(), value)))

    def blind_metrics(self) -> dict[str, int]:
        """輸出官方 adapter 的 source-scope metrics，不含 UI expected count。"""

        return {
            "runtime_entity_count": self.runtime_entity_count,
            "package_declared_count": self.package_declared_count,
            "canonical_union_count": self.canonical_union_count,
            "exact_duplicate_count": self.exact_duplicate_count,
            "metadata_sufficient_count": self.metadata_sufficient_count,
            "metadata_sparse_count": self.metadata_sparse_count,
            "metadata_opaque_count": self.metadata_opaque_count,
            "identity_unresolved_count": self.identity_unresolved_count,
            "semantically_considered_count": self.semantically_considered_count,
            "never_considered_count": self.never_considered_count,
        }


def adapt_official_app_inventory(
    app_list_response: Mapping[str, object],
    app_installed_response: Mapping[str, object],
    app_read_response: Mapping[str, object],
    *,
    provenance: Sequence[str] = (),
) -> ProviderAdapterInventory:
    """解析 `app/list`, `app/installed`, `app/read` 的官方欄位。"""

    listed = _records(app_list_response, "data")
    installed = _records(app_installed_response, "apps")
    read = _records(app_read_response, "apps")
    missing = _identifiers(app_read_response.get("missingAppIds", ()), "missingAppIds")
    installed_by_id = _unique_by_id(installed, "installed App")
    read_by_id = _unique_by_id(read, "read App")
    declarations: list[SupportingProviderDeclaration] = []
    evidence: list[AppReadinessEvidence] = []
    diagnostics: list[str] = []

    for item in listed:
        app_id = _id(item, "App")
        name = _text(item.get("name"), "App name")
        description = _nullable_text(item.get("description"), "App description")
        accessible = _bool(item.get("isAccessible"), "App isAccessible")
        configured_enabled = _bool(item.get("isEnabled"), "App isEnabled")
        installed_item = installed_by_id.get(app_id)
        read_item = read_by_id.get(app_id)
        runtime_name: str | None = None
        runtime_enabled = False
        callable_state = False
        runtime_evidence_available = installed_item is not None
        if installed_item is None:
            diagnostics.append(f"app_missing_installed:{app_id}")
        else:
            runtime_name = _nullable_text(installed_item.get("runtimeName"), "App runtimeName")
            runtime_enabled = _bool(installed_item.get("enabled"), "App enabled")
            callable_state = _bool(installed_item.get("callable"), "App callable")

        metadata_readable = read_item is not None and app_id not in missing
        tools: tuple[SupportingToolSummary, ...] = ()
        if metadata_readable:
            if read_item.get("id") != app_id:
                metadata_readable = False
                diagnostics.append(f"app_read_identity_mismatch:{app_id}")
            else:
                raw_tools = read_item.get("toolSummaries")
                if raw_tools is not None:
                    if not isinstance(raw_tools, Sequence) or isinstance(raw_tools, (str, bytes)):
                        raise ValueError("ConnectorMetadata.toolSummaries must be a list or null")
                    parsed_tools = []
                    for raw_tool in raw_tools:
                        parsed = _app_tool_summary(raw_tool)
                        # Tool enabled/callable 是 execution readiness；保留所有
                        # 可讀 summary 讓 Provider semantic consideration 不漏掉。
                        parsed_tools.append(parsed)
                    tools = tuple(parsed_tools)
                if not tools:
                    diagnostics.append(f"app_no_enabled_tool_summary:{app_id}")
        else:
            diagnostics.append(f"app_metadata_unreadable:{app_id}")

        declaration = SupportingProviderDeclaration(
            provider_id=app_id,
            kind="app",
            host_identity=app_id,
            host_grouping=("app",),
            description=description,
            callable_tools=tools,
            callable_exposure=metadata_readable and any(tool.is_enabled for tool in tools),
            provenance=tuple(provenance),
            display_name=name,
            existence_evidence_state=ExistenceEvidenceState.RUNTIME_ENTITY_PRESENT,
        )
        declarations.append(declaration)
        evidence.append(
            AppReadinessEvidence(
                provider_id=app_id,
                accessible=accessible,
                configured_enabled=configured_enabled,
                runtime_enabled=runtime_enabled,
                callable=callable_state,
                metadata_readable=metadata_readable,
                runtime_name=runtime_name,
                runtime_evidence_available=runtime_evidence_available,
                provenance=tuple(provenance),
            )
        )

    hard_count = sum(
        1
        for declaration, item in zip(declarations, evidence)
        if item.hard_eligible and _app_hard_tool_surface(declaration)
    )
    selectable_count = sum(
        1
        for declaration, item in zip(declarations, evidence)
        if _is_selectable_provider(declaration, item)
    )
    present_unverified_count = sum(
        1
        for declaration, item in zip(declarations, evidence)
        if _is_present_unverified_provider(declaration, item)
    )
    return ProviderAdapterInventory(
        kind="app",
        provider_declarations=tuple(declarations),
        readiness_evidence=tuple(evidence),
        discovered_count=len(listed),
        hard_eligible_count=hard_count,
        diagnostics=tuple(diagnostics),
        present_count=len(declarations),
        selectable_count=selectable_count,
        verified_ready_count=hard_count,
        present_unverified_count=present_unverified_count,
        metadata_insufficient_count=sum(not _has_minimum_provider_metadata(item) for item in declarations),
        explicit_negative_count=sum(item.readiness_state == "KNOWN_UNAVAILABLE" for item in evidence),
    )


def adapt_official_mcp_inventory(
    mcp_status_response: Mapping[str, object],
    *,
    provenance: Sequence[str] = (),
    detail: str = MCP_STATUS_DETAIL,
) -> ProviderAdapterInventory:
    """解析 `mcpServerStatus/list(detail=toolsAndAuthOnly)` 的官方欄位。"""

    if detail != MCP_STATUS_DETAIL:
        raise ValueError("MCP adapter requires detail=toolsAndAuthOnly")
    servers = _records(mcp_status_response, "data")
    declarations: list[SupportingProviderDeclaration] = []
    evidence: list[McpReadinessEvidence] = []
    diagnostics: list[str] = []
    for server in servers:
        server_id = _text(server.get("name"), "MCP server identity")
        runtime_status = server.get("runtimeStatus")
        if runtime_status is not None and not isinstance(runtime_status, str):
            raise ValueError("MCP runtimeStatus must be an official enum or null")
        auth_status = server.get("authStatus")
        if not isinstance(auth_status, str):
            raise ValueError("MCP authStatus must be an official enum")
        plugin_id = server.get("pluginId")
        if plugin_id is not None:
            plugin_id = _text(plugin_id, "MCP pluginId")
        raw_tools = server.get("tools")
        if not isinstance(raw_tools, Mapping):
            raise ValueError("MCP tools must be an object")
        tools: list[SupportingToolDeclaration] = []
        for key, raw_tool in raw_tools.items():
            if not isinstance(key, str) or not isinstance(raw_tool, Mapping):
                diagnostics.append(f"mcp_invalid_tool:{server_id}")
                continue
            parsed = _mcp_tool(key, raw_tool, provenance=provenance)
            if parsed is not None:
                tools.append(parsed)
        server_info = server.get("serverInfo")
        description = None
        if isinstance(server_info, Mapping):
            description = _nullable_text(server_info.get("description"), "MCP server description")
        if not tools:
            diagnostics.append(f"mcp_no_usable_tool:{server_id}")
        declaration = SupportingProviderDeclaration(
            provider_id=server_id,
            kind="mcp",
            host_identity=server_id,
            host_grouping=("mcpServerStatus",),
            description=description,
            callable_tools=tuple(tools),
            callable_exposure=bool(tools),
            provenance=tuple(provenance),
            display_name=server_id,
            existence_evidence_state=ExistenceEvidenceState.RUNTIME_ENTITY_PRESENT,
        )
        declarations.append(declaration)
        evidence.append(
            McpReadinessEvidence(
                provider_id=server_id,
                runtime_status=runtime_status,
                auth_status=auth_status,
                callable_tool_ids=tuple(tool.id for tool in tools),
                plugin_id=plugin_id,
                provenance=tuple(provenance),
            )
        )
    hard_count = sum(
        1
        for declaration, item in zip(declarations, evidence)
        if item.hard_eligible and bool(declaration.callable_tools)
    )
    selectable_count = sum(
        1
        for declaration, item in zip(declarations, evidence)
        if _is_selectable_provider(declaration, item)
    )
    present_unverified_count = sum(
        1
        for declaration, item in zip(declarations, evidence)
        if _is_present_unverified_provider(declaration, item)
    )
    return ProviderAdapterInventory(
        kind="mcp",
        provider_declarations=tuple(declarations),
        readiness_evidence=tuple(evidence),
        discovered_count=len(servers),
        hard_eligible_count=hard_count,
        diagnostics=tuple(diagnostics),
        detail=detail,
        present_count=len(declarations),
        selectable_count=selectable_count,
        verified_ready_count=hard_count,
        present_unverified_count=present_unverified_count,
        metadata_insufficient_count=sum(not _has_minimum_provider_metadata(item) for item in declarations),
        explicit_negative_count=sum(item.readiness_state == "KNOWN_UNAVAILABLE" for item in evidence),
    )


def adapt_codex_mcp_cli_inventory(
    payload: Sequence[Mapping[str, object]],
    *,
    provenance: Sequence[str] = ("cli:codex-mcp-list",),
) -> ProviderAdapterInventory:
    """將現行 `codex mcp list --json` 的 server list 轉成存在 Provider。

    CLI list 只提供 configured/runtime entity identity；未把 snake_case
    readiness 欄位猜成 `mcpServerStatus/list` certificate。沒有 identity 的
    record 留下 diagnostic，未知 optional 欄位忽略；所有已解析 server 都
    是 PRESENT、PRESENT_UNVERIFIED 且可進 semantic consideration。
    """

    if isinstance(payload, (str, bytes)) or not isinstance(payload, Sequence):
        raise ValueError("codex MCP CLI payload must be a list")
    declarations_by_id: dict[str, SupportingProviderDeclaration] = {}
    diagnostics: list[str] = []
    valid_entry_count = 0
    for item in payload:
        if not isinstance(item, Mapping):
            diagnostics.append("mcp_cli_invalid_entry")
            continue
        try:
            server_id = _text(item.get("name"), "MCP CLI server identity")
            declaration = SupportingProviderDeclaration(
                provider_id=server_id,
                kind="mcp",
                host_identity=server_id,
                host_grouping=("mcp-cli",),
                description=None,
                callable_tools=(),
                callable_exposure=False,
                provenance=tuple(provenance),
                display_name=server_id,
                discovery_evidence_state="DISCOVERED_TRUSTED",
                existence_evidence_state=ExistenceEvidenceState.RUNTIME_ENTITY_PRESENT,
            )
        except (TypeError, ValueError):
            diagnostics.append("mcp_cli_missing_or_invalid_identity")
            continue
        valid_entry_count += 1
        if server_id in declarations_by_id:
            diagnostics.append(f"mcp_cli_exact_duplicate:{server_id}")
            continue
        declarations_by_id[server_id] = declaration
    declarations = tuple(
        sorted(declarations_by_id.values(), key=lambda item: (item.provider_id.casefold(), item.provider_id))
    )
    sufficient = sum(item.metadata_quality.value == "SUFFICIENT" for item in declarations)
    sparse = sum(item.metadata_quality.value == "SPARSE" for item in declarations)
    opaque = sum(item.metadata_quality.value == "OPAQUE" for item in declarations)
    return ProviderAdapterInventory(
        kind="mcp",
        provider_declarations=declarations,
        readiness_evidence=(),
        discovered_count=len(payload),
        hard_eligible_count=0,
        diagnostics=tuple(diagnostics),
        detail=None,
        present_count=len(declarations),
        selectable_count=len(declarations),
        verified_ready_count=0,
        present_unverified_count=len(declarations),
        metadata_insufficient_count=sparse + opaque,
        explicit_negative_count=0,
        runtime_entity_count=valid_entry_count,
        package_declared_count=0,
        canonical_union_count=len(declarations),
        exact_duplicate_count=valid_entry_count - len(declarations),
        metadata_sufficient_count=sufficient,
        metadata_sparse_count=sparse,
        metadata_opaque_count=opaque,
        semantically_considered_count=0,
        never_considered_count=len(declarations),
    )


def _records(payload: Mapping[str, object], key: str) -> list[Mapping[str, object]]:
    """讀取官方 response list，不對缺欄位做推測。"""

    if not isinstance(payload, Mapping):
        raise TypeError("Host response must be a mapping")
    value = payload.get(key)
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise ValueError(f"Host response {key} must be a list")
    if not all(isinstance(item, Mapping) for item in value):
        raise ValueError(f"Host response {key} contains a non-object record")
    return list(value)  # type: ignore[arg-type]


def _source_records(
    payload: Sequence[Mapping[str, object]] | Mapping[str, object],
    key: str,
) -> list[Mapping[str, object]]:
    """讀取 generic trusted source envelope，不猜測缺少的 registry 欄位。"""

    if isinstance(payload, Mapping):
        return _records(payload, key)
    if isinstance(payload, (str, bytes)) or not isinstance(payload, Sequence):
        raise ValueError("trusted capability source must be a sequence or mapping envelope")
    if not all(isinstance(item, Mapping) for item in payload):
        raise ValueError("trusted capability source contains a non-object record")
    return list(payload)  # type: ignore[arg-type]


def _unique_by_id(records: Sequence[Mapping[str, object]], label: str) -> dict[str, Mapping[str, object]]:
    """建立 exact canonical ID index，拒絕 ambiguous duplicate records。"""

    result: dict[str, Mapping[str, object]] = {}
    for record in records:
        identifier = _id(record, label)
        if identifier in result:
            raise ValueError(f"duplicate {label} identity")
        result[identifier] = record
    return result


def _identifiers(value: object, field: str) -> set[str]:
    """驗證官方 ID 清單。"""

    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise ValueError(f"{field} must be a list")
    return {_text(item, field) for item in value}


def _id(record: Mapping[str, object], label: str) -> str:
    """取得官方 App `id`，不接受 display/name 猜測。"""

    value = record.get("id")
    return _text(value, f"{label} identity")


def _text(value: object, field: str) -> str:
    """驗證 bounded public text；實際安全限制由 supporting model 統一執行。"""

    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be non-empty text")
    return value.strip()


def _nullable_text(value: object, field: str) -> str | None:
    """保留官方 nullable metadata，不以 placeholder 填補。"""

    if value is None:
        return None
    return _text(value, field)


def _bool(value: object, field: str) -> bool:
    """驗證官方 boolean 欄位。"""

    if not isinstance(value, bool):
        raise ValueError(f"{field} must be boolean")
    return value


def _has_minimum_provider_metadata(declaration: SupportingProviderDeclaration) -> bool:
    """確認 Provider description 或 tool summary 足以交給 LLM 理解。"""

    if declaration.description is not None and declaration.description.strip():
        return True
    return any(
        bool(getattr(tool, "description", "").strip()) or bool(getattr(tool, "title", None))
        for tool in declaration.callable_tools
    )


def _app_hard_tool_surface(declaration: SupportingProviderDeclaration) -> bool:
    """判斷 App 是否具備 hard-ready tool surface；不影響 semantic presence。"""

    return bool(declaration.callable_tools) and all(
        not isinstance(tool, SupportingToolSummary)
        or (tool.is_enabled and tool.disabled_reason is None)
        for tool in declaration.callable_tools
    )


def _is_selectable_provider(declaration: SupportingProviderDeclaration, evidence: object) -> bool:
    """只以 formal presence 與 resolved identity 計算 selectable Provider。

    `evidence` 仍由 caller 傳入以維持 adapter API，但 readiness state 不再是
    semantic candidate exclusion gate；metadata quality 與 execution phase 只作
    診斷，不會讓已存在 Provider 從 LLM consideration 消失。
    """

    return (
        declaration.kind in FORMAL_SUPPORTING_PROVIDER_KINDS
        and declaration.presence_state == "PRESENT"
        and declaration.existence_evidence_state != ExistenceEvidenceState.DECLARATION_ONLY
    )


def _is_present_unverified_provider(declaration: SupportingProviderDeclaration, evidence: object) -> bool:
    """計算尚未具備完整 callable surface 的 optimistic Provider。"""

    return _is_selectable_provider(declaration, evidence) and not (
        getattr(evidence, "readiness_state", None) == "VERIFIED_READY"
        and declaration.callable_exposure
        and bool(declaration.callable_tools)
    )


def _app_tool_summary(value: object) -> SupportingToolSummary:
    """把官方 AppToolSummary 轉成無 schema 的 public summary。"""

    if not isinstance(value, Mapping):
        raise ValueError("App tool summary must be an object")
    return SupportingToolSummary(
        id=_text(value.get("name"), "App tool name"),
        title=None if value.get("title") is None else _text(value.get("title"), "App tool title"),
        description=_text(value.get("description"), "App tool description"),
        is_enabled=_bool(value.get("isEnabled"), "App tool isEnabled"),
        disabled_reason=(
            None if value.get("disabledReason") is None else _text(value.get("disabledReason"), "App tool disabledReason")
        ),
        is_read_only=_bool(value.get("isReadOnly"), "App tool isReadOnly"),
    )


def _mcp_tool(
    key: str,
    value: Mapping[str, object],
    *,
    provenance: Sequence[str],
) -> SupportingToolDeclaration | None:
    """保留 MCP tool 的官方 inputSchema，沒有完整 metadata 就排除。"""

    tool_name = _text(value.get("name"), "MCP tool name")
    if tool_name != key:
        raise ValueError("MCP tool map key and Tool.name disagree")
    # Schema 是 execution detail，不是 semantic discovery 的最低 metadata；
    # 缺少或不完整時保留 public tool summary，將 readiness/detail 留給後續階段。
    schema = value.get("inputSchema", {})
    if not isinstance(schema, Mapping):
        schema = {}
    description_value = value.get("description", value.get("title"))
    if not isinstance(description_value, str) or not description_value.strip():
        return None
    return SupportingToolDeclaration(
        id=tool_name,
        description=description_value,
        schema=schema,
        provenance=tuple(provenance),
    )
