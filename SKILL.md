---
name: codex-capability-router
description: Use when routing capability.
---

## Contract

- TaskAnalysis first; Skills explain; Providers run; Python validates.
- Discover trusted roots, Plugin Skill paths, and HostCapabilitySnapshot; never top-k truncate or lose recalled capabilities.
- Existence plus resolved identity means `PRESENT`/selectable. Metadata quality is diagnostic; readiness is execution evidence.
- Sweep every resolved digest, including `SUFFICIENT`, `SPARSE`, and `OPAQUE`; select any candidate with plausible task-relevant value.
- Semantic overlap is neutral: select each relevant Skill. Exclude only clearly irrelevant, absent, unresolved, exact-duplicate, controller, routing-support, explicitly constrained, or unsafe-handoff records.
- Negative readiness remains selectable. Plugin is provenance; kinds are App, MCP, builtin Tool, and `host_tool`.
- unknown hierarchy becomes visible `host_tool` with `hierarchy_state=UNKNOWN`, never a guessed App/MCP/native kind.
- Unknown existence stays diagnostic. Handoff is a later safety boundary.
- At most one bounded Skill Coverage Check and one bounded Supporting Coverage Check. `route(SelectionRouteInput(...))` creates `FINALIZED` receipts. Never execute, install, authorize, network-discover, persist inventory, or emit private data.

## References

- [Discovery, provenance, and registry fields](references/discovery-and-provenance.md)
- [Routing policy and unknown handling](references/routing-policy.md)
- [Bilingual output and i18n policy](references/i18n-policy.md)
