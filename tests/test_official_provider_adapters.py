"""官方 App/MCP Provider adapter 與 formal boundary regression tests。"""

from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from codex_capability_router.provider_adapters import (
    MCP_STATUS_DETAIL,
    adapt_official_app_inventory,
    adapt_official_mcp_inventory,
    build_official_provider_requests,
)
from codex_capability_router.route_context import (
    ValidatedDecisionPayloads,
    ValidatedSkillSelection,
    prepare_route_context,
)
from codex_capability_router.routing import SelectionRouteInput, route
from codex_capability_router.supporting_context import (
    AppReadinessEvidence,
    ExecutionNeed,
    McpReadinessEvidence,
    SupportingCapabilitySelection,
    SupportingFinalSelection,
    prepare_supporting_context,
    validate_supporting_decision,
)
from codex_capability_router.task_analysis import validate_task_analysis


def _app_responses(
    *,
    accessible: bool = True,
    configured_enabled: bool = True,
    runtime_enabled: bool = True,
    callable_state: bool = True,
    tool_enabled: bool = True,
    missing_read: bool = False,
    missing_installed: bool = False,
):
    """建立符合目前 generated protocol 欄位的 bounded App fixture。"""

    return (
        {
            "data": [
                {
                    "id": "calendar_app",
                    "name": "Calendar",
                    "description": "Read-only calendar access.",
                    "isAccessible": accessible,
                    "isEnabled": configured_enabled,
                    "pluginDisplayNames": [],
                }
            ],
            "nextCursor": None,
        },
        {
            "apps": [] if missing_installed else [
                {
                    "id": "calendar_app",
                    "runtimeName": "calendar-runtime",
                    "enabled": runtime_enabled,
                    "callable": callable_state,
                }
            ]
        },
        {
            "apps": [] if missing_read else [
                {
                    "id": "calendar_app",
                    "name": "Calendar",
                    "description": "Read-only calendar access.",
                    "pluginDisplayNames": [],
                    "toolSummaries": [
                        {
                            "name": "list_events",
                            "title": "List events",
                            "description": "Read events for a date range.",
                            "isEnabled": tool_enabled,
                            "disabledReason": None if tool_enabled else "disabled by policy",
                            "isReadOnly": True,
                        }
                    ],
                }
            ],
            "missingAppIds": ["calendar_app"] if missing_read else [],
        },
    )


def _mcp_response(*, runtime_status="connected", auth_status="unsupported", include_tool=True):
    """建立符合目前 generated MCP status type 的 bounded fixture。"""

    tools = {}
    if include_tool:
        tools["read_value"] = {
            "name": "read_value",
            "title": "Read value",
            "description": "Read a bounded value without side effects.",
            "inputSchema": {"type": "object", "properties": {}},
        }
    return {
        "data": [
            {
                "name": "safe_mcp",
                "runtimeStatus": runtime_status,
                "pluginId": None,
                "serverInfo": {
                    "name": "safe-mcp",
                    "title": "Safe MCP",
                    "version": "1",
                    "description": "Read-only MCP server.",
                },
                "tools": tools,
                "authStatus": auth_status,
            }
        ],
        "nextCursor": None,
    }


class OfficialProviderAdapterTests(unittest.TestCase):
    """確認官方 readiness surface 與 Provider-level selection boundary。"""

    def test_app_hard_gate_is_diagnostic_and_presence_is_selectable(self) -> None:
        positive = adapt_official_app_inventory(*_app_responses())
        self.assertEqual(positive.discovered_count, 1)
        self.assertEqual(positive.hard_eligible_count, 1)
        self.assertEqual(positive.hard_eligible_ids, ("calendar_app",))
        self.assertEqual(positive.readiness_evidence[0].readiness_source, "app/installed")
        self.assertNotIn("authorization", positive.readiness_evidence[0].to_mapping())
        self.assertNotIn("connection", positive.readiness_evidence[0].to_mapping())
        self.assertNotIn("schema", positive.provider_declarations[0].callable_tools[0].to_mapping())

        cases = (
            {"accessible": False},
            {"configured_enabled": False},
            {"runtime_enabled": False},
            {"callable_state": False},
            {"tool_enabled": False},
            {"missing_read": True},
        )
        for kwargs in cases:
            with self.subTest(**kwargs):
                result = adapt_official_app_inventory(*_app_responses(**kwargs))
                self.assertEqual(result.discovered_count, 1)
                self.assertEqual(result.hard_eligible_count, 0)
                context = prepare_supporting_context(
                    (ExecutionNeed("read App data", "需要 Host App capability"),),
                    provider_declarations=result.provider_declarations,
                    readiness_evidence=result.readiness_evidence,
                )
                if kwargs.get("tool_enabled", True) is False or kwargs.get("missing_read", False):
                    self.assertEqual(len(context.provider_digests), 1)
                    self.assertEqual(context.provider_digests[0].readiness_state, "PRESENT_UNVERIFIED")
                    self.assertEqual(context.metrics.metadata_insufficient_count, 0)
                    self.assertEqual(context.metrics.explicit_negative_count, 0)
                else:
                    self.assertEqual(len(context.provider_digests), 1)
                    self.assertEqual(context.provider_digests[0].readiness_state, "KNOWN_UNAVAILABLE")
                    self.assertEqual(context.metrics.explicit_negative_count, 1)

        unverified = adapt_official_app_inventory(*_app_responses(missing_installed=True))
        self.assertEqual(unverified.hard_eligible_count, 0)
        self.assertEqual(unverified.present_count, 1)
        self.assertEqual(unverified.selectable_count, 1)
        self.assertEqual(unverified.present_unverified_count, 1)
        unverified_context = prepare_supporting_context(
            (ExecutionNeed("read App data", "需要 Host App capability"),),
            provider_declarations=unverified.provider_declarations,
            readiness_evidence=unverified.readiness_evidence,
        )
        self.assertEqual(unverified_context.provider_digests[0].readiness_state, "PRESENT_UNVERIFIED")

        inaccessible_without_runtime = adapt_official_app_inventory(
            *_app_responses(accessible=False, missing_installed=True)
        )
        self.assertEqual(inaccessible_without_runtime.selectable_count, 1)
        self.assertEqual(inaccessible_without_runtime.explicit_negative_count, 1)

    def test_fresh_request_specs_use_official_force_flags_and_detail(self) -> None:
        requests = build_official_provider_requests(("calendar_app",), thread_id="thread")
        self.assertEqual([item["method"] for item in requests], ["app/list", "app/installed", "app/read", "mcpServerStatus/list"])
        self.assertEqual(requests[0]["params"], {"forceRefetch": True, "threadId": "thread"})
        self.assertEqual(requests[1]["params"], {"forceRefresh": True, "threadId": "thread"})
        self.assertEqual(requests[2]["params"], {"appIds": ["calendar_app"], "includeTools": True, "threadId": "thread"})
        self.assertEqual(requests[3]["params"], {"detail": "toolsAndAuthOnly", "threadId": "thread"})

    def test_mcp_readiness_is_diagnostic_and_server_presence_is_selectable(self) -> None:
        result = adapt_official_mcp_inventory(_mcp_response())
        self.assertEqual(result.detail, MCP_STATUS_DETAIL)
        self.assertEqual(result.discovered_count, 1)
        self.assertEqual(result.hard_eligible_count, 1)
        self.assertEqual(result.blind_metrics()["runtime_entity_count"], 1)
        self.assertEqual(result.blind_metrics()["package_declared_count"], 0)
        self.assertEqual(result.provider_declarations[0].existence_evidence_state.value, "RUNTIME_ENTITY_PRESENT")
        context = prepare_supporting_context(
            (ExecutionNeed("read a value", "需要安全 read-only runtime capability"),),
            provider_declarations=result.provider_declarations,
            readiness_evidence=result.readiness_evidence,
        )
        self.assertEqual(context.provider_digests[0].kind, "mcp")
        self.assertEqual(context.provider_digests[0].provider_id, "safe_mcp")

        for kwargs in (
            {"runtime_status": "failed"},
            {"auth_status": "notLoggedIn"},
            {"include_tool": False},
        ):
            with self.subTest(**kwargs):
                invalid = adapt_official_mcp_inventory(_mcp_response(**kwargs))
                self.assertEqual(invalid.hard_eligible_count, 0)

                invalid_context = prepare_supporting_context(
                    (ExecutionNeed("read a value", "需要安全 read-only runtime capability"),),
                    provider_declarations=invalid.provider_declarations,
                    readiness_evidence=invalid.readiness_evidence,
                )
                if kwargs.get("auth_status") == "notLoggedIn":
                    self.assertEqual(invalid_context.metrics.present_unverified_count, 1)
                    self.assertEqual(invalid_context.provider_digests[0].readiness_state, "PRESENT_UNVERIFIED")
                elif kwargs.get("include_tool", True) is False:
                    self.assertEqual(len(invalid_context.provider_digests), 1)
                    self.assertEqual(invalid_context.provider_digests[0].readiness_state, "PRESENT_UNVERIFIED")
                    self.assertEqual(invalid_context.metrics.metadata_insufficient_count, 0)
                else:
                    self.assertEqual(len(invalid_context.provider_digests), 1)
                    self.assertEqual(invalid_context.provider_digests[0].readiness_state, "KNOWN_UNAVAILABLE")

    def test_plugin_is_never_new_formal_selection(self) -> None:
        app = adapt_official_app_inventory(*_app_responses())
        context = prepare_supporting_context(
            (ExecutionNeed("read App data", "需要 App capability"),),
            provider_declarations=app.provider_declarations,
            readiness_evidence=app.readiness_evidence,
        )
        plugin = {
            "request_detail": None,
            "final_selection": {
                "selected_supporting_capabilities": [
                    {"kind": "plugin", "canonical_provider_id": "calendar_app", "purpose": "legacy"}
                ],
                "unmet_execution_needs": [],
            },
        }
        with self.assertRaises(ValueError):
            validate_supporting_decision(
                plugin,
                (ExecutionNeed("read App data", "需要 App capability"),),
                context,
            )

    def test_official_app_can_finalize_through_production_route(self) -> None:
        with tempfile.TemporaryDirectory() as value:
            root = Path(value)
            skill_dir = root / "app-routing-skill"
            skill_dir.mkdir()
            (skill_dir / "SKILL.md").write_text(
                "---\nid: app-routing-skill\nname: app-routing-skill\ndescription: App route test.\nstatus: available\n---\nread\n",
                encoding="utf-8",
            )
            analysis = validate_task_analysis(
                {
                    "task_summary": "Read calendar data without changes.",
                    "work_items": ["read calendar data"],
                    "deliverables": ["read result"],
                    "constraints": ["read-only"],
                    "quality_expectations": ["traceable"],
                }
            )
            skill = ValidatedSkillSelection(
                analysis.task_summary,
                (("app-routing-skill", "The Skill is applicable."),),
                "selected",
            )
            app = adapt_official_app_inventory(*_app_responses())
            need = ExecutionNeed("read calendar data", "The task needs the Host App read capability.")
            final = SupportingFinalSelection(
                (SupportingCapabilitySelection("app", "calendar_app", "Read calendar data."),),
                (),
            )
            decision = ValidatedDecisionPayloads(analysis, skill, (need,), final)
            skill_context = prepare_route_context(analysis, skill_roots=(root,), task_summary=analysis.task_summary)
            support_context = prepare_supporting_context(
                (need,),
                provider_declarations=app.provider_declarations,
                readiness_evidence=app.readiness_evidence,
            )
            receipt = route(
                SelectionRouteInput(
                    task_summary=analysis.task_summary,
                    skill_roots=(root,),
                    preliminary_skill_ids=("app-routing-skill",),
                    final_selection=skill.to_mapping(),
                    validated_decision_payloads=decision,
                    skill_context=skill_context,
                    supporting_context=support_context,
                    supporting_provider_declarations=app.provider_declarations,
                    supporting_readiness_evidence=app.readiness_evidence,
                    supporting_selection={
                        "request_detail": None,
                        "final_selection": final.to_mapping(),
                    },
                )
            )
            self.assertEqual(receipt["selection_state"], "FINALIZED")
            self.assertEqual(receipt["selected_supporting_capabilities"][0]["kind"], "app")
            self.assertEqual(receipt["selected_supporting_capabilities"][0]["readiness_state"], "VERIFIED_READY")
            self.assertEqual(receipt["selected_provider_readiness_evidence"][0]["readiness_source"], "app/installed")
            stale_app = adapt_official_app_inventory(*_app_responses(callable_state=False))
            with self.assertRaisesRegex(ValueError, "Supporting context fingerprint is stale"):
                route(
                    SelectionRouteInput(
                        task_summary=analysis.task_summary,
                        skill_roots=(root,),
                        preliminary_skill_ids=("app-routing-skill",),
                        final_selection=skill.to_mapping(),
                        validated_decision_payloads=decision,
                        skill_context=skill_context,
                        supporting_context=support_context,
                        supporting_provider_declarations=stale_app.provider_declarations,
                        supporting_readiness_evidence=stale_app.readiness_evidence,
                        supporting_selection={
                            "request_detail": None,
                            "final_selection": final.to_mapping(),
                        },
                    )
                )

    def test_fresh_snapshot_change_is_rejected_by_context_fingerprint(self) -> None:
        need = ExecutionNeed("read App data", "需要 App capability")
        first = adapt_official_app_inventory(*_app_responses())
        second = adapt_official_app_inventory(*_app_responses(callable_state=False))
        first_context = prepare_supporting_context(
            (need,), provider_declarations=first.provider_declarations, readiness_evidence=first.readiness_evidence
        )
        second_context = prepare_supporting_context(
            (need,), provider_declarations=second.provider_declarations, readiness_evidence=second.readiness_evidence
        )
        self.assertNotEqual(first_context.context_fingerprint, second_context.context_fingerprint)
        self.assertEqual(first_context.metrics.hard_eligible_count, 1)
        self.assertEqual(second_context.metrics.hard_eligible_count, 0)

    def test_mcp_plugin_id_is_provenance_only(self) -> None:
        response = _mcp_response()
        response["data"][0]["pluginId"] = "package-origin"
        result = adapt_official_mcp_inventory(response)
        evidence = result.readiness_evidence[0]
        self.assertIsInstance(evidence, McpReadinessEvidence)
        self.assertEqual(evidence.plugin_id, "package-origin")
        self.assertEqual(result.provider_declarations[0].kind, "mcp")


if __name__ == "__main__":
    unittest.main()
