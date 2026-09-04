# Deterministic Routing Policy

## v0.2 High-recall discovery and Skill selection

- Production flow is `DISCOVERY INVENTORY -> SEMANTIC CONSIDERATION POOL -> FINAL
  SELECTION`. Trusted Skill roots are scanned by breadth first; Host exposure or
  runtime callability is not required for Skill availability.
- The semantic pool is built from all structurally valid, identity-resolved,
  present Skills. Metadata quality is diagnostic rather than a selection gate. A
  deterministic bounded digest sweep covers every pool item; no top-k retrieval or
  tail truncation may decide which Skill the LLM can see. `skill_never_considered_total`
  must be 0.
- Select every Skill with any plausible task-relevant value for one or more
  TaskAnalysis items, deliverables, constraints, quality expectations, verification
  needs, artifact requirements, quality improvements, documentation, explanation,
  tooling, or safety work. Clearly relevant, moderately relevant, weakly but
  plausibly relevant, and relevant-but-overlapping Skills may all be selected.
  There is no fixed Skill selection maximum.
- Semantic redundancy is not an exclusion reason. Do not stop after one sufficient
  Skill, pick an overlap-group winner, require distinct or unique value, or remove a
  Skill because another selected Skill covers the same work item. Exclude only clearly
  irrelevant, absent, identity-unresolvable, exact canonical duplicates, explicit task
  constraints, controller records, routing-support records, or records rejected by a
  later full-handoff safety boundary. Readiness negatives remain selectable when
  presence is established.
- Final applicability checks preserve the LLM's plausible-relevance decision and do
  not impose a materiality, distinctness, or non-redundancy threshold. At most one
  bounded Skill Coverage Check may inspect remaining candidates; a relevant addition
  may be added even when another Skill already supports the same work item. The
  addition's `supports` and `distinct_value` fields are bounded public audit evidence,
  not a claim that the Skill must be semantically unique.
- Trusted-root discovery plus full handoff establish Skill availability; Host
  exposure is optional observation and never a formal Skill gate. Unknown
  profiles may appear only as possible-relevance diagnostics and never enter
  handoff or formal coverage completion.
- The historical primary/optional policy below remains read compatibility for
  deprecated catalog data; it does not govern the v0.2 `route()` path.

## v0.2 Supporting Provider selection override

- Formal kinds are `app`, `mcp`, `builtin_tool`, and `host_tool`; Plugin is a
  provenance container, not a Provider. Active Plugin manifests may contribute
  child Skill, App, and MCP records to their corresponding inventories. App/MCP
  child tools do not become builtin Providers.
- Discovery evidence, presence, and readiness are separate. A trusted Host-native
  top-level registry entry may become a generic `builtin_tool`; official App/MCP
  and trusted configured inventories remain their own formal kinds.
- All present, resolved Provider digests enter a deterministic bounded semantic
  sweep, including sparse or opaque metadata. Unknown Host hierarchy uses the
  `host_tool` fallback; no top-k truncation may starve a Provider;
  `provider_never_considered_total` must be 0.
- Select every selectable Provider with plausible material and non-redundant value
  for one or more Execution Needs. There is no fixed Provider selection maximum.
- `PRESENT_UNVERIFIED` and `KNOWN_UNAVAILABLE` remain selectable when presence
  and identity are resolved; readiness uncertainty is recorded for execution
  rather than used as a semantic exclusion.
- A Provider description or understandable tool title/summary improves metadata
  quality but is not a consideration gate. Python must not infer Provider
  categories, rank Providers, or map keywords to Provider IDs.
- One bounded Supporting Coverage Check may inspect remaining selectable
  Providers and add distinct Providers. Each addition must cite one original
  `execution_need` and a public `distinct_value`; no second check or expanded
  provider loop is allowed.
- A generic local execution Provider and a specialized image, diagram, document,
  research, validation, or publication Provider are not redundant solely because
  they can contribute to the same final artifact; semantic distinction remains
  the Codex/LLM decision.

## Selection tie-break and execution boundary

- `WHEN IN DOUBT BETWEEN A PLAUSIBLY USEFUL CAPABILITY AND NOT SELECTING IT,
  SELECT IT.` Only clearly irrelevant, constraint-violating, absent,
  identity-unresolvable, exact canonical duplicates, explicitly constrained,
  controller, or routing-support records are excluded before semantic selection.
- Readiness, callability, authorization, and connection uncertainty never remove
  a present capability from semantic consideration. Execution remains conservative:
  permission, authorization, network, write/delete/send/publish safety, and runtime
  errors are enforced after selection and recorded separately.
- Python may parse, canonicalize, exact-dedupe, validate metadata, batch, and
  fingerprint. It must not map keywords to IDs, rank semantic relevance, or decide
  whether a Provider is an image/document/diagram match.

## 輸出層級

- `selected_primary` / `selected_optional`：deprecated presentation fields only;
  `LEGACY PRESENTATION ONLY`, not a v0.2 semantic selection limit. The current
  `route()` path uses `selected_skills` with no fixed Skill maximum。
- `recommendation_only`：只放明確標記的 trusted `unknown` advisory record；不等於 selected，也不代表可執行。
- `outcome`：固定為 `downstream_selected`、`native_model_sufficient` 或 `no_safe_match`；空 selected 不自動等於 native model sufficient。
- `execution_constraints`：保留 caller 的 bounded constraints，供 downstream executor/renderer 傳遞；不宣稱已實際執行。
- `rejected_candidates`：保留 hard-exclusion diagnostics such as self-routing,
  exact duplicate, explicit constraint, and handoff-safety reasons; overlap and
  selection-limit are not Skill exclusion reasons。
- `selection_evidence`：保留 selected/recommendation-only capability 的 level、reason codes、matched triggers 與 matched requirements，供雙語 explanation renderer 使用。

Router 是 advisory-only；不執行命令、載入 Plugin、安裝 capability、變更 permission 或替呼叫端授權。

## 必要排除

1. `codex-capability-router` 永遠不能推薦自己。
2. `KNOWN_UNAVAILABLE`、disabled、auth-required、disconnected 與 uncallable 狀態不會
   在 presence 已建立且 metadata 足夠時阻擋 semantic selection；它們只供 execution diagnostics。
3. 無法證明 capability 存在、identity 無法解析、metadata 完全不足的 record 不進 semantic pool。
4. `unknown` 若只是 existence 未建立，保留為 diagnostic，不當作 present capability。
5. 未找到可信候選時回傳空 selected tuple 與 `no_match` rationale，不湊數。

## Structured intent

- `explicit_requests` 只接受 bounded canonical capability ID/alias；不保存 private absolute path、`SKILL.md` path、raw frontmatter 或 secret-like values。
- `action_requirements` 支援 bounded canonical tokens：`rewrite_text`、`generate_text`、`edit_spreadsheet`、`compose_image`，必要時可使用 `verify_facts`、`debug_firmware`。
- `execution_constraints` 支援 `preserve_original`、`no_generative_redraw`、`no_invented_content` 與 `no_screen_content_modification`。
- hard gates 先排除 controller、routing support、無法證明存在、identity 無法解析與明確 constraint/action incompatibility；metadata sparse/opaque 與 readiness 不在此 gate。explicit request 不得繞過安全規則。
- 通過 hard gates 後，Codex/LLM 可依完整 metadata 做語意判斷；Python 僅維持 canonical identity、exact duplicate dedupe、schema、安全與 deterministic batching，不以 overlap、materiality 或另一個 Skill 已足夠來排除 present capability。
- `rewrite_text`/`generate_text` 在沒有 explicit downstream request 且沒有相容下游能力時，可回傳 `native_model_sufficient`；不可用 explicit capability 則回傳 `no_safe_match`。

## Presentation contract

- `## Router / Controller` 只顯示 `router_controller_ids`。
- Selected section 只讀 `selected_primary` 與 `selected_optional`；不得從 `rejected_candidates`、controller 或 routing support 推導 selected。
- Previous selected capability 不會自動成為 next-task mandatory capability；external handoff integration 留待後續 audit。

## 排序與界線

Semantic relevance 與 selection 由 Codex/LLM 根據完整 capability metadata 判斷；Python 僅負責 canonical identity、exact dedupe、bounded metadata validation、deterministic batching 與 fingerprint。相同輸入必須產生相同 structured result。

同一 `overlap_group` 不再選 winner 或只保留第一筆；不同 canonical IDs 只要各自具備 plausible task relevance 即可同時 selected。`overlap_group` 僅作 provenance/diagnostic metadata。`unknown` 的 recommendation-only output 也依同一 deterministic key 排序。

Human-readable output 只將 `selection_evidence` 轉成短句 rationale；不輸出 hidden chain-of-thought，也不以未記錄的比較性宣稱補理由。
