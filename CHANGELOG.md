# Changelog

All notable changes to `codex-capability-router` are documented here.

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
