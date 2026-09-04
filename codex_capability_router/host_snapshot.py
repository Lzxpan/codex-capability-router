"""Controller-owned Host capability snapshot contract。

這個模組只驗證 Host/controller 傳入的 session-scoped public metadata；不掃描
檔案系統、不呼叫工具、不推導 authorization、category 或 semantic priority。
"""

from __future__ import annotations

# 修改紀錄（2026-09-02，Steve Peng）
# 原始內容：Host snapshot 只有既成 envelope parser，controller 的 current-session public registry 沒有明確 projection contract。
# 修改原因：beta.3 需要讓 controller 已取得的 public registry 以 task-independent 方式投影進同一個 trusted snapshot boundary。
# 修改後功能：新增 explicit-field controller registry projection；不解析 hidden prompt/CoT、不依 tool name 猜 hierarchy。
# 修改紀錄（2026-09-01，Steve Peng）
# 原始內容：Router 只有 raw host_native_provider_registry，沒有 controller-owned
# 的 typed session capability snapshot 與 hierarchy diagnostics。
# 修改原因：Host 已知道本 session 暴露的 capability，但 Python 沒有 machine-readable
# registry；需要一條 bounded、可稽核且不依賴特定 tool ID 的 Host → Router bridge。
# 修改後功能：新增 trusted_host_snapshot envelope、公開 capability 欄位、identity/fingerprint
# 驗證與 hierarchy/exposure state；信任邊界由 Codex controller/orchestration layer 承擔。
# 修改紀錄（2026-09-02，Steve Peng）
# 原始內容：formalizable_count 只計算已知 host_native/App/MCP hierarchy。
# 修改原因：beta.4 對 unknown hierarchy 提供正式 host_tool fallback，不能讓 snapshot metrics 將其視為不可 formalize。
# 修改後功能：formalizable_count 也涵蓋已暴露且 identity 已解析的 unknown capability；control-plane/Plugin 仍為 boundary exclusion。

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import hashlib
import json
import re


HOST_SNAPSHOT_TRUST_MARKER = "trusted_host_snapshot"
HOST_SNAPSHOT_PROVENANCE = "host-session-capability-snapshot"
HOST_SNAPSHOT_CONTRACT_VERSION = "v0.2-host-capability-snapshot-v1"
MAX_HOST_SNAPSHOT_CAPABILITIES = 4096

HOST_EXPOSURE_STATES = frozenset({"EXPOSED", "NOT_EXPOSED", "BLOCKED", "UNKNOWN"})
HOST_HIERARCHIES = frozenset({"host_native", "app_child", "mcp_child", "plugin_child", "control_plane", "unknown"})
HOST_PARENT_KINDS = frozenset({"app", "mcp", "plugin"})
_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]*$")
_SENSITIVE_ASSIGNMENT = re.compile(
    r"(?:api[_-]?key|password|secret|token|credential)\s*(?:=|:)\s*[^\s,;]+",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class HostCapability:
    """Host 暴露的單一 capability public record。

    `hierarchy` 若未由 Host 明確提供，仍保留為 `unknown`，由 Provider adapter
    轉成 `host_tool` fallback；不可猜成 App/MCP/native。可選 runtime 欄位只作
    evidence，不會被轉成 authorization、connection 或 semantic category。
    """

    namespace: str
    action_name: str
    display_name: str
    description: str | None
    exposure_state: str = "EXPOSED"
    hierarchy: str = "unknown"
    parent_kind: str | None = None
    parent_identity: str | None = None
    provenance: tuple[str, ...] = (HOST_SNAPSHOT_PROVENANCE,)
    is_read_only: bool | None = None
    has_side_effect: bool | None = None
    callable_evidence: bool | None = None

    def __post_init__(self) -> None:
        """驗證 Host public identity、hierarchy 與不含秘密的 bounded metadata。"""

        object.__setattr__(self, "namespace", _identifier(self.namespace, "capability namespace"))
        object.__setattr__(self, "action_name", _identifier(self.action_name, "capability action name"))
        object.__setattr__(self, "display_name", _text(self.display_name, "capability display name", 512))
        object.__setattr__(self, "description", _nullable_text(self.description, "capability description", 2048))
        if self.exposure_state not in HOST_EXPOSURE_STATES:
            raise ValueError("unsupported Host capability exposure state")
        if self.hierarchy not in HOST_HIERARCHIES:
            raise ValueError("unsupported Host capability hierarchy")
        if self.parent_kind is not None:
            if self.parent_kind not in HOST_PARENT_KINDS:
                raise ValueError("unsupported Host capability parent kind")
            object.__setattr__(self, "parent_kind", _identifier(self.parent_kind, "capability parent kind"))
        if self.parent_identity is not None:
            object.__setattr__(self, "parent_identity", _identifier(self.parent_identity, "capability parent identity"))
        if self.hierarchy in {"app_child", "mcp_child", "plugin_child"}:
            expected = {"app_child": "app", "mcp_child": "mcp", "plugin_child": "plugin"}[self.hierarchy]
            if self.parent_kind != expected or self.parent_identity is None:
                raise ValueError("child Host capability requires matching parent kind and identity")
        for field_name in ("is_read_only", "has_side_effect", "callable_evidence"):
            value = getattr(self, field_name)
            if value is not None and not isinstance(value, bool):
                raise ValueError(f"{field_name} must be boolean or null")
        object.__setattr__(self, "provenance", _provenance(self.provenance))
        if HOST_SNAPSHOT_PROVENANCE not in self.provenance:
            raise ValueError("Host capability provenance must identify the session snapshot")

    @property
    def canonical_id(self) -> str:
        """以 Host namespace/action 組合產生 exact capability identity。"""

        return f"{self.namespace}.{self.action_name}"

    @classmethod
    def from_mapping(cls, payload: Mapping[str, object]) -> "HostCapability":
        """Parse one already trusted Host capability mapping。"""

        allowed = {
            "namespace",
            "action_name",
            "display_name",
            "description",
            "exposure_state",
            "hierarchy",
            "parent_kind",
            "parent_identity",
            "provenance",
            "is_read_only",
            "has_side_effect",
            "callable_evidence",
        }
        if set(payload) - allowed:
            raise ValueError("Host capability has unsupported fields")
        return cls(
            namespace=payload.get("namespace"),  # type: ignore[arg-type]
            action_name=payload.get("action_name"),  # type: ignore[arg-type]
            display_name=payload.get("display_name"),  # type: ignore[arg-type]
            description=payload.get("description"),  # type: ignore[arg-type]
            exposure_state=payload.get("exposure_state", "EXPOSED"),  # type: ignore[arg-type]
            hierarchy=payload.get("hierarchy", "unknown"),  # type: ignore[arg-type]
            parent_kind=payload.get("parent_kind"),  # type: ignore[arg-type]
            parent_identity=payload.get("parent_identity"),  # type: ignore[arg-type]
            provenance=payload.get("provenance", (HOST_SNAPSHOT_PROVENANCE,)),  # type: ignore[arg-type]
            is_read_only=payload.get("is_read_only"),  # type: ignore[arg-type]
            has_side_effect=payload.get("has_side_effect"),  # type: ignore[arg-type]
            callable_evidence=payload.get("callable_evidence"),  # type: ignore[arg-type]
        )

    def to_mapping(self) -> dict[str, object]:
        """輸出 bounded public record，不包含 raw arguments 或 private path。"""

        return {
            "canonical_id": self.canonical_id,
            "namespace": self.namespace,
            "action_name": self.action_name,
            "display_name": self.display_name,
            "description": self.description,
            "exposure_state": self.exposure_state,
            "hierarchy": self.hierarchy,
            "parent_kind": self.parent_kind,
            "parent_identity": self.parent_identity,
            "provenance": list(self.provenance),
            "is_read_only": self.is_read_only,
            "has_side_effect": self.has_side_effect,
            "callable_evidence": self.callable_evidence,
        }


@dataclass(frozen=True)
class HostCapabilitySnapshot:
    """由 controller/orchestration layer 建立的 session-scoped Host snapshot。

    Python 無法對一般 Python object 提供 cryptographic origin proof，因此這個
    contract 將 trust boundary 明確放在 caller：只有 controller-owned envelope
    經 `from_trusted_envelope()` 正規化後才能傳入 production route。
    """

    snapshot_id: str
    source: str
    session_scope: str
    capabilities: tuple[HostCapability, ...]
    trust_marker: str = HOST_SNAPSHOT_TRUST_MARKER
    provenance: tuple[str, ...] = (HOST_SNAPSHOT_PROVENANCE,)

    def __post_init__(self) -> None:
        """固定 snapshot 順序、exact identity 與 bounded trust marker。"""

        object.__setattr__(self, "snapshot_id", _identifier(self.snapshot_id, "Host snapshot id"))
        object.__setattr__(self, "source", _text(self.source, "Host snapshot source", 256))
        object.__setattr__(self, "session_scope", _text(self.session_scope, "Host snapshot session scope", 256))
        if self.trust_marker != HOST_SNAPSHOT_TRUST_MARKER:
            raise ValueError("Host snapshot requires trusted_host_snapshot marker")
        object.__setattr__(self, "provenance", _provenance(self.provenance))
        if HOST_SNAPSHOT_PROVENANCE not in self.provenance:
            raise ValueError("Host snapshot provenance must identify the session source")
        capabilities = tuple(self.capabilities)
        if len(capabilities) > MAX_HOST_SNAPSHOT_CAPABILITIES:
            raise ValueError("Host snapshot exceeds bounded capability count")
        if not all(isinstance(item, HostCapability) for item in capabilities):
            raise TypeError("Host snapshot capabilities must be validated HostCapability values")
        ordered = tuple(sorted(capabilities, key=lambda item: (item.canonical_id.casefold(), item.canonical_id)))
        if len({item.canonical_id for item in ordered}) != len(ordered):
            raise ValueError("Host snapshot cannot contain duplicate capability identity")
        object.__setattr__(self, "capabilities", ordered)

    @classmethod
    def from_trusted_envelope(cls, payload: Mapping[str, object]) -> "HostCapabilitySnapshot":
        """Normalize a controller-owned envelope; reject ordinary user mappings."""

        if not isinstance(payload, Mapping):
            raise TypeError("Host snapshot envelope must be a mapping")
        allowed = {"snapshot_id", "source", "session_scope", "capabilities", "trust_marker", "provenance"}
        if set(payload) - allowed:
            raise ValueError("Host snapshot envelope has unsupported fields")
        if payload.get("trust_marker") != HOST_SNAPSHOT_TRUST_MARKER:
            raise ValueError("Host snapshot envelope is not marked trusted_host_snapshot")
        raw_capabilities = payload.get("capabilities", ())
        if isinstance(raw_capabilities, (str, bytes)) or not isinstance(raw_capabilities, Sequence):
            raise ValueError("Host snapshot capabilities must be a sequence")
        capabilities = tuple(
            item if isinstance(item, HostCapability) else HostCapability.from_mapping(item)
            for item in raw_capabilities
        )
        return cls(
            snapshot_id=payload.get("snapshot_id"),  # type: ignore[arg-type]
            source=payload.get("source"),  # type: ignore[arg-type]
            session_scope=payload.get("session_scope"),  # type: ignore[arg-type]
            capabilities=capabilities,
            trust_marker=payload.get("trust_marker"),  # type: ignore[arg-type]
            provenance=payload.get("provenance", (HOST_SNAPSHOT_PROVENANCE,)),  # type: ignore[arg-type]
        )

    @classmethod
    def from_controller_registry(
        cls,
        registry: Sequence[Mapping[str, object]],
        *,
        snapshot_id: str,
        session_scope: str,
        source: str = "controller-session-registry",
        provenance: Sequence[str] = (HOST_SNAPSHOT_PROVENANCE,),
    ) -> "HostCapabilitySnapshot":
        """將 controller 已取得的 public registry 投影成 trusted snapshot。

        Caller 必須先完成 controller-side trust boundary；每筆 hierarchy、parent
        identity 與 namespace/action 都要由 registry 明確提供。此函式不讀 hidden
        prompt、不解析 chain-of-thought，也不以名稱關鍵字猜測 App/MCP parent。
        缺少 hierarchy 只會保留為 `unknown` structural state；Provider adapter
        會將它轉成 `host_tool`，不會猜成 builtin/App/MCP。
        """

        if isinstance(registry, (str, bytes)) or not isinstance(registry, Sequence):
            raise ValueError("controller registry must be a sequence")
        capabilities: list[HostCapability] = []
        for item in registry:
            if not isinstance(item, Mapping):
                raise ValueError("controller registry entries must be objects")
            if "namespace" not in item or "action_name" not in item:
                raise ValueError("controller registry entries require explicit namespace and action_name")
            canonical_id = f"{item.get('namespace')}.{item.get('action_name')}"
            item_provenance = item.get("provenance", ())
            if isinstance(item_provenance, (str, bytes)) or not isinstance(item_provenance, Sequence):
                raise ValueError("controller registry provenance must be a sequence")
            capabilities.append(
                HostCapability.from_mapping(
                    {
                        "namespace": item.get("namespace"),
                        "action_name": item.get("action_name"),
                        "display_name": item.get("display_name", item.get("name", canonical_id)),
                        "description": item.get("description"),
                        "exposure_state": item.get("exposure_state", "EXPOSED"),
                        "hierarchy": item.get("hierarchy", "unknown"),
                        "parent_kind": item.get("parent_kind"),
                        "parent_identity": item.get("parent_identity"),
                        "provenance": tuple(dict.fromkeys(tuple(provenance) + tuple(item_provenance))),
                        "is_read_only": item.get("is_read_only"),
                        "has_side_effect": item.get("has_side_effect"),
                        "callable_evidence": item.get("callable_evidence"),
                    }
                )
            )
        return cls(
            snapshot_id=snapshot_id,
            source=source,
            session_scope=session_scope,
            capabilities=tuple(capabilities),
            trust_marker=HOST_SNAPSHOT_TRUST_MARKER,
            provenance=tuple(provenance),
        )

    @property
    def fingerprint(self) -> str:
        """計算 normalized snapshot fingerprint，供 context/receipt audit 使用。"""

        return _sha256(self.to_mapping(include_fingerprint=False))

    def to_mapping(self, *, include_fingerprint: bool = True) -> dict[str, object]:
        """輸出可稽核 snapshot public projection。"""

        result: dict[str, object] = {
            "contract_version": HOST_SNAPSHOT_CONTRACT_VERSION,
            "snapshot_id": self.snapshot_id,
            "source": self.source,
            "session_scope": self.session_scope,
            "trust_marker": self.trust_marker,
            "provenance": list(self.provenance),
            "capabilities": [item.to_mapping() for item in self.capabilities],
        }
        if include_fingerprint:
            result["fingerprint"] = self.fingerprint
        return result

    @property
    def host_native_count(self) -> int:
        """回傳 Host 明確標示 top-level native 的數量。"""

        return sum(item.hierarchy == "host_native" for item in self.capabilities)

    @property
    def app_child_count(self) -> int:
        """回傳 Host 明確標示 App child 的數量。"""

        return sum(item.hierarchy == "app_child" for item in self.capabilities)

    @property
    def mcp_child_count(self) -> int:
        """回傳 Host 明確標示 MCP child 的數量。"""

        return sum(item.hierarchy == "mcp_child" for item in self.capabilities)

    @property
    def unclassified_count(self) -> int:
        """回傳未知 hierarchy 的數量；不包含已知 Plugin child。"""

        return sum(item.hierarchy == "unknown" for item in self.capabilities)

    @property
    def control_plane_count(self) -> int:
        """回傳 controller/control-plane capability 數量。"""

        return sum(item.hierarchy == "control_plane" for item in self.capabilities)

    @property
    def plugin_child_count(self) -> int:
        """回傳 Plugin child 診斷 capability 數量。"""

        return sum(item.hierarchy == "plugin_child" for item in self.capabilities)

    @property
    def formalizable_count(self) -> int:
        """回傳可建立精確 Provider 或 host_tool fallback 的 public capability 數量。"""

        return sum(
            item.exposure_state == "EXPOSED"
            and item.hierarchy in {"host_native", "app_child", "mcp_child", "unknown"}
            for item in self.capabilities
        )

    @property
    def intentionally_excluded_count(self) -> int:
        """回傳依 structural boundary 不進 formal Provider 的 capability 數量。"""

        return sum(item.hierarchy in {"control_plane", "plugin_child"} for item in self.capabilities)

    @property
    def missing_count(self) -> int:
        """回傳 projection 遺失數量；validated registry 會逐筆轉換，因此固定為零。"""

        return 0


def prepare_host_capability_snapshot(
    controller_registry: Sequence[Mapping[str, object]],
    *,
    snapshot_id: str,
    session_scope: str,
    source: str = "controller-session-registry",
    provenance: Sequence[str] = (HOST_SNAPSHOT_PROVENANCE,),
) -> HostCapabilitySnapshot:
    """在 route preparation boundary 將 controller registry 建立成 session snapshot。

    參數：`controller_registry` 必須是 controller 已取得的 current-session public
    definitions；每筆需要 explicit namespace、action_name，並以 controller structural
    evidence提供 hierarchy/parent。回傳值是可傳入 `SelectionRouteInput` 的 typed
    `HostCapabilitySnapshot`。本函式不接受 task、keywords 或 execution needs，因此
    snapshot membership 不會被任務內容裁剪；unknown hierarchy 會保留為
    `host_tool` fallback 的 structural state。
    """

    normalized_provenance = tuple(
        dict.fromkeys((HOST_SNAPSHOT_PROVENANCE, *tuple(provenance)))
    )
    return HostCapabilitySnapshot.from_controller_registry(
        controller_registry,
        snapshot_id=snapshot_id,
        session_scope=session_scope,
        source=source,
        provenance=normalized_provenance,
    )


def _identifier(value: object, field: str) -> str:
    """限制 canonical public identifier。"""

    if not isinstance(value, str) or _IDENTIFIER.fullmatch(value.strip()) is None:
        raise ValueError(f"{field} must be a canonical identifier")
    return value.strip()


def _text(value: object, field: str, maximum: int) -> str:
    """限制 bounded public text，拒絕 secrets、absolute paths 與 NUL。"""

    if not isinstance(value, str):
        raise ValueError(f"{field} must be text")
    result = value.strip()
    if not result or len(result) > maximum or "\x00" in result or _SENSITIVE_ASSIGNMENT.search(result):
        raise ValueError(f"{field} must be bounded public text")
    if re.match(r"^(?:[A-Za-z]:[\\/]|/|\\\\)", result):
        raise ValueError(f"{field} must not be an absolute path")
    return result


def _nullable_text(value: object, field: str, maximum: int) -> str | None:
    """保留 Host 缺少 description 的事實，不自行補 semantic 內容。"""

    if value is None:
        return None
    return _text(value, field, maximum)


def _provenance(value: Sequence[str]) -> tuple[str, ...]:
    """驗證 abstract provenance label，不保存 path 或 secret。"""

    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise ValueError("Host snapshot provenance must be a sequence")
    result = tuple(_text(item, "Host snapshot provenance", 256) for item in value)
    if len(set(result)) != len(result):
        raise ValueError("Host snapshot provenance cannot contain duplicates")
    return tuple(sorted(result, key=lambda item: (item.casefold(), item)))


def _sha256(value: object) -> str:
    """計算 normalized public JSON fingerprint。"""

    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
