# Codex Capability Router

Current version: <code>0.2.0-beta.1</code>

Compatibility baseline: <code>0.1.0</code>; Phase 1 remains read-only, performs no network discovery, and does not expose a private capability inventory.

[繁體中文](README.md) | English

![Codex Capability Router hero](docs/assets/readme/router-hero.svg)

> Let Codex understand the work first, then find the Skills and Supporting Providers the task actually needs.

![Codex Capability Router mascot](docs/assets/readme/router-mascot.svg)

Codex Capability Router is a **local-first, context-first, read-only** capability router. It is not another execution Agent and does not execute capabilities on Codex's behalf. It turns a complete request into an auditable TaskAnalysis, lets Codex judge method Skills and currently callable Supporting Providers, and produces a Receipt that execution failures cannot silently rewrite.

## What it does

The Router has one focused job:

~~~text
Task understanding
→ Capability discovery
→ Skill selection
→ Supporting Provider selection
→ auditable Receipt
~~~

Python handles schema, canonical identity, readiness, fingerprints, privacy, and lifecycle validation only. Codex makes the semantic decisions; the Router does not use keyword-to-ID mapping or hide a second semantic selector in Python.

## Core capabilities

| Area | Current support |
| --- | --- |
| Task and Skills | <code>TaskAnalysis</code>, trusted-root Skill discovery, coverage-first selection, at most one bounded Coverage Check, material and non-redundant selection, and full Skill handoff |
| Supporting Providers | lazy <code>Execution Needs</code>, formal <code>App</code>, <code>MCP</code>, and <code>builtin_tool</code> kinds, <code>PRESENT_UNVERIFIED</code> optimistic selection, explicit-negative exclusion, and a capability metadata gate |
| Audit and safety | immutable <code>FINALIZED</code> Receipt, <code>ExecutionAttempt</code> audit, Plugin package and provenance boundary, privacy validation, content fingerprints, and deterministic validation |

### Coverage-first Skill selection

![Skill coverage comic](docs/assets/readme/feature-skill-coverage.svg)

The Router reads the whole task first, then finds useful, non-overlapping methods in the live candidate set. Selecting fewer Skills is fine when every material work item is covered. Coverage Check is one bounded correction, not an invitation to expand the candidate list forever.

### Provider readiness and optimistic selection

![Provider selection comic](docs/assets/readme/feature-provider-selection.svg)

A Provider can enter semantic selection only when its instance is present and its capability metadata is sufficient. <code>PRESENT_UNVERIFIED</code> remains selectable; <code>KNOWN_UNAVAILABLE</code>, explicit negatives, insufficient metadata, and uncertified instances are excluded before selection.

### Safe execution and Receipt

![Safe execution and Receipt](docs/assets/readme/feature-safe-execution.svg)

<code>route(SelectionRouteInput(...))</code> creates a <code>FINALIZED</code> Receipt. The Receipt records the original selection, supports, readiness, and execution needs. A later execution attempt is an independent audit outcome; it does not rewrite the original selection.

## How it works

![Router workflow diagram](docs/assets/readme/router-flow.svg)

Keep the two boundaries separate: a Skill tells Codex how to do the work, while a Supporting Provider represents what the Host can execute now. <code>route()</code> accepts only inputs that pass trust, handoff, metadata, fingerprint, and lifecycle gates; it does not call a Provider endpoint itself.

## Skill, Provider, and Plugin

| Term | Responsibility | Formal selection? |
| --- | --- | --- |
| Skill | Provides methods, constraints, and a full handoff that tell Codex how to do the work. | Yes, as a method Skill |
| Supporting Provider | Provides a runtime capability callable by the current Host. | Yes, only as <code>app</code>, <code>mcp</code>, or <code>builtin_tool</code> |
| Plugin | Holds package and provenance boundaries and may expose an App or MCP server. | No, a Plugin is never a formal Provider |

## Provider readiness

| State | Meaning | Selection |
| --- | --- | --- |
| <code>VERIFIED_READY</code> | Stronger runtime evidence, exact identity, and a callable surface are present. | selectable |
| <code>PRESENT_UNVERIFIED</code> | The instance exists and capability metadata is sufficient, but readiness is not fully verified. | selectable |
| <code>KNOWN_UNAVAILABLE</code> | The capability is known to be unusable or has passed an explicit negative gate. | excluded |

<code>selected</code> ≠ <code>guaranteed executable</code>. A production route preserves the readiness state; actual execution still depends on Host permission, authorization, connection, policy, and safety.

## Installation

This repository is itself a Codex Skill source tree. Skill discovery requires <code>SKILL.md</code> in the target directory; there are no additional Python dependencies and no installer. Python 3.11 or newer is needed only for tests and local verification.

### Windows / PowerShell

Step 1: verify Git.

~~~powershell
git --version
~~~

Step 2: create or confirm the Skills directory.

~~~powershell
$skillRoot = Join-Path $env:USERPROFILE ".agents\skills"
$skillPath = Join-Path $skillRoot "codex-capability-router"
New-Item -ItemType Directory -Force -Path $skillRoot | Out-Null
~~~

Step 3: clone into the correct Skill path, or update an existing clone with fast-forward only.

~~~powershell
if (Test-Path (Join-Path $skillPath ".git")) {
    git -C $skillPath pull --ff-only
} else {
    git clone https://github.com/Lzxpan/codex-capability-router.git $skillPath
}
~~~

Step 4: confirm that <code>SKILL.md</code> exists.

~~~powershell
Test-Path (Join-Path $skillPath "SKILL.md")
~~~

Step 5: if the current Codex session has already loaded an older Skill inventory, open a new appropriate session so the updated Skill can be discovered.

Step 6: run the minimum verification from the repository checkout.

~~~powershell
python -m unittest discover -s tests -p "test_*.py"
python -m compileall -q codex_capability_router tests
~~~

### macOS / Linux

Step 1: verify Git.

~~~bash
git --version
~~~

Steps 2–3: create the Skills directory, then clone or fast-forward update.

~~~bash
skill_root="\${HOME}/.agents/skills"
skill_path="\${skill_root}/codex-capability-router"
mkdir -p "$skill_root"
if [ -d "$skill_path/.git" ]; then
  git -C "$skill_path" pull --ff-only
else
  git clone https://github.com/Lzxpan/codex-capability-router.git "$skill_path"
fi
~~~

Step 4: confirm that <code>SKILL.md</code> exists.

~~~bash
test -f "$skill_path/SKILL.md"
~~~

Step 5: if the Codex session has cached an older inventory, open a new session.

Step 6: run the minimum verification.

~~~bash
python3 -m unittest discover -s tests -p 'test_*.py'
python3 -m compileall -q codex_capability_router tests
~~~

## Updating

From the cloned Skill repository, use:

~~~bash
git pull --ff-only
~~~

Do not overwrite an existing Skill directory by hand. If the directory is not a Git clone, keep it intact and confirm the installation scope separately.

## Quick Start

Give Codex a natural-language task and let the Router decide from the task and trusted inventory. The examples do not name a Skill ID or Provider ID.

### A. A simple task

~~~text
Read the configuration files in this repository, summarize the three most important constraints, and do not edit anything yet.
~~~

The Router should keep the smallest sufficient explanation or inspection coverage rather than adding capabilities just to increase the count.

### B. A complex engineering task

~~~text
Trace the input validation, error paths, and tests for a parser. Write a Traditional Chinese technical explanation and label which conclusions are supported only by source code.
~~~

The Router may select complementary code explanation, verification, and technical writing methods; overlapping Skills should not all be selected.

### C. A task that needs external execution capability

~~~text
Check the current repository test and compilation state. If the task needs a Host runtime, list the capabilities that are actually present and their readiness before running the required read-only checks.
~~~

The Router creates <code>Execution Needs</code> first, then lets Codex choose among formal App, MCP, and builtin tool candidates. One Provider does not guarantee that the entire task is covered.

## Receipt example

This is a sanitized example, not the raw output of a user task:

~~~json
{
  "task_summary": "Explain and verify a bounded repository change",
  "selected_skills": ["documentation-method", "verification-method"],
  "supporting_providers": [
    {"kind": "builtin_tool", "readiness": "VERIFIED_READY"}
  ],
  "status": "FINALIZED",
  "fingerprint": "sha256:0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
}
~~~

The Receipt contains no private paths, credentials, hidden prompts, or chain-of-thought. A production output retains provenance, supports, readiness, and the necessary audit fields.

## Safety / Design boundaries

- No Python semantic routing; Python performs deterministic validation only.
- No keyword-to-ID mapping, silent fallback, or fixed Skill count.
- A Plugin is a package and provenance container, not a formal Provider.
- Formal Provider kinds are <code>app</code>, <code>mcp</code>, and <code>builtin_tool</code>; a raw tool endpoint cannot bypass that boundary.
- Execution still requires normal permission, authorization, connection, policy, and safety controls.
- A <code>FINALIZED</code> selection is not silently rewritten after execution failure; a new decision requires a new route.

## Current limitations

- The Optimistic Provider Core is covered by deterministic regression tests, including the <code>PRESENT_UNVERIFIED</code> selectable path and explicit-negative exclusion.
- The installed smoke path and the <code>builtin_tool</code> <code>functions.exec_command</code> <code>VERIFIED_READY</code> positive path are verified; this README acceptance also used the production <code>route()</code> to create a Receipt.
- This Host did not expose a connectable official App Server surface, so official App/MCP live acceptance remains Host-surface blocked. App adapters, MCP adapters, and readiness contracts are tested, but this project does not claim that every App or MCP was live tested.
- The repository does not execute Provider endpoints or automatically install, log in, authorize, or manage Plugins and Skills. Actual execution results must be recorded separately as <code>ExecutionAttempt</code> data.
- The six README visuals are original SVG files stored in the repository; no external images, stock art, watermark, or external asset loading is used.

## Tests

Current repository regression: **165/165 PASS**.

~~~bash
python -m unittest discover -s tests -p "test_*.py"
python -m compileall -q codex_capability_router tests
~~~

The suite covers TaskAnalysis, trusted-root discovery, Skill coverage, optimistic Provider readiness, official adapter gates, the Plugin boundary, Receipt finalization, and the execution outcome contract. The latest output from running the commands above is the source of truth.

## Related documents

- [Skill contract](SKILL.md)
- [Traditional Chinese v0.2 user guide](docs/v0.2_user_guide.zh-TW.md)
- [License](LICENSE)

## License

MIT; see [LICENSE](LICENSE).
