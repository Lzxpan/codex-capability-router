"""Phase 3 deterministic classification、availability filter、deduplication 與 routing。"""

from __future__ import annotations

import re
import unicodedata

from .models import (
    CapabilityRecord,
    CapabilityStatus,
    RecommendationResult,
    RejectedCandidate,
    RouterInput,
    SelectionEvidence,
)
from .registry import merge_capability_records


# 修改紀錄（2026-08-17，Steve Peng）
# 原始內容：unknown record 會沿用 available/optional 分支，可能被正常推薦；rejected candidate 只保留 id/reason/status。
# 修改原因：Phase 5R 要求 unknown 排除 selected/recommendation，且 beta review 要求 rejected output 可追溯來源與衝突。
# 修改後功能：unknown 僅能進 recommendation_only advisory output；每個 rejected candidate 保留 source、provenance、confidence、conflicts。
# 修改紀錄（2026-08-18，Steve Peng）
# 原始內容：route result 只有 selected records，沒有可供 explanation renderer 使用的結構化 selection evidence。
# 修改原因：Phase 5D 需要 deterministic、auditable reason codes，且不得產生 hidden reasoning trace。
# 修改後功能：依既有 task/category/trigger/ranking evidence 產生 selection_evidence；不改變候選排序或 selection limits。

_TASK_ALIASES: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "firmware debugging",
        ("firmware", "韌體", "microcontroller", "mcu", "embedded", "嵌入式", "uart", "serial", "除錯"),
    ),
    (
        "react ui bug",
        ("react", "component", "元件", "frontend", "css"),
    ),
    (
        "pr code review",
        ("pull request", "pr", "code review", "程式碼審查", "拉取請求", "diff"),
    ),
    (
        "research document search",
        ("research", "研究", "document", "文件", "paper", "論文", "查資料"),
    ),
    (
        "spreadsheet data analysis",
        ("spreadsheet", "試算表", "csv", "excel", "資料分析", "data table"),
    ),
    (
        "ui ux design",
        ("user experience", "使用者體驗", "ux", "design", "設計", "prototype", "原型"),
    ),
)

_BROAD_TERMS = {
    "analysis",
    "bug",
    "code",
    "data",
    "debug",
    "design",
    "review",
    "search",
    "ui",
    "ux",
    "錯誤",
    "問題",
    "分析",
    "資料",
    "設計",
    "搜尋",
    "介面",
}

_PRIMARY_LEVEL = "PRIMARY"
_OPTIONAL_LEVEL = "OPTIONAL"
_RECOMMENDATION_ONLY_LEVEL = "RECOMMENDATION_ONLY"


def classify_task(user_task: str) -> tuple[str, ...]:
    """依固定 alias 表分類 user task，回傳穩定 canonical category tuple。"""

    normalized = _normalize(user_task)
    ranked: list[tuple[int, int, str]] = []
    for index, (category, aliases) in enumerate(_TASK_ALIASES):
        score = sum(_phrase_in_text(normalized, alias) for alias in aliases)
        if score:
            ranked.append((score, -index, category))
    ranked.sort(reverse=True)
    return tuple(category for _, _, category in ranked[:1])


def route(request: RouterInput) -> RecommendationResult:
    """以純函式規則產生 advisory recommendation，不執行、安裝或連線 capability。"""

    # 先套用 runtime authority 再做 relevance/ranking，避免 supplemental claim
    # 以競爭 record 形式進入 selected_primary/selected_optional。
    registry = merge_capability_records(request.capability_registry).records
    task = _normalize(request.user_task)
    task_categories = classify_task(request.user_task)
    rejected: list[RejectedCandidate] = []
    relevant: list[CapabilityRecord] = []
    recommendation_only: list[CapabilityRecord] = []

    for record in registry:
        if record.id.casefold() == "codex-capability-router":
            rejected.append(_rejected(record, "self-routing protection"))
            continue
        if record.status == CapabilityStatus.UNKNOWN:
            if record.recommendation_only and _trusted_recommendation_source(record.source) and _is_relevant(record, task, task_categories):
                recommendation_only.append(record)
            else:
                rejected.append(_rejected(record, "unknown capability"))
            continue
        if not _is_relevant(record, task, task_categories):
            continue
        if record.status == CapabilityStatus.UNAVAILABLE:
            rejected.append(_rejected(record, "unavailable"))
            continue
        relevant.append(record)

    ranked = sorted(relevant, key=lambda record: _ranking_key(record, task, task_categories))
    winners: list[CapabilityRecord] = []
    overlap_winners: dict[str, CapabilityRecord] = {}
    for record in ranked:
        group = record.overlap_group
        if group and group in overlap_winners:
            rejected.append(
                _rejected(record, f"redundant overlap_group: {group}")
            )
            continue
        if group:
            overlap_winners[group] = record
        winners.append(record)

    primary = tuple(record for record in winners if record.status == CapabilityStatus.INSTALLED)[:3]
    optional = tuple(record for record in winners if record.status != CapabilityStatus.INSTALLED)[:2]
    selected_ids = {record.id for record in primary + optional}

    for record in winners:
        if record.id in selected_ids:
            continue
        reason = "primary selection limit" if record.status == CapabilityStatus.INSTALLED else "optional selection limit"
        rejected.append(_rejected(record, reason))

    rejected.sort(key=lambda item: (item.id.casefold(), item.id, item.reason))
    recommendation_only.sort(key=lambda record: _ranking_key(record, task, task_categories))
    recommendation_records = tuple(recommendation_only)
    selection_evidence = tuple(
        _selection_evidence(record, _PRIMARY_LEVEL, task, task_categories)
        for record in primary
    ) + tuple(
        _selection_evidence(record, _OPTIONAL_LEVEL, task, task_categories)
        for record in optional
    ) + tuple(
        _selection_evidence(record, _RECOMMENDATION_ONLY_LEVEL, task, task_categories)
        for record in recommendation_records
    )
    rationale = _rationale(request, task_categories, primary, optional, recommendation_records)
    return RecommendationResult(primary, optional, tuple(rejected), rationale, recommendation_records, selection_evidence)


def _rejected(record: CapabilityRecord, reason: str) -> RejectedCandidate:
    """建立帶 provenance 的 rejected candidate，避免 routing diagnostics 失去來源。"""

    return RejectedCandidate(
        record.id,
        reason,
        record.status,
        source=record.source,
        provenance=record.provenance,
        confidence=record.confidence,
        conflicts=record.conflicts,
    )


def _trusted_recommendation_source(source: str) -> bool:
    """只信任明確 runtime 或 manual inventory source 的 recommendation-only 標記。"""

    normalized = source.casefold()
    return normalized.startswith("runtime") or normalized.startswith("manual")


def _is_relevant(record: CapabilityRecord, task: str, task_categories: tuple[str, ...]) -> bool:
    """只保留類別、preferred_for 或非 broad trigger 真正命中的候選。"""

    normalized_categories = {_normalize(value) for value in record.categories}
    normalized_preferred = {_normalize(value) for value in record.preferred_for}
    if set(task_categories) & normalized_categories or set(task_categories) & normalized_preferred:
        return True

    for value in (*record.categories, *record.preferred_for, *record.triggers):
        normalized_value = _normalize(value)
        if normalized_value in _BROAD_TERMS:
            continue
        if _phrase_in_text(task, normalized_value):
            return True
    return False


def _ranking_key(
    record: CapabilityRecord,
    task: str,
    task_categories: tuple[str, ...],
) -> tuple[int, int, int, int, int, int, str, str]:
    """建立固定排序 tuple：exact、specialist、installed、preferred、evidence、priority、id。"""

    exact = int(any(_phrase_in_text(task, trigger) for trigger in record.triggers))
    specialist = int(not _is_generic(record))
    installed = int(record.status == CapabilityStatus.INSTALLED)
    preferred = int(
        any(
            _normalize(value) in {_normalize(category) for category in task_categories}
            or _phrase_in_text(task, value)
            for value in record.preferred_for
        )
    )
    evidence = sum(
        _phrase_in_text(task, value)
        for value in (*record.categories, *record.triggers)
        if _normalize(value) not in _BROAD_TERMS
    )
    return (-exact, -specialist, -installed, -preferred, -evidence, -record.priority, record.id.casefold(), record.id)


def _is_generic(record: CapabilityRecord) -> bool:
    """辨識 fixture 明確標示的 generic capability，不猜測 vendor 類型。"""

    values = (record.id, record.name, *record.categories)
    return any("generic" in _normalize(value) or "general" in _normalize(value) for value in values)


def _selection_evidence(
    record: CapabilityRecord,
    selection_level: str,
    task: str,
    task_categories: tuple[str, ...],
) -> SelectionEvidence:
    """由既有 match evidence 建立 bounded reason codes，不建立 scoring 或 reasoning trace。"""

    matched_triggers = tuple(
        trigger for trigger in record.triggers if _phrase_in_text(task, trigger)
    )
    matched_requirements = _unique_text(
        value
        for value in (*record.preferred_for, *record.categories)
        if _normalize(value) in task_categories
    )
    reason_codes: list[str] = []
    if _phrase_in_text(task, record.id) or _phrase_in_text(task, record.name):
        reason_codes.append("explicit_request")
    if matched_triggers:
        reason_codes.append("exact_trigger_match")
    if not _is_generic(record):
        reason_codes.append("specialist_match")
    if matched_requirements:
        reason_codes.append("requirement_coverage")
    if record.status in {CapabilityStatus.INSTALLED, CapabilityStatus.AVAILABLE}:
        reason_codes.append("installed_available")
    if record.source.casefold().startswith(("skill-root", "explicit-skill-root")):
        reason_codes.append("workspace_specific")
    if record.overlap_group and matched_requirements:
        reason_codes.append("preferred_overlap_member")
    if selection_level == _OPTIONAL_LEVEL:
        reason_codes.append("complementary_optional")
    if not reason_codes:
        reason_codes.append("fallback")
    return SelectionEvidence(
        capability_id=record.id,
        selection_level=selection_level,
        reason_codes=tuple(reason_codes),
        matched_triggers=matched_triggers,
        matched_requirements=matched_requirements,
    )


def _unique_text(values) -> tuple[str, ...]:
    """依第一次出現順序去重 matched evidence，保持 machine result deterministic。"""

    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return tuple(result)


def _rationale(
    request: RouterInput,
    task_categories: tuple[str, ...],
    primary: tuple[CapabilityRecord, ...],
    optional: tuple[CapabilityRecord, ...],
    recommendation_only: tuple[CapabilityRecord, ...] = (),
) -> str:
    """產生短且可追溯的 rationale，包含 task category、選擇與 provenance。"""

    category_text = ", ".join(task_categories) if task_categories else "no classified category"
    selected = primary + optional
    if not selected and not recommendation_only:
        return f"No suitable capability matched task category: {category_text}."
    evidence = ", ".join(
        f"{record.id} ({record.status.value}, source={record.source})" for record in selected
    )
    if recommendation_only:
        advisory = ", ".join(record.id for record in recommendation_only)
        evidence = f"{evidence}; recommendation-only: {advisory}" if evidence else f"recommendation-only: {advisory}"
    return f"Matched task category: {category_text}; selected: {evidence}."


def _normalize(value: str) -> str:
    """以 Unicode NFKC 與 casefold 固定中英文文字比對形式。"""

    return unicodedata.normalize("NFKC", value).casefold().strip()


def _phrase_in_text(text: str, phrase: str) -> bool:
    """做不依賴外部 NLP 的 bounded phrase match；中英文均使用 normalized substring。"""

    candidate = _normalize(phrase)
    if not candidate:
        return False
    # ponytail: 兩字元 ASCII trigger 只接受單字邊界，避免 pr 命中 prototype；
    # 需要完整 tokenizer 或語意模型時才升級這個 bounded matcher。
    if len(candidate) <= 2 and candidate.isascii() and candidate.isalnum():
        return re.search(rf"(?<![a-z0-9]){re.escape(candidate)}(?![a-z0-9])", text) is not None
    return candidate in text
