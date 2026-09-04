"""Phase 1 inventory、Profile cache 與 fingerprint 的 bounded tests。"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from codex_capability_router.discovery import import_manual_inventory, import_runtime_envelope
from codex_capability_router.inventory import ProfileCache, refresh_skill_inventory
from codex_capability_router.models import CapabilityStatus, DiscoveryResult
from codex_capability_router.validation import record_from_mapping


def _write_skill(
    directory: Path,
    name: str,
    *,
    description: str = "A synthetic skill.",
    status: str = "available",
    body: str = "Initial skill instructions.",
) -> None:
    """建立 Phase 1 使用的 temporary Skill root；不寫入 repository inventory。"""

    directory.mkdir(parents=True)
    (directory / "SKILL.md").write_text(
        "---\n"
        f"id: {name}\n"
        f"name: {name}\n"
        f"description: {description}\n"
        f"status: {status}\n"
        "---\n"
        f"{body}\n",
        encoding="utf-8",
    )


def _runtime_record(
    capability_id: str,
    status: str,
    *,
    source: str = "runtime:envelope",
    controller: bool = False,
    routing_support: bool = False,
):
    """建立明確 runtime claim，讓測試固定 availability 與 role 邊界。"""

    return record_from_mapping(
        {
            "id": capability_id,
            "name": capability_id,
            "kind": "skill",
            "status": status,
            "categories": ["phase1"],
            "triggers": [],
            "priority": 1,
            "overlap_group": None,
            "preferred_for": [],
            "requires": [],
            "source": source,
            "last_verified": None,
            "controller": controller,
            "routing_support": routing_support,
        }
    )


class Phase1InventoryTests(unittest.TestCase):
    """驗證 Phase 1 的 inventory refresh 與 cache invalidation。"""

    def test_new_skill_discovery_builds_basic_profile(self) -> None:
        """新增 Skill 可被既有 discovery 發現並建立 Basic Profile。"""

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _write_skill(root / "future", "future-engineering-doc-maker")
            cache = ProfileCache()

            result = refresh_skill_inventory([root], cache=cache)

            self.assertEqual([record.id for record in result.records], ["future-engineering-doc-maker"])
            self.assertEqual([record.id for record in result.available_records], ["future-engineering-doc-maker"])
            profile = result.profiles[0]
            self.assertEqual(profile.id, "future-engineering-doc-maker")
            self.assertEqual(profile.description, "A synthetic skill.")
            self.assertEqual(profile.status, CapabilityStatus.AVAILABLE)
            self.assertEqual(len(profile.fingerprint), 64)
            self.assertEqual(cache.get(profile.id), profile)

    def test_skill_update_marks_old_profile_stale_and_rebuilds(self) -> None:
        """description 或 SKILL.md 內容更新時，舊 Profile stale 並建立新 fingerprint。"""

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            skill_file = root / "future" / "SKILL.md"
            _write_skill(root / "future", "future-engineering-doc-maker")
            cache = ProfileCache()
            first = refresh_skill_inventory([root], cache=cache)
            old_profile = first.profiles[0]

            skill_file.write_text(
                skill_file.read_text(encoding="utf-8").replace(
                    "description: A synthetic skill.",
                    "description: Updated engineering skill.",
                ).replace(
                    "Initial skill instructions.",
                    "Updated skill instructions.",
                ),
                encoding="utf-8",
            )
            second = refresh_skill_inventory([root], cache=cache)

            self.assertNotEqual(second.profiles[0].fingerprint, old_profile.fingerprint)
            self.assertEqual(second.profiles[0].description, "Updated engineering skill.")
            self.assertEqual(cache.get(old_profile.id), second.profiles[0])
            self.assertEqual(cache.get_stale(old_profile.id).fingerprint, old_profile.fingerprint)
            self.assertTrue(cache.get_stale(old_profile.id).stale)

    def test_identical_content_has_stable_fingerprint(self) -> None:
        """相同 canonical profile 與 SKILL.md bytes 必須產生相同 fingerprint。"""

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _write_skill(root / "stable", "stable-skill")
            first = refresh_skill_inventory([root], cache=ProfileCache())
            second = refresh_skill_inventory([root], cache=ProfileCache())

            self.assertEqual(first.profiles[0].fingerprint, second.profiles[0].fingerprint)

    def test_removed_skill_is_not_served_from_old_cache(self) -> None:
        """Skill 消失後不得由舊 cache 恢復為可用 inventory entry。"""

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _write_skill(root / "removed", "removed-skill")
            cache = ProfileCache()
            first = refresh_skill_inventory([root], cache=cache)
            old_profile = first.profiles[0]
            (root / "removed" / "SKILL.md").unlink()

            second = refresh_skill_inventory([root], cache=cache)

            self.assertEqual(second.records, ())
            self.assertEqual(second.profiles, ())
            self.assertEqual(second.available_records, ())
            self.assertIsNone(cache.get(old_profile.id))
            self.assertTrue(cache.get_stale(old_profile.id).stale)

    def test_runtime_unavailable_and_disabled_override_cached_availability(self) -> None:
        """每次 refresh 以 runtime availability 為準，不沿用 cache 的 available 狀態。"""

        for status in ("unavailable", "disabled"):
            with self.subTest(status=status), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                _write_skill(root / "runtime", "runtime-sensitive-skill")
                cache = ProfileCache()
                first = refresh_skill_inventory([root], cache=cache)
                self.assertEqual(first.available_records[0].status, CapabilityStatus.AVAILABLE)

                runtime = import_runtime_envelope(
                    {"capabilities": [_runtime_record("runtime-sensitive-skill", status).to_mapping()]}
                )
                second = refresh_skill_inventory([root], cache=cache, runtime=runtime)

                self.assertEqual(second.profiles[0].status.value, status)
                self.assertEqual(second.profiles[0].description, "A synthetic skill.")
                self.assertEqual([record.id for record in second.available_records], ["runtime-sensitive-skill"])
                self.assertEqual(cache.get("runtime-sensitive-skill").status.value, status)

    def test_runtime_precedence_retains_provenance(self) -> None:
        """runtime > CLI > skill-root > manual，且合併後保留 provenance。"""

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _write_skill(root / "shared", "shared-skill")
            runtime = import_runtime_envelope(
                {"capabilities": [_runtime_record("shared-skill", "available").to_mapping()]}
            )
            cli = DiscoveryResult(
                records=(
                    _runtime_record(
                        "shared-skill",
                        "unavailable",
                        source="cli:codex-plugin-list",
                    ),
                )
            )
            manual = import_manual_inventory(
                {
                    "capabilities": [
                        _runtime_record(
                            "shared-skill",
                            "available",
                            source="manual:fixture",
                        ).to_mapping()
                    ]
                },
                source_id="manual:fixture",
            )

            result = refresh_skill_inventory([root], cache=ProfileCache(), runtime=runtime, cli=cli, manual=manual)

            profile = result.profiles[0]
            self.assertEqual(profile.source, "runtime:envelope")
            self.assertIn("runtime:envelope", profile.provenance)
            self.assertIn("cli:codex-plugin-list", profile.provenance)
            self.assertIn("skill-root:0", profile.provenance)
            self.assertIn("manual:fixture", profile.provenance)
            self.assertEqual([record.id for record in result.available_records], ["shared-skill"])

    def test_ineligible_roles_are_not_available_but_trusted_root_unknown_is_promoted(self) -> None:
        """trusted-root valid Skill 不因 unknown metadata 被餓死，角色 hard gate 仍生效。"""

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _write_skill(root / "normal", "normal-skill")
            runtime = import_runtime_envelope(
                {
                    "capabilities": [
                        _runtime_record("normal-skill", "unknown").to_mapping(),
                        _runtime_record("controller-skill", "available", controller=True).to_mapping(),
                        _runtime_record("support-skill", "available", routing_support=True).to_mapping(),
                        _runtime_record("codex-capability-router", "available").to_mapping(),
                    ]
                }
            )

            result = refresh_skill_inventory([root], cache=ProfileCache(), runtime=runtime)

            self.assertEqual([record.id for record in result.available_records], ["normal-skill"])

    def test_disabled_status_remains_excluded_from_current_inventory(self) -> None:
        """新增 disabled 狀態不得進入新版 production candidate preparation。"""

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _write_skill(root / "disabled", "disabled-skill")
            runtime = import_runtime_envelope(
                {"capabilities": [_runtime_record("disabled-skill", "disabled").to_mapping()]}
            )

            result = refresh_skill_inventory([root], cache=ProfileCache(), runtime=runtime)

            self.assertEqual([record.id for record in result.available_records], ["disabled-skill"])

    def test_cache_does_not_store_skill_content_or_private_paths(self) -> None:
        """cache 只保存 Basic Profile，不保存 SKILL.md 內容或 private path。"""

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _write_skill(root / "private", "private-boundary-skill", body="PRIVATE_CONTENT_MUST_NOT_BE_CACHED")
            cache = ProfileCache()
            refresh_skill_inventory([root], cache=cache)

            rendered = repr(cache)
            self.assertNotIn("PRIVATE_CONTENT_MUST_NOT_BE_CACHED", rendered)
            self.assertNotIn(str(root), rendered)


if __name__ == "__main__":
    unittest.main()
