"""Existence-first discovery 與獨立 post-hoc reconciliation tests。"""

from __future__ import annotations

from pathlib import Path
import inspect
import tempfile
import unittest

import codex_capability_router.discovery as discovery_module
from codex_capability_router.discovery import (
    discover_plugin_skill_declarations,
    discover_plugin_skill_roots,
)
from codex_capability_router.inventory import ProfileCache, refresh_skill_inventory
from codex_capability_router.models import CapabilityStatus
from codex_capability_router.provider_adapters import (
    adapt_official_app_inventory,
    adapt_official_mcp_inventory,
    discover_active_plugin_children,
)
from codex_capability_router.reconciliation import (
    CurrentUiInventoryReference,
    reconcile_current_ui_inventory,
)
from codex_capability_router.selection import prepare_high_recall_selection
from codex_capability_router.supporting_context import ExecutionNeed, prepare_supporting_context


def _write_skill(root: Path, skill_id: str, *, status: str = "unknown") -> Path:
    """建立只含必要 public metadata 的測試 Skill。"""

    directory = root / skill_id
    directory.mkdir(parents=True)
    (directory / "SKILL.md").write_text(
        f"---\nid: {skill_id}\nname: {skill_id}\ndescription: A present test capability.\nstatus: {status}\n---\nmethod\n",
        encoding="utf-8",
    )
    return directory


class ExistenceFirstSkillTests(unittest.TestCase):
    """Skill physical presence 決定 eligibility，readiness 僅保留在 profile。"""

    def test_disabled_skill_with_readable_path_remains_present_and_selectable(self) -> None:
        """runtime disabled 不會把 trusted-root `SKILL.md` 移出 semantic pool。"""

        with tempfile.TemporaryDirectory() as value:
            root = Path(value)
            _write_skill(root, "disabled-present", status="disabled")
            inventory = refresh_skill_inventory((root,), cache=ProfileCache())

            self.assertEqual(inventory.profiles[0].status, CapabilityStatus.DISABLED)
            self.assertEqual([item.id for item in inventory.available_records], ["disabled-present"])

    def test_plugin_manifest_resolves_declared_cache_skill_without_enabled_gate(self) -> None:
        """已確認 Plugin entity 的 cache package 可帶入 declared bundled Skill。"""

        with tempfile.TemporaryDirectory() as value:
            package = Path(value) / "plugins" / "cache" / "plugin-v1"
            skill_path = _write_skill(package / "skills", "bundled-present")
            manifest = {
                "plugin_id": "plugin.example",
                "present": True,
                "enabled": False,
                "package_root": str(package),
                "skill_roots": [str(skill_path)],
            }
            self.assertEqual(discover_plugin_skill_roots((manifest,)), (skill_path,))
            inventory = refresh_skill_inventory((), cache=ProfileCache(), plugin_manifests=(manifest,))
            self.assertEqual([item.id for item in inventory.available_records], ["bundled-present"])

    def test_plugin_manifest_cannot_escape_declared_package_root(self) -> None:
        """package root 存在時，manifest 外的 Skill path 不可污染 trusted discovery。"""

        with tempfile.TemporaryDirectory() as value:
            package = Path(value) / "package"
            outside = Path(value) / "outside"
            _write_skill(outside, "outside-skill")
            manifest = {
                "plugin_id": "plugin.example",
                "present": True,
                "package_root": str(package),
                "skills": [{"path": str(outside)}],
            }
            self.assertEqual(discover_plugin_skill_roots((manifest,)), ())

    def test_plugin_declared_container_resolves_only_direct_skill_children(self) -> None:
        """container declaration 只解析一層合法 child，不遞迴掃整個 package。"""

        with tempfile.TemporaryDirectory() as value:
            package = Path(value) / "package"
            container = package / "bundled-skills"
            alpha = _write_skill(container, "alpha")
            beta = _write_skill(container, "beta")
            _write_skill(alpha / "nested", "hidden")
            manifest = {
                "plugin_id": "plugin.container",
                "present": True,
                "package_root": str(package),
                "skills": [{"path": "bundled-skills"}],
            }
            self.assertEqual(discover_plugin_skill_roots((manifest,)), (alpha, beta))

    def test_package_only_skill_is_present_without_filesystem_handoff(self) -> None:
        """package-only Skill 有 metadata 就進存在 union；handoff 仍由 execution boundary 處理。"""

        manifest = {
            "plugin_id": "plugin.package-only",
            "present": True,
            "skills": [{"id": "package-only", "name": "Package Skill", "description": "Provides package work."}],
        }
        declarations = discover_plugin_skill_declarations((manifest,))
        self.assertEqual([record.id for record in declarations.records], ["package-only"])
        inventory = refresh_skill_inventory((), cache=ProfileCache(), plugin_manifests=(manifest,))
        self.assertEqual([record.id for record in inventory.present_records], ["package-only"])
        self.assertEqual(inventory.available_records, ())
        self.assertEqual(inventory.package_declared_count, 1)
        self.assertEqual(inventory.metadata_sufficient_count, 1)
        preparation = prepare_high_recall_selection(inventory, "package capability audit")
        self.assertEqual([profile.id for profile in preparation.candidates], ["package-only"])
        self.assertEqual(preparation.inventory_sweep.never_considered_ids, ())


class ExistenceFirstProviderTests(unittest.TestCase):
    """Provider readiness 不再是 semantic candidate 的存在性 gate。"""

    def test_disabled_app_with_disabled_tool_is_still_selectable(self) -> None:
        """App/list entity 與 disabled tool summary 都保留給 semantic consideration。"""

        inventory = adapt_official_app_inventory(
            {
                "data": [{"id": "disabled-app", "name": "Disabled App", "description": "Creates reports.", "isAccessible": False, "isEnabled": False}],
            },
            {"apps": [{"id": "disabled-app", "runtimeName": "disabled", "enabled": False, "callable": False}]},
            {"apps": [{"id": "disabled-app", "toolSummaries": [{"name": "report", "title": "Report", "description": "Creates a report.", "isEnabled": False, "disabledReason": "not ready", "isReadOnly": False}]}], "missingAppIds": []},
        )
        self.assertEqual(inventory.selectable_count, 1)
        self.assertEqual(inventory.provider_declarations[0].callable_tools[0].is_enabled, False)
        context = prepare_supporting_context(
            (ExecutionNeed("create a report", "A report capability may help."),),
            provider_declarations=inventory.provider_declarations,
            readiness_evidence=inventory.readiness_evidence,
        )
        self.assertEqual(len(context.provider_digests), 1)
        self.assertEqual(context.provider_digests[0].readiness_state, "KNOWN_UNAVAILABLE")
        self.assertEqual(context.metrics.never_considered_count, 0)

    def test_failed_mcp_with_metadata_is_still_selectable(self) -> None:
        """MCP failed/auth state 只影響 readiness，不移除 server Provider。"""

        inventory = adapt_official_mcp_inventory(
            {
                "data": [{
                    "name": "offline-mcp",
                    "runtimeStatus": "failed",
                    "authStatus": "notLoggedIn",
                    "tools": {"read": {"name": "read", "description": "Reads repository data."}},
                    "serverInfo": {"description": "Reads repository data."},
                }]
            }
        )
        context = prepare_supporting_context(
            (ExecutionNeed("inspect repository", "A repository reader may help."),),
            provider_declarations=inventory.provider_declarations,
            readiness_evidence=inventory.readiness_evidence,
        )
        self.assertEqual(inventory.selectable_count, 1)
        self.assertEqual(context.provider_digests[0].readiness_state, "KNOWN_UNAVAILABLE")
        self.assertEqual(context.metrics.semantically_considered_count, 1)

    def test_plugin_children_use_presence_not_active_state_and_keep_formal_boundary(self) -> None:
        """Plugin enabled=false 的 child 可發現，但 Plugin package 本身不成 Provider。"""

        inventory = discover_active_plugin_children(
            ({
                "plugin_id": "present-disabled-plugin",
                "present": True,
                "enabled": False,
                "capabilities": ({
                    "kind": "app",
                    "provider_id": "plugin.app",
                    "name": "Plugin App",
                    "description": "Provides app actions.",
                },),
            },)
        )
        self.assertEqual([(item.kind, item.provider_id) for item in inventory.provider_declarations], [("app", "plugin.app")])

    def test_plugin_provider_child_path_cannot_escape_package_root(self) -> None:
        """Plugin App/MCP declaration 的 physical path 也受 package containment 保護。"""

        with tempfile.TemporaryDirectory() as value:
            root = Path(value)
            package = root / "package"
            outside = root / "outside"
            manifest = {
                "plugin_id": "plugin.boundary",
                "present": True,
                "package_root": str(package),
                "capabilities": [{
                    "kind": "mcp",
                    "provider_id": "escaped-mcp",
                    "path": str(outside),
                    "description": "Should be rejected outside the package.",
                }],
            }
            inventory = discover_active_plugin_children((manifest,))
            self.assertEqual(inventory.provider_declarations, ())
            self.assertIn("plugin_path_escape:plugin.boundary", inventory.diagnostics)

    def test_provider_duplicate_evidence_merges_exactly(self) -> None:
        """同一 formal Provider 的兩筆 source evidence 只形成一個 canonical record。"""

        manifests = (
            {"plugin_id": "plugin.one", "present": True, "capabilities": [{"kind": "app", "provider_id": "shared-app", "description": "Runs app actions."}]},
            {"plugin_id": "plugin.two", "present": True, "capabilities": [{"kind": "app", "provider_id": "shared-app", "description": "Runs app actions."}]},
        )
        inventory = discover_active_plugin_children(manifests)
        self.assertEqual(inventory.raw_evidence_count, 2)
        self.assertEqual(inventory.canonical_unique_count, 1)
        self.assertEqual(inventory.exact_duplicate_count, 1)


class CurrentUiReconciliationTests(unittest.TestCase):
    """UI 數字比較 logical entities，不比較 cache folders 或 child tools。"""

    def test_discovery_is_decoupled_from_post_hoc_ui_reconciliation(self) -> None:
        """Blind discovery 不 import UI reference，也不接受 expected total。"""

        source = Path(discovery_module.__file__).read_text(encoding="utf-8")
        self.assertNotIn("CURRENT_UI_REFERENCE", source)
        signature = inspect.signature(reconcile_current_ui_inventory)
        self.assertIs(signature.parameters["reference"].default, inspect.Parameter.empty)

    def test_reconciliation_deduplicates_plugin_cache_materializations(self) -> None:
        """同一 Plugin 的兩個 cache materialization 只算一個 logical Plugin。"""

        reference = CurrentUiInventoryReference(skills=3, plugins=3, apps=2, mcp=1)
        result = reconcile_current_ui_inventory(
            skills=[{"id": f"skill-{index}"} for index in range(reference.skills)],
            plugins=[{"plugin_id": "same-plugin", "version": "v1"}, {"plugin_id": "same-plugin", "version": "v2"}]
            + [{"plugin_id": f"plugin-{index}"} for index in range(reference.plugins - 1)],
            apps=[{"id": f"app-{index}"} for index in range(reference.apps)],
            mcp=[{"name": f"mcp-{index}", "tools": [{"name": "child"}]} for index in range(reference.mcp)],
            reference=reference,
        )
        self.assertTrue(result.passed)
        self.assertEqual(result.plugins.raw_count, reference.plugins + 1)
        self.assertEqual(result.plugins.unique_count, reference.plugins)
        self.assertEqual(result.plugins.duplicate_count, 1)
        self.assertEqual(result.mcp.unique_count, reference.mcp)


if __name__ == "__main__":
    unittest.main()
