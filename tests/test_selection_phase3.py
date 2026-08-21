"""Phase 3 Selection Contract 的 Python contract/state tests。"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from codex_capability_router.inventory import ProfileCache, refresh_skill_inventory
from codex_capability_router.selection import (
    FullInstructionHandoff,
    SelectionState,
    apply_correction,
    expanded_retrieve,
    handoff_full_instructions,
    prepare_selection,
    preliminary_select,
    render_selection,
    validate_selection,
)


def _write_skill(
    root: Path,
    skill_id: str,
    *,
    status: str = "available",
    controller: bool = False,
    routing_support: bool = False,
) -> None:
    """建立 temporary Skill fixture；ID 只存在測試，不加入 production mapping。"""

    directory = root / skill_id
    directory.mkdir(parents=True)
    metadata = [
        "---",
        f"name: {skill_id}",
        "description: A clear skill description for Phase 3 contract tests.",
        f"status: {status}",
    ]
    if controller:
        metadata.append("controller: true")
    if routing_support:
        metadata.append("routing_support: true")
    metadata.extend(["---", f"Full instructions for {skill_id}.", ""])
    (directory / "SKILL.md").write_text("\n".join(metadata), encoding="utf-8")


class SelectionContractTests(unittest.TestCase):
    """只驗證 Phase 3 的 schema、state、handoff 與 final validation。"""

    def _inventory(self, *skills: str):
        root = Path(self.temp_dir.name)
        for skill_id in skills:
            _write_skill(root, skill_id)
        return refresh_skill_inventory([root], cache=ProfileCache())

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_selection_schema_requires_consistent_status_and_list(self) -> None:
        """selected 必須非空，no_matching_skill 必須為空，其他 status 拒絕。"""

        valid_selected = {
            "task_summary": "建立技術文件",
            "selected_skills": [{"id": "document-skill", "reason": "可協助建立技術文件"}],
            "selection_status": "selected",
        }
        valid_empty = {
            "task_summary": "特殊工作",
            "selected_skills": [],
            "selection_status": "no_matching_skill",
        }
        self.assertEqual(validate_selection(valid_selected), valid_selected)
        self.assertEqual(validate_selection(valid_empty), valid_empty)
        for invalid in (
            {**valid_selected, "selected_skills": []},
            {**valid_empty, "selected_skills": [{"id": "x", "reason": "y"}]},
            {**valid_selected, "selection_status": "partial_coverage"},
            {**valid_selected, "selected_skills": [{"id": "x"}]},
        ):
            with self.subTest(invalid=invalid):
                with self.assertRaises(ValueError):
                    validate_selection(invalid)

    def test_prepare_preliminary_and_handoff_only_read_selected_skill(self) -> None:
        """初選後只對初選 ID 讀完整 SKILL.md，並記錄 handoff。"""

        inventory = self._inventory("phase3-selected", "phase3-not-selected")
        preparation = prepare_selection(inventory, "建立技術文件")
        preliminary = preliminary_select(preparation, ("phase3-selected",))
        original_read_bytes = Path.read_bytes
        with patch.object(Path, "read_bytes", autospec=True, side_effect=original_read_bytes) as read_bytes:
            handoffs = handoff_full_instructions(inventory, preliminary)
        self.assertEqual(tuple(handoff.id for handoff in handoffs), ("phase3-selected",))
        self.assertEqual(len(read_bytes.call_args_list), 1)
        selected_profile = next(profile for profile in inventory.profiles if profile.id == "phase3-selected")
        self.assertEqual(handoffs[0].fingerprint, selected_profile.fingerprint)
        self.assertIn("Full instructions", handoffs[0].instructions)

    def test_final_selection_requires_handoff_and_current_fingerprint(self) -> None:
        """未 handoff 或 handoff fingerprint 過期時不得通過 final validation。"""

        inventory = self._inventory("phase3-selected")
        preparation = prepare_selection(inventory, "建立技術文件")
        preliminary = preliminary_select(preparation, ("phase3-selected",))
        handoffs = handoff_full_instructions(inventory, preliminary)
        output = {
            "task_summary": "建立技術文件",
            "selected_skills": [{"id": "phase3-selected", "reason": "可協助目前工作"}],
            "selection_status": "selected",
        }
        self.assertEqual(validate_selection(output, inventory=inventory, handoffs=handoffs), output)
        with self.assertRaises(ValueError):
            validate_selection(output, inventory=inventory, handoffs=())

        skill_file = Path(self.temp_dir.name) / "phase3-selected" / "SKILL.md"
        skill_file.write_text(skill_file.read_text(encoding="utf-8") + "changed\n", encoding="utf-8")
        with self.assertRaises(ValueError):
            validate_selection(output, inventory=inventory, handoffs=handoffs)
        refreshed = refresh_skill_inventory([Path(self.temp_dir.name)], cache=ProfileCache())
        with self.assertRaises(ValueError):
            validate_selection(output, inventory=refreshed, handoffs=handoffs)

    def test_final_validator_rejects_unavailable_disabled_unknown_controller_and_support(self) -> None:
        """五種不可選 role/status 不得因 handoff 或 selected output 進入 final。"""

        root = Path(self.temp_dir.name)
        _write_skill(root, "phase3-valid")
        _write_skill(root, "phase3-unavailable", status="unavailable")
        _write_skill(root, "phase3-disabled", status="disabled")
        _write_skill(root, "phase3-unknown", status="unknown")
        _write_skill(root, "phase3-controller", controller=True)
        _write_skill(root, "phase3-support", routing_support=True)
        inventory = refresh_skill_inventory([root], cache=ProfileCache())
        valid_profile = next(profile for profile in inventory.profiles if profile.id == "phase3-valid")
        valid_handoff = FullInstructionHandoff("phase3-valid", valid_profile.fingerprint, "full")
        valid_output = {
            "task_summary": "測試",
            "selected_skills": [{"id": "phase3-valid", "reason": "可用"}],
            "selection_status": "selected",
        }
        self.assertEqual(validate_selection(valid_output, inventory=inventory, handoffs=(valid_handoff,)), valid_output)
        for profile in inventory.profiles:
            if profile.id == "phase3-valid":
                continue
            output = {
                "task_summary": "測試",
                "selected_skills": [{"id": profile.id, "reason": "候選"}],
                "selection_status": "selected",
            }
            handoff = FullInstructionHandoff(profile.id, profile.fingerprint, "full")
            with self.subTest(skill=profile.id), self.assertRaises(ValueError):
                validate_selection(output, inventory=inventory, handoffs=(handoff,))

    def test_correction_requires_handoff_and_allows_only_once(self) -> None:
        """替代 Skill 必須先 handoff，且 correction 最多一次。"""

        state = SelectionState()
        with self.assertRaises(ValueError):
            apply_correction(state, ("replacement",), handoffs=())
        replacement_handoff = FullInstructionHandoff("replacement", "a" * 64, "full")
        corrected = apply_correction(state, ("replacement",), handoffs=(replacement_handoff,))
        self.assertEqual(corrected.correction_count, 1)
        with self.assertRaises(ValueError):
            apply_correction(corrected, ("replacement-2",), handoffs=(replacement_handoff,))

    def test_applicability_and_expanded_retrieval_share_single_budget(self) -> None:
        """Applicability 最多一次；expanded retrieval 與 route 共用唯一額度。"""

        state = SelectionState()
        checked = state.start_applicability_check()
        expanded = checked.consume_expanded_retrieval()
        self.assertEqual(expanded.budget.expanded_retrievals_used, 1)
        with self.assertRaises(ValueError):
            expanded.consume_expanded_retrieval()
        with self.assertRaises(ValueError):
            expanded.start_applicability_check()

        already_used = SelectionState().consume_expanded_retrieval()
        with self.assertRaises(ValueError):
            already_used.consume_expanded_retrieval()

    def test_expanded_retrieve_updates_preparation_once(self) -> None:
        """實際 expanded retrieval 沿用 preparation budget，第二輪被拒絕。"""

        inventory = self._inventory("phase3-expanded")
        preparation = prepare_selection(inventory, "建立技術文件")
        expanded = expanded_retrieve(inventory, preparation)
        self.assertEqual(expanded.state.budget.expanded_retrievals_used, 1)
        self.assertEqual(expanded.state.retrieval_rounds, 2)
        with self.assertRaises(ValueError):
            expanded_retrieve(inventory, expanded)

    def test_render_emits_only_the_two_selection_statuses(self) -> None:
        """render 保持最小 JSON output，不引入舊 outcome 或額外 status。"""

        output = {
            "task_summary": "沒有匹配能力",
            "selected_skills": [],
            "selection_status": "no_matching_skill",
        }
        rendered = render_selection(output)
        self.assertEqual(json.loads(rendered), output)


if __name__ == "__main__":
    unittest.main()
