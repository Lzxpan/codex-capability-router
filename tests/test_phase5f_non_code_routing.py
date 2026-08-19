"""Phase 5F non-code artifact routing 的四個 behavior tests。

修改紀錄（2026-08-19，Steve Peng）
原始內容：discovery 可保留非程式 capability，但 routing 只消費 categories、triggers
與 preferred_for，無法可靠使用 description/provides 表達 artifact task requirement。
修改原因：real-world 文件、圖片與 PDF 任務需要 generic task-capability metadata，且
capability role 必須依本次用途判定，不能依 system/built-in/plugin source 猜測。
修改後功能：固定非程式 task selection、source-neutral task capability、role-based
routing_support 與 route-only selection 的四個最小 regression behaviors。
"""

from __future__ import annotations

import unittest

from codex_capability_router.models import RouterInput
from codex_capability_router.routing import route
from codex_capability_router.validation import record_from_mapping


_TASK = (
    "Create a one-page product instruction PDF from three product photos, "
    "optimize and annotate the photos, preserve the originals, then verify the PDF."
)


def _record(
    *,
    capability_id: str,
    name: str,
    source: str,
    status: str = "installed",
    description: str,
    provides: tuple[str, ...],
    routing_support: bool = False,
):
    """建立只有 generic artifact metadata 的 synthetic capability record。"""

    payload = {
        "id": capability_id,
        "name": name,
        "kind": "skill",
        "status": status,
        "categories": [],
        "triggers": [],
        "priority": 10,
        "overlap_group": None,
        "preferred_for": [],
        "requires": [],
        "source": source,
        "last_verified": None,
        "description": description,
        "provides": list(provides),
    }
    if routing_support:
        payload["routing_support"] = True
    try:
        return record_from_mapping(payload)
    except (TypeError, ValueError) as error:
        # TDD RED：metadata 尚未被 canonical normalization/routing 支援時，保留可讀失敗。
        raise AssertionError(f"Phase 5F generic artifact metadata is unsupported: {error}") from error


def _artifact_records():
    """建立不依賴特定正式 capability ID 的文件、圖片與 PDF synthetic records。"""

    return (
        _record(
            capability_id="document-cap",
            name="One-page Product Instructions",
            source="system:documents",
            description="Creates one-page product instructions and PDF artifacts.",
            provides=("one-page product instruction", "PDF"),
        ),
        _record(
            capability_id="image-cap",
            name="Photo Optimization and Annotation",
            source="built-in:image",
            description="Optimizes product photos, adds arrows and text annotations, and preserves originals.",
            provides=("product photos", "annotate the photos", "original preservation"),
        ),
        _record(
            capability_id="pdf-cap",
            name="PDF Artifact Verification",
            source="plugin:pdf",
            status="available",
            description="Verifies generated PDF artifacts.",
            provides=("verify the PDF",),
        ),
    )


def _request(records, *, execution_allowed: bool) -> RouterInput:
    """建立 route-only 或 execution-enabled request；兩者 selection 必須相同。"""

    return RouterInput(
        user_task=_TASK,
        capability_registry=records,
        requested_output_language="en",
        execution_allowed=execution_allowed,
    )


class Phase5FNonCodeRoutingTests(unittest.TestCase):
    """驗證非程式 artifact capability 的 generic selection semantics。"""

    def test_non_code_artifact_task_selects_required_capabilities(self) -> None:
        """Name the break: document/image/PDF requirements must all have selected coverage."""

        result = route(_request(_artifact_records(), execution_allowed=False))

        self.assertEqual(
            tuple(record.id for record in result.selected_primary),
            ("document-cap", "image-cap"),
        )
        self.assertEqual(
            tuple(record.id for record in result.selected_optional),
            ("pdf-cap",),
        )

    def test_system_capability_can_be_task_capability(self) -> None:
        """Name the break: system source alone must not exclude a task capability."""

        record = _record(
            capability_id="system-document-cap",
            name="System Document Creator",
            source="system:documents",
            description="Creates one-page product instructions.",
            provides=("one-page product instruction",),
        )

        result = route(_request((record,), execution_allowed=False))

        self.assertEqual(tuple(item.id for item in result.selected_primary), ("system-document-cap",))

    def test_routing_support_is_role_based_not_source_based(self) -> None:
        """Name the break: same built-in source must allow task role and exclude support role."""

        task_capability = _record(
            capability_id="built-in-image-task",
            name="Built-in Image Editor",
            source="built-in:image",
            description="Optimizes product photos and adds text annotations.",
            provides=("product photos", "annotate the photos"),
        )
        discovery_support = _record(
            capability_id="built-in-image-inspection",
            name="Built-in Image Metadata Inspection",
            source="built-in:image",
            description="Inspects capability metadata during Router discovery.",
            provides=("product photos", "annotate the photos"),
            routing_support=True,
        )

        result = route(_request((discovery_support, task_capability), execution_allowed=False))
        selected_ids = tuple(item.id for item in result.selected_primary + result.selected_optional)

        self.assertEqual(selected_ids, ("built-in-image-task",))

    def test_route_only_non_code_keeps_target_selection(self) -> None:
        """Name the break: execution_allowed=false must not alter non-code selected IDs or order."""

        route_only = route(_request(_artifact_records(), execution_allowed=False))
        execution_enabled = route(_request(_artifact_records(), execution_allowed=True))

        self.assertEqual(
            tuple(item.id for item in route_only.selected_primary + route_only.selected_optional),
            tuple(item.id for item in execution_enabled.selected_primary + execution_enabled.selected_optional),
        )
        self.assertFalse(route_only.execution_allowed)
        self.assertTrue(execution_enabled.execution_allowed)


if __name__ == "__main__":
    unittest.main()
