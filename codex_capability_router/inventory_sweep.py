"""高召回 inventory 的 deterministic batching contract。"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import hashlib
import json
import re


_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]*$")
DEFAULT_SWEEP_ITEM_LIMIT = 24
DEFAULT_SWEEP_BYTE_LIMIT = 24_000


@dataclass(frozen=True)
class InventorySweep:
    """完整 digest sweep 的公開證據；不包含語意排序或 semantic score。"""

    identity_field: str
    batches: tuple[tuple[str, ...], ...]
    considered_ids: tuple[str, ...]
    never_considered_ids: tuple[str, ...]
    fingerprint: str

    def __post_init__(self) -> None:
        """驗證 batches 完整覆蓋且每個 identity 只被考慮一次。"""

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
        if flattened != considered:
            raise ValueError("considered IDs must preserve deterministic batch order")
        if never:
            raise ValueError("completed inventory sweep cannot leave IDs unconsidered")
        if any(_IDENTIFIER.fullmatch(item) is None for item in (*considered, *never)):
            raise ValueError("sweep IDs must be canonical identifiers")
        if not isinstance(self.fingerprint, str) or not re.fullmatch(r"[0-9a-f]{64}", self.fingerprint):
            raise ValueError("sweep fingerprint must be a SHA-256 digest")
        object.__setattr__(self, "batches", batches)
        object.__setattr__(self, "considered_ids", considered)
        object.__setattr__(self, "never_considered_ids", never)

    @property
    def batch_count(self) -> int:
        """回傳 deterministic batch 數量。"""

        return len(self.batches)

    def to_mapping(self) -> dict[str, object]:
        """輸出可放入 receipt/metrics 的 bounded sweep evidence。"""

        return {
            "identity_field": self.identity_field,
            "batch_count": self.batch_count,
            "considered_count": len(self.considered_ids),
            "never_considered_count": len(self.never_considered_ids),
            "batch_ids": [list(batch) for batch in self.batches],
            "fingerprint": self.fingerprint,
        }


def build_inventory_sweep(
    items: Sequence[Mapping[str, object]],
    *,
    identity_field: str,
    item_limit: int = DEFAULT_SWEEP_ITEM_LIMIT,
    byte_limit: int = DEFAULT_SWEEP_BYTE_LIMIT,
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
    }
    fingerprint = hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return InventorySweep(
        identity_field=identity_field,
        batches=tuple(batches),
        considered_ids=considered,
        never_considered_ids=(),
        fingerprint=fingerprint,
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
    }


def provider_digest(provider: object) -> dict[str, object]:
    """將 Provider digest轉成 inventory sweep 的 public projection。"""

    return provider.to_mapping()
