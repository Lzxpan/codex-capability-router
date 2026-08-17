"""Phase 3 fixture/runtime registry 的 deterministic normalization helpers。"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace

from .models import CapabilityRecord, DiscoveryDiagnostic, DiscoveryResult


# 修改紀錄（2026-08-17，Steve Peng）
# 原始內容：registry 只有同 source 去重，跨 source claim 會直接並列且無 authority/provenance model。
# 修改原因：Phase 5R 要求 runtime > verified CLI > manual 的明確 precedence，並保留衝突證據；beta review 另指出同 source 去重不得遺失 evidence。
# 修改後功能：提供 bounded merge，runtime record 勝出、CLI 次之、manual 最後；保留 field-level conflict、provenance 與 evidence，不執行外部能力。


def classify_capability(record: CapabilityRecord) -> CapabilityRecord:
    """保留 fixture 明確 kind；未知 kind 不猜測，直接原樣返回。"""

    return record


def deduplicate_registry(records: Sequence[CapabilityRecord]) -> tuple[CapabilityRecord, ...]:
    """移除同 source、同 identifier 的重複 record，並合併可追溯 metadata。"""

    result: list[CapabilityRecord] = []
    positions: dict[tuple[str, str], int] = {}
    for record in records:
        key = (record.source, record.id)
        if key in positions:
            index = positions[key]
            result[index] = _merge_same_source_claims(result[index], record)
            continue
        positions[key] = len(result)
        result.append(classify_capability(record))
    return tuple(result)


def merge_capability_records(records: Sequence[CapabilityRecord]) -> DiscoveryResult:
    """依來源可信度合併同 identifier records，保留 provenance 與 conflict evidence。

    使用方式：傳入本次 runtime 的 records；source label 必須是 abstract label。
    precedence 固定為 runtime > cli > explicit skill root > manual；未知來源不猜測，
    與 manual 同級。這是 O(n) grouping；需要跨 runtime persistence 時才升級資料庫模型。
    """

    grouped: dict[str, list[CapabilityRecord]] = {}
    order: list[str] = []
    for record in records:
        if record.id not in grouped:
            grouped[record.id] = []
            order.append(record.id)
        grouped[record.id].append(record)

    merged: list[CapabilityRecord] = []
    diagnostics: list[DiscoveryDiagnostic] = []
    for capability_id in order:
        claims = grouped[capability_id]
        winner = max(enumerate(claims), key=lambda item: (_source_precedence(item[1].source), -item[0]))[1]
        provenance = _unique(value for claim in claims for value in (claim.source, *claim.provenance))
        evidence = _unique(value for claim in claims for value in claim.evidence)
        conflicts = _claim_conflicts(claims)
        if conflicts:
            diagnostics.append(
                DiscoveryDiagnostic(
                    "source_conflict",
                    "capability field conflict retained as evidence",
                    winner.source,
                )
            )
        merged.append(
            replace(
                winner,
                provenance=provenance,
                conflicts=conflicts,
                evidence=evidence,
            )
        )

    return DiscoveryResult(tuple(merged), tuple(diagnostics), partial=False)


def _source_precedence(source: str) -> int:
    """將已知 abstract source label 映射到固定 precedence，不猜測內容。"""

    normalized = source.casefold()
    if normalized.startswith("runtime") or normalized.startswith("runtime_envelope"):
        return 3
    if normalized.startswith("cli") or normalized.startswith("cli_probe"):
        return 2
    if normalized.startswith("skill-root") or normalized.startswith("explicit-skill-root"):
        return 1
    return 0


def _merge_same_source_claims(first: CapabilityRecord, second: CapabilityRecord) -> CapabilityRecord:
    """合併同 source 重複項，保留第一次欄位值與所有安全追溯 metadata。"""

    conflicts = _unique((*first.conflicts, *second.conflicts, *_claim_conflicts((first, second))))
    return replace(
        first,
        provenance=_unique((*first.provenance, *second.provenance, first.source, second.source)),
        conflicts=conflicts,
        evidence=_unique((*first.evidence, *second.evidence)),
    )


def _claim_conflicts(records: Sequence[CapabilityRecord]) -> tuple[str, ...]:
    """保留 bounded、非敏感欄位的差異，不輸出 raw path 或任意 metadata。"""

    fields = (
        ("status", lambda record: record.status.value),
        ("last_verified", lambda record: record.last_verified),
        ("version", lambda record: record.version),
        ("limitations", lambda record: record.limitations),
        ("confidence", lambda record: record.confidence),
        ("recommendation_only", lambda record: record.recommendation_only),
    )
    conflicts: list[str] = []
    for field, value_of in fields:
        values = [value_of(record) for record in records]
        if len(set(values)) <= 1:
            continue
        conflicts.extend(
            f"{record.source}.{field}={value_of(record)}"
            for record in records
        )
    return _unique(conflicts)


def _unique(values) -> tuple[str, ...]:
    """以第一次出現順序去重，確保 provenance 與 diagnostics deterministic。"""

    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return tuple(result)
