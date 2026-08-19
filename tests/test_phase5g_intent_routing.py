"""Phase 5G-B structured intent-aware routing behavior tests。

修改紀錄（2026-08-19，Steve Peng）
原始內容：Phase 5G-A 只有 topic-based routing，沒有 bounded structured task semantics。
修改原因：以恰好六個 behavior tests 固定 explicit request、action requirement、
execution constraint、native-model outcome 與 controller presentation contract。
修改後功能：先以 synthetic registry 驗證 Phase 5G-B RED/GREEN 行為，不修改 canonical
12-scenario fixture，也不掃描或執行真實 capability。
"""

from __future__ import annotations

import unittest

from codex_capability_router.catalog import render_recommendations
from codex_capability_router.models import RouterInput
from codex_capability_router.routing import route
from codex_capability_router.validation import record_from_mapping


def _record(
    *,
    capability_id: str,
    name: str | None = None,
    status: str = "installed",
    kind: str = "skill",
    category: str = "generic",
    triggers: tuple[str, ...] = (),
    provides: tuple[str, ...] = (),
    priority: int = 10,
    overlap_group: str | None = None,
    aliases: tuple[str, ...] = (),
    controller: bool = False,
) :
    """建立最小 synthetic canonical record，避免測試依賴真實 inventory。"""

    payload = {
        "id": capability_id,
        "name": name or capability_id,
        "kind": kind,
        "status": status,
        "categories": [category],
        "triggers": list(triggers),
        "priority": priority,
        "overlap_group": overlap_group,
        "preferred_for": [],
        "requires": [],
        "source": "fixture:phase5g",
        "last_verified": None,
        "aliases": list(aliases),
        "provides": list(provides),
    }
    if controller:
        payload["controller"] = True
    return record_from_mapping(payload)


def _request(
    task: str,
    records,
    *,
    explicit_requests: tuple[str, ...] = (),
    action_requirements: tuple[str, ...] = (),
    execution_constraints: tuple[str, ...] = (),
    language: str = "en",
) -> RouterInput:
    """建立 Phase 5G structured request；欄位尚未存在時保留明確 RED 訊息。"""

    try:
        return RouterInput(
            user_task=task,
            capability_registry=records,
            requested_output_language=language,
            execution_allowed=True,
            explicit_requests=explicit_requests,
            action_requirements=action_requirements,
            execution_constraints=execution_constraints,
        )
    except TypeError as error:
        # TDD RED：RouterInput 尚未支援 Phase 5G structured fields 時，轉成可讀 assertion failure。
        raise AssertionError(f"Phase 5G RouterInput semantics are not supported yet: {error}") from error


class Phase5GIntentRoutingTests(unittest.TestCase):
    """驗證六個 bounded structured intent routing contracts。"""

    def test_explicit_requested_capability_is_preferred(self) -> None:
        """Name the break: a compatible explicit request must outrank another compatible candidate."""

        writer = _record(
            capability_id="generic-writing-capability",
            name="Generic Writing Capability",
            category="writing",
            triggers=("writing",),
            provides=("rewrite_text",),
            aliases=("writer-alias",),
            priority=1,
            overlap_group="writing-tools",
        )
        other = _record(
            capability_id="generic-other-capability",
            name="Generic Other Capability",
            category="writing",
            triggers=("writing",),
            provides=("rewrite_text",),
            priority=100,
            overlap_group="writing-tools",
        )

        result = route(
            _request(
                "Rewrite this text naturally.",
                (other, writer),
                explicit_requests=("writer-alias",),
                action_requirements=("rewrite_text",),
            )
        )

        self.assertEqual(tuple(record.id for record in result.selected_primary), ("generic-writing-capability",))
        evidence = next(item for item in result.selection_evidence if item.capability_id == "generic-writing-capability")
        self.assertIn("explicit_request", evidence.reason_codes)

    def test_explicit_request_does_not_bypass_unavailable_or_controller(self) -> None:
        """Name the break: explicit IDs must still pass availability and controller hard gates."""

        unavailable = _record(
            capability_id="unavailable-writer",
            status="unavailable",
            category="writing",
            provides=("rewrite_text",),
        )
        controller = _record(
            capability_id="codex-capability-router",
            name="Codex Capability Router",
            category="writing",
            provides=("rewrite_text",),
            controller=True,
        )

        result = route(
            _request(
                "Rewrite this text.",
                (unavailable, controller),
                explicit_requests=("unavailable-writer", "codex-capability-router"),
                action_requirements=("rewrite_text",),
            )
        )

        self.assertEqual(result.selected_primary, ())
        self.assertEqual(result.selected_optional, ())
        self.assertEqual(result.outcome, "no_safe_match")
        rejected = {item.id: item.reason for item in result.rejected_candidates}
        self.assertEqual(rejected["unavailable-writer"], "unavailable")
        self.assertEqual(rejected["codex-capability-router"], "self-routing protection")

    def test_rewrite_intent_does_not_select_firmware_from_topic_keywords(self) -> None:
        """Name the break: firmware vocabulary must not override a rewrite-only action requirement."""

        firmware = _record(
            capability_id="firmware-debugging",
            name="Firmware Debugging",
            category="firmware debugging",
            triggers=("Keil", "UART", "EEPROM", "firmware"),
            provides=("debug_firmware",),
        )

        result = route(
            _request(
                "Rewrite this Keil C51 UART EEPROM firmware progress naturally without AI tone.",
                (firmware,),
                action_requirements=("rewrite_text",),
            )
        )

        self.assertEqual(result.selected_primary, ())
        self.assertEqual(result.selected_optional, ())
        self.assertEqual(result.outcome, "native_model_sufficient")
        self.assertIn("firmware-debugging", tuple(item.id for item in result.rejected_candidates))

    def test_native_model_sufficient_allows_empty_selection(self) -> None:
        """Name the break: native-capable rewrite work must not be forced into a generic skill."""

        controller = _record(
            capability_id="codex-capability-router",
            name="Codex Capability Router",
            category="writing",
            controller=True,
        )
        result = route(
            _request(
                "Rewrite this firmware progress naturally.",
                (controller,),
                action_requirements=("rewrite_text",),
            )
        )

        self.assertEqual(result.selected_primary, ())
        self.assertEqual(result.selected_optional, ())
        self.assertEqual(result.outcome, "native_model_sufficient")
        self.assertEqual(result.router_controller_ids, ("codex-capability-router",))

        english = render_recommendations(
            result,
            language="en",
            user_request="Rewrite this firmware progress naturally.",
        )
        zh_tw = render_recommendations(
            result,
            language="zh-TW",
            user_request="請自然改寫這段韌體進度。",
        )
        self.assertIn("No downstream capability required. Native model is sufficient for this task.", english)
        self.assertIn("本次不需要額外下游能力，可直接使用基礎模型完成。", zh_tw)
        for output in (english, zh_tw):
            self.assertIn("## Router / Controller", output)
            self.assertIn("codex-capability-router", output)
            selected_heading = "## Selected Capabilities" if "## Selected Capabilities" in output else "## 已選能力"
            primary_heading = "## Primary" if "## Primary" in output else "## 主要建議"
            selected_section = output.split(selected_heading, 1)[1].split(primary_heading, 1)[0]
            self.assertNotIn("codex-capability-router", selected_section)

    def test_spreadsheet_edit_requires_spreadsheet_coverage_but_text_generation_does_not(self) -> None:
        """Name the break: Excel as context must not imply editing, while edit action must require coverage."""

        spreadsheet_editor = _record(
            capability_id="spreadsheet-editor",
            name="Spreadsheet Editor",
            category="spreadsheet editing",
            triggers=("Excel", "spreadsheet"),
            provides=("edit_spreadsheet",),
        )

        generate_text = route(
            _request(
                "Refer to the Excel format and generate text that I will paste into Excel myself.",
                (spreadsheet_editor,),
                action_requirements=("generate_text",),
            )
        )
        direct_edit = route(
            _request(
                "Directly modify the latest progress column in Excel.",
                (spreadsheet_editor,),
                action_requirements=("edit_spreadsheet",),
            )
        )

        self.assertNotIn("spreadsheet-editor", tuple(item.id for item in generate_text.selected_primary + generate_text.selected_optional))
        self.assertEqual(generate_text.outcome, "native_model_sufficient")
        self.assertEqual(tuple(item.id for item in direct_edit.selected_primary), ("spreadsheet-editor",))

    def test_image_composition_preserves_non_generative_execution_constraints(self) -> None:
        """Name the break: composition constraints must pass through and exclude generate-only capabilities."""

        composition = _record(
            capability_id="image-composition-editor",
            name="Image Composition Editor",
            kind="tool",
            category="image editing",
            triggers=("photo", "image"),
            provides=("compose_image", "edit_supplied_images"),
        )
        generate_only = _record(
            capability_id="image-generation-only",
            name="Image Generation Only",
            kind="tool",
            category="image generation",
            triggers=("photo", "image"),
            provides=("generate_image",),
            priority=100,
        )
        constraints = (
            "preserve_original",
            "no_generative_redraw",
            "no_invented_content",
            "no_screen_content_modification",
        )

        result = route(
            _request(
                "Compose three supplied photos into one; preserve the originals, do not redraw, invent content, or modify screen content.",
                (generate_only, composition),
                action_requirements=("compose_image",),
                execution_constraints=constraints,
            )
        )

        self.assertEqual(tuple(item.id for item in result.selected_primary), ("image-composition-editor",))
        self.assertNotIn("image-generation-only", tuple(item.id for item in result.selected_primary + result.selected_optional))
        self.assertEqual(result.execution_constraints, constraints)
        evidence = next(item for item in result.selection_evidence if item.capability_id == "image-composition-editor")
        self.assertEqual(evidence.constraint_preserved, constraints)


if __name__ == "__main__":
    unittest.main()
