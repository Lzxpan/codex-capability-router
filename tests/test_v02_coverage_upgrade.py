"""v0.2 coverage upgrade 的 Host evidence、metrics 與 bounded diagnostics tests。"""

# 修改紀錄（2026-08-31，Steve Peng）
# 原始內容：既有 deterministic suite 沒有 Host exposure、coverage reference、addition 或 unknown diagnostic boundary tests。
# 修改原因：驗證 v0.2 upgrade 的 safety contract，而非假造 LLM semantic correctness。
# 修改後功能：涵蓋 Host promotion/stale rejection、Skill-layer metrics、bounded diagnostics 與 Coverage Check handoff。

from __future__ import annotations

import hashlib
from dataclasses import replace
from pathlib import Path
import tempfile
import unittest

from codex_capability_router.discovery import import_runtime_envelope
from codex_capability_router.host_exposure import (
    HostExposureError,
    HostSkillExposureAdapter,
    HostSkillExposureRecord,
    revalidate_host_exposure,
)
from codex_capability_router.inventory import (
    BasicProfile,
    build_possible_relevance_diagnostics,
    refresh_skill_inventory,
    serialize_recalled_unknown_profiles,
)
from codex_capability_router.models import CapabilityStatus
from codex_capability_router.route_context import (
    ValidatedDecisionPayloads,
    ValidatedSkillSelection,
    prepare_route_context,
)
from codex_capability_router.routing import SelectionRouteInput, route
from codex_capability_router.task_analysis import TaskAnalysis


def _write_skill(root: Path, skill_id: str, *, status: str = "unknown") -> Path:
    """建立最小 test Skill；內容只供 handoff/fingerprint 驗證。"""

    directory = root / skill_id
    directory.mkdir()
    path = directory / "SKILL.md"
    path.write_text(
        f"---\nid: {skill_id}\nname: {skill_id}\ndescription: A bounded test Skill.\nstatus: {status}\n---\nbody\n",
        encoding="utf-8",
    )
    return path


def _host_envelope(root: Path, path: Path, *, enabled: bool = True, source: str = "runtime:host"):
    """以 designated adapter 建立同一 workspace/session 的 typed Host evidence。"""

    record = HostSkillExposureRecord(
        id=path.parent.name,
        enabled=enabled,
        source=source,
        session_id="test-session",
        workspace=root,
        cwd=root,
        path=path,
        content_fingerprint=hashlib.sha256(path.read_bytes()).hexdigest(),
    )
    return HostSkillExposureAdapter.create_envelope(
        session_id="test-session",
        workspace=root,
        cwd=root,
        records=(record,),
        semantics_certified=True,
    )


class HostExposureRouteTests(unittest.TestCase):
    """驗證 Host exposure 僅作觀測，Skill availability 由 trusted root 決定。"""

    def test_trusted_root_skill_stays_available_without_host_exposure(self) -> None:
        with tempfile.TemporaryDirectory() as value:
            root = Path(value)
            path = _write_skill(root, "host-visible")
            inventory = refresh_skill_inventory((root,))
            self.assertEqual(inventory.host_exposed_skill_ids, ())
            self.assertEqual(inventory.trusted_root_skill_ids, ("host-visible",))
            self.assertEqual(inventory.router_available_skill_ids, ("host-visible",))
            self.assertEqual(inventory.available_records[0].status, CapabilityStatus.UNKNOWN)

            unknown_host = _host_envelope(root, path, enabled=False)
            observed_inventory = refresh_skill_inventory((root,), host_exposure=unknown_host)
            self.assertEqual(observed_inventory.host_exposed_skill_ids, ())
            self.assertEqual(observed_inventory.router_available_skill_ids, ("host-visible",))

    def test_duplicate_trusted_root_id_uses_existing_root_precedence(self) -> None:
        with tempfile.TemporaryDirectory() as first, tempfile.TemporaryDirectory() as second:
            first_root, second_root = Path(first), Path(second)
            first_path = _write_skill(first_root, "same-id", status="unknown")
            second_path = _write_skill(second_root, "same-id", status="unknown")
            envelope = _host_envelope(second_root, second_path)
            inventory = refresh_skill_inventory((first_root, second_root), host_exposure=envelope)
            self.assertEqual(inventory.router_available_skill_ids, ("same-id",))
            self.assertEqual(inventory._skill_paths["same-id"], first_path)

    def test_runtime_only_skill_never_becomes_formal_available(self) -> None:
        """runtime declaration 不能取代 trusted root 的 Skill instance binding。"""

        with tempfile.TemporaryDirectory() as value:
            root = Path(value)
            runtime = import_runtime_envelope(
                {
                    "capabilities": [
                        {
                            "id": "runtime-only",
                            "name": "runtime-only",
                            "kind": "skill",
                            "status": "available",
                            "categories": [],
                            "triggers": [],
                            "priority": 0,
                            "overlap_group": None,
                            "preferred_for": [],
                            "requires": [],
                            "source": "runtime:host",
                            "last_verified": None,
                        }
                    ]
                }
            )
            inventory = refresh_skill_inventory((root,), runtime=runtime)
            self.assertEqual(inventory.trusted_root_skill_ids, ())
            self.assertEqual(inventory.router_available_skill_ids, ())
            self.assertEqual(inventory.available_records, ())

    def test_untrusted_filesystem_skill_is_ignored(self) -> None:
        """未傳入 trusted root 的任意 filesystem Skill 不得進 inventory。"""

        with tempfile.TemporaryDirectory() as allowed, tempfile.TemporaryDirectory() as outside:
            allowed_root = Path(allowed)
            outside_root = Path(outside)
            _write_skill(outside_root, "outside-skill")
            inventory = refresh_skill_inventory((allowed_root,))
            self.assertNotIn("outside-skill", {profile.id for profile in inventory.profiles})
            self.assertEqual(inventory.router_available_skill_ids, ())

    def test_changed_host_exposure_does_not_override_skill_safety_gates(self) -> None:
        with tempfile.TemporaryDirectory() as value:
            root = Path(value)
            path = _write_skill(root, "host-visible")
            prepared = _host_envelope(root, path)
            stale = _host_envelope(root, path, enabled=False)
            analysis = TaskAnalysis("use host skill", ("inspect source",), (), (), ())
            selection = ValidatedSkillSelection(
                analysis.task_summary,
                (("host-visible", "It supports source inspection."),),
                "selected",
                ((("work_items", 0),),),
            )
            decision = ValidatedDecisionPayloads(analysis, selection)
            context = prepare_route_context(analysis, skill_roots=(root,), host_exposure=prepared)
            request = SelectionRouteInput(
                task_summary=analysis.task_summary,
                skill_roots=(root,),
                preliminary_skill_ids=("host-visible",),
                final_selection=selection.to_mapping(),
                validated_decision_payloads=decision,
                skill_context=context,
                host_exposure=prepared,
                finalize_host_exposure=stale,
            )
            fresh_receipt = route(replace(request, finalize_host_exposure=prepared))
            self.assertEqual(fresh_receipt["selection_status"], "selected")
            self.assertEqual(
                route(replace(request, host_exposure=stale, finalize_host_exposure=stale))["selection_status"],
                "selected",
            )
            stale_receipt = route(request)
            self.assertEqual(stale_receipt["selection_status"], "selected")
            with self.assertRaises(HostExposureError):
                revalidate_host_exposure(prepared, stale, ("host-visible",))

    def test_host_adapter_requires_explicit_enabled_semantics_certification(self) -> None:
        with tempfile.TemporaryDirectory() as value:
            root = Path(value)
            path = _write_skill(root, "host-visible")
            record = HostSkillExposureRecord(
                "host-visible",
                True,
                "runtime:host",
                "test-session",
                root,
                root,
                path,
                hashlib.sha256(path.read_bytes()).hexdigest(),
            )
            with self.assertRaises(HostExposureError):
                HostSkillExposureAdapter.create_envelope(
                    session_id="test-session",
                    workspace=root,
                    cwd=root,
                    records=(record,),
                )

    def test_host_adapter_binds_typed_skills_list_to_exact_canonical_id(self) -> None:
        with tempfile.TemporaryDirectory() as value:
            root = Path(value)
            path = _write_skill(root, "host-visible")
            envelope = HostSkillExposureAdapter.from_skills_list(
                {
                    "data": [
                        {
                            "errors": [],
                            "skills": [
                                {
                                    "name": "Host Visible",
                                    "id": "host-visible",
                                    "enabled": True,
                                    "path": str(path),
                                }
                            ],
                        }
                    ]
                },
                session_id="test-session",
                workspace=root,
                cwd=root,
                canonical_ids={"Host Visible": "host-visible"},
                semantics_certified=True,
            )
            self.assertEqual(envelope.exposed_ids, ("host-visible",))

    def test_host_adapter_rejects_unknown_name_with_valid_but_unbound_id(self) -> None:
        """Host name 不在 exact binding 時，不得借用 mapping value 偽造 canonical ID。"""

        with tempfile.TemporaryDirectory() as value:
            root = Path(value)
            path = _write_skill(root, "host-visible")
            with self.assertRaises(HostExposureError):
                HostSkillExposureAdapter.from_skills_list(
                    {
                        "data": [
                            {
                                "errors": [],
                                "skills": [
                                    {
                                        "name": "Unbound Name",
                                        "id": "host-visible",
                                        "enabled": True,
                                        "path": str(path),
                                    }
                                ],
                            }
                        ]
                    },
                    session_id="test-session",
                    workspace=root,
                    cwd=root,
                    canonical_ids={"Host Visible": "host-visible"},
                    semantics_certified=True,
                )

    def test_host_observation_staleness_does_not_bypass_skill_fingerprint_gate(self) -> None:
        with tempfile.TemporaryDirectory() as value, tempfile.TemporaryDirectory() as other:
            root = Path(value)
            other_root = Path(other)
            path = _write_skill(root, "host-visible")
            other_path = _write_skill(other_root, "host-visible")
            prepared = _host_envelope(root, path)
            declaration_changed = _host_envelope(root, path, source="runtime:host-v2")
            missing = HostSkillExposureAdapter.create_envelope(
                session_id="test-session",
                workspace=root,
                cwd=root,
                records=(),
                semantics_certified=True,
            )
            analysis = TaskAnalysis("use host skill", ("inspect source",), (), (), ())
            selection = ValidatedSkillSelection(
                analysis.task_summary,
                (("host-visible", "It supports source inspection."),),
                "selected",
                ((("work_items", 0),),),
            )
            decision = ValidatedDecisionPayloads(analysis, selection)
            context = prepare_route_context(analysis, skill_roots=(root,), host_exposure=prepared)

            def invoke(fresh):
                return route(
                    SelectionRouteInput(
                        task_summary=analysis.task_summary,
                        skill_roots=(root,),
                        preliminary_skill_ids=("host-visible",),
                        final_selection=selection.to_mapping(),
                        validated_decision_payloads=decision,
                        skill_context=context,
                        host_exposure=prepared,
                        finalize_host_exposure=fresh,
                    )
                )

            self.assertEqual(invoke(declaration_changed)["selection_status"], "selected")
            self.assertEqual(invoke(missing)["selection_status"], "selected")
            with self.assertRaises(HostExposureError):
                revalidate_host_exposure(prepared, declaration_changed, ("host-visible",))
            with self.assertRaises(HostExposureError):
                revalidate_host_exposure(prepared, missing, ("host-visible",))

            changed_workspace = _host_envelope(other_root, other_path)
            self.assertEqual(invoke(changed_workspace)["selection_status"], "selected")
            with self.assertRaises(HostExposureError):
                revalidate_host_exposure(prepared, changed_workspace, ("host-visible",))

            path.write_text(path.read_text(encoding="utf-8") + "changed\n", encoding="utf-8")
            changed_content = _host_envelope(root, path)
            with self.assertRaises(ValueError):
                invoke(changed_content)
            with self.assertRaises(HostExposureError):
                revalidate_host_exposure(prepared, changed_content, ("host-visible",))


class CoverageContractTests(unittest.TestCase):
    """驗證 Skill reference metrics 與 deterministic possible relevance budget。"""

    def test_receipt_exposes_supports_and_skill_layer_metrics(self) -> None:
        with tempfile.TemporaryDirectory() as value:
            root = Path(value)
            _write_skill(root, "coverage-skill", status="available")
            analysis = TaskAnalysis("coverage", ("inspect source",), (), ("preserve API",), ())
            selection = ValidatedSkillSelection(
                analysis.task_summary,
                (("coverage-skill", "It supports source inspection."),),
                "selected",
                ((("work_items", 0),),),
            )
            decision = ValidatedDecisionPayloads(analysis, selection)
            context = prepare_route_context(analysis, skill_roots=(root,))
            receipt = route(
                SelectionRouteInput(
                    task_summary=analysis.task_summary,
                    skill_roots=(root,),
                    preliminary_skill_ids=("coverage-skill",),
                    final_selection=selection.to_mapping(),
                    validated_decision_payloads=decision,
                    skill_context=context,
                )
            )
            self.assertEqual(receipt["selected_skills"][0]["supports"], [{"section": "work_items", "index": 0}])
            self.assertEqual(receipt["skill_metrics"]["task_analysis_indexed_item_count"], 2)
            self.assertEqual(receipt["skill_metrics"]["trusted_root_skill_count"], 1)
            self.assertEqual(receipt["skill_metrics"]["skill_supported_item_count"], 1)
            self.assertEqual(receipt["skill_metrics"]["skill_unreferenced_item_count"], 1)

    def test_task_analysis_retrieval_projection_includes_all_indexed_arrays_once(self) -> None:
        analysis = TaskAnalysis(
            "Firmware review",
            ("Trace source",),
            ("firmware review", "Write report"),
            ("Preserve API",),
            ("Preserve API",),
        )
        self.assertEqual(
            analysis.retrieval_items(),
            ("Firmware review", "Trace source", "Write report", "Preserve API"),
        )

    def test_possible_relevance_budget_is_utf8_canonical_and_bounded(self) -> None:
        profile = BasicProfile(
            "unknown-skill",
            "Unknown Skill",
            "可供診斷的 profile",
            None,
            CapabilityStatus.UNKNOWN,
            "skill-root:0",
            ("skill-root:0",),
            "a" * 64,
        )
        serialized = serialize_recalled_unknown_profiles((profile,))
        diagnostics, status = build_possible_relevance_diagnostics(
            (profile,),
            {"unknown-skill": "可能支援目前工作"},
            budget_bytes=len(serialized),
        )
        self.assertEqual(status, "produced")
        self.assertEqual(diagnostics[0].availability_state, "unknown")
        _, skipped = build_possible_relevance_diagnostics(
            (profile,),
            {"unknown-skill": "可能支援目前工作"},
            budget_bytes=len(serialized) - 1,
        )
        self.assertEqual(skipped, "skipped_context_budget")

    def test_possible_relevance_budget_is_not_caller_tunable(self) -> None:
        with self.assertRaises(ValueError):
            SelectionRouteInput(
                task_summary="budget",
                skill_roots=(Path("."),),
                preliminary_skill_ids=(),
                final_selection={
                    "task_summary": "budget",
                    "selected_skills": [],
                    "selection_status": "no_matching_skill",
                },
                possible_relevance_serialized_budget_bytes=1,
            )

    def test_coverage_addition_requires_distinct_value_and_is_handed_off(self) -> None:
        with tempfile.TemporaryDirectory() as value:
            root = Path(value)
            for skill_id in ("base-skill", "coverage-addition"):
                _write_skill(root, skill_id, status="available")
            analysis = TaskAnalysis("coverage", ("inspect source",), ("write report",), (), ())
            selection = ValidatedSkillSelection(
                analysis.task_summary,
                (
                    ("base-skill", "Base support."),
                    ("coverage-addition", "Additional support."),
                ),
                "selected",
                ((("work_items", 0),), (("deliverables", 0),)),
            )
            decision = ValidatedDecisionPayloads(analysis, selection)
            context = prepare_route_context(analysis, skill_roots=(root,))
            receipt = route(
                SelectionRouteInput(
                    task_summary=analysis.task_summary,
                    skill_roots=(root,),
                    preliminary_skill_ids=("base-skill",),
                    final_selection=selection.to_mapping(),
                    validated_decision_payloads=decision,
                    skill_context=context,
                    coverage_check_used=True,
                    coverage_additions=(
                        {
                            "id": "coverage-addition",
                            "supports": [{"section": "deliverables", "index": 0}],
                            "distinct_value": "Adds report generation not supplied by the base Skill.",
                        },
                    ),
                )
            )
            self.assertEqual(receipt["full_handoff_skills"], ["base-skill", "coverage-addition"])
            self.assertTrue(receipt["skill_metrics"]["coverage_check_used"])

    def test_possible_relevance_is_diagnostic_only_in_production_route(self) -> None:
        with tempfile.TemporaryDirectory() as value:
            root = Path(value)
            _write_skill(root, "available-skill", status="available")
            runtime = import_runtime_envelope(
                {
                    "capabilities": [
                        {
                            "id": "unknown-skill",
                            "name": "unknown-skill",
                            "kind": "skill",
                            "status": "unknown",
                            "categories": [],
                            "triggers": [],
                            "priority": 0,
                            "overlap_group": None,
                            "preferred_for": [],
                            "requires": [],
                            "source": "runtime:diagnostic",
                            "last_verified": None,
                        }
                    ]
                }
            )
            analysis = TaskAnalysis("inspect source", ("inspect source",), (), (), ())
            selection = ValidatedSkillSelection(
                analysis.task_summary,
                (("available-skill", "It supports source inspection."),),
                "selected",
                ((("work_items", 0),),),
            )
            decision = ValidatedDecisionPayloads(analysis, selection)
            context = prepare_route_context(analysis, skill_roots=(root,), runtime=runtime)
            receipt = route(
                SelectionRouteInput(
                    task_summary=analysis.task_summary,
                    skill_roots=(root,),
                    preliminary_skill_ids=("available-skill",),
                    final_selection=selection.to_mapping(),
                    validated_decision_payloads=decision,
                    skill_context=context,
                    runtime=runtime,
                    possible_relevance_reasons={"unknown-skill": "可能協助來源檢查"},
                )
            )
            self.assertEqual(receipt["selected_skills"][0]["id"], "available-skill")
            # 修改紀錄（2026-09-02，Steve Peng）
            # 原始內容：runtime unknown Skill 會被移到 possible-relevance diagnostic。
            # 修改原因：beta.2 以存在證據建立 semantic candidate；readiness/unknown 只留給 execution evidence。
            # 修改後功能：unknown 但具 identity/metadata 的 Skill 保留在 candidate pool，不再被 diagnostic-only gate 排除。
            self.assertEqual(receipt["possible_relevance_diagnostics"], [])
            self.assertEqual(receipt["skill_metrics"]["possibly_relevant_unavailable_count"], 0)


if __name__ == "__main__":
    unittest.main()
