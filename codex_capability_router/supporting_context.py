"""Phase 3 lazy Supporting Provider context 與 readiness evidence contract。"""

# 修改紀錄（2026-08-26，Steve Peng）
# 原始內容：Phase 3 只準備 hard-eligible Provider digest/detail references，尚無 final decision protocol。
# 修改原因：Phase 4 需要 bounded request_detail/final_selection、status gate 與 exact Provider validation。
# 修改後功能：新增 immutable Supporting decision contracts；只驗證 schema、canonical identity、readiness 與原始 need 來源，不做 semantic selection 或 endpoint invocation。

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import PurePosixPath, PureWindowsPath
import re


SUPPORTING_CONTEXT_CONTRACT_VERSION = "v0.2-supporting-context-v1"
READINESS_EVIDENCE_CONTRACT_VERSION = "v0.2-phase0-runtime-readiness-v1"
_FINGERPRINT = re.compile(r"^[0-9a-f]{64}$")
_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]*$")
_PROVIDER_KINDS = frozenset({"mcp", "builtin_tool", "app", "plugin"})
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


SUPPORTING_SELECTION_STATUSES = frozenset(
    {"not_required", "selected", "no_matching_supporting_capability"}
)


@dataclass(frozen=True)
class SupportingCapabilitySelection:
    """Codex final selection 的單一 Provider-level public item。"""

    kind: str
    canonical_provider_id: str
    purpose: str

    def __post_init__(self) -> None:
        """只驗證 schema 與 bounded public text，不判斷語意適用性。"""

        if self.kind not in {"mcp", "builtin_tool", "app", "plugin"}:
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
class SupportingDetailRequest:
    """一輪 bounded request_detail；只引用 exact hard-eligible provider/tool IDs。"""

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
class SupportingProviderDeclaration:
    """Host runtime 暴露的單一 Provider declaration；不執行任何 endpoint。"""

    provider_id: str
    kind: str
    host_identity: str
    host_grouping: tuple[str, ...]
    description: str
    callable_tools: tuple[SupportingToolDeclaration, ...]
    callable_exposure: bool
    provenance: tuple[str, ...]

    def __post_init__(self) -> None:
        """驗證 Host identity/grouping 與 exact callable surface。"""

        object.__setattr__(self, "provider_id", _identifier(self.provider_id, "provider id"))
        if self.kind not in _PROVIDER_KINDS:
            raise ValueError("unsupported supporting provider kind")
        object.__setattr__(self, "host_identity", _identifier(self.host_identity, "host identity"))
        object.__setattr__(self, "host_grouping", _identifier_tuple(self.host_grouping, "host_grouping"))
        object.__setattr__(self, "description", _safe_text(self.description, "provider description", 1024))
        object.__setattr__(self, "callable_tools", _tool_tuple(self.callable_tools))
        if not isinstance(self.callable_exposure, bool):
            raise ValueError("callable_exposure must be boolean")
        object.__setattr__(self, "provenance", _provenance(self.provenance))

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
            callable_tools=tuple(
                item if isinstance(item, SupportingToolDeclaration) else SupportingToolDeclaration.from_mapping(item)
                for item in tools
            ),
            callable_exposure=payload.get("callable_exposure"),  # type: ignore[arg-type]
            provenance=payload.get("provenance", ()),  # type: ignore[arg-type]
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

        return {
            "provider_id": self.provider_id,
            "kind": self.kind,
            "host_identity": self.host_identity,
            "host_grouping": list(self.host_grouping),
            "description": self.description,
            "callable_tools": [tool.to_mapping() for tool in self.callable_tools],
            "callable_exposure": self.callable_exposure,
            "provenance": list(self.provenance),
        }


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
    """Hard-eligible Provider 的 deterministic digest；不含 semantic ranking。"""

    provider_id: str
    kind: str
    description: str
    callable_tools: tuple[SupportingToolDeclaration, ...]
    provenance: tuple[str, ...]
    fingerprint: str

    def __post_init__(self) -> None:
        """驗證 digest fingerprint 與 public provider metadata。"""

        object.__setattr__(self, "provider_id", _identifier(self.provider_id, "provider id"))
        if self.kind not in {"mcp", "builtin_tool"}:
            raise ValueError("provider digest requires a certified provider kind")
        object.__setattr__(self, "description", _safe_text(self.description, "provider description", 1024))
        object.__setattr__(self, "callable_tools", _tool_tuple(self.callable_tools))
        object.__setattr__(self, "provenance", _provenance(self.provenance))
        if _FINGERPRINT.fullmatch(self.fingerprint) is None:
            raise ValueError("provider digest requires a SHA-256 fingerprint")

    def to_mapping(self) -> dict[str, object]:
        """輸出 digest public projection，不產生 semantic fields。"""

        return {
            "provider_id": self.provider_id,
            "kind": self.kind,
            "description": self.description,
            "callable_tools": [tool.to_mapping() for tool in self.callable_tools],
            "provenance": list(self.provenance),
            "fingerprint": self.fingerprint,
        }


@dataclass(frozen=True)
class SupportingMetrics:
    """Phase 3 preparation metrics；selected_count 永遠保持 0。"""

    run_state: str
    discovered_count: int
    hard_eligible_count: int
    selected_count: int
    digest_total_size: int
    detail_expansion_used: bool

    def __post_init__(self) -> None:
        """驗證 lazy run state 與未選擇 contract。"""

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
        if self.hard_eligible_count > self.discovered_count:
            raise ValueError("hard_eligible_count cannot exceed discovered_count")
        if self.selected_count != 0:
            raise ValueError("Phase 3 selected_count must remain zero")
        if not isinstance(self.detail_expansion_used, bool):
            raise ValueError("detail_expansion_used must be boolean")
        if self.run_state == "not_run" and any(
            value != 0
            for value in (
                self.discovered_count,
                self.hard_eligible_count,
                self.selected_count,
                self.digest_total_size,
            )
        ):
            raise ValueError("not_run metrics must contain zero counts")

    def to_mapping(self) -> dict[str, object]:
        """輸出 metrics mapping。"""

        return {
            "run_state": self.run_state,
            "discovered_count": self.discovered_count,
            "hard_eligible_count": self.hard_eligible_count,
            "selected_count": self.selected_count,
            "digest_total_size": self.digest_total_size,
            "detail_expansion_used": self.detail_expansion_used,
        }


@dataclass(frozen=True)
class SupportingRouteContext:
    """真正 lazy、read-only、stateless 的 Phase 3 Supporting context。"""

    execution_needs: tuple[ExecutionNeed, ...]
    readiness_evidence: tuple[ReadinessEvidenceCertificate, ...]
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
            "detail_references": [item.to_mapping() for item in self.detail_references],
            "metrics": self.metrics.to_mapping(),
            "context_fingerprint": self.context_fingerprint,
        }

    def hard_eligible_provider(self, provider_id: str) -> ProviderDigest | None:
        """回傳目前 context 中 exact hard-eligible provider digest。"""

        return next((item for item in self.provider_digests if item.provider_id == provider_id), None)


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
            digest = context.hard_eligible_provider(provider_id)
            if digest is None:
                raise ValueError("detail request must reference a hard-eligible provider")
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


def normalize_execution_needs(
    value: Sequence[ExecutionNeed | Mapping[str, object]],
) -> tuple[ExecutionNeed, ...]:
    """將 Execution Needs 正規化為 immutable tuple，不做 semantic interpretation。"""

    return _execution_needs(value)


def supporting_selection_status(
    execution_needs: Sequence[ExecutionNeed | Mapping[str, object]],
    final_selection: SupportingFinalSelection | None,
) -> str:
    """依結構化選擇數量 deterministic 產生三值 Supporting status。"""

    needs = _execution_needs(execution_needs)
    if not needs:
        return "not_required"
    if final_selection is not None and final_selection.selected_supporting_capabilities:
        return "selected"
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
        digest = context.hard_eligible_provider(item.canonical_provider_id)
        if digest is None or digest.kind != item.kind:
            raise ValueError("selected supporting provider is not hard-eligible with matching kind")


def prepare_supporting_context(
    execution_needs: Sequence[ExecutionNeed | Mapping[str, object]],
    *,
    provider_declarations: Sequence[SupportingProviderDeclaration | Mapping[str, object]] = (),
    readiness_evidence: Sequence[ReadinessEvidenceCertificate] = (),
) -> SupportingRouteContext:
    """準備 Supporting context；不呼叫 Provider、LLM、Receipt 或 production route。"""

    # lazy: execution_needs 為空時，在任何 Provider input 被讀取前立即返回 not_run。
    if isinstance(execution_needs, (str, bytes)) or not isinstance(execution_needs, Sequence):
        raise ValueError("execution_needs must be a sequence")
    if len(execution_needs) == 0:
        metrics = SupportingMetrics("not_run", 0, 0, 0, 0, False)
        return SupportingRouteContext((), (), (), (), metrics, _context_fingerprint((), (), (), (), metrics))

    needs = _execution_needs(execution_needs)
    declarations = tuple(
        item if isinstance(item, SupportingProviderDeclaration) else SupportingProviderDeclaration.from_mapping(item)
        for item in provider_declarations
    )
    evidence = tuple(
        item if isinstance(item, ReadinessEvidenceCertificate) else _reject_non_certificate(item)
        for item in readiness_evidence
    )
    evidence_by_key = {(item.provider_id, item.kind): item for item in evidence}
    eligible: list[tuple[SupportingProviderDeclaration, ReadinessEvidenceCertificate]] = []
    for declaration in sorted(declarations, key=lambda item: (item.provider_id.casefold(), item.provider_id, item.kind)):
        certificate = evidence_by_key.get((declaration.provider_id, declaration.kind))
        if certificate is None or not _matches_certificate(declaration, certificate):
            continue
        eligible.append((declaration, certificate))

    digests = tuple(_build_digest(declaration, certificate) for declaration, certificate in eligible)
    references = tuple(
        ProviderDetailReference(
            provider_id=digest.provider_id,
            callable_tool_ids=tuple(tool.id for tool in digest.callable_tools),
            digest_fingerprint=digest.fingerprint,
        )
        for digest in digests
    )
    matched_evidence = tuple(certificate for _, certificate in eligible)
    metrics = SupportingMetrics(
        "ran",
        len(declarations),
        len(eligible),
        0,
        sum(len(json.dumps(digest.to_mapping(), ensure_ascii=False, sort_keys=True, separators=(",", ":"))) for digest in digests),
        False,
    )
    fingerprint = _context_fingerprint(needs, matched_evidence, digests, references, metrics)
    return SupportingRouteContext(needs, matched_evidence, digests, references, metrics, fingerprint)


def _matches_certificate(
    declaration: SupportingProviderDeclaration,
    certificate: ReadinessEvidenceCertificate,
) -> bool:
    """以 exact Host evidence 比對 eligibility；任何差異均排除。"""

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
    certificate: ReadinessEvidenceCertificate,
) -> ProviderDigest:
    """只對 hard-eligible declaration 建立 deterministic digest。"""

    payload = {
        "provider_id": declaration.provider_id,
        "kind": declaration.kind,
        "description": declaration.description,
        "callable_tools": [tool.to_mapping() for tool in declaration.callable_tools],
        "readiness_evidence_fingerprint": certificate.fingerprint,
        "provenance": list(declaration.provenance),
    }
    return ProviderDigest(
        provider_id=declaration.provider_id,
        kind=declaration.kind,
        description=declaration.description,
        callable_tools=declaration.callable_tools,
        provenance=declaration.provenance,
        fingerprint=_sha256(payload),
    )


def _context_fingerprint(
    needs: Sequence[ExecutionNeed],
    evidence: Sequence[ReadinessEvidenceCertificate],
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


def _tool_tuple(value: Sequence[SupportingToolDeclaration]) -> tuple[SupportingToolDeclaration, ...]:
    """固定 tool declaration 順序，拒絕重複 exact tool ID。"""

    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise ValueError("callable_tools must be a sequence")
    tools = tuple(value)
    if not all(isinstance(item, SupportingToolDeclaration) for item in tools):
        raise TypeError("callable_tools must contain SupportingToolDeclaration")
    ordered = tuple(sorted(tools, key=lambda item: (item.id.casefold(), item.id)))
    if len({item.id for item in ordered}) != len(ordered):
        raise ValueError("callable_tools cannot contain duplicate IDs")
    return ordered


def _reject_non_certificate(value: object) -> ReadinessEvidenceCertificate:
    """拒絕未經明確 certificate validation 的 mapping，避免 production 猜 readiness。"""

    raise TypeError("readiness_evidence must contain ReadinessEvidenceCertificate instances")


def _identifier(value: object, field: str) -> str:
    """驗證 canonical public identifier。"""

    if not isinstance(value, str) or _IDENTIFIER.fullmatch(value.strip()) is None:
        raise ValueError(f"{field} must be a canonical identifier")
    return value.strip()


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
