---
name: codex-capability-router
description: Use when starting a work task that benefits from trusted capability discovery and selection.
---

## Contract (1.1.3)

- TaskAnalysis first. Follow [Host API workflow](references/routing-policy.md#host-api-workflow) using installed library and snapshots.
- Only `route()` creates formal routing evidence. Use `render_recommendations`; guidance is not routing.
- Discover trusted roots, Plugin paths and HostCapabilitySnapshot; never top-k truncate or lose recalled capabilities; unknown hierarchy stays `host_tool`.
- Stage every resolved PRESENT digest, including SPARSE/OPAQUE. Select plausible task-relevant value; readiness is execution evidence.
- Semantic overlap is neutral. Exclude only clearly irrelevant, absent, unresolved, exact-duplicate, controller, routing-support, explicitly constrained or unsafe-handoff records.
- Final Skill/Provider selections require matching batch selected evidence. Missing unselected decisions or needs_detail remain PARTIAL. FINALIZED proves neither coverage nor execution. At most one bounded Skill Coverage Check and one bounded Supporting Coverage Check.
- Read full handoffs; apply documented APIs. Try authorized minimal probes; report exact errors and limits. Distinguish Read, Applied, Called and Verified.
- Router never executes, installs, authorizes, network-discovers, persists inventory or emits private data.

## References

- [Discovery](references/discovery-and-provenance.md)
- [Routing](references/routing-policy.md)
- [Bilingual output](references/i18n-policy.md)
