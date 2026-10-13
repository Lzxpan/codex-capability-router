# Changelog

All notable changes to `codex-capability-router` are documented here.

## v1.1.3 - 2026-10-13

- GitHub 正式發布，包含 v1.1.0–v1.1.2 本機修正版的累積修改。
- 將 legacy frontmatter fixture 改為 `SKILL.fixture.md`，避免本機技能探索將測試資料當成正式技能。
- 相容測試只在暫存目錄建立 `SKILL.md`；新增交付入口、正式來源與完整 handoff 的回歸驗證。
- 保留 v1.1.2 的最終選用批次證據檢查及既有路由 API。

已知限制：Skill 指引不能保證 Host 完全遵從；批次資料驗證不證明模型已獨立判斷所有候選。缺少判斷的候選維持 `PARTIAL`，`FINALIZED` 僅代表選用資料定案。

## v1.1.2 - 2026-10-12（本機修正版，未獨立發布）

- 結構化路由要求每個最終選用 Skill／Provider 具有同上下文的 selected 批次證據；缺少證據時拒絕定案並列出缺少的 IDs。
- 未選候選仍可保留缺少決策或 needs_detail，不強迫全部 Coverage COMPLETE；無 TaskAnalysis 的相容呼叫維持可用並明確標示證據限制。
- 保留公開文字驗證，斜線錯誤改為指出具體限制；操作指引使用 UTF-8 隔離載入並保留實際路由輸入、輸出與失敗紀錄。
- 新增缺批次、部分覆蓋、相容輸出與錯誤訊息回歸檢查，移轉既有 typed fixtures；不新增相依套件、選用演算法、Hook 或記憶功能。

## v1.1.1 - 2026-10-08（本機修正版，未獨立發布）

- 調整技能入口，區分只套用指引與實際正式路由；使用既有 renderer 回報 Receipt。
- 補齊 Host 輸入欄位、路徑型別、完整 handoff 欄位及公開工具描述界線；保留稀疏候選。
- 正式雙語輸出顯示 Provider 選用狀態，保留獨立覆蓋與執行回報。
- 工具不可用結論須依目前文件初始化與最小授權探測，保留實際失敗範圍。
- 說明技能指引與 API 檢查的遵從邊界，增加操作範例與輸出回歸檢查；不新增相依套件、選用演算法、記憶或全域 Hook。

## v1.1.0 - 2026-10-07（本機修正版，未獨立發布）

- 以 `v1.0.0` 為基線，保留寬鬆選用、重疊方法並存與完整候選判斷規則；不加入 Skill Preference Memory。
- 補齊 Host API 範例，從可信 discovery、完整 Skill handoff 到正式 `route()`；沿用同一份 typed snapshots，明確回報實際失敗位置。
- 修正定案後 `provider_selected_total` 仍為準備階段零值的問題，使其與最終 Provider 清單及 `selected_count` 一致。
- 正式雙語輸出加入已選 Provider、判斷覆蓋與選填的 Host 執行回報；缺少回報維持未知，不推定執行成功。
- 驗證執行回報與 Receipt fingerprint、Provider kind／id、原始需求的綁定，保留失敗與後續重試。
- 增加 API 範例與輸出回歸測試；不新增相依套件、路由入口、Hook 或自動安裝。

原有 `v1.0.0` 圖解與驗證文件保留為歷史資料。`v1.1.0`–`v1.1.2` 未建立獨立公開 tag；累積修改隨 `v1.1.3` 發布。

## v1.0.1 - 2026-09-11（已停用）

- 曾加入 Skill Preference Memory；實際使用出現適用技能未選用的問題，後續停用並將 `main` 回復至 `v1.0.0`。
- 保留歷史 tag；`v1.1.3` 不包含這項偏好記憶功能。

## v1.0.0 - 2026-09-08

Promote `v0.2.0-beta.10` to stable `v1.0.0` without runtime behavior changes.

- Refresh the Traditional Chinese homepage and matching English README with
  portable installation, practical scenarios and accurate current contracts.
- Add an original animal-cast hero, continuous eight-panel tutorial, four-panel
  principles comic and version-controlled SVG/Mermaid architecture.
- Add focused version, documentation, asset and privacy/static release checks.
- Preserve historical beta records, tags and protocol identifiers.

See the [1.0.0 validation guide](docs/validation/v1.0.0-validation.md) and
[release notes](docs/releases/v1.0.0.md) for acceptance and remaining boundaries.

## v0.2.0-beta.10 — 2026-09-05

Bug-fix release for the beta.9 audit's remediation phase A.

- Preserve explicitly declared nested Skill roots beyond the parent's scanner depth.
- Report unreadable roots with the correct source label and continue readable roots.
- Refresh the changed selected Skill, independent of selection order; parse its
  current metadata before deciding whether selection revalidation is required.
- Separate inventory staging from observed Host decisions across discovery,
  preparation, and finalized receipts. Missing batches or `needs_detail` remain
  PARTIAL. Validate exact batch IDs, task and digest fingerprints, Execution Needs,
  duplicate batches, and final-selection consistency.
- Expose `context.inventory_sweep` and optional `skill_batch_decisions` /
  `supporting_batch_decisions`. Existing callers without responses retain partial
  coverage; FINALIZED does not imply complete semantic coverage.
- Align all READMEs and current references; keep early v0.2 guidance explicitly
  historical. Remove the broken README image reference without changing assets.

Python >=3.11, no runtime dependencies. Validation and evidence boundaries:
[beta.10 validation record](docs/validation/v0.2.0-beta.10-validation.md).
Host automatic integration, real Provider invocation, complete installed inventory,
semantic accuracy, performance targets, and preference learning are not established
by this release.

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
