# Codex Capability Router

Version: `v0.1.0-beta.2`
Status: **Beta / Pre-release**

Codex Capability Router v0.1.0-beta.2 is a local-first, context-first, read-only capability
recommendation skill with bounded local discovery, deterministic routing, and
bilingual output.

This release has passed its deterministic functional validation suite: **46/46
tests pass**, including 12 routing scenarios (6 `zh-TW`, 6 `en`). Plugin Eval
currently reports a high static deferred-context estimate. That estimate
includes repository artifacts and is not measured runtime token consumption.
Empirical runtime token measurement remains a requirement before promotion to
stable `v0.1.0`.

Real-world local acceptance has also completed successfully in one independent
STM32G0 firmware workspace. It verified automatic and explicit routing,
workspace-specific specialist preference, route-only selection, downstream
execution, and the PASS/FAIL/BLOCKED/HARDWARE_PENDING evidence boundaries.
Private project details are intentionally omitted.

## Current v0.1.0 boundary

The implementation accepts only caller-supplied skill roots, manual inventory,
canonical registry records, and a user task. It validates records, performs
deterministic advisory routing, and renders `en` or `zh-TW` catalogs and
recommendations. It does not execute capabilities, install or manage Plugins,
scan unrequested paths, use network discovery, access a Marketplace, change
permissions, or persist private inventory.

No private capability inventory, account data, credentials, secrets, or
unnecessary personal absolute paths are stored or emitted.

## What this project is

The project provides a small Python standard-library implementation and a
Codex `SKILL.md` entrypoint. It turns caller-supplied capability descriptions
into a runtime-scoped registry and explainable advisory recommendations.

## What the skill does

- Reads a runtime capability envelope, approved read-only CLI probe results,
  explicitly supplied skill roots, and manual inventory.
- Normalizes records, deduplicates stable identifiers, and preserves
  provenance, confidence, evidence, and conflicts.
- Applies runtime > CLI > explicit skill root > manual precedence.
- Produces deterministic primary/optional recommendations and `en` or `zh-TW`
  catalog/output.
- Adds a concise Selected Capabilities explanation with capability kind,
  PRIMARY/OPTIONAL level, registry-provided Function metadata, and deterministic
  reason codes rendered as short user-facing rationale.

## What the skill does NOT do

It does not execute capabilities, install/update/uninstall Plugins or skills,
change permissions, access a Marketplace, perform network discovery, scan
unrequested paths, store private inventory, or handle credentials, API keys,
tokens, OAuth, or account data.

## Supported languages

Explicit output languages are English (`en`) and Traditional Chinese
(`zh-TW`). `auto` selects `zh-TW` only when the request contains Traditional
Chinese characters; otherwise it conservatively selects English.

## Installation, update, and uninstall

This repository is the installable skill checkout; no package-index installer
or automatic permission change is included.

1. Clone or copy this repository into a local skill checkout.
2. Expose that checkout's `SKILL.md` through the host's normal local-skill
   mechanism.
3. Keep the checkout in an explicitly approved skill root.

To update a Git checkout, run `git pull --ff-only` in that checkout. To update a
copied checkout, replace it with a reviewed release copy. To uninstall, remove
only the local checkout you installed; the skill does not remove other skills,
plugins, permissions, or user data.

## Capability discovery behavior

The runtime envelope is authoritative. The two bounded CLI probes are
`codex plugin list --json` and `codex mcp list --json`; failure produces a
partial result with an `unknown` record rather than an availability guess.
Only caller-provided skill roots are scanned. Manual inventory is descriptive
input, not verification or execution authorization.

## Registry location and behavior

The runtime registry is canonical and runtime-scoped: it exists for the
current routing operation and is not persisted as a private inventory. Its
public schema is `schema/capability-registry.schema.json`; the fixed test
registry is `tests/fixtures/routing_registry.json` and is not a real user
inventory. Generated bilingual catalogs are `docs/CATALOG.en.md` and
`docs/CATALOG.zh-TW.md`.

Optional bilingual Function metadata uses the registry `function` object with
`en` and `zh-TW` values. Machine-readable route output retains
`selection_evidence` with capability ID, selection level, reason codes, and
matched evidence.

## Routing behavior

Routing is deterministic and advisory-only. It excludes `unavailable` and
normal `unknown` records, protects against self-routing, keeps at most three
installed primary recommendations and two available optional recommendations,
and reports rationale and rejected-candidate provenance. A trusted,
explicitly marked `unknown` record may appear only in the separate
recommendation-only section.

The router controller itself and records marked as internal routing support are
permanently excluded from downstream task selections. In route-only mode,
target-task capabilities are still selected with `execution_allowed=false`;
selection does not execute the selected capability.

After routing, the human-readable output includes `Selected Capabilities` and,
when applicable, `Selected Skills`. Each entry shows Name, Kind, selection level,
Function, and a brief rationale derived only from recorded routing evidence such
as trigger matches, requirement coverage, specialist match, availability, or
optional coverage. Missing Function metadata uses an explicit unavailable
fallback; it is never inferred from a category.

## Security and privacy model

Inputs are validated at the boundary. Source labels are abstract labels;
explicit roots are an allowlist; probes use bounded, non-shell execution; and
diagnostics do not echo rejected sensitive values. The implementation stores
or emits no API keys, tokens, passwords, OAuth credentials, private account
data, raw personal absolute paths, or private Plugin inventory.

## Known limitations and v0.1 scope

The beta scope is read-only local discovery, canonical registry merge,
deterministic routing, provenance/conflict handling, bilingual catalogs, and
bounded validation. The fixed validation set contains exactly 12 scenarios:
6 `zh-TW` and 6 `en`.

Plugin Eval reports an estimated-static deferred context cost. This figure is
not measured runtime token usage; repository documentation, tests, fixtures,
and implementation artifacts are included in that static estimate. Measured
runtime token usage remains unavailable. Local software evidence also does
not prove external capability execution, hardware behavior, or physical
acceptance.

Deferred features include capability execution, installation/management,
permission mutation, remote discovery, private inventory persistence, account
integration, telemetry, GUI/service deployment, MCP hosting, and automatic
routing-policy learning.

## Example usage

Run the deterministic suite and regenerate the bilingual catalogs locally:

```powershell
python -m unittest discover -s tests -v
python -m codex_capability_router.catalog --input tests/fixtures/routing_registry.json --output docs
```

For a task such as `Fix the React component UI bug.`, the explanation includes:

```text
## Selected Capabilities
### Selected Skills
#### PRIMARY
- Name: React UI Debugging
  Kind: skill
  Selection level: PRIMARY
  Function: Diagnoses React UI regressions.
  Why selected: The task matches trigger(s): react, component, ui, bug. It is a specialist match for the task category.
```

The rationale is rendered from deterministic route evidence; it is not a hidden
reasoning trace.

## Stable release requirement

Stable `v0.1.0` requires empirical runtime token measurement (or independent
evidence of the actual loading model with an acceptable bounded budget), in
addition to the beta functional and privacy gates.

## Repository layout

```text
SKILL.md
README.md
README.zh-TW.md
LICENSE
CHANGELOG.md
pyproject.toml
codex_capability_router/
schema/
references/
scripts/
tests/
examples/
```

The `schema/`, `references/`, `scripts/`, and `examples/` directories remain
deliberately small. They do not grant execution or installation authority.

## Phase 5 evidence boundary

The bounded evaluation contains exactly twelve routing cases. Local software
tests do not prove hardware, physical water-path, external capability, or
biological acceptance.

## Real-world local acceptance

One independent STM32G0 firmware workspace completed the beta acceptance case:

- Auto-trigger, explicit routing, workspace-specific specialist preference,
  overlap/deduplication, controller exclusion, internal support exclusion, and
  route-only semantics: PASS.
- Selected Capability Explanation, deterministic rationale, downstream skill
  execution, and PASS/FAIL/BLOCKED/HARDWARE_PENDING boundaries: PASS.

This is public routing evidence only; private source, absolute paths, and
project inventory are not part of this repository.

## Local verification

Use Python 3.11 or newer and the standard library only:

```powershell
python -m unittest discover -s tests -v
python -m compileall -q codex_capability_router tests
git diff --check
```

This repository is a skill checkout, not a network service or a package
Marketplace submission.

<!--
修改紀錄（2026-08-17，Steve Peng）
原始內容：README 仍標示 Phase 1，並否認目前 source 已存在的 discovery/routing。
修改原因：同步公開說明與實際 v0.1.0 source，避免錯誤觸發與錯誤能力承諾。
修改後功能：文件說明目前唯讀功能、Phase 5 軟體證據邊界與完整 local test command。
修改紀錄（2026-08-18，Steve Peng）：補充 Phase 5D selected capability explanation、Function metadata 與 deterministic rationale 範例。
修改紀錄（2026-08-18，Steve Peng）
原始內容：README 仍標示 beta.1/42 tests，且未記錄 Phase 5E/5E-R 的 route-only 與 STM32G0 acceptance 結果。
修改原因：同步 beta.2 公開文件與已驗證的路由排除、execution suppression、46/46 deterministic suite 及 real-world evidence。
修改後功能：讀者可辨識目前 beta.2 行為、已選能力說明、recommendation-only 分離、無自動安裝/權限變更與公開驗收邊界。
-->
