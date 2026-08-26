# Changelog

All notable changes to `codex-capability-router` are documented here.

## v0.2.0-beta.1

Pre-release for the LLM TaskAnalysis and Supporting Capability Selection
architecture. This release keeps the beta.4 route, Receipt, lifecycle, and
Skill semantics while adding a bounded lazy Supporting Provider path.

### Added

- Immutable strict LLM TaskAnalysis with `task_summary`, `work_items`,
  `deliverables`, `constraints`, and `quality_expectations`.
- Skill-only `prepare_route_context()` with deterministic fingerprints and
  validated `validated_decision_payloads`.
- Execution Needs and true-lazy `prepare_supporting_context()`.
- Provider-level Supporting decision contracts with
  `ReadinessEvidenceCertificate`, deterministic Provider digests, and one
  bounded `request_detail` / `final_selection` protocol.
- v0.2 Receipt fields for TaskAnalysis, Execution Needs, Supporting status,
  Provider readiness, fingerprints, metrics, and bounded detail references.
- Formal Supporting scope for the certified instances MCP `node_repl` and
  builtin-equivalent `functions.exec_command`.

### Changed

- The v0.2 production path requires TaskAnalysis; legacy `task_summary` is a
  compatibility projection and must match it.
- `route()` finalizes Skill and Supporting decisions together; it remains the
  only formal Receipt and `FINALIZED` entry point.
- Supporting Provider discovery is skipped entirely when
  `execution_needs=[]`.
- The existing 12 Skill routing scenarios remain exactly 6 `zh-TW` and 6
  `en`, migrated to the mandatory TaskAnalysis input contract.

### Fixed

- Bounded legacy frontmatter normalization for `explain-code`.
- Compatibility parsing for scalar/block metadata, simple `allowed-tools`
  lists, limited scalar metadata, and one safe scalar-leaf level under
  `metadata.source_frontmatter`.
- Malformed, sensitive, unavailable, controller, routing-support, and unsafe
  records remain rejected.

### Verified

- Phase 1 focused: **30/30 PASS**; Phase 1 full: **102/102 PASS**.
- Phase 2 focused: **43/43 PASS**; Phase 2 full: **111/111 PASS**.
- Phase 3 focused: **36/36 PASS**; Phase 3 full: **123/123 PASS**.
- Phase 4 focused: **14/14 PASS**; Phase 4 full: **137/137 PASS**.
- Phase 5 deterministic full: **137/137 PASS**.
- Phase 5 focused Phase 1–4: **45/45 PASS**.
- Codex Live Acceptance A–E: **PASS**.
- Positive Provider selection: `mcp:node_repl` and
  `builtin_tool:functions.exec_command`.
- Lazy `not_required` path: **PASS**; no-match path: **PASS**;
  Receipt/privacy: **PASS**.

### Known limitations

- The current Host did not expose a Router-trusted Skill availability
  declaration during v0.2 Live Acceptance.
- Formal Supporting Provider scope is limited to certified instances.
- App remains `INSUFFICIENT_RUNTIME_EVIDENCE`.
- Plugin remains `NO_RUNTIME_SAMPLE`.
- Other MCP and builtin providers are not automatically trusted.
- Supporting detail expansion was covered deterministically but was not
  naturally triggered in the five Live Acceptance cases.
- Live destructive stale mutation was intentionally not performed.

This is a pre-release preparation only. No tag, GitHub Release, push, or
release commit is created by this change.

## v0.1.0-beta.4

Integration hardening release. This release does not replace the beta.3
semantic selection design.

### Hardened

- Enforced formal Selection Results through
  `routing.route(SelectionRouteInput(...))`; outer orchestration cannot create
  a production Receipt.
- Added an automatic, bounded, auditable Selection Receipt for candidate,
  preliminary, full-handoff, final-selection, status, retrieval, correction,
  and finalization evidence. It stores no private chain-of-thought or sensitive
  data.
- Enforced canonical Skill IDs for machine paths; display names remain for
  human presentation only.
- Added an immutable `OPEN` -> `FINALIZED` selection lifecycle. Finalized
  selections reject correction, Expanded Retrieval, and selected-Skill
  mutation; new work starts a new routing request.
- Kept the beta.3 semantic Skill selection core unchanged.

### Validation

- Full automated tests: **91/91 PASS**.
- Integration Live Acceptance: **4/4 PASS**.
- Compileall, UTF-8/U+FFFD, diff, and production-source checks: PASS.

### Known observation

Existing runtime inventory may report malformed Skill metadata diagnostics.
This observation predates beta.4 and was not introduced or changed by this
release.

## v0.1.0-beta.3

Third public beta release, focused on semantic Codex-driven Skill selection and
the Phase 0-5 selection contract.

### Added and validated

- Codex's main model now makes final Skill Selection from task meaning after
  candidate preparation and full `SKILL.md` applicability validation.
- Added runtime Skill inventory refresh, cache fingerprints, Basic/Enriched
  Profiles, recall-first Candidate Retrieval, and explicit Skill inclusion.
- Added bounded full-instruction handoff, at most one Expanded Retrieval, at
  most one Correction, and `selected` / `no_matching_skill` output validation.
- Removed keyword/category/provides final-selection semantics, PRIMARY/OPTIONAL
  output, the 3+2 production limit, legacy fallback, and silent fallback.
- New or updated Skills no longer require a Router production mapping.
- The full regression suite passes **81/81** tests and Phase 5 Full Live
  Acceptance passes all five cases. Compileall, UTF-8/U+FFFD, diff, and
  production-source checks also pass.

### Known limitation

Runtime discovery reports 139 malformed Skill diagnostics. This is a
non-blocking observation and is not changed in beta.3. Measured runtime token
usage also remains unavailable; the existing `estimated-static` Plugin Eval
value is not measured runtime consumption and remains a stable-release
requirement.

## v0.1.0-beta.2

Second public beta release, focused on route-only selection semantics and
real-world validation after beta.1.

### Fixed and validated

- Fixed route-only capability selection semantics.
- Router controller cannot be selected downstream.
- Internal discovery and routing-support capabilities are excluded from task selections.
- Route-only mode selects target-task capabilities without executing them.
- Workspace-specific specialist preference was validated.
- Real-world STM32G0 local acceptance was completed successfully.
- The deterministic suite now passes **46/46** tests; the canonical routing fixture remains 12 scenarios: 6 `zh-TW` and 6 `en`.

### Known limitation

Measured runtime token usage remains unavailable. Plugin Eval's deferred value is
an `estimated-static` diagnostic: 43,789 deferred tokens and 44,200 total
estimated tokens, not measured runtime consumption. Empirical runtime measurement
or credible bounded runtime evidence remains required before stable `v0.1.0`.

## v0.1.0-beta.1

Initial public beta release.

### Included

- Local capability discovery through the runtime envelope, bounded CLI probes,
  explicit skill roots, and manual imports.
- Canonical runtime-scoped registry with deterministic normalization,
  capability deduplication, provenance, and conflict handling.
- Runtime/CLI/manual precedence with runtime authority preserved.
- Unknown-safe routing, including safe CLI probe failure handling and explicit
  protection against routing `UNKNOWN` capabilities as normally available.
- Deterministic advisory routing with English (`en`) and Traditional Chinese
  (`zh-TW`) catalogs.
- Human-readable selected capability explanations with localized Function
  metadata, PRIMARY/OPTIONAL levels, deterministic reason codes, and separate
  recommendation-only output.
- Bounded validation with exactly 12 routing scenarios: 6 `zh-TW` and 6 `en`.
- Privacy and public-safety protections for secrets, credentials, private
  inventory, unnecessary absolute paths, and unrequested filesystem scanning.

### Beta limitation

Measured runtime token usage remains unavailable. Plugin Eval reports an
estimated-static deferred context cost, not measured runtime token consumption;
repository documentation, tests, fixtures, and implementation artifacts are
included in that static estimate. Empirical runtime token measurement remains
required before stable `v0.1.0`.

Phase 5D adds presentation/explainability only; existing routing selection and
the 12-scenario fixture remain unchanged.

## [0.1.0-dev] - 2026-08-17

Development baseline before the public beta; this is not a stable release.

### Added

- Phase 1 repository skeleton and package version metadata.
- `SKILL.md` with English and Traditional Chinese boundaries.
- English and Traditional Chinese README files.
- MIT license and changelog.
- Deterministic, local, standard-library structural tests.

### Not included

- Capability discovery, routing, deduplication, or Plugin scanning.
- Network or Marketplace access.
- Capability execution, installation, permission changes, or private capability inventory.
