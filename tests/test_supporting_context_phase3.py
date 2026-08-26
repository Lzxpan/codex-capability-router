"""Phase 3 lazy Supporting context、readiness evidence 與 digest tests。"""

from __future__ import annotations

from dataclasses import replace
import inspect
import json
import unittest

from codex_capability_router.supporting_context import (
    ExecutionNeed,
    ReadinessEvidenceCertificate,
    SupportingProviderDeclaration,
    SupportingToolDeclaration,
    prepare_supporting_context,
)


def _tool(
    tool_id: str,
    *,
    schema: dict[str, object] | None = None,
    description: str = "Read-only callable tool declaration.",
) -> SupportingToolDeclaration:
    """建立 bounded Host tool declaration fixture。"""

    return SupportingToolDeclaration.from_mapping(
        {
            "id": tool_id,
            "description": description,
            "schema": schema or {"type": "object", "properties": {}, "required": []},
            "required_inputs": [],
            "output_description": "Public bounded result.",
            "side_effect": "none",
            "provenance": ["host-registry:phase0-sample"],
        }
    )


def _provider(
    provider_id: str = "node_repl",
    *,
    kind: str = "mcp",
    host_identity: str = "mcp__node_repl__js",
    host_grouping: tuple[str, ...] = ("mcp__node_repl",),
    tool_id: str = "js",
    description: str = "Read-only node_repl callable surface.",
    callable_exposure: bool = True,
    provenance: tuple[str, ...] = ("host-registry:phase0-sample",),
) -> SupportingProviderDeclaration:
    """建立不含 semantic ranking 的 Host provider declaration fixture。"""

    return SupportingProviderDeclaration(
        provider_id=provider_id,
        kind=kind,
        host_identity=host_identity,
        host_grouping=host_grouping,
        description=description,
        callable_tools=(_tool(tool_id),),
        callable_exposure=callable_exposure,
        provenance=provenance,
    )


def _need() -> ExecutionNeed:
    """建立 bounded execution need fixture。"""

    return ExecutionNeed("read-only runtime inspection", "需要目前 Host 的既有 callable surface。")


def _certificate(declaration: SupportingProviderDeclaration) -> ReadinessEvidenceCertificate:
    """以 Phase 0 已驗證 fixture 建立 evidence input；production 不自行 certification。"""

    return ReadinessEvidenceCertificate(
        provider_id=declaration.provider_id,
        kind=declaration.kind,
        host_identity=declaration.host_identity,
        host_grouping=declaration.host_grouping,
        callable_tool_ids=tuple(tool.id for tool in declaration.callable_tools),
        expected_schema_fingerprint=declaration.schema_fingerprint,
        expected_declaration_fingerprint=declaration.fingerprint,
        provenance=declaration.provenance,
    )


class Phase3SupportingContextTests(unittest.TestCase):
    """驗證 Phase 3 只做 lazy deterministic preparation。"""

    def test_empty_execution_needs_skip_provider_path_completely(self) -> None:
        """execution_needs=[] 不讀取 Provider declarations 或 evidence。"""

        class ExplodingSequence:
            def __iter__(self):
                raise AssertionError("provider path must not iterate when needs are empty")

        context = prepare_supporting_context(
            [],
            provider_declarations=ExplodingSequence(),  # type: ignore[arg-type]
            readiness_evidence=ExplodingSequence(),  # type: ignore[arg-type]
        )
        self.assertEqual(context.run_state, "not_run")
        self.assertEqual(context.metrics.to_mapping(), {
            "run_state": "not_run",
            "discovered_count": 0,
            "hard_eligible_count": 0,
            "selected_count": 0,
            "digest_total_size": 0,
            "detail_expansion_used": False,
        })
        self.assertEqual(context.provider_digests, ())
        self.assertEqual(context.detail_references, ())

    def test_non_empty_execution_needs_runs_read_only_preparation(self) -> None:
        """execution_needs 非空才 discovery/normalization/digest。"""

        declaration = _provider()
        context = prepare_supporting_context(
            [_need()],
            provider_declarations=(declaration,),
            readiness_evidence=(_certificate(declaration),),
        )
        self.assertEqual(context.run_state, "ran")
        self.assertEqual(context.metrics.discovered_count, 1)
        self.assertEqual(context.metrics.hard_eligible_count, 1)
        self.assertEqual(context.metrics.selected_count, 0)
        self.assertEqual([item.provider_id for item in context.provider_digests], ["node_repl"])

    def test_node_repl_exact_verified_evidence_is_hard_eligible(self) -> None:
        """node_repl exact identity、schema、exposure、fingerprint、provenance 均符合時才 eligible。"""

        declaration = _provider()
        evidence = _certificate(declaration)
        context = prepare_supporting_context(
            [_need()], provider_declarations=(declaration,), readiness_evidence=(evidence,)
        )
        self.assertEqual(context.metrics.hard_eligible_count, 1)
        self.assertEqual(context.readiness_evidence, (evidence,))

    def test_node_repl_evidence_mismatch_is_unknown_and_excluded(self) -> None:
        """node_repl 任一 readiness evidence mismatch 都不得進 digest。"""

        original = _provider()
        certificate = _certificate(original)
        cases = (
            replace(original, host_grouping=("mcp__wrong",)),
            replace(original, callable_tools=(_tool("js", schema={"type": "string"}),)),
            replace(original, callable_exposure=False),
            replace(certificate, expected_declaration_fingerprint="0" * 64),
            replace(original, provenance=("host-registry:other-sample",)),
        )
        for case in cases:
            with self.subTest(case=case):
                evidence = case if isinstance(case, ReadinessEvidenceCertificate) else certificate
                declaration = original if isinstance(case, ReadinessEvidenceCertificate) else case
                context = prepare_supporting_context(
                    [_need()], provider_declarations=(declaration,), readiness_evidence=(evidence,)
                )
                self.assertEqual(context.metrics.hard_eligible_count, 0)
                self.assertEqual(context.provider_digests, ())

    def test_functions_exec_command_exact_verified_evidence_is_hard_eligible(self) -> None:
        """builtin Tool 只接受 exact functions.exec_command evidence。"""

        declaration = _provider(
            provider_id="functions.exec_command",
            kind="builtin_tool",
            host_identity="functions.exec_command",
            host_grouping=("functions",),
            tool_id="functions.exec_command",
            description="Read-only builtin command declaration.",
        )
        evidence = _certificate(declaration)
        self.assertEqual(evidence.authorization, "not_required")
        self.assertEqual(evidence.connection, "not_required")
        context = prepare_supporting_context(
            [_need()], provider_declarations=(declaration,), readiness_evidence=(evidence,)
        )
        self.assertEqual(context.metrics.hard_eligible_count, 1)
        self.assertEqual(context.provider_digests[0].provider_id, "functions.exec_command")

    def test_functions_exec_command_mismatch_is_excluded(self) -> None:
        """builtin exact identity、schema、exposure、fingerprint 不符時排除。"""

        original = _provider(
            provider_id="functions.exec_command",
            kind="builtin_tool",
            host_identity="functions.exec_command",
            host_grouping=("functions",),
            tool_id="functions.exec_command",
        )
        certificate = _certificate(original)
        cases = (
            replace(original, host_identity="functions.other_command"),
            replace(original, callable_tools=(_tool("functions.exec_command", schema={"type": "array"}),)),
            replace(original, callable_exposure=False),
            replace(certificate, expected_schema_fingerprint="1" * 64),
        )
        for case in cases:
            with self.subTest(declaration=case):
                declaration = original if isinstance(case, ReadinessEvidenceCertificate) else case
                evidence = case if isinstance(case, ReadinessEvidenceCertificate) else certificate
                context = prepare_supporting_context(
                    [_need()], provider_declarations=(declaration,), readiness_evidence=(evidence,)
                )
                self.assertEqual(context.metrics.hard_eligible_count, 0)

    def test_other_mcp_builtin_app_and_plugin_are_not_auto_accepted(self) -> None:
        """kind 相同或其他 kind 不會繞過 exact certification。"""

        declarations = (
            _provider(provider_id="other_mcp", host_identity="mcp__other__js", host_grouping=("mcp__other",)),
            _provider(
                provider_id="other_builtin",
                kind="builtin_tool",
                host_identity="functions.other",
                host_grouping=("functions",),
                tool_id="functions.other",
            ),
            _provider(
                provider_id="app-sample",
                kind="app",
                host_identity="mcp__codex_apps__sample",
                host_grouping=("mcp__codex_apps",),
                tool_id="sample.read",
            ),
            _provider(
                provider_id="plugin-sample",
                kind="plugin",
                host_identity="plugin-sample",
                host_grouping=("plugin",),
                tool_id="plugin.read",
            ),
        )
        context = prepare_supporting_context([_need()], provider_declarations=declarations)
        self.assertEqual(context.metrics.discovered_count, 4)
        self.assertEqual(context.metrics.hard_eligible_count, 0)
        self.assertEqual(context.provider_digests, ())

    def test_digest_is_deterministic_and_metadata_change_changes_fingerprint(self) -> None:
        """相同 Host metadata digest 相同；description/schema 改變會變更 digest。"""

        declaration = _provider()
        evidence = _certificate(declaration)
        first = prepare_supporting_context(
            [_need()], provider_declarations=(declaration,), readiness_evidence=(evidence,)
        )
        second = prepare_supporting_context(
            [_need()], provider_declarations=(declaration,), readiness_evidence=(evidence,)
        )
        self.assertEqual(first.context_fingerprint, second.context_fingerprint)
        self.assertEqual(first.provider_digests[0].fingerprint, second.provider_digests[0].fingerprint)

        changed = replace(declaration, description="Changed public declaration.")
        changed_evidence = _certificate(changed)
        changed_context = prepare_supporting_context(
            [_need()], provider_declarations=(changed,), readiness_evidence=(changed_evidence,)
        )
        self.assertNotEqual(first.provider_digests[0].fingerprint, changed_context.provider_digests[0].fingerprint)

    def test_digest_contains_no_semantic_fields_or_private_content(self) -> None:
        """digest 只含 Host declaration，不含 taxonomy、ranking 或 private content。"""

        declaration = _provider()
        evidence = _certificate(declaration)
        context = prepare_supporting_context(
            [_need()], provider_declarations=(declaration,), readiness_evidence=(evidence,)
        )
        rendered = json.dumps(context.to_mapping(), ensure_ascii=False, sort_keys=True)
        for field in ("category", "provides", "best_for", "priority", "score", "keyword"):
            self.assertNotIn(field, rendered)
        self.assertNotIn("C:\\private", rendered)
        self.assertNotIn("password", rendered.casefold())

    def test_privacy_boundary_rejects_sensitive_or_private_schema(self) -> None:
        """credentials 與 private path 不得進 Provider declaration。"""

        with self.assertRaises(ValueError):
            _tool("js", schema={"properties": {"password": {"type": "string"}}})
        with self.assertRaises(ValueError):
            _tool("js", schema={"description": "C:\\private\\schema.json"})

    def test_preparation_source_has_no_endpoint_invocation(self) -> None:
        """production preparation source 不含 endpoint invocation/active probe。"""

        source = inspect.getsource(prepare_supporting_context)
        for marker in ("exec_command", "mcp__", "subprocess", "requests", "invoke("):
            self.assertNotIn(marker, source)

    def test_metrics_keep_selected_count_zero_and_detail_reference_bounded(self) -> None:
        """Phase 3 只建立 detail references，不執行 expansion 或 selection。"""

        declaration = _provider()
        context = prepare_supporting_context(
            [_need()],
            provider_declarations=(declaration,),
            readiness_evidence=(_certificate(declaration),),
        )
        self.assertEqual(context.metrics.selected_count, 0)
        self.assertFalse(context.metrics.detail_expansion_used)
        self.assertEqual(context.detail_references[0].provider_id, "node_repl")


if __name__ == "__main__":
    unittest.main()
