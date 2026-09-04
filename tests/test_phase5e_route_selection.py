"""Phase 4 route-only and hard-gate regression tests。"""

from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from codex_capability_router.models import RouterInput
from codex_capability_router.routing import SelectionRouteInput, route
from tests.test_phase4_production import _write_skill


class Phase5ERouteSelectionTests(unittest.TestCase):
    """保留 route-only advisory 與 controller/support/availability 邊界。"""

    def test_valid_skill_is_selected_only_from_codex_output(self) -> None:
        """valid available Skill 通過 handoff/validation，Python 不自行選擇。"""

        with tempfile.TemporaryDirectory() as value:
            root = Path(value)
            _write_skill(root, "phase5e-valid")
            payload = {
                "task_summary": "route-only task",
                "selected_skills": [{"id": "phase5e-valid", "reason": "Codex selected it."}],
                "selection_status": "selected",
            }
            request = SelectionRouteInput(
                task_summary="route-only task",
                skill_roots=(root,),
                preliminary_skill_ids=("phase5e-valid",),
                final_selection=payload,
            )
            result = route(request)
            self.assertEqual(result.selection_payload(), payload)
            self.assertTrue(result["router_invoked"])

    def test_controller_and_support_only_role_gates_remain(self) -> None:
        """既有 hard gates 仍在新版 production path 生效。"""

        with tempfile.TemporaryDirectory() as value:
            root = Path(value)
            for skill_id, options in (
                ("phase5e-controller", {"controller": True}),
                ("phase5e-support", {"routing_support": True}),
                ("phase5e-unavailable", {"status": "unavailable"}),
            ):
                _write_skill(root, skill_id, **options)
                payload = {
                    "task_summary": "route-only task",
                    "selected_skills": [{"id": skill_id, "reason": "invalid"}],
                    "selection_status": "selected",
                }
                request = SelectionRouteInput(
                    task_summary="route-only task",
                    skill_roots=(root,),
                    preliminary_skill_ids=(skill_id,),
                    final_selection=payload,
                )
                with self.subTest(skill_id=skill_id):
                    if skill_id.endswith("controller") or skill_id.endswith("support"):
                        with self.assertRaises(ValueError):
                            route(request)
                    else:
                        self.assertEqual(route(request)["selected_skills"][0]["id"], skill_id)

    def test_legacy_router_input_cannot_trigger_selection(self) -> None:
        """舊 RouterInput 不得成為第二 production path。"""

        with self.assertRaises(TypeError):
            route(RouterInput("legacy task", ()))


if __name__ == "__main__":
    unittest.main()
