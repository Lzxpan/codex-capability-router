"""beta.4 unknown Host hierarchy fallback 與 zero-miss consideration regression。"""

from __future__ import annotations

from dataclasses import replace
import unittest

from codex_capability_router.host_snapshot import prepare_host_capability_snapshot
from codex_capability_router.provider_adapters import discover_provider_inventory
from codex_capability_router.routing import SelectionReceipt
from codex_capability_router.supporting_context import (
    ExecutionAttempt,
    ExecutionNeed,
    SupportingCapabilitySelection,
    prepare_supporting_context,
)


def _snapshot(*records: dict[str, object]):
    """建立 bounded controller projection fixture；不代表 live Host source。"""

    return prepare_host_capability_snapshot(
        records,
        snapshot_id="beta4-host-tool-smoke",
        session_scope="current-session",
        source="controller-session-registry",
    )


class Beta4HostToolFallbackTests(unittest.TestCase):
    """unknown hierarchy 不再阻斷 formalization 或 Provider sweep。"""

    def test_unknown_hierarchy_becomes_host_tool_and_is_considered(self) -> None:
        snapshot = _snapshot(
            {
                "namespace": "opaque",
                "action_name": "tool",
                "display_name": "opaque.tool",
                "description": None,
            },
        )
        inventory = discover_provider_inventory(host_capability_snapshot=snapshot)
        self.assertEqual([(item.kind, item.provider_id) for item in inventory.provider_declarations], [("host_tool", "opaque.tool")])
        declaration = inventory.provider_declarations[0]
        self.assertEqual(declaration.raw_external_identity, "opaque.tool")
        self.assertEqual(declaration.hierarchy_state, "UNKNOWN")
        context = prepare_supporting_context(
            (ExecutionNeed("inspect", "An exposed Host capability may help."),),
            host_capability_snapshot=snapshot,
        )
        self.assertEqual(context.metrics.metadata_opaque_count, 1)
        self.assertEqual(context.metrics.selectable_count, 1)
        self.assertEqual(context.metrics.never_considered_count, 1)
        self.assertEqual(context.metrics.semantically_considered_count, 0)
        self.assertEqual(context.provider_digests[0].kind, "host_tool")
        self.assertEqual(context.provider_digests[0].hierarchy_state, "UNKNOWN")

    def test_unknown_control_plane_like_name_is_not_guessed_away(self) -> None:
        snapshot = _snapshot(
            {
                "namespace": "controller",
                "action_name": "manage",
                "display_name": "Controller management",
                "description": "Public capability with no structural hierarchy evidence.",
            },
        )
        inventory = discover_provider_inventory(host_capability_snapshot=snapshot)
        self.assertEqual(inventory.provider_declarations[0].kind, "host_tool")
        self.assertNotIn("control_plane", inventory.provider_declarations[0].kind)

    def test_known_control_plane_remains_excluded(self) -> None:
        snapshot = _snapshot(
            {
                "namespace": "controller",
                "action_name": "manage",
                "display_name": "Controller management",
                "description": "Controller-owned control plane.",
                "hierarchy": "control_plane",
            },
        )
        inventory = discover_provider_inventory(host_capability_snapshot=snapshot)
        self.assertEqual(inventory.provider_declarations, ())
        self.assertEqual(inventory.host_snapshot_intentionally_excluded_count, 1)

    def test_known_hierarchy_keeps_precise_formal_kind(self) -> None:
        snapshot = _snapshot(
            {
                "namespace": "native",
                "action_name": "tool",
                "display_name": "Native tool",
                "description": "A top-level native capability.",
                "hierarchy": "host_native",
            },
            {
                "namespace": "calendar",
                "action_name": "list",
                "display_name": "Calendar list",
                "description": "Lists calendar items.",
                "hierarchy": "app_child",
                "parent_kind": "app",
                "parent_identity": "calendar_app",
            },
            {
                "namespace": "research",
                "action_name": "search",
                "display_name": "Research search",
                "description": "Searches a configured server.",
                "hierarchy": "mcp_child",
                "parent_kind": "mcp",
                "parent_identity": "research_mcp",
            },
        )
        inventory = discover_provider_inventory(host_capability_snapshot=snapshot)
        self.assertEqual(
            {(item.kind, item.provider_id) for item in inventory.provider_declarations},
            {("builtin_tool", "native.tool"), ("app", "calendar_app"), ("mcp", "research_mcp")},
        )
        self.assertNotIn("host_tool", {item.kind for item in inventory.provider_declarations})

    def test_host_tool_structurally_upgrades_without_duplicate(self) -> None:
        snapshot = _snapshot(
            {
                "namespace": "host",
                "action_name": "tool",
                "display_name": "Unknown host tool",
                "description": "The same exposed capability before hierarchy evidence arrived.",
            },
        )
        inventory = discover_provider_inventory(
            host_capability_snapshot=snapshot,
            host_native_registry=(
                {
                    "provider_id": "host.tool",
                    "name": "Known native tool",
                    "description": "The same capability with trusted native evidence.",
                    "top_level": True,
                    "kind": "builtin_tool",
                    "callable_exposure": True,
                },
            ),
        )
        self.assertEqual([(item.kind, item.provider_id) for item in inventory.provider_declarations], [("builtin_tool", "host.tool")])
        self.assertTrue(any(item.startswith("structural_identity_upgraded:") for item in inventory.diagnostics))

    def test_negative_readiness_does_not_remove_host_tool_candidate(self) -> None:
        snapshot = _snapshot(
            {
                "namespace": "host",
                "action_name": "unavailable",
                "display_name": "Known unavailable host tool",
                "description": "A public capability whose runtime status is negative.",
            },
        )
        inventory = discover_provider_inventory(host_capability_snapshot=snapshot)
        declaration = replace(inventory.provider_declarations[0], explicit_negative_reason="runtime unavailable")
        context = prepare_supporting_context(
            (ExecutionNeed("inspect", "The capability remains visible for semantic consideration."),),
            provider_declarations=(declaration,),
        )
        self.assertEqual(context.metrics.selectable_count, 1)
        self.assertEqual(context.metrics.never_considered_count, 1)
        self.assertEqual(context.metrics.semantically_considered_count, 0)

    def test_receipt_and_execution_attempt_accept_host_tool(self) -> None:
        receipt = SelectionReceipt._from_route(
            task_summary="beta4 host tool receipt smoke",
            candidate_skills=(),
            preliminary_selected_skills=(),
            full_handoff_skills=(),
            selected_skills=[],
            selection_status="no_matching_skill",
            expanded_retrieval=False,
            correction=False,
            selection_state="FINALIZED",
            execution_needs=({"need": "inspect", "reason": "A Host capability may help."},),
            supporting_selection_status="selected",
            selected_supporting_capabilities=(
                SupportingCapabilitySelection("host_tool", "host.tool", "Visible Host capability.").to_mapping(),
            ),
            selected_supporting_provider_evidence=(
                {
                    "kind": "host_tool",
                    "canonical_provider_id": "host.tool",
                    "presence_state": "PRESENT",
                    "readiness_state": "PRESENT_UNVERIFIED",
                    "provenance": ["host-session-capability-snapshot"],
                    "digest_fingerprint": "a" * 64,
                    "hierarchy_state": "UNKNOWN",
                    "existence_evidence_state": "HOST_SESSION_EXPOSED",
                    "metadata_quality": "OPAQUE",
                    "raw_external_identity": "host.tool",
                },
            ),
        )
        selected = receipt.to_mapping()["selected_supporting_capabilities"][0]
        self.assertEqual(selected["kind"], "host_tool")
        self.assertEqual(selected["hierarchy_state"], "UNKNOWN")
        self.assertEqual(selected["raw_external_identity"], "host.tool")
        attempt = ExecutionAttempt(
            selection_receipt_fingerprint=receipt.receipt_fingerprint,
            execution_need="inspect",
            provider_kind="host_tool",
            provider_id="host.tool",
            readiness_state="PRESENT_UNVERIFIED",
            outcome="UNAVAILABLE",
            error_category="runtime unavailable",
        )
        self.assertEqual(attempt.to_mapping()["provider_kind"], "host_tool")

    def test_large_unknown_inventory_is_fully_considered(self) -> None:
        snapshot = _snapshot(
            *(
                {
                    "namespace": "host",
                    "action_name": f"tool_{index:03d}",
                    "display_name": f"host.tool_{index:03d}",
                    "description": None,
                }
                for index in range(125)
            )
        )
        context = prepare_supporting_context(
            (ExecutionNeed("inspect", "All exposed capabilities must be considered."),),
            host_capability_snapshot=snapshot,
        )
        self.assertEqual(context.metrics.selectable_count, 125)
        self.assertEqual(context.metrics.never_considered_count, 125)
        self.assertEqual(context.metrics.semantically_considered_count, 0)
        self.assertGreater(context.metrics.sweep_batch_count, 1)


if __name__ == "__main__":
    unittest.main()
