"""Phase 4 固定六個 bilingual catalog/output tests。

修改紀錄（2026-08-17，Steve Peng）
原始內容：Phase 4 尚無 catalog 或 language output tests。
修改原因：先以 TDD 固定單一 canonical registry、雙語 catalog 結構與 auto language 行為；beta review 再固定 recommendation traceability。
修改後功能：只驗證 6 個核心行為，不建立大型 translation test suite。
"""

from __future__ import annotations

import json
from pathlib import Path
import unittest

from codex_capability_router.catalog import generate_catalog, render_recommendations
from codex_capability_router.models import CapabilityRecord
from codex_capability_router.validation import record_from_mapping


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
CANONICAL_REGISTRY_PATH = REPOSITORY_ROOT / "tests" / "fixtures" / "routing_registry.json"


def _load_canonical_registry() -> tuple[CapabilityRecord, ...]:
    """載入單一 machine-readable canonical registry fixture，不讀取第二份語言 registry。"""

    payload = json.loads(CANONICAL_REGISTRY_PATH.read_text(encoding="utf-8"))
    return tuple(record_from_mapping(item) for item in payload)


def _catalog_ids(catalog: str) -> tuple[str, ...]:
    """從兩份 Markdown catalog 讀取 canonical ID，驗證輸出集合與順序。"""

    return tuple(line.removeprefix("- ID: ") for line in catalog.splitlines() if line.startswith("- ID: "))


class Phase4CatalogTests(unittest.TestCase):
    """只包含需求指定的六個 Phase 4 核心測試。"""

    @classmethod
    def setUpClass(cls) -> None:
        """共用同一份 canonical registry，避免測試建立語言分叉輸入。"""

        cls.registry = _load_canonical_registry()
        cls.bundle = generate_catalog(cls.registry)

    def test_english_catalog_generation(self) -> None:
        """English catalog 產生必要欄位且保留 ID/enum 原值。"""

        catalog = self.bundle.en
        self.assertIn("# Codex Capability Router Catalog", catalog)
        self.assertIn("Name", catalog)
        self.assertIn("Primary Purpose", catalog)
        self.assertIn("- ID: codex-capability-router", catalog)
        self.assertIn("- Status: installed", catalog)
        self.assertNotIn("名稱", catalog)

    def test_zh_tw_catalog_generation(self) -> None:
        """zh-TW catalog 使用固定繁中 labels 並保留 ID/enum 原值。"""

        catalog = self.bundle.zh_tw
        self.assertIn("# Codex Capability Router Catalog（繁體中文）", catalog)
        self.assertIn("名稱", catalog)
        self.assertIn("主要用途", catalog)
        self.assertIn("韌體除錯", catalog)
        self.assertIn("- ID: codex-capability-router", catalog)
        self.assertIn("- 狀態: installed", catalog)

    def test_identical_capability_count(self) -> None:
        """兩份 catalog 的 capability 數量與 canonical ID 集合完全一致。"""

        english_ids = _catalog_ids(self.bundle.en)
        zh_tw_ids = _catalog_ids(self.bundle.zh_tw)
        self.assertEqual(len(english_ids), len(self.registry))
        self.assertEqual(english_ids, zh_tw_ids)
        self.assertEqual(len(english_ids), len(set(english_ids)))

    def test_identical_capability_ordering(self) -> None:
        """兩份 catalog 依同一 canonical ID ordering 輸出。"""

        english_ids = _catalog_ids(self.bundle.en)
        self.assertEqual(english_ids, tuple(sorted(english_ids, key=lambda value: (value.casefold(), value))))
        self.assertEqual(english_ids, _catalog_ids(self.bundle.zh_tw))

    def test_auto_language_selects_english(self) -> None:
        """English user request 使用 auto 時輸出新版英文 selection labels。"""

        task = "Fix the React component UI bug."
        payload = {
            "task_summary": task,
            "selected_skills": [{"id": "react-ui-debugging", "reason": "Codex selected it."}],
            "selection_status": "selected",
        }
        output = render_recommendations(payload, language="auto", user_request=task)
        self.assertIn("## Selected Skills", output)
        self.assertIn("react-ui-debugging", output)
        self.assertIn("selection status", output.lower())
        self.assertNotIn("主要建議", output)

    def test_auto_language_selects_zh_tw(self) -> None:
        """Traditional Chinese user request 使用 auto 時輸出新版繁中 labels。"""

        task = "請協助除錯 MCU 韌體的 UART 錯誤。"
        payload = {
            "task_summary": task,
            "selected_skills": [{"id": "firmware-debugging", "reason": "Codex 選擇此 Skill。"}],
            "selection_status": "selected",
        }
        output = render_recommendations(payload, language="auto", user_request=task)
        self.assertIn("## 已選技能", output)
        self.assertIn("firmware-debugging", output)
        self.assertIn("選擇狀態", output)
        self.assertNotIn("PRIMARY", output)


if __name__ == "__main__":
    unittest.main()
