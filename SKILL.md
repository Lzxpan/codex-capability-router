---
name: codex-capability-router
description: Use when bounded capability discovery, validation, routing, or evaluation.
---

## Contract

- TaskAnalysis first.
- Skills are methods; Supporting Providers execute. Python validates only.
- Select materially useful, non-redundant recalled Skills; no fixed count.
- One Coverage Check may add candidates with ID, availability, handoff, applicability,
  `supports`, and `distinct_value`.
- `supports` cites TaskAnalysis items. trusted-root discovery plus handoff establish
  availability; unknown profiles are diagnostics only.
- `prepare_route_context()` is deterministic Skill-only context; Supporting discovery is lazy
  with `execution_needs`.
- Formal Supporting kinds are App, MCP, and builtin Tool. Trusted present Providers with
  sufficient metadata may be `VERIFIED_READY` or `PRESENT_UNVERIFIED`; explicit
  negatives, insufficient metadata, and uncertified instances stay excluded. Plugin is only
  package/provenance, never formal selection.
- `route(SelectionRouteInput(...))` creates `FINALIZED` Receipts; preserve provenance and reject
  untrusted records.
- Preserve 12 fixtures (6 zh-TW, 6 en); never execute/install/authorize, network-discover,
  persist inventory, or emit private data.

<!-- 2026-08-31 Steve Peng：coverage-first。 -->
<!-- 2026-09-01 Steve Peng：optimistic Supporting Provider selection。 -->

## References

- [Discovery, provenance, and registry fields](references/discovery-and-provenance.md)
- [Routing policy and unknown handling](references/routing-policy.md)
- [Bilingual output and i18n policy](references/i18n-policy.md)
