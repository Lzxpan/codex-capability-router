"""Synthetic, temporary metadata only; never touch a user's preference store."""

from dataclasses import FrozenInstanceError, replace
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from codex_capability_router.preferences import MAX_PREFERENCE_BYTES, PreferenceSnapshot, SkillPreference
from codex_capability_router.inventory import refresh_skill_inventory
from codex_capability_router.preference_store import (
    clear_preferences, load_preferences, set_preference_enabled, update_preferences,
)
from tests.test_route_context_phase2 import _write_skill


KEY = ("code_modification", "code-comments")
DAY = "2026-01-01"


class PreferenceStoreTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.path = Path(self.temporary.name) / "prefs.json"
        # 使用正式 discovery 產生分類資料；不在測試中複製 controller 判斷規則。
        skills = tempfile.TemporaryDirectory()
        self.addCleanup(skills.cleanup)
        self.skill_root = Path(skills.name)
        for skill_id in (KEY[1], "skill-000", "codex-capability-router"):
            _write_skill(self.skill_root, skill_id)
        _write_skill(self.skill_root, "flow-coordinator", controller=True)
        _write_skill(self.skill_root, "flow-helper", routing_support=True)
        self.inventory = refresh_skill_inventory((self.skill_root,))

    def learn(self, **changes):
        args = dict(learning_decision=(KEY,),
                    user_observations=({"preferred_skill_id": KEY[1], "source": "USER_MANUALLY_ADDED"},),
                    observed_on=DAY, skill_inventory=self.inventory)
        args.update(changes)
        return update_preferences(self.path, **args)

    def test_round_trip_count_and_exact_persisted_fields(self):
        first = self.learn()
        self.assertTrue(first.written)
        self.assertEqual(load_preferences(self.path), first.snapshot)
        raw = self.path.read_bytes()
        self.assertFalse(raw.startswith(b"\xef\xbb\xbf"))
        payload = json.loads(raw)
        self.assertEqual(set(payload), {"schema_version", "preferences"})
        self.assertEqual(set(payload["preferences"][0]), {
            "task_pattern", "preferred_skill_id", "learned_from", "use_count", "last_used", "enabled"})
        self.assertEqual(first.snapshot.preferences[0].use_count, 1)
        self.assertEqual(self.learn().snapshot.preferences[0].use_count, 2)
        with self.assertRaises(FrozenInstanceError):
            first.snapshot.preferences = ()

    def test_prompt_specification_is_a_user_source_and_no_llm_decision_means_no_learning(self):
        result = self.learn(user_observations=({"preferred_skill_id": KEY[1], "source": "USER_SPECIFIED"},))
        self.assertEqual(result.snapshot.preferences[0].learned_from, "USER_SPECIFIED")
        before = self.path.read_bytes()
        self.assertFalse(self.learn(learning_decision=()).written)
        self.assertEqual(before, self.path.read_bytes())

    def test_model_and_memory_selection_cannot_establish_user_preferences(self):
        for source in ("MODEL_SELECTED", "MEMORY_ADDED", "TOOL_OUTPUT"):
            with self.subTest(source=source):
                result = self.learn(user_observations=({"preferred_skill_id": KEY[1], "source": source},))
                self.assertFalse(result.written)
                self.assertIn("MEMORY_INVALID_LEARNING", result.diagnostics)
        self.assertFalse(self.learn(user_observations=()).written)
        self.assertFalse(self.path.exists())

    def test_router_prompt_and_manual_selection_never_form_preferences(self):
        """起始 prompt 的 Router 指定及手動補選，都不能繞過 production eligibility。"""
        key = ("code_modification", "codex-capability-router")
        for source in ("USER_SPECIFIED", "USER_MANUALLY_ADDED"):
            result = self.learn(learning_decision=(key,),
                user_observations=({"preferred_skill_id": key[1], "source": source},))
            self.assertFalse(result.written)
            self.assertEqual(result.diagnostics, ("MEMORY_SKILL_INELIGIBLE",))
            self.assertEqual(result.snapshot.preferences, ())
        self.assertFalse(self.path.exists())

    def test_metadata_controllers_and_routing_support_are_rejected(self):
        """不同名稱的控制與路由支援 Skill 必須由 metadata 排除。"""
        for skill_id in ("flow-coordinator", "flow-helper"):
            result = self.learn(learning_decision=(("technical_writing", skill_id),),
                user_observations=({"preferred_skill_id": skill_id, "source": "USER_SPECIFIED"},))
            self.assertFalse(result.written)
            self.assertEqual(result.diagnostics, ("MEMORY_SKILL_INELIGIBLE",))
        self.assertFalse(self.path.exists())

    def test_mixed_payload_rejects_only_ineligible_targets_and_preserves_normal_learning(self):
        """同批拒絕控制 Skill，正常關聯仍可寫入、重新載入及累計。"""
        keys = (KEY, (KEY[0], "flow-coordinator"), (KEY[0], "flow-helper"))
        observations = tuple({"preferred_skill_id": key[1], "source": "USER_MANUALLY_ADDED"} for key in keys)
        for count in (1, 2):
            result = self.learn(learning_decision=keys, user_observations=observations)
            self.assertTrue(result.written)
            self.assertEqual(result.diagnostics, ("MEMORY_SKILL_INELIGIBLE",))
            self.assertEqual([item.key for item in load_preferences(self.path).preferences], [KEY])
            self.assertEqual(result.snapshot.preferences[0].use_count, count)
        self.assertNotIn("flow-", self.path.read_text(encoding="utf-8"))

    def test_missing_inventory_or_target_does_not_update_existing_preferences(self):
        """缺少當輪存在性證據時拒絕更新，但保留既有合法偏好。"""
        self.learn()
        before = self.path.read_bytes()
        for inventory in (None, replace(self.inventory, records=(), present_records=())):
            result = self.learn(skill_inventory=inventory)
            self.assertFalse(result.written)
            self.assertEqual(result.diagnostics, ("MEMORY_SKILL_MISSING",))
            self.assertEqual(self.path.read_bytes(), before)

    def test_existing_controller_cannot_be_reinforced_by_learning_or_confirmed_use(self):
        """舊版誤學資料不自動刪除，也不能再藉學習或使用確認更新。"""
        key = ("technical_writing", "flow-coordinator")
        record = SkillPreference(*key, "USER_SPECIFIED", 1, DAY)
        self.path.write_text(json.dumps(PreferenceSnapshot((record,)).to_mapping()), encoding="utf-8")
        before = self.path.read_bytes()
        for changes in (dict(learning_decision=(key,),
                             user_observations=({"preferred_skill_id": key[1], "source": "USER_SPECIFIED"},)),
                        dict(learning_decision=(), confirmed_memory_uses=(key,))):
            result = self.learn(**changes, observed_on="2026-01-02")
            self.assertFalse(result.written)
            self.assertEqual(result.diagnostics, ("MEMORY_SKILL_INELIGIBLE",))
            self.assertEqual(self.path.read_bytes(), before)

    def test_duplicate_pairs_are_counted_once_per_update_and_order_is_deterministic(self):
        result = self.learn(learning_decision=(KEY, KEY))
        self.assertEqual(result.snapshot.preferences[0].use_count, 1)
        other = SkillPreference("technical_writing", "source-notes", "USER_SPECIFIED", 7, DAY)
        one = PreferenceSnapshot((other, result.snapshot.preferences[0]))
        two = PreferenceSnapshot(tuple(reversed(one.preferences)))
        self.assertEqual(one.to_mapping(), two.to_mapping())
        self.assertEqual(one.fingerprint, two.fingerprint)

    def test_confirmed_memory_use_only_updates_existing_date_not_user_count(self):
        self.learn()
        update = update_preferences(self.path, confirmed_memory_uses=(KEY,), observed_on="2026-01-02",
                                    skill_inventory=self.inventory)
        record = update.snapshot.preferences[0]
        self.assertEqual((record.last_used, record.use_count), ("2026-01-02", 1))
        before = self.path.read_bytes()
        result = update_preferences(self.path, observed_on="2026-01-03")
        self.assertFalse(result.written)
        self.assertEqual(before, self.path.read_bytes())
        missing = update_preferences(self.path, confirmed_memory_uses=(("image_creation", "image-helper"),), observed_on=DAY)
        self.assertIn("MEMORY_KEY_MISSING", missing.diagnostics)
        self.assertEqual(len(missing.snapshot.preferences), 1)

    def test_disable_learning_does_not_reenable_and_deletion_is_scoped(self):
        self.learn()
        self.assertFalse(set_preference_enabled(self.path, KEY, False).snapshot.preferences[0].enabled)
        self.assertFalse(self.learn().snapshot.preferences[0].enabled)
        self.assertTrue(set_preference_enabled(self.path, KEY, True).snapshot.preferences[0].enabled)
        self.assertTrue(clear_preferences(self.path, KEY).written)
        self.assertEqual(load_preferences(self.path).preferences, ())
        self.learn()
        self.assertTrue(clear_preferences(self.path).written)
        self.assertEqual(json.loads(self.path.read_bytes())["preferences"], [])

    def test_missing_empty_corrupt_version_and_duplicate_json_keys(self):
        self.assertEqual(load_preferences(self.path), PreferenceSnapshot())
        self.path.write_bytes(b" \n")
        self.assertEqual(load_preferences(self.path), PreferenceSnapshot())
        for raw, code in ((b"{", "MEMORY_INVALID"), (b"\xff", "MEMORY_INVALID"),
                          (b'{"schema_version":2,"preferences":[]}', "MEMORY_VERSION_UNSUPPORTED"),
                          (b'{"schema_version":1,"schema_version":1,"preferences":[]}', "MEMORY_INVALID"),
                          (b'[' * 2000, "MEMORY_INVALID")):
            with self.subTest(code=code, size=len(raw)):
                self.path.write_bytes(raw)
                self.assertIn(code, load_preferences(self.path).diagnostics)
                self.assertFalse(self.learn().written)
                self.assertEqual(self.path.read_bytes(), raw)
        self.assertTrue(clear_preferences(self.path).written)
        self.assertEqual(load_preferences(self.path), PreferenceSnapshot())

    def test_unreadable_and_oversized_memory(self):
        with patch.object(Path, "open", side_effect=PermissionError("synthetic private path")):
            snapshot = load_preferences(self.path)
        self.assertEqual(snapshot.diagnostics, ("MEMORY_UNREADABLE",))
        self.assertNotIn("synthetic", repr(snapshot))
        self.path.write_bytes(b" " * (MAX_PREFERENCE_BYTES + 1))
        self.assertEqual(load_preferences(self.path).diagnostics, ("MEMORY_TOO_LARGE",))
        self.assertFalse(self.learn().written)

    def test_capacity_preserves_records_but_allows_update_and_delete(self):
        records = tuple(SkillPreference("technical_writing", f"skill-{i:03}", "USER_SPECIFIED", 1, DAY)
                        for i in range(256))
        self.path.write_text(json.dumps(PreferenceSnapshot(records).to_mapping()), encoding="utf-8")
        before = self.path.read_bytes()
        result = self.learn()
        self.assertIn("MEMORY_CAPACITY", result.diagnostics)
        self.assertEqual(before, self.path.read_bytes())
        key = records[0].key
        changed = self.learn(learning_decision=(key,), user_observations=({"preferred_skill_id": key[1], "source": "USER_SPECIFIED"},))
        self.assertEqual(changed.snapshot.preferences[0].use_count, 2)
        clear_preferences(self.path, key)
        self.assertTrue(self.learn().written)
        self.assertEqual(len(load_preferences(self.path).preferences), 256)

    def test_busy_lock_is_not_stolen_or_removed(self):
        self.learn()
        before = self.path.read_bytes()
        lock = self.path.with_name(self.path.name + ".lock")
        lock.write_bytes(b"")
        self.assertIn("MEMORY_BUSY", self.learn().diagnostics)
        self.assertTrue(lock.exists())
        self.assertEqual(before, self.path.read_bytes())

    def test_failed_replace_preserves_original_and_cleans_temporary_files(self):
        self.learn()
        before = self.path.read_bytes()
        with patch("codex_capability_router.preference_store.os.replace", side_effect=OSError("synthetic private path")):
            result = self.learn()
        self.assertFalse(result.written)
        self.assertEqual(result.diagnostics, ("MEMORY_WRITE_FAILED",))
        self.assertEqual(before, self.path.read_bytes())
        self.assertEqual(list(self.path.parent.iterdir()), [self.path])
        self.assertTrue(self.learn().written)

    def test_default_path_uses_codex_home_and_never_stores_the_path(self):
        with patch.dict(os.environ, {"CODEX_HOME": self.temporary.name}):
            result = update_preferences(learning_decision=(KEY,),
                user_observations=({"preferred_skill_id": KEY[1], "source": "USER_SPECIFIED"},),
                observed_on=DAY, skill_inventory=self.inventory)
        target = Path(self.temporary.name) / "capability-router" / "skill-preferences.json"
        self.assertTrue(result.written)
        self.assertNotIn(self.temporary.name, target.read_text(encoding="utf-8"))
        self.assertEqual(load_preferences(Path("//remote/share/prefs.json")).diagnostics, ("MEMORY_UNREADABLE",))

    def test_private_fields_patterns_ids_and_values_are_rejected_without_echo(self):
        record = SkillPreference(*KEY, "USER_SPECIFIED", 1, DAY).to_mapping()
        for field in ("raw_prompt", "source_code", "bug", "solution", "private_path", "credentials", "inventory", "hidden_reasoning"):
            self.path.write_text(json.dumps({"schema_version": 1, "preferences": [{**record, field: "synthetic content"}]}), encoding="utf-8")
            self.assertEqual(load_preferences(self.path).diagnostics, ("MEMORY_INVALID",))
            self.assertFalse(self.learn(user_observations=({"preferred_skill_id": KEY[1], "source": "USER_SPECIFIED", field: "synthetic"},)).written)
        for key in (("a" * 65, KEY[1]), ("project/file.py", KEY[1]), ("code_modification", "C:\\private\\file"),
                    ("code_modification", "ghp_" + "x" * 40), ("code_modification", "sk-proj-" + "x" * 40)):
            with self.subTest(key_type=len(key[0])):
                result = self.learn(learning_decision=(key,))
                self.assertEqual(result.diagnostics, ("MEMORY_INVALID_LEARNING",))
                self.assertNotIn("private", repr(result))

    def test_strict_counts_dates_boolean_and_duplicate_records(self):
        record = SkillPreference(*KEY, "USER_SPECIFIED", 1, DAY)
        for kwargs in ({"use_count": True}, {"use_count": 0}, {"last_used": "2026-02-30"},
                       {"last_used": "20260101"}, {"enabled": 1}, {"preferred_skill_id": "C:private"}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                replace(record, **kwargs)
        with self.assertRaises(ValueError):
            PreferenceSnapshot((record, record))


if __name__ == "__main__":
    unittest.main()
