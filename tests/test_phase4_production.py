"""Phase 4 唯一 production Skill selection path 的 focused tests。"""

from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from codex_capability_router.catalog import render_selection_payload
from codex_capability_router.models import RouterInput
from codex_capability_router.routing import SelectionReceipt, SelectionRouteInput, route


def _write_skill(
    root: Path,
    skill_id: str,
    *,
    description: str = "A clear Phase 4 skill for controlled production selection.",
    status: str = "available",
    categories: tuple[str, ...] = (),
    triggers: tuple[str, ...] = (),
    priority: int = 0,
    controller: bool = False,
    routing_support: bool = False,
) -> None:
    """建立 Phase 4 temporary Skill；synthetic IDs 僅存在測試 fixture。"""

    directory = root / skill_id
    directory.mkdir(parents=True)
    lines = [
        "---",
        f"id: {skill_id}",
        f"name: {skill_id}",
        f"description: {description}",
        f"status: {status}",
        f"categories: {json.dumps(list(categories), ensure_ascii=False)}",
        f"triggers: {json.dumps(list(triggers), ensure_ascii=False)}",
    ]
    if controller:
        lines.append("controller: true")
    if routing_support:
        lines.append("routing_support: true")
    lines.extend(["---", f"Full instructions for {skill_id}.", ""])
    (directory / "SKILL.md").write_text("\n".join(lines), encoding="utf-8")


class Phase4ProductionSelectionTests(unittest.TestCase):
    """驗證新版 contract 已成為唯一 final selector，不驗證 Codex 語意品質。"""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def _request(
        self,
        task_summary: str,
        preliminary_skill_ids: tuple[str, ...],
        final_selection: dict[str, object],
        *,
        explicit_skill_ids: tuple[str, ...] = (),
        correction_skill_ids: tuple[str, ...] = (),
        expanded_retrieval: bool = False,
    ) -> SelectionRouteInput:
        """建立 production route input，明確提供 Codex 階段結果。"""

        return SelectionRouteInput(
            task_summary=task_summary,
            skill_roots=(self.root,),
            preliminary_skill_ids=preliminary_skill_ids,
            final_selection=final_selection,
            explicit_skill_ids=explicit_skill_ids,
            correction_skill_ids=correction_skill_ids,
            expanded_retrieval=expanded_retrieval,
        )

    @staticmethod
    def _selected(skill_ids: tuple[str, ...], task_summary: str = "phase4 task") -> dict[str, object]:
        """建立 Codex 提供的新版 final selection payload。"""

        return {
            "task_summary": task_summary,
            "selected_skills": [
                {"id": skill_id, "reason": "Codex 判斷此 Skill 適合目前工作"}
                for skill_id in skill_ids
            ],
            "selection_status": "selected",
        }

    def test_production_route_returns_codex_selection_contract(self) -> None:
        """production route 應回傳 selected_skills，不再產生舊兩層 output。"""

        _write_skill(self.root, "phase4-choice")
        task = "phase4 task"
        output = route(self._request(task, ("phase4-choice",), self._selected(("phase4-choice",), task)))
        self.assertIsInstance(output, SelectionReceipt)
        self.assertTrue(output["router_invoked"])
        self.assertEqual(output.selection_payload(), self._selected(("phase4-choice",), task))
        self.assertEqual(output["selection_status"], "selected")
        self.assertEqual(output["selected_skills"][0]["id"], "phase4-choice")

    def test_codex_final_selection_is_not_rewritten_by_old_keyword_ranking(self) -> None:
        """task keyword、priority 與 metadata 不得覆寫 Codex 提供的 final ID。"""

        _write_skill(
            self.root,
            "phase4-codex-choice",
            categories=("unrelated",),
            priority=0,
        )
        _write_skill(
            self.root,
            "phase4-keyword-winner",
            categories=("firmware",),
            triggers=("firmware",),
            priority=999,
        )
        task = "firmware task"
        output = route(self._request(task, ("phase4-codex-choice",), self._selected(("phase4-codex-choice",), task)))
        self.assertEqual(tuple(item["id"] for item in output["selected_skills"]), ("phase4-codex-choice",))

    def test_more_than_three_plus_two_skills_are_valid_new_output(self) -> None:
        """新版 selection 不受 PRIMARY 3 與 OPTIONAL 2 hard limit 影響。"""

        skill_ids = tuple(f"phase4-selected-{index}" for index in range(6))
        for skill_id in skill_ids:
            _write_skill(self.root, skill_id)
        task = "phase4 many skills"
        output = route(self._request(task, skill_ids, self._selected(skill_ids, task)))
        self.assertEqual(tuple(item["id"] for item in output["selected_skills"]), skill_ids)
        self.assertNotIn("selected_primary", output)
        self.assertNotIn("selected_optional", output)

    def test_no_matching_skill_does_not_trigger_legacy_fallback(self) -> None:
        """no_matching_skill 必須直接輸出空清單，不補入任意 fallback Skill。"""

        _write_skill(
            self.root,
            "phase4-unrelated",
            description="An office scheduling skill unrelated to the requested task.",
        )
        task = "a task with no matching capability"
        output = route(self._request(task, (), {
            "task_summary": task,
            "selected_skills": [],
            "selection_status": "no_matching_skill",
        }))
        self.assertEqual(output["selected_skills"], [])
        self.assertEqual(output["selection_status"], "no_matching_skill")

    def test_explicit_skill_survives_production_candidate_preparation(self) -> None:
        """explicit available Skill 仍直接進候選，final 仍需完成 handoff。"""

        for index in range(35):
            _write_skill(
                self.root,
                f"phase4-unrelated-{index}",
                description="Office scheduling and payroll support.",
            )
        explicit_id = "phase4-explicit"
        _write_skill(self.root, explicit_id, description="A specialized archive capability.")
        task = "a task about an unrelated topic"
        output = route(
            self._request(
                task,
                (explicit_id,),
                self._selected((explicit_id,), task),
                explicit_skill_ids=(explicit_id,),
            )
        )
        self.assertEqual(output["selected_skills"][0]["id"], explicit_id)

    def test_unavailable_disabled_controller_and_support_stay_rejected(self) -> None:
        """trusted-root unknown 不再餓死；unavailable、controller 與 routing-support 仍是 hard gates。"""

        cases = (
            ("phase4-unavailable", {"status": "unavailable"}),
            ("phase4-disabled", {"status": "disabled"}),
            ("phase4-controller", {"controller": True}),
            ("phase4-support", {"routing_support": True}),
        )
        for skill_id, options in cases:
            _write_skill(self.root, skill_id, **options)
            with self.subTest(skill_id=skill_id):
                request = self._request("phase4 task", (skill_id,), self._selected((skill_id,)))
                if options.get("controller") or options.get("routing_support"):
                    with self.assertRaises(ValueError):
                        route(request)
                else:
                    self.assertEqual(route(request)["selected_skills"][0]["id"], skill_id)
        _write_skill(self.root, "phase4-unknown", status="unknown")
        output = route(self._request("phase4 task", ("phase4-unknown",), self._selected(("phase4-unknown",))))
        self.assertEqual(output["selected_skills"][0]["id"], "phase4-unknown")

    def test_new_bilingual_renderer_has_only_new_selection_semantics(self) -> None:
        """雙語 renderer 只輸出 selected_skills/status，不渲染舊 PRIMARY/OPTIONAL。"""

        task = "phase4 task"
        payload = self._selected(("phase4-choice",), task)
        english = render_selection_payload(payload, language="en", user_request=task)
        traditional_chinese = render_selection_payload(payload, language="zh-TW", user_request="請處理 Phase 4 工作")
        for output in (english, traditional_chinese):
            self.assertIn("phase4-choice", output)
            self.assertIn("selected", output.lower())
            self.assertNotIn("PRIMARY", output)
            self.assertNotIn("OPTIONAL", output)
            self.assertNotIn("selected_primary", output)
            self.assertNotIn("selected_optional", output)

    def test_legacy_router_input_is_not_a_second_production_path(self) -> None:
        """舊 RouterInput 不得繼續觸發任何 final selection。"""

        with self.assertRaises(TypeError):
            route(RouterInput("legacy task", ()))

    def test_production_selector_source_has_no_old_selector_entrypoints(self) -> None:
        """production selector source 不保留固定 alias、舊 output 或 synthetic mapping。"""

        repository_root = Path(__file__).resolve().parents[1]
        routing_source = (repository_root / "codex_capability_router" / "routing.py").read_text(encoding="utf-8")
        for forbidden in (
            "_TASK_ALIASES",
            "classify_task",
            "selected_primary",
            "selected_optional",
            "native_model_sufficient",
            "no_safe_match",
            "phase4-choice",
        ):
            self.assertNotIn(forbidden, routing_source)


if __name__ == "__main__":
    unittest.main()
