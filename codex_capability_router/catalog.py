"""Phase 4 deterministic bilingual catalog 與 user-facing output。"""

from __future__ import annotations

import argparse
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import json
from pathlib import Path

from .models import CapabilityRecord
from .routing import SelectionReceipt
from .selection import validate_selection
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
# 修改紀錄（2026-08-19，Steve Peng）
# 原始內容：empty selection 一律渲染成 no-safe-match，且沒有獨立 Router/controller presentation section。
# 修改原因：Phase 5G-B 需要區分 native-model-sufficient 與 no-safe-match，並避免 controller 被誤顯示為 selected capability。
# 修改後功能：加入 deterministic native-model message 與獨立 `Router / Controller` section；selected section 只讀 selected tuples。
# 修改紀錄（2026-08-21，Steve Peng）
# 原始內容：render_recommendations 仍可接收舊 RecommendationResult，且私有 renderer 保留 PRIMARY/OPTIONAL 與舊 outcome。
# 修改原因：v2.1 Phase 4 要求新版 selection contract 成為唯一 production output，不得由舊 renderer 影響正式結果。
# 修改後功能：render_recommendations 只接受並驗證 selected/no_matching_skill payload；移除未被入口使用的舊 selection renderer，catalog metadata 產生仍保留。
# 修改紀錄（2026-08-25，Steve Peng）
# 原始內容：正式 renderer 接受普通 selection dict，無法辨識結果是否真的經過 production route。
# 修改原因：Integration Hardening 要求外層 hand-written result 不得被認定為 Router Receipt。
# 修改後功能：render_recommendations 只接受 SelectionReceipt；render_selection_payload 僅保留低階 payload 渲染測試用途。

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
    payload: SelectionReceipt,
    *,
    language: str = "en",
    user_request: str = "",
) -> str:
    """只渲染 production route 產生的 SelectionReceipt。"""

    if not isinstance(payload, SelectionReceipt):
        raise TypeError("production renderer requires a SelectionReceipt from route()")
    return render_selection_payload(
        payload.selection_payload(),
        language=language,
        user_request=user_request,
    )


def render_selection_payload(
    payload: Mapping[str, object],
    *,
    language: str = "en",
    user_request: str = "",
) -> str:
    """渲染低階 selection payload；此函式不宣稱 payload 曾經過 production route。"""

    locale = resolve_language(language, user_request)
    validated = validate_selection(payload)
    selected = validated["selected_skills"]
    if locale == "en":
        lines = ["# Skill Selection", "", f"Task: {validated['task_summary']}", "", "## Selected Skills"]
        if selected:
            lines.extend(f"- `{item['id']}` — {item['reason']}" for item in selected)
        else:
            lines.append("- No matching skill.")
        lines.extend(["", f"Selection status: `{validated['selection_status']}`"])
    else:
        lines = ["# Skill 選擇", "", f"任務：{validated['task_summary']}", "", "## 已選技能"]
        if selected:
            lines.extend(f"- `{item['id']}` — {item['reason']}" for item in selected)
        else:
            lines.append("- 沒有符合的 Skill。")
        lines.extend(["", f"選擇狀態：`{validated['selection_status']}`"])
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


def _function_text(record: CapabilityRecord, locale: str) -> str:
    """只讀取 canonical Function metadata；缺少 locale 值時使用明確 fallback。"""

    return record.function_for(locale) or (
        "目前沒有足夠的功能說明資料。"
        if locale == "zh-TW"
        else "Function information unavailable."
    )


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


def _write_utf8(path: Path, content: str) -> None:
    """以固定 UTF-8/LF 寫入生成 artifact，避免主機編碼影響結果。"""

    with path.open("w", encoding="utf-8", newline="\n") as stream:
        stream.write(content)


if __name__ == "__main__":
    raise SystemExit(main())
