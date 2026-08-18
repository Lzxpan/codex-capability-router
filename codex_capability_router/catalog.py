"""Phase 4 deterministic bilingual catalog 與 user-facing output。"""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from dataclasses import dataclass
import json
from pathlib import Path

from .models import CapabilityRecord, RecommendationResult, SelectionEvidence
from .validation import record_from_mapping


# 修改紀錄（2026-08-17，Steve Peng）
# 原始內容：Phase 3 只有 canonical registry 與 English rationale，沒有 catalog/output localization。
# 修改原因：依 Phase 4 要求以單一 registry 產生兩份 Markdown，並支援 en、zh-TW、auto；Phase 5R
# 另要求 unknown recommendation-only 不得混入 selected output，beta review 要求 recommendation/rejection 保留 provenance。
# 修改後功能：固定 labels/templates、canonical ID ordering、UTF-8 output，且明確分離 advisory-only 區段與 traceability metadata。
# 修改紀錄（2026-08-18，Steve Peng）
# 原始內容：render_recommendations 只有 primary/optional ID 清單，沒有 selected capability explanation。
# 修改原因：Phase 5D 需要雙語、短句、可稽核且不暴露 chain-of-thought 的 Function/Why selected output。
# 修改後功能：依 registry Function metadata 與 route selection_evidence 渲染 selected skills、其他 capability、no-match 與 recommendation-only 區段。
# 修改紀錄（2026-08-18，Steve Peng）
# 原始內容：route-only result 沒有 user-facing execution suppression 說明。
# 修改原因：Phase 5E 必須清楚表達 selected 不等於 executed，且不把 internal support 混入 selected output。
# 修改後功能：只在 execution_allowed=false 時加入簡短 route-only 說明，不新增 execution engine。

SUPPORTED_LANGUAGES = ("en", "zh-TW", "auto")

_LABELS = {
    "en": {
        "name": "Name",
        "kind": "Kind",
        "status": "Status",
        "category": "Category",
        "purpose": "Primary Purpose",
        "use_when": "Use When",
        "avoid_when": "Avoid When",
        "overlap": "Overlap Group",
        "priority": "Priority",
        "primary": "Primary",
        "optional": "Optional",
        "selected_capabilities": "Selected Capabilities",
        "selected_skills": "Selected Skills",
        "other_selected_capabilities": "Other Selected Capabilities",
        "selection_level": "Selection level",
        "function": "Function",
        "why_selected": "Why selected",
        "why_considered": "Why considered",
        "recommendation_only": "Recommended but not selected",
        "not_executable": "Not selected as an executable capability.",
        "not_automatic": "It will not be installed or executed automatically.",
        "no_safe_match": "No suitable installed and safely usable capability was found.",
        "no_evidence": "No deterministic routing evidence was recorded.",
        "execution_suppressed": "Execution: not performed because this request is route-only.",
        "rejected": "Rejected Candidates",
        "rationale": "Rationale",
        "no_recommendation": "No recommendation available.",
        "matched": "Matched categories",
        "selected": "selected",
        "unavailable": "Unavailable",
        "redundant": "Redundant overlap group",
        "self_routing": "Self-routing protection",
    },
    "zh-TW": {
        "name": "名稱",
        "kind": "類型",
        "status": "狀態",
        "category": "類別",
        "purpose": "主要用途",
        "use_when": "適用時機",
        "avoid_when": "避免時機",
        "overlap": "重疊群組",
        "priority": "優先級",
        "primary": "主要建議",
        "optional": "可選建議",
        "selected_capabilities": "已選能力",
        "selected_skills": "已選技能",
        "other_selected_capabilities": "其他已選能力",
        "selection_level": "選擇層級",
        "function": "功能",
        "why_selected": "選用理由",
        "why_considered": "考慮理由",
        "recommendation_only": "建議但未選用",
        "not_executable": "尚未被選為可執行能力。",
        "not_automatic": "不會自動安裝，也不會自動執行。",
        "no_safe_match": "目前沒有找到符合條件且可安全使用的已安裝能力。",
        "no_evidence": "目前沒有記錄可稽核的路由證據。",
        "execution_suppressed": "執行：此請求為只路由模式，因此未執行。",
        "rejected": "拒絕候選",
        "rationale": "理由",
        "no_recommendation": "目前沒有可用的建議。",
        "matched": "符合類別",
        "selected": "選擇",
        "unavailable": "無法使用",
        "redundant": "重疊群組中的冗餘候選",
        "self_routing": "防止 Router 自我路由",
    },
}

_CATEGORY_LABELS = {
    "capability routing": "能力路由",
    "router": "Router 路由器",
    "firmware debugging": "韌體除錯",
    "firmware": "韌體",
    "debugging": "除錯",
    "react ui bug": "React 介面錯誤",
    "react": "React",
    "ui": "UI 介面",
    "pr code review": "PR 程式碼審查",
    "code review": "程式碼審查",
    "review": "審查",
    "research document search": "研究文件搜尋",
    "research": "研究",
    "document search": "文件搜尋",
    "search": "搜尋",
    "spreadsheet data analysis": "試算表資料分析",
    "spreadsheet": "試算表",
    "data analysis": "資料分析",
    "ui ux design": "UI/UX 設計",
    "ux": "UX 使用者體驗",
    "design": "設計",
    "generic": "通用",
}


@dataclass(frozen=True)
class CatalogBundle:
    """同一 canonical registry 的英文與繁中 Markdown catalog。"""

    en: str
    zh_tw: str


def generate_catalog(registry: Sequence[CapabilityRecord]) -> CatalogBundle:
    """以單一 registry 產生相同 ID/order 的英文與 zh-TW catalog。"""

    records = _ordered_records(registry)
    return CatalogBundle(
        en=_render_catalog(records, "en"),
        zh_tw=_render_catalog(records, "zh-TW"),
    )


def render_recommendations(
    result: RecommendationResult,
    *,
    language: str = "en",
    user_request: str = "",
) -> str:
    """渲染 Router recommendation；auto 依 user request 判斷語言，無法判定時用英文。"""

    locale = resolve_language(language, user_request)
    labels = _LABELS[locale]
    selected = result.selected_primary + result.selected_optional
    lines = [
        "# Capability Recommendations" if locale == "en" else "# Capability 建議",
        "",
    ]
    lines.extend(_render_selected_explanations(result, locale))
    if not result.execution_allowed:
        lines.extend(["", labels["execution_suppressed"]])
    lines.extend([
        "",
        f"## {labels['primary']}",
    ])
    if result.selected_primary:
        lines.extend(_recommendation_lines(result.selected_primary))
    else:
        lines.append(f"- {labels['no_recommendation']}")

    lines.extend(["", f"## {labels['optional']}"])
    if result.selected_optional:
        lines.extend(_recommendation_lines(result.selected_optional))
    else:
        lines.append("- None" if locale == "en" else "- 無")

    if result.recommendation_only:
        lines.extend(["", f"## {labels['recommendation_only']}"])
        lines.extend(_render_recommendation_only_lines(result, locale))

    if result.rejected_candidates:
        lines.extend(["", f"## {labels['rejected']}"])
        lines.extend(
            f"- `{candidate.id}` — {_localized_rejection(candidate.reason, locale)}"
            f" (source: {candidate.source or 'unknown'}; provenance: {', '.join(candidate.provenance) or 'none'})"
            for candidate in result.rejected_candidates
        )

    lines.extend(["", f"{labels['rationale']}：" if locale == "zh-TW" else f"{labels['rationale']}: "])
    if selected:
        categories = _display_categories(selected, locale)
        ids = ", ".join(record.id for record in selected)
        if locale == "en":
            lines.append(f"{labels['matched']}: {categories}; {labels['selected']}: {ids}.")
        else:
            lines.append(f"{labels['matched']}：{categories}；{labels['selected']}：{ids}。")
    else:
        lines.append(labels["no_recommendation"])
    return "\n".join(lines) + "\n"


def resolve_language(language: str, user_request: str = "") -> str:
    """驗證 en/zh-TW/auto，並將 auto 映射為 zh-TW 或保守英文。"""

    if language not in SUPPORTED_LANGUAGES:
        accepted = ", ".join(SUPPORTED_LANGUAGES)
        raise ValueError(f"language must be one of: {accepted}")
    if language != "auto":
        return language
    return "zh-TW" if any("\u4e00" <= character <= "\u9fff" for character in user_request) else "en"


def write_catalog(bundle: CatalogBundle, *, output_dir: Path) -> tuple[Path, Path]:
    """寫出固定檔名 CATALOG.en.md 與 CATALOG.zh-TW.md，回傳英文、繁中路徑。"""

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    english_path = output_dir / "CATALOG.en.md"
    zh_tw_path = output_dir / "CATALOG.zh-TW.md"
    _write_utf8(english_path, bundle.en)
    _write_utf8(zh_tw_path, bundle.zh_tw)
    return english_path, zh_tw_path


def load_registry(path: Path) -> tuple[CapabilityRecord, ...]:
    """讀取單一 JSON registry fixture 並套用既有 canonical boundary validation。"""

    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError("registry must be a JSON array")
    return tuple(record_from_mapping(item) for item in payload)


def main(argv: Sequence[str] | None = None) -> int:
    """提供 bounded local catalog generator，不執行 capability 或呼叫網路服務。"""

    parser = argparse.ArgumentParser(description="Generate bilingual Codex capability catalogs")
    parser.add_argument("--input", required=True, type=Path, help="canonical JSON registry")
    parser.add_argument("--output", default=Path("docs"), type=Path, help="output directory")
    arguments = parser.parse_args(argv)
    write_catalog(generate_catalog(load_registry(arguments.input)), output_dir=arguments.output)
    return 0


def _ordered_records(registry: Sequence[CapabilityRecord]) -> tuple[CapabilityRecord, ...]:
    """依 canonical ID 排序且不建立語言副本。"""

    return tuple(sorted(registry, key=lambda record: (record.id.casefold(), record.id)))


def _render_catalog(records: Sequence[CapabilityRecord], locale: str) -> str:
    """以固定欄位渲染完整 catalog；ID、enum、overlap key 不翻譯。"""

    if locale == "en":
        lines = [
            "# Codex Capability Router Catalog",
            "",
            "Generated from one canonical registry. Capability IDs and enum values are unchanged.",
        ]
    else:
        lines = [
            "# Codex Capability Router Catalog（繁體中文）",
            "",
            "由單一 canonical registry 產生。Capability ID 與 enum value 保持不變。",
        ]
    for record in records:
        labels = _LABELS[locale]
        lines.extend(
            [
                "",
                f"## Capability: `{record.id}`",
                "",
                f"- ID: {record.id}",
                f"- {labels['name']}: {record.name}",
                f"- {labels['kind']}: {record.kind.value}",
                f"- {labels['status']}: {record.status.value}",
                f"- {labels['category']}: {_display_categories((record,), locale)}",
                f"- {labels['purpose']}: {_primary_purpose(record, locale)}",
                f"- {labels['use_when']}: {_use_when(record, locale)}",
                f"- {labels['avoid_when']}: {_avoid_when(record, locale)}",
                f"- {labels['overlap']}: {record.overlap_group if record.overlap_group is not None else 'null'}",
                f"- {labels['priority']}: {record.priority}",
            ]
        )
    return "\n".join(lines) + "\n"


def _recommendation_lines(records: Sequence[CapabilityRecord]) -> list[str]:
    """輸出 recommendation 的 ID/name/status 與 bounded provenance metadata。"""

    lines: list[str] = []
    for record in records:
        provenance = ", ".join(record.provenance) or record.source
        details = f"status: {record.status.value}; source: {record.source}; provenance: {provenance}"
        if record.confidence is not None:
            details += f"; confidence: {record.confidence:g}"
        if record.conflicts:
            details += f"; conflicts: {', '.join(record.conflicts)}"
        lines.append(f"- `{record.id}` — {record.name} ({details})")
    return lines


def _render_selected_explanations(result: RecommendationResult, locale: str) -> list[str]:
    """渲染 selected capability explanation，依 kind 與 PRIMARY/OPTIONAL 分組。"""

    labels = _LABELS[locale]
    selected_pairs = tuple(
        [(record, "PRIMARY") for record in result.selected_primary]
        + [(record, "OPTIONAL") for record in result.selected_optional]
    )
    lines = [f"## {labels['selected_capabilities']}"]
    if not selected_pairs:
        lines.append(f"- {labels['no_safe_match']}")
        return lines

    evidence_by_id = {item.capability_id: item for item in result.selection_evidence}
    skill_pairs = tuple(pair for pair in selected_pairs if pair[0].kind.value == "skill")
    other_pairs = tuple(pair for pair in selected_pairs if pair[0].kind.value != "skill")
    if skill_pairs:
        lines.extend([f"### {labels['selected_skills']}", *_render_selected_group(skill_pairs, evidence_by_id, locale)])
    if other_pairs:
        lines.extend([
            f"### {labels['other_selected_capabilities']}",
            *_render_selected_group(other_pairs, evidence_by_id, locale),
        ])
    return lines


def _render_selected_group(
    pairs: Sequence[tuple[CapabilityRecord, str]],
    evidence_by_id: dict[str, SelectionEvidence],
    locale: str,
) -> list[str]:
    """渲染單一 kind group 的 level、Function 與 bounded routing rationale。"""

    labels = _LABELS[locale]
    separator = "：" if locale == "zh-TW" else ": "
    lines: list[str] = []
    for level in ("PRIMARY", "OPTIONAL"):
        level_pairs = tuple(pair for pair in pairs if pair[1] == level)
        if not level_pairs:
            continue
        lines.extend([f"#### {level}", ""])
        for record, selection_level in level_pairs:
            evidence = evidence_by_id.get(record.id)
            lines.extend(
                [
                    f"- {labels['name']}{separator}{record.name}",
                    f"  {labels['kind']}{separator}{record.kind.value}",
                    f"  {labels['selection_level']}{separator}{selection_level}",
                    f"  {labels['function']}{separator}{_function_text(record, locale)}",
                    f"  {labels['why_selected']}{separator}{_selection_why(record, evidence, locale)}",
                    "",
                ]
            )
    return lines[:-1] if lines and lines[-1] == "" else lines


def _render_recommendation_only_lines(result: RecommendationResult, locale: str) -> list[str]:
    """渲染 advisory-only capability，明確表示它不是 executable selection。"""

    labels = _LABELS[locale]
    separator = "：" if locale == "zh-TW" else ": "
    evidence_by_id = {item.capability_id: item for item in result.selection_evidence}
    lines: list[str] = []
    for record in result.recommendation_only:
        evidence = evidence_by_id.get(record.id)
        lines.extend(
            [
                f"- {labels['name']}{separator}{record.name}",
                f"  {labels['kind']}{separator}{record.kind.value}",
                f"  {labels['function']}{separator}{_function_text(record, locale)}",
                f"  {labels['why_considered']}{separator}{_selection_why(record, evidence, locale)}",
                f"  {labels['not_executable']}",
                f"  {labels['not_automatic']}",
                "",
            ]
        )
    return lines[:-1] if lines and lines[-1] == "" else lines


def _function_text(record: CapabilityRecord, locale: str) -> str:
    """只讀取 canonical Function metadata；缺少 locale 值時使用明確 fallback。"""

    return record.function_for(locale) or (
        "目前沒有足夠的功能說明資料。"
        if locale == "zh-TW"
        else "Function information unavailable."
    )


def _selection_why(
    record: CapabilityRecord,
    evidence: SelectionEvidence | None,
    locale: str,
) -> str:
    """將既有 reason codes 轉成最多兩句 user-facing rationale，不生成 hidden reasoning。"""

    if evidence is None:
        return _LABELS[locale]["no_evidence"]
    messages = [
        message
        for code in evidence.reason_codes
        if (message := _reason_message(code, record, evidence, locale))
    ]
    return " ".join(messages[:2]) or _LABELS[locale]["no_evidence"]


def _reason_message(
    code: str,
    record: CapabilityRecord,
    evidence: SelectionEvidence,
    locale: str,
) -> str:
    """以固定 code/template 產生短理由；未知 code 不自行猜測文字。"""

    if locale == "zh-TW":
        if code == "explicit_request":
            return "任務明確提出此能力。"
        if code == "exact_trigger_match":
            return f"任務符合觸發詞：{'、'.join(evidence.matched_triggers)}。"
        if code == "specialist_match":
            return "它是符合此任務類別的專門能力。"
        if code == "requirement_coverage":
            return f"它涵蓋符合的需求：{'、'.join(evidence.matched_requirements)}。"
        if code == "installed_available":
            return "目前已安裝且可供選用。" if record.status.value == "installed" else "目前可用，作為可選能力。"
        if code == "workspace_specific":
            return "它由明確的 workspace skill root 提供。"
        if code == "preferred_overlap_member":
            return "它是重疊群組中符合任務的優先成員。"
        if code == "complementary_optional":
            return "它提供互補的可選涵蓋。"
        if code == "fallback":
            return "它是固定規則下的 fallback capability。"
        return ""
    if code == "explicit_request":
        return "The task explicitly requests this capability."
    if code == "exact_trigger_match":
        return f"The task matches trigger(s): {', '.join(evidence.matched_triggers)}."
    if code == "specialist_match":
        return "It is a specialist match for the task category."
    if code == "requirement_coverage":
        return f"It covers the matched requirement: {', '.join(evidence.matched_requirements)}."
    if code == "installed_available":
        return "It is installed and available for selection." if record.status.value == "installed" else "It is available for optional selection."
    if code == "workspace_specific":
        return "It is declared by an explicit workspace skill root."
    if code == "preferred_overlap_member":
        return "It is the preferred member of its overlap group."
    if code == "complementary_optional":
        return "It provides complementary optional coverage."
    if code == "fallback":
        return "It is a deterministic fallback capability."
    return ""


def _display_categories(records: Sequence[CapabilityRecord], locale: str) -> str:
    """將 category display name 翻譯，未知 category 保留 canonical text。"""

    values = {category for record in records for category in record.categories}
    ordered = sorted(values, key=lambda value: (value.casefold(), value))
    if locale == "en":
        return ", ".join(ordered) or "none"
    return "、".join(_CATEGORY_LABELS.get(value, value) for value in ordered) or "無"


def _primary_purpose(record: CapabilityRecord, locale: str) -> str:
    """優先使用 canonical Function metadata；缺少時輸出明確 fallback，不猜測功能。"""

    return _function_text(record, locale)


def _use_when(record: CapabilityRecord, locale: str) -> str:
    """依固定 triggers 產生 Use When/適用時機，不執行或改寫 trigger。"""

    triggers = ", ".join(record.triggers) or "the capability category"
    return f"Task mentions: {triggers}." if locale == "en" else f"任務提及：{triggers}。"


def _avoid_when(record: CapabilityRecord, locale: str) -> str:
    """產生 bounded Avoid When 說明，保留 overlap/status 邊界。"""

    if record.status.value == "unavailable":
        return "when status is unavailable." if locale == "en" else "狀態為 unavailable 時。"
    if record.overlap_group:
        return (
            "when another capability in the same overlap group is a better fit."
            if locale == "en"
            else "同一重疊群組已有更合適的能力時。"
        )
    return (
        "when the task does not match its category or triggers."
        if locale == "en"
        else "任務不符合類別或 triggers 時。"
    )


def _localized_rejection(reason: str, locale: str) -> str:
    """將 routing rejection 的固定 reason 轉為 user-facing labels。"""

    labels = _LABELS[locale]
    if reason == "unavailable":
        return labels["unavailable"]
    if reason == "self-routing protection":
        return labels["self_routing"]
    if reason.startswith("redundant overlap_group: "):
        group = reason.removeprefix("redundant overlap_group: ")
        return f"{labels['redundant']}: {group}"
    return reason


def _write_utf8(path: Path, content: str) -> None:
    """以固定 UTF-8/LF 寫入生成 artifact，避免主機編碼影響結果。"""

    with path.open("w", encoding="utf-8", newline="\n") as stream:
        stream.write(content)


if __name__ == "__main__":
    raise SystemExit(main())
