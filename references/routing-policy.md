# Deterministic Routing Policy

## v0.2 Skill selection override

- The production objective applies only to the current recall-first available
  candidate set: select every Skill with material, non-redundant value for one or
  more TaskAnalysis items. Do not stop after one sufficient Skill or impose a
  fixed selected count.
- Final applicability checks material value, not whether another Skill already
  appears sufficient. One bounded Coverage Check may inspect only remaining
  recalled available candidates; every addition repeats canonical ID,
  availability, handoff, and applicability gates and carries `supports` plus
  `distinct_value` public evidence.
- Trusted-root discovery plus full handoff establish Skill availability; Host
  exposure is optional observation and never a formal Skill gate. Unknown
  profiles may appear only as possible-relevance diagnostics and never enter
  handoff or formal coverage completion.
- The historical primary/optional policy below remains read compatibility for
  deprecated catalog data; it does not govern the v0.2 `route()` path.

## 輸出層級

- `selected_primary`：最多 3 筆 `installed` capability。
- `selected_optional`：最多 2 筆 `available` capability。
- `recommendation_only`：只放明確標記的 trusted `unknown` advisory record；不等於 selected，也不代表可執行。
- `outcome`：固定為 `downstream_selected`、`native_model_sufficient` 或 `no_safe_match`；空 selected 不自動等於 native model sufficient。
- `execution_constraints`：保留 caller 的 bounded constraints，供 downstream executor/renderer 傳遞；不宣稱已實際執行。
- `rejected_candidates`：保留 self-routing、unavailable、unknown、overlap 與 selection-limit 原因。
- `selection_evidence`：保留 selected/recommendation-only capability 的 level、reason codes、matched triggers 與 matched requirements，供雙語 explanation renderer 使用。

Router 是 advisory-only；不執行命令、載入 Plugin、安裝 capability、變更 permission 或替呼叫端授權。

## 必要排除

1. `codex-capability-router` 永遠不能推薦自己。
2. `unavailable` 永遠不能被選取。
3. `unknown` 永遠不能進 `selected_primary`、`selected_optional` 或 normal recommendation。
4. `unknown` 只有在 `source` 為 trusted runtime/manual，且輸入明確有 `recommendation_only=true` 時，才能進 `recommendation_only`。
5. 未找到可信候選時回傳空 selected tuple 與 `no_match` rationale，不湊數。

## Structured intent

- `explicit_requests` 只接受 bounded canonical capability ID/alias；不保存 private absolute path、`SKILL.md` path、raw frontmatter 或 secret-like values。
- `action_requirements` 支援 bounded canonical tokens：`rewrite_text`、`generate_text`、`edit_spreadsheet`、`compose_image`，必要時可使用 `verify_facts`、`debug_firmware`。
- `execution_constraints` 支援 `preserve_original`、`no_generative_redraw`、`no_invented_content` 與 `no_screen_content_modification`。
- hard gates 先排除 controller、routing support、unavailable、unknown 與 action-incompatible records；explicit request 不得繞過安全規則。
- 通過 hard gates 後，排序優先順序為 explicit request、action coverage、exact trigger、specialist/workspace specificity、availability、preferred_for、priority、stable ID。Topic vocabulary 只作 fallback/context evidence。
- `rewrite_text`/`generate_text` 在沒有 explicit downstream request 且沒有相容下游能力時，可回傳 `native_model_sufficient`；不可用 explicit capability 則回傳 `no_safe_match`。

## Presentation contract

- `## Router / Controller` 只顯示 `router_controller_ids`。
- Selected section 只讀 `selected_primary` 與 `selected_optional`；不得從 `rejected_candidates`、controller 或 routing support 推導 selected。
- Previous selected capability 不會自動成為 next-task mandatory capability；external handoff integration 留待後續 audit。

## 排序與界線

先以固定 task aliases 與 bounded phrase matching 判斷 relevance，再依 exact trigger、specialist、installed、preferred、evidence、priority、identifier 排序；同分以 `(id.casefold(), id)` 穩定決定。相同輸入必須產生相同 selected、rejected、rationale。

同一 `overlap_group` 只保留排序後第一筆。`unknown` 的 recommendation-only output 也依同一 deterministic key 排序。

Human-readable output 只將 `selection_evidence` 轉成短句 rationale；不輸出 hidden chain-of-thought，也不以未記錄的比較性宣稱補理由。
