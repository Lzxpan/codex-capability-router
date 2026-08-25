"""v0.1.0-beta.4 Integration Hardening 的 public seam tests。"""

from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from codex_capability_router.catalog import render_recommendations
from codex_capability_router.discovery import discover_skill_roots
from codex_capability_router.inventory import ProfileCache, refresh_skill_inventory
from codex_capability_router.routing import SelectionRouteInput, SelectionReceipt, route
from codex_capability_router.selection import FullInstructionHandoff, SelectionState, apply_correction, validate_selection
from codex_capability_router.validation import record_from_mapping


def _write_skill(root: Path, skill_id: str, *, display_name: str | None = None) -> None:
    """建立 integration test Skill；machine path 使用 canonical ID，name 保留 display name。"""

    directory = root / skill_id
    directory.mkdir(parents=True)
    name = display_name or skill_id
    metadata = [
        "---",
        f"id: {skill_id}",
        f"name: {name}",
        "description: A bounded integration-hardening test Skill.",
        "status: available",
        "---",
        "Full instructions are private and must not enter the receipt.",
        "",
    ]
    (directory / "SKILL.md").write_text("\n".join(metadata), encoding="utf-8")


def _write_skill_without_id(root: Path, directory_name: str, display_name: str) -> None:
    """建立只提供 display name 的 metadata，canonical ID 應由 allowlisted 目錄提供。"""

    directory = root / directory_name
    directory.mkdir(parents=True)
    metadata = [
        "---",
        f"name: {display_name}",
        "description: A bounded canonical-id integration Skill.",
        "status: available",
        "---",
        "Canonical ID comes from the discovered entry, not its display name.",
        "",
    ]
    (directory / "SKILL.md").write_text("\n".join(metadata), encoding="utf-8")


class IntegrationHardeningReceiptTests(unittest.TestCase):
    """驗證 production route 才能產生正式、可稽核的 selection receipt。"""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        _write_skill(self.root, "receipt-skill", display_name="Receipt Skill Display Name")

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    @staticmethod
    def _request(final_selection: dict[str, object], *, preliminary: tuple[str, ...] = ("receipt-skill",)) -> SelectionRouteInput:
        """建立明確 production route request，避免測試自行模擬 receipt。"""

        return SelectionRouteInput(
            task_summary="Prepare a bounded selection receipt.",
            skill_roots=(Path("."),),
            preliminary_skill_ids=preliminary,
            final_selection=final_selection,
        )

    def _route_request(self, final_selection: dict[str, object], *, preliminary: tuple[str, ...] = ("receipt-skill",)) -> SelectionRouteInput:
        """將測試 request 指向明確 temporary Skill root。"""

        request = self._request(final_selection, preliminary=preliminary)
        return SelectionRouteInput(
            task_summary=request.task_summary,
            skill_roots=(self.root,),
            preliminary_skill_ids=request.preliminary_skill_ids,
            final_selection=request.final_selection,
        )

    def test_successful_route_returns_automatic_finalized_receipt(self) -> None:
        """成功 route 必須自動產生完整 receipt，且只保存 canonical IDs。"""

        task = "Prepare a bounded selection receipt."
        receipt = route(
            self._route_request(
                {
                    "task_summary": task,
                    "selected_skills": [{"id": "receipt-skill", "reason": "Codex judged it applicable."}],
                    "selection_status": "selected",
                }
            )
        )
        self.assertIsInstance(receipt, SelectionReceipt)
        payload = receipt.to_mapping()
        self.assertEqual(payload["router_invoked"], True)
        self.assertEqual(payload["contract_version"], "0.1.0-beta.4")
        self.assertEqual(payload["candidate_skills"], ["receipt-skill"])
        self.assertEqual(payload["preliminary_selected_skills"], ["receipt-skill"])
        self.assertEqual(payload["full_handoff_skills"], ["receipt-skill"])
        self.assertEqual(payload["selected_skills"], [{"id": "receipt-skill", "reason": "Codex judged it applicable."}])
        self.assertEqual(payload["selection_status"], "selected")
        self.assertFalse(payload["expanded_retrieval"])
        self.assertFalse(payload["correction"])
        self.assertEqual(payload["selection_state"], "FINALIZED")
        self.assertNotIn("Receipt Skill Display Name", json.dumps(payload, ensure_ascii=False))
        self.assertNotIn("Full instructions", json.dumps(payload, ensure_ascii=False))
        self.assertNotIn(str(self.root), json.dumps(payload, ensure_ascii=False))

    def test_no_matching_route_returns_automatic_empty_receipt(self) -> None:
        """no_matching_skill 也必須由 production route 自動產生 receipt。"""

        task = "No matching integration-hardening task."
        receipt = route(
            self._route_request(
                {
                    "task_summary": task,
                    "selected_skills": [],
                    "selection_status": "no_matching_skill",
                },
                preliminary=(),
            )
        )
        self.assertIsInstance(receipt, SelectionReceipt)
        payload = receipt.to_mapping()
        self.assertTrue(payload["router_invoked"])
        self.assertEqual(payload["candidate_skills"], ["receipt-skill"])
        self.assertEqual(payload["preliminary_selected_skills"], [])
        self.assertEqual(payload["full_handoff_skills"], [])
        self.assertEqual(payload["selected_skills"], [])
        self.assertEqual(payload["selection_status"], "no_matching_skill")
        self.assertEqual(payload["selection_state"], "FINALIZED")

    def test_formal_renderer_rejects_handwritten_receipt_mapping(self) -> None:
        """普通 dict 即使欄位完整，也不得被正式 production renderer 當成 receipt。"""

        handwritten = {
            "router_invoked": True,
            "contract_version": "0.1.0-beta.4",
            "task_summary": "handwritten result",
            "candidate_skills": ["receipt-skill"],
            "preliminary_selected_skills": ["receipt-skill"],
            "full_handoff_skills": ["receipt-skill"],
            "selected_skills": [{"id": "receipt-skill", "reason": "handwritten"}],
            "selection_status": "selected",
            "expanded_retrieval": False,
            "correction": False,
            "selection_state": "FINALIZED",
        }
        with self.assertRaises(TypeError):
            render_recommendations(handwritten, language="en")

    def test_receipt_records_bounded_pre_final_transitions(self) -> None:
        """Expanded Retrieval 與 correction 可在 final 前各使用一次，receipt 正確記錄。"""

        _write_skill(self.root, "correction-skill", display_name="Correction Skill Display Name")
        task = "Prepare a bounded selection receipt."
        receipt = route(
            SelectionRouteInput(
                task_summary=task,
                skill_roots=(self.root,),
                preliminary_skill_ids=("receipt-skill",),
                correction_skill_ids=("correction-skill",),
                expanded_retrieval=True,
                final_selection={
                    "task_summary": task,
                    "selected_skills": [{"id": "correction-skill", "reason": "Correction applicability confirmed."}],
                    "selection_status": "selected",
                },
            )
        )

        payload = receipt.to_mapping()
        self.assertTrue(payload["expanded_retrieval"])
        self.assertTrue(payload["correction"])
        self.assertEqual(payload["selection_state"], "FINALIZED")
        self.assertEqual(payload["selected_skills"][0]["id"], "correction-skill")


class IntegrationHardeningCanonicalIdTests(unittest.TestCase):
    """驗證 discovery、handoff 與 final selection 全程使用 canonical ID。"""

    def test_discovery_uses_entry_id_when_frontmatter_has_only_display_name(self) -> None:
        """缺少 machine id 時使用明確 entry 名稱，不把 display name 當 ID。"""

        with tempfile.TemporaryDirectory() as value:
            root = Path(value)
            canonical_id = "verification-before-completion"
            _write_skill_without_id(root, canonical_id, "Verification Before Completion")

            result = discover_skill_roots((root,))

            self.assertEqual([record.id for record in result.records], [canonical_id])
            self.assertEqual(result.records[0].name, "Verification Before Completion")
            self.assertEqual(result.diagnostics, ())

    def test_inventory_profile_and_route_use_canonical_id_on_first_attempt(self) -> None:
        """第一次正式 route 即可用 canonical ID 完成，不依賴 display-name retry。"""

        with tempfile.TemporaryDirectory() as value:
            root = Path(value)
            canonical_id = "verification-before-completion"
            _write_skill_without_id(root, canonical_id, "Verification Before Completion")
            inventory = refresh_skill_inventory((root,), cache=ProfileCache())
            receipt = route(
                SelectionRouteInput(
                    task_summary="Verify the completed implementation.",
                    skill_roots=(root,),
                    preliminary_skill_ids=(canonical_id,),
                    final_selection={
                        "task_summary": "Verify the completed implementation.",
                        "selected_skills": [{"id": canonical_id, "reason": "Verification is required."}],
                        "selection_status": "selected",
                    },
                )
            )
            self.assertEqual([profile.id for profile in inventory.profiles], [canonical_id])
            self.assertEqual(receipt["selected_skills"][0]["id"], canonical_id)
            self.assertNotIn("Verification Before Completion", receipt.to_mapping()["selected_skills"])

    def test_display_name_cannot_be_used_as_selected_id(self) -> None:
        """display name 不得穿透 final validation 成為 machine ID。"""

        with tempfile.TemporaryDirectory() as value:
            root = Path(value)
            _write_skill(root, "canonical-skill", display_name="Verification Before Completion")
            with self.assertRaises(ValueError):
                route(
                    SelectionRouteInput(
                        task_summary="Verify the completed implementation.",
                        skill_roots=(root,),
                        preliminary_skill_ids=("canonical-skill",),
                        final_selection={
                            "task_summary": "Verify the completed implementation.",
                            "selected_skills": [
                                {"id": "Verification Before Completion", "reason": "display name is not an ID"}
                            ],
                            "selection_status": "selected",
                        },
                    )
                )

    def test_mapping_without_id_is_rejected_instead_of_guessing_from_display_name(self) -> None:
        """runtime/manual mapping 缺少 canonical id 時不得把 name 當 machine ID。"""

        with self.assertRaises(ValueError):
            record_from_mapping(
                {
                    "name": "Verification Before Completion",
                    "kind": "skill",
                    "status": "available",
                    "source": "runtime:codex",
                }
            )


class IntegrationHardeningFinalizationTests(unittest.TestCase):
    """驗證 final selection 封存後不可被當成 workflow state 修改。"""

    def test_finalized_state_rejects_expanded_correction_and_changed_selection(self) -> None:
        """FINALIZED 後三種 selection transition 都必須拒絕。"""

        finalized = SelectionState().finalize(("route-a-skill",))
        handoff = FullInstructionHandoff("replacement-skill", "a" * 64, "full instructions")
        changed_payload = {
            "task_summary": "new work",
            "selected_skills": [{"id": "replacement-skill", "reason": "new work"}],
            "selection_status": "selected",
        }

        self.assertEqual(finalized.lifecycle, "FINALIZED")
        with self.assertRaises(ValueError):
            finalized.consume_expanded_retrieval()
        with self.assertRaises(ValueError):
            apply_correction(finalized, ("replacement-skill",), handoffs=(handoff,))
        with self.assertRaises(ValueError):
            validate_selection(changed_payload, state=finalized)

    def test_new_work_starts_an_independent_route_state(self) -> None:
        """Route A 封存後的新 debugging 工作只能從新的 OPEN state 開始。"""

        route_a = SelectionState().finalize(("executing-plans", "verification-before-completion"))
        route_b = SelectionState()

        self.assertEqual(route_a.lifecycle, "FINALIZED")
        self.assertEqual(route_a.final_selected_skill_ids, ("executing-plans", "verification-before-completion"))
        self.assertEqual(route_b.lifecycle, "OPEN")
        route_b_finalized = route_b.finalize(("systematic-debugging",))
        self.assertEqual(route_b_finalized.final_selected_skill_ids, ("systematic-debugging",))
        self.assertEqual(route_a.final_selected_skill_ids, ("executing-plans", "verification-before-completion"))


if __name__ == "__main__":
    unittest.main()
