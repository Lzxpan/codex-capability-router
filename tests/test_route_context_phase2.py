"""Phase 2 Skill-side route context 與 validated decision payload tests。"""

from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from codex_capability_router.discovery import import_runtime_envelope
from codex_capability_router.route_context import (
    SkillContextMetrics,
    ValidatedDecisionPayloads,
    prepare_route_context,
    validate_decision_payloads,
)
from codex_capability_router.task_analysis import TaskAnalysis, validate_task_analysis


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
EXPLAIN_CODE_FIXTURE = REPOSITORY_ROOT / "tests" / "fixtures" / "legacy_frontmatter" / "explain-code"


def _analysis(summary: str = "分析 source 並整理技術說明。") -> TaskAnalysis:
    """建立 Phase 2 測試使用的正式 immutable TaskAnalysis。"""

    return validate_task_analysis(
        {
            "task_summary": summary,
            "work_items": ["理解 source"],
            "deliverables": ["技術說明"],
            "constraints": ["read-only"],
            "quality_expectations": ["證據可追蹤"],
        }
    )


def _write_skill(
    root: Path,
    skill_id: str,
    *,
    status: str = "available",
    controller: bool = False,
    routing_support: bool = False,
    description: str = "A clear source analysis skill for context tests.",
    body: str = "Full instructions for context tests.",
) -> None:
    """建立明確 temporary Skill root，不加入任何 semantic mapping。"""

    directory = root / skill_id
    directory.mkdir(parents=True)
    lines = [
        "---",
        f"id: {skill_id}",
        f"name: {skill_id}",
        f"description: {description}",
        f"status: {status}",
    ]
    if controller:
        lines.append("controller: true")
    if routing_support:
        lines.append("routing_support: true")
    lines.extend(["---", body, ""])
    (directory / "SKILL.md").write_text("\n".join(lines), encoding="utf-8")


def _runtime_record(
    skill_id: str,
    status: str,
    *,
    controller: bool = False,
    routing_support: bool = False,
) -> dict[str, object]:
    """建立明確 runtime availability fact，不從名稱猜測狀態。"""

    payload = {
        "id": skill_id,
        "name": skill_id,
        "kind": "skill",
        "status": status,
        "categories": [],
        "triggers": [],
        "priority": 0,
        "overlap_group": None,
        "preferred_for": [],
        "requires": [],
        "last_verified": None,
    }
    if controller:
        payload["controller"] = True
    if routing_support:
        payload["routing_support"] = True
    return payload


class Phase2RouteContextTests(unittest.TestCase):
    """驗證 v0.2 Skill-only context 的 deterministic contract。"""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        _write_skill(self.root, "canonical-source-skill")

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_task_analysis_is_mandatory_and_task_summary_is_projection(self) -> None:
        """缺少 TaskAnalysis 不建立第二套 semantics；相同 summary 只作 projection。"""

        with self.assertRaises(ValueError):
            prepare_route_context(skill_roots=(self.root,))
        analysis = _analysis()
        context = prepare_route_context(analysis, skill_roots=(self.root,), task_summary=analysis.task_summary)
        self.assertEqual(context.task_analysis, analysis)
        self.assertEqual(context.task_summary, analysis.task_summary)

    def test_task_summary_mismatch_is_rejected(self) -> None:
        """legacy task_summary 與正式 TaskAnalysis 不一致時拒絕。"""

        with self.assertRaises(ValueError):
            prepare_route_context(_analysis(), skill_roots=(self.root,), task_summary="different task")

    def test_context_is_deterministic_and_skill_only(self) -> None:
        """相同 Skill input 產生相同 context/fingerprint，且不包含 Provider 或 private path。"""

        analysis = _analysis()
        first = prepare_route_context(analysis, skill_roots=(self.root,))
        second = prepare_route_context(analysis, skill_roots=(self.root,))

        self.assertEqual(first.context_fingerprint, second.context_fingerprint)
        self.assertEqual(first.to_mapping(), second.to_mapping())
        rendered = json.dumps(first.to_mapping(), ensure_ascii=False, sort_keys=True)
        self.assertNotIn(str(self.root), rendered)
        self.assertNotIn("provider", rendered.casefold())
        self.assertNotIn("runtime_callable", rendered)
        self.assertNotIn("Full instructions", rendered)
        self.assertEqual(first.handoff_references[0].id, "canonical-source-skill")

    def test_context_fingerprint_changes_for_formal_inputs(self) -> None:
        """TaskAnalysis、Skill content 與 runtime eligibility 改變都會改變 fingerprint。"""

        base = prepare_route_context(_analysis(), skill_roots=(self.root,))
        changed_task = prepare_route_context(_analysis("另一個正式工作。"), skill_roots=(self.root,))
        self.assertNotEqual(base.context_fingerprint, changed_task.context_fingerprint)

        skill_file = self.root / "canonical-source-skill" / "SKILL.md"
        skill_file.write_text(skill_file.read_text(encoding="utf-8").replace("Full instructions", "Changed instructions"), encoding="utf-8")
        changed_skill = prepare_route_context(_analysis(), skill_roots=(self.root,))
        self.assertNotEqual(base.context_fingerprint, changed_skill.context_fingerprint)

        unavailable_runtime = import_runtime_envelope(
            {"capabilities": [_runtime_record("canonical-source-skill", "unavailable")]}
        )
        changed_runtime = prepare_route_context(_analysis(), skill_roots=(self.root,), runtime=unavailable_runtime)
        self.assertNotEqual(changed_skill.context_fingerprint, changed_runtime.context_fingerprint)

    def test_canonical_ids_and_eligibility_gates_are_preserved(self) -> None:
        """canonical ID、controller、routing-support 與 availability hard gates 均保留。"""

        _write_skill(self.root, "controller-skill", controller=True)
        _write_skill(self.root, "routing-support-skill", routing_support=True)
        _write_skill(self.root, "unknown-skill", status="unknown")
        runtime = import_runtime_envelope(
            {
                "capabilities": [
                    _runtime_record("controller-skill", "available", controller=True),
                    _runtime_record("routing-support-skill", "available", routing_support=True),
                    _runtime_record("unknown-skill", "unknown"),
                ]
            }
        )
        context = prepare_route_context(_analysis(), skill_roots=(self.root,), runtime=runtime)
        by_id = {item.id: item for item in context.skill_eligibility}

        self.assertEqual(
            [profile.id for profile in context.candidates],
            ["canonical-source-skill", "unknown-skill"],
        )
        self.assertTrue(by_id["canonical-source-skill"].eligible)
        self.assertFalse(by_id["controller-skill"].eligible)
        self.assertTrue(by_id["controller-skill"].controller)
        self.assertFalse(by_id["routing-support-skill"].eligible)
        self.assertTrue(by_id["routing-support-skill"].routing_support)
        self.assertTrue(by_id["unknown-skill"].eligible)

    def test_metrics_and_zero_available_ratio(self) -> None:
        """metrics 保留 available/candidate/selected/reduction，零 available ratio 為 null。"""

        context = prepare_route_context(_analysis(), skill_roots=(self.root,))
        self.assertEqual(context.metrics.available_count, 1)
        self.assertEqual(context.metrics.candidate_count, 1)
        self.assertEqual(context.metrics.selected_count, 0)
        self.assertEqual(context.metrics.candidate_reduction_ratio, 0.0)

        with tempfile.TemporaryDirectory() as empty:
            empty_context = prepare_route_context(_analysis(), skill_roots=(Path(empty),))
        self.assertEqual(empty_context.metrics.available_count, 0)
        self.assertEqual(empty_context.metrics.candidate_count, 0)
        self.assertIsNone(empty_context.metrics.candidate_reduction_ratio)

        self.assertEqual(
            SkillContextMetrics(available_count=4, candidate_count=1).candidate_reduction_ratio,
            0.75,
        )

    def test_validated_decision_payloads_are_skill_side_only(self) -> None:
        """foundation 只接受 TaskAnalysis + 既有 Skill selection，不接受 Provider payload。"""

        analysis = _analysis()
        empty = validate_decision_payloads(
            {
                "contract_version": "v0.2-validated-decision-payloads-v1",
                "task_analysis": analysis.to_mapping(),
                "skill_selection": None,
            }
        )
        self.assertIsInstance(empty, ValidatedDecisionPayloads)
        self.assertIsNone(empty.skill_selection)

        selected = validate_decision_payloads(
            {
                "contract_version": "v0.2-validated-decision-payloads-v1",
                "task_analysis": analysis.to_mapping(),
                "skill_selection": {
                    "task_summary": analysis.task_summary,
                    "selected_skills": [],
                    "selection_status": "no_matching_skill",
                },
            }
        )
        self.assertEqual(selected.skill_selection.selection_status, "no_matching_skill")
        with self.assertRaises(ValueError):
            validate_decision_payloads(
                {
                    "contract_version": "v0.2-validated-decision-payloads-v1",
                    "task_analysis": analysis.to_mapping(),
                    "skill_selection": {
                        "task_summary": "mismatch",
                        "selected_skills": [],
                        "selection_status": "no_matching_skill",
                    },
                }
            )
        with self.assertRaises(ValueError):
            validate_decision_payloads(
                {
                    "contract_version": "v0.2-validated-decision-payloads-v1",
                    "task_analysis": analysis.to_mapping(),
                    "skill_selection": None,
                    "provider_selection": [],
                }
            )

    def test_explain_code_phase1_contract_is_available_from_trusted_root(self) -> None:
        """合法 explain-code trusted-root Skill 不依賴 runtime availability fact。"""

        trusted_context = prepare_route_context(_analysis(), skill_roots=(EXPLAIN_CODE_FIXTURE,))
        self.assertEqual([profile.id for profile in trusted_context.candidates], ["explain-code"])
        runtime = import_runtime_envelope(
            {"capabilities": [_runtime_record("explain-code", "available")]}
        )
        available_context = prepare_route_context(
            _analysis(),
            skill_roots=(EXPLAIN_CODE_FIXTURE,),
            runtime=runtime,
        )
        self.assertEqual([profile.id for profile in available_context.candidates], ["explain-code"])


if __name__ == "__main__":
    unittest.main()
