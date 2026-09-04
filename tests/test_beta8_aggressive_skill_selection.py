"""beta8 Skill semantic-selection policy regression tests。"""

from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from codex_capability_router.inventory import refresh_skill_inventory
from codex_capability_router.routing import SelectionRouteInput, route
from codex_capability_router.selection import validate_coverage_additions, validate_selection
from codex_capability_router.task_analysis import TaskAnalysis


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def _write_skill(root: Path, skill_id: str, *, overlap_group: str | None = None) -> None:
    skill_dir = root / skill_id
    skill_dir.mkdir(parents=True)
    lines = [
        "---",
        f"id: {skill_id}",
        f"name: {skill_id}",
        "description: A plausible task-relevant Skill.",
        "status: available",
    ]
    if overlap_group is not None:
        lines.append(f"overlap_group: {overlap_group}")
    lines.extend(["---", f"Instructions for {skill_id}.", ""])
    (skill_dir / "SKILL.md").write_text("\n".join(lines), encoding="utf-8")


class Beta8AggressiveSkillSelectionTests(unittest.TestCase):
    """固定 beta8 的選擇政策與 exact-identity 安全邊界。"""

    def test_current_skill_policy_removes_semantic_redundancy_gates(self) -> None:
        skill_contract = (REPOSITORY_ROOT / "SKILL.md").read_text(encoding="utf-8")
        policy = (REPOSITORY_ROOT / "references" / "routing-policy.md").read_text(encoding="utf-8")
        skill_section = policy.split("## v0.2 Supporting Provider selection override", 1)[0]

        for phrase in (
            "plausible task-relevant value",
            "Semantic overlap is neutral",
            "no fixed Skill selection maximum",
            "At most one bounded Skill Coverage Check",
        ):
            self.assertIn(phrase, skill_contract if phrase.startswith(("Semantic", "At most")) else skill_section)
        for forbidden in (
            "Select every Skill with material, non-redundant value",
            "Exclude only clearly irrelevant or redundant capabilities",
            "same `overlap_group` 只保留排序後第一筆",
            "最多 3 筆",
            "最多 2 筆",
        ):
            self.assertNotIn(forbidden, skill_section)

    def test_relevant_same_overlap_group_skills_can_both_be_selected(self) -> None:
        with tempfile.TemporaryDirectory() as value:
            root = Path(value)
            _write_skill(root, "skill-one", overlap_group="same-method")
            _write_skill(root, "skill-two", overlap_group="same-method")
            task = "prepare a technical review"
            selection = {
                "task_summary": task,
                "selected_skills": [
                    {"id": "skill-one", "reason": "It may help review the implementation."},
                    {"id": "skill-two", "reason": "It may provide another useful review method."},
                ],
                "selection_status": "selected",
            }
            receipt = route(
                SelectionRouteInput(
                    task_summary=task,
                    skill_roots=(root,),
                    preliminary_skill_ids=("skill-one", "skill-two"),
                    final_selection=selection,
                )
            )
            self.assertEqual(
                tuple(item["id"] for item in receipt["selected_skills"]),
                ("skill-one", "skill-two"),
            )

    def test_exact_canonical_duplicate_still_has_one_logical_skill(self) -> None:
        with tempfile.TemporaryDirectory() as first, tempfile.TemporaryDirectory() as second:
            first_root, second_root = Path(first), Path(second)
            _write_skill(first_root, "same-skill")
            _write_skill(second_root, "same-skill")
            inventory = refresh_skill_inventory((first_root, second_root))
            self.assertEqual(tuple(profile.id for profile in inventory.profiles), ("same-skill",))

    def test_coverage_check_can_add_relevant_overlapping_skill(self) -> None:
        analysis = TaskAnalysis("review", ("inspect source",), (), (), ())
        additions = validate_coverage_additions(
            {
                "additions": [
                    {
                        "id": "overlapping-skill",
                        "supports": [{"section": "work_items", "index": 0}],
                        "distinct_value": "Another relevant method for the same work item.",
                    }
                ]
            },
            candidate_ids=("base-skill", "overlapping-skill"),
            selected_ids=("base-skill",),
            task_analysis=analysis,
        )
        self.assertEqual(additions[0].id, "overlapping-skill")

    def test_skill_selection_has_no_fixed_maximum(self) -> None:
        payload = {
            "task_summary": "a broad task",
            "selected_skills": [
                {"id": f"skill-{index}", "reason": "Plausibly useful for part of the task."}
                for index in range(12)
            ],
            "selection_status": "selected",
        }
        self.assertEqual(len(validate_selection(payload)["selected_skills"]), 12)


if __name__ == "__main__":
    unittest.main()
