"""beta.9 canonical Skill source binding 與 handoff freshness tests。"""

from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from codex_capability_router.inventory import (
    refresh_selected_skill_snapshot,
    refresh_skill_inventory_snapshot,
)
from codex_capability_router.selection import (
    PreliminarySelection,
    handoff_full_instructions,
    handoff_with_selected_skill_refresh,
)
from codex_capability_router.skill_plan import build_skill_root_plan


def _write_skill(root: Path, body: str) -> Path:
    skill = root / "pdf"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text(
        "---\nname: pdf\ndescription: Handle PDF documents\n---\n" + body,
        encoding="utf-8",
    )
    return skill / "SKILL.md"


class Beta9SkillSourceBindingTests(unittest.TestCase):
    def test_multiple_physical_sources_keep_one_binding_and_are_order_independent(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            first = base / "a-root"
            second = base / "b-root"
            first_path = _write_skill(first, "first\n")
            second_path = _write_skill(second, "second\n")

            plan_a = build_skill_root_plan(
                include_fixed_global=False,
                runtime_extra_roots=(first, second),
            )
            plan_b = build_skill_root_plan(
                include_fixed_global=False,
                runtime_extra_roots=(second, first),
            )
            snapshot_a = refresh_skill_inventory_snapshot(plan_a)
            snapshot_b = refresh_skill_inventory_snapshot(plan_b)
            binding_a = snapshot_a.inventory.source_binding("pdf")
            binding_b = snapshot_b.inventory.source_binding("pdf")

            self.assertIsNotNone(binding_a)
            self.assertIsNotNone(binding_b)
            assert binding_a is not None and binding_b is not None
            self.assertEqual(binding_a.path, binding_b.path)
            self.assertEqual(binding_a.path, first_path)
            self.assertEqual(binding_a.alternate_paths, (second_path,))
            self.assertEqual(snapshot_a.inventory.profiles[0].source_binding, binding_a)
            self.assertEqual(snapshot_a.inventory._skill_paths["pdf"], binding_a.path)
            self.assertTrue(
                any(diagnostic.code == "multiple_physical_skill_sources" for diagnostic in snapshot_a.inventory.diagnostics)
            )

    def test_profile_and_handoff_use_the_same_selected_binding(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "skills"
            skill_path = _write_skill(root, "stable\n")
            plan = build_skill_root_plan(include_fixed_global=False, runtime_extra_roots=(root,))
            snapshot = refresh_skill_inventory_snapshot(plan)
            binding = snapshot.inventory.source_binding("pdf")

            self.assertIsNotNone(binding)
            assert binding is not None
            self.assertEqual(binding.path, skill_path)
            handoffs = handoff_full_instructions(snapshot.inventory, PreliminarySelection(("pdf",)))
            self.assertEqual(handoffs[0].fingerprint, snapshot.inventory.profiles[0].fingerprint)

    def test_mismatch_refreshes_only_selected_source_once_and_retries(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "skills"
            skill_path = _write_skill(root, "before\n")
            plan = build_skill_root_plan(include_fixed_global=False, runtime_extra_roots=(root,))
            snapshot = refresh_skill_inventory_snapshot(plan)
            skill_path.write_text(
                "---\nname: pdf\ndescription: Handle PDF documents\n---\nafter\n",
                encoding="utf-8",
            )

            recovered = handoff_with_selected_skill_refresh(
                snapshot,
                PreliminarySelection(("pdf",)),
            )

            self.assertEqual(recovered.refresh.source_reads, 1)
            self.assertFalse(recovered.refresh.semantic_digest_changed)
            self.assertEqual(
                recovered.snapshot.inventory.profiles[0].fingerprint,
                recovered.handoffs[0].fingerprint,
            )
            self.assertEqual(
                recovered.snapshot.inventory.profiles[0].source_binding,
                recovered.snapshot.inventory.source_binding("pdf"),
            )
            self.assertEqual(
                handoff_full_instructions(
                    recovered.snapshot.inventory,
                    PreliminarySelection(("pdf",)),
                )[0].fingerprint,
                recovered.handoffs[0].fingerprint,
            )

    def test_selected_refresh_returns_a_new_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "skills"
            skill_path = _write_skill(root, "before\n")
            plan = build_skill_root_plan(include_fixed_global=False, runtime_extra_roots=(root,))
            snapshot = refresh_skill_inventory_snapshot(plan)
            skill_path.write_text(
                "---\nname: pdf\ndescription: Handle PDF documents\n---\nafter\n",
                encoding="utf-8",
            )

            refreshed = refresh_selected_skill_snapshot(snapshot, "pdf")

            self.assertIsNot(refreshed.snapshot, snapshot)
            self.assertIsNot(refreshed.snapshot.inventory, snapshot.inventory)
            self.assertEqual(snapshot.inventory.profiles[0].fingerprint != refreshed.snapshot.inventory.profiles[0].fingerprint, True)


if __name__ == "__main__":
    unittest.main()
