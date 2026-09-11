"""Preference integration using synthetic Skills and explicit Host decisions."""

from dataclasses import replace
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from codex_capability_router.inventory import refresh_skill_inventory_snapshot
from codex_capability_router.preferences import PreferenceSnapshot, SkillPreference, SkillPreferenceInput
from codex_capability_router.route_context import prepare_route_context, ValidatedDecisionPayloads, ValidatedSkillSelection
from codex_capability_router.routing import SelectionRouteInput, route
from codex_capability_router.selection import handoff_full_instructions
from codex_capability_router.skill_plan import build_skill_root_plan, SkillRootSpec, ROOT_KIND_RUNTIME_EXTRA
from tests.test_beta10_decision_coverage import _responses
from tests.test_route_context_phase2 import _analysis, _write_skill


EXAMPLES = (("code_modification", "code-comments"), ("zh_tw_writing", "humanizer-zh"),
            ("substantial_project_work", "work-log"))


class SkillPreferenceMemoryTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        for skill_id in ("baseline", *(key[1] for key in EXAMPLES), "source-notes"):
            _write_skill(self.root, skill_id)
        self.analysis = _analysis("Synthetic generic task")
        self.memory = PreferenceSnapshot(tuple(SkillPreference(*key, "USER_SPECIFIED", 1, "2026-01-01") for key in EXAMPLES))

    def request(self, selected=("baseline",), explicit=(), snapshot=None):
        context = prepare_route_context(self.analysis, skill_roots=(self.root,), explicit_skill_ids=explicit,
                                        skill_inventory_snapshot=snapshot)
        selection = ValidatedSkillSelection(self.analysis.task_summary,
                    tuple((skill_id, "Host normal selection") for skill_id in selected),
                    "selected" if selected else "no_matching_skill")
        return SelectionRouteInput(self.analysis.task_summary, (self.root,), selected, selection.to_mapping(),
            explicit_skill_ids=explicit, skill_inventory_snapshot=snapshot, skill_context=context,
            validated_decision_payloads=ValidatedDecisionPayloads(self.analysis, selection),
            skill_batch_decisions=_responses(context.inventory_sweep, context.context_fingerprint, selected))

    def with_memory(self, request, matches=(EXAMPLES[0],), **kwargs):
        args = dict(task_patterns=("code_modification",), snapshot=self.memory, matched_preferences=matches,
                    task_fingerprint=request.skill_context.context_fingerprint,
                    sweep_fingerprint=request.skill_context.inventory_sweep.fingerprint,
                    memory_fingerprint=self.memory.fingerprint)
        args.update(kwargs)
        return replace(request, preference_input=SkillPreferenceInput(**args))

    def snapshot(self):
        plan = build_skill_root_plan(include_fixed_global=False,
            additional_roots=(SkillRootSpec(self.root, "TEST", ROOT_KIND_RUNTIME_EXTRA),))
        return refresh_skill_inventory_snapshot(plan)

    def test_three_preferences_are_added_only_from_host_matches_and_preserve_batch(self):
        for key in EXAMPLES:
            with self.subTest(key=key):
                request = self.request()
                baseline = route(request)
                caller_payload = request.final_selection.copy()
                receipt = route(self.with_memory(request, (key,), task_patterns=(key[0],)))
                self.assertEqual([item["id"] for item in receipt.selected_skills], ["baseline", key[1]])
                self.assertIn(key[1], receipt.full_handoff_skills)
                self.assertEqual(receipt.selection_state, "FINALIZED")
                evidence = receipt.preference_evidence
                self.assertEqual(evidence["selection_provenance"][-1], {"id": key[1], "source": "MEMORY_ADDED"})
                self.assertEqual(evidence["host_selected_skill_ids"], ["baseline"])
                self.assertEqual(receipt["skill_metrics"]["decision_coverage"], baseline["skill_metrics"]["decision_coverage"])
                self.assertEqual(receipt["skill_metrics"]["skill_selected_total"], 2)
                self.assertEqual(request.final_selection, caller_payload)
                self.assertEqual(receipt.selection_payload()["selected_skills"][-1].keys(), {"id", "reason"})

    def test_model_and_explicit_selection_are_not_duplicated_or_relabeled_memory(self):
        for explicit in ((), ("code-comments",)):
            request = self.request(("baseline", "code-comments"), explicit=explicit)
            receipt = route(self.with_memory(request))
            self.assertEqual(len(receipt.selected_skills), 2)
            self.assertEqual(receipt.preference_evidence["memory_additions"], [])
            expected = "USER_SPECIFIED" if explicit else "MODEL_SELECTED"
            self.assertEqual(receipt.preference_evidence["selection_provenance"][-1]["source"], expected)
            self.assertEqual(receipt.selected_skills[-1]["reason"], "Host normal selection")

    def test_memory_stage_runs_after_base_selection_and_batch_validation(self):
        """確認 production route 先固定 base selection，再進行 Memory handoff。"""
        request = self.with_memory(self.request(), (EXAMPLES[0],))
        from codex_capability_router.selection import preliminary_select as production_preliminary_select
        calls = []

        def observe_preliminary(preparation, selected_ids):
            calls.append(tuple(selected_ids))
            return production_preliminary_select(preparation, selected_ids)

        with patch("codex_capability_router.selection.preliminary_select", side_effect=observe_preliminary):
            receipt = route(request)
        self.assertEqual(calls[:2], [("baseline",), ("code-comments",)])
        self.assertEqual(receipt.preference_evidence["host_selected_skill_ids"], ["baseline"])
        self.assertEqual(receipt.preference_evidence["memory_additions"],
                         [{"id": "code-comments", "task_patterns": ["code_modification"]}])

    def test_user_exclusion_wins_and_conflicting_host_input_is_not_silently_fixed(self):
        receipt = route(self.with_memory(self.request(), excluded_skill_ids=("code-comments",)))
        self.assertEqual(len(receipt.selected_skills), 1)
        self.assertIn("MEMORY_USER_EXCLUDED", [item["code"] for item in receipt.preference_evidence["diagnostics"]])
        request = self.request(("baseline", "code-comments"))
        with self.assertRaisesRegex(ValueError, "explicit Skill exclusion"):
            route(self.with_memory(request, excluded_skill_ids=("code-comments",)))

    def test_missing_disabled_forged_and_unselected_memory_cannot_add(self):
        missing = SkillPreference("image_creation", "missing-skill", "USER_SPECIFIED", 1, "2026-01-01")
        disabled = replace(self.memory.preferences[0], enabled=False)
        for record, code in ((missing, "MEMORY_SKILL_MISSING"), (disabled, "MEMORY_DISABLED")):
            memory = PreferenceSnapshot((record,))
            receipt = route(self.with_memory(self.request(), (record.key,), snapshot=memory, memory_fingerprint=memory.fingerprint))
            self.assertEqual(len(receipt.selected_skills), 1)
            self.assertEqual(receipt.preference_evidence["diagnostics"][0]["code"], code)
        receipt = route(self.with_memory(self.request(), (("unknown_pattern", "source-notes"),)))
        self.assertEqual(receipt.preference_evidence["diagnostics"][0]["code"], "MEMORY_KEY_MISSING")
        self.assertEqual(len(receipt.selected_skills), 1)

    def test_unrelated_task_and_high_use_count_do_not_create_python_matches(self):
        memory = PreferenceSnapshot(tuple(replace(item, use_count=1000) for item in self.memory.preferences))
        receipt = route(self.with_memory(self.request(), (), snapshot=memory,
                        memory_fingerprint=memory.fingerprint, task_patterns=("image_creation",)))
        self.assertEqual([item["id"] for item in receipt.selected_skills], ["baseline"])

    def test_host_may_match_different_pattern_wording_and_new_skill(self):
        record = SkillPreference("generic_source_documentation", "source-notes", "USER_MANUALLY_ADDED", 1, "2026-01-01")
        memory = PreferenceSnapshot((record,))
        receipt = route(self.with_memory(self.request(), (record.key,), task_patterns=("technical_writing",),
                        snapshot=memory, memory_fingerprint=memory.fingerprint))
        self.assertEqual(receipt.selected_skills[-1]["id"], "source-notes")

    def test_multiple_patterns_for_one_skill_deduplicate_and_append_sorted(self):
        another = SkillPreference("technical_writing", "code-comments", "USER_SPECIFIED", 1, "2026-01-01")
        memory = PreferenceSnapshot((*self.memory.preferences, another))
        matches = tuple(item.key for item in reversed(memory.preferences))
        receipt = route(self.with_memory(self.request(), matches, snapshot=memory, memory_fingerprint=memory.fingerprint))
        self.assertEqual([item["id"] for item in receipt.selected_skills], ["baseline", "code-comments", "humanizer-zh", "work-log"])
        self.assertEqual(len(receipt.full_handoff_skills), 4)

    def test_empty_and_disabled_memory_preserve_entire_receipt_and_fingerprint(self):
        request = self.request()
        baseline = route(request).to_mapping()
        empty = PreferenceSnapshot()
        for altered in (self.with_memory(request, (), snapshot=empty, memory_fingerprint=empty.fingerprint),
                        self.with_memory(request, enabled=False)):
            self.assertEqual(route(altered).to_mapping(), baseline)

    def test_corrupt_and_unreadable_memory_keep_normal_selection_and_diagnostic(self):
        for code in ("MEMORY_INVALID", "MEMORY_UNREADABLE"):
            memory = PreferenceSnapshot(diagnostics=(code,))
            receipt = route(self.with_memory(self.request(), (), snapshot=memory, memory_fingerprint=memory.fingerprint))
            self.assertEqual([item["id"] for item in receipt.selected_skills], ["baseline"])
            self.assertEqual(receipt.preference_evidence["diagnostics"], [{"code": code}])

    def test_each_stale_preference_binding_fails_open_but_stale_batch_still_fails(self):
        request = self.request()
        for field in ("task_fingerprint", "sweep_fingerprint", "memory_fingerprint"):
            receipt = route(self.with_memory(request, **{field: "0" * 64}))
            self.assertEqual(len(receipt.selected_skills), 1)
            self.assertEqual(receipt.preference_evidence["diagnostics"], [{"code": "MEMORY_STALE"}])
        broken = replace(request, skill_batch_decisions=({**request.skill_batch_decisions[0], "task_fingerprint": "0" * 64},))
        with self.assertRaises(ValueError):
            route(self.with_memory(broken))

    def test_needs_detail_cannot_be_promoted_and_missing_batches_remain_partial(self):
        request = self.request()
        responses = tuple({**response, "dispositions": {**response["dispositions"], "code-comments": "needs_detail"}}
                          for response in request.skill_batch_decisions)
        receipt = route(self.with_memory(replace(request, skill_batch_decisions=responses)))
        self.assertEqual(len(receipt.selected_skills), 1)
        self.assertEqual(receipt["skill_metrics"]["skill_unresolved_total"], 1)
        self.assertEqual(receipt.preference_evidence["diagnostics"][0]["code"], "MEMORY_NEEDS_DETAIL")
        receipt = route(self.with_memory(replace(request, skill_batch_decisions=())))
        self.assertEqual(len(receipt.selected_skills), 2)
        self.assertEqual(receipt["skill_metrics"]["skill_semantically_considered_total"], 0)
        self.assertEqual(receipt["skill_metrics"]["skill_semantic_coverage_status"], "PARTIAL")

    def test_receipt_provenance_is_detached_and_affects_fingerprint(self):
        request = self.request()
        baseline = route(request)
        receipt = route(self.with_memory(request, ()))
        self.assertNotEqual(receipt.receipt_fingerprint, baseline.receipt_fingerprint)
        fingerprint = receipt.receipt_fingerprint
        receipt.preference_evidence["selection_provenance"].clear()
        self.assertEqual(receipt.receipt_fingerprint, fingerprint)

    def test_route_never_calls_persistence(self):
        with patch("codex_capability_router.preference_store.load_preferences", side_effect=AssertionError("route read store")), \
             patch("codex_capability_router.preference_store.update_preferences", side_effect=AssertionError("route wrote store")):
            self.assertEqual(len(route(self.with_memory(self.request())).selected_skills), 2)

    def test_unsafe_memory_handoff_is_optional_but_baseline_failure_is_not(self):
        request = self.with_memory(self.request())
        def failed_memory(inventory, preliminary):
            if "code-comments" in preliminary.skill_ids:
                raise ValueError("synthetic private source failure")
            return handoff_full_instructions(inventory, preliminary)
        with patch("codex_capability_router.selection.handoff_full_instructions", side_effect=failed_memory):
            receipt = route(request)
        self.assertEqual(len(receipt.selected_skills), 1)
        self.assertEqual(receipt.preference_evidence["diagnostics"], [{"code": "MEMORY_HANDOFF_REJECTED", "id": "code-comments"}])
        with patch("codex_capability_router.selection.handoff_full_instructions", side_effect=ValueError("baseline unsafe")):
            with self.assertRaisesRegex(ValueError, "baseline unsafe"):
                route(request)

    def test_instruction_refresh_is_bounded_and_preserves_cached_snapshot(self):
        snapshot = self.snapshot()
        request = self.with_memory(self.request(snapshot=snapshot))
        path = self.root / "code-comments" / "SKILL.md"
        path.write_text(path.read_text(encoding="utf-8") + "Changed instructions\n", encoding="utf-8")
        from codex_capability_router.selection import handoff_with_selected_skill_refresh
        fingerprint = snapshot.inventory_fingerprint
        with patch("codex_capability_router.selection.handoff_with_selected_skill_refresh", wraps=handoff_with_selected_skill_refresh) as refreshed:
            receipt = route(request)
        self.assertEqual(len(receipt.selected_skills), 2)
        self.assertEqual(snapshot.inventory_fingerprint, fingerprint)
        self.assertEqual(refreshed.call_count, 2)  # baseline (no refresh), memory (one targeted refresh)
        self.assertEqual(receipt["skill_metrics"]["decision_coverage"]["fingerprint"], request.skill_context.inventory_sweep.fingerprint)

    def test_changed_metadata_or_identity_requires_revalidation_without_breaking_baseline(self):
        snapshot = self.snapshot()
        request = self.with_memory(self.request(snapshot=snapshot))
        path = self.root / "code-comments" / "SKILL.md"
        path.write_text(path.read_text(encoding="utf-8").replace("description:", "description: changed "), encoding="utf-8")
        receipt = route(request)
        self.assertEqual(len(receipt.selected_skills), 1)
        self.assertEqual(receipt.preference_evidence["diagnostics"][0]["code"], "SELECTION_REVALIDATION_REQUIRED")

    def test_empty_host_selection_can_receive_memory_without_fabricating_batch_selection(self):
        receipt = route(self.with_memory(self.request(())))
        self.assertEqual(receipt.selection_status, "selected")
        self.assertEqual(receipt["skill_metrics"]["decision_coverage"]["selected_count"], 0)
        self.assertEqual(receipt.selected_skills[0]["id"], "code-comments")

    def test_late_memory_source_change_is_rejected_at_final_validation(self):
        request = self.with_memory(self.request(), (EXAMPLES[0], EXAMPLES[1]))
        path = self.root / "code-comments" / "SKILL.md"
        def change_previous(inventory, preliminary):
            instructions = handoff_full_instructions(inventory, preliminary)
            if "humanizer-zh" in preliminary.skill_ids:
                path.write_text(path.read_text(encoding="utf-8") + "late change\n", encoding="utf-8")
            return instructions
        with patch("codex_capability_router.selection.handoff_full_instructions", side_effect=change_previous):
            receipt = route(request)
        self.assertEqual([item["id"] for item in receipt.selected_skills], ["baseline", "humanizer-zh"])
        self.assertNotIn("code-comments", receipt.full_handoff_skills)
        self.assertEqual(receipt.preference_evidence["diagnostics"][0]["code"], "MEMORY_HANDOFF_REJECTED")

    def test_baseline_becoming_stale_during_memory_handoff_is_not_swallowed(self):
        request = self.with_memory(self.request())
        path = self.root / "baseline" / "SKILL.md"
        def change_baseline(inventory, preliminary):
            instructions = handoff_full_instructions(inventory, preliminary)
            if "code-comments" in preliminary.skill_ids:
                path.write_text(path.read_text(encoding="utf-8") + "late baseline change\n", encoding="utf-8")
            return instructions
        with patch("codex_capability_router.selection.handoff_full_instructions", side_effect=change_baseline):
            with self.assertRaisesRegex(ValueError, "fingerprint is stale"):
                route(request)

    def test_only_one_memory_refresh_is_allowed_and_repeated_mismatch_is_rejected(self):
        snapshot = self.snapshot()
        request = self.with_memory(self.request(snapshot=snapshot), (EXAMPLES[0], EXAMPLES[1]))
        for _, skill_id in EXAMPLES[:2]:
            path = self.root / skill_id / "SKILL.md"
            path.write_text(path.read_text(encoding="utf-8") + "new body\n", encoding="utf-8")
        receipt = route(request)
        self.assertEqual([item["id"] for item in receipt.selected_skills], ["baseline", "code-comments"])
        self.assertEqual(receipt.preference_evidence["diagnostics"][0]["code"], "HANDOFF_REJECTION_AFTER_ONE_REFRESH")
        from codex_capability_router.selection import SkillHandoffFingerprintMismatch
        def always_changed(inventory, preliminary):
            if "code-comments" in preliminary.skill_ids:
                raise SkillHandoffFingerprintMismatch("code-comments")
            return handoff_full_instructions(inventory, preliminary)
        with patch("codex_capability_router.selection.handoff_full_instructions", side_effect=always_changed):
            receipt = route(self.with_memory(self.request(snapshot=snapshot)))
        self.assertEqual(len(receipt.selected_skills), 1)
        self.assertEqual(receipt.preference_evidence["diagnostics"][0]["code"], "HANDOFF_REJECTION_AFTER_ONE_REFRESH")

    def test_disappeared_source_and_controller_skill_are_never_rescued_by_memory(self):
        snapshot = self.snapshot()
        request = self.with_memory(self.request(snapshot=snapshot))
        (self.root / "code-comments" / "SKILL.md").unlink()
        receipt = route(request)
        self.assertEqual(len(receipt.selected_skills), 1)
        self.assertEqual(receipt.preference_evidence["diagnostics"][0]["code"], "MEMORY_HANDOFF_REJECTED")
        _write_skill(self.root, "controller-helper", controller=True)
        record = SkillPreference("code_modification", "controller-helper", "USER_SPECIFIED", 1, "2026-01-01")
        memory = PreferenceSnapshot((record,))
        receipt = route(self.with_memory(self.request(), (record.key,), snapshot=memory, memory_fingerprint=memory.fingerprint))
        self.assertEqual(len(receipt.selected_skills), 1)
        self.assertEqual(receipt.preference_evidence["diagnostics"][0]["code"], "MEMORY_SKILL_MISSING")


if __name__ == "__main__":
    unittest.main()
