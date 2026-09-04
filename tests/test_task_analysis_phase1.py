"""Phase 1 TaskAnalysis 與 legacy frontmatter correctness tests。"""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from pathlib import Path
import tempfile
import unittest

from codex_capability_router.discovery import discover_skill_roots, import_runtime_envelope
from codex_capability_router.inventory import refresh_skill_inventory
from codex_capability_router.models import DiscoveryResult
from codex_capability_router.selection import FullInstructionHandoff, PreliminarySelection, handoff_full_instructions
from codex_capability_router.task_analysis import TaskAnalysis, validate_task_analysis


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
EXPLAIN_CODE_FIXTURE = REPOSITORY_ROOT / "tests" / "fixtures" / "legacy_frontmatter" / "explain-code"


def _analysis_payload() -> dict[str, object]:
    """建立不含 private prompt 的合法 TaskAnalysis fixture。"""

    return {
        "task_summary": "分析 source 並整理可追蹤的技術說明。",
        "work_items": ["理解 source", "整理驗證結果"],
        "deliverables": ["技術文件", "findings"],
        "constraints": ["read-only"],
        "quality_expectations": ["證據可追蹤", "版面清楚"],
    }


def _discover_frontmatter_fixture(frontmatter: str) -> DiscoveryResult:
    """在明確 temporary root 建立並讀取單一 frontmatter fixture。"""

    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        skill = root / "fixture-skill"
        skill.mkdir()
        (skill / "SKILL.md").write_text(f"---\n{frontmatter}\n---\nbody\n", encoding="utf-8")
        return discover_skill_roots([root])


class TaskAnalysisContractTests(unittest.TestCase):
    """驗證 strict schema、tuple normalization 與 immutable result。"""

    def test_valid_payload_is_normalized_and_immutable(self) -> None:
        """合法 structured output 轉成 immutable TaskAnalysis。"""

        payload = _analysis_payload()
        analysis = validate_task_analysis(payload)

        self.assertIsInstance(analysis, TaskAnalysis)
        self.assertEqual(analysis.work_items, ("理解 source", "整理驗證結果"))
        payload["work_items"].append("後續工作")  # type: ignore[union-attr]
        self.assertEqual(analysis.work_items, ("理解 source", "整理驗證結果"))
        with self.assertRaises(FrozenInstanceError):
            analysis.task_summary = "changed"  # type: ignore[misc]
        rendered = analysis.to_mapping()
        rendered["work_items"].append("render-only")  # type: ignore[union-attr]
        self.assertEqual(analysis.work_items, ("理解 source", "整理驗證結果"))

    def test_schema_rejects_missing_extra_and_wrong_types(self) -> None:
        """缺漏、額外欄位與錯誤型別不可進入 contract。"""

        for payload in (
            {key: value for key, value in _analysis_payload().items() if key != "constraints"},
            {**_analysis_payload(), "extra": "reject"},
            {**_analysis_payload(), "work_items": "not-a-list"},
            {**_analysis_payload(), "deliverables": ["" ]},
        ):
            with self.subTest(payload=payload):
                with self.assertRaises(ValueError):
                    validate_task_analysis(payload)

    def test_schema_rejects_unbounded_or_sensitive_text(self) -> None:
        """超長、absolute path 與 secret-like text 不可保存到分析結果。"""

        too_long = {**_analysis_payload(), "task_summary": "x" * 2049}
        absolute_path = {**_analysis_payload(), "constraints": [r"C:\private\source.c"]}
        secret = {**_analysis_payload(), "quality_expectations": ["token: private"]}
        for payload in (too_long, absolute_path, secret):
            with self.subTest(payload=payload):
                with self.assertRaises(ValueError):
                    validate_task_analysis(payload)


class LegacyFrontmatterCorrectnessTests(unittest.TestCase):
    """驗證 explain-code 相容 normalization 與六類拒絕案例。"""

    def test_real_explain_code_fixture_is_discovered(self) -> None:
        """真實 legacy frontmatter 可 discovery，且 source_frontmatter 不進 record。"""

        result = discover_skill_roots([EXPLAIN_CODE_FIXTURE])

        self.assertEqual(result.diagnostics, ())
        self.assertEqual([record.id for record in result.records], ["explain-code"])
        self.assertEqual(result.records[0].name, "explain-code")
        self.assertEqual(result.records[0].status.value, "unknown")
        self.assertNotIn("source_frontmatter", result.to_registry_json())

    def test_explain_code_profile_and_runtime_handoff(self) -> None:
        """trusted-root 合法 Skill 可直接建立 available profile 並 handoff。"""

        trusted_inventory = refresh_skill_inventory([EXPLAIN_CODE_FIXTURE])
        self.assertEqual([record.id for record in trusted_inventory.available_records], ["explain-code"])
        trusted_handoffs = handoff_full_instructions(
            trusted_inventory,
            PreliminarySelection(("explain-code",)),
        )
        self.assertEqual([handoff.id for handoff in trusted_handoffs], ["explain-code"])

        runtime = import_runtime_envelope(
            {
                "capabilities": [
                    {
                        "id": "explain-code",
                        "name": "explain-code",
                        "kind": "skill",
                        "status": "available",
                        "categories": [],
                        "triggers": [],
                        "priority": 0,
                        "overlap_group": None,
                        "preferred_for": [],
                        "requires": [],
                        "last_verified": None,
                    }
                ]
            }
        )
        inventory = refresh_skill_inventory([EXPLAIN_CODE_FIXTURE], runtime=runtime)

        self.assertEqual([profile.id for profile in inventory.profiles], ["explain-code"])
        self.assertEqual([record.id for record in inventory.available_records], ["explain-code"])
        self.assertEqual(inventory._skill_paths["explain-code"], EXPLAIN_CODE_FIXTURE / "SKILL.md")
        handoffs = handoff_full_instructions(inventory, PreliminarySelection(("explain-code",)))
        self.assertEqual([handoff.id for handoff in handoffs], ["explain-code"])

    def test_unknown_nested_metadata_is_ignored_after_core_metadata(self) -> None:
        """可讀的核心 metadata 足夠時，未知 nested metadata 不阻擋存在性發現。"""

        result = _discover_frontmatter_fixture("name: unknown-nested\nmetadata:\n  unknown: value")
        self.assertEqual(len(result.records), 1)
        self.assertEqual(result.diagnostics, ())

    def test_deeper_source_frontmatter_nesting_is_ignored_after_core_metadata(self) -> None:
        """source_frontmatter 的額外巢狀內容不阻擋核心 Skill metadata。"""

        result = _discover_frontmatter_fixture(
            "name: deep-source\nmetadata:\n  source_frontmatter:\n    outer:\n      inner: value"
        )
        self.assertEqual(len(result.records), 1)
        self.assertEqual(result.diagnostics, ())

    def test_invalid_list_or_object_is_rejected(self) -> None:
        """legacy scalar 欄位不可偷偷接受 list/object。"""

        for value in ("[one, two]", '{"nested": "object"}'):
            with self.subTest(value=value):
                result = _discover_frontmatter_fixture(f"name: invalid-structure\nmetadata:\n  source_repo: {value}")
                self.assertEqual([record.id for record in result.records], ["fixture-skill"])
                self.assertEqual([diagnostic.code for diagnostic in result.diagnostics], ["malformed_skill"])

    def test_malformed_syntax_is_rejected(self) -> None:
        """缺少 key/value separator 的 frontmatter 維持 malformed。"""

        result = _discover_frontmatter_fixture("name: malformed-syntax\nmetadata:\n  source_repo broken")
        self.assertEqual([record.id for record in result.records], ["fixture-skill"])
        self.assertEqual([diagnostic.code for diagnostic in result.diagnostics], ["malformed_skill"])

    def test_duplicate_critical_key_is_rejected(self) -> None:
        """重複 critical key 不得由後值覆蓋前值。"""

        result = _discover_frontmatter_fixture("name: duplicate-critical\nname: duplicate-again")
        self.assertEqual([record.id for record in result.records], ["fixture-skill"])
        self.assertEqual([diagnostic.code for diagnostic in result.diagnostics], ["malformed_skill"])

    def test_sensitive_metadata_is_rejected(self) -> None:
        """credential-like metadata 不得進入 compatibility normalization。"""

        result = _discover_frontmatter_fixture("name: sensitive-metadata\nmetadata:\n  api_key: private")
        self.assertEqual([record.id for record in result.records], ["fixture-skill"])
        self.assertEqual([diagnostic.code for diagnostic in result.diagnostics], ["malformed_skill"])


if __name__ == "__main__":
    unittest.main()
