"""Phase 3 lazy Supporting Provider context 與 readiness evidence contract。"""

# 修改紀錄（2026-08-26，Steve Peng）
# 原始內容：Phase 3 只準備 hard-eligible Provider digest/detail references，尚無 final decision protocol。
# 修改原因：Phase 4 需要 bounded request_detail/final_selection、status gate 與 exact Provider validation。
# 修改後功能：新增 immutable Supporting decision contracts；只驗證 schema、canonical identity、readiness 與原始 need 來源，不做 semantic selection 或 endpoint invocation。
# 修改紀錄（2026-09-02，Steve Peng）
# 原始內容：metadata insufficient 會在 semantic consideration 前排除 Provider。
# 修改原因：beta.3 的存在優先 contract 要求所有已解析 identity 都至少被 LLM 看見。
# 修改後功能：metadata 改為 SUFFICIENT/SPARSE/OPAQUE 品質診斷；品質與 readiness 都不再是 consideration gate。
# 修改紀錄（2026-09-02，Steve Peng）
# 原始內容：外部 Plugin identity 直接放入 canonical host_grouping。
# 修改原因：真實 Plugin identity 可含 `@` 等 canonical key 不允許的字元。
# 修改後功能：保存 raw_external_identity，並以 stable hash-backed canonical grouping key 供 exact merge。
# 修改紀錄（2026-09-01，Steve Peng）
# 原始內容：只有 hard-eligible readiness certificate 才能建立 Provider digest，unknown readiness 會被排除。
# 修改原因：Optimistic Supporting Provider Selection Upgrade 要分離 instance presence、capability metadata 與 runtime readiness。
# 修改後功能：PRESENT_UNVERIFIED Provider 可進 semantic candidate；explicit negative 與 metadata insufficient 仍在 semantic selection 前排除，並新增最小 execution outcome record。
# 修改紀錄（2026-09-01，Steve Peng）
# 原始內容：Supporting context 沒有 discovery evidence 分層與完整 Provider digest sweep metrics。
# 修改原因：High-recall inventory discovery 必須把 discovery、presence、readiness 分開，且所有 selectable digest 至少進一次 semantic consideration。
# 修改後功能：新增 discovery evidence state、generic Host/Plugin envelope 接口與 deterministic provider sweep evidence；不執行 Provider。
# 修改紀錄（2026-09-01，Steve Peng）
# 原始內容：Supporting context 只能接 raw Host registry，沒有 controller-owned Host snapshot identity 與 hierarchy metrics。
# 修改原因：Host snapshot bridge 必須保留 snapshot fingerprint，並將 formal Provider evidence 合併後送入同一條 sweep。
# 修改後功能：接收 validated HostCapabilitySnapshot、合併 exact Provider evidence、輸出 Host snapshot metrics；不改 Skill path 或 execution safety。

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import PurePosixPath, PureWindowsPath
import re

from .host_snapshot import HostCapabilitySnapshot
from .inventory_sweep import build_inventory_sweep, provider_digest
from .existence import ExistenceEvidenceState, MetadataQuality, classify_metadata_quality


SUPPORTING_CONTEXT_CONTRACT_VERSION = "v0.2-supporting-context-v2"
READINESS_EVIDENCE_CONTRACT_VERSION = "v0.2-phase0-runtime-readiness-v1"
_FINGERPRINT = re.compile(r"^[0-9a-f]{64}$")
_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]*$")
_PUBLIC_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:@-]*$")
FORMAL_SUPPORTING_PROVIDER_KINDS = frozenset({"app", "mcp", "builtin_tool", "host_tool"})
PROVIDER_PRESENCE_STATES = frozenset({"PRESENT", "ABSENT", "EXPLICITLY_BLOCKED"})
PROVIDER_READINESS_STATES = frozenset({"VERIFIED_READY", "PRESENT_UNVERIFIED", "KNOWN_UNAVAILABLE"})
PROVIDER_METADATA_STATES = frozenset({"SUFFICIENT", "SPARSE", "OPAQUE", "INSUFFICIENT_CAPABILITY_METADATA"})
DISCOVERY_EVIDENCE_STATES = frozenset(
    {"DISCOVERED_TRUSTED", "DISCOVERED_DECLARED", "DECLARED_ONLY", "NOT_DISCOVERED"}
)
EXECUTION_OUTCOMES = frozenset(
    {
        "SUCCESS",
        "AUTH_REQUIRED",
        "UNAVAILABLE",
        "CONNECTION_FAILED",
        "POLICY_BLOCKED",
        "CALL_FAILED",
        "NOT_ATTEMPTED",
    }
)
# plugin remains parseable for historical records, but is never a new formal
# selected Provider.  Keeping this compatibility set here avoids rewriting
# old receipts while the production validator uses the formal set below.
_PROVIDER_KINDS = FORMAL_SUPPORTING_PROVIDER_KINDS | {"plugin"}
# Phase 0 evidence certification scope；這是 exact readiness instance scope，非 task/category mapping。
_CERTIFIED_PROVIDER_SCOPE = frozenset(
    {("mcp", "node_repl"), ("builtin_tool", "functions.exec_command")}
)
_RUN_STATES = frozenset({"not_run", "ran"})
_SENSITIVE = re.compile(r"(?:api[_-]?key|password|secret|token|credential)", re.IGNORECASE)


@dataclass(frozen=True)
class ExecutionNeed:
    """Validated public execution need；不在 Python 判斷 semantic applicability。"""

    need: str
    reason: str

    def __post_init__(self) -> None:
        """限制 execution need 為 bounded public text，拒絕 prompt/path/secret。"""

        object.__setattr__(self, "need", _safe_text(self.need, "need", 256))
        object.__setattr__(self, "reason", _safe_text(self.reason, "reason", 512))

    def to_mapping(self) -> dict[str, str]:
        """輸出 privacy-bounded execution need。"""

        return {"need": self.need, "reason": self.reason}


@dataclass(frozen=True)
class ExecutionAttempt:
    """獨立的 bounded Provider execution outcome；不會改寫 Selection Receipt。"""

    selection_receipt_fingerprint: str
    execution_need: str
    provider_kind: str
    provider_id: str
    readiness_state: str
    outcome: str
    error_category: str | None = None
    actual_server: str | None = None
    actual_tool: str | None = None
    app_context: str | None = None
    plugin_id: str | None = None

    def __post_init__(self) -> None:
        """驗證 execution audit 的 bounded identity、state 與 public metadata。"""

        if _FINGERPRINT.fullmatch(self.selection_receipt_fingerprint) is None:
            raise ValueError("selection_receipt_fingerprint must be a SHA-256 fingerprint")
        object.__setattr__(self, "execution_need", _safe_text(self.execution_need, "execution need", 256))
        if self.provider_kind not in FORMAL_SUPPORTING_PROVIDER_KINDS:
            raise ValueError("execution attempts require a formal provider kind")
        object.__setattr__(self, "provider_id", _identifier(self.provider_id, "execution provider id"))
        if self.readiness_state not in PROVIDER_READINESS_STATES:
            raise ValueError("execution attempt has an unsupported readiness state")
        if self.outcome not in EXECUTION_OUTCOMES:
            raise ValueError("execution attempt has an unsupported outcome")
        for field_name in ("error_category", "actual_server", "app_context"):
            value = getattr(self, field_name)
            if value is not None:
                object.__setattr__(self, field_name, _safe_text(value, field_name, 512))
        if self.actual_tool is not None:
            object.__setattr__(self, "actual_tool", _identifier(self.actual_tool, "actual tool"))
        if self.plugin_id is not None:
            object.__setattr__(self, "plugin_id", _identifier(self.plugin_id, "plugin provenance id"))

    def to_mapping(self) -> dict[str, object]:
        """輸出不含 secret、raw arguments 或 private path 的 execution audit。"""

        result: dict[str, object] = {
            "selection_receipt_fingerprint": self.selection_receipt_fingerprint,
            "execution_need": self.execution_need,
            "provider_kind": self.provider_kind,
            "provider_id": self.provider_id,
            "readiness_state": self.readiness_state,
            "outcome": self.outcome,
            "error_category": self.error_category,
        }
        for field_name in ("actual_server", "actual_tool", "app_context", "plugin_id"):
            value = getattr(self, field_name)
            if value is not None:
                result[field_name] = value
        return result


SUPPORTING_SELECTION_STATUSES = frozenset(
    {
        "not_required",
        "selected",
        "no_matching_supporting_capability",
        "no_present_supporting_provider",
        "insufficient_capability_metadata",
        "explicit_negative_exclusion",
    }
)


@dataclass(frozen=True)
class SupportingCapabilitySelection:
    """Codex final selection 的單一 Provider-level public item。"""

    kind: str
    canonical_provider_id: str
    purpose: str

    def __post_init__(self) -> None:
        """只驗證 schema 與 bounded public text，不判斷語意適用性。"""

        if self.kind not in _PROVIDER_KINDS:
            raise ValueError("unsupported selected supporting capability kind")
        object.__setattr__(self, "canonical_provider_id", _identifier(self.canonical_provider_id, "canonical provider id"))
        object.__setattr__(self, "purpose", _safe_text(self.purpose, "supporting purpose", 512))

    def to_mapping(self) -> dict[str, str]:
        """輸出不含 schema、prompt 或 credentials 的 public selection。"""

        return {
            "kind": self.kind,
            "canonical_provider_id": self.canonical_provider_id,
            "purpose": self.purpose,
        }


@dataclass(frozen=True)
class UnmetExecutionNeed:
    """Codex 明示未滿足的原始 Execution Need。"""

    need: str
    reason: str

    def __post_init__(self) -> None:
        """限制 unmet item 為 bounded structured text。"""

        object.__setattr__(self, "need", _safe_text(self.need, "unmet need", 256))
        object.__setattr__(self, "reason", _safe_text(self.reason, "unmet reason", 512))

    def to_mapping(self) -> dict[str, str]:
        """輸出 public unmet need。"""

        return {"need": self.need, "reason": self.reason}


@dataclass(frozen=True)
class SupportingFinalSelection:
    """Supporting final_selection structured result；不含 semantic score。"""

    selected_supporting_capabilities: tuple[SupportingCapabilitySelection, ...]
    unmet_execution_needs: tuple[UnmetExecutionNeed, ...]

    def __post_init__(self) -> None:
        """固定 immutable tuples 並拒絕 Provider/need duplicates。"""

        selected = tuple(self.selected_supporting_capabilities)
        unmet = tuple(self.unmet_execution_needs)
        if not all(isinstance(item, SupportingCapabilitySelection) for item in selected):
            raise TypeError("selected_supporting_capabilities must contain validated items")
        if not all(isinstance(item, UnmetExecutionNeed) for item in unmet):
            raise TypeError("unmet_execution_needs must contain validated items")
        if len({item.canonical_provider_id for item in selected}) != len(selected):
            raise ValueError("selected supporting provider IDs must be unique")
        if len({item.need for item in unmet}) != len(unmet):
            raise ValueError("unmet execution needs must be unique")
        object.__setattr__(self, "selected_supporting_capabilities", selected)
        object.__setattr__(self, "unmet_execution_needs", unmet)

    def to_mapping(self) -> dict[str, object]:
        """輸出 final selection 的 bounded public projection。"""

        return {
            "selected_supporting_capabilities": [item.to_mapping() for item in self.selected_supporting_capabilities],
            "unmet_execution_needs": [item.to_mapping() for item in self.unmet_execution_needs],
        }


@dataclass(frozen=True)
class SupportingCoverageAddition:
    """單一 bounded Supporting Coverage Check 的新增 Provider 證據。"""

    provider_id: str
    execution_need: str
    distinct_value: str

    def __post_init__(self) -> None:
        """驗證新增 Provider、原始 Execution Need 與可公開的 distinct value。"""

        object.__setattr__(self, "provider_id", _identifier(self.provider_id, "coverage provider id"))
        object.__setattr__(self, "execution_need", _safe_text(self.execution_need, "coverage execution need", 256))
        object.__setattr__(self, "distinct_value", _safe_text(self.distinct_value, "coverage distinct value", 512))

    def to_mapping(self) -> dict[str, str]:
        """輸出不含 hidden reasoning 的 bounded Supporting coverage evidence。"""

        return {
            "provider_id": self.provider_id,
            "execution_need": self.execution_need,
            "distinct_value": self.distinct_value,
        }


@dataclass(frozen=True)
class SupportingDetailRequest:
    """一輪 bounded request_detail；只引用 exact selectable provider/tool IDs。"""

    requests: tuple[tuple[str, tuple[str, ...]], ...]

    def __post_init__(self) -> None:
        """固定 request 順序並限制 detail expansion 規模。"""

        normalized = []
        total_tools = 0
        for provider_id, tool_ids in self.requests:
            provider = _identifier(provider_id, "detail provider id")
            tools = _identifier_tuple(tool_ids, "detail tool ids")
            if not tools:
                raise ValueError("detail request must name at least one tool")
            total_tools += len(tools)
            normalized.append((provider, tools))
        if not normalized or len(normalized) > 2 or total_tools > 4:
            raise ValueError("detail request exceeds bounded expansion limit")
        providers = [item[0] for item in normalized]
        if len(set(providers)) != len(providers):
            raise ValueError("detail request cannot duplicate providers")
        object.__setattr__(
            self,
            "requests",
            tuple(sorted(normalized, key=lambda item: (item[0].casefold(), item[0]))),
        )

    def to_mapping(self) -> dict[str, object]:
        """輸出只含 exact canonical IDs 的 request。"""

        return {
            "requests": [
                {"provider_id": provider_id, "tool_ids": list(tool_ids)}
                for provider_id, tool_ids in self.requests
            ]
        }


@dataclass(frozen=True)
class SupportingDecisionPayload:
    """互斥的 request_detail/final_selection protocol payload。"""

    request_detail: SupportingDetailRequest | None = None
    final_selection: SupportingFinalSelection | None = None

    def __post_init__(self) -> None:
        """要求恰好一種 protocol phase，避免 partial/combined status。"""

        if (self.request_detail is None) == (self.final_selection is None):
            raise ValueError("supporting payload must contain exactly one protocol phase")

    def to_mapping(self) -> dict[str, object]:
        """輸出互斥 public payload。"""

        return {
            "request_detail": None if self.request_detail is None else self.request_detail.to_mapping(),
            "final_selection": None if self.final_selection is None else self.final_selection.to_mapping(),
        }


@dataclass(frozen=True)
class SupportingToolDeclaration:
    """Host callable tool 的 deterministic public declaration。"""

    id: str
    description: str
    schema: str
    required_inputs: tuple[str, ...] = ()
    output_description: str | None = None
    side_effect: str | None = None
    provenance: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        """固定 exact tool identity、schema 與 bounded public metadata。"""

        object.__setattr__(self, "id", _identifier(self.id, "tool id"))
        object.__setattr__(self, "description", _safe_text(self.description, "tool description", 1024))
        object.__setattr__(self, "schema", _canonical_schema(self.schema))
        object.__setattr__(
            self,
            "required_inputs",
            _identifier_tuple(self.required_inputs, "required_inputs"),
        )
        if self.output_description is not None:
            object.__setattr__(
                self,
                "output_description",
                _safe_text(self.output_description, "output_description", 512),
            )
        if self.side_effect is not None:
            object.__setattr__(self, "side_effect", _safe_text(self.side_effect, "side_effect", 512))
        object.__setattr__(self, "provenance", _provenance(self.provenance))

    @classmethod
    def from_mapping(cls, payload: Mapping[str, object]) -> "SupportingToolDeclaration":
        """將 Host tool declaration mapping 驗證成 immutable public record。"""

        if set(payload) - {
            "id",
            "description",
            "schema",
            "required_inputs",
            "output_description",
            "side_effect",
            "provenance",
        }:
            raise ValueError("supporting tool declaration has unsupported fields")
        return cls(
            id=payload.get("id"),  # type: ignore[arg-type]
            description=payload.get("description"),  # type: ignore[arg-type]
            schema=payload.get("schema", {}),  # type: ignore[arg-type]
            required_inputs=payload.get("required_inputs", ()),  # type: ignore[arg-type]
            output_description=payload.get("output_description"),  # type: ignore[arg-type]
            side_effect=payload.get("side_effect"),  # type: ignore[arg-type]
            provenance=payload.get("provenance", ()),  # type: ignore[arg-type]
        )

    @property
    def schema_fingerprint(self) -> str:
        """取得 canonical schema digest。"""

        return _sha256(json.loads(self.schema))

    def to_mapping(self) -> dict[str, object]:
        """輸出 deterministic tool declaration，不含私有內容。"""

        return {
            "id": self.id,
            "description": self.description,
            "schema": json.loads(self.schema),
            "required_inputs": list(self.required_inputs),
            "output_description": self.output_description,
            "side_effect": self.side_effect,
            "provenance": list(self.provenance),
        }


@dataclass(frozen=True)
class SupportingToolSummary:
    """Official App/MCP public tool summary without an invented JSON schema."""

    id: str
    title: str | None
    description: str
    is_enabled: bool
    disabled_reason: str | None
    is_read_only: bool | None
    provenance: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        """Validate only fields exposed by the Host protocol."""

        object.__setattr__(self, "id", _identifier(self.id, "tool id"))
        if self.title is not None:
            object.__setattr__(self, "title", _safe_text(self.title, "tool title", 512))
        object.__setattr__(self, "description", _safe_text(self.description, "tool description", 1024))
        if not isinstance(self.is_enabled, bool):
            raise ValueError("tool is_enabled must be boolean")
        if self.disabled_reason is not None:
            object.__setattr__(self, "disabled_reason", _safe_text(self.disabled_reason, "disabled reason", 512))
        if self.is_read_only is not None and not isinstance(self.is_read_only, bool):
            raise ValueError("tool is_read_only must be boolean or null")
        object.__setattr__(self, "provenance", _provenance(self.provenance))

    @classmethod
    def from_mapping(cls, payload: Mapping[str, object]) -> "SupportingToolSummary":
        """Parse the normalized summary projection used by route inputs."""

        allowed = {"id", "title", "description", "is_enabled", "disabled_reason", "is_read_only", "provenance"}
        if set(payload) - allowed:
            raise ValueError("supporting tool summary has unsupported fields")
        return cls(
            id=payload.get("id"),  # type: ignore[arg-type]
            title=payload.get("title"),  # type: ignore[arg-type]
            description=payload.get("description"),  # type: ignore[arg-type]
            is_enabled=payload.get("is_enabled"),  # type: ignore[arg-type]
            disabled_reason=payload.get("disabled_reason"),  # type: ignore[arg-type]
            is_read_only=payload.get("is_read_only"),  # type: ignore[arg-type]
            provenance=payload.get("provenance", ()),  # type: ignore[arg-type]
        )

    def to_mapping(self) -> dict[str, object]:
        """Return the bounded official summary; no schema is fabricated."""

        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "is_enabled": self.is_enabled,
            "disabled_reason": self.disabled_reason,
            "is_read_only": self.is_read_only,
            "provenance": list(self.provenance),
        }


SupportingTool = SupportingToolDeclaration | SupportingToolSummary


@dataclass(frozen=True)
class SupportingProviderDeclaration:
    """Host runtime 暴露的單一 Provider declaration；不執行任何 endpoint。"""

    provider_id: str
    kind: str
    host_identity: str
    host_grouping: tuple[str, ...]
    description: str | None
    callable_tools: tuple[SupportingTool, ...]
    callable_exposure: bool
    provenance: tuple[str, ...]
    display_name: str | None = None
    presence_state: str = "PRESENT"
    explicit_negative_reason: str | None = None
    discovery_evidence_state: str = "DISCOVERED_TRUSTED"
    existence_evidence_state: ExistenceEvidenceState = ExistenceEvidenceState.RUNTIME_ENTITY_PRESENT
    raw_external_identity: str | None = None
    canonical_grouping_key: str | None = None
    metadata_quality: MetadataQuality | None = None
    hierarchy_state: str | None = None

    def __post_init__(self) -> None:
        """驗證 Host identity/grouping 與 exact callable surface。"""

        object.__setattr__(self, "provider_id", _identifier(self.provider_id, "provider id"))
        if self.kind not in _PROVIDER_KINDS:
            raise ValueError("unsupported supporting provider kind")
        if self.hierarchy_state is not None:
            if self.hierarchy_state not in {"KNOWN", "UNKNOWN"}:
                raise ValueError("unsupported provider hierarchy state")
            if self.kind == "host_tool" and self.hierarchy_state != "UNKNOWN":
                raise ValueError("host_tool requires UNKNOWN hierarchy state")
        if self.presence_state not in PROVIDER_PRESENCE_STATES:
            raise ValueError("unsupported provider presence state")
        if self.discovery_evidence_state not in DISCOVERY_EVIDENCE_STATES:
            raise ValueError("unsupported discovery evidence state")
        if not isinstance(self.existence_evidence_state, ExistenceEvidenceState):
            try:
                object.__setattr__(self, "existence_evidence_state", ExistenceEvidenceState(self.existence_evidence_state))
            except ValueError as error:
                raise ValueError("unsupported provider existence evidence state") from error
        object.__setattr__(self, "host_identity", _identifier(self.host_identity, "host identity"))
        object.__setattr__(self, "host_grouping", _identifier_tuple(self.host_grouping, "host_grouping"))
        object.__setattr__(self, "description", _nullable_text(self.description, "provider description", 1024))
        object.__setattr__(self, "callable_tools", _tool_tuple(self.callable_tools))
        if not isinstance(self.callable_exposure, bool):
            raise ValueError("callable_exposure must be boolean")
        object.__setattr__(self, "provenance", _provenance(self.provenance))
        if self.display_name is not None:
            object.__setattr__(self, "display_name", _safe_public_label(self.display_name, "provider display name", 512))
        if self.explicit_negative_reason is not None:
            object.__setattr__(
                self,
                "explicit_negative_reason",
                _safe_text(self.explicit_negative_reason, "provider negative reason", 512),
            )
        if self.raw_external_identity is not None:
            object.__setattr__(
                self,
                "raw_external_identity",
                _safe_public_label(self.raw_external_identity, "raw external identity", 512),
            )
        if self.canonical_grouping_key is not None:
            object.__setattr__(
                self,
                "canonical_grouping_key",
                _identifier(self.canonical_grouping_key, "canonical grouping key"),
            )
        # quality 是由目前 public fields 計算的 diagnostic；不接受 stale caller
        # 值，避免 dataclasses.replace() 修改 description 後仍保留舊品質。
        quality = classify_metadata_quality(
            name=None if self.display_name == self.provider_id else self.display_name,
            description=self.description,
            summaries=tuple(
                value
                for tool in self.callable_tools
                for value in (getattr(tool, "title", None), getattr(tool, "description", None))
            ),
        )
        object.__setattr__(self, "metadata_quality", quality)

    @classmethod
    def from_mapping(cls, payload: Mapping[str, object]) -> "SupportingProviderDeclaration":
        """將 Host runtime mapping 驗證成 immutable provider declaration。"""

        allowed = {
            "provider_id",
            "kind",
            "host_identity",
            "host_grouping",
            "description",
            "callable_tools",
            "callable_exposure",
            "provenance",
            "display_name",
            "presence_state",
            "explicit_negative_reason",
            "discovery_evidence_state",
            "existence_evidence_state",
            "raw_external_identity",
            "canonical_grouping_key",
            "metadata_quality",
            "hierarchy_state",
        }
        if set(payload) - allowed:
            raise ValueError("supporting provider declaration has unsupported fields")
        tools = payload.get("callable_tools", ())
        if not isinstance(tools, Sequence) or isinstance(tools, (str, bytes)):
            raise ValueError("callable_tools must be a sequence")
        return cls(
            provider_id=payload.get("provider_id"),  # type: ignore[arg-type]
            kind=payload.get("kind"),  # type: ignore[arg-type]
            host_identity=payload.get("host_identity"),  # type: ignore[arg-type]
            host_grouping=payload.get("host_grouping", ()),  # type: ignore[arg-type]
            description=payload.get("description"),  # type: ignore[arg-type]
            callable_tools=tuple(_tool_from_mapping(item) for item in tools),
            callable_exposure=payload.get("callable_exposure"),  # type: ignore[arg-type]
            provenance=payload.get("provenance", ()),  # type: ignore[arg-type]
            display_name=payload.get("display_name"),  # type: ignore[arg-type]
            presence_state=payload.get("presence_state", "PRESENT"),  # type: ignore[arg-type]
            explicit_negative_reason=payload.get("explicit_negative_reason"),  # type: ignore[arg-type]
            discovery_evidence_state=payload.get("discovery_evidence_state", "DISCOVERED_TRUSTED"),  # type: ignore[arg-type]
            existence_evidence_state=payload.get(
                "existence_evidence_state", ExistenceEvidenceState.RUNTIME_ENTITY_PRESENT
            ),  # type: ignore[arg-type]
            raw_external_identity=payload.get("raw_external_identity"),  # type: ignore[arg-type]
            canonical_grouping_key=payload.get("canonical_grouping_key"),  # type: ignore[arg-type]
            metadata_quality=payload.get("metadata_quality"),  # type: ignore[arg-type]
            hierarchy_state=payload.get("hierarchy_state"),  # type: ignore[arg-type]
        )

    @property
    def schema_fingerprint(self) -> str:
        """計算 callable tool schemas 的 deterministic fingerprint。"""

        return _sha256({"tools": [tool.to_mapping() for tool in self.callable_tools]})

    @property
    def fingerprint(self) -> str:
        """計算完整 Host declaration fingerprint。"""

        return _sha256(self.to_mapping())

    def to_mapping(self) -> dict[str, object]:
        """輸出 public provider declaration。"""

        result: dict[str, object] = {
            "provider_id": self.provider_id,
            "kind": self.kind,
            "host_identity": self.host_identity,
            "host_grouping": list(self.host_grouping),
            "description": self.description,
            "display_name": self.display_name,
            "callable_tools": [tool.to_mapping() for tool in self.callable_tools],
            "callable_exposure": self.callable_exposure,
            "provenance": list(self.provenance),
            "presence_state": self.presence_state,
            "explicit_negative_reason": self.explicit_negative_reason,
            "discovery_evidence_state": self.discovery_evidence_state,
            "existence_evidence_state": self.existence_evidence_state.value,
            "metadata_quality": self.metadata_quality.value,
        }
        if self.raw_external_identity is not None:
            result["raw_external_identity"] = self.raw_external_identity
        if self.canonical_grouping_key is not None:
            result["canonical_grouping_key"] = self.canonical_grouping_key
        if self.hierarchy_state is not None:
            result["hierarchy_state"] = self.hierarchy_state
        return result


@dataclass(frozen=True)
class ReadinessEvidenceCertificate:
    """Phase 0 certified evidence，限定 exact provider instance，不是 semantic allowlist。"""

    provider_id: str
    kind: str
    host_identity: str
    host_grouping: tuple[str, ...]
    callable_tool_ids: tuple[str, ...]
    expected_schema_fingerprint: str
    expected_declaration_fingerprint: str
    provenance: tuple[str, ...]
    verification_scope: str = READINESS_EVIDENCE_CONTRACT_VERSION
    normalization_rule: str | None = None
    presence: str = "present"
    availability: str = "available"
    authorization: str | None = None
    connection: str | None = None
    runtime_callable: bool = True

    def __post_init__(self) -> None:
        """驗證 Phase 0 readiness normalization，拒絕 unsupported kind 猜測。"""

        object.__setattr__(self, "provider_id", _identifier(self.provider_id, "provider id"))
        if self.kind not in {"mcp", "builtin_tool"}:
            raise ValueError("readiness certificates support only certified MCP or builtin_tool instances")
        object.__setattr__(self, "host_identity", _identifier(self.host_identity, "host identity"))
        object.__setattr__(self, "host_grouping", _identifier_tuple(self.host_grouping, "host_grouping"))
        object.__setattr__(self, "callable_tool_ids", _identifier_tuple(self.callable_tool_ids, "callable_tool_ids"))
        for field_name in ("expected_schema_fingerprint", "expected_declaration_fingerprint"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or _FINGERPRINT.fullmatch(value) is None:
                raise ValueError(f"{field_name} must be a SHA-256 fingerprint")
        object.__setattr__(self, "provenance", _provenance(self.provenance))
        if self.verification_scope != READINESS_EVIDENCE_CONTRACT_VERSION:
            raise ValueError("unsupported readiness evidence contract version")
        expected = (
            ("mcp-callable-surface-v1", "authorized", "connected", True)
            if self.kind == "mcp"
            else ("builtin-tool-callable-v1", "not_required", "not_required", True)
        )
        if self.normalization_rule is None:
            object.__setattr__(self, "normalization_rule", expected[0])
        if self.normalization_rule != expected[0]:
            raise ValueError("unsupported readiness normalization rule")
        if self.authorization is None:
            object.__setattr__(self, "authorization", expected[1])
        if self.connection is None:
            object.__setattr__(self, "connection", expected[2])
        if (
            self.presence,
            self.availability,
            self.authorization,
            self.connection,
            self.runtime_callable,
        ) != ("present", "available", expected[1], expected[2], expected[3]):
            raise ValueError("readiness normalization does not match certified provider contract")

    @property
    def fingerprint(self) -> str:
        """計算 readiness evidence 自身的 deterministic fingerprint。"""

        return _sha256(self.to_mapping())

    def to_mapping(self) -> dict[str, object]:
        """輸出可稽核 readiness evidence，不含 task 或 semantic metadata。"""

        return {
            "provider_id": self.provider_id,
            "kind": self.kind,
            "host_identity": self.host_identity,
            "host_grouping": list(self.host_grouping),
            "callable_tool_ids": list(self.callable_tool_ids),
            "expected_schema_fingerprint": self.expected_schema_fingerprint,
            "expected_declaration_fingerprint": self.expected_declaration_fingerprint,
            "provenance": list(self.provenance),
            "verification_scope": self.verification_scope,
            "normalization_rule": self.normalization_rule,
            "presence": self.presence,
            "availability": self.availability,
            "authorization": self.authorization,
            "connection": self.connection,
            "runtime_callable": self.runtime_callable,
        }

    @property
    def presence_state(self) -> str:
        """既有 exact certificate 已證明該 Provider instance 存在。"""

        return "PRESENT"

    @property
    def readiness_state(self) -> str:
        """既有 exact certificate 維持 compatibility verified-ready 語意。"""

        return "VERIFIED_READY"


@dataclass(frozen=True)
class AppReadinessEvidence:
    """Typed `app/list` + `app/installed` readiness facts for one App."""

    provider_id: str
    accessible: bool
    configured_enabled: bool
    runtime_enabled: bool
    callable: bool
    metadata_readable: bool
    runtime_name: str | None
    runtime_evidence_available: bool = True
    provenance: tuple[str, ...] = ()
    readiness_source: str = "app/installed"

    @property
    def kind(self) -> str:
        """Return the formal Provider kind represented by this evidence."""

        return "app"

    def __post_init__(self) -> None:
        """Reject guessed App authorization/connection facts and bad source data."""

        object.__setattr__(self, "provider_id", _identifier(self.provider_id, "provider id"))
        for field_name in ("accessible", "configured_enabled", "runtime_enabled", "callable", "metadata_readable"):
            if not isinstance(getattr(self, field_name), bool):
                raise ValueError(f"{field_name} must be boolean")
        if self.runtime_name is not None:
            object.__setattr__(self, "runtime_name", _safe_text(self.runtime_name, "runtime name", 256))
        if not isinstance(self.runtime_evidence_available, bool):
            raise ValueError("runtime_evidence_available must be boolean")
        if self.readiness_source != "app/installed":
            raise ValueError("App readiness must come from app/installed")
        object.__setattr__(self, "provenance", _provenance(self.provenance))

    @property
    def hard_eligible(self) -> bool:
        """Return the deterministic App state predicate excluding tool metadata."""

        return (
            self.runtime_evidence_available
            and self.accessible
            and self.configured_enabled
            and self.runtime_enabled
            and self.callable
            and self.metadata_readable
        )

    @property
    def presence_state(self) -> str:
        """官方 App response 已證明列出的 instance 存在。"""

        return "PRESENT"

    @property
    def readiness_state(self) -> str:
        """將官方 runtime facts 正規化為 readiness state，不偽造 auth/connection。"""

        # 修改紀錄（2026-09-01，Steve Peng）
        # 原始內容：runtime evidence 缺席時先回傳 PRESENT_UNVERIFIED，會掩蓋 app/list 已明示的 negative。
        # 修改原因：explicit inaccessible/disabled 必須在 readiness surface 缺席時仍排除，unknown 只適用於未知狀態。
        # 修改後功能：先保留官方已證明的 negative，再將真正未知的 runtime 狀態降級為 PRESENT_UNVERIFIED。
        if not self.accessible or not self.configured_enabled:
            return "KNOWN_UNAVAILABLE"
        if not self.runtime_evidence_available:
            return "PRESENT_UNVERIFIED"
        if not self.runtime_enabled or not self.callable:
            return "KNOWN_UNAVAILABLE"
        return "VERIFIED_READY"

    def _base_mapping(self) -> dict[str, object]:
        return {
            "kind": "app",
            "provider_id": self.provider_id,
            "readiness_source": self.readiness_source,
            "accessible": self.accessible,
            "configured_enabled": self.configured_enabled,
            "runtime_enabled": self.runtime_enabled,
            "callable": self.callable,
            "metadata_readable": self.metadata_readable,
            "runtime_name": self.runtime_name,
            "runtime_evidence_available": self.runtime_evidence_available,
            "presence_state": self.presence_state,
            "readiness_state": self.readiness_state,
            "provenance": list(self.provenance),
        }

    @property
    def fingerprint(self) -> str:
        """Fingerprint only the typed Host readiness facts."""

        return _sha256(self._base_mapping())

    def to_mapping(self) -> dict[str, object]:
        """Return public readiness evidence without invented auth/connection fields."""

        result = self._base_mapping()
        result["fingerprint"] = self.fingerprint
        return result


@dataclass(frozen=True)
class McpReadinessEvidence:
    """Typed `mcpServerStatus/list` readiness facts for one MCP server."""

    provider_id: str
    runtime_status: str | None
    auth_status: str
    callable_tool_ids: tuple[str, ...]
    plugin_id: str | None = None
    provenance: tuple[str, ...] = ()
    readiness_source: str = "mcpServerStatus/list"

    @property
    def kind(self) -> str:
        """Return the formal Provider kind represented by this evidence."""

        return "mcp"

    def __post_init__(self) -> None:
        """Validate current generated enum values and exact available tool IDs."""

        object.__setattr__(self, "provider_id", _identifier(self.provider_id, "provider id"))
        if self.runtime_status is not None and self.runtime_status not in {"notStarted", "starting", "connected", "authenticationRequired", "failed", "cancelled", "disabled"}:
            raise ValueError("unsupported MCP runtime status")
        if self.auth_status not in {"unknown", "unsupported", "notLoggedIn", "bearerToken", "oAuth"}:
            raise ValueError("unsupported MCP auth status")
        object.__setattr__(self, "callable_tool_ids", _identifier_tuple(self.callable_tool_ids, "callable_tool_ids"))
        if self.plugin_id is not None:
            object.__setattr__(self, "plugin_id", _identifier(self.plugin_id, "plugin provenance id"))
        if self.readiness_source != "mcpServerStatus/list":
            raise ValueError("MCP readiness must come from mcpServerStatus/list")
        object.__setattr__(self, "provenance", _provenance(self.provenance))

    @property
    def hard_eligible(self) -> bool:
        """Return the official runtime/auth gate before tool metadata matching."""

        return self.readiness_state == "VERIFIED_READY"

    @property
    def presence_state(self) -> str:
        """官方 MCP status response 已證明列出的 server instance 存在。"""

        return "PRESENT"

    @property
    def readiness_state(self) -> str:
        """將官方 MCP runtime/auth facts 正規化，不把 auth-required 猜成 auth denial。"""

        if self.runtime_status in {"failed", "cancelled", "disabled"}:
            return "KNOWN_UNAVAILABLE"
        if (
            self.runtime_status == "connected"
            and self.auth_status in {"unsupported", "bearerToken", "oAuth"}
            and bool(self.callable_tool_ids)
        ):
            return "VERIFIED_READY"
        return "PRESENT_UNVERIFIED"

    def _base_mapping(self) -> dict[str, object]:
        return {
            "kind": "mcp",
            "provider_id": self.provider_id,
            "readiness_source": self.readiness_source,
            "runtime_status": self.runtime_status,
            "auth_status": self.auth_status,
            "callable_tool_ids": list(self.callable_tool_ids),
            "plugin_id": self.plugin_id,
            "presence_state": self.presence_state,
            "readiness_state": self.readiness_state,
            "provenance": list(self.provenance),
        }

    @property
    def fingerprint(self) -> str:
        """Fingerprint runtime, auth, available tools and provenance."""

        return _sha256(self._base_mapping())

    def to_mapping(self) -> dict[str, object]:
        """Return public MCP readiness evidence; plugin identity is provenance only."""

        result = self._base_mapping()
        result["fingerprint"] = self.fingerprint
        return result


@dataclass(frozen=True)
class ProviderDetailReference:
    """一輪 bounded detail expansion 的 read-only reference，不執行 lookup。"""

    provider_id: str
    callable_tool_ids: tuple[str, ...]
    digest_fingerprint: str

    def __post_init__(self) -> None:
        """驗證 detail reference 只含 canonical IDs 與 digest fingerprint。"""

        object.__setattr__(self, "provider_id", _identifier(self.provider_id, "provider id"))
        object.__setattr__(self, "callable_tool_ids", _identifier_tuple(self.callable_tool_ids, "callable_tool_ids"))
        if _FINGERPRINT.fullmatch(self.digest_fingerprint) is None:
            raise ValueError("digest_fingerprint must be a SHA-256 fingerprint")

    def to_mapping(self) -> dict[str, object]:
        """輸出 bounded detail reference。"""

        return {
            "provider_id": self.provider_id,
            "callable_tool_ids": list(self.callable_tool_ids),
            "digest_fingerprint": self.digest_fingerprint,
        }


@dataclass(frozen=True)
class ProviderDigest:
    """Selectable Provider 的 deterministic digest；不含 semantic ranking。"""

    provider_id: str
    kind: str
    description: str | None
    callable_tools: tuple[SupportingTool, ...]
    provenance: tuple[str, ...]
    fingerprint: str
    display_name: str = "provider"
    presence_state: str = "PRESENT"
    readiness_state: str = "PRESENT_UNVERIFIED"
    discovery_evidence_state: str = "DISCOVERED_TRUSTED"
    existence_evidence_state: ExistenceEvidenceState = ExistenceEvidenceState.RUNTIME_ENTITY_PRESENT
    metadata_quality: MetadataQuality = MetadataQuality.OPAQUE
    raw_external_identity: str | None = None
    canonical_grouping_key: str | None = None
    hierarchy_state: str | None = None

    def __post_init__(self) -> None:
        """驗證 digest fingerprint 與 public provider metadata。"""

        object.__setattr__(self, "provider_id", _identifier(self.provider_id, "provider id"))
        if self.kind not in FORMAL_SUPPORTING_PROVIDER_KINDS:
            raise ValueError("provider digest requires a formal provider kind")
        if self.hierarchy_state is not None:
            if self.hierarchy_state not in {"KNOWN", "UNKNOWN"}:
                raise ValueError("unsupported provider hierarchy state")
            if self.kind == "host_tool" and self.hierarchy_state != "UNKNOWN":
                raise ValueError("host_tool requires UNKNOWN hierarchy state")
        object.__setattr__(self, "display_name", _safe_public_label(self.display_name, "provider display name", 512))
        object.__setattr__(self, "description", _nullable_text(self.description, "provider description", 1024))
        object.__setattr__(self, "callable_tools", _tool_tuple(self.callable_tools))
        object.__setattr__(self, "provenance", _provenance(self.provenance))
        if self.presence_state not in PROVIDER_PRESENCE_STATES:
            raise ValueError("provider digest has an unsupported presence state")
        if self.readiness_state not in PROVIDER_READINESS_STATES:
            raise ValueError("provider digest has an unsupported readiness state")
        if self.discovery_evidence_state not in DISCOVERY_EVIDENCE_STATES:
            raise ValueError("provider digest has an unsupported discovery evidence state")
        if not isinstance(self.existence_evidence_state, ExistenceEvidenceState):
            try:
                object.__setattr__(self, "existence_evidence_state", ExistenceEvidenceState(self.existence_evidence_state))
            except ValueError as error:
                raise ValueError("provider digest has an unsupported existence evidence state") from error
        if not isinstance(self.metadata_quality, MetadataQuality):
            try:
                object.__setattr__(self, "metadata_quality", MetadataQuality(self.metadata_quality))
            except ValueError as error:
                raise ValueError("provider digest has an unsupported metadata quality") from error
        if self.raw_external_identity is not None:
            object.__setattr__(
                self,
                "raw_external_identity",
                _safe_public_label(self.raw_external_identity, "raw external identity", 512),
            )
        if self.canonical_grouping_key is not None:
            object.__setattr__(
                self,
                "canonical_grouping_key",
                _identifier(self.canonical_grouping_key, "canonical grouping key"),
            )
        if self.presence_state != "PRESENT":
            raise ValueError("provider digest requires PRESENT state")
        if _FINGERPRINT.fullmatch(self.fingerprint) is None:
            raise ValueError("provider digest requires a SHA-256 fingerprint")

    def to_mapping(self) -> dict[str, object]:
        """輸出 digest public projection，不產生 semantic fields。"""

        result: dict[str, object] = {
            "provider_id": self.provider_id,
            "kind": self.kind,
            "display_name": self.display_name,
            "description": self.description,
            "callable_tools": [tool.to_mapping() for tool in self.callable_tools],
            "provenance": list(self.provenance),
            "fingerprint": self.fingerprint,
            "presence_state": self.presence_state,
            "readiness_state": self.readiness_state,
            "discovery_evidence_state": self.discovery_evidence_state,
            "existence_evidence_state": self.existence_evidence_state.value,
            "metadata_quality": self.metadata_quality.value,
        }
        if self.raw_external_identity is not None:
            result["raw_external_identity"] = self.raw_external_identity
        if self.canonical_grouping_key is not None:
            result["canonical_grouping_key"] = self.canonical_grouping_key
        if self.hierarchy_state is not None:
            result["hierarchy_state"] = self.hierarchy_state
        return result


@dataclass(frozen=True)
class SupportingMetrics:
    """Supporting preparation metrics；selected_count 在 preparation 階段保持 0。"""

    run_state: str
    discovered_count: int
    hard_eligible_count: int
    selected_count: int
    digest_total_size: int
    detail_expansion_used: bool
    present_count: int | None = None
    selectable_count: int | None = None
    verified_ready_count: int | None = None
    present_unverified_count: int | None = None
    metadata_insufficient_count: int | None = None
    explicit_negative_count: int | None = None
    metadata_sufficient_count: int | None = None
    metadata_sparse_count: int | None = None
    metadata_opaque_count: int | None = None
    identity_unresolved_count: int | None = None
    semantically_considered_count: int = 0
    plausible_count: int = 0
    never_considered_count: int = 0
    sweep_batch_count: int = 0
    sweep_fingerprint: str | None = None
    host_snapshot_capability_count: int = 0
    host_snapshot_builtin_count: int = 0
    host_snapshot_app_child_count: int = 0
    host_snapshot_mcp_child_count: int = 0
    host_snapshot_unclassified_count: int = 0
    host_snapshot_id: str | None = None
    host_snapshot_fingerprint: str | None = None

    def __post_init__(self) -> None:
        """驗證 lazy run state 與未選擇 contract。"""

        # Legacy construction without decisions leaves every candidate pending.
        if (
            self.run_state == "ran"
            and self.selectable_count
            and self.semantically_considered_count == 0
            and self.plausible_count == 0
            and self.never_considered_count == 0
            and self.sweep_fingerprint is None
        ):
            object.__setattr__(self, "never_considered_count", self.selectable_count)

        if self.run_state not in _RUN_STATES:
            raise ValueError("unsupported supporting metrics run_state")
        for field_name in (
            "discovered_count",
            "hard_eligible_count",
            "selected_count",
            "digest_total_size",
        ):
            value = getattr(self, field_name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{field_name} must be a non-negative integer")
        defaults = {
            "present_count": self.hard_eligible_count,
            "selectable_count": self.hard_eligible_count,
            "verified_ready_count": self.hard_eligible_count,
            "present_unverified_count": 0,
            "metadata_insufficient_count": 0,
            "explicit_negative_count": 0,
            "metadata_sufficient_count": 0,
            "metadata_sparse_count": 0,
            "metadata_opaque_count": 0,
            "identity_unresolved_count": 0,
        }
        for field_name, default in defaults.items():
            value = getattr(self, field_name)
            if value is None:
                object.__setattr__(self, field_name, 0 if self.run_state == "not_run" else default)
            elif isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{field_name} must be a non-negative integer or null")
        if self.hard_eligible_count != self.verified_ready_count:
            raise ValueError("hard_eligible_count must match verified_ready_count")
        if self.present_count > self.discovered_count:
            raise ValueError("present_count cannot exceed discovered_count")
        if self.selectable_count > self.present_count:
            raise ValueError("selectable_count cannot exceed present_count")
        if self.verified_ready_count > self.selectable_count:
            raise ValueError("verified_ready_count cannot exceed selectable_count")
        if self.present_unverified_count > self.selectable_count:
            raise ValueError("present_unverified_count cannot exceed selectable_count")
        if self.verified_ready_count + self.present_unverified_count != self.selectable_count:
            raise ValueError("readiness counts must account for every selectable provider")
        if self.selected_count != 0:
            raise ValueError("Phase 3 selected_count must remain zero")
        if self.semantically_considered_count > self.selectable_count:
            raise ValueError("semantically_considered_count cannot exceed selectable_count")
        if self.plausible_count > self.semantically_considered_count:
            raise ValueError("plausible_count cannot exceed semantically_considered_count")
        if self.never_considered_count > self.selectable_count:
            raise ValueError("never_considered_count cannot exceed selectable_count")
        if self.semantically_considered_count + self.never_considered_count != self.selectable_count:
            raise ValueError("Provider sweep counts must account for every selectable provider")
        if self.sweep_fingerprint is not None and _FINGERPRINT.fullmatch(self.sweep_fingerprint) is None:
            raise ValueError("sweep_fingerprint must be a SHA-256 digest or null")
        for field_name in (
            "host_snapshot_capability_count",
            "host_snapshot_builtin_count",
            "host_snapshot_app_child_count",
            "host_snapshot_mcp_child_count",
            "host_snapshot_unclassified_count",
        ):
            value = getattr(self, field_name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{field_name} must be a non-negative integer")
        if sum(
            (
                self.host_snapshot_builtin_count,
                self.host_snapshot_app_child_count,
                self.host_snapshot_mcp_child_count,
                self.host_snapshot_unclassified_count,
            )
        ) > self.host_snapshot_capability_count:
            raise ValueError("Host snapshot hierarchy counts exceed capability count")
        if self.host_snapshot_id is not None and not isinstance(self.host_snapshot_id, str):
            raise ValueError("host_snapshot_id must be text or null")
        if self.host_snapshot_fingerprint is not None and _FINGERPRINT.fullmatch(self.host_snapshot_fingerprint) is None:
            raise ValueError("host_snapshot_fingerprint must be a SHA-256 digest or null")
        if not isinstance(self.detail_expansion_used, bool):
            raise ValueError("detail_expansion_used must be boolean")
        if self.run_state == "not_run" and any(
            value != 0
            for value in (
                self.discovered_count,
                self.hard_eligible_count,
                self.selected_count,
                self.digest_total_size,
                self.present_count,
                self.selectable_count,
                self.verified_ready_count,
                self.present_unverified_count,
                self.metadata_insufficient_count,
                self.explicit_negative_count,
                self.metadata_sufficient_count,
                self.metadata_sparse_count,
                self.metadata_opaque_count,
                self.identity_unresolved_count,
                self.semantically_considered_count,
                self.plausible_count,
                self.never_considered_count,
                self.sweep_batch_count,
                self.host_snapshot_capability_count,
                self.host_snapshot_builtin_count,
                self.host_snapshot_app_child_count,
                self.host_snapshot_mcp_child_count,
                self.host_snapshot_unclassified_count,
            )
        ):
            raise ValueError("not_run metrics must contain zero counts")
        if self.run_state == "not_run" and (self.host_snapshot_id is not None or self.host_snapshot_fingerprint is not None):
            raise ValueError("not_run metrics must not contain a Host snapshot")

    def to_mapping(self) -> dict[str, object]:
        """輸出 metrics mapping。"""

        result: dict[str, object] = {
            "run_state": self.run_state,
            "discovered_count": self.discovered_count,
            "hard_eligible_count": self.hard_eligible_count,
            "selected_count": self.selected_count,
            "digest_total_size": self.digest_total_size,
            "detail_expansion_used": self.detail_expansion_used,
            "present_count": self.present_count,
            "selectable_count": self.selectable_count,
            "verified_ready_count": self.verified_ready_count,
            "present_unverified_count": self.present_unverified_count,
            "metadata_insufficient_count": self.metadata_insufficient_count,
            "explicit_negative_count": self.explicit_negative_count,
        }
        if self.run_state == "ran":
            result.update(
                {
                    "metadata_sufficient_count": self.metadata_sufficient_count,
                    "metadata_sparse_count": self.metadata_sparse_count,
                    "metadata_opaque_count": self.metadata_opaque_count,
                    "identity_unresolved_count": self.identity_unresolved_count,
                    "provider_discovered_total": self.discovered_count,
                    "provider_present_total": self.present_count,
                    "provider_metadata_sufficient_total": self.metadata_sufficient_count,
                    "provider_metadata_sparse_total": self.metadata_sparse_count,
                    "provider_metadata_opaque_total": self.metadata_opaque_count,
                    "provider_identity_unresolved_total": self.identity_unresolved_count,
                    "provider_semantically_considered_total": self.semantically_considered_count,
                    "provider_staged_total": self.selectable_count,
                    "provider_plausible_total": self.plausible_count,
                    "provider_selected_total": self.selected_count,
                    "provider_never_considered_total": self.never_considered_count,
                    "sweep_batch_count": self.sweep_batch_count,
                    "sweep_fingerprint": self.sweep_fingerprint,
                    "host_snapshot_capability_count": self.host_snapshot_capability_count,
                    "host_snapshot_builtin_count": self.host_snapshot_builtin_count,
                    "host_snapshot_app_child_count": self.host_snapshot_app_child_count,
                    "host_snapshot_mcp_child_count": self.host_snapshot_mcp_child_count,
                    "host_snapshot_unclassified_count": self.host_snapshot_unclassified_count,
                    "host_snapshot_id": self.host_snapshot_id,
                    "host_snapshot_fingerprint": self.host_snapshot_fingerprint,
                }
            )
        return result


@dataclass(frozen=True)
class SupportingRouteContext:
    """真正 lazy、read-only、stateless 的 Phase 3 Supporting context。"""

    execution_needs: tuple[ExecutionNeed, ...]
    readiness_evidence: tuple[ReadinessEvidenceCertificate | AppReadinessEvidence | McpReadinessEvidence, ...]
    provider_digests: tuple[ProviderDigest, ...]
    detail_references: tuple[ProviderDetailReference, ...]
    metrics: SupportingMetrics
    context_fingerprint: str

    def __post_init__(self) -> None:
        """驗證 immutable context 與 deterministic fingerprint。"""

        object.__setattr__(self, "execution_needs", _execution_needs(self.execution_needs))
        object.__setattr__(self, "readiness_evidence", tuple(self.readiness_evidence))
        object.__setattr__(self, "provider_digests", tuple(self.provider_digests))
        object.__setattr__(self, "detail_references", tuple(self.detail_references))
        if not isinstance(self.metrics, SupportingMetrics):
            raise TypeError("supporting context requires SupportingMetrics")
        if _FINGERPRINT.fullmatch(self.context_fingerprint) is None:
            raise ValueError("supporting context requires a SHA-256 fingerprint")
        expected = _context_fingerprint(
            self.execution_needs,
            self.readiness_evidence,
            self.provider_digests,
            self.detail_references,
            self.metrics,
        )
        if self.context_fingerprint != expected:
            raise ValueError("supporting context fingerprint does not match contents")

    @property
    def inventory_sweep(self):
        return build_inventory_sweep(
            tuple(provider_digest(p) for p in self.provider_digests), identity_field="provider_id",
            scope_fingerprint=_sha256({"execution_needs": [need.to_mapping() for need in self.execution_needs]}),
        )

    @property
    def run_state(self) -> str:
        """回傳 supporting preparation run state。"""

        return self.metrics.run_state

    def to_mapping(self) -> dict[str, object]:
        """輸出 privacy-bounded Supporting context。"""

        return {
            "contract_version": SUPPORTING_CONTEXT_CONTRACT_VERSION,
            "execution_needs": [item.to_mapping() for item in self.execution_needs],
            "readiness_evidence": [item.to_mapping() for item in self.readiness_evidence],
            "provider_digests": [item.to_mapping() for item in self.provider_digests],
            "inventory_sweep": self.inventory_sweep.to_mapping(),
            "detail_references": [item.to_mapping() for item in self.detail_references],
            "metrics": self.metrics.to_mapping(),
            "context_fingerprint": self.context_fingerprint,
        }

    def hard_eligible_provider(self, provider_id: str) -> ProviderDigest | None:
        """回傳目前 context 中 exact selectable Provider digest；名稱保留相容性。"""

        return next((item for item in self.provider_digests if item.provider_id == provider_id), None)

    def selectable_provider(self, provider_id: str) -> ProviderDigest | None:
        """回傳目前 context 中 exact selectable Provider digest。"""

        return self.hard_eligible_provider(provider_id)


def validate_supporting_decision(
    payload: Mapping[str, object],
    execution_needs: Sequence[ExecutionNeed | Mapping[str, object]],
    context: SupportingRouteContext,
    *,
    detail_expansion_used: bool = False,
    require_final: bool = False,
) -> SupportingDecisionPayload:
    """驗證 Supporting protocol；Python 只做 identity/readiness/schema gate。"""

    if not isinstance(payload, Mapping) or set(payload) != {"request_detail", "final_selection"}:
        raise ValueError("supporting decision has an invalid schema")
    needs = _execution_needs(execution_needs)
    if not needs:
        raise ValueError("supporting decision is forbidden when execution_needs is empty")
    if not isinstance(context, SupportingRouteContext) or context.run_state != "ran":
        raise ValueError("supporting decision requires a prepared supporting context")

    request_detail = _parse_detail_request(payload["request_detail"])
    final_selection = _parse_final_selection(payload["final_selection"])
    if request_detail is not None and final_selection is not None:
        raise ValueError("request_detail and final_selection are mutually exclusive")
    if request_detail is not None:
        if detail_expansion_used or require_final:
            raise ValueError("request_detail cannot remain unresolved after one expansion")
        for provider_id, tool_ids in request_detail.requests:
            digest = context.selectable_provider(provider_id)
            if digest is None:
                raise ValueError("detail request must reference a selectable provider")
            available_tools = {tool.id for tool in digest.callable_tools}
            if not set(tool_ids).issubset(available_tools):
                raise ValueError("detail request must reference exact callable tool IDs")
        return SupportingDecisionPayload(request_detail=request_detail)

    if final_selection is None:
        raise ValueError("supporting decision requires request_detail or final_selection")
    _validate_final_selection(final_selection, needs, context)
    return SupportingDecisionPayload(final_selection=final_selection)


def validate_supporting_final_selection_payload(value: object) -> SupportingFinalSelection | None:
    """驗證 decision payload 內的 final_supporting_decision 結構。"""

    return _parse_final_selection(value)


def validate_supporting_coverage_additions(
    payload: object,
    *,
    candidate_ids: Sequence[str],
    selected_ids: Sequence[str] = (),
    execution_needs: Sequence[ExecutionNeed | Mapping[str, object]],
) -> tuple[SupportingCoverageAddition, ...]:
    """驗證唯一 Supporting Coverage Check 的 additions，不判斷 Provider 語意。"""

    if isinstance(payload, Mapping):
        if set(payload) != {"additions"}:
            raise ValueError("supporting coverage additions wrapper has an invalid schema")
        payload = payload["additions"]
    if not isinstance(payload, Sequence) or isinstance(payload, (str, bytes)):
        raise ValueError("supporting coverage additions must be a list")

    candidates = {_identifier(item, "coverage candidate provider id") for item in candidate_ids}
    selected = {_identifier(item, "coverage selected provider id") for item in selected_ids}
    need_ids = {item.need for item in _execution_needs(execution_needs)}
    result: list[SupportingCoverageAddition] = []
    seen: set[str] = set()
    for item in payload:
        if not isinstance(item, Mapping) or set(item) != {"provider_id", "execution_need", "distinct_value"}:
            raise ValueError("supporting coverage addition has an invalid schema")
        addition = SupportingCoverageAddition(
            provider_id=item["provider_id"],  # type: ignore[arg-type]
            execution_need=item["execution_need"],  # type: ignore[arg-type]
            distinct_value=item["distinct_value"],  # type: ignore[arg-type]
        )
        if addition.provider_id not in candidates:
            raise ValueError("supporting coverage addition must reference a current selectable provider")
        if addition.provider_id in selected or addition.provider_id in seen:
            raise ValueError("supporting coverage additions must contain unselected unique providers")
        if addition.execution_need not in need_ids:
            raise ValueError("supporting coverage addition must reference an original execution need")
        seen.add(addition.provider_id)
        result.append(addition)
    return tuple(result)


def normalize_execution_needs(
    value: Sequence[ExecutionNeed | Mapping[str, object]],
) -> tuple[ExecutionNeed, ...]:
    """將 Execution Needs 正規化為 immutable tuple，不做 semantic interpretation。"""

    return _execution_needs(value)


def supporting_selection_status(
    execution_needs: Sequence[ExecutionNeed | Mapping[str, object]],
    final_selection: SupportingFinalSelection | None,
    context: SupportingRouteContext | None = None,
) -> str:
    """區分 semantic no-match、presence、metadata 與 explicit negative 結果。"""

    needs = _execution_needs(execution_needs)
    if not needs:
        return "not_required"
    if final_selection is not None and final_selection.selected_supporting_capabilities:
        return "selected"
    if context is not None:
        metrics = context.metrics
        if metrics.present_count == 0:
            if metrics.explicit_negative_count:
                return "explicit_negative_exclusion"
            return "no_present_supporting_provider"
        if metrics.selectable_count == 0:
            if metrics.explicit_negative_count:
                return "explicit_negative_exclusion"
            if metrics.metadata_insufficient_count:
                return "insufficient_capability_metadata"
    return "no_matching_supporting_capability"


def _parse_detail_request(value: object) -> SupportingDetailRequest | None:
    """解析 request_detail mapping，拒絕未知欄位與未界定清單。"""

    if value is None:
        return None
    if not isinstance(value, Mapping) or set(value) != {"requests"}:
        raise ValueError("request_detail has an invalid schema")
    requests = value["requests"]
    if isinstance(requests, (str, bytes)) or not isinstance(requests, Sequence):
        raise ValueError("request_detail.requests must be a list")
    parsed = []
    for item in requests:
        if not isinstance(item, Mapping) or set(item) != {"provider_id", "tool_ids"}:
            raise ValueError("request_detail request has an invalid schema")
        tool_ids = item["tool_ids"]
        if isinstance(tool_ids, (str, bytes)) or not isinstance(tool_ids, Sequence):
            raise ValueError("request_detail.tool_ids must be a list")
        parsed.append((item["provider_id"], tuple(tool_ids)))
    return SupportingDetailRequest(tuple(parsed))


def _parse_final_selection(value: object) -> SupportingFinalSelection | None:
    """解析 final_selection public lists，不執行 Provider semantic ranking。"""

    if value is None:
        return None
    if not isinstance(value, Mapping) or set(value) != {
        "selected_supporting_capabilities",
        "unmet_execution_needs",
    }:
        raise ValueError("final_selection has an invalid schema")
    selected = value["selected_supporting_capabilities"]
    unmet = value["unmet_execution_needs"]
    if isinstance(selected, (str, bytes)) or not isinstance(selected, Sequence):
        raise ValueError("selected_supporting_capabilities must be a list")
    if isinstance(unmet, (str, bytes)) or not isinstance(unmet, Sequence):
        raise ValueError("unmet_execution_needs must be a list")
    selected_items = []
    for item in selected:
        if not isinstance(item, Mapping) or set(item) != {"kind", "canonical_provider_id", "purpose"}:
            raise ValueError("selected supporting capability has an invalid schema")
        selected_items.append(
            SupportingCapabilitySelection(
                kind=item["kind"],  # type: ignore[arg-type]
                canonical_provider_id=item["canonical_provider_id"],  # type: ignore[arg-type]
                purpose=item["purpose"],  # type: ignore[arg-type]
            )
        )
    unmet_items = []
    for item in unmet:
        if not isinstance(item, Mapping) or set(item) != {"need", "reason"}:
            raise ValueError("unmet execution need has an invalid schema")
        unmet_items.append(
            UnmetExecutionNeed(item["need"], item["reason"])  # type: ignore[arg-type]
        )
    return SupportingFinalSelection(tuple(selected_items), tuple(unmet_items))


def _validate_final_selection(
    selection: SupportingFinalSelection,
    needs: Sequence[ExecutionNeed],
    context: SupportingRouteContext,
) -> None:
    """驗證 canonical ID、kind、hard eligibility 與 unmet 原始 need 來源。"""

    need_ids = {item.need for item in needs}
    unmet_ids = {item.need for item in selection.unmet_execution_needs}
    if not unmet_ids.issubset(need_ids):
        raise ValueError("unmet execution need must originate from original needs")
    if not selection.selected_supporting_capabilities and unmet_ids != need_ids:
        raise ValueError("no selected provider requires every execution need to be unmet")
    for item in selection.selected_supporting_capabilities:
        if item.kind not in FORMAL_SUPPORTING_PROVIDER_KINDS:
            raise ValueError("plugin package is not a formal selected supporting provider")
        digest = context.hard_eligible_provider(item.canonical_provider_id)
        if digest is None or digest.kind != item.kind:
            raise ValueError("selected supporting provider is not selectable with matching kind")


def prepare_supporting_context(
    execution_needs: Sequence[ExecutionNeed | Mapping[str, object]],
    *,
    provider_declarations: Sequence[SupportingProviderDeclaration | Mapping[str, object]] = (),
    readiness_evidence: Sequence[ReadinessEvidenceCertificate | AppReadinessEvidence | McpReadinessEvidence] = (),
    host_capability_snapshot: HostCapabilitySnapshot | None = None,
    host_native_registry: Sequence[Mapping[str, object]] | Mapping[str, object] = (),
    plugin_manifests: Sequence[Mapping[str, object]] = (),
) -> SupportingRouteContext:
    """準備 Supporting context；不呼叫 Provider、LLM、Receipt 或 production route。

    `host_capability_snapshot` 必須是 controller-owned trusted envelope 正規化後的
    `HostCapabilitySnapshot`；legacy `host_native_registry` 與 `plugin_manifests`
    仍可供既有 adapter compatibility 使用。
    """

    # lazy: execution_needs 為空時，在任何 Provider input 被讀取前立即返回 not_run。
    if isinstance(execution_needs, (str, bytes)) or not isinstance(execution_needs, Sequence):
        raise ValueError("execution_needs must be a sequence")
    if len(execution_needs) == 0:
        metrics = SupportingMetrics("not_run", 0, 0, 0, 0, False)
        return SupportingRouteContext((), (), (), (), metrics, _context_fingerprint((), (), (), (), metrics))

    needs = _execution_needs(execution_needs)
    from .provider_adapters import _merge_declaration_into

    evidence = tuple(_validate_readiness_evidence(item) for item in readiness_evidence)
    declarations = tuple(
        item if isinstance(item, SupportingProviderDeclaration) else SupportingProviderDeclaration.from_mapping(item)
        for item in provider_declarations
    )
    discovered_inventory = None
    if host_capability_snapshot is not None or host_native_registry or plugin_manifests:
        from .provider_adapters import discover_provider_inventory

        discovered_inventory = discover_provider_inventory(
            host_capability_snapshot=host_capability_snapshot,
            host_native_registry=host_native_registry,
            plugin_manifests=plugin_manifests,
        )
        declarations = (*declarations, *discovered_inventory.provider_declarations)
    certified_before_merge = {
        (certificate.kind, certificate.provider_id)
        for certificate in evidence
        if isinstance(certificate, ReadinessEvidenceCertificate)
        and any(
            (declaration.kind, declaration.provider_id) == (certificate.kind, certificate.provider_id)
            and _matches_certificate(declaration, certificate)
            for declaration in declarations
        )
    }
    exact_declarations: dict[tuple[str, str], SupportingProviderDeclaration] = {}
    for declaration in declarations:
        key = (declaration.kind, declaration.provider_id)
        previous = exact_declarations.get(key)
        if previous is None:
            exact_declarations[key] = declaration
        elif declaration.kind in FORMAL_SUPPORTING_PROVIDER_KINDS:
            _merge_declaration_into(exact_declarations, declaration)
        elif previous.to_mapping() != declaration.to_mapping():
            raise ValueError("supporting Provider identity has conflicting non-formal metadata")
    declarations = tuple(exact_declarations.values())
    evidence_by_key = {(item.provider_id, item.kind): item for item in evidence}
    eligible: list[
        tuple[
            SupportingProviderDeclaration,
            ReadinessEvidenceCertificate | AppReadinessEvidence | McpReadinessEvidence | None,
            str,
            tuple[SupportingTool, ...],
            bool,
        ]
    ] = []
    present_count = 0
    metadata_insufficient_count = 0
    metadata_sufficient_count = 0
    metadata_sparse_count = 0
    metadata_opaque_count = 0
    identity_unresolved_count = 0
    explicit_negative_count = 0
    for declaration in sorted(declarations, key=lambda item: (item.provider_id.casefold(), item.provider_id, item.kind)):
        if declaration.kind not in FORMAL_SUPPORTING_PROVIDER_KINDS:
            explicit_negative_count += 1
            continue
        if declaration.presence_state != "PRESENT":
            explicit_negative_count += 1
            continue
        if declaration.existence_evidence_state == ExistenceEvidenceState.DECLARATION_ONLY:
            identity_unresolved_count += 1
            continue
        present_count += 1
        callable_tools = _usable_tools(declaration.callable_tools)
        if declaration.explicit_negative_reason is not None:
            # Provider readiness/negative evidence 只供 execution diagnostics；
            # declaration 仍可進 semantic candidate，只要 metadata 足夠。
            explicit_negative_count += 1
        certificate = evidence_by_key.get((declaration.provider_id, declaration.kind))
        if certificate is not None and _certificate_is_explicit_negative(certificate):
            explicit_negative_count += 1
        readiness_state = _provider_readiness_state(
            declaration,
            certificate,
            certified_before_merge=(declaration.kind, declaration.provider_id) in certified_before_merge,
        )
        quality = declaration.metadata_quality
        if quality == MetadataQuality.SUFFICIENT:
            metadata_sufficient_count += 1
        elif quality == MetadataQuality.SPARSE:
            metadata_sparse_count += 1
        else:
            metadata_opaque_count += 1
        if quality != MetadataQuality.SUFFICIENT:
            metadata_insufficient_count += 1
        include_evidence = certificate is not None and (
            isinstance(certificate, (AppReadinessEvidence, McpReadinessEvidence))
            or _matches_certificate(declaration, certificate)
        )
        eligible.append((declaration, certificate, readiness_state, callable_tools, include_evidence))

    digests = tuple(
        _build_digest(declaration, certificate, readiness_state, callable_tools)
        for declaration, certificate, readiness_state, callable_tools, _ in eligible
    )
    references = tuple(
        ProviderDetailReference(
            provider_id=digest.provider_id,
            callable_tool_ids=tuple(tool.id for tool in digest.callable_tools),
            digest_fingerprint=digest.fingerprint,
        )
        for digest in digests
    )
    matched_evidence = tuple(
        certificate
        for _, certificate, _, _, include_evidence in eligible
        if certificate is not None and include_evidence
    )
    verified_ready_count = sum(item.readiness_state == "VERIFIED_READY" for item in digests)
    # Compatibility counter：除 VERIFIED_READY 外的所有 present digest 都屬於
    # unverified execution readiness，包含 KNOWN_UNAVAILABLE。
    present_unverified_count = sum(item.readiness_state != "VERIFIED_READY" for item in digests)
    provider_sweep = build_inventory_sweep(
        tuple(provider_digest(item) for item in digests),
        identity_field="provider_id",
        scope_fingerprint=_sha256({"execution_needs": [need.to_mapping() for need in needs]}),
    )
    metrics = SupportingMetrics(
        run_state="ran",
        discovered_count=len(declarations),
        hard_eligible_count=verified_ready_count,
        selected_count=0,
        digest_total_size=sum(
            len(json.dumps(digest.to_mapping(), ensure_ascii=False, sort_keys=True, separators=(",", ":")))
            for digest in digests
        ),
        detail_expansion_used=False,
        present_count=present_count,
        selectable_count=len(digests),
        verified_ready_count=verified_ready_count,
        present_unverified_count=present_unverified_count,
        metadata_insufficient_count=metadata_insufficient_count,
        explicit_negative_count=explicit_negative_count,
        metadata_sufficient_count=metadata_sufficient_count,
        metadata_sparse_count=metadata_sparse_count,
        metadata_opaque_count=metadata_opaque_count,
        identity_unresolved_count=identity_unresolved_count,
        semantically_considered_count=len(provider_sweep.considered_ids),
        plausible_count=0,
        never_considered_count=len(provider_sweep.never_considered_ids),
        sweep_batch_count=provider_sweep.batch_count,
        sweep_fingerprint=provider_sweep.fingerprint,
        host_snapshot_capability_count=(
            0 if discovered_inventory is None else discovered_inventory.host_snapshot_capability_count
        ),
        host_snapshot_builtin_count=(
            0 if discovered_inventory is None else discovered_inventory.host_snapshot_builtin_count
        ),
        host_snapshot_app_child_count=(
            0 if discovered_inventory is None else discovered_inventory.host_snapshot_app_child_count
        ),
        host_snapshot_mcp_child_count=(
            0 if discovered_inventory is None else discovered_inventory.host_snapshot_mcp_child_count
        ),
        host_snapshot_unclassified_count=(
            0 if discovered_inventory is None else discovered_inventory.host_snapshot_unclassified_count
        ),
        host_snapshot_id=(None if discovered_inventory is None else discovered_inventory.host_snapshot_id),
        host_snapshot_fingerprint=(
            None if discovered_inventory is None else discovered_inventory.host_snapshot_fingerprint
        ),
    )
    fingerprint = _context_fingerprint(needs, matched_evidence, digests, references, metrics)
    return SupportingRouteContext(needs, matched_evidence, digests, references, metrics, fingerprint)


def _matches_certificate(
    declaration: SupportingProviderDeclaration,
    certificate: ReadinessEvidenceCertificate | AppReadinessEvidence | McpReadinessEvidence,
) -> bool:
    """以 exact Host evidence 判斷 verified-ready；差異只會降級為 unverified。"""

    if isinstance(certificate, AppReadinessEvidence):
        return (
            declaration.kind == "app"
            and declaration.provider_id == certificate.provider_id
            and declaration.callable_exposure
            and certificate.hard_eligible
            and bool(declaration.callable_tools)
            and all(
                isinstance(tool, SupportingToolSummary)
                and tool.is_enabled
                and tool.disabled_reason is None
                for tool in declaration.callable_tools
            )
        )
    if isinstance(certificate, McpReadinessEvidence):
        declared_ids = _tool_ids(declaration.callable_tools)
        return (
            declaration.kind == "mcp"
            and declaration.provider_id == certificate.provider_id
            and declaration.callable_exposure
            and certificate.hard_eligible
            and declared_ids == certificate.callable_tool_ids
            and bool(declared_ids)
        )
    if (declaration.kind, declaration.provider_id) not in _CERTIFIED_PROVIDER_SCOPE:
        return False
    if not declaration.callable_exposure:
        return False
    return (
        declaration.kind == certificate.kind
        and declaration.host_identity == certificate.host_identity
        and declaration.host_grouping == certificate.host_grouping
        and tuple(tool.id for tool in declaration.callable_tools) == certificate.callable_tool_ids
        and declaration.schema_fingerprint == certificate.expected_schema_fingerprint
        and declaration.fingerprint == certificate.expected_declaration_fingerprint
        and declaration.provenance == certificate.provenance
    )


def _build_digest(
    declaration: SupportingProviderDeclaration,
    certificate: ReadinessEvidenceCertificate | AppReadinessEvidence | McpReadinessEvidence | None,
    readiness_state: str,
    callable_tools: Sequence[SupportingTool],
) -> ProviderDigest:
    """對存在且 identity 已解析的 Provider 建立 digest，不以 metadata/readiness 排除。"""

    payload = {
        "provider_id": declaration.provider_id,
        "kind": declaration.kind,
        "display_name": declaration.display_name or declaration.provider_id,
        "description": declaration.description,
        "callable_tools": [tool.to_mapping() for tool in callable_tools],
        "readiness_evidence_fingerprint": None if certificate is None else certificate.fingerprint,
        "presence_state": declaration.presence_state,
        "readiness_state": readiness_state,
        "discovery_evidence_state": declaration.discovery_evidence_state,
        "provenance": list(declaration.provenance),
        "metadata_quality": declaration.metadata_quality.value,
        "raw_external_identity": declaration.raw_external_identity,
        "canonical_grouping_key": declaration.canonical_grouping_key,
        "hierarchy_state": declaration.hierarchy_state,
    }
    return ProviderDigest(
        provider_id=declaration.provider_id,
        kind=declaration.kind,
        description=declaration.description,
        callable_tools=tuple(callable_tools),
        provenance=declaration.provenance,
        fingerprint=_sha256(payload),
        display_name=declaration.display_name or declaration.provider_id,
        presence_state=declaration.presence_state,
        readiness_state=readiness_state,
        discovery_evidence_state=declaration.discovery_evidence_state,
        existence_evidence_state=declaration.existence_evidence_state,
        metadata_quality=declaration.metadata_quality,
        raw_external_identity=declaration.raw_external_identity,
        canonical_grouping_key=declaration.canonical_grouping_key,
        hierarchy_state=declaration.hierarchy_state,
    )


def _usable_tools(value: Sequence[SupportingTool]) -> tuple[SupportingTool, ...]:
    """保留所有可讀 tool summary；enabled 只留作 execution readiness。"""

    return tuple(value)


def _has_sufficient_capability_metadata(
    declaration: SupportingProviderDeclaration,
    callable_tools: Sequence[SupportingTool],
) -> bool:
    """確認 Provider name 加 description 或 tool summary 足以交給 LLM。"""

    # Provider presence/readiness 與語意理解分開；description 足夠時不要求
    # callable tool detail，具備 title/description 的 tool summary 也可提供最低語意。
    provider_description = declaration.description is not None and bool(declaration.description.strip())
    tool_summary = any(
        bool(getattr(tool, "description", "").strip()) or bool(getattr(tool, "title", None))
        for tool in callable_tools
    )
    return provider_description or tool_summary


def _certificate_is_explicit_negative(
    certificate: ReadinessEvidenceCertificate | AppReadinessEvidence | McpReadinessEvidence,
) -> bool:
    """辨識 Host 明確 negative，不把 absence of readiness evidence 當 negative。"""

    return isinstance(certificate, (AppReadinessEvidence, McpReadinessEvidence)) and certificate.readiness_state == "KNOWN_UNAVAILABLE"


def _provider_readiness_state(
    declaration: SupportingProviderDeclaration,
    certificate: ReadinessEvidenceCertificate | AppReadinessEvidence | McpReadinessEvidence | None,
    *,
    certified_before_merge: bool = False,
) -> str:
    """將 typed readiness evidence 正規化為 ready 或 present-unverified。

    `certified_before_merge` 表示 exact certificate 已在多來源 merge 前驗證成功；
    merge 只增加 discovery/metadata provenance，不會使較強 runtime evidence 消失。
    """

    if certificate is None:
        return "PRESENT_UNVERIFIED"
    if isinstance(certificate, ReadinessEvidenceCertificate) and certified_before_merge:
        return "VERIFIED_READY"
    if isinstance(certificate, (AppReadinessEvidence, McpReadinessEvidence)):
        if (
            certificate.readiness_state == "VERIFIED_READY"
            and (not declaration.callable_exposure or not declaration.callable_tools)
        ):
            return "PRESENT_UNVERIFIED"
        return certificate.readiness_state
    return "VERIFIED_READY" if _matches_certificate(declaration, certificate) else "PRESENT_UNVERIFIED"


def _context_fingerprint(
    needs: Sequence[ExecutionNeed],
    evidence: Sequence[ReadinessEvidenceCertificate | AppReadinessEvidence | McpReadinessEvidence],
    digests: Sequence[ProviderDigest],
    references: Sequence[ProviderDetailReference],
    metrics: SupportingMetrics,
) -> str:
    """固定 context inputs 產生 deterministic fingerprint。"""

    return _sha256(
        {
            "contract_version": SUPPORTING_CONTEXT_CONTRACT_VERSION,
            "execution_needs": [item.to_mapping() for item in needs],
            "readiness_evidence": [item.to_mapping() for item in evidence],
            "provider_digests": [item.to_mapping() for item in digests],
            "detail_references": [item.to_mapping() for item in references],
            "metrics": metrics.to_mapping(),
        }
    )


def _execution_needs(value: Sequence[ExecutionNeed | Mapping[str, object]]) -> tuple[ExecutionNeed, ...]:
    """將 execution needs 轉成 immutable public records。"""

    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise ValueError("execution_needs must be a sequence")
    result: list[ExecutionNeed] = []
    for item in value:
        if isinstance(item, ExecutionNeed):
            result.append(item)
            continue
        if not isinstance(item, Mapping) or set(item) != {"need", "reason"}:
            raise ValueError("execution need has an invalid schema")
        result.append(ExecutionNeed(item["need"], item["reason"]))  # type: ignore[arg-type]
    return tuple(result)


def _tool_tuple(value: Sequence[SupportingTool]) -> tuple[SupportingTool, ...]:
    """固定 tool declaration 順序，拒絕重複 exact tool ID。"""

    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise ValueError("callable_tools must be a sequence")
    tools = tuple(value)
    if not all(isinstance(item, (SupportingToolDeclaration, SupportingToolSummary)) for item in tools):
        raise TypeError("callable_tools must contain validated tool declarations or summaries")
    ordered = tuple(sorted(tools, key=lambda item: (item.id.casefold(), item.id)))
    if len({item.id for item in ordered}) != len(ordered):
        raise ValueError("callable_tools cannot contain duplicate IDs")
    return ordered


def _tool_from_mapping(value: object) -> SupportingTool:
    """Parse either legacy schema declarations or official metadata summaries."""

    if isinstance(value, (SupportingToolDeclaration, SupportingToolSummary)):
        return value
    if not isinstance(value, Mapping):
        raise TypeError("callable_tools must contain mappings or validated tool values")
    if "schema" in value:
        return SupportingToolDeclaration.from_mapping(value)
    return SupportingToolSummary.from_mapping(value)


def _tool_ids(value: Sequence[SupportingTool]) -> tuple[str, ...]:
    """Return stable tool IDs without interpreting capability semantics."""

    return tuple(sorted((tool.id for tool in value), key=lambda item: (item.casefold(), item)))


def _validate_readiness_evidence(
    value: object,
) -> ReadinessEvidenceCertificate | AppReadinessEvidence | McpReadinessEvidence:
    """Accept only designated typed readiness evidence; never infer from mappings."""

    if isinstance(value, (ReadinessEvidenceCertificate, AppReadinessEvidence, McpReadinessEvidence)):
        return value
    raise TypeError(
        "readiness_evidence must contain ReadinessEvidenceCertificate, AppReadinessEvidence, or McpReadinessEvidence instances"
    )


def _reject_non_certificate(value: object) -> ReadinessEvidenceCertificate:
    """拒絕未經明確 certificate validation 的 mapping，避免 production 猜 readiness。"""

    raise TypeError("readiness_evidence must contain ReadinessEvidenceCertificate instances")


def _identifier(value: object, field: str) -> str:
    """驗證 canonical public identifier。"""

    if not isinstance(value, str) or _IDENTIFIER.fullmatch(value.strip()) is None:
        raise ValueError(f"{field} must be a canonical identifier")
    return value.strip()


def canonicalize_external_identity(raw_external_identity: object, namespace: str) -> str:
    """將外部 identity 轉成 collision-safe internal grouping key。

    外部值只保存作 provenance；Router 的 canonical validator 仍維持原本嚴格
    規則。SHA-256 key 不做 semantic normalization，因此 `foo@bar` 與
    `foo-bar` 不會因字串替換而意外合併。
    """

    raw = _safe_text(raw_external_identity, "raw external identity", 512)
    prefix = _identifier(namespace, "canonical grouping namespace")
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    return f"{prefix}-{digest}"


def _identifier_tuple(value: Sequence[str], field: str) -> tuple[str, ...]:
    """驗證並 deterministic sort identifier sequence。"""

    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise ValueError(f"{field} must be a sequence of identifiers")
    result = tuple(_identifier(item, field) for item in value)
    if len(set(result)) != len(result):
        raise ValueError(f"{field} cannot contain duplicate identifiers")
    return tuple(sorted(result, key=lambda item: (item.casefold(), item)))


def _provenance(value: Sequence[str]) -> tuple[str, ...]:
    """驗證 abstract provenance labels，不保存 private path。"""

    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise ValueError("provenance must be a sequence")
    result = tuple(_safe_text(item, "provenance", 256) for item in value)
    if len(set(result)) != len(result):
        raise ValueError("provenance cannot contain duplicates")
    return tuple(sorted(result, key=lambda item: (item.casefold(), item)))


def _safe_text(value: object, field: str, maximum: int) -> str:
    """限制 public text，拒絕 absolute path、secret-like input 與 NUL。"""

    if not isinstance(value, str):
        raise ValueError(f"{field} must be text")
    result = value.strip()
    if (
        not result
        or len(result) > maximum
        or "\x00" in result
        or _SENSITIVE.search(result)
        or PureWindowsPath(result).is_absolute()
        or PurePosixPath(result).is_absolute()
    ):
        raise ValueError(f"{field} must be bounded public text")
    return result


def _safe_public_label(value: object, field: str, maximum: int) -> str:
    """驗證 public label/identity；允許含保留字的穩定 tool ID，不允許 secret assignment。"""

    if not isinstance(value, str):
        raise ValueError(f"{field} must be text")
    result = value.strip()
    if (
        not result
        or len(result) > maximum
        or "\x00" in result
        or PureWindowsPath(result).is_absolute()
        or PurePosixPath(result).is_absolute()
    ):
        raise ValueError(f"{field} must be bounded public text")
    if _SENSITIVE.search(result) and _PUBLIC_ID.fullmatch(result) is None:
        raise ValueError(f"{field} must not contain secret-like content")
    return result


def _nullable_text(value: object, field: str, maximum: int) -> str | None:
    """Validate an official nullable public description without inventing text."""

    if value is None:
        return None
    return _safe_text(value, field, maximum)


def _canonical_schema(value: object) -> str:
    """驗證 bounded JSON-like schema，移除格式差異但不保存 private content。"""

    normalized = _public_value(value, depth=0)
    if not isinstance(normalized, dict):
        raise ValueError("tool schema must be an object")
    return json.dumps(normalized, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _public_value(value: object, *, depth: int) -> object:
    """遞迴固定 schema public values，拒絕 sensitive keys 與無界 nested data。"""

    if depth > 5:
        raise ValueError("tool schema nesting is too deep")
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError("tool schema numbers must be finite")
        return value
    if isinstance(value, str):
        return _safe_text(value, "tool schema text", 512)
    if isinstance(value, Mapping):
        if len(value) > 64:
            raise ValueError("tool schema object is too large")
        result: dict[str, object] = {}
        for key in sorted(value, key=lambda item: str(item).casefold()):
            if not isinstance(key, str) or not key.strip() or _SENSITIVE.search(key):
                raise ValueError("tool schema contains unsupported key")
            result[key] = _public_value(value[key], depth=depth + 1)
        return result
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
        if len(value) > 64:
            raise ValueError("tool schema array is too large")
        return [_public_value(item, depth=depth + 1) for item in value]
    raise ValueError("tool schema contains unsupported value")


def _sha256(payload: Mapping[str, object]) -> str:
    """以 canonical JSON 產生 deterministic SHA-256 digest。"""

    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
