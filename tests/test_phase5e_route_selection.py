"""Phase 5E route-only selection semantics 的四個 behavior tests。

修改紀錄（2026-08-18，Steve Peng）
原始內容：Router 尚未固定 controller、internal discovery support 與 execution
permission 不得改變 downstream selection 的行為。
修改原因：Real-world acceptance 暴露 route-only 將 controller/tool 誤當成
target capability，且可能因不執行 specialist 而錯誤改變 selection。
修改後功能：以 synthetic registry 固定四個最小 regression behaviors，不加入
canonical 12-scenario dataset，也不保存真實 workspace inventory。
"""

from __future__ import annotations

import unittest

from codex_capability_router.models import RouterInput
from codex_capability_router.routing import route
from codex_capability_router.validation import record_from_mapping


def _record(
    *,
    capability_id: str,
    name: str | None = None,
    status: str = "installed",
    category: str = "firmware debugging",
    triggers: tuple[str, ...] = ("firmware", "debug"),
    priority: int = 10,
    source: str = "fixture:phase5e",
    overlap_group: str | None = None,
    controller: bool = False,
    aliases: tuple[str, ...] = (),
    routing_support: bool = False,
):
    """建立最小 synthetic canonical record；不掃描真實專案或執行 capability。"""

    payload = {
        "id": capability_id,
        "name": name or capability_id,
        "kind": "skill",
        "status": status,
        "categories": [category],
        "triggers": list(triggers),
        "priority": priority,
        "overlap_group": overlap_group,
        "preferred_for": [category] if category != "generic" else [],
        "requires": [],
        "source": source,
        "last_verified": None,
    }
    if controller:
        payload["controller"] = True
    if aliases:
        payload["aliases"] = list(aliases)
    if routing_support:
        payload["routing_support"] = True
    try:
        return record_from_mapping(payload)
    except ValueError as error:
        # TDD RED：metadata 尚未進入 canonical validation 時，轉成可讀 assertion failure。
        raise AssertionError(f"Phase 5E record metadata is not supported yet: {error}") from error


def _request(task: str, records, *, execution_allowed: bool) -> RouterInput:
    """建立帶 execution permission 的 route request；selection 不應讀取該 permission。"""

    try:
        return RouterInput(
            user_task=task,
            capability_registry=records,
            requested_output_language="en",
            execution_allowed=execution_allowed,
        )
    except TypeError as error:
        # TDD RED：尚未有最小 permission metadata 時，保留預期的行為失敗而非 setup error。
        raise AssertionError(f"Phase 5E execution permission is not supported yet: {error}") from error


class Phase5ERouteSelectionTests(unittest.TestCase):
    """驗證 downstream selection 與 routing support/execution metadata 的邊界。"""

    def test_controller_is_never_selected(self) -> None:
        """Name the break: controller IDs/aliases must never enter selected output."""

        records = (
            _record(
                capability_id="codex-capability-router",
                name="Codex Capability Router",
                priority=1000,
                controller=True,
                aliases=("codex-router",),
            ),
            _record(
                capability_id="codex-router",
                name="Codex Router Alias",
                priority=999,
            ),
            _record(
                capability_id="workspace-firmware-triage",
                source="skill-root:workspace",
                triggers=("stm32g0", "firmware", "debug"),
            ),
        )

        result = route(_request("Debug the STM32G0 firmware problem.", records, execution_allowed=False))
        selected_ids = {record.id for record in result.selected_primary + result.selected_optional}

        self.assertNotIn("codex-capability-router", selected_ids)
        self.assertNotIn("codex-router", selected_ids)
        self.assertEqual(tuple(record.id for record in result.selected_primary), ("workspace-firmware-triage",))

    def test_internal_discovery_support_is_not_task_selection(self) -> None:
        """Name the break: exec_command used for discovery must not be a task capability."""

        records = (
            _record(
                capability_id="exec_command",
                name="Internal Discovery Support",
                priority=1000,
                routing_support=True,
            ),
            _record(
                capability_id="workspace-firmware-triage",
                source="skill-root:workspace",
                triggers=("firmware", "debug"),
            ),
        )

        result = route(_request("Debug the firmware build blocker.", records, execution_allowed=False))
        selected_ids = {record.id for record in result.selected_primary + result.selected_optional}

        self.assertNotIn("exec_command", selected_ids)
        self.assertEqual(tuple(record.id for record in result.selected_primary), ("workspace-firmware-triage",))

    def test_route_only_still_selects_target_specialist(self) -> None:
        """Name the break: route-only must select the target specialist before suppressing execution."""

        records = (
            # 修改紀錄（2026-08-18，Steve Peng）
            # 原始內容：workspace specialist 未傳入 overlap_group。
            # 修改原因：routing-policy 以同一 overlap_group 判定重複候選；fixture 必須表達它與 generic debugger 的競爭關係。
            # 修改後功能：generic candidate 在 specialist 已覆蓋目標需求時依既有 overlap policy 被排除。
            _record(
                capability_id="workspace-firmware-triage",
                source="skill-root:workspace",
                triggers=("stm32g0", "firmware", "debug"),
                overlap_group="firmware-debugging",
            ),
            _record(
                capability_id="generic-firmware-debugger",
                name="Generic Firmware Debugger",
                category="generic",
                triggers=("firmware", "debug"),
                priority=100,
                overlap_group="firmware-debugging",
            ),
        )

        result = route(
            _request(
                "STM32G0 firmware problem involving PWM, EXTI, OLED and build blocker.",
                records,
                execution_allowed=False,
            )
        )

        self.assertEqual(tuple(record.id for record in result.selected_primary), ("workspace-firmware-triage",))
        self.assertFalse(result.execution_allowed)

    def test_execution_permission_does_not_change_selection(self) -> None:
        """Name the break: execution permission must change metadata only, never ranking or IDs."""

        records = (
            _record(
                capability_id="workspace-firmware-triage",
                source="skill-root:workspace",
                triggers=("stm32g0", "firmware", "debug"),
            ),
            _record(
                capability_id="generic-firmware-debugger",
                name="Generic Firmware Debugger",
                category="generic",
                triggers=("firmware", "debug"),
                priority=100,
                overlap_group="firmware-debugging",
            ),
        )
        task = "Debug the STM32G0 firmware build blocker."

        route_only = route(_request(task, records, execution_allowed=False))
        execution_enabled = route(_request(task, records, execution_allowed=True))

        self.assertEqual(
            tuple(record.id for record in route_only.selected_primary + route_only.selected_optional),
            tuple(record.id for record in execution_enabled.selected_primary + execution_enabled.selected_optional),
        )
        self.assertFalse(route_only.execution_allowed)
        self.assertTrue(execution_enabled.execution_allowed)


if __name__ == "__main__":
    unittest.main()
