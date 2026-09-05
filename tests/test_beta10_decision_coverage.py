"""Observed decision coverage, distinct from deterministic digest staging."""

from dataclasses import replace
from pathlib import Path
import tempfile
import unittest

from codex_capability_router.inventory_sweep import build_inventory_sweep, validate_sweep_decisions
from codex_capability_router.route_context import prepare_route_context
from codex_capability_router.supporting_context import prepare_supporting_context
from tests.test_route_context_phase2 import _analysis, _write_skill
from tests.test_supporting_context_phase3 import _need, _provider
from tests import test_supporting_decision_phase4 as phase4
from codex_capability_router.routing import route
from codex_capability_router.inventory import refresh_skill_inventory
from codex_capability_router.provider_adapters import adapt_codex_mcp_cli_inventory, discover_active_plugin_children


def _responses(sweep, task, selected=()):
    return tuple({"task_fingerprint": task, "sweep_fingerprint": sweep.fingerprint,
                  "batch_index": index, "dispositions": {identity: "selected" if identity in selected else "not_selected" for identity in batch}}
                 for index, batch in enumerate(sweep.batches))


class DecisionCoverageTests(unittest.TestCase):
    def test_discovery_inventories_do_not_report_semantic_decisions(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _write_skill(root, "alpha")
            skill = refresh_skill_inventory((root,))
            mcp = adapt_codex_mcp_cli_inventory(({"name": "example", "enabled": True},))
            plugin = discover_active_plugin_children(({
                "plugin_id": "example@local", "present": True,
                "capabilities": ({"kind": "app", "provider_id": "example", "name": "Example"},),
            },))
            for inventory in (skill, mcp, plugin):
                with self.subTest(inventory=type(inventory).__name__):
                    self.assertEqual(inventory.semantically_considered_count, 0)
                    self.assertEqual(inventory.never_considered_count, 1)

    def test_staging_500_digests_without_responses_considers_zero(self):
        sweep = build_inventory_sweep(tuple({"id": f"skill-{i:03}"} for i in range(500)), identity_field="id")
        self.assertEqual(sweep.batch_count, 21)
        self.assertEqual(len(sweep.considered_ids), 0)
        self.assertEqual(len(sweep.never_considered_ids), 500)

    def test_skill_and_provider_preparation_do_not_invent_decisions(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _write_skill(root, "alpha")
            context = prepare_route_context(_analysis(), skill_roots=(root,))
            self.assertEqual(context.metrics.semantically_considered_count, 0)
            self.assertEqual(context.metrics.never_considered_count, 1)
        context = prepare_supporting_context((_need(),), provider_declarations=(_provider(),))
        self.assertEqual(context.metrics.semantically_considered_count, 0)
        self.assertEqual(context.metrics.never_considered_count, 1)

    def test_missing_batches_and_needs_detail_remain_partial(self):
        sweep = build_inventory_sweep(({"id": "alpha"}, {"id": "beta"}), identity_field="id", item_limit=1)
        responses = _responses(sweep, "a" * 64)
        partial = validate_sweep_decisions(sweep, responses[:1], task_fingerprint="a" * 64)
        self.assertEqual(partial.to_mapping()["decision_received_count"], 1)
        self.assertEqual(partial.unresolved_ids, ("beta",))
        self.assertEqual(partial.to_mapping()["semantic_coverage_status"], "PARTIAL")
        detail = {**responses[1], "dispositions": {"beta": "needs_detail"}}
        partial = validate_sweep_decisions(sweep, (responses[0], detail), task_fingerprint="a" * 64)
        self.assertEqual(len(partial.decision_received_ids), 2)
        self.assertEqual(partial.unresolved_ids, ("beta",))
        complete = validate_sweep_decisions(sweep, responses, task_fingerprint="a" * 64)
        self.assertEqual(complete.to_mapping()["semantic_coverage_status"], "COMPLETE")
        self.assertEqual(complete.considered_ids, ("alpha", "beta"))

    def test_reject_stale_incomplete_extra_duplicate_or_conflicting_responses(self):
        sweep = build_inventory_sweep(({"id": "alpha", "description": "old"},), identity_field="id")
        response = _responses(sweep, "a" * 64)[0]
        invalid = (
            {**response, "task_fingerprint": "b" * 64},
            {**response, "sweep_fingerprint": "b" * 64},
            {**response, "dispositions": {}},
            {**response, "dispositions": {"alpha": "not_selected", "extra": "not_selected"}},
            {**response, "dispositions": {"alpha": "invented"}},
            {**response, "dispositions": {"alpha": "selected"}},
            {**response, "batch_index": True},
            {**response, "batch_index": -1},
            {**response, "batch_index": 1},
            {**response, "all_considered": True},
        )
        for payloads in (*((item,) for item in invalid), (response, response)):
            with self.subTest(payloads=payloads), self.assertRaises(ValueError):
                validate_sweep_decisions(sweep, payloads, task_fingerprint="a" * 64)
        changed = build_inventory_sweep(({"id": "alpha", "description": "new"},), identity_field="id")
        with self.assertRaises(ValueError):
            validate_sweep_decisions(changed, (response,), task_fingerprint="a" * 64)
        with self.assertRaises(ValueError):
            validate_sweep_decisions(sweep, (response,), task_fingerprint="a" * 64, selected_ids=("alpha",))

    def test_provider_sweep_cannot_replay_decisions_for_different_execution_needs(self):
        first = prepare_supporting_context((_need(),), provider_declarations=(_provider(),))
        second = prepare_supporting_context((replace(_need(), need="different execution need"),), provider_declarations=(_provider(),))
        with self.assertRaises(ValueError):
            validate_sweep_decisions(second.inventory_sweep, _responses(first.inventory_sweep, "a" * 64), task_fingerprint="a" * 64)

    def test_finalized_route_requires_observed_skill_and_provider_decisions_for_complete_coverage(self):
        fixture = phase4.Phase4SupportingDecisionTests()
        fixture.setUp()
        self.addCleanup(fixture.tearDown)
        final = phase4.SupportingFinalSelection(
            (phase4.SupportingCapabilitySelection("mcp", "node_repl", "Inspect source"),), ()
        )
        request = fixture._route_request(fixture._decision(needs=(fixture.need,), final=final),
                                         provider_declarations=(fixture.provider,), readiness_evidence=(fixture.evidence,))
        receipt = route(request)
        self.assertEqual(receipt["selection_state"], "FINALIZED")
        for kind in ("skill", "provider"):
            metrics = receipt["skill_metrics" if kind == "skill" else "supporting_metrics"]
            self.assertEqual(metrics[f"{kind}_semantically_considered_total"], 0)
            self.assertEqual(metrics[f"{kind}_semantic_coverage_status"], "PARTIAL")
        task = request.skill_context.context_fingerprint
        completed = replace(request,
            skill_batch_decisions=_responses(request.skill_context.inventory_sweep, task, ("phase4-skill",)),
            supporting_batch_decisions=_responses(request.supporting_context.inventory_sweep, task, ("node_repl",)))
        receipt = route(completed)
        for kind in ("skill", "provider"):
            metrics = receipt["skill_metrics" if kind == "skill" else "supporting_metrics"]
            self.assertEqual(metrics[f"{kind}_decision_received_total"], 1)
            self.assertEqual(metrics[f"{kind}_semantic_coverage_status"], "COMPLETE")
        for field in ("skill_batch_decisions", "supporting_batch_decisions"):
            responses = getattr(completed, field)
            stale = ({**responses[0], "task_fingerprint": "0" * 64},)
            with self.subTest(field=field), self.assertRaises(ValueError):
                route(replace(completed, **{field: stale}))


if __name__ == "__main__":
    unittest.main()
