# Codex Capability Router

Version: `v0.2.0-beta.1`
Status: **Beta / Pre-release**

Codex Capability Router v0.2.0-beta.1 is a local-first, context-first,
read-only Router that first uses Codex LLM TaskAnalysis to understand the full
work request, then separates method Skills from currently callable Supporting
Providers.

Phase 1–5 deterministic implementation is complete: the current full suite is
**137/137 PASS**, and Codex Live Acceptance A–E is PASS. This is a pre-release;
the Host did not expose a Router-trusted Skill availability declaration during
live acceptance, App remains `INSUFFICIENT_RUNTIME_EVIDENCE`, Plugin remains
`NO_RUNTIME_SAMPLE`, and formal Supporting Provider scope is limited.

## What v0.2.0-beta.1 adds

- LLM TaskAnalysis produces `task_summary`, `work_items`, `deliverables`,
  `constraints`, and `quality_expectations` as an immutable strict contract.
- Skills answer **how to do the work**; Supporting Providers answer **which
  currently callable runtime capability can execute part of it**.
- `prepare_route_context()` is read-only, deterministic, stateless, and
  Skill-only. Supporting discovery is truly lazy: when `execution_needs=[]`,
  no Supporting Provider discovery, readiness normalization, or digest work is
  performed.
- `prepare_supporting_context()` accepts only runtime-evidence-certified exact
  instances. Current formal scope is MCP `node_repl` and builtin-equivalent
  `functions.exec_command`.
- Provider semantic selection remains a Codex decision. Python performs only
  schema, identity, readiness, fingerprint, privacy, and finalization checks.
- One production `route()` creates the v0.2 Receipt and moves the route to
  `FINALIZED`; finalized decisions are immutable. Skill and Supporting status
  remain independent, including no-match results.
- `explain-code` legacy frontmatter receives bounded compatibility
  normalization without weakening malformed, sensitive, or unavailable gates.

App, Plugin, uncertified MCP instances, and uncertified builtin tools are not
formal production scope. They are not guessed, recommended, auto-installed,
auto-authorized, or used as silent fallback.

## Documentation / v0.2

- [Illustrated v0.2 User Guide](docs/v0.2_user_guide.zh-TW.md)
- [Installed Skill Live Test Report](docs/v0.2_installed_skill_live_test_report.zh-TW.md)
- [v0.2 Architecture / Design](docs/v0.2_llm_task_analysis_supporting_capability_selection_design.zh-TW.md)

## Historical v0.1.0-beta.4 baseline

This release does not replace the beta.3 semantic selection design. It hardens
the integration boundary:

- Formal Selection Results must come from `routing.route(SelectionRouteInput(...))`;
  outer orchestration cannot create a production Receipt.
- Each formal route emits a bounded, auditable Selection Receipt containing
  candidate, preliminary, full-handoff, final-selection, status, retrieval,
  correction, and finalization evidence. It stores no private chain-of-thought
  or sensitive data.
- Machine paths use canonical Skill IDs; display names remain presentation-only.
- Selection lifecycle is `OPEN` to `FINALIZED`; finalized selections are
  immutable. New work starts a new routing request.

The beta.3 semantic selection core—Codex task-meaning selection, recall-first
retrieval, profiles, and bounded Expanded Retrieval/Correction limits—remains
unchanged.

## Historical v0.1.0 boundary

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
- Builds immutable TaskAnalysis before Skill routing and derives Execution
  Needs only after Skill applicability is complete.
- Runs Supporting Provider preparation only when Execution Needs are non-empty;
  the final Provider decision is provider-level and validated by `route()`.

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
Formal production routing also returns the bounded Selection Receipt described
above.
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

## Known limitations and v0.2.0-beta.1 scope

The current pre-release includes read-only runtime discovery, canonical
registry merge, immutable TaskAnalysis, Skill-side context fingerprints,
recall-first retrieval, Codex-driven Skill selection, lazy Supporting Provider
context, bounded finalization, bilingual output, and bounded validation. The
canonical fixture contains 12 scenarios: 6 `zh-TW` and 6 `en`; the full suite
contains 137 tests and Live Acceptance contains five cases.

The Host did not expose a Router-trusted Skill availability declaration during
v0.2 Live Acceptance. Formal Supporting Provider scope is limited to the
certified instances `node_repl` and `functions.exec_command`; App is
`INSUFFICIENT_RUNTIME_EVIDENCE`, Plugin is `NO_RUNTIME_SAMPLE`, and other
MCP/builtin providers are not automatically trusted. Detail expansion was
covered deterministically but did not naturally trigger in the five cases.
Live destructive stale mutation was intentionally not performed.

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

## Promotion beyond beta requirement

Promotion beyond this beta requires continued runtime evidence for Skill
availability and broader Provider certification; this release does not claim
stable `v0.2.0` or universal Provider support.

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
regression contains 137 tests and Codex Live Acceptance contains five runtime
cases. Local software tests do not prove hardware, physical water-path,
external capability, or biological acceptance.

Runtime discovery currently reports 139 malformed Skill diagnostics. This is a
non-blocking observation recorded for follow-up; beta.4 does not change
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
修改紀錄（2026-08-25，Steve Peng）
原始內容：README 仍標示 beta.3 與 beta.3 validation baseline。
修改原因：準備 beta.4 release metadata 與 Integration Hardening release notes。
修改後功能：文件反映 91/91 tests、Integration Live Acceptance 4/4 與 production route、Receipt、canonical ID、finalization 邊界；不改變 production behavior。
修改紀錄（2026-08-26，Steve Peng）
原始內容：README 仍以 beta.4 為 current release 說明。
修改原因：v0.2.0-beta.1 release preparation 需要公開 TaskAnalysis、lazy Supporting scope 與真實限制。
修改後功能：文件反映 137/137 regression、Live Acceptance A–E、正式 Provider instance scope 與 privacy/finalization 邊界。
-->
