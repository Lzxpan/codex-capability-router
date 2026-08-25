"""Phase 2 capability schema 與 bounded discovery 的固定八個核心測試。"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from codex_capability_router.discovery import (
    discover_skill_roots,
    import_manual_inventory,
)
from codex_capability_router.models import CapabilityKind, CapabilityStatus


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def _write_skill(directory: Path, name: str, description: str = "test skill") -> None:
    """建立 temporary fixture 用的最小合法 SKILL.md。"""

    directory.mkdir(parents=True)
    (directory / "SKILL.md").write_text(
        f"---\nid: {name}\nname: {name}\ndescription: {description}\n---\n",
        encoding="utf-8",
    )


class Phase2DiscoveryTests(unittest.TestCase):
    """驗證 Phase 2 的固定 discovery 行為，不依賴真實 inventory。"""

    def test_discover_one_valid_skill(self) -> None:
        """明確指定的根目錄可發現一筆合法 skill record。"""

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _write_skill(root / "alpha", "alpha-skill")

            result = discover_skill_roots([root])

            self.assertEqual(len(result.records), 1)
            record = result.records[0]
            self.assertEqual(record.id, "alpha-skill")
            self.assertEqual(record.name, "alpha-skill")
            self.assertEqual(record.kind, CapabilityKind.SKILL)
            self.assertEqual(record.status, CapabilityStatus.UNKNOWN)
            self.assertEqual(record.source, "skill-root:0")
            self.assertIsNone(record.last_verified)
            self.assertEqual(
                set(json.loads((REPOSITORY_ROOT / "schema/capability-registry.schema.json").read_text(encoding="utf-8"))["required"]),
                {
                    "id",
                    "name",
                    "kind",
                    "status",
                    "categories",
                    "triggers",
                    "priority",
                    "overlap_group",
                    "preferred_for",
                    "requires",
                    "source",
                    "last_verified",
                },
            )

    def test_discover_multiple_valid_skills(self) -> None:
        """多筆合法 skill 依 canonical id 排序輸出。"""

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _write_skill(root / "zeta", "zeta-skill")
            _write_skill(root / "alpha", "alpha-skill")

            result = discover_skill_roots([root])

            self.assertEqual([record.id for record in result.records], ["alpha-skill", "zeta-skill"])

    def test_ignore_unrelated_directory(self) -> None:
        """沒有 SKILL.md 的無關目錄不得被當成 capability。"""

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _write_skill(root / "valid", "valid-skill")
            (root / "unrelated").mkdir()
            (root / "unrelated" / "notes.txt").write_text("ignored", encoding="utf-8")

            result = discover_skill_roots([root])

            self.assertEqual([record.id for record in result.records], ["valid-skill"])

    # 修改紀錄（2026-08-19，Steve Peng）
    # 原始內容：discovery tests 僅覆蓋單行 frontmatter，未固定合法 multiline scalar 與 malformed 邊界。
    # 修改原因：Phase 5G-A 必須先以 synthetic fixture 重現 humanizer-zh 的 `description: |` 相容性問題。
    # 修改後功能：固定 description 保留、normalized registry 輸出，以及真正 malformed metadata 的診斷行為。
    def test_multiline_frontmatter_skill_is_discovered(self) -> None:
        """合法的 block scalar description 可進入 normalized registry。"""

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            skill = root / "multiline"
            skill.mkdir()
            (skill / "SKILL.md").write_text(
                "---\n"
                "id: synthetic-multiline-skill\n"
                "name: synthetic-multiline-skill\n"
                "description: |\n"
                "  First description line.\n"
                "  Second description line.\n"
                "allowed-tools:\n"
                "  - Read\n"
                "  - Write\n"
                "metadata:\n"
                "  trigger: generic trigger\n"
                "  source: generic source\n"
                "---\n",
                encoding="utf-8",
            )

            result = discover_skill_roots([root])

            self.assertEqual(result.diagnostics, ())
            self.assertEqual(len(result.records), 1)
            record = result.records[0]
            self.assertEqual(record.name, "synthetic-multiline-skill")
            self.assertEqual(record.description, "First description line.\nSecond description line.")
            normalized = json.loads(result.to_registry_json())
            self.assertEqual(normalized[0]["name"], "synthetic-multiline-skill")
            self.assertEqual(normalized[0]["description"], record.description)
            self.assertNotIn(str(root), result.to_registry_json())

    def test_truly_malformed_frontmatter_remains_diagnostic(self) -> None:
        """未縮排的 block scalar 後續內容不得被猜測成 metadata。"""

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            skill = root / "malformed"
            skill.mkdir()
            (skill / "SKILL.md").write_text(
                "---\n"
                "name: synthetic-malformed-skill\n"
                "description: |\n"
                "  Valid description line.\n"
                "not-a-metadata-entry\n"
                "---\n",
                encoding="utf-8",
            )

            result = discover_skill_roots([root])

            self.assertEqual(result.records, ())
            self.assertEqual([diagnostic.code for diagnostic in result.diagnostics], ["malformed_skill"])
            self.assertNotIn(str(root), result.diagnostics[0].message)

    def test_malformed_skill_md_handled_safely(self) -> None:
        """格式錯誤的 SKILL.md 只產生診斷，不中斷其他 discovery。"""

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            broken = root / "broken"
            broken.mkdir()
            (broken / "SKILL.md").write_text("name: missing-frontmatter\n", encoding="utf-8")

            result = discover_skill_roots([root])

            self.assertEqual(result.records, ())
            self.assertEqual([diagnostic.code for diagnostic in result.diagnostics], ["malformed_skill"])

    def test_unreadable_entry_handled_safely(self) -> None:
        """無法以檔案讀取的 SKILL.md entry 只產生安全診斷。"""

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            broken = root / "broken"
            broken.mkdir()
            (broken / "SKILL.md").mkdir()

            result = discover_skill_roots([root])

            self.assertEqual(result.records, ())
            self.assertEqual([diagnostic.code for diagnostic in result.diagnostics], ["unreadable_skill"])
            self.assertNotIn(str(root), result.diagnostics[0].message)

    def test_deterministic_ordering(self) -> None:
        """相同 temporary input 每次產生相同 registry JSON。"""

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _write_skill(root / "b", "b-skill")
            _write_skill(root / "a", "a-skill")

            first = discover_skill_roots([root]).to_registry_json()
            second = discover_skill_roots([root]).to_registry_json()

            self.assertEqual(first, second)

    def test_manual_plugin_inventory_import(self) -> None:
        """machine-readable manual inventory 可匯入 plugin record。"""

        inventory = {
            "capabilities": [
                {
                    "id": "plugin.alpha",
                    "name": "Alpha Plugin",
                    "kind": "plugin",
                    "status": "available",
                    "categories": ["testing"],
                    "triggers": ["alpha"],
                    "priority": 5,
                    "overlap_group": None,
                    "preferred_for": ["tests"],
                    "requires": [],
                    "last_verified": None,
                }
            ]
        }

        result = import_manual_inventory(inventory, source_id="manual:test")

        self.assertEqual(len(result.records), 1)
        self.assertEqual(result.records[0].kind, CapabilityKind.PLUGIN)
        self.assertEqual(result.records[0].status, CapabilityStatus.AVAILABLE)
        self.assertEqual(result.records[0].source, "manual:test")

    def test_unknown_status_remains_unknown(self) -> None:
        """缺少可靠狀態資訊時不得推測為 installed 或 unavailable。"""

        inventory = {
            "capabilities": [
                {
                    "id": "plugin.unknown",
                    "name": "Unknown Plugin",
                    "kind": "plugin",
                }
            ]
        }

        result = import_manual_inventory(inventory, source_id="manual:test")

        self.assertEqual(result.records[0].status, CapabilityStatus.UNKNOWN)


if __name__ == "__main__":
    unittest.main()
