"""beta.7 fixed root plan、bounded traversal 與 Skill snapshot cache tests。"""

from __future__ import annotations

from pathlib import Path
from dataclasses import FrozenInstanceError
import inspect
import tempfile
import unittest
from unittest.mock import patch

from codex_capability_router.discovery import (
    discover_plugin_skill_root_specs,
    discover_skill_roots,
)
from codex_capability_router.inventory import (
    SkillInventoryCache,
    refresh_skill_inventory_snapshot,
)
from codex_capability_router.route_context import prepare_route_context
from codex_capability_router.routing import SelectionRouteInput, route
from codex_capability_router.skill_plan import (
    ROOT_KIND_FIXED_GLOBAL,
    ROOT_KIND_RUNTIME_EXTRA,
    RootPlanSnapshot,
    SkillRootSpec,
    TRAVERSAL_BOUNDED_SUBTREE,
    TRAVERSAL_KNOWN_SYSTEM,
    TRAVERSAL_PLUGIN_CONTAINER,
    build_skill_root_plan,
)
from codex_capability_router.task_analysis import TaskAnalysis


def _write_skill(directory: Path, name: str, *, description: str | None = "A bounded Skill.") -> None:
    """建立小型 temporary Skill fixture，不觸碰 live Skill roots。"""

    directory.mkdir(parents=True)
    description_line = "" if description is None else f"description: {description}\n"
    (directory / "SKILL.md").write_text(
        f"---\nid: {name}\nname: {name}\n{description_line}---\nbody\n",
        encoding="utf-8",
    )


class Beta7FixedSkillRootCacheTests(unittest.TestCase):
    """驗證 root-level contract，不以 UI 或歷史 Skill count 作條件。"""

    def test_fixed_global_roots_compress_system_and_preserve_scope(self) -> None:
        """CODEX_HOME/skills 是唯一 managed root，但 .system Skill 仍被找到。"""

        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            home = base / "home"
            codex_home = base / "codex-home"
            _write_skill(home / ".agents" / "skills" / "user-skill", "user-skill")
            _write_skill(codex_home / "skills" / "managed-skill", "managed-skill")
            _write_skill(codex_home / "skills" / ".system" / "system-skill", "system-skill")
            system_spec = SkillRootSpec(
                codex_home / "skills" / ".system",
                "OFFICIAL_SYSTEM_SKILL_ROOT",
                ROOT_KIND_FIXED_GLOBAL,
                scope="system",
            )

            plan = build_skill_root_plan(home=home, codex_home=codex_home, additional_roots=(system_spec,))
            result = discover_skill_roots(plan)

            self.assertEqual(plan.root_count, 2)
            self.assertEqual(plan.input_root_count, 3)
            self.assertEqual(plan.descendant_roots_removed, 1)
            self.assertEqual({record.id for record in result.records}, {"user-skill", "managed-skill", "system-skill"})
            self.assertEqual(
                [record.source for record in result.records if record.id == "system-skill"],
                ["skill-root:system"],
            )

    def test_compression_requires_explicit_coverage(self) -> None:
        """ancestor 只有帶 coverage evidence 才能移除 descendant。"""

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "A"
            child = root / "B"
            covering = SkillRootSpec(root, "TEST", ROOT_KIND_RUNTIME_EXTRA, TRAVERSAL_BOUNDED_SUBTREE)
            nested = SkillRootSpec(child, "TEST", ROOT_KIND_RUNTIME_EXTRA)
            covered = build_skill_root_plan(include_fixed_global=False, additional_roots=(covering, nested))
            not_covered = build_skill_root_plan(
                include_fixed_global=False,
                additional_roots=(SkillRootSpec(root, "TEST", ROOT_KIND_RUNTIME_EXTRA), nested),
            )

            self.assertEqual(covered.root_count, 1)
            self.assertEqual(covered.descendant_roots_removed, 1)
            self.assertEqual(not_covered.root_count, 2)

    def test_same_path_and_independent_roots_are_deterministic(self) -> None:
        """same path 只留一個 node；互不包含的 roots 不被錯誤合併。"""

        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            one = SkillRootSpec(base / "one", "TEST", ROOT_KIND_RUNTIME_EXTRA)
            duplicate = SkillRootSpec(base / "one", "OTHER", ROOT_KIND_RUNTIME_EXTRA, provenance=("duplicate",))
            two = SkillRootSpec(base / "two", "TEST", ROOT_KIND_RUNTIME_EXTRA)
            first = build_skill_root_plan(include_fixed_global=False, additional_roots=(one, duplicate, two))
            second = build_skill_root_plan(include_fixed_global=False, additional_roots=(two, duplicate, one))

            self.assertEqual(first.root_count, 2)
            self.assertEqual(first.duplicate_roots_removed, 1)
            self.assertEqual(first.fingerprint, second.fingerprint)

    def test_project_and_runtime_roots_are_exactly_declared(self) -> None:
        """project 只 derive known exact path；未宣告 runtime root 不會出現。"""

        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            project = base / "project"
            (project / ".agents" / "skills").mkdir(parents=True)
            plan = build_skill_root_plan(
                include_fixed_global=False,
                project_scope=project,
                runtime_extra_roots=(),
            )

            self.assertEqual(plan.root_count, 1)
            self.assertEqual(plan.roots[0].path, (project / ".agents" / "skills").resolve())
            self.assertEqual(
                build_skill_root_plan(include_fixed_global=False).root_count,
                0,
            )

    def test_runtime_root_under_explicit_cover_is_not_added(self) -> None:
        """runtime extra 被已知 parent coverage 涵蓋時不建立第二 node。"""

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "skills"
            parent = SkillRootSpec(root, "TEST", ROOT_KIND_RUNTIME_EXTRA, TRAVERSAL_BOUNDED_SUBTREE)
            extra = SkillRootSpec(root / "extra", "RUNTIME", ROOT_KIND_RUNTIME_EXTRA)
            plan = build_skill_root_plan(include_fixed_global=False, additional_roots=(parent, extra))

            self.assertEqual(plan.root_count, 1)

    def test_plugin_container_is_one_root_and_only_scans_immediate_children(self) -> None:
        """Plugin container 是一個 root node；grandchild 不會被 package-wide recursion 發現。"""

        with tempfile.TemporaryDirectory() as temporary:
            package = Path(temporary) / "plugin"
            skills = package / "skills"
            _write_skill(skills / "alpha", "alpha")
            _write_skill(skills / "beta", "beta")
            _write_skill(skills / "nested" / "deep", "deep")
            manifest = {
                "plugin_id": "example@marketplace",
                "present": True,
                "package_root": str(package),
                "skills": "./skills",
            }

            specs = discover_plugin_skill_root_specs((manifest,))
            plan = build_skill_root_plan(include_fixed_global=False, plugin_roots=specs)
            result = discover_skill_roots(plan)

            self.assertEqual(len(specs), 1)
            self.assertEqual(plan.root_count, 1)
            self.assertEqual(plan.roots[0].traversal_mode, TRAVERSAL_PLUGIN_CONTAINER)
            self.assertEqual({record.id for record in result.records}, {"alpha", "beta"})
            self.assertNotIn("deep", {record.id for record in result.records})

    def test_plugin_direct_and_overlapping_paths_are_bounded(self) -> None:
        """direct Skill 保留；同 package 的 container/child declaration 只留 container。"""

        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            package = base / "plugin"
            _write_skill(package / "skills" / "direct", "direct")
            (package / "skills" / "container").mkdir(parents=True)
            manifest = {
                "plugin_id": "one@marketplace",
                "present": True,
                "package_root": str(package),
                "skills": ["./skills", "./skills/direct"],
            }
            specs = discover_plugin_skill_root_specs((manifest,))
            plan = build_skill_root_plan(include_fixed_global=False, plugin_roots=specs)

            self.assertEqual(len(specs), 1)
            self.assertEqual(plan.root_count, 1)
            self.assertEqual(plan.roots[0].traversal_mode, TRAVERSAL_PLUGIN_CONTAINER)

    def test_different_plugins_are_never_collapsed_to_store_parent(self) -> None:
        """兩個 Plugin 的相對 skills path 必須維持不同 package scope。"""

        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            manifests = []
            for plugin_name in ("one", "two"):
                package = base / plugin_name
                (package / "skills").mkdir(parents=True)
                manifests.append(
                    {
                        "plugin_id": f"{plugin_name}@marketplace",
                        "present": True,
                        "package_root": str(package),
                        "skills": "./skills",
                    }
                )

            plan = build_skill_root_plan(
                include_fixed_global=False,
                plugin_roots=discover_plugin_skill_root_specs(tuple(manifests)),
            )

            self.assertEqual(plan.root_count, 2)
            self.assertNotIn("plugins\\cache", str(plan.roots[0].path).casefold())

    def test_snapshot_and_cache_are_deterministic_and_task_independent(self) -> None:
        """same root/source 產生相同 snapshot；cache reuse 不接受 task input。"""

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "skills"
            _write_skill(root / "cache-skill", "cache-skill")
            plan = build_skill_root_plan(
                include_fixed_global=False,
                additional_roots=(SkillRootSpec(root, "TEST", ROOT_KIND_RUNTIME_EXTRA),),
            )
            first = refresh_skill_inventory_snapshot(plan)
            second = refresh_skill_inventory_snapshot(plan)
            cache = SkillInventoryCache()
            cached_first = cache.get_or_refresh(plan, source_fingerprint="same-source")
            cached_second = cache.get_or_refresh(plan, source_fingerprint="same-source")
            cache.get_or_refresh(plan, source_fingerprint="changed-source")

            self.assertEqual(first.root_plan_fingerprint, plan.fingerprint)
            self.assertEqual(first.inventory_fingerprint, second.inventory_fingerprint)
            self.assertIs(cached_first, cached_second)
            self.assertEqual(cache.root_plan_build_count, 2)
            self.assertEqual(cache.skill_inventory_refresh_count, 2)
            self.assertEqual(cache.cached_inventory_reuse_count, 1)
            self.assertNotIn("task_summary", inspect.signature(build_skill_root_plan).parameters)

    def test_snapshot_carries_plan_fingerprint_and_route_reuses_without_refresh(self) -> None:
        """有效 snapshot 讓 route/context 不再呼叫 Skill filesystem refresh。"""

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "skills"
            _write_skill(root / "cached", "cached")
            plan = build_skill_root_plan(
                include_fixed_global=False,
                additional_roots=(SkillRootSpec(root, "TEST", ROOT_KIND_RUNTIME_EXTRA),),
            )
            snapshot = refresh_skill_inventory_snapshot(plan)
            analysis = TaskAnalysis("cached task", ("inspect",), (), (), ())

            with patch("codex_capability_router.route_context.refresh_skill_inventory", side_effect=AssertionError("refresh")):
                context = prepare_route_context(
                    analysis,
                    skill_roots=(),
                    skill_root_plan=plan,
                    skill_inventory_snapshot=snapshot,
                )
            self.assertEqual(context.root_plan_fingerprint, plan.fingerprint)
            self.assertEqual(context.skill_inventory_fingerprint, snapshot.inventory_fingerprint)

            payload = {
                "task_summary": "cached task",
                "selected_skills": [],
                "selection_status": "no_matching_skill",
            }
            request = SelectionRouteInput(
                task_summary="cached task",
                skill_roots=(),
                preliminary_skill_ids=(),
                final_selection=payload,
                skill_root_plan=plan,
                skill_inventory_snapshot=snapshot,
            )
            with patch("codex_capability_router.inventory.refresh_skill_inventory", side_effect=AssertionError("refresh")):
                receipt = route(request)
            self.assertEqual(receipt.selection_payload(), payload)

    def test_source_change_requires_refresh_but_task_change_does_not(self) -> None:
        """cache key 只依 plan/source state；TaskAnalysis 不在 refresh contract。"""

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "skills"
            root.mkdir()
            plan = build_skill_root_plan(
                include_fixed_global=False,
                additional_roots=(SkillRootSpec(root, "TEST", ROOT_KIND_RUNTIME_EXTRA),),
            )
            cache = SkillInventoryCache()
            cache.get_or_refresh(plan, source_fingerprint="source-a")
            cache.get_or_refresh(plan, source_fingerprint="source-a")
            cache.get_or_refresh(plan, source_fingerprint="source-b")

            self.assertEqual(cache.skill_inventory_refresh_count, 2)
            self.assertEqual(cache.cached_inventory_reuse_count, 1)

    def test_system_rule_does_not_admit_other_hidden_children(self) -> None:
        """known-child 只允許 .system，不會順便遞迴其他 dot-directory。"""

        with tempfile.TemporaryDirectory() as temporary:
            codex_home = Path(temporary) / "codex"
            _write_skill(codex_home / "skills" / ".system" / "system", "system")
            _write_skill(codex_home / "skills" / ".other" / "hidden", "hidden")
            plan = build_skill_root_plan(home=Path(temporary) / "home", codex_home=codex_home)
            result = discover_skill_roots(plan)

            self.assertIn("system", {record.id for record in result.records})
            self.assertNotIn("hidden", {record.id for record in result.records})

    def test_same_path_duplicate_merges_provenance(self) -> None:
        """same physical root 只保留一個 node，但不丟 provenance。"""

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "skills"
            first = SkillRootSpec(root, "FIRST", ROOT_KIND_RUNTIME_EXTRA, provenance=("first",))
            second = SkillRootSpec(root, "SECOND", ROOT_KIND_RUNTIME_EXTRA, provenance=("second",))
            plan = build_skill_root_plan(include_fixed_global=False, additional_roots=(first, second))

            self.assertEqual(plan.root_count, 1)
            self.assertEqual(plan.roots[0].provenance, ("first", "second"))

    def test_independent_fixed_global_roots_are_retained(self) -> None:
        """HOME 與 CODEX_HOME 不包含彼此時，兩個 global roots 都保留。"""

        with tempfile.TemporaryDirectory() as temporary:
            plan = build_skill_root_plan(home=Path(temporary) / "home", codex_home=Path(temporary) / "codex")

            self.assertEqual(plan.root_count, 2)
            self.assertEqual({root.root_kind for root in plan.roots}, {ROOT_KIND_FIXED_GLOBAL})

    def test_missing_project_scope_is_not_added(self) -> None:
        """project scope 未具備 exact .agents/skills 時不猜 ancestor。"""

        with tempfile.TemporaryDirectory() as temporary:
            plan = build_skill_root_plan(include_fixed_global=False, project_scope=Path(temporary) / "missing")

            self.assertEqual(plan.root_count, 0)

    def test_runtime_declared_root_has_explicit_runtime_kind(self) -> None:
        """runtime root 只有 caller 明確宣告時才建立 exact node。"""

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "runtime-skills"
            plan = build_skill_root_plan(include_fixed_global=False, runtime_extra_roots=(root,))

            self.assertEqual(plan.root_count, 1)
            self.assertEqual(plan.roots[0].root_kind, ROOT_KIND_RUNTIME_EXTRA)

    def test_runtime_root_rejects_string_guessing(self) -> None:
        """runtime extra root 不接受未驗證字串，避免任意 path 猜測。"""

        with self.assertRaises(TypeError):
            build_skill_root_plan(include_fixed_global=False, runtime_extra_roots=("arbitrary",))  # type: ignore[arg-type]

    def test_plugin_direct_skill_path_is_one_direct_node(self) -> None:
        """manifest 直接指向 SKILL.md 所屬目錄時只建立一個 direct node。"""

        with tempfile.TemporaryDirectory() as temporary:
            package = Path(temporary) / "package"
            _write_skill(package / "skills" / "direct", "direct")
            manifest = {
                "plugin_id": "direct@marketplace",
                "present": True,
                "package_root": str(package),
                "skills": "./skills/direct",
            }
            specs = discover_plugin_skill_root_specs((manifest,))

            self.assertEqual(len(specs), 1)
            self.assertEqual(specs[0].traversal_mode, "direct-skill-root")

    def test_plugin_container_size_does_not_expand_root_plan(self) -> None:
        """container child 數量只影響 inventory，不影響 root-plan node 數。"""

        with tempfile.TemporaryDirectory() as temporary:
            package = Path(temporary) / "package"
            for index in range(5):
                _write_skill(package / "skills" / f"skill-{index}", f"skill-{index}")
            manifest = {
                "plugin_id": "many@marketplace",
                "present": True,
                "package_root": str(package),
                "skills": "./skills",
            }
            plan = build_skill_root_plan(
                include_fixed_global=False,
                plugin_roots=discover_plugin_skill_root_specs((manifest,)),
            )

            self.assertEqual(plan.root_count, 1)

    def test_plugin_path_escape_has_no_root(self) -> None:
        """manifest declared path 離開 package 時拒絕 physical root。"""

        with tempfile.TemporaryDirectory() as temporary:
            package = Path(temporary) / "package"
            package.mkdir()
            manifest = {
                "plugin_id": "escape@marketplace",
                "present": True,
                "package_root": str(package),
                "skills": "../outside",
            }

            self.assertEqual(discover_plugin_skill_root_specs((manifest,)), ())

    def test_plugin_without_package_root_keeps_no_physical_guess(self) -> None:
        """沒有 package root 時不從 manifest identity 猜 filesystem path。"""

        manifest = {"plugin_id": "logical@marketplace", "present": True, "skills": "./skills"}

        self.assertEqual(discover_plugin_skill_root_specs((manifest,)), ())

    def test_plugin_same_relative_declaration_keeps_package_scope(self) -> None:
        """不同 Plugin 的 ./skills 不能被壓成共同 cache root。"""

        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            manifests = []
            for plugin in ("one", "two"):
                package = base / plugin
                (package / "skills").mkdir(parents=True)
                manifests.append(
                    {
                        "plugin_id": f"{plugin}@marketplace",
                        "present": True,
                        "package_root": str(package),
                        "skills": "./skills",
                    }
                )
            plan = build_skill_root_plan(
                include_fixed_global=False,
                plugin_roots=discover_plugin_skill_root_specs(tuple(manifests)),
            )

            self.assertEqual({root.plugin_identity for root in plan.roots}, {"one@marketplace", "two@marketplace"})

    def test_plan_fingerprint_changes_with_traversal_contract(self) -> None:
        """traversal contract 改變時 snapshot fingerprint 必須改變。"""

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "root"
            immediate = build_skill_root_plan(
                include_fixed_global=False,
                additional_roots=(SkillRootSpec(root, "TEST", ROOT_KIND_RUNTIME_EXTRA),),
            )
            bounded = build_skill_root_plan(
                include_fixed_global=False,
                additional_roots=(SkillRootSpec(root, "TEST", ROOT_KIND_RUNTIME_EXTRA, TRAVERSAL_BOUNDED_SUBTREE),),
            )

            self.assertNotEqual(immediate.fingerprint, bounded.fingerprint)

    def test_root_plan_snapshot_is_frozen(self) -> None:
        """root plan 建立後不可被 route 改寫。"""

        plan = build_skill_root_plan(include_fixed_global=False)

        with self.assertRaises(FrozenInstanceError):
            plan.roots = ()  # type: ignore[misc]

    def test_inventory_snapshot_is_frozen(self) -> None:
        """inventory snapshot 是 refresh artifact，不可被 task route 改寫。"""

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "skills"
            _write_skill(root / "frozen", "frozen")
            plan = build_skill_root_plan(
                include_fixed_global=False,
                additional_roots=(SkillRootSpec(root, "TEST", ROOT_KIND_RUNTIME_EXTRA),),
            )
            snapshot = refresh_skill_inventory_snapshot(plan)

            with self.assertRaises(FrozenInstanceError):
                snapshot.inventory = snapshot.inventory  # type: ignore[misc]

    def test_cache_api_has_no_task_filter_inputs(self) -> None:
        """cache API 不接受 task summary/work items/keywords 作 inventory filter。"""

        parameters = inspect.signature(SkillInventoryCache.get_or_refresh).parameters

        self.assertNotIn("task_summary", parameters)
        self.assertNotIn("work_items", parameters)
        self.assertNotIn("keywords", parameters)

    def test_cache_explicit_refresh_rebuilds_snapshot(self) -> None:
        """explicit refresh 會建立新 snapshot，即使 source state 未改變。"""

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "skills"
            _write_skill(root / "refresh", "refresh")
            plan = build_skill_root_plan(
                include_fixed_global=False,
                additional_roots=(SkillRootSpec(root, "TEST", ROOT_KIND_RUNTIME_EXTRA),),
            )
            cache = SkillInventoryCache()
            first = cache.get_or_refresh(plan, source_fingerprint="same")
            second = cache.get_or_refresh(plan, source_fingerprint="same", refresh=True)

            self.assertIsNot(first, second)
            self.assertEqual(cache.skill_inventory_refresh_count, 2)

    def test_cache_invalidate_forces_next_refresh(self) -> None:
        """explicit invalidation 清除 caller-owned session snapshot。"""

        with tempfile.TemporaryDirectory() as temporary:
            plan = build_skill_root_plan(
                include_fixed_global=False,
                additional_roots=(SkillRootSpec(Path(temporary), "TEST", ROOT_KIND_RUNTIME_EXTRA),),
            )
            cache = SkillInventoryCache()
            cache.get_or_refresh(plan, source_fingerprint="state")
            cache.invalidate()
            cache.get_or_refresh(plan, source_fingerprint="state")

            self.assertEqual(cache.skill_inventory_refresh_count, 2)

    def test_cached_snapshot_preserves_zero_miss_inventory(self) -> None:
        """refresh 建立的 snapshot 保留既有 high-recall zero-miss metrics。"""

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "skills"
            _write_skill(root / "zero-miss", "zero-miss", description=None)
            plan = build_skill_root_plan(
                include_fixed_global=False,
                additional_roots=(SkillRootSpec(root, "TEST", ROOT_KIND_RUNTIME_EXTRA),),
            )
            snapshot = refresh_skill_inventory_snapshot(plan)

            self.assertEqual(snapshot.inventory.canonical_unique_count, 1)
            self.assertEqual(snapshot.inventory.never_considered_count, 0)

    def test_known_system_plan_has_single_managed_node(self) -> None:
        """.system known-child metadata 屬於 parent node，不是額外 root。"""

        with tempfile.TemporaryDirectory() as temporary:
            codex_home = Path(temporary) / "codex"
            plan = build_skill_root_plan(home=Path(temporary) / "home", codex_home=codex_home)

            managed = [root for root in plan.roots if root.path == (codex_home / "skills").resolve()]
            self.assertEqual(len(managed), 1)
            self.assertEqual(managed[0].traversal_mode, TRAVERSAL_KNOWN_SYSTEM)
            self.assertEqual(managed[0].known_children, (".system",))


if __name__ == "__main__":
    unittest.main()
