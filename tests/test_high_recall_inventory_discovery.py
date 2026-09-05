"""High-recall inventory discovery 與 bounded semantic consideration regression tests。"""

from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from codex_capability_router.inventory import ProfileCache, refresh_skill_inventory
from codex_capability_router.inventory_sweep import build_inventory_sweep
from codex_capability_router.provider_adapters import (
    adapt_official_mcp_inventory,
    discover_active_plugin_children,
    discover_host_native_provider_inventory,
    discover_provider_inventory,
)
from codex_capability_router.route_context import prepare_route_context
from codex_capability_router.selection import prepare_high_recall_selection
from codex_capability_router.supporting_context import (
    ExecutionNeed,
    prepare_supporting_context,
)
from codex_capability_router.task_analysis import TaskAnalysis


# 修改紀錄（2026-09-01，Steve Peng）
# 原始內容：既有 regression 只驗證 bounded relevance retrieval，沒有 full inventory sweep、tail coverage 或 generic Host-native discovery。
# 修改原因：High-recall upgrade 必須證明 discovery、semantic consideration pool 與 final selection 已分層，且不因 top-k 截斷造成 starvation。
# 修改後功能：覆蓋 deterministic batching、Skill/Provider 全量 consideration、PRESENT_UNVERIFIED、Plugin/child boundary 與 Host-native generic normalization。


def _write_skill(root: Path, skill_id: str, description: str | None = "A meaningful skill description.") -> None:
    """建立最小 trusted Skill fixture，不含 private metadata。"""

    directory = root / skill_id
    directory.mkdir()
    description_line = "" if description is None else f"description: {description}\n"
    (directory / "SKILL.md").write_text(
        "---\n"
        f"id: {skill_id}\n"
        f"name: {skill_id}\n"
        f"{description_line}"
        "status: available\n"
        "---\n"
        "Use this bounded test capability.\n",
        encoding="utf-8",
    )


class HighRecallInventoryTests(unittest.TestCase):
    """確認 high-recall path 只做 deterministic gate，不做 Python 語意選擇。"""

    def test_batching_covers_tail_deterministically(self) -> None:
        """inventory 超過單批上限時，尾端項目仍被考慮且 fingerprint 固定。"""

        items = tuple(
            {"id": f"tail-{index:03d}", "description": "meaningful public metadata"}
            for index in range(61)
        )
        first = build_inventory_sweep(items, identity_field="id", item_limit=7, byte_limit=800)
        second = build_inventory_sweep(tuple(reversed(items)), identity_field="id", item_limit=7, byte_limit=800)
        self.assertEqual(first.staged_ids, tuple(item["id"] for item in sorted(items, key=lambda item: item["id"])))
        self.assertEqual(first.considered_ids, ())
        self.assertEqual(first.fingerprint, second.fingerprint)
        self.assertGreater(first.batch_count, 1)

    def test_skill_high_recall_pool_includes_tail_and_metrics(self) -> None:
        """正式 Skill pool 不使用舊 top-k shortlist，tail Skill 仍可進 final handoff。"""

        with tempfile.TemporaryDirectory() as value:
            root = Path(value)
            for index in range(31):
                _write_skill(root, f"skill-{index:02d}")
            inventory = refresh_skill_inventory((root,), cache=ProfileCache())
            preparation = prepare_high_recall_selection(inventory, "a broad repository task")
            self.assertEqual(len(preparation.candidates), 31)
            self.assertIn("skill-30", {item.id for item in preparation.candidates})
            self.assertEqual(preparation.inventory_sweep.staged_ids[-1], "skill-30")
            self.assertEqual(preparation.inventory_sweep.considered_ids, ())

            analysis = TaskAnalysis(
                "a broad repository task",
                ("document", "verify"),
                ("README", "test result"),
                (),
                (),
            )
            context = prepare_route_context(analysis, skill_roots=(root,))
            self.assertEqual(context.metrics.never_considered_count, 31)
            self.assertEqual(context.metrics.semantically_considered_count, 0)
            self.assertGreater(context.metrics.sweep_batch_count, 1)

    def test_skill_metadata_quality_does_not_exclude_opaque_profile(self) -> None:
        """Skill 名片 metadata 不足只降低品質，不阻擋全量 consideration。"""

        with tempfile.TemporaryDirectory() as value:
            root = Path(value)
            _write_skill(root, "described-skill")
            _write_skill(root, "opaque-skill", description=None)
            inventory = refresh_skill_inventory((root,), cache=ProfileCache())
            preparation = prepare_high_recall_selection(inventory, "task")
            self.assertEqual(
                [item.id for item in preparation.candidates],
                ["described-skill", "opaque-skill"],
            )
            self.assertEqual(preparation.inventory_sweep.considered_ids, ())

    def test_host_native_registry_is_generic_and_preserves_child_boundary(self) -> None:
        """top-level native capability 可成 builtin_tool；App child 不會升格。"""

        inventory = discover_host_native_provider_inventory(
            (
                {
                    "provider_id": "native.visual",
                    "name": "Visual asset renderer",
                    "description": "Creates original visual assets.",
                    "top_level": True,
                },
                {
                    "provider_id": "app.child.action",
                    "name": "Child action",
                    "description": "An App child action.",
                    "top_level": False,
                    "parent_kind": "app",
                },
            )
        )
        self.assertEqual([(item.kind, item.provider_id) for item in inventory.provider_declarations], [("builtin_tool", "native.visual")])
        self.assertIn("child_tool_not_formal_builtin", inventory.diagnostics)

    def test_plugin_children_are_discovered_without_formal_plugin_provider(self) -> None:
        """active Plugin 的 App/MCP/Skill child 保留，Plugin package 不進 formal Provider。"""

        inventory = discover_active_plugin_children(
            (
                {
                    "plugin_id": "active-package",
                    "active_installed": True,
                    "capabilities": (
                        {"kind": "skill", "skill_id": "bundled-skill", "title": "Bundled Skill", "description": "A bundled method."},
                        {"kind": "app", "provider_id": "bundled.app", "name": "Bundled App", "description": "Provides app actions."},
                        {"kind": "mcp", "provider_id": "bundled.mcp", "name": "Bundled MCP", "description": "Provides MCP actions."},
                    ),
                },
                {"plugin_id": "cache-only", "active_installed": False, "capabilities": ()},
            )
        )
        self.assertEqual({item.kind for item in inventory.provider_declarations}, {"app", "mcp"})
        self.assertEqual([item["skill_id"] for item in inventory.child_skill_declarations], ["bundled-skill"])
        self.assertNotIn("plugin", {item.kind for item in inventory.provider_declarations})
        self.assertIn("DECLARED_ONLY:cache-only", inventory.diagnostics)

    def test_provider_sweep_covers_all_present_unverified_digests(self) -> None:
        """meaningful description + PRESENT_UNVERIFIED Provider 全部可 semantic consideration。"""

        providers = tuple(
            {
                "provider_id": f"provider-{index:02d}",
                "kind": "mcp",
                "host_identity": f"provider-{index:02d}",
                "host_grouping": ["test"],
                "description": "Provides a distinct public execution capability.",
                "callable_tools": [],
                "callable_exposure": False,
                "provenance": ["test-high-recall"],
            }
            for index in range(29)
        )
        context = prepare_supporting_context(
            (ExecutionNeed("execute task", "A public execution capability is useful."),),
            provider_declarations=providers,
        )
        self.assertEqual(context.metrics.selectable_count, 29)
        self.assertEqual(context.metrics.never_considered_count, 29)
        self.assertEqual(context.metrics.semantically_considered_count, 0)
        self.assertEqual(context.metrics.present_unverified_count, 29)
        self.assertEqual(len(context.provider_digests), 29)

    def test_supporting_context_accepts_trusted_host_inventory_envelope(self) -> None:
        """formal context 可直接接收 generic Host discovery，不需手寫 Provider ID mapping。"""

        context = prepare_supporting_context(
            (ExecutionNeed("create visual asset", "A visual runtime capability may help."),),
            host_native_registry={
                "capabilities": [
                    {
                        "provider_id": "native.visual",
                        "name": "Visual asset renderer",
                        "description": "Creates original visual assets.",
                        "top_level": True,
                    }
                ]
            },
        )
        self.assertEqual([item.provider_id for item in context.provider_digests], ["native.visual"])
        self.assertEqual(context.provider_digests[0].kind, "builtin_tool")
        self.assertEqual(context.provider_digests[0].readiness_state, "PRESENT_UNVERIFIED")
        self.assertEqual(context.metrics.semantically_considered_count, 0)

    def test_mcp_provider_description_survives_missing_schema(self) -> None:
        """MCP schema/detail 不完整時，meaningful provider metadata 仍可被考慮。"""

        inventory = adapt_official_mcp_inventory(
            {
                "data": [
                    {
                        "name": "visual-mcp",
                        "runtimeStatus": "notStarted",
                        "authStatus": "notLoggedIn",
                        "tools": {
                            "render": {"name": "render", "description": "Creates a visual asset."}
                        },
                        "serverInfo": {"description": "Provides visual asset generation."},
                    }
                ]
            }
        )
        self.assertEqual(inventory.discovered_count, 1)
        self.assertEqual(inventory.metadata_insufficient_count, 0)
        context = prepare_supporting_context(
            (ExecutionNeed("create visual asset", "A visual capability may help."),),
            provider_declarations=inventory.provider_declarations,
            readiness_evidence=inventory.readiness_evidence,
        )
        self.assertEqual(context.metrics.present_unverified_count, 1)
        self.assertEqual(context.metrics.semantically_considered_count, 0)

    def test_provider_discovery_merge_deduplicates_exact_identity_only(self) -> None:
        """同一 exact declaration 可去重；不同 kind/identity 不因相似用途合併。"""

        registry = {
            "capabilities": [
                {
                    "provider_id": "native.exec",
                    "name": "Native execution",
                    "description": "Runs bounded local commands.",
                    "top_level": True,
                },
            ]
        }
        first = discover_provider_inventory(host_native_registry=registry)
        second = discover_provider_inventory(host_native_registry=registry)
        self.assertEqual(first.provider_declarations, second.provider_declarations)
        self.assertEqual(first.provider_declarations[0].kind, "builtin_tool")


if __name__ == "__main__":
    unittest.main()
