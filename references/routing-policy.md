# Routing Policy

## v1.1.3 normative contract

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
- Every final selected Skill or Provider must have a received `selected`
  disposition in its own task/sweep-bound batch. Missing selected decisions
  fail with `selected candidates require batch evidence`, naming the missing IDs;
  no Receipt is created. Missing whole batches containing only unselected
  candidates are allowed and remain `PARTIAL`. Missing/extra IDs
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
- Calls without validated TaskAnalysis retain legacy compatibility and cannot
  submit observed batch evidence. The renderer labels them as legacy, with
  unreported evidence. Structured calls require observed decisions for all final
  selected items; remaining candidates may stay unresolved. Evidence supplied
  to route requires validated TaskAnalysis.
  No Provider decisions are accepted when Execution Needs are empty.

## Execution and integration boundary

Router is read-only. The Host owns actual Skill application, Provider invocation,
authorization, network/write/delete/send/publish controls, and ExecutionAttempt.
Selection does not authorize execution. Installation of SKILL.md is instruction
integration, not proof that an enforced per-task Host entry point exists.
No persistent inventory, private arguments, credentials, or hidden chain-of-thought
are required for this protocol.

## Host API workflow

Run all four Python blocks in the same Host process. The examples reuse the
existing public APIs and one typed inventory snapshot. `to_mapping()` is a public
projection, not a saved context that can be loaded for finalization.
The inventory snapshot is a typed container; use
`inventory_snapshot.inventory`, not `inventory_snapshot.to_mapping()`.

The Host supplies these inputs from the current task and session:

| Input | Source |
| --- | --- |
| `task_analysis` | Task summary, work items, deliverables, constraints and quality expectations |
| `host_home`, `host_codex_home` | The Host's actual user home and Codex home directories |
| `runtime_extra_roots`, `plugin_manifests` | Trusted roots and active Plugin declarations actually exposed by the Host; empty tuples when none are supplied |
| `host_preliminary_skill_ids` | Model judgments using the discovered candidate IDs |
| `host_decision`, `host_final_decision` | Initial Skill selection and Execution Needs, followed by the same payload with the Host's final Supporting decision when needed |
| `skill_batch_decisions`, `supporting_batch_decisions` | Actual Host dispositions using the prepared task and sweep fingerprints |
| `host_registry`, `host_snapshot_id`, `host_session_scope` | Current-session tool metadata and snapshot identity |
| `readiness_evidence` | Existing typed readiness certificates or observations; an empty tuple when readiness has not been established |

`task_analysis` has exactly five fields: `task_summary` is a non-empty string;
`work_items`, `deliverables`, `constraints` and `quality_expectations` are arrays
of bounded public strings. Keep actual targets and authorized stages in those
fields. Do not substitute `tasks` for `work_items` or omit an empty array.
Receipt summary/reasons have stricter public-text validation, including slash
rejection. Use a faithful public summary without paths; retain original interface
names and exact requirements in work items and the original task. If validation
fails, retain its error; changing the task requires fresh contexts and decisions.

`host_decision` uses `DECISION_PAYLOAD_CONTRACT_VERSION` from `route_context`,
the same `task_analysis`, `skill_selection` and `execution_needs`. Skill selection
contains `task_summary`, `selected_skills` and `selection_status`; each selected
item has a discovered `id`, a specific public `reason`, and optional indexed
`supports` from TaskAnalysis. Each execution need contains `need` and `reason`.
If the task actually needs tools, describe those needs; empty needs mean Provider
selection is not required, not that tools were unavailable or unused.
When needs exist, `host_final_decision` also includes `final_supporting_decision`
with `selected_supporting_capabilities` and `unmet_execution_needs`.

Project Host tool metadata into the documented registry fields, keeping stable
`namespace`, `action_name`, public purpose and known hierarchy. Host descriptions
allow up to 2,048 characters; downstream Provider descriptions allow 1,024 and
also reject secret-like text and absolute paths. Use a faithful bounded public
summary rather than copying full tool documentation. A nullable description can
remain `None` when no safe public summary is established; retain that SPARSE
candidate and consult the original trusted metadata for semantic judgment.
Do not relax validators, remove candidates or invent hierarchy to hide an error.

Before importing, check the selected runtime from a neutral directory using
`python -X utf8 -B -I`. Add only its explicit root to `sys.path`, inspect the package's
`__file__` and `__version__`, and verify that the loaded file belongs to that root.
Absence of an exposed routing tool does not prove that the installed Python API
is unavailable. Try the documented library entry; if it fails, report the actual
import/API error and stopping point. Only `route()` can create a formal Receipt.
Do not substitute a development checkout after an installed-runtime failure.
Import success proves loadability only; it does not create a routing Receipt.

### Prepare the actual candidates

<!-- host-workflow:prepare -->
```python
from pathlib import Path
from codex_capability_router.inventory import refresh_skill_inventory_snapshot
from codex_capability_router.route_context import prepare_route_context
from codex_capability_router.skill_plan import build_skill_root_plan
from codex_capability_router.task_analysis import validate_task_analysis

analysis = validate_task_analysis(task_analysis)
plan = build_skill_root_plan(
    home=Path(host_home), codex_home=Path(host_codex_home),
    runtime_extra_roots=tuple(Path(root) for root in runtime_extra_roots),
    plugin_manifests=plugin_manifests,
)
inventory_snapshot = refresh_skill_inventory_snapshot(
    plan, plugin_manifests=plugin_manifests,
)
skill_context = prepare_route_context(
    analysis, skill_roots=(), skill_root_plan=plan,
    skill_inventory_snapshot=inventory_snapshot,
    plugin_manifests=plugin_manifests,
)
candidate_batches = skill_context.inventory_sweep.to_mapping()
candidate_details = skill_context.to_mapping()
```

The Host reads every supplied batch and records its own judgments. It must not
slice the candidate list, manufacture dispositions from final selected IDs, or
reuse judgments from another task. Missing batches and `needs_detail` remain
`PARTIAL`; do not replace them with automatic `not_selected` responses.

### Read the selected instructions

<!-- host-workflow:handoff -->
```python
from codex_capability_router.selection import (
    handoff_full_instructions, preliminary_select, prepare_selection,
)

preparation = prepare_selection(
    inventory_snapshot.inventory, analysis.task_summary,
    task_analysis_items=analysis.retrieval_items(), high_recall=True,
)
preliminary = preliminary_select(preparation, host_preliminary_skill_ids)
handoffs = handoff_full_instructions(inventory_snapshot.inventory, preliminary)
handoff_instructions = {item.id: item.instructions for item in handoffs}
```

The Host reads every full value in `handoff_instructions` before deciding
Execution Needs and Providers. `FullInstructionHandoff` exposes `id`,
`fingerprint` and `instructions`; it is not a dict and has no `skill_id` field.
Instruction content stays in the Host's task context and must not enter public
Receipts. Selection and handoff do not prove that a Skill's method was applied.
If applicability changes, use the existing bounded correction or Coverage Check
inputs before finalization; do not overwrite a finalized Receipt.

### Prepare the Provider candidates

<!-- host-workflow:supporting -->
```python
from codex_capability_router.host_snapshot import prepare_host_capability_snapshot
from codex_capability_router.route_context import validate_decision_payloads
from codex_capability_router.supporting_context import prepare_supporting_context

decision = validate_decision_payloads(host_decision)
if decision.skill_selection is None:
    raise ValueError("Host final Skill selection is required")
host_snapshot = None
supporting_context = None
if decision.execution_needs:
    host_snapshot = prepare_host_capability_snapshot(
        host_registry, snapshot_id=host_snapshot_id,
        session_scope=host_session_scope,
    )
    supporting_context = prepare_supporting_context(
        decision.execution_needs, host_capability_snapshot=host_snapshot,
        readiness_evidence=readiness_evidence,
        plugin_manifests=plugin_manifests,
    )
supporting_batches = (
    supporting_context.to_mapping() if supporting_context is not None else None
)
```

For both kinds of batch response, `task_fingerprint` is
`skill_context.context_fingerprint`; `sweep_fingerprint` belongs to that batch
context. Do not use `supporting_context.context_fingerprint` as the task fingerprint.

The Host reads the supplied Provider batches and builds `host_final_decision` and
`supporting_batch_decisions`. Retain the same prepared context. Empty Needs skip
Provider preparation and require empty Supporting decisions.

### Finalize through the existing route API

<!-- host-workflow:finalize -->
```python
from codex_capability_router.catalog import render_recommendations
from codex_capability_router.routing import SelectionRouteInput, route

decision = validate_decision_payloads(host_final_decision)
if decision.skill_selection is None:
    raise ValueError("Host final Skill selection is required")
receipt = route(SelectionRouteInput(
    task_summary=analysis.task_summary, skill_roots=(),
    preliminary_skill_ids=preliminary.skill_ids,
    final_selection=decision.skill_selection.to_mapping(),
    validated_decision_payloads=decision,
    skill_context=skill_context, supporting_context=supporting_context,
    skill_root_plan=plan, skill_inventory_snapshot=inventory_snapshot,
    host_capability_snapshot=host_snapshot,
    plugin_manifests=(plugin_manifests if supporting_context else ()),
    supporting_readiness_evidence=(readiness_evidence if supporting_context else ()),
    skill_batch_decisions=skill_batch_decisions,
    supporting_batch_decisions=supporting_batch_decisions,
))
report = render_recommendations(receipt, language="zh-TW")
```

With empty Execution Needs, Plugin Skill declarations remain in the supplied
Skill snapshot. Do not pass their manifests as Provider context to finalization;
the existing lazy Provider gate rejects any Provider context in that case.

`route()` validates context, source and batch fingerprints. A changed task,
source or tool snapshot requires fresh decisions when validation rejects the old
input. Do not retry with changed IDs or synthesize a Receipt to hide the failure.

### Report actual use and blocked actions

Publish the actual `report` from the final block. Do not reconstruct statuses
using guessed attributes such as `skill_coverage_status`. The renderer retains
Skill and Provider coverage, `supporting_selection_status`, the finalized state
and Host-reported execution as separate evidence. `not_required` means empty
Execution Needs; `no_present_supporting_provider` means no present Provider;
`no_matching_supporting_capability` means none was selected from the present
pool; `selected` means a Provider selection. Missing coverage remains unreported.

The renderer distinguishes structured calls from legacy compatibility using the
existing TaskAnalysis field, without adding caller-supplied status. Structured
finalization verifies the batch evidence of selected items, not semantic accuracy
or complete discovery. It cannot prove that every Host-exposed capability was
supplied. Keep actual root/source boundaries and the current tool snapshot; do not
replace discovery with a familiar `wanted` list or prune the Host registry to a
single tool before judging it. Unjudged candidates remain unresolved.

Keep failed attempts and the successful result in UTF-8 TEMP evidence. Preserve
`receipt.to_mapping()`, the official rendered report and original task/snapshot
bindings; do not overwrite an earlier Receipt or record speculative execution.
Import `DECISION_PAYLOAD_CONTRACT_VERSION` instead of guessing a version. Slash
validation errors identify that character restriction; a faithful public reason
can spell out both terms without treating the source as sensitive data.

For every claimed use, name its concrete contribution and evidence. A Skill can
be read without being applied; a selected tool can remain uncalled. A bounded
read-only spreadsheet extraction may use the available Python library or standard
library; that does not prove a spreadsheet Provider was called.

- **Read:** the Host actually loaded the full authoritative Skill instructions.
- **Applied:** the Host performed identifiable steps from those instructions.
- **Called:** a script, CLI or Provider tool has an actual invocation record.
- **Verified:** the relevant result has fresh verification evidence.

For Provider results, pass existing typed `ExecutionAttempt` records using
`render_recommendations(receipt, execution_attempts=attempts, language="zh-TW")`.
They must belong to this Receipt, a selected Provider and one of its Execution
Needs. The renderer labels them as Host-reported outcomes; it does not independently
verify tool execution. An empty attempt list means **execution not reported**, not
**never executed**. Preserve every attempt, including failures before a later success.

Keep the authorized stage, targets, time window and required evidence in
`TaskAnalysis.constraints` and `quality_expectations`. Source, build, artifact,
visual checks and hardware checks require their own evidence. A planning-only
constraint controls actual actions; it must not become a name-based Skill filter.

Before declaring a tool unavailable, read its selected Skill's current setup and
API documentation, initialize the documented entry point, then make the smallest
authorized probe. For desktop inspection this can be a read-only window inventory;
for a browser it can be a state query. Honor current platform restrictions and
planning-only limits. A missing method on one object proves that call failed;
it does not establish that every tool for that purpose is unavailable. Do not
switch to prohibited APIs or bypass permissions. Record the exact scope tested.

When a tool is blocked, record the failed action, actual error and unchanged
preconditions. Do not repeatedly retry the same failure. A global hook that also
blocks recovery tools requires a user-controlled recovery path; Router must not
uninstall Plugins or change settings. After recovery, run the smallest new check.
Changing capabilities after finalization requires a new route under the existing
authorization, without changing the previous Receipt.

## Instruction compliance and evaluation

Skill instructions guide model behavior; installation alone cannot force the
Host to call `route()`, run a validator or invoke another tool. Router validation
protects calls that reach its API, including source, batch and Receipt bindings.
It cannot enforce unrelated Host actions. Stronger action-time enforcement needs
Host integration and is outside this library's instruction-only installation.

Keep the entry short and operational detail in references. Diagnose actual traces
before adding rules. The [Agent Skills creation guidance](https://agentskills.io/skill-creation/best-practices)
and [OpenAI skill documentation](https://developers.openai.com/codex/skills)
support focused instructions, explicit inputs/outputs and representative testing.
[OpenAI's skill evaluation guide](https://developers.openai.com/blog/eval-skills)
distinguishes outcome, process, style and efficiency; inspect tool order and
artifacts as well as final text. [ManyIFEval](https://aclanthology.org/2025.findings-emnlp.896/)
reports degradation as simultaneous instructions increase in its tested models.
That result does not establish a failure rate or a single cause for this Host.

Before accepting a guidance change, run the executable contract/renderer tests
and a fresh independent routing-only replay of representative tasks. Check
explicit and implicit triggers, necessary steps, correct documented API use,
precise failure reports, unrelated tasks and forbidden actions. Do not supply
expected Skill IDs to the replay agent. Record source boundaries, model/session,
actual invocations, errors and per-rule results; keep selection, coverage, applied
methods and tool outcomes separate. Small replays cannot prove universal model
compliance or a statistically measured improvement. Unit fixtures test protocol
and rendering behavior, not semantic selection quality.

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
