"""測試資料不得成為正式技能入口，正式來源與交接內容必須一致。"""

from pathlib import Path
import tempfile
import unittest

from codex_capability_router.inventory import refresh_skill_inventory_snapshot
from codex_capability_router.selection import PreliminarySelection, handoff_full_instructions
from codex_capability_router.skill_plan import build_skill_root_plan


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_ROOT = REPOSITORY_ROOT / "tests" / "fixtures" / "legacy_frontmatter" / "explain-code"


class FixtureIsolationTests(unittest.TestCase):
    def test_package_exposes_only_its_formal_skill_entrypoint(self) -> None:
        """以實際交付檔案清單防止 Host 將巢狀 fixture 當成技能。"""

        self.assertEqual(
            sorted(path.relative_to(REPOSITORY_ROOT).as_posix()
                   for path in REPOSITORY_ROOT.rglob("SKILL.md")),
            ["SKILL.md"],
        )

    def test_explicit_fixture_root_does_not_override_formal_source(self) -> None:
        """重現舊呼叫端加入 fixture root，仍須綁定正式來源及完整正文。"""

        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary)
            codex_home = home / "managed"
            formal = codex_home / "skills" / "explain-code" / "SKILL.md"
            formal.parent.mkdir(parents=True)
            instructions = (
                "---\nname: explain-code\ndescription: Trace the current source and its error paths.\n---\n"
                "Trace execution, verify references, and distinguish source facts from inference.\n"
            )
            formal.write_bytes(instructions.encode("utf-8"))
            plan = build_skill_root_plan(
                home=home, codex_home=codex_home,
                runtime_extra_roots=(FIXTURE_ROOT,), plugin_manifests=(),
            )
            snapshot = refresh_skill_inventory_snapshot(plan, plugin_manifests=())
            binding = snapshot.inventory.source_binding("explain-code")
            self.assertIsNotNone(binding)
            self.assertEqual(binding.path.resolve(), formal.resolve())
            handoffs = handoff_full_instructions(
                snapshot.inventory, PreliminarySelection(("explain-code",)),
            )
            self.assertEqual(len(handoffs), 1)
            self.assertEqual(handoffs[0].instructions, instructions)


if __name__ == "__main__":
    unittest.main()
