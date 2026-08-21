# Codex Capability Router

Version: `v0.1.0-beta.3`
Status: **Beta / Pre-release**

Codex Capability Router v0.1.0-beta.3 is a local-first, context-first, read-only
capability recommendation skill with bounded runtime discovery, profile-based
candidate retrieval, Codex-assisted final Skill selection, and bilingual output.

This release has passed the full regression suite: **81/81 tests pass**, and
Phase 5 Full Live Acceptance passes all five cases. Compile, UTF-8/U+FFFD,
diff, and production-source checks also pass. The canonical routing fixture
remains 12 scenarios (6 `zh-TW`, 6 `en`). Plugin Eval currently reports a
static deferred-context estimate; that estimate includes repository artifacts
and is not measured runtime token consumption. Empirical runtime token
measurement remains a requirement before promotion to stable `v0.1.0`.

Real-world local acceptance has also completed successfully in one independent
STM32G0 firmware workspace. It verified automatic and explicit routing,
workspace-specific specialist preference, route-only selection, downstream
execution, and the PASS/FAIL/BLOCKED/HARDWARE_PENDING evidence boundaries.
Private project details are intentionally omitted.

## Current v0.1.0 boundary

The implementation accepts the runtime-visible inventory, approved skill roots,
canonical registry records, and a user task. It validates records, builds
cached inventory fingerprints and Basic/Enriched Profiles, performs recall-first
candidate retrieval, and validates Codex's final Skill selection before
rendering `en` or `zh-TW` output. It does not execute capabilities, install or
manage Plugins, scan unrequested paths, use network discovery, access a
Marketplace, change permissions, or persist private inventory.

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
- Builds Basic/Enriched Profiles and retrieves candidates from the current
  runtime inventory, including explicit Skill requests when eligible.
- Reads the complete `SKILL.md` for preliminary selections before the final
  applicability check; expanded retrieval and correction are each bounded.
- Lets Codex select Skills from task meaning. The final contract contains only
  `selected_skills` and `selection_status` (`selected` or `no_matching_skill`);
  it has no keyword-to-Skill mapping, PRIMARY/OPTIONAL output, or 3+2 limit.

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
`en` and `zh-TW` values. Machine-readable selection output contains
`task_summary`, `selected_skills` with concise reasons, and `selection_status`.
It does not emit PRIMARY/OPTIONAL levels or recommendation-only final-selection
semantics.

## Routing behavior

Routing is advisory-only. Discovery, normalization, availability filtering,
profile construction, and candidate retrieval prepare the context; Codex's
main model makes the final Skill selection from the task's meaning. A Skill is
selected only when it is discovered, available, and passes the complete
`SKILL.md` applicability check. An empty result is reported as
`no_matching_skill`, never as `native_model_sufficient`; the router does not
add a legacy or silent fallback.

Keyword, category, and `provides` data may help candidate retrieval, but they do
not determine the final Skill IDs. The production output has no
PRIMARY/OPTIONAL semantics and no fixed 3+2 selection limit. New or updated
Skills do not require a Router production mapping. Expanded retrieval is used
at most once and selection correction is used at most once.

The router controller itself and records marked as internal routing support are
permanently excluded from downstream task selections. In route-only mode,
target-task capabilities are still selected with `execution_allowed=false`;
selection does not execute the selected capability.

After routing, the human-readable output includes the selected Skill IDs and a
brief Codex selection reason, or an explicit empty result with
`no_matching_skill`. Selection does not execute the Skill. The Router controller
and records marked as internal routing support remain excluded from downstream
task selection.

## Security and privacy model

Inputs are validated at the boundary. Source labels are abstract labels;
explicit roots are an allowlist; probes use bounded, non-shell execution; and
diagnostics do not echo rejected sensitive values. The implementation stores
or emits no API keys, tokens, passwords, OAuth credentials, private account
data, raw personal absolute paths, or private Plugin inventory.

## Known limitations and v0.1 scope

The beta scope is read-only runtime discovery, canonical registry merge,
inventory/profile caching, recall-first retrieval, Codex-driven Skill selection,
full applicability validation, bilingual output, and bounded validation. The
canonical fixture contains 12 scenarios: 6 `zh-TW` and 6 `en`; the full suite
contains 81 tests and Phase 5 Live Acceptance contains five cases.

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

Run the full suite and regenerate the bilingual catalogs locally:

```powershell
python -m unittest discover -s tests -v
python -m codex_capability_router.catalog --input tests/fixtures/routing_registry.json --output docs
```

For a task such as `Fix the React component UI bug.`, the selection output includes:

```text
{"selected_skills":[{"id":"react-ui-debugging","reason":"Codex judged this Skill applicable to the UI debugging task."}],"selection_status":"selected"}
```

The reason is a concise, auditable selection explanation; it is not a hidden
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

The canonical fixture contains twelve routing cases, while the full Python
regression contains 81 tests and Full Live Acceptance contains five runtime
cases. Local software tests do not prove hardware, physical water-path,
external capability, or biological acceptance.

Runtime discovery currently reports 139 malformed Skill diagnostics. This is a
non-blocking observation recorded for follow-up; beta.3 does not change
discovery scope to address it.

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
修改紀錄（2026-08-21，Steve Peng）
原始內容：README 仍描述 beta.2 的固定 primary/optional routing 與 46/46 suite。
修改原因：同步 beta.3 的 Codex final Skill selection contract、81/81 regression 與 Phase 5 Full Live Acceptance。
修改後功能：文件反映 inventory/profile、recall-first retrieval、完整 SKILL.md applicability、兩種 selection status、無 legacy/silent fallback，以及 139 malformed diagnostics 的 non-blocking 邊界。
-->
