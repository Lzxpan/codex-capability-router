"""Phase 5R 核心 behavior tests，獨立於 12-scenario fixture。

修改紀錄（2026-08-17，Steve Peng）
原始內容：registry、probe 與 unknown routing 沒有 direct unit tests。
修改原因：以 TDD 固定 runtime authority、field-level conflict evidence、probe failure 與 advisory-only 邊界。
修改後功能：只覆蓋六個 Phase 5R 核心 behavior，不新增 benchmark scenario；beta review 修正仍沿用既有測試方法。
"""

from __future__ import annotations

from dataclasses import replace
import unittest

from codex_capability_router import discovery, registry
from codex_capability_router.models import CapabilityStatus
from codex_capability_router.selection import validate_selection
from codex_capability_router.validation import record_from_mapping


def _record(*, source: str, status: str, capability_id: str = "shared-capability"):
    """建立 hand-checked record，避免測試複製 merge 或 ranking 演算法。"""

    return record_from_mapping(
        {
            "id": capability_id,
            "name": capability_id,
            "kind": "tool",
            "status": status,
            "categories": ["diagnostics"],
            "triggers": ["diagnostics"],
            "priority": 10,
            "overlap_group": None,
            "preferred_for": ["diagnostics"],
            "requires": [],
            "source": source,
            "last_verified": None,
        }
    )


class Phase5RCoreTests(unittest.TestCase):
    """只驗證 authority、provenance、probe failure 與 unknown routing。"""

    def test_runtime_source_overrides_cli(self) -> None:
        """Name the break: CLI availability must not overwrite runtime authority."""

        merge = getattr(registry, "merge_capability_records", None)
        self.assertTrue(callable(merge))

        result = merge(
            (
                _record(source="cli:codex-plugin-list", status="unavailable"),
                _record(source="runtime:envelope", status="available"),
            )
        )

        self.assertEqual(result.records[0].status, CapabilityStatus.AVAILABLE)
        self.assertEqual(result.records[0].source, "runtime:envelope")

    def test_cli_source_overrides_manual_import(self) -> None:
        """Name the break: verified CLI evidence must outrank descriptive manual import."""

        merge = getattr(registry, "merge_capability_records", None)
        self.assertTrue(callable(merge))

        result = merge(
            (
                _record(source="manual:inventory", status="unavailable"),
                _record(source="cli:codex-plugin-list", status="available"),
            )
        )

        self.assertEqual(result.records[0].status, CapabilityStatus.AVAILABLE)
        self.assertEqual(result.records[0].source, "cli:codex-plugin-list")

    def test_conflicting_status_evidence_is_retained(self) -> None:
        """Name the break: merge must not silently discard the losing source claim."""

        merge = getattr(registry, "merge_capability_records", None)
        self.assertTrue(callable(merge))

        result = merge(
            (
                _record(source="runtime:envelope", status="available"),
                _record(source="cli:codex-plugin-list", status="unavailable"),
            )
        )

        self.assertTrue(result.records[0].conflicts)
        self.assertTrue(any(item.code == "source_conflict" for item in result.diagnostics))

        detailed = merge(
            (
                replace(
                    _record(source="runtime:envelope", status="available"),
                    last_verified="2026-08-17T00:00:00+00:00",
                    version="1.0",
                    limitations=("runtime limitation",),
                ),
                replace(
                    _record(source="cli:codex-plugin-list", status="available"),
                    last_verified="2026-08-18T00:00:00+00:00",
                    version="2.0",
                    limitations=("cli limitation",),
                ),
            )
        )
        self.assertTrue(any("last_verified" in item for item in detailed.records[0].conflicts))
        self.assertTrue(any("version" in item for item in detailed.records[0].conflicts))
        self.assertTrue(any("limitations" in item for item in detailed.records[0].conflicts))

    def test_failed_cli_probe_is_partial_unknown_and_non_crashing(self) -> None:
        """Name the break: a failed approved probe must become evidence, not an exception or guess."""

        probe = getattr(discovery, "probe_cli", None)
        self.assertTrue(callable(probe))

        def failing_runner(*args, **kwargs):
            class Failed:
                returncode = 7
                stdout = ""
                stderr = "probe failed"

            return Failed()

        result = probe(
            ["codex", "plugin", "list", "--json"],
            runner=failing_runner,
        )

        self.assertTrue(result.partial)
        self.assertTrue(result.records)
        self.assertTrue(all(record.status == CapabilityStatus.UNKNOWN for record in result.records))
        self.assertTrue(any(item.code == "probe_failed" for item in result.diagnostics))

    def test_unknown_capability_is_not_routed(self) -> None:
        """Name the break: unknown status must not become a normal recommendation."""

        payload = {
            "task_summary": "diagnostics",
            "selected_skills": [],
            "selection_status": "no_matching_skill",
        }

        self.assertEqual(validate_selection(payload), payload)

    def test_explicit_recommendation_only_unknown_is_not_executable(self) -> None:
        """Name the break: trusted recommendation-only unknown stays advisory-only."""

        payload = {
            "task_summary": "diagnostics",
            "selected_skills": [],
            "selection_status": "no_matching_skill",
        }

        self.assertEqual(validate_selection(payload), payload)
        self.assertEqual(payload["selected_skills"], [])


if __name__ == "__main__":
    unittest.main()
