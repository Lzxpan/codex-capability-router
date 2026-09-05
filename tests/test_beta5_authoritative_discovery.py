"""beta.5 authoritative-path discovery 與 declared capability regression tests。"""

from __future__ import annotations

from pathlib import Path
import json
import tempfile
import unittest

from codex_capability_router.discovery import DiscoveryRootPlan, discover_plugin_skill_roots, discover_skill_roots
from codex_capability_router.inventory import refresh_skill_inventory
from codex_capability_router.provider_adapters import discover_active_plugin_children
from codex_capability_router.supporting_context import ExecutionNeed, prepare_supporting_context


class Beta5AuthoritativeDiscoveryTests(unittest.TestCase):
    """固定 root、manifest exact path 與 existence-only consideration 邊界。"""

    def test_root_plan_is_immediate_only_and_reports_bounded_cost(self) -> None:
        """官方 root 只看 immediate entries，不會遞迴到未宣告的孫目錄。"""

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            nested = root / "container" / "deep-skill"
            nested.mkdir(parents=True)
            (nested / "SKILL.md").write_text("---\nid: deep-skill\nname: deep-skill\n---\n", encoding="utf-8")

            result = discover_skill_roots(
                DiscoveryRootPlan.from_roots(
                    (root,),
                    source_kind="OFFICIAL_SKILL_ROOT",
                    authority="test-authority",
                    provenance="test",
                )
            )

            self.assertEqual(result.records, ())
            self.assertEqual(result.metrics["filesystem_root_count"], 1)
            self.assertEqual(result.metrics["filesystem_directory_entries_visited"], 1)
            self.assertEqual(result.metrics["whole_disk_scan_attempted"], 0)

    def test_malformed_skill_with_stable_directory_identity_is_considered(self) -> None:
        """SKILL.md 存在但 frontmatter malformed 時保留 opaque Skill。"""

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            skill = root / "malformed-skill"
            skill.mkdir()
            (skill / "SKILL.md").write_text("---\nname: malformed-skill\nmetadata:\n  broken\n---\n", encoding="utf-8")

            inventory = refresh_skill_inventory((root,))

            self.assertEqual(inventory.canonical_unique_count, 1)
            self.assertIn(inventory.profiles[0].metadata_quality.value, {"SPARSE", "OPAQUE"})
            self.assertEqual(inventory.never_considered_count, 1)
            self.assertEqual(inventory.semantically_considered_count, 0)

    def test_plugin_manifest_string_paths_are_exact_and_bounded(self) -> None:
        """現行 string declaration 只讀 exact Skill/App/MCP paths。"""

        with tempfile.TemporaryDirectory() as temporary:
            package = Path(temporary) / "package"
            skills = package / "skills"
            alpha = skills / "alpha"
            alpha.mkdir(parents=True)
            (alpha / "SKILL.md").write_text(
                "---\nid: alpha\nname: Alpha\ndescription: Alpha capability.\n---\n",
                encoding="utf-8",
            )
            (skills / "unreferenced" / "nested" / "SKILL.md").parent.mkdir(parents=True)
            (skills / "unreferenced" / "nested" / "SKILL.md").write_text(
                "---\nid: unreferenced\nname: Unreferenced\n---\n", encoding="utf-8"
            )
            (package / ".app.json").write_text(
                json.dumps({"apps": {"declared-app": {"title": "Declared App"}}}), encoding="utf-8"
            )
            (package / ".mcp.json").write_text(
                json.dumps({"mcpServers": {"declared-mcp": {}}}), encoding="utf-8"
            )
            manifest = {
                "plugin_id": "plugin@marketplace",
                "present": True,
                "package_root": str(package),
                "skills": "./skills/",
                "apps": "./.app.json",
                "mcpServers": "./.mcp.json",
            }

            skill_roots = discover_plugin_skill_roots((manifest,))
            provider_inventory = discover_active_plugin_children((manifest,))
            context = prepare_supporting_context(
                (ExecutionNeed("inspect declared capabilities", "Declared app and MCP may help."),),
                provider_declarations=provider_inventory.provider_declarations,
            )

            self.assertEqual(skill_roots, (alpha,))
            self.assertEqual(
                {(item.kind, item.provider_id) for item in provider_inventory.provider_declarations},
                {("app", "declared-app"), ("mcp", "declared-mcp")},
            )
            self.assertEqual(context.metrics.never_considered_count, 2)
            self.assertEqual(context.metrics.semantically_considered_count, 0)
            self.assertEqual(provider_inventory.raw_evidence_count, 2)

    def test_declared_child_path_escape_is_rejected_without_package_glob(self) -> None:
        """exact declaration path escape 只產生 diagnostic，不讀 package 外檔案。"""

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            package = root / "package"
            package.mkdir()
            outside = root / "outside.app.json"
            outside.write_text(json.dumps({"apps": {"escaped": {}}}), encoding="utf-8")

            inventory = discover_active_plugin_children(
                ({
                    "plugin_id": "plugin.boundary",
                    "present": True,
                    "package_root": str(package),
                    "apps": "../outside.app.json",
                },)
            )

            self.assertEqual(inventory.provider_declarations, ())
            self.assertIn("plugin_path_escape:plugin.boundary", inventory.diagnostics)


if __name__ == "__main__":
    unittest.main()
