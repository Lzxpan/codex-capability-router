"""V1.1.2：最終選用須有批次證據，未選候選仍可維持部分覆蓋。"""

from dataclasses import replace
import unittest

from codex_capability_router.catalog import render_recommendations
from codex_capability_router.inventory_sweep import build_inventory_sweep, validate_sweep_decisions
from codex_capability_router.routing import SelectionRouteInput, route
from tests import test_supporting_decision_phase4 as phase4


class SelectedDecisionEvidenceTests(unittest.TestCase):
    """以公開 validator 與正式 route 驗證缺少證據的失敗邊界。"""

    def setUp(self):
        self.fixture = phase4.Phase4SupportingDecisionTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.tearDown)

    def test_selected_skill_without_batches_is_rejected(self):
        request = self.fixture._route_request(self.fixture._decision())
        with self.assertRaisesRegex(ValueError, "selected.*batch.*phase4-skill"):
            route(replace(request, skill_batch_decisions=()))

    def test_selected_provider_without_batches_is_rejected(self):
        final = phase4.SupportingFinalSelection(
            (phase4.SupportingCapabilitySelection("mcp", "node_repl", "Inspect source"),), ()
        )
        request = self.fixture._route_request(
            self.fixture._decision(needs=(self.fixture.need,), final=final),
            provider_declarations=(self.fixture.provider,), readiness_evidence=(self.fixture.evidence,),
        )
        # 此受控 fixture 明確選擇唯一 Skill；Provider 缺失不能由 Skill 證據補足。
        sweep = request.skill_context.inventory_sweep
        observed = ({
            "task_fingerprint": request.skill_context.context_fingerprint,
            "sweep_fingerprint": sweep.fingerprint, "batch_index": 0,
            "dispositions": {"phase4-skill": "selected"},
        },)
        with self.assertRaisesRegex(ValueError, "selected.*batch.*node_repl"):
            route(replace(request, skill_batch_decisions=observed, supporting_batch_decisions=()))

    def test_unrelated_received_batch_cannot_cover_a_missing_selected_batch(self):
        sweep = build_inventory_sweep(({"id": "alpha"}, {"id": "beta"}), identity_field="id", item_limit=1)
        response = {"task_fingerprint": "a" * 64, "sweep_fingerprint": sweep.fingerprint,
                    "batch_index": 1, "dispositions": {"beta": "not_selected"}}
        with self.assertRaisesRegex(ValueError, "selected.*batch.*alpha"):
            validate_sweep_decisions(sweep, (response,), task_fingerprint="a" * 64, selected_ids=("alpha",))

    def test_observed_selected_with_unreceived_unselected_batch_stays_partial(self):
        sweep = build_inventory_sweep(({"id": "alpha"}, {"id": "beta"}), identity_field="id", item_limit=1)
        response = {"task_fingerprint": "a" * 64, "sweep_fingerprint": sweep.fingerprint,
                    "batch_index": 0, "dispositions": {"alpha": "selected"}}
        result = validate_sweep_decisions(sweep, (response,), task_fingerprint="a" * 64, selected_ids=("alpha",))
        self.assertEqual(result.selected_ids, ("alpha",))
        self.assertEqual(result.never_considered_ids, ("beta",))
        self.assertEqual(result.to_mapping()["semantic_coverage_status"], "PARTIAL")

    def test_observed_selected_with_needs_detail_stays_partial(self):
        sweep = build_inventory_sweep(({"id": "alpha"}, {"id": "beta"}), identity_field="id")
        response = {"task_fingerprint": "a" * 64, "sweep_fingerprint": sweep.fingerprint,
                    "batch_index": 0, "dispositions": {"alpha": "selected", "beta": "needs_detail"}}
        result = validate_sweep_decisions(sweep, (response,), task_fingerprint="a" * 64, selected_ids=("alpha",))
        self.assertEqual(result.considered_ids, ("alpha",))
        self.assertEqual(result.unresolved_ids, ("beta",))
        self.assertEqual(result.to_mapping()["semantic_coverage_status"], "PARTIAL")

    def test_empty_selection_does_not_invent_candidate_decisions(self):
        for digests, status in (((), "COMPLETE"), (({"id": "alpha"},), "PARTIAL")):
            with self.subTest(status=status):
                sweep = build_inventory_sweep(digests, identity_field="id")
                result = validate_sweep_decisions(sweep, (), task_fingerprint="a" * 64)
                self.assertEqual(result.considered_ids, ())
                self.assertEqual(result.to_mapping()["semantic_coverage_status"], status)

    def test_legacy_call_is_preserved_and_labeled_without_observed_evidence(self):
        receipt = route(SelectionRouteInput(
            task_summary=self.fixture.analysis.task_summary, skill_roots=(self.fixture.root,),
            preliminary_skill_ids=("phase4-skill",), final_selection=self.fixture.skill_selection.to_mapping(),
        ))
        self.assertEqual(receipt.selection_state, "FINALIZED")
        self.assertIsNone(receipt.to_mapping()["task_analysis"])
        for locale, label in (("en", "Legacy compatibility"), ("zh-TW", "相容呼叫")):
            with self.subTest(locale=locale):
                output = render_recommendations(receipt, language=locale)
                self.assertIn(label, output)
                self.assertNotIn("`COMPLETE`", output)

    def test_public_reason_error_identifies_slash_without_relaxing_validation(self):
        request = SelectionRouteInput(
            task_summary=self.fixture.analysis.task_summary, skill_roots=(self.fixture.root,),
            preliminary_skill_ids=("phase4-skill",),
            final_selection={"task_summary": self.fixture.analysis.task_summary,
                             "selected_skills": [{"id": "phase4-skill", "reason": "Inspect TDS/NTC"}],
                             "selection_status": "selected"},
        )
        with self.assertRaisesRegex(ValueError, "slash"):
            route(request)


if __name__ == "__main__":
    unittest.main()
