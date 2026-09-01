"""Official Codex App Server Provider adapters.

這個模組只把 Host 已取得的 typed protocol response 正規化成 Router
Provider declarations/readiness evidence；不呼叫 RPC、不執行 tool，也不使用
under-development 的 Plugin RPC。
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from .supporting_context import (
    AppReadinessEvidence,
    McpReadinessEvidence,
    SupportingProviderDeclaration,
    SupportingToolDeclaration,
    SupportingToolSummary,
)

# 修改紀錄（2026-09-01，Steve Peng）
# 原始內容：官方 App/MCP adapter 只有 hard_eligible count，缺少 presence 與 unverified readiness 統計。
# 修改原因：Optimistic Supporting Provider Selection Upgrade 要讓 readiness unknown 不再阻擋 semantic candidate。
# 修改後功能：官方 adapter 保留 hard-ready evidence，同時回報 present/selectable/unverified；不把 package 或 Plugin state 當 runtime readiness。


APP_LIST_METHOD = "app/list"
APP_INSTALLED_METHOD = "app/installed"
APP_READ_METHOD = "app/read"
MCP_STATUS_LIST_METHOD = "mcpServerStatus/list"
MCP_STATUS_DETAIL = "toolsAndAuthOnly"


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
                eligible = item.hard_eligible and bool(declaration.callable_tools)
            else:
                eligible = item.hard_eligible and bool(declaration.callable_tools)
            if eligible:
                result.append(declaration.provider_id)
        return tuple(sorted(result, key=lambda value: (value.casefold(), value)))


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
                        if parsed.is_enabled:
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
            callable_exposure=metadata_readable and bool(tools),
            provenance=tuple(provenance),
            display_name=name,
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
        if item.hard_eligible and bool(declaration.callable_tools)
    )
    selectable_count = sum(
        1
        for declaration, item in zip(declarations, evidence)
        if declaration.callable_exposure
        and bool(declaration.callable_tools)
        and item.readiness_state != "KNOWN_UNAVAILABLE"
    )
    present_unverified_count = sum(
        1
        for declaration, item in zip(declarations, evidence)
        if declaration.callable_exposure
        and bool(declaration.callable_tools)
        and item.readiness_state == "PRESENT_UNVERIFIED"
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
        metadata_insufficient_count=sum(not bool(item.callable_tools) for item in declarations),
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
        if declaration.callable_exposure
        and bool(declaration.callable_tools)
        and item.readiness_state != "KNOWN_UNAVAILABLE"
    )
    present_unverified_count = sum(
        1
        for declaration, item in zip(declarations, evidence)
        if declaration.callable_exposure
        and bool(declaration.callable_tools)
        and item.readiness_state == "PRESENT_UNVERIFIED"
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
        metadata_insufficient_count=sum(not bool(item.callable_tools) for item in declarations),
        explicit_negative_count=sum(item.readiness_state == "KNOWN_UNAVAILABLE" for item in evidence),
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
    schema = value.get("inputSchema")
    if not isinstance(schema, Mapping):
        raise ValueError("MCP Tool.inputSchema must be an object")
    description_value = value.get("description", value.get("title"))
    if not isinstance(description_value, str) or not description_value.strip():
        return None
    return SupportingToolDeclaration(
        id=tool_name,
        description=description_value,
        schema=schema,
        provenance=tuple(provenance),
    )
