"""beta.6 official PluginStore root resolution 與 declared-child completion tests。"""

from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from codex_capability_router.discovery import discover_plugin_skill_root_specs, discover_plugin_skill_roots
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
            self.assertEqual(context.metrics.never_considered_count, 2)
            self.assertEqual(context.metrics.semantically_considered_count, 0)
            self.assertEqual(skills.never_considered_count, 1)
            self.assertEqual(skills.semantically_considered_count, 0)

    def test_portable_manifest_discovers_conventional_skill_directory(self) -> None:
        """標準 portable package 的 skills 目錄可進入正式候選，且不掃描其他路徑。"""

        with tempfile.TemporaryDirectory() as temporary:
            store = Path(temporary) / "plugins" / "cache"
            package = store / "market" / "demo" / "1.0.0"
            skill = package / "skills" / "alpha"
            skill.mkdir(parents=True)
            (skill / "SKILL.md").write_text("---\nname: alpha\ndescription: Test skill\n---\n", encoding="utf-8")
            (package / "plugin.json").write_text(json.dumps({
                "$schema": "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json",
                "name": "demo", "version": "1.0.0",
            }), encoding="utf-8")
            result = resolve_plugin_store_inventory([self._row()], plugin_store_root=store)

            self.assertEqual(result.resolved_count, 1)
            self.assertEqual(discover_plugin_skill_roots(result.manifests), (skill.resolve(),))
            self.assertIn("PLUGIN_PORTABLE_LAYOUT_SKILL", discover_plugin_skill_root_specs(result.manifests)[0].source_kind)
            inventory = refresh_skill_inventory((), plugin_manifests=result.manifests)
            self.assertIn("alpha", {item.id for item in inventory.records})
            self.assertEqual(result.metrics.unreferenced_plugin_cache_roots_visited, 0)

    def test_claude_manifest_with_declared_skills_is_resolved(self) -> None:
        """已安裝外掛的 Claude 格式宣告沿既有受限技能路徑處理。"""

        with tempfile.TemporaryDirectory() as temporary:
            store = Path(temporary) / "plugins" / "cache"
            package = store / "market" / "demo" / "1.0.0"
            skill = package / "skills" / "alpha"
            skill.mkdir(parents=True)
            (skill / "SKILL.md").write_text("---\nname: alpha\ndescription: Test skill\n---\n", encoding="utf-8")
            manifest = package / ".claude-plugin" / "plugin.json"
            manifest.parent.mkdir()
            manifest.write_text(json.dumps({"name": "demo", "skills": "./skills/"}), encoding="utf-8")
            result = resolve_plugin_store_inventory([self._row()], plugin_store_root=store)

            self.assertEqual(result.resolved_count, 1)
            self.assertEqual(result.resolutions[0].manifest_path, manifest)
            self.assertEqual(discover_plugin_skill_roots(result.manifests), (skill.resolve(),))

    def test_legacy_codex_manifest_is_preserved_without_portable_manifest(self) -> None:
        """沒有 portable 根宣告時，保留 V1.1.3 的 Codex 宣告。"""

        with tempfile.TemporaryDirectory() as temporary:
            store = Path(temporary) / "plugins" / "cache"
            package = self._write_package(store, manifest={"skills": "./codex-skills/"})
            (package / ".claude-plugin").mkdir()
            (package / ".claude-plugin" / "plugin.json").write_text('{"name":"demo"}', encoding="utf-8")
            result = resolve_plugin_store_inventory([self._row()], plugin_store_root=store)
            self.assertEqual(result.resolutions[0].manifest_path, package / ".codex-plugin" / "plugin.json")
            self.assertEqual(result.manifests[0]["skills"], "./codex-skills/")

    def test_portable_root_precedes_codex_overlay(self) -> None:
        """Portable 標準目錄為準，inline OpenAI 設定取代 Codex overlay。"""

        with tempfile.TemporaryDirectory() as temporary:
            store = Path(temporary) / "plugins" / "cache"
            package = self._write_package(store, manifest={"skills": "./other-skills/", "apps": "./old.json"})
            (package / "skills" / "alpha").mkdir(parents=True)
            (package / "skills" / "alpha" / "SKILL.md").write_text("---\nname: alpha\n---\n", encoding="utf-8")
            root = package / "plugin.json"
            payload = {"$schema": "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json", "name": "demo"}
            for inline in (False, True):
                with self.subTest(inline=inline):
                    if inline:
                        payload["extensions"] = {"com.openai": {"apps": "./new.json"}}
                    root.write_text(json.dumps(payload), encoding="utf-8")
                    result = resolve_plugin_store_inventory([self._row()], plugin_store_root=store)
                    self.assertEqual(result.resolutions[0].manifest_path, root)
                    self.assertEqual(result.metrics.plugin_manifests_opened, 1 if inline else 2)
                    self.assertEqual(discover_plugin_skill_roots(result.manifests), ((package / "skills" / "alpha").resolve(),))
                    self.assertEqual(result.manifests[0]["apps"], "./new.json" if inline else "./old.json")

    def test_unrelated_root_format_does_not_hide_codex_manifest(self) -> None:
        """其他 root JSON 不可遮蔽既有 Codex 外掛；未知 portable 版本不可降級。"""

        with tempfile.TemporaryDirectory() as temporary:
            store = Path(temporary) / "plugins" / "cache"
            package = self._write_package(store, manifest={"skills": "./skills/"})
            root = package / "plugin.json"
            for schema in (None, "https://antigravity.google/schemas/v1/plugin.json"):
                with self.subTest(schema=schema):
                    payload = {"name": "demo"}
                    if schema is not None:
                        payload["$schema"] = schema
                    root.write_text(json.dumps(payload), encoding="utf-8")
                    result = resolve_plugin_store_inventory([self._row()], plugin_store_root=store)
                    self.assertEqual(result.resolutions[0].manifest_path, package / ".codex-plugin" / "plugin.json")
                    self.assertEqual(result.metrics.plugin_manifests_opened, 2)
                    self.assertEqual(result.manifests[0]["skills"], "./skills/")
            for schema in ("https://agent-plugins.org/schemas/2.0.0/plugin.schema.json", None):
                with self.subTest(invalid_portable_schema=schema):
                    root.write_text(json.dumps({"name": "demo", "$schema": schema}), encoding="utf-8")
                    result = resolve_plugin_store_inventory([self._row()], plugin_store_root=store)
                    self.assertEqual(result.resolved_count, 0)
                    self.assertIn("plugin_manifest_schema_unsupported:demo@market", result.diagnostics)

    def test_alternate_manifest_rejects_mismatched_identity_or_schema(self) -> None:
        """新格式不可把其他身分或未知根目錄 JSON 當成可信外掛宣告。"""

        with tempfile.TemporaryDirectory() as temporary:
            store = Path(temporary) / "plugins" / "cache"
            package = store / "market" / "demo" / "1.0.0"
            package.mkdir(parents=True)
            manifest = package / "plugin.json"
            for payload, diagnostic in (
                ({"name": "other", "$schema": "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json"}, "plugin_manifest_identity_mismatch"),
                ({"name": "demo", "$schema": "https://example.invalid/unrecognized"}, "plugin_manifest_schema_unsupported"),
            ):
                manifest.write_text(json.dumps(payload), encoding="utf-8")
                result = resolve_plugin_store_inventory([self._row()], plugin_store_root=store)
                self.assertEqual(result.resolved_count, 0)
                self.assertIn(diagnostic + ":demo@market", result.diagnostics)

    def test_portable_manifest_ignores_unknown_fields_and_uses_default_skills(self) -> None:
        """Portable 未知欄位不得覆蓋標準目錄或注入其他候選。"""

        with tempfile.TemporaryDirectory() as temporary:
            store = Path(temporary) / "plugins" / "cache"
            package = store / "market" / "demo" / "1.0.0"
            (package / "skills" / "alpha").mkdir(parents=True)
            (package / "skills" / "alpha" / "SKILL.md").write_text("---\nname: alpha\n---\n", encoding="utf-8")
            for extra in ([], "./other-skills/"):
                with self.subTest(skills=extra):
                    (package / "plugin.json").write_text(json.dumps({
                        "$schema": "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json",
                        "name": "demo", "skills": extra, "capabilities": "invalid",
                        "mcpServers": {"injected": {}}, "plugin_skill_root_origin": "spoofed",
                        "/example/private-key-placeholder": "ignored",
                    }), encoding="utf-8")
                    result = resolve_plugin_store_inventory([self._row()], plugin_store_root=store)
                    self.assertEqual(result.resolved_count, 1)
                    self.assertEqual(discover_plugin_skill_roots(result.manifests), ((package / "skills" / "alpha").resolve(),))
                    self.assertNotIn("capabilities", result.manifests[0])
                    self.assertNotIn("mcpServers", result.manifests[0])
                    self.assertIn("plugin_manifest_unknown_field:demo@market", result.diagnostics)
                    self.assertNotIn("/example/private-key-placeholder", str(result.to_mapping()))

    def test_claude_default_and_additional_skill_paths_are_both_discovered(self) -> None:
        """Claude 預設目錄不受省略、空清單或額外宣告影響。"""

        with tempfile.TemporaryDirectory() as temporary:
            store = Path(temporary) / "plugins" / "cache"
            package = store / "market" / "demo" / "1.0.0"
            for parent, name in (("skills", "alpha"), ("extra", "beta")):
                skill = package / parent / name
                skill.mkdir(parents=True)
                (skill / "SKILL.md").write_text(f"---\nname: {name}\n---\n", encoding="utf-8")
            manifest = package / ".claude-plugin" / "plugin.json"
            manifest.parent.mkdir()
            for extra in (None, [], "./extra/"):
                with self.subTest(skills=extra):
                    payload = {"name": "demo"}
                    if extra is not None:
                        payload["skills"] = extra
                    manifest.write_text(json.dumps(payload), encoding="utf-8")
                    result = resolve_plugin_store_inventory([self._row()], plugin_store_root=store)
                    names = {path.name for path in discover_plugin_skill_roots(result.manifests)}
                    self.assertEqual(names, {"alpha", "beta"} if extra == "./extra/" else {"alpha"})
                    specs = discover_plugin_skill_root_specs(result.manifests)
                    self.assertTrue(any(spec.source_kind.startswith("PLUGIN_CLAUDE_LAYOUT_SKILL:") for spec in specs))
                    if extra == "./extra/":
                        self.assertTrue(any(spec.source_kind.startswith("PLUGIN_MANIFEST_DECLARED_SKILL:") for spec in specs))

    def test_codex_manifest_cannot_spoof_portable_provenance(self) -> None:
        """外部宣告不得偽造由 resolver 建立的來源標記。"""

        with tempfile.TemporaryDirectory() as temporary:
            store = Path(temporary) / "plugins" / "cache"
            package = self._write_package(store, manifest={"skills": "./skills/", "plugin_skill_root_origin": "portable_layout"})
            (package / "skills").mkdir()
            result = resolve_plugin_store_inventory([self._row()], plugin_store_root=store)
            specs = discover_plugin_skill_root_specs(result.manifests)
            self.assertEqual(len(specs), 1)
            self.assertTrue(specs[0].source_kind.startswith("PLUGIN_MANIFEST_DECLARED_SKILL:"))

    def test_alternate_manifest_cannot_discover_outside_package(self) -> None:
        """外掛清單內的相對路徑不得取得 package 之外的技能。"""

        with tempfile.TemporaryDirectory() as temporary:
            store = Path(temporary) / "plugins" / "cache"
            package = store / "market" / "demo" / "1.0.0"
            package.mkdir(parents=True)
            outside = package.parent / "outside"
            outside.mkdir()
            (outside / "SKILL.md").write_text("---\nname: outside\n---\n", encoding="utf-8")
            manifest = package / ".claude-plugin" / "plugin.json"
            manifest.parent.mkdir()
            manifest.write_text(json.dumps({"name": "demo", "skills": "../outside"}), encoding="utf-8")
            result = resolve_plugin_store_inventory([self._row()], plugin_store_root=store)
            self.assertEqual(result.resolved_count, 1)
            self.assertEqual(discover_plugin_skill_roots(result.manifests), ())

    def test_portable_resolved_paths_cannot_escape_package(self) -> None:
        """模擬連結解析至外部時，拒絕 manifest 與預設技能目錄。"""

        with tempfile.TemporaryDirectory() as temporary:
            store = Path(temporary) / "plugins" / "cache"
            package = store / "market" / "demo" / "1.0.0"
            (package / "skills").mkdir(parents=True)
            manifest = package / "plugin.json"
            manifest.write_text(json.dumps({
                "$schema": "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json", "name": "demo",
            }), encoding="utf-8")
            outside = (package.parent / "outside").resolve()
            resolve = Path.resolve
            for escaped in (manifest, package / "skills"):
                with self.subTest(escaped=escaped.name):
                    def mocked_resolve(path: Path, *args: object, **kwargs: object) -> Path:
                        return outside if path == escaped else resolve(path, *args, **kwargs)

                    with patch.object(Path, "resolve", autospec=True, side_effect=mocked_resolve):
                        result = resolve_plugin_store_inventory([self._row()], plugin_store_root=store)
                        if escaped == manifest:
                            self.assertEqual(result.resolved_count, 0)
                            self.assertIn("plugin_manifest_unsafe_path:demo@market", result.diagnostics)
                        else:
                            self.assertEqual(discover_plugin_skill_roots(result.manifests), ())

    def test_resolver_has_no_cache_wide_recursive_discovery(self) -> None:
        """source guard 固定 resolver 不使用 whole-store recursive search。"""

        source = Path(__file__).resolve().parents[1] / "codex_capability_router" / "plugin_store.py"
        text = source.read_text(encoding="utf-8")
        self.assertNotIn("os.walk", text)
        self.assertNotIn(".rglob(", text)
        self.assertNotIn("glob(", text)


if __name__ == "__main__":
    unittest.main()
