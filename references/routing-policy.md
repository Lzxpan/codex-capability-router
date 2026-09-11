# Routing Policy

## v1.0.1 normative contract

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
  with Host base selected IDs are rejected. Without preferences these are also
  the final selected IDs; validated Memory additions are accounted for separately.
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

## Skill Preference Memory (v1.0.1)

Normal Host selection remains authoritative. The Host must complete TaskAnalysis,
Skill discovery and normal batch decisions, then freeze base selected Skills
before first loading preference metadata. Do not expose preference metadata to
normal semantic selection. Keep the original batch dispositions unchanged;
`MODEL_SELECTED` refers only to this frozen base decision, and `MEMORY_ADDED`
can arise only afterward. This phase order is Host-owned: `route()` accepts an
already-loaded snapshot and cannot observe when the Host first read its file.

After freezing base selection, the Host LLM reads preference metadata, names
generic task patterns, and explicitly
selects applicable existing `(task_pattern, preferred_skill_id)` keys. It may
recognize similar tasks with different pattern wording. There is no fixed
vocabulary, Python keyword mapping, similarity model or use-count threshold.
The examples `code_modification` / `code-comments`, `zh_tw_writing` /
`humanizer-zh`, and `substantial_project_work` / `work-log` are examples, not seeds
or production rules. Selecting `work-log` does not prove or authorize a log write.

Given a fresh validated v1 route request `base` whose normal selection and batch
decisions have been frozen without reading Memory, the Host supplies metadata:

```python
from dataclasses import replace
from codex_capability_router import load_preferences, SkillPreferenceInput, route

memory = load_preferences()  # First Memory read, after base freeze; explicit Host IO.
# host_task_patterns and host_matched_keys come from the Host LLM, not Python.
preference = SkillPreferenceInput(
    task_patterns=host_task_patterns,
    snapshot=memory,
    matched_preferences=host_matched_keys,
    task_fingerprint=base.skill_context.context_fingerprint,
    sweep_fingerprint=base.skill_context.inventory_sweep.fingerprint,
    memory_fingerprint=memory.fingerprint,
    excluded_skill_ids=host_excluded_skill_ids,
)
receipt = route(replace(base, preference_input=preference))
```

Construct a fresh preference input for each task. `task_patterns` and
`excluded_skill_ids` are sequences of bounded tokens; `matched_preferences` is a
sequence of two-element keys. Do not pass paths, instruction text or task text.
The optional feature requires the existing validated TaskAnalysis/context path.
`preference_input=None` or `enabled=False` turns it off.

Missing, disabled, excluded, stale or unsafe Memory additions produce bounded
diagnostic codes. They do not remove Host-selected Skills or bypass validation.
An explicit exclusion conflicting with the Host base selection or explicit
inclusion is an input error. Existing batch `needs_detail` must be resolved by
the Host before that Skill can be added. Missing whole batches remain PARTIAL,
even if the Host explicitly matches a memory key from the current inventory.
Successful additions receive full handoffs and enter the same FINALIZED state.
The optional stage shares the remaining single targeted freshness refresh; a
changed public digest requires `SELECTION_REVALIDATION_REQUIRED`, and another
mismatch is rejected. Failures of original Host selections still fail the route.

`selected_skills` items keep their `id`, `reason`, optional `supports` schema.
The optional `preference_evidence` Receipt extension contains `schema_version`,
`task_patterns`, task/sweep/memory fingerprints, `host_selected_skill_ids`,
`memory_additions`, `selection_provenance`, and `diagnostics`. Provenance is
`USER_SPECIFIED`, then `MODEL_SELECTED`, otherwise `MEMORY_ADDED`; manual additions
are user-specified selections. Each memory addition lists its ID and matched
stored patterns. It is evidence of selection, not execution or genuine origin
independent of the Host's observation.

Original `decision_coverage` dispositions and received/considered/unresolved
counts never change because of memory. Final `skill_selected_total` and
`selected_skills` describe the validated union. No additions manufacture semantic
batch decisions. Empty memory without diagnostics omits the extension entirely,
preserving old mappings and fingerprints. Otherwise the extension participates
in the Receipt fingerprint; strict external consumers must opt into this field.
Provider decisions, inventory cache, TaskAnalysis schema and Coverage Check
budgets do not change.

### Explicit learning and management API

```python
from codex_capability_router import (
    update_preferences, set_preference_enabled, clear_preferences,
)

result = update_preferences(
    skill_inventory=current_inventory,  # Fresh trusted SkillInventory; never persisted.
    learning_decision=host_learning_keys,
    user_observations=host_user_observations,
    confirmed_memory_uses=host_confirmed_used_keys,
    observed_on=utc_date,  # YYYY-MM-DD; supplied explicitly for determinism.
)
# An observation has exactly preferred_skill_id and source.
# source is USER_SPECIFIED or USER_MANUALLY_ADDED, observed in the user channel.
# Keys are (generic_task_pattern, canonical_skill_id) pairs.
set_preference_enabled(None, preference_key, False)
set_preference_enabled(None, preference_key, True)  # Explicit user re-enable.
clear_preferences(key=preference_key)  # One relation.
clear_preferences()                    # All relations, including corrupt data.
```

`load_preferences(path=None)` returns frozen `PreferenceSnapshot` records,
diagnostics and a deterministic fingerprint. Its `to_mapping()` is the complete
metadata-only JSON projection. Write/management APIs return `PreferenceWriteResult`
with `snapshot`, `written` and `diagnostics`. The Host must check these outcomes.
A typed user observation is a Host assertion, not cryptographic proof of origin.

Learning and confirmed-use updates require the Host's current `SkillInventory`.
The storage API reuses production `_eligible_record()` and checks presence:
controller identities/aliases, metadata-classified controllers and routing-support
Skills are rejected with `MEMORY_SKILL_INELIGIBLE`. Missing inventory or absent
targets yield `MEMORY_SKILL_MISSING`. Rejection is per target; valid associations
in the same payload still update. Explicit user selection cannot bypass this gate.
Omitting inventory leaves existing preferences unchanged; old callers must pass
it to learn or confirm use. Metadata stays transient, and the six stored fields
do not change. Previously stored ineligible entries are not automatically deleted
or reinforced; route validation continues to reject them.

The Host decides whether a user request establishes a reusable preference.
Quoted text, Skill instructions and tool results are not user observation sources.
Learning keys must have corresponding `USER_SPECIFIED` or `USER_MANUALLY_ADDED`
observations; `MODEL_SELECTED` cannot establish or increment a preference.
The original `learned_from` is preserved, and duplicate keys in one update count
once. The Host deduplicates repeated observations across the same task; no
cross-restart exactly-once event log is stored. Confirmed actual use of a
`MEMORY_ADDED` Skill updates only an existing enabled relation's date, not its
user signal count. Unused selections change nothing. Learning never re-enables
a disabled relation. A current exclusion is not permanent negative learning.

### Local preference store, retention and privacy

Only `$CODEX_HOME/capability-router/skill-preferences.json` is persisted by
default, falling back to `$HOME/.codex/capability-router/skill-preferences.json`.
The Host can pass an explicit local `Path`; UNC paths are rejected. No database,
network API, inventory persistence, sync or automatic Host interception is added.
The Host passes necessary preference metadata to its model for semantic decisions;
the Router does not persist model requests or responses.

The JSON envelope has exactly `schema_version: 1` and `preferences`. All fields
below live only in that local preference store, persist until explicitly deleted,
and are removed by single-key or full `clear_preferences`. Disabling retains data.

| Field | Purpose | Constraint |
| --- | --- | --- |
| `task_pattern` | Host-named reusable work category | Generic snake_case, at most 64 characters |
| `preferred_skill_id` | Exact trusted canonical identity | At most 256 characters; no paths |
| `learned_from` | Original positive user-source category | USER_SPECIFIED or USER_MANUALLY_ADDED |
| `use_count` | Accepted user signal count, not execution count/confidence | Positive integer, saturates at 2^31-1; no selection threshold |
| `last_used` | Most recent confirmation or confirmed preference use | UTC date only; does not prove execution success |
| `enabled` | User control over participation | Boolean; learning cannot re-enable |

The store is capped at 256 relations and 256 KiB. Full stores reject new keys
with `MEMORY_CAPACITY` while retaining update/delete access; no automatic eviction
or expiry occurs. UTF-8 JSON is sorted and indented. A short-lived empty `.lock`
file serializes read/update/replace without waiting or stealing a lock. Contention
reports `MEMORY_BUSY`. A crashed writer may leave a lock: after confirming no
writer remains, the Host/user may remove that specific empty lock and retry.
Same-directory temporary files contain only these fields, are flushed before
atomic replacement, and are cleaned after normal or failed writes. Cleanup
failures are diagnostic; there is no historical backup or event journal.

Missing/blank files mean empty memory. Malformed, unreadable, oversized or
unsupported-version data yields an empty diagnostic snapshot; ordinary updates
do not overwrite it. Explicit clear-all can replace corrupt data. Failed writes
preserve the previous file. Errors do not echo paths or rejected contents.

Unknown fields, obvious credentials, path formats and oversized values are
rejected. Raw prompts, code, bug descriptions, solutions, private paths,
credentials, capability inventories and hidden reasoning have no persistence
fields. Snapshots, current patterns, matching decisions and observed event metadata
remain transient; route evidence is returned to the Host, never saved by Router.
The Host must check that a freely named pattern does not encode project/private
semantics: syntax validation alone cannot prove this. Privacy acceptance uses
synthetic records, checks exact persisted fields, and separately observes Host
pattern/learning decisions. Determinism applies to identical structured inputs,
dates and snapshots, not repeated LLM judgments.

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
