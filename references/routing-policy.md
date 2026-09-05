# Routing Policy

## v0.2.0-beta.10 normative contract

This section and the current SKILL.md govern production `route()`. The historical
compatibility section below does not constrain current selection or rendering.

1. The Host creates TaskAnalysis and supplies trusted roots, active Plugin paths,
   and available Host capability metadata. Python discovers, canonicalizes,
   validates, fingerprints, and batches; it does not perform semantic selection.
2. Every present, identity-resolved candidate is staged. Metadata quality
   (`SUFFICIENT`, `SPARSE`, `OPAQUE`) and negative readiness do not exclude it.
   Unknown existence remains diagnostic; unknown Host hierarchy becomes
   `host_tool`, never an inferred App/MCP/native kind.
3. Select any Skill or Provider with plausible task-relevant value. Overlap,
   materiality, uniqueness, another sufficient capability, and fixed top-k limits
   are not exclusion rules. Exclude only clearly irrelevant, absent, unresolved,
   exact canonical duplicates, controller/routing-support, explicit constraints,
   or later unsafe handoff. In doubt between a plausibly useful capability and
   omission, select it. There is no fixed Skill selection maximum or Provider maximum.
4. Skills define methods; formal Provider kinds are `app`, `mcp`,
   `builtin_tool`, and `host_tool`. Plugin is provenance, not a Provider.
   Presence, selection, readiness, authorization, invocation, and success are
   distinct states.
5. Preserve one bounded Skill Coverage Check and one bounded Supporting Coverage
   Check. The public `distinct_value` field describes a contribution; it does not
   require semantic uniqueness. No retry loop or expanded authority is implied.
6. Handoff reads the selected authoritative source. A mismatch carries its exact
   canonical Skill ID. One targeted refresh is allowed; changed public metadata
   or identity requires `SELECTION_REVALIDATION_REQUIRED`. A further mismatch
   returns `HANDOFF_REJECTION_AFTER_ONE_REFRESH`.
7. Production presentation reads `selected_skills`, `selection_status`,
   `selected_supporting_capabilities`, `supporting_selection_status`,
   TaskAnalysis, public reasons, and coverage/readiness evidence. It never derives
   selection from rejected candidates or historical primary/optional fields.

## Observed batch decision protocol

Preparation only stages digests. It reports zero semantic decisions. Host callers
obtain `context.inventory_sweep` (also exposed by `context.to_mapping()`) and
return batches through `SelectionRouteInput.skill_batch_decisions` and
`supporting_batch_decisions`.

Each response has exactly these fields:

```json
{
  "task_fingerprint": "<skill_context.context_fingerprint>",
  "sweep_fingerprint": "<corresponding context.inventory_sweep.fingerprint>",
  "batch_index": 0,
  "dispositions": {
    "candidate-id": "selected",
    "another-candidate-id": "not_selected",
    "unresolved-candidate-id": "needs_detail"
  }
}
```

The IDs above are placeholders, not routing recommendations. Every ID from that
batch must appear exactly once. Host judgments must determine the dispositions;
Python must not manufacture them from a final selection list.

- Fingerprints bind the TaskAnalysis/context and digest contents, including Skill
  source fingerprints. Provider sweep fingerprints additionally bind Execution
  Needs. Responses cannot be reused across changed tasks or snapshots.
- Missing whole batches are allowed and remain `PARTIAL`. Missing/extra IDs
  inside a response, duplicate batch indices, invalid dispositions, and conflicts
  with final selected IDs are rejected.
- `selected` and `not_selected` are resolved decisions. `needs_detail` is a
  received but unresolved decision; it cannot accompany a final selected ID.
- `*_staged_total`, `*_decision_received_total`,
  `*_semantically_considered_total`, `*_never_considered_total`,
  `*_unresolved_total`, and `*_selected_total` describe different evidence.
  Never-considered counts missing responses; unresolved includes missing responses
  and `needs_detail`. The nested `decision_coverage` retains public dispositions.
- Coverage is `COMPLETE` only when no staged candidate is unresolved, including
  the empty-pool case. It is scoped to supplied candidates, not proof that every
  possible source was discovered. It measures Host response completeness, not
  LLM accuracy. Independent semantic acceptance is still required.
- `FINALIZED` freezes a validated selection Receipt. It may coexist with
  `PARTIAL` coverage and never proves application or execution success.
- Legacy callers can omit batch evidence; they gain no automatic complete
  coverage claim. Evidence supplied to route requires validated TaskAnalysis.
  No Provider decisions are accepted when Execution Needs are empty.

## Execution and integration boundary

Router is read-only. The Host owns actual Skill application, Provider invocation,
authorization, network/write/delete/send/publish controls, and ExecutionAttempt.
Selection does not authorize execution. Installation of SKILL.md is instruction
integration, not proof that an enforced per-task Host entry point exists.
No persistent inventory, private arguments, credentials, or hidden chain-of-thought
are required for this protocol.

## Historical v0.1 compatibility — not normative

Everything below is retained solely to interpret historical catalog artifacts.
Its readiness gates, output fields, fixed outcomes, and presentation instructions
must not be applied to current production routing.

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
