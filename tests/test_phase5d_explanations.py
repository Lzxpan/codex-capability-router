"""Phase 4 bilingual rendering regression tests for the new selection output。"""

from __future__ import annotations

import unittest

from codex_capability_router.catalog import render_selection_payload


class Phase5DExplanationTests(unittest.TestCase):
    """保留雙語與公開 reason，移除舊 PRIMARY/OPTIONAL explanation semantics。"""

    def test_selected_skill_render_keeps_id_and_reason(self) -> None:
        """新版 renderer 只呈現 Codex 提供的 selected Skill 與公開理由。"""

        payload = {
            "task_summary": "Review the supplied source.",
            "selected_skills": [{"id": "source-review", "reason": "Codex judged it applicable."}],
            "selection_status": "selected",
        }
        output = render_selection_payload(payload, language="en")
        self.assertIn("source-review", output)
        self.assertIn("Codex judged it applicable.", output)
        self.assertNotIn("PRIMARY", output)
        self.assertNotIn("OPTIONAL", output)

    def test_no_matching_render_has_no_silent_fallback(self) -> None:
        """no_matching_skill 只渲染空選擇，不補入其他 Skill 或 native outcome。"""

        payload = {
            "task_summary": "No matching task.",
            "selected_skills": [],
            "selection_status": "no_matching_skill",
        }
        for language in ("en", "zh-TW"):
            with self.subTest(language=language):
                output = render_selection_payload(payload, language=language)
                self.assertIn("no_matching_skill", output)
                self.assertNotIn("native_model_sufficient", output)
                self.assertNotIn("PRIMARY", output)
                self.assertNotIn("OPTIONAL", output)

    def test_invalid_status_is_rejected_before_render(self) -> None:
        """renderer 不接受舊 outcome 或新增 status taxonomy。"""

        payload = {
            "task_summary": "Invalid output.",
            "selected_skills": [],
            "selection_status": "native_model_sufficient",
        }
        with self.assertRaises(ValueError):
            render_selection_payload(payload)


if __name__ == "__main__":
    unittest.main()
