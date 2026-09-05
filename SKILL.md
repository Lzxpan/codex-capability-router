---
name: codex-capability-router
description: Use when starting a work task that benefits from trusted capability discovery and selection.
---

## Contract (beta.10)

- TaskAnalysis first; Skills explain; Providers run; Python validates.
- Discover trusted roots, Plugin paths, and HostCapabilitySnapshot; never top-k truncate or lose recalled capabilities.
- Stage every resolved PRESENT digest, including SPARSE/OPAQUE. Select any plausible task-relevant value; readiness is execution evidence.
- Semantic overlap is neutral. Exclude only clearly irrelevant, absent, unresolved, exact-duplicate, controller, routing-support, explicitly constrained, or unsafe-handoff records.
- Plugin is provenance; unknown hierarchy stays `host_tool`, never guessed App/MCP/native.
- Validate Host batch dispositions against task/snapshot fingerprints. Missing responses or needs_detail remain PARTIAL. FINALIZED is not coverage completion or execution proof.
- At most one bounded Skill Coverage Check and one bounded Supporting Coverage Check.
- Router never executes, installs, authorizes, network-discovers, persists inventory, or emits private data.

## References

- [Discovery](references/discovery-and-provenance.md)
- [Routing](references/routing-policy.md)
- [Bilingual output](references/i18n-policy.md)
