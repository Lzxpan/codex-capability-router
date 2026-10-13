"""執行文件中的 Host API 範例；受控決策只驗證契約，不代表模型選用品質。"""

from contextlib import ExitStack
from pathlib import Path
import re
import tempfile
import unittest
from unittest.mock import patch

from codex_capability_router.route_context import DECISION_PAYLOAD_CONTRACT_VERSION
from tests.test_beta10_decision_coverage import _responses
from tests.test_beta7_fixed_skill_root_cache import _write_skill


POLICY = Path(__file__).resolve().parents[1] / "references" / "routing-policy.md"


class HostWorkflowExampleTests(unittest.TestCase):
    """2026-10-07 Steve Peng：直接執行四段範例，核對 snapshot、lazy Provider 與失敗分支。"""

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.home = self.root / "home"
        self.codex_home = self.root / "codex"
        self.ids = tuple(f"workflow-{index}" for index in range(7))
        for identity in self.ids:
            _write_skill(self.home / ".agents" / "skills" / identity, identity)
        self.blocks = dict(re.findall(
            r"<!-- host-workflow:(\w+) -->\s*```python\n(.*?)```",
            POLICY.read_text(encoding="utf-8").replace("\r\n", "\n"), re.S,
        ))
        self.assertEqual(set(self.blocks), {"prepare", "handoff", "supporting", "finalize"})
        self.analysis = {
            "task_summary": "Inspect firmware and record verification limits",
            "work_items": ["Inspect the UART contract"],
            "deliverables": ["Evidence report"],
            "constraints": ["read-only", "800G only", "no flashing"],
            "quality_expectations": ["Separate source build artifact and hardware evidence"],
        }
        self.namespace = {
            "task_analysis": self.analysis,
            "host_home": self.home, "host_codex_home": self.codex_home,
            "runtime_extra_roots": (), "plugin_manifests": (),
            "host_registry": (), "host_snapshot_id": "workflow-test",
            "host_session_scope": "current-test", "readiness_evidence": (),
            "supporting_batch_decisions": (),
        }

    def run_block(self, name):
        exec(compile(self.blocks[name], f"routing-policy:{name}", "exec"), self.namespace)

    def prepare_decisions(self, *, needs=()):
        self.run_block("prepare")
        context = self.namespace["skill_context"]
        self.assertEqual({p.id for p in context.candidates}, set(self.ids))
        self.namespace["host_preliminary_skill_ids"] = self.ids
        self.run_block("handoff")
        # 受控 fixture 的 Host 判斷；production 範例本身不得從 final IDs 反填批次。
        self.namespace["skill_batch_decisions"] = _responses(
            context.inventory_sweep, context.context_fingerprint, self.ids,
        )
        self.namespace["host_decision"] = {
            "contract_version": DECISION_PAYLOAD_CONTRACT_VERSION,
            "task_analysis": self.analysis,
            "skill_selection": {
                "task_summary": self.analysis["task_summary"],
                "selected_skills": [{"id": identity, "reason": "Host fixture judgment"} for identity in self.ids],
                "selection_status": "selected",
            },
            "execution_needs": list(needs),
        }
        self.namespace["host_final_decision"] = self.namespace["host_decision"]

    def test_path_strings_are_normalized_and_handoff_uses_public_fields(self):
        """2026-10-08 Steve Peng：Host 常見字串路徑與全文交接走文件中的實際 API。"""
        extra = self.root / "extra"
        _write_skill(extra / "workflow-extra", "workflow-extra")
        self.ids += ("workflow-extra",)
        self.namespace.update(host_home=str(self.home), host_codex_home=str(self.codex_home), runtime_extra_roots=(str(extra),))
        self.prepare_decisions()
        self.assertEqual(set(self.namespace["handoff_instructions"]), set(self.ids))
        for identity, instructions in self.namespace["handoff_instructions"].items():
            self.assertIn(identity, instructions)
        self.run_block("supporting")
        self.run_block("finalize")
        self.assertIn("workflow-extra", [item["id"] for item in self.namespace["receipt"]["selected_skills"]])

    def test_structured_example_reuses_snapshot_and_preserves_all_selected_skills(self):
        before = {p: p.read_bytes() for p in self.home.rglob("SKILL.md")}
        self.prepare_decisions()
        self.run_block("supporting")
        with ExitStack() as stack:
            for module in ("inventory", "route_context"):
                stack.enter_context(patch(
                    f"codex_capability_router.{module}.refresh_skill_inventory_snapshot",
                    side_effect=AssertionError("unexpected inventory refresh"),
                ))
            self.run_block("finalize")
        receipt = self.namespace["receipt"]
        self.assertTrue(receipt["router_invoked"])
        self.assertEqual(receipt["selection_state"], "FINALIZED")
        self.assertEqual([item["id"] for item in receipt["selected_skills"]], list(self.ids))
        self.assertEqual(receipt["task_analysis"]["constraints"], self.analysis["constraints"])
        self.assertEqual(receipt["skill_metrics"]["skill_semantic_coverage_status"], "COMPLETE")
        self.assertEqual(before, {p: p.read_bytes() for p in self.home.rglob("SKILL.md")})
        self.assertNotIn("preferences", self.blocks["prepare"] + self.blocks["finalize"])

    def test_empty_needs_skip_host_tool_snapshot_and_provider_preparation(self):
        self.prepare_decisions()
        with patch("codex_capability_router.host_snapshot.prepare_host_capability_snapshot", side_effect=AssertionError("unexpected snapshot")), patch("codex_capability_router.supporting_context.prepare_supporting_context", side_effect=AssertionError("unexpected Provider preparation")):
            self.run_block("supporting")
            self.run_block("finalize")
        self.assertIsNone(self.namespace["supporting_context"])
        self.assertEqual(self.namespace["receipt"]["supporting_selection_status"], "not_required")

    def test_plugin_skills_remain_selectable_when_provider_needs_are_empty(self):
        package = self.root / "plugin"
        identity = "workflow-plugin"
        _write_skill(package / "skills" / identity, identity)
        self.ids += (identity,)
        self.namespace["plugin_manifests"] = ({
            "plugin_id": "workflow@test", "present": True,
            "package_root": str(package), "skills": "./skills",
        },)
        self.prepare_decisions()
        self.run_block("supporting")
        self.run_block("finalize")
        receipt = self.namespace["receipt"]
        self.assertIn(identity, [item["id"] for item in receipt["selected_skills"]])
        self.assertEqual(receipt["supporting_selection_status"], "not_required")
        self.assertEqual(receipt["skill_metrics"]["skill_semantic_coverage_status"], "COMPLETE")

    def test_provider_judgment_occurs_after_preparation_and_final_counts_match(self):
        self.prepare_decisions(needs=({"need": "Inspect source", "reason": "Read current source"},))
        self.namespace["host_registry"] = ({
            "namespace": "fixture", "action_name": "inspect", "display_name": "Inspect",
            "description": "Read-only fixture tool", "hierarchy": "host_native",
        },)
        self.run_block("supporting")
        context = self.namespace["supporting_context"]
        identity = context.inventory_sweep.staged_ids[0]
        self.namespace["supporting_batch_decisions"] = _responses(
            context.inventory_sweep, self.namespace["skill_context"].context_fingerprint, (identity,),
        )
        self.namespace["host_final_decision"] = {
            **self.namespace["host_decision"],
            "final_supporting_decision": {
                "selected_supporting_capabilities": [{"kind": "builtin_tool", "canonical_provider_id": identity, "purpose": "Inspect source"}],
                "unmet_execution_needs": [],
            },
        }
        self.run_block("finalize")
        metrics = self.namespace["receipt"]["supporting_metrics"]
        self.assertEqual(metrics["selected_count"], 1)
        self.assertEqual(metrics["provider_selected_total"], 1)
        self.assertEqual(metrics["provider_semantic_coverage_status"], "COMPLETE")

    def test_missing_or_stale_host_decisions_cannot_create_complete_coverage(self):
        self.prepare_decisions()
        self.run_block("supporting")
        self.namespace["skill_batch_decisions"] = ()
        with self.assertRaisesRegex(ValueError, "selected candidates require batch evidence"):
            self.run_block("finalize")
        self.assertNotIn("receipt", self.namespace)
        context = self.namespace["skill_context"]
        self.namespace["skill_batch_decisions"] = _responses(context.inventory_sweep, "0" * 64, self.ids)
        with self.assertRaises(ValueError):
            self.run_block("finalize")


if __name__ == "__main__":
    unittest.main()
