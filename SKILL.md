---
name: codex-capability-router
description: Use when bounded, read-only capability discovery, validation, routing, or evaluation.
---

## Contract

- TaskAnalysis first: summary, work items, deliverables, constraints, quality.
- Skills describe methods; Supporting Providers describe callable execution. Python
  validates schema/readiness, never semantic selection.
- `prepare_route_context()` is deterministic Skill-only context; Supporting
  discovery is lazy and runs only for non-empty `execution_needs`.
- Beta scope: MCP `node_repl` and builtin `functions.exec_command`.
  App, Plugin, and uncertified providers remain excluded.
- `route(SelectionRouteInput(...))` creates the Receipt and `FINALIZED` result;
  finalized decisions are immutable and new work uses a new route.
- Preserve provenance, reject unknown/unavailable records; keep 12 fixtures:
  6 `zh-TW`, 6 `en`.
- Never execute, install, authorize, network-discover, or persist private inventory.
- Never emit prompts, private reasoning, full instructions/schemas, credentials,
  or private data.

## References

- [Discovery, provenance, and registry fields](references/discovery-and-provenance.md)
- [Routing policy and unknown handling](references/routing-policy.md)
- [Bilingual output and i18n policy](references/i18n-policy.md)

## Local verification

`python -m unittest discover -s tests -v`

<!-- 2026-08-17 Steve Peng：保留 read-only、安全與 12-case 契約。 -->
<!-- 2026-08-25 Steve Peng：正式結果必須來自 production route。 -->
<!-- 2026-08-26 Steve Peng：補充 v0.2 TaskAnalysis、lazy Supporting scope。 -->
