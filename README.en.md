# Codex Capability Router

[繁體中文](README.md) | English

![Codex Capability Router](docs/assets/readme-v2/router-hero.png)

[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-2ea44f)](LICENSE)
[![Release: 0.2.0-beta.10](https://img.shields.io/badge/release-0.2.0--beta.10-f59e0b)](https://github.com/Lzxpan/codex-capability-router/releases/tag/v0.2.0-beta.10)

**Current version: `v0.2.0-beta.10`, Beta / Pre-release.**

A read-only Python library for a Codex / Host controller. The Host LLM understands the task and selects useful Skills and Providers. Python handles trusted discovery, canonical identity, full-instruction handoff, input validation, and immutable selection Receipts.

Installing the Skill provides instruction-based integration. Automatic routing for every task, complete local inventory, Skill application, and real Provider invocation still require Host integration and separate evidence. Installation or a `FINALIZED` Receipt does not establish those behaviors.

Compatibility baseline: `0.1.0`; read-only routing does not emit a private capability inventory.

## Fixed in beta.10

- **Nested roots:** compression respects the scanner's actual depth and retains explicitly declared children the parent cannot reach. No recursive scan was added.
- **Unreadable roots:** missing or unreadable roots produce their own `unreadable_root` diagnostic while readable sources remain available.
- **Selected Skill freshness:** the one allowed recovery refreshes the changed canonical Skill, regardless of selection order. Changed metadata or identity requires `SELECTION_REVALIDATION_REQUIRED`; a second mismatch remains `HANDOFF_REJECTION_AFTER_ONE_REFRESH`.
- **Decision coverage:** staged candidates, received Host decisions, resolved decisions, and selected candidates are distinct. 500 digests with no responses means staged 500, decision received 0, and `PARTIAL`.
- **Current policy:** Skills and Providers share plausible relevance, neutral overlap, SPARSE/OPAQUE retention, and separate presence/readiness. Historical primary/optional contracts do not govern production routing.

## Flow and responsibility

![Conceptual Router architecture](docs/assets/readme-v2/router-architecture.svg)

The diagram is conceptual; the Host must supply actual candidate decisions.

```text
Host TaskAnalysis
  -> trusted Skill discovery + digest batches
  -> Host Skill decisions + full handoff + one Skill Coverage Check
  -> Host Execution Needs
  -> Provider discovery + digest batches (only when needs are non-empty)
  -> Host Provider decisions + one Supporting Coverage Check
  -> route(SelectionRouteInput(...)) -> FINALIZED Receipt
  -> Host application/invocation -> separate ExecutionAttempt
```

| Term | Responsibility |
| --- | --- |
| Skill | Methods and quality rules; the Host reads and applies the full instructions. |
| Provider | An `app`, `mcp`, `builtin_tool`, or `host_tool`; invoked by the Host. |
| Plugin | A package and provenance container, not a callable Provider. |
| Router | Validation and handoff; it does not call an LLM or selected endpoint. |

There is no top-k truncation or fixed selection limit. Overlap does not exclude plausible task-relevant capabilities. `SUFFICIENT`, `SPARSE`, and `OPAQUE` metadata can all enter the pool. Established presence and identity remain selectable even with unknown or negative readiness; execution retains authorization and safety boundaries. Unknown Host hierarchy remains a `host_tool`, not a guessed App or MCP.

## Reading coverage

| Field / state | What it establishes |
| --- | --- |
| `*_staged_total` | Candidates placed in deterministic digest batches. |
| `*_decision_received_total` | Candidates with Host responses validated against schema, task, and snapshot. |
| `*_semantically_considered_total` | Responses with final `selected` or `not_selected` dispositions, excluding `needs_detail`. |
| `*_never_considered_total` | Candidates without a received Host response. |
| `*_unresolved_total` | Missing responses plus candidates still marked `needs_detail`. |
| `*_semantic_coverage_status=COMPLETE` | All candidates in this supplied pool have final dispositions. It proves neither LLM judgment quality nor discovery of every external capability. |
| `selection_state=FINALIZED` | Receipt finalization; coverage can still be `PARTIAL`. |

The Host obtains batches from `skill_context.inventory_sweep` and `supporting_context.inventory_sweep`, then passes responses through `SelectionRouteInput.skill_batch_decisions` and `supporting_batch_decisions`. Each response includes the Skill context's `task_fingerprint`, the relevant `sweep_fingerprint`, a zero-based `batch_index`, and an exact `dispositions` mapping. Missing whole batches remain PARTIAL. Missing or extra candidate IDs within a response, duplicate batches, conflicting selections, and stale task/snapshot responses are rejected. Provider sweeps also bind the Execution Needs.

These are public Host dispositions, not Python semantic reasoning or hidden chain-of-thought. See the [current routing contract](references/routing-policy.md) and [usage guide](docs/v0.2_user_guide.zh-TW.md).

## Discovery and cache

Fixed global roots are `$HOME/.agents/skills` and `$CODEX_HOME/skills`; only the declared `.system` child receives additional traversal. Plugin discovery follows resolved active packages and manifest-declared paths. Unknown subtrees, shared Plugin cache ancestors, and whole disks are not scan roots.

`RootPlanSnapshot` and `SkillInventorySnapshot` are caller/session-owned caches. The Host invalidates or refreshes them when sources change. Ordinary routes can reuse snapshots; selected Skill handoff still checks authoritative bytes. There is no persistent cache, preference memory, or background learning.

CLI probes require Host support. Missing, unsupported, timed-out, or unreadable sources report partial evidence, never an invented empty installation inventory.

## Install and check locally

Python 3.11+ is required. Runtime dependencies are empty; tests use the standard library.

### Windows / PowerShell

```powershell
$skillRoot = Join-Path $HOME ".agents\skills\codex-capability-router"
if (Test-Path -LiteralPath $skillRoot) {
    if (-not (Test-Path -LiteralPath (Join-Path $skillRoot ".git"))) {
        throw "Target exists and is not a Git checkout: $skillRoot"
    }
    git -C $skillRoot pull --ff-only
} else {
    New-Item -ItemType Directory -Force -Path (Split-Path $skillRoot) | Out-Null
    git clone https://github.com/Lzxpan/codex-capability-router.git $skillRoot
}
if ($LASTEXITCODE -ne 0) { throw "Git update failed" }
Push-Location $skillRoot
try {
    python -m unittest discover -s tests -q
    if ($LASTEXITCODE -ne 0) { throw "Tests failed" }
    python -m compileall -q codex_capability_router tests
} finally {
    Pop-Location
}
```

### macOS / Linux

```bash
skill_root="${HOME}/.agents/skills/codex-capability-router"
if [ -e "$skill_root" ]; then
    [ -d "$skill_root/.git" ] || { printf '%s\n' "Target is not a Git checkout" >&2; exit 1; }
    git -C "$skill_root" pull --ff-only || exit 1
else
    mkdir -p "$(dirname "$skill_root")" || exit 1
    git clone https://github.com/Lzxpan/codex-capability-router.git "$skill_root" || exit 1
fi
(cd "$skill_root" && python -m unittest discover -s tests -q &&
 python -m compileall -q codex_capability_router tests)
```

Existing non-Git directories are not overwritten. Updating this source checkout does not update other global Skill copies.

## Validation and limits

See the [beta.10 validation record](docs/validation/v0.2.0-beta.10-validation.md). From the repository root:

```powershell
python -m unittest discover -s tests -q
python -m compileall -q codex_capability_router tests
git diff --check
```

Local tests cover deterministic contracts, temporary fixture discovery, bounded freshness recovery, Host response validation, and production `route()`. Automatic Host triggering, blind natural-language selection quality, complete App/MCP inventory, real Providers, production, hardware, and GitHub browser rendering remain `NOT VERIFIED`.

The Router does not perform network discovery, installation, OAuth, authorization, external mutation, deletion, publishing, or endpoint execution. `ExecutionAttempt` remains separate from the selection Receipt.

## Documentation

- [Traditional Chinese README](README.md)
- [Usage guide and historical v0.2 examples](docs/v0.2_user_guide.zh-TW.md)
- [Routing policy](references/routing-policy.md)
- [Discovery / provenance](references/discovery-and-provenance.md)
- [Changelog](CHANGELOG.md)
- [MIT License](LICENSE)
