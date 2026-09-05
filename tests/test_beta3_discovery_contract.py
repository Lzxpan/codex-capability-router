"""beta.3 live discovery contract regression tests。"""

from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from codex_capability_router.discovery import probe_cli
from codex_capability_router.host_snapshot import HostCapabilitySnapshot
from codex_capability_router.inventory import ProfileCache, refresh_skill_inventory
from codex_capability_router.provider_adapters import (
    adapt_codex_mcp_cli_inventory,
    discover_active_plugin_children,
    discover_host_capability_snapshot_inventory,
)
from codex_capability_router.selection import prepare_high_recall_selection
from codex_capability_router.supporting_context import (
    ExecutionNeed,
    SupportingProviderDeclaration,
    canonicalize_external_identity,
    prepare_supporting_context,
)


# 修改紀錄（2026-09-02，Steve Peng）
# 原始內容：beta.2 沒有涵蓋現行 CLI envelope、Plugin 外部 identity 與 metadata-only consideration。
# 修改原因：beta.3 必須以 bounded deterministic tests 鎖定 existence-only semantic contract。
# 修改後功能：驗證 @ identity、collision-safe grouping、現行 CLI 最小 schema、controller projection 與 sparse/opaque consideration。


class Beta3DiscoveryContractTests(unittest.TestCase):
    """只驗證 discovery/existence/consideration contract，不執行下游 Provider。"""

    def test_external_plugin_identity_is_preserved_and_grouped_without_validator_error(self) -> None:
        first = discover_active_plugin_children(
            ({
                "plugin_id": "foo@bar",
                "present": True,
                "capabilities": ({"kind": "app", "provider_id": "foo_app", "name": "Foo App"},),
            },)
        ).provider_declarations[0]
        second_key = canonicalize_external_identity("foo-bar", "plugin")
        self.assertEqual(first.raw_external_identity, "foo@bar")
        self.assertEqual(first.canonical_grouping_key, canonicalize_external_identity("foo@bar", "plugin"))
        self.assertNotEqual(first.canonical_grouping_key, second_key)
        self.assertTrue(all("@" not in item for item in first.host_grouping))

    def test_current_plugin_cli_shape_uses_installed_entities_only(self) -> None:
        payload = {
            "available": [{"pluginId": "marketplace-only@plugin"}],
            "installed": [
                {
                    "pluginId": "foo@bar",
                    "name": "Foo",
                    "enabled": False,
                    "installed": True,
                    "unknownFutureField": {"ignored": True},
                }
            ],
        }

        def runner(*args, **kwargs):
            return type("Completed", (), {"returncode": 0, "stdout": json.dumps(payload)})()

        result = probe_cli(("codex", "plugin", "list", "--json"), runner=runner)
        self.assertFalse(result.partial)
        self.assertEqual(len(result.records), 1)
        self.assertNotEqual(result.records[0].id, "marketplace-only@plugin")
        self.assertEqual(result.records[0].kind.value, "plugin")

    def test_current_mcp_cli_shape_accepts_unknown_fields_and_missing_identity_is_diagnostic(self) -> None:
        payload = [
            {"name": "node_repl", "enabled": False, "auth_status": "unknown", "transport": "stdio", "future": 1},
            {"enabled": True, "auth_status": "unknown", "transport": "stdio"},
        ]

        def runner(*args, **kwargs):
            return type("Completed", (), {"returncode": 0, "stdout": json.dumps(payload)})()

        result = probe_cli(("codex", "mcp", "list", "--json"), runner=runner)
        self.assertTrue(result.partial)
        self.assertEqual([record.id for record in result.records], ["node_repl"])
        self.assertTrue(any(item.code == "malformed_probe_entry" for item in result.diagnostics))

    def test_current_mcp_cli_entities_become_present_provider_candidates(self) -> None:
        inventory = adapt_codex_mcp_cli_inventory(
            (
                {"name": "configured_mcp", "enabled": False, "auth_status": "unknown"},
                {"name": "offline_mcp", "enabled": True, "auth_status": "unknown"},
            )
        )
        context = prepare_supporting_context(
            (ExecutionNeed("inspect", "An existing MCP capability may help."),),
            provider_declarations=inventory.provider_declarations,
        )
        self.assertEqual(inventory.runtime_entity_count, 2)
        self.assertEqual(inventory.selectable_count, 2)
        self.assertEqual(inventory.never_considered_count, 2)
        self.assertEqual(inventory.semantically_considered_count, 0)
        self.assertEqual(context.metrics.semantically_considered_count, 0)

    def test_opaque_provider_is_considered_without_readiness_or_metadata_gate(self) -> None:
        declaration = SupportingProviderDeclaration(
            provider_id="opaque.provider",
            kind="app",
            host_identity="opaque.provider",
            host_grouping=("app",),
            description=None,
            callable_tools=(),
            callable_exposure=False,
            provenance=("beta3-test",),
            display_name=None,
        )
        context = prepare_supporting_context(
            (ExecutionNeed("inspect", "An existing capability may help."),),
            provider_declarations=(declaration,),
        )
        self.assertEqual(context.provider_digests[0].metadata_quality.value, "OPAQUE")
        self.assertEqual(context.metrics.never_considered_count, 1)
        self.assertEqual(context.metrics.semantically_considered_count, 0)

    def test_sparse_skill_is_considered_even_without_description(self) -> None:
        with tempfile.TemporaryDirectory() as value:
            root = Path(value) / "skills"
            skill = root / "sparse-skill"
            skill.mkdir(parents=True)
            (skill / "SKILL.md").write_text(
                "---\nid: sparse-skill\nname: Sparse Skill\n---\n",
                encoding="utf-8",
            )
            inventory = refresh_skill_inventory((root,), cache=ProfileCache())
            preparation = prepare_high_recall_selection(inventory, "unrelated task")
            self.assertEqual(len(preparation.candidates), 1)
            self.assertEqual(preparation.candidates[0].metadata_quality.value, "SPARSE")
            self.assertEqual(preparation.inventory_sweep.considered_ids, ())

    def test_controller_registry_projection_preserves_hierarchy_boundary(self) -> None:
        snapshot = HostCapabilitySnapshot.from_controller_registry(
            (
                {
                    "namespace": "functions",
                    "action_name": "exec_command",
                    "display_name": "Command",
                    "hierarchy": "host_native",
                },
                {
                    "namespace": "calendar",
                    "action_name": "list_events",
                    "display_name": "List events",
                    "hierarchy": "app_child",
                    "parent_kind": "app",
                    "parent_identity": "calendar_app",
                },
                {
                    "namespace": "node",
                    "action_name": "js",
                    "display_name": "JavaScript",
                    "hierarchy": "mcp_child",
                    "parent_kind": "mcp",
                    "parent_identity": "node_repl",
                },
            ),
            snapshot_id="controller-snapshot-beta3",
            session_scope="current-session",
        )
        inventory = discover_host_capability_snapshot_inventory(snapshot)
        self.assertEqual(snapshot.host_native_count, 1)
        self.assertEqual(snapshot.app_child_count, 1)
        self.assertEqual(snapshot.mcp_child_count, 1)
        self.assertEqual({item.kind for item in inventory.provider_declarations}, {"builtin_tool", "app", "mcp"})


if __name__ == "__main__":
    unittest.main()
