"""Phase 2 Basic/Enriched Profile 與 recall-first Candidate Retrieval tests。"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from codex_capability_router.discovery import import_runtime_envelope
from codex_capability_router.inventory import (
    EnrichedProfile,
    ProfileCache,
    RetrievalBudget,
    refresh_skill_inventory,
    retrieve_candidates,
)
from codex_capability_router.models import DiscoveryResult
from codex_capability_router.validation import record_from_mapping


def _write_skill(
    directory: Path,
    name: str,
    *,
    description: str = "A synthetic skill for unrelated office scheduling.",
    status: str | None = "available",
    summary: str | None = None,
    limitations: tuple[str, ...] = (),
    requirements: tuple[str, ...] = (),
    triggers: tuple[str, ...] = (),
    provides: tuple[str, ...] = (),
    body: str = "Synthetic instructions.",
) -> None:
    """建立 Phase 2 temporary Skill；synthetic IDs 僅存在測試 fixture。"""

    directory.mkdir(parents=True)
    lines = ["---", f"id: {name}", f"name: {name}", f"description: {description}"]
    if status is not None:
        lines.append(f"status: {status}")
    if summary is not None:
        lines.append(f"summary: {summary}")
    if limitations:
        lines.append(f"limitations: {json.dumps(list(limitations), ensure_ascii=False)}")
    if requirements:
        lines.append(f"requirements: {json.dumps(list(requirements), ensure_ascii=False)}")
    if triggers:
        lines.append(f"triggers: {json.dumps(list(triggers), ensure_ascii=False)}")
    if provides:
        lines.append(f"provides: {json.dumps(list(provides), ensure_ascii=False)}")
    lines.extend(["---", body, ""])
    (directory / "SKILL.md").write_text("\n".join(lines), encoding="utf-8")


def _runtime_record(
    capability_id: str,
    status: str,
    *,
    controller: bool = False,
    routing_support: bool = False,
):
    """建立 runtime eligibility fixture，避免測試依賴 production Skill ID。"""

    return record_from_mapping(
        {
            "id": capability_id,
            "name": capability_id,
            "kind": "skill",
            "status": status,
            "categories": [],
            "triggers": [],
            "priority": 0,
            "overlap_group": None,
            "preferred_for": [],
            "requires": [],
            "source": "runtime:phase2-test",
            "last_verified": None,
            "controller": controller,
            "routing_support": routing_support,
        }
    )


class Phase2ProfileRetrievalTests(unittest.TestCase):
    """只驗證候選召回與 Profile handoff，不驗證 final selection。"""

    def test_basic_profile_contract_remains_minimal_and_available(self) -> None:
        """Basic Profile 保留必要欄位，缺少舊 metadata 仍可進候選。"""

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _write_skill(
                root / "unknown-metadata",
                "synthetic-unknown-metadata",
                description="A useful engineering source reader with no taxonomy metadata.",
            )
            inventory = refresh_skill_inventory([root], cache=ProfileCache())

            profile = inventory.profiles[0]
            self.assertEqual(profile.id, "synthetic-unknown-metadata")
            self.assertEqual(profile.name, "synthetic-unknown-metadata")
            self.assertEqual(profile.status.value, "available")
            self.assertTrue(profile.source)
            self.assertTrue(profile.fingerprint)
            result = retrieve_candidates(inventory, "analyze engineering source")
            self.assertEqual([item.id for item in result.candidates], [profile.id])

    def test_sufficient_description_does_not_read_full_skill_instructions(self) -> None:
        """description 足夠時，retrieval 不讀完整 SKILL.md 建立 Enriched Profile。"""

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _write_skill(
                root / "clear",
                "synthetic-clear-skill",
                description="Analyzes engineering source files and writes structured findings.",
                body="FULL_INSTRUCTIONS_MUST_NOT_BE_READ_FOR_CLEAR_DESCRIPTION",
            )
            inventory = refresh_skill_inventory([root], cache=ProfileCache())

            with patch.object(Path, "read_text", side_effect=AssertionError("unexpected full instruction read")):
                result = retrieve_candidates(inventory, "analyze engineering source")

            self.assertEqual(result.enriched_profiles, ())
            self.assertEqual([item.id for item in result.candidates], ["synthetic-clear-skill"])

    def test_short_description_builds_minimal_enriched_profile(self) -> None:
        """description 太短時才讀完整 SKILL.md，且只保留 summary/limitations/requirements。"""

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _write_skill(
                root / "short",
                "synthetic-short-skill",
                description="short",
                summary="Reads engineering source files.",
                limitations=("Does not compile code.",),
                requirements=("A source directory.",),
                body="FULL_BODY_IS_NOT_STORED_IN_ENRICHED_PROFILE",
            )
            inventory = refresh_skill_inventory([root], cache=ProfileCache())

            result = retrieve_candidates(inventory, "engineering source")

            self.assertEqual([item.id for item in result.candidates], ["synthetic-short-skill"])
            self.assertEqual(len(result.enriched_profiles), 1)
            enriched = result.enriched_profiles[0]
            self.assertEqual(enriched.id, "synthetic-short-skill")
            self.assertEqual(enriched.summary, "Reads engineering source files.")
            self.assertEqual(enriched.limitations, ("Does not compile code.",))
            self.assertEqual(enriched.requirements, ("A source directory.",))
            self.assertNotIn("FULL_BODY_IS_NOT_STORED", repr(enriched))

    def test_large_inventory_searches_each_work_part_and_keeps_recall(self) -> None:
        """90 筆 inventory 中，分散於不同 work part 的相關 Skill 不得被 pre-filter 漏掉。"""

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for index in range(87):
                _write_skill(
                    root / f"unrelated-{index:02d}",
                    f"synthetic-unrelated-{index:02d}",
                    description="Manages office calendar scheduling and contact lists.",
                )
            _write_skill(
                root / "source-reader",
                "synthetic-source-reader",
                description="Reads and analyzes engineering source code.",
            )
            _write_skill(
                root / "diagram-maker",
                "synthetic-diagram-maker",
                description="Creates architecture diagrams for technical systems.",
            )
            _write_skill(
                root / "document-writer",
                "synthetic-document-writer",
                description="Writes technical documents from verified engineering notes.",
            )
            _write_skill(
                root / "metadata-only",
                "synthetic-metadata-only",
                description="A tool.",
                triggers=("architecture", "diagram"),
                provides=("technical diagram",),
            )
            inventory = refresh_skill_inventory([root], cache=ProfileCache())

            result = retrieve_candidates(
                inventory,
                "prepare a project deliverable",
                work_parts=(
                    "analyze engineering source",
                    "draw architecture diagram",
                    "write technical document",
                ),
            )
            candidate_ids = {item.id for item in result.candidates}

            self.assertTrue(
                {
                    "synthetic-source-reader",
                    "synthetic-diagram-maker",
                    "synthetic-document-writer",
                } <= candidate_ids
            )
            self.assertIn("synthetic-metadata-only", candidate_ids)
            self.assertLess(len(candidate_ids), len(inventory.profiles))

    def test_existing_enriched_summary_can_recall_candidate(self) -> None:
        """既有 Enriched summary 可參與搜尋，不需重新讀取完整 SKILL.md。"""

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for index in range(39):
                _write_skill(
                    root / f"unrelated-{index:02d}",
                    f"synthetic-unrelated-{index:02d}",
                    description="Manages office calendar scheduling.",
                )
            _write_skill(
                root / "known",
                "synthetic-known-summary",
                description="A short utility.",
            )
            inventory = refresh_skill_inventory([root], cache=ProfileCache())
            known = EnrichedProfile(
                id="synthetic-known-summary",
                summary="Creates architecture diagrams.",
                limitations=(),
                requirements=(),
            )

            result = retrieve_candidates(
                inventory,
                "draw architecture diagram",
                known_enriched_profiles=(known,),
            )

            self.assertIn("synthetic-known-summary", {item.id for item in result.candidates})

    def test_explicit_available_skill_is_retained_but_ineligible_is_excluded(self) -> None:
        """explicit Skill 只 bypass retrieval；不可用或角色不合法仍被排除。"""

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _write_skill(root / "explicit", "synthetic-explicit-available", description="Calendar helper.")
            _write_skill(root / "unavailable", "synthetic-explicit-unavailable", status="unavailable")
            _write_skill(root / "disabled", "synthetic-explicit-disabled", status="disabled")
            _write_skill(root / "unknown", "synthetic-explicit-unknown", status=None)
            runtime = import_runtime_envelope(
                {
                    "capabilities": [
                        _runtime_record("synthetic-explicit-controller", "available", controller=True).to_mapping(),
                        _runtime_record("synthetic-explicit-support", "available", routing_support=True).to_mapping(),
                    ]
                }
            )
            inventory = refresh_skill_inventory([root], cache=ProfileCache(), runtime=runtime)

            result = retrieve_candidates(
                inventory,
                "a completely unrelated topic",
                explicit_skill_ids=(
                    "synthetic-explicit-available",
                    "synthetic-explicit-unavailable",
                    "synthetic-explicit-disabled",
                    "synthetic-explicit-unknown",
                    "synthetic-explicit-controller",
                    "synthetic-explicit-support",
                ),
            )
            candidate_ids = {item.id for item in result.candidates}

            self.assertEqual(
                candidate_ids,
                {
                    "synthetic-explicit-available",
                    "synthetic-explicit-unavailable",
                    "synthetic-explicit-disabled",
                    "synthetic-explicit-unknown",
                },
            )

    def test_expanded_retrieval_can_run_once_and_rejects_third_round(self) -> None:
        """expanded retrieval budget 僅能從 0 消耗到 1，第三輪必須拒絕。"""

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for index in range(39):
                _write_skill(
                    root / f"unrelated-{index:02d}",
                    f"synthetic-unrelated-{index:02d}",
                    description="Maintains office calendar scheduling.",
                )
            _write_skill(root / "weak", "synthetic-weak-diagram", description="diagram")
            inventory = refresh_skill_inventory([root], cache=ProfileCache())

            first = retrieve_candidates(
                inventory,
                "prepare deliverable",
                work_parts=("draw diagram",),
                budget=RetrievalBudget(),
            )
            second = retrieve_candidates(
                inventory,
                "prepare deliverable",
                work_parts=("draw diagram",),
                budget=first.budget,
                use_expanded=True,
            )

            self.assertNotIn("synthetic-weak-diagram", {item.id for item in first.candidates})
            self.assertIn("synthetic-weak-diagram", {item.id for item in second.candidates})
            self.assertEqual(second.budget.expanded_retrievals_used, 1)
            with self.assertRaises(ValueError):
                retrieve_candidates(
                    inventory,
                    "prepare deliverable",
                    work_parts=("draw diagram",),
                    budget=second.budget,
                    use_expanded=True,
                )
            with self.assertRaises(ValueError):
                RetrievalBudget(expanded_retrievals_used=2)


if __name__ == "__main__":
    unittest.main()
