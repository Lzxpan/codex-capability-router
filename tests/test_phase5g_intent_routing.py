"""Phase 4 migration tests for deprecated structured-intent output semantics。"""

from __future__ import annotations

import unittest

from codex_capability_router.catalog import render_recommendations
from codex_capability_router.selection import validate_selection


class Phase5GIntentRoutingTests(unittest.TestCase):
    """舊 action taxonomy 不再決定 final selection 或空結果語意。"""

    def test_native_model_sufficient_is_not_a_new_selection_status(self) -> None:
        """新版核心只接受 selected 與 no_matching_skill。"""

        payload = {
            "task_summary": "rewrite text",
            "selected_skills": [],
            "selection_status": "native_model_sufficient",
        }
        with self.assertRaises(ValueError):
            validate_selection(payload)
        with self.assertRaises(ValueError):
            render_recommendations(payload)

    def test_old_action_fields_cannot_rewrite_valid_codex_output(self) -> None:
        """新版 output 不保存 action/constraint taxonomy，也不自行補 Skill。"""

        payload = {
            "task_summary": "Rewrite firmware UART notes naturally.",
            "selected_skills": [],
            "selection_status": "no_matching_skill",
        }
        validated = validate_selection(payload)
        self.assertEqual(validated, payload)
        self.assertNotIn("action_requirements", validated)
        self.assertNotIn("execution_constraints", validated)


if __name__ == "__main__":
    unittest.main()
