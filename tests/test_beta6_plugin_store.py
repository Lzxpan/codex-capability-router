"""beta.6 official PluginStore root resolution 與 declared-child completion tests。"""

from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from codex_capability_router.discovery import discover_plugin_skill_roots
from codex_capability_router.inventory import refresh_skill_inventory
from codex_capability_router.plugin_store import resolve_plugin_store_inventory
from codex_capability_router.provider_adapters import discover_active_plugin_children
from codex_capability_router.supporting_context import ExecutionNeed, prepare_supporting_context


class Beta6PluginStoreTests(unittest.TestCase):
    """驗證 logical Plugin 先於 per-entity filesystem lookup 的 bounded contract。"""

    @staticmethod
    def _write_package(
        store: Path,
        *,
        marketplace: str = "market",
        name: str = "demo",
        version: str = "1.0.0",
        manifest: dict[str, object] | None = None,
    ) -> Path:
        """建立測試用 exact PluginStore package 與唯一 manifest。"""

        package = store / marketplace / name / version
        manifest_path = package / ".codex-plugin" / "plugin.json"
        manifest_path.parent.mkdir(parents=True)
        payload: dict[str, object] = {"name": name, "version": version}
        if manifest:
            payload.update(manifest)
        manifest_path.write_text(json.dumps(payload), encoding="utf-8")
        return package

    @staticmethod
    def _row(
        *,
        name: str = "demo",
        marketplace: str = "market",
        version: str | None = "1.0.0",
        path: str | None = None,
    ) -> dict[str, object]:
        """建立 current CLI `installed` row；不填入 UI expected count。"""

        return {
            "pluginId": f"{name}@{marketplace}",
            "name": name,
            "marketplaceName": marketplace,
            "version": version,
            "source": {"source": "local" if path else "remote", "path": path},
        }

    def test_version_direct_root_is_resolved_from_store_contract(self) -> None:
        """CLI 缺少 source.path 時依 marketplace/name/version 定位 exact root。"""

        with tempfile.TemporaryDirectory() as temporary:
            store = Path(temporary) / "plugins" / "cache"
            package = self._write_package(store)
            result = resolve_plugin_store_inventory(
                {"available": [{"pluginId": "not-installed@market"}], "installed": [self._row()]},
                plugin_store_root=store,
            )

            self.assertEqual(result.resolved_count, 1)
            self.assertEqual(result.metrics.plugin_logical_total, 1)
            self.assertEqual(result.metrics.plugin_version_direct_root_total, 1)
            self.assertEqual(result.metrics.plugin_manifests_opened, 1)
            self.assertEqual(result.resolutions[0].package_root, package.resolve())
            self.assertEqual(result.resolutions[0].status, "RESOLVED")

    def test_cli_exact_path_has_priority_over_store_derivation(self) -> None:
        """CLI 明確 source.path 是最高優先 evidence，即使它不在測試 store 下。"""

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            store = root / "plugins" / "cache"
            store.mkdir(parents=True)
            exact = self._write_package(root / "runtime-package")
            result = resolve_plugin_store_inventory(
                [self._row(path=str(exact))],
                plugin_store_root=store,
            )

            self.assertEqual(result.metrics.plugin_cli_exact_path_total, 1)
            self.assertEqual(result.metrics.plugin_version_direct_root_total, 0)
            self.assertEqual(result.resolutions[0].package_root, exact.resolve())

    def test_active_fallback_requires_one_direct_version_directory(self) -> None:
        """無 version 時只接受 known base 下唯一直接版本目錄，不猜 latest 或 mtime。"""

        with tempfile.TemporaryDirectory() as temporary:
            store = Path(temporary) / "plugins" / "cache"
            package = self._write_package(store, version="v1")
            result = resolve_plugin_store_inventory(
                [self._row(version=None)],
                plugin_store_root=store,
            )
            self.assertEqual(result.metrics.plugin_active_root_resolved_total, 1)
            self.assertEqual(result.resolutions[0].package_root, package.resolve())

            self._write_package(store, version="v2")
            multiple = resolve_plugin_store_inventory(
                [self._row(version=None)],
                plugin_store_root=store,
            )
            self.assertEqual(multiple.metrics.plugin_active_root_resolved_total, 0)
            self.assertEqual(multiple.metrics.plugin_root_unresolved_total, 1)
            self.assertEqual(multiple.metrics.plugin_version_entries_visited, 2)
            self.assertEqual(multiple.manifests, ())

    def test_invalid_identity_and_missing_root_preserve_diagnostics(self) -> None:
        """invalid identity 與 missing package 不會被假造成存在 manifest。"""

        with tempfile.TemporaryDirectory() as temporary:
            store = Path(temporary) / "plugins" / "cache"
            store.mkdir(parents=True)
            invalid = resolve_plugin_store_inventory(
                [self._row(name="../escape")],
                plugin_store_root=store,
            )
            self.assertEqual(invalid.metrics.plugin_logical_total, 0)
            self.assertEqual(invalid.metrics.plugin_root_unresolved_total, 1)
            self.assertTrue(any(item.startswith("plugin_identity_unresolved:") for item in invalid.diagnostics))

            missing = resolve_plugin_store_inventory(
                [self._row(name="missing")],
                plugin_store_root=store,
            )
            self.assertEqual(missing.metrics.plugin_logical_total, 1)
            self.assertEqual(missing.metrics.plugin_root_missing_total, 1)
            self.assertEqual(missing.resolutions[0].status, "MISSING")
            self.assertEqual(missing.resolutions[0].identity.plugin_name, "missing")  # type: ignore[union-attr]

    def test_duplicate_physical_evidence_is_one_logical_plugin(self) -> None:
        """同一 Plugin 的 exact/version evidence 只形成一個 logical entity。"""

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            store = root / "plugins" / "cache"
            exact = self._write_package(root / "exact")
            self._write_package(store)
            result = resolve_plugin_store_inventory(
                [self._row(path=str(exact)), self._row()],
                plugin_store_root=store,
            )

            self.assertEqual(result.metrics.plugin_logical_total, 1)
            self.assertEqual(len(result.resolutions), 1)
            self.assertEqual(result.metrics.plugin_cli_exact_path_total, 1)
            self.assertEqual(result.resolutions[0].resolution, "CLI_EXACT_PATH")

    def test_manifest_declared_skill_app_mcp_reach_existing_adapters(self) -> None:
        """resolver 的 exact manifest 可直接接入既有 Skill/App/MCP declared paths。"""

        with tempfile.TemporaryDirectory() as temporary:
            store = Path(temporary) / "plugins" / "cache"
            package = self._write_package(
                store,
                manifest={"skills": "./skills/", "apps": "./.app.json", "mcpServers": "./.mcp.json"},
            )
            alpha = package / "skills" / "alpha"
            alpha.mkdir(parents=True)
            (alpha / "SKILL.md").write_text(
                "---\nid: alpha\nname: Alpha Skill\n---\n",
                encoding="utf-8",
            )
            nested = package / "skills" / "unreferenced" / "deep"
            nested.mkdir(parents=True)
            (nested / "SKILL.md").write_text("---\nid: deep\nname: Deep\n---\n", encoding="utf-8")
            (package / ".app.json").write_text(
                json.dumps({"apps": {"declared-app": {"title": "Declared App"}}}), encoding="utf-8"
            )
            (package / ".mcp.json").write_text(
                json.dumps({"mcpServers": {"declared-mcp": {}}}), encoding="utf-8"
            )

            resolved = resolve_plugin_store_inventory([self._row()], plugin_store_root=store)
            skill_roots = discover_plugin_skill_roots(resolved.manifests)
            providers = discover_active_plugin_children(resolved.manifests)
            context = prepare_supporting_context(
                (ExecutionNeed("inspect declared capabilities", "Package declarations may help."),),
                provider_declarations=providers.provider_declarations,
            )
            skills = refresh_skill_inventory((), plugin_manifests=resolved.manifests)

            self.assertEqual(skill_roots, (alpha.resolve(),))
            self.assertEqual(
                {(item.kind, item.provider_id) for item in providers.provider_declarations},
                {("app", "declared-app"), ("mcp", "declared-mcp")},
            )
            self.assertEqual(context.metrics.semantically_considered_count, 2)
            self.assertEqual(context.metrics.never_considered_count, 0)
            self.assertEqual(skills.semantically_considered_count, 1)
            self.assertEqual(skills.never_considered_count, 0)

    def test_resolver_has_no_cache_wide_recursive_discovery(self) -> None:
        """source guard 固定 resolver 不使用 whole-store recursive search。"""

        source = Path(__file__).resolve().parents[1] / "codex_capability_router" / "plugin_store.py"
        text = source.read_text(encoding="utf-8")
        self.assertNotIn("os.walk", text)
        self.assertNotIn(".rglob(", text)
        self.assertNotIn("glob(", text)


if __name__ == "__main__":
    unittest.main()
