"""Deterministic digest staging and validated Host decision coverage."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
import hashlib
import json
import re


_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]*$")
DEFAULT_SWEEP_ITEM_LIMIT = 24
DEFAULT_SWEEP_BYTE_LIMIT = 24_000


@dataclass(frozen=True)
class InventorySweep:
    """Public staging and Host disposition evidence; no semantic ranking."""

    identity_field: str
    batches: tuple[tuple[str, ...], ...]
    considered_ids: tuple[str, ...]
    never_considered_ids: tuple[str, ...]
    fingerprint: str
    decision_received_ids: tuple[str, ...] = ()
    selected_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        """Validate batch identities and the received/resolved/missing partitions."""

        if not isinstance(self.identity_field, str) or not self.identity_field.strip():
            raise ValueError("identity_field must be non-empty text")
        batches = tuple(tuple(batch) for batch in self.batches)
        considered = tuple(self.considered_ids)
        never = tuple(self.never_considered_ids)
        if len(set(considered)) != len(considered):
            raise ValueError("considered IDs must be unique")
        if len(set(never)) != len(never) or set(considered) & set(never):
            raise ValueError("sweep IDs must be disjoint and unique")
        flattened = tuple(item for batch in batches for item in batch)
        received = tuple(self.decision_received_ids)
        selected = tuple(self.selected_ids)
        if len(set(flattened)) != len(flattened):
            raise ValueError("staged IDs must be unique")
        for values in (considered, never, received, selected):
            identities = set(values)
            if tuple(item for item in flattened if item in identities) != values:
                raise ValueError("sweep IDs must preserve deterministic batch order")
        if not set(selected) <= set(considered) <= set(received):
            raise ValueError("selected and considered IDs require received decisions")
        if set(never) != set(flattened) - set(received):
            raise ValueError("missing decisions must remain unconsidered")
        if any(_IDENTIFIER.fullmatch(item) is None for item in (*considered, *never)):
            raise ValueError("sweep IDs must be canonical identifiers")
        if not isinstance(self.fingerprint, str) or not re.fullmatch(r"[0-9a-f]{64}", self.fingerprint):
            raise ValueError("sweep fingerprint must be a SHA-256 digest")
        object.__setattr__(self, "batches", batches)
        object.__setattr__(self, "considered_ids", considered)
        object.__setattr__(self, "never_considered_ids", never)
        object.__setattr__(self, "decision_received_ids", received)
        object.__setattr__(self, "selected_ids", selected)

    @property
    def staged_ids(self) -> tuple[str, ...]:
        return tuple(item for batch in self.batches for item in batch)

    @property
    def unresolved_ids(self) -> tuple[str, ...]:
        resolved = set(self.considered_ids)
        return tuple(item for item in self.staged_ids if item not in resolved)

    @property
    def batch_count(self) -> int:
        """回傳 deterministic batch 數量。"""

        return len(self.batches)

    def to_mapping(self) -> dict[str, object]:
        """輸出可放入 receipt/metrics 的 bounded sweep evidence。"""

        return {
            "identity_field": self.identity_field,
            "batch_count": self.batch_count,
            "staged_count": len(self.staged_ids),
            "decision_received_count": len(self.decision_received_ids),
            "selected_count": len(self.selected_ids),
            "unresolved_count": len(self.unresolved_ids),
            "semantic_coverage_status": "PARTIAL" if self.unresolved_ids else "COMPLETE",
            "considered_count": len(self.considered_ids),
            "never_considered_count": len(self.never_considered_ids),
            "batch_ids": [list(batch) for batch in self.batches],
            "fingerprint": self.fingerprint,
            "dispositions": {
                identity: ("selected" if identity in self.selected_ids else "not_selected" if identity in self.considered_ids else "needs_detail")
                for identity in self.decision_received_ids
            },
        }


def build_inventory_sweep(
    items: Sequence[Mapping[str, object]],
    *,
    identity_field: str,
    item_limit: int = DEFAULT_SWEEP_ITEM_LIMIT,
    byte_limit: int = DEFAULT_SWEEP_BYTE_LIMIT,
    scope_fingerprint: str | None = None,
) -> InventorySweep:
    """將所有已通過 deterministic gate 的 digest 排成 bounded batches。

    Python 只負責 canonical ordering、exact identity 去重驗證、byte budget 與
    batch 完整性；它不讀取 task 語意，也不決定任何 capability 是否 material。
    單一 digest 超過 byte budget 時仍獨立成 batch，避免靜默遺漏尾端能力。
    """

    if not isinstance(identity_field, str) or not identity_field.strip():
        raise ValueError("identity_field must be non-empty text")
    if isinstance(item_limit, bool) or not isinstance(item_limit, int) or item_limit <= 0:
        raise ValueError("item_limit must be a positive integer")
    if isinstance(byte_limit, bool) or not isinstance(byte_limit, int) or byte_limit <= 0:
        raise ValueError("byte_limit must be a positive integer")
    if scope_fingerprint is not None and (not isinstance(scope_fingerprint, str) or re.fullmatch(r"[0-9a-f]{64}", scope_fingerprint) is None):
        raise ValueError("scope fingerprint must be a SHA-256 digest")

    normalized: list[tuple[str, bytes]] = []
    seen: set[str] = set()
    for item in items:
        if not isinstance(item, Mapping):
            raise TypeError("inventory sweep items must be mappings")
        identity = item.get(identity_field)
        if not isinstance(identity, str) or _IDENTIFIER.fullmatch(identity) is None:
            raise ValueError("inventory sweep item requires a canonical identity")
        if identity in seen:
            raise ValueError("inventory sweep accepts exact identities only once")
        seen.add(identity)
        encoded = json.dumps(
            dict(item),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        normalized.append((identity, encoded))

    normalized.sort(key=lambda pair: (pair[0].casefold(), pair[0]))
    batches: list[tuple[str, ...]] = []
    current: list[str] = []
    current_bytes = 0
    for identity, encoded in normalized:
        item_bytes = len(encoded)
        if current and (len(current) >= item_limit or current_bytes + item_bytes > byte_limit):
            batches.append(tuple(current))
            current = []
            current_bytes = 0
        current.append(identity)
        current_bytes += item_bytes
    if current:
        batches.append(tuple(current))

    considered = tuple(identity for batch in batches for identity in batch)
    payload = {
        "identity_field": identity_field,
        "item_limit": item_limit,
        "byte_limit": byte_limit,
        "batches": [list(batch) for batch in batches],
        "digests": [encoded.decode("utf-8") for _, encoded in normalized],
        "scope_fingerprint": scope_fingerprint,
    }
    fingerprint = hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return InventorySweep(
        identity_field=identity_field,
        batches=tuple(batches),
        considered_ids=(),
        never_considered_ids=considered,
        fingerprint=fingerprint,
    )


def validate_sweep_decisions(
    sweep: InventorySweep,
    responses: Sequence[Mapping[str, object]],
    *,
    task_fingerprint: str,
    selected_ids: Sequence[str] = (),
) -> InventorySweep:
    """Validate Host dispositions; missing batches remain partial, never inferred."""

    if not isinstance(task_fingerprint, str) or re.fullmatch(r"[0-9a-f]{64}", task_fingerprint) is None:
        raise ValueError("decisions require a task context fingerprint")
    if isinstance(responses, (str, bytes)) or not isinstance(responses, Sequence):
        raise ValueError("batch decisions must be a sequence")
    selected = set(selected_ids)
    if not selected <= set(sweep.staged_ids):
        raise ValueError("selected IDs must belong to this sweep")
    seen: set[int] = set()
    decisions: dict[str, str] = {}
    for response in responses:
        if not isinstance(response, Mapping) or set(response) != {"task_fingerprint", "sweep_fingerprint", "batch_index", "dispositions"}:
            raise ValueError("invalid batch decision fields")
        if response["task_fingerprint"] != task_fingerprint or response["sweep_fingerprint"] != sweep.fingerprint:
            raise ValueError("batch decision task or snapshot is stale")
        index = response["batch_index"]
        if isinstance(index, bool) or not isinstance(index, int) or not 0 <= index < sweep.batch_count or index in seen:
            raise ValueError("invalid or duplicate batch index")
        dispositions = response["dispositions"]
        if not isinstance(dispositions, Mapping) or set(dispositions) != set(sweep.batches[index]):
            raise ValueError("batch dispositions must match every candidate exactly")
        for identity, disposition in dispositions.items():
            if not isinstance(disposition, str) or disposition not in {"selected", "not_selected", "needs_detail"}:
                raise ValueError("invalid candidate disposition")
            if (disposition == "selected") != (identity in selected):
                raise ValueError("candidate disposition conflicts with final selection")
        seen.add(index)
        decisions.update(dispositions)
    return replace(
        sweep,
        decision_received_ids=tuple(i for i in sweep.staged_ids if i in decisions),
        considered_ids=tuple(i for i in sweep.staged_ids if i in decisions and decisions[i] != "needs_detail"),
        never_considered_ids=tuple(i for i in sweep.staged_ids if i not in decisions),
        selected_ids=tuple(i for i in sweep.staged_ids if decisions.get(i) == "selected"),
    )


def skill_digest(profile: object) -> dict[str, object]:
    """建立 Skill first-pass digest；只保留可供 LLM 理解的短 public metadata。"""

    return {
        "id": profile.id,
        "name": profile.name,
        "description": profile.description,
        "status": profile.status.value,
        "source": profile.source,
        "provenance": list(profile.provenance),
        "fingerprint": profile.fingerprint,
    }


def provider_digest(provider: object) -> dict[str, object]:
    """將 Provider digest轉成 inventory sweep 的 public projection。"""

    return provider.to_mapping()
