"""HostCapabilitySnapshot bridge 與 generic Provider boundary regression tests。"""

from __future__ import annotations

import unittest

from codex_capability_router.host_snapshot import (
    HOST_SNAPSHOT_PROVENANCE,
    HOST_SNAPSHOT_TRUST_MARKER,
    HostCapabilitySnapshot,
    prepare_host_capability_snapshot,
)
from codex_capability_router.provider_adapters import (
    discover_host_capability_snapshot_inventory,
    discover_provider_inventory,
)
from codex_capability_router.routing import (
    SelectionRouteInput,
    prepare_route_input_from_controller_registry,
)
from codex_capability_router.supporting_context import (
    ExecutionNeed,
    ReadinessEvidenceCertificate,
    SupportingProviderDeclaration,
    prepare_supporting_context,
)


# 修改紀錄（2026-09-01，Steve Peng）
# 原始內容：既有 tests 只能用 raw registry mapping 驗證 generic builtin，沒有 Host-owned
# snapshot trust boundary、hierarchy classification、source merge 或 snapshot metrics。
# 修改原因：Host Capability Snapshot Bridge 必須證明 Host metadata 可完整進入同一條 Provider sweep，且不以 image/tool ID 特判。
# 修改後功能：覆蓋 empty/multiple/native/child/unknown/plugin、metadata gate、PRESENT_UNVERIFIED、
# exact readiness merge、deterministic batching、route trust boundary 與既有 exec compatibility。


def _snapshot(*capabilities: dict[str, object]) -> HostCapabilitySnapshot:
    """建立 controller-owned fixture envelope；不代表 live Host execution。"""

    return HostCapabilitySnapshot.from_trusted_envelope(
        {
            "trust_marker": HOST_SNAPSHOT_TRUST_MARKER,
            "snapshot_id": "session-snapshot-01",
            "source": "codex-controller-session",
            "session_scope": "current-session",
            "provenance": [HOST_SNAPSHOT_PROVENANCE],
            "capabilities": capabilities,
        }
    )


class HostCapabilitySnapshotTests(unittest.TestCase):
    """確認 snapshot 只提供 discovery evidence，semantic 判斷仍留給 LLM。"""

    def test_empty_snapshot_is_valid_and_has_zero_metrics(self) -> None:
        snapshot = _snapshot()
        inventory = discover_host_capability_snapshot_inventory(snapshot)
        self.assertEqual(snapshot.capabilities, ())
        self.assertEqual(snapshot.fingerprint, snapshot.fingerprint)
        self.assertEqual(inventory.discovered_count, 0)
        self.assertEqual(inventory.host_snapshot_capability_count, 0)

    def test_controller_projection_attaches_snapshot_to_production_route_input(self) -> None:
        request = SelectionRouteInput(
            task_summary="bridge smoke",
            skill_roots=(),
            preliminary_skill_ids=(),
            final_selection={
                "task_summary": "bridge smoke",
                "selected_skills": [],
                "selection_status": "no_matching_skill",
            },
        )
        prepared = prepare_route_input_from_controller_registry(
            request,
            (
                {
                    "namespace": "host",
                    "action_name": "public_tool",
                    "display_name": "Public tool",
                    "description": "A current-session public capability.",
                    "hierarchy": "host_native",
                },
            ),
            snapshot_id="bridge-smoke",
            session_scope="current-session",
        )
        self.assertIsInstance(prepared.host_capability_snapshot, HostCapabilitySnapshot)
        assert prepared.host_capability_snapshot is not None
        self.assertEqual(prepared.host_capability_snapshot.capabilities[0].canonical_id, "host.public_tool")

    def test_control_plane_is_structurally_excluded_and_counted(self) -> None:
        snapshot = prepare_host_capability_snapshot(
            (
                {
                    "namespace": "controller",
                    "action_name": "manage",
                    "display_name": "Controller management",
                    "description": "A controller control-plane capability.",
                    "hierarchy": "control_plane",
                },
            ),
            snapshot_id="control-plane-smoke",
            session_scope="current-session",
        )
        inventory = discover_host_capability_snapshot_inventory(snapshot)
        self.assertEqual(snapshot.control_plane_count, 1)
        self.assertEqual(snapshot.intentionally_excluded_count, 1)
        self.assertEqual(snapshot.missing_count, 0)
        self.assertEqual(inventory.provider_declarations, ())
        self.assertIn("host_snapshot_control_plane_excluded:controller.manage", inventory.diagnostics)
        self.assertEqual(inventory.host_snapshot_control_plane_count, 1)
        self.assertEqual(inventory.host_snapshot_intentionally_excluded_count, 1)

    def test_multiple_top_level_capabilities_become_builtin_providers(self) -> None:
        snapshot = _snapshot(
            {
                "namespace": "functions",
                "action_name": "exec_command",
                "display_name": "Command execution",
                "description": "Runs a bounded repository command.",
                "hierarchy": "host_native",
            },
            {
                "namespace": "visual",
                "action_name": "render_asset",
                "display_name": "Visual asset renderer",
                "description": "Creates an original visual asset.",
                "hierarchy": "host_native",
            },
        )
        inventory = discover_host_capability_snapshot_inventory(snapshot)
        self.assertEqual(
            [(item.kind, item.provider_id) for item in inventory.provider_declarations],
            [("builtin_tool", "functions.exec_command"), ("builtin_tool", "visual.render_asset")],
        )
        self.assertEqual(inventory.host_snapshot_builtin_count, 2)

    def test_app_mcp_plugin_and_unknown_hierarchy_keep_boundaries(self) -> None:
        snapshot = _snapshot(
            {
                "namespace": "calendar",
                "action_name": "list_events",
                "display_name": "List events",
                "description": "Reads events for a date range.",
                "hierarchy": "app_child",
                "parent_kind": "app",
                "parent_identity": "calendar_app",
            },
            {
                "namespace": "research",
                "action_name": "search",
                "display_name": "Search research",
                "description": "Searches the configured research server.",
                "hierarchy": "mcp_child",
                "parent_kind": "mcp",
                "parent_identity": "research_mcp",
            },
            {
                "namespace": "package",
                "action_name": "bundled_action",
                "display_name": "Bundled action",
                "description": "An action declared by a Plugin package.",
                "hierarchy": "plugin_child",
                "parent_kind": "plugin",
                "parent_identity": "active_package",
            },
            {
                "namespace": "opaque",
                "action_name": "action",
                "display_name": "Unclassified action",
                "description": "A Host capability with unknown hierarchy.",
                "hierarchy": "unknown",
            },
        )
        inventory = discover_host_capability_snapshot_inventory(snapshot)
        self.assertEqual({(item.kind, item.provider_id) for item in inventory.provider_declarations}, {
            ("app", "calendar_app"),
            ("mcp", "research_mcp"),
            ("host_tool", "opaque.action"),
        })
        self.assertIn("host_snapshot_plugin_child_not_formal:package.bundled_action", inventory.diagnostics)
        self.assertIn("DISCOVERED_UNCLASSIFIED_HOST_CAPABILITY:opaque.action", inventory.diagnostics)
        self.assertEqual(inventory.host_snapshot_app_child_count, 1)
        self.assertEqual(inventory.host_snapshot_mcp_child_count, 1)
        self.assertEqual(inventory.host_snapshot_unclassified_count, 1)
        unknown = next(item for item in inventory.provider_declarations if item.provider_id == "opaque.action")
        self.assertEqual(unknown.hierarchy_state, "UNKNOWN")

    def test_metadata_quality_preserves_opaque_record_for_consideration(self) -> None:
        snapshot = _snapshot(
            {
                "namespace": "opaque",
                "action_name": "only_id",
                "display_name": "opaque.only_id",
                "description": None,
                "hierarchy": "host_native",
            }
        )
        context = prepare_supporting_context(
            (ExecutionNeed("run task", "A runtime capability may help."),),
            host_capability_snapshot=snapshot,
        )
        self.assertEqual(context.metrics.host_snapshot_capability_count, 1)
        self.assertEqual(context.metrics.selectable_count, 1)
        self.assertEqual(context.metrics.metadata_opaque_count, 1)
        self.assertEqual(context.provider_digests[0].metadata_quality.value, "OPAQUE")
        self.assertEqual(context.metrics.never_considered_count, 0)

    def test_snapshot_provider_enters_sweep_as_present_unverified(self) -> None:
        snapshot = _snapshot(
            {
                "namespace": "visual",
                "action_name": "generate",
                "display_name": "Image generation",
                "description": "Generates original visual assets.",
                "hierarchy": "host_native",
            }
        )
        context = prepare_supporting_context(
            (ExecutionNeed("create visuals", "A visual capability is material."),),
            host_capability_snapshot=snapshot,
        )
        self.assertEqual([item.provider_id for item in context.provider_digests], ["visual.generate"])
        self.assertEqual(context.provider_digests[0].readiness_state, "PRESENT_UNVERIFIED")
        self.assertEqual(context.provider_digests[0].discovery_evidence_state, "DISCOVERED_TRUSTED")
        self.assertEqual(context.metrics.semantically_considered_count, 1)
        self.assertEqual(context.metrics.never_considered_count, 0)
        self.assertEqual(context.metrics.host_snapshot_builtin_count, 1)
        self.assertEqual(context.metrics.host_snapshot_fingerprint, snapshot.fingerprint)

    def test_snapshot_and_certified_evidence_merge_and_preserve_verified_ready(self) -> None:
        snapshot = _snapshot(
            {
                "namespace": "functions",
                "action_name": "exec_command",
                "display_name": "Command execution",
                "description": "Runs a bounded repository command.",
                "hierarchy": "host_native",
            }
        )
        inventory = discover_host_capability_snapshot_inventory(snapshot)
        declaration = inventory.provider_declarations[0]
        certified_declaration = SupportingProviderDeclaration(
            provider_id=declaration.provider_id,
            kind=declaration.kind,
            host_identity=declaration.host_identity,
            host_grouping=declaration.host_grouping,
            description=declaration.description,
            callable_tools=declaration.callable_tools,
            callable_exposure=declaration.callable_exposure,
            provenance=("legacy-certified",),
            display_name=declaration.display_name,
        )
        certificate = ReadinessEvidenceCertificate(
            provider_id=certified_declaration.provider_id,
            kind=certified_declaration.kind,
            host_identity=certified_declaration.host_identity,
            host_grouping=certified_declaration.host_grouping,
            callable_tool_ids=(),
            expected_schema_fingerprint=certified_declaration.schema_fingerprint,
            expected_declaration_fingerprint=certified_declaration.fingerprint,
            provenance=certified_declaration.provenance,
        )
        context = prepare_supporting_context(
            (ExecutionNeed("validate repository", "Command execution can validate files."),),
            host_capability_snapshot=snapshot,
            provider_declarations=(certified_declaration,),
            readiness_evidence=(certificate,),
        )
        self.assertEqual(context.metrics.verified_ready_count, 1)
        self.assertEqual(context.provider_digests[0].readiness_state, "VERIFIED_READY")
        self.assertIn("legacy-certified", context.provider_digests[0].provenance)
        self.assertIn(HOST_SNAPSHOT_PROVENANCE, context.provider_digests[0].provenance)
        self.assertEqual(context.metrics.host_snapshot_id, snapshot.snapshot_id)

    def test_untrusted_mapping_cannot_enter_production_route_field(self) -> None:
        with self.assertRaises(TypeError):
            SelectionRouteInput(
                task_summary="bounded task",
                skill_roots=(),
                preliminary_skill_ids=(),
                final_selection={"task_summary": "bounded task", "selected_skills": [], "selection_status": "no_matching_skill"},
                host_capability_snapshot={"trust_marker": HOST_SNAPSHOT_TRUST_MARKER},
            )

    def test_same_snapshot_batches_deterministically_without_special_case(self) -> None:
        capabilities = tuple(
            {
                "namespace": "native",
                "action_name": f"tool_{index:02d}",
                "display_name": f"Native tool {index:02d}",
                "description": "Provides a distinct public Host capability.",
                "hierarchy": "host_native",
            }
            for index in range(41)
        )
        first = prepare_supporting_context(
            (ExecutionNeed("execute", "Several capabilities may help."),),
            host_capability_snapshot=_snapshot(*capabilities),
        )
        second = prepare_supporting_context(
            (ExecutionNeed("execute", "Several capabilities may help."),),
            host_capability_snapshot=_snapshot(*reversed(capabilities)),
        )
        self.assertEqual(first.metrics.selectable_count, 41)
        self.assertEqual(first.metrics.semantically_considered_count, 41)
        self.assertEqual(first.metrics.never_considered_count, 0)
        self.assertGreater(first.metrics.sweep_batch_count, 1)
        self.assertEqual(first.context_fingerprint, second.context_fingerprint)


if __name__ == "__main__":
    unittest.main()
