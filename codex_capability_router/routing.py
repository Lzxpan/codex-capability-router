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
# 修改紀錄（2026-08-18，Steve Peng）
# 原始內容：self-routing 只比對單一 codex-capability-router ID，route-only 也沒有 execution metadata。
# 修改原因：Phase 5E 要排除 controller/aliases/internal support，且 execution permission 不得改變 target-task selection。
# 修改後功能：以固定 controller aliases 與 routing_support filter 保護 downstream set，並只回傳 execution_allowed metadata。
# 修改紀錄（2026-08-19，Steve Peng）
# 原始內容：relevance/ranking 只消費固定 categories、preferred_for 與 triggers，description/provides 無法覆蓋非程式 artifact requirement。
# 修改原因：Phase 5F 發現 capability 已被 discovery/normalization 保留，但 document/image/PDF task 會因 generic metadata 未參與 routing 而落空。
# 修改後功能：以 record 的 description/provides 擴充 generic relevance、ranking 與 bounded selection evidence；source 不參與 role 判定。
# 修改紀錄（2026-08-19，Steve Peng）
# 原始內容：routing 只有 topic-based relevance，explicit request、action requirement 與 execution constraint 不會影響 hard gate 或結果語意。
# 修改原因：Phase 5G-B 必須先排除 controller/unsafe/incompatible candidate，再依 explicit、action、trigger 與 specificity 排序。
# 修改後功能：加入 bounded structured intent routing、native-model outcome、constraint pass-through 與獨立 controller identity；保留無 structured input 時的 topic fallback。

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
_CONTROLLER_ALIASES = frozenset(
    {
        "codex-capability-router",
        "codex capability router",
        "codex-router",
        "codex router",
        "capability-router",
        "capability router",
    }
)
_NATIVE_MODEL_ACTIONS = frozenset({"rewrite_text", "generate_text"})


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
    router_controller_ids: list[str] = []

    for record in registry:
        explicit_match = _matches_explicit_request(record, request.explicit_requests)
        topic_relevant = _is_relevant(record, task, task_categories)
        if _is_controller(record):
            router_controller_ids.append(record.id)
            rejected.append(_rejected(record, "self-routing protection"))
            continue
        if record.routing_support:
            # ponytail: internal support 完全不進 output；需要獨立 support trace 時才新增 routing_support section。
            continue
        if record.status == CapabilityStatus.UNKNOWN:
            if record.recommendation_only and _trusted_recommendation_source(record.source) and (
                explicit_match or topic_relevant or _is_relevant(record, task, task_categories, request.action_requirements)
            ):
                recommendation_only.append(record)
            elif explicit_match or topic_relevant:
                rejected.append(_rejected(record, "unknown capability"))
            continue
        if record.status == CapabilityStatus.UNAVAILABLE:
            if explicit_match or topic_relevant:
                rejected.append(_rejected(record, "unavailable"))
            continue
        if not _action_compatible(record, request.action_requirements):
            if explicit_match or topic_relevant:
                rejected.append(_rejected(record, "action incompatibility"))
            continue
        if not explicit_match and not _is_relevant(record, task, task_categories, request.action_requirements):
            continue
        relevant.append(record)

    ranked = sorted(
        relevant,
        key=lambda record: _ranking_key(
            record,
            task,
            task_categories,
            request.explicit_requests,
            request.action_requirements,
        ),
    )
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
    recommendation_only.sort(
        key=lambda record: _ranking_key(
            record,
            task,
            task_categories,
            request.explicit_requests,
            request.action_requirements,
        )
    )
    recommendation_records = tuple(recommendation_only)
    outcome = _routing_outcome(request, primary, optional, recommendation_records)
    selection_evidence = tuple(
        _selection_evidence(
            record,
            _PRIMARY_LEVEL,
            task,
            task_categories,
            request.explicit_requests,
            request.action_requirements,
            request.execution_constraints,
        )
        for record in primary
    ) + tuple(
        _selection_evidence(
            record,
            _OPTIONAL_LEVEL,
            task,
            task_categories,
            request.explicit_requests,
            request.action_requirements,
            request.execution_constraints,
        )
        for record in optional
    ) + tuple(
        _selection_evidence(
            record,
            _RECOMMENDATION_ONLY_LEVEL,
            task,
            task_categories,
            request.explicit_requests,
            request.action_requirements,
            request.execution_constraints,
        )
        for record in recommendation_records
    )
    rationale = _rationale(request, task_categories, primary, optional, recommendation_records, outcome)
    return RecommendationResult(
        primary,
        optional,
        tuple(rejected),
        rationale,
        recommendation_records,
        selection_evidence,
        execution_allowed=request.execution_allowed,
        outcome=outcome,
        execution_constraints=request.execution_constraints,
        router_controller_ids=tuple(sorted(router_controller_ids, key=lambda value: (value.casefold(), value))),
    )


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


def _is_controller(record: CapabilityRecord) -> bool:
    """辨識明確 controller flag 與固定 Router aliases，永久排除 downstream selection。"""

    if record.controller:
        return True
    identifiers = (record.id, record.name, *record.aliases)
    return any(_normalize(value) in _CONTROLLER_ALIASES for value in identifiers)


def _is_relevant(
    record: CapabilityRecord,
    task: str,
    task_categories: tuple[str, ...],
    action_requirements: tuple[str, ...] = (),
) -> bool:
    """只保留類別、preferred_for 或非 broad trigger 真正命中的候選。"""

    if action_requirements:
        return _action_compatible(record, action_requirements)

    normalized_categories = {_normalize(value) for value in record.categories}
    normalized_preferred = {_normalize(value) for value in record.preferred_for}
    if set(task_categories) & normalized_categories or set(task_categories) & normalized_preferred:
        return True

    for value in (*record.categories, *record.preferred_for, *record.triggers, *record.provides):
        normalized_value = _normalize(value)
        if normalized_value in _BROAD_TERMS:
            continue
        if _phrase_in_text(task, normalized_value):
            return True
    if record.description and _phrase_in_text(task, record.description):
        return True
    return False


def _ranking_key(
    record: CapabilityRecord,
    task: str,
    task_categories: tuple[str, ...],
    explicit_requests: tuple[str, ...] = (),
    action_requirements: tuple[str, ...] = (),
) -> tuple[int, int, int, int, int, int, int, int, int, str, str]:
    """依 explicit、action、trigger、specificity、availability、preferred、priority、ID 固定排序。"""

    explicit = int(_matches_explicit_request(record, explicit_requests))
    action_coverage = len(_action_coverage(record, action_requirements))
    exact = int(
        any(_phrase_in_text(task, value) for value in (*record.triggers, *record.provides))
    )
    specialist = int(not _is_generic(record))
    workspace_specific = int(record.source.casefold().startswith(("skill-root", "explicit-skill-root")))
    available = int(record.status == CapabilityStatus.INSTALLED)
    preferred = int(
        any(
            _normalize(value) in {_normalize(category) for category in task_categories}
            or _phrase_in_text(task, value)
            for value in record.preferred_for
        )
    )
    evidence = sum(
        _phrase_in_text(task, value)
        for value in (*record.categories, *record.triggers, *record.provides)
        if _normalize(value) not in _BROAD_TERMS
    )
    return (
        -explicit,
        -action_coverage,
        -exact,
        -specialist,
        -workspace_specific,
        -available,
        -preferred,
        -evidence,
        -record.priority,
        record.id.casefold(),
        record.id,
    )


def _is_generic(record: CapabilityRecord) -> bool:
    """辨識 fixture 明確標示的 generic capability，不猜測 vendor 類型。"""

    values = (record.id, record.name, *record.categories)
    return any("generic" in _normalize(value) or "general" in _normalize(value) for value in values)


def _selection_evidence(
    record: CapabilityRecord,
    selection_level: str,
    task: str,
    task_categories: tuple[str, ...],
    explicit_requests: tuple[str, ...] = (),
    action_requirements: tuple[str, ...] = (),
    execution_constraints: tuple[str, ...] = (),
) -> SelectionEvidence:
    """由既有 match evidence 建立 bounded reason codes，不建立 scoring 或 reasoning trace。"""

    matched_triggers = tuple(
        trigger for trigger in record.triggers if _phrase_in_text(task, trigger)
    )
    matched_provides = tuple(
        value for value in record.provides if _phrase_in_text(task, value)
    )
    matched_requirements = _unique_text(
        value
        for value in (*action_requirements, *record.preferred_for, *record.categories, *matched_provides)
        if _normalize(value) in task_categories
        or value in action_requirements
        or value in matched_provides
    )
    reason_codes: list[str] = []
    if _matches_explicit_request(record, explicit_requests) or _phrase_in_text(task, record.id) or _phrase_in_text(task, record.name):
        reason_codes.append("explicit_request")
    if _action_coverage(record, action_requirements):
        reason_codes.append("action_requirement_coverage")
    if matched_triggers:
        reason_codes.append("exact_trigger_match")
    if matched_provides:
        reason_codes.append("provides_match")
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
        constraint_preserved=execution_constraints,
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
    outcome: str = "no_safe_match",
) -> str:
    """產生短且可追溯的 rationale，包含 task category、選擇與 provenance。"""

    category_text = ", ".join(task_categories) if task_categories else "no classified category"
    selected = primary + optional
    if not selected and not recommendation_only:
        if outcome == "native_model_sufficient":
            return "Native model is sufficient for this task."
        return f"No suitable capability matched task category: {category_text}."
    evidence = ", ".join(
        f"{record.id} ({record.status.value}, source={record.source})" for record in selected
    )
    if recommendation_only:
        advisory = ", ".join(record.id for record in recommendation_only)
        evidence = f"{evidence}; recommendation-only: {advisory}" if evidence else f"recommendation-only: {advisory}"
    return f"Matched task category: {category_text}; selected: {evidence}."


def _matches_explicit_request(record: CapabilityRecord, explicit_requests: tuple[str, ...]) -> bool:
    """以 canonical ID/name/alias 比對 explicit request，不讀取 private metadata。"""

    requested = {_normalize(value) for value in explicit_requests}
    return bool(requested & {_normalize(value) for value in (record.id, record.name, *record.aliases)})


def _action_coverage(record: CapabilityRecord, action_requirements: tuple[str, ...]) -> tuple[str, ...]:
    """只以 record.provides 的 exact canonical token 計算 action coverage。"""

    provided = {_normalize(value) for value in record.provides}
    return tuple(action for action in action_requirements if _normalize(action) in provided)


def _action_compatible(record: CapabilityRecord, action_requirements: tuple[str, ...]) -> bool:
    """確認 capability 覆蓋全部 bounded action requirements；沒有 action 時保留 topic fallback。"""

    return not action_requirements or len(_action_coverage(record, action_requirements)) == len(action_requirements)


def _routing_outcome(
    request: RouterInput,
    primary: tuple[CapabilityRecord, ...],
    optional: tuple[CapabilityRecord, ...],
    recommendation_only: tuple[CapabilityRecord, ...],
) -> str:
    """將空選擇區分為 native-model sufficient 與 no-safe-match。"""

    if primary or optional:
        return "downstream_selected"
    if (
        not request.explicit_requests
        and not recommendation_only
        and request.action_requirements
        and set(request.action_requirements) <= _NATIVE_MODEL_ACTIONS
    ):
        return "native_model_sufficient"
    return "no_safe_match"


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
