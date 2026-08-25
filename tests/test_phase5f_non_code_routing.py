"""Phase 4 metadata preservation regression tests。"""

from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from codex_capability_router.routing import SelectionRouteInput, route
from tests.test_phase4_production import _write_skill


class Phase5FNonCodeRoutingTests(unittest.TestCase):
    """metadata 可保留供 discovery/retrieval，但不能接管 Codex final selection。"""

    def test_metadata_does_not_override_codex_selection(self) -> None:
        """categories/triggers/provides 仍可存在，final ID 仍以 Codex output 為準。"""

        with tempfile.TemporaryDirectory() as value:
            root = Path(value)
            _write_skill(root, "phase5f-document", categories=("document",), triggers=("document",))
            _write_skill(root, "phase5f-image", categories=("image",), triggers=("image",))
            payload = {
                "task_summary": "document task",
                "selected_skills": [{"id": "phase5f-image", "reason": "Codex selected the image capability."}],
                "selection_status": "selected",
            }
            request = SelectionRouteInput(
                task_summary="document task",
                skill_roots=(root,),
                preliminary_skill_ids=("phase5f-image",),
                final_selection=payload,
            )
            result = route(request)
            self.assertEqual(result.selection_payload(), payload)
            self.assertTrue(result["router_invoked"])

    def test_selection_output_has_no_execution_or_artifact_fallback(self) -> None:
        """route 只回傳新版 selection contract，不管理 workflow 或 artifact execution。"""

        with tempfile.TemporaryDirectory() as value:
            root = Path(value)
            _write_skill(root, "phase5f-valid")
            payload = {
                "task_summary": "artifact task",
                "selected_skills": [],
                "selection_status": "no_matching_skill",
            }
            request = SelectionRouteInput(
                task_summary="artifact task",
                skill_roots=(root,),
                preliminary_skill_ids=(),
                final_selection=payload,
            )
            result = route(request)
            self.assertEqual(result.selection_payload(), payload)
            self.assertTrue(result["router_invoked"])
            self.assertNotIn("execution_allowed", result)
            self.assertNotIn("workflow", result)


if __name__ == "__main__":
    unittest.main()
