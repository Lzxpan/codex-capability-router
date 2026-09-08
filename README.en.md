# Codex Capability Router

**Find the right Skills and Tools for the task in front of you.**

[繁體中文](README.md) | English

![An otter Router guides a rabbit developer through many methods and tools while an owl checks the results.](docs/assets/v1.0.0/hero.png)

[![Version: 1.0.0](https://img.shields.io/badge/version-1.0.0-168C84)](https://github.com/Lzxpan/codex-capability-router/releases/tag/v1.0.0)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-3776AB)](pyproject.toml)
[![License: MIT](https://img.shields.io/badge/license-MIT-E6B13E)](LICENSE)

**Current version: `v1.0.0`, Stable.** Runtime behavior is unchanged from `v0.2.0-beta.10`; this release refreshes the project homepage, illustrated guides, and release validation.

You already have plenty of Skills and tools. But debugging firmware, explaining a project, creating images, and checking a release often need several capabilities working together.

**Codex Capability Router is a read-only Python library and Skill guide for Codex or another Host.** It organizes capabilities from trusted sources, presents candidates to the Host LLM, validates the resulting choices, hands off full instructions, and produces a traceable Receipt. The Host is the application running the model and actually operating tools.

## Start here

You need **Git, Python 3.11+**, and a Codex/Host that can read Skills. There are no Python runtime dependencies.

### Install

These commands are for a fresh installation. Git refuses to overwrite an existing target; inspect that installation before updating it.

**Windows PowerShell**

```powershell
$skillRoot = Join-Path $HOME ".agents/skills/codex-capability-router"
git clone --branch v1.0.0 --depth 1 https://github.com/Lzxpan/codex-capability-router.git $skillRoot
if ($LASTEXITCODE -ne 0) { throw "Installation failed" }
```

**macOS / Linux**

```bash
skill_root="${HOME}/.agents/skills/codex-capability-router"
git clone --branch v1.0.0 --depth 1 https://github.com/Lzxpan/codex-capability-router.git "$skill_root"
```

Reload the Host's Skill list, then use it in a prompt:

```text
$codex-capability-router
Analyze this task and find suitable Skills and Providers:
Improve my project README, create explanatory images,
and verify that the documentation matches the code.
```

**Read a Receipt by asking: what was selected, did every candidate receive a decision, and where is the actual execution evidence?**
`FINALIZED` means the selection record is frozen. Look separately at Host execution evidence to learn whether the work succeeded.

Installation supplies instruction-level integration. Automatic triggering, complete inventory, and actual Skill application depend on Host wiring; **automatic Host integration is not established in every environment**. Integrator APIs and examples are in the [current contract](references/routing-policy.md).

## Follow one task from confusion to evidence

The rabbit is the developer, the teal-vested otter is the Router guide, and the yellow-aproned owl represents tools and Verification. These characters illustrate the workflow; semantic decisions are made by the Host LLM.

![Comic part one: capability overload, task analysis, trusted discovery, and batch-by-batch Host decisions.](docs/assets/v1.0.0/story-a.png)

Follow the number in each panel: `1–4` on the first page, then `5–8` on the second. Each page reads top-left, top-right, bottom-left, bottom-right:

1. **Where do I start?** A developer wants to finish a project explanation but faces a desk overflowing with Skills and Tools.
2. **Understand the Task first.** The Host creates TaskAnalysis: work items, deliverables, constraints, and quality expectations.
3. **Open the trusted cabinets.** The Router discovers capabilities and organizes digest batches. Staging a candidate is not semantic consideration.
4. **Let the Host judge each batch.** The model decides which candidates could help. Related or overlapping methods can remain together.

![Comic part two: full instructions and coverage, a frozen selection record, actual work, then verification and separate execution evidence.](docs/assets/v1.0.0/story-b.png)

5. **Read the methods and cover gaps.** Full Skill handoff and one bounded Skill Coverage Check precede Host Execution Needs. Providers are considered only when needed.
6. **Freeze the plan first.** Python validates `route()` inputs and produces a `FINALIZED` Receipt. The sealed folder records the selection, not a successful result.
7. **Do the work.** The Host applies methods and invokes tools under its existing authorization to produce documents, images, or code.
8. **Inspect what happened.** Verification checks real outputs. A separate `ExecutionAttempt` records the execution outcome alongside the selection Receipt.

## Four principles

![Four-panel feature comic: discover trusted sources, consider varied metadata, retain multiple useful methods, and execute with permission and checks.](docs/assets/v1.0.0/principles.png)

| Principle | What it means in practice |
| --- | --- |
| **1. DISCOVER BROADLY** | Discover capabilities from explicitly trusted roots and Host metadata, preserving provenance. Do not scan the entire disk. |
| **2. CONSIDER BROADLY** | Stage present, identity-resolved candidates. `SPARSE` and `OPAQUE` metadata can remain; staged != semantically considered. |
| **3. SELECT GENEROUSLY** | No fixed top-k and no fixed Skill maximum. Overlap / redundancy is not an automatic exclusion reason. Plausible task-relevant value is enough. |
| **4. EXECUTE CAREFULLY** | Selection is not authorization, callability, or success. The Host still enforces permissions, connectivity, deletion, sending, and publication boundaries. |

## Skills, Providers, and Plugins

| Name | Think of it as |
| --- | --- |
| **Skill** | A method book: how to debug, write, review, or verify. The Host reads the full instructions and applies them. |
| **Provider** | A source of execution capability: `app`, `mcp`, `builtin_tool`, or `host_tool`. Presence and readiness are recorded separately. |
| **Plugin** | A package and provenance container for Skills, Apps, or MCP. **A Plugin is not a Provider.** |
| **Host LLM** | The decision maker that understands the task, judges relevance, and identifies Execution Needs. |
| **Python Router** | Deterministic discovery, validation, fingerprints, handoff, and evidence. It does not make semantic decisions for the model. |

A tool with unknown Host hierarchy remains `host_tool`; it is not guessed to be an App or MCP. Installed, selected, authorized, invoked, and successful are different states.

## What this looks like at work

### Firmware debugging / implementation
“The panel light stays on after water dispensing stops.” The Host can combine firmware analysis, state-machine investigation, and regression methods, then select file, build, or log tools. The Receipt explains the choices; passing source tests does not prove flashing or hardware acceptance.

### Documentation, READMEs, and images
“Help a new reader understand this project.” The Host can retain technical writing, visual storytelling, image generation, and bilingual checking methods together, then use image or diagram tools. The output still needs image inspection, working links, and factual checks.

### Tests, code review, and verification
“Can we release this version?” The Host can combine review, testing, and release-check methods, connecting observed results to requirements. Missing evidence stays visible rather than being treated as a passing test because selection completed.

## Architecture: who decides, who validates?

![1.0.0 flow: the Host makes semantic decisions, Python organizes and validates evidence, and Host execution with a separate ExecutionAttempt follows the Receipt.](docs/assets/v1.0.0/architecture.svg)

Coral means **Host LLM = semantic decisions**; teal means **Python Router = deterministic validation / evidence**. Yellow records separate selection from execution.

The flow is TaskAnalysis → trusted discovery → digest batches → Host Skill decisions → Skill handoff / Coverage Check → Execution Needs → Provider decisions → `route()` → FINALIZED Receipt → Host execution → ExecutionAttempt. Empty Execution Needs skip the Provider path; at most one Supporting Coverage Check is allowed.

The version-controlled [Mermaid source](docs/assets/v1.0.0/architecture.mmd) and [SVG](docs/assets/v1.0.0/architecture.svg) ship in the repository. Reading them does not require a Figma account.

## How to read a Receipt

| Field / state | What it establishes |
| --- | --- |
| `STAGED` | Candidates placed into batches. |
| `DECISION_RECEIVED` | Candidates with a received, validated Host disposition. |
| `SEMANTICALLY_CONSIDERED` | Candidates resolved as `selected` or `not_selected`. |
| `NEVER_CONSIDERED` | Candidates with no Host response. |
| `UNRESOLVED` | Missing responses plus candidates still marked `needs_detail`. |
| `COMPLETE` / `PARTIAL` | Whether all supplied candidates have resolved decisions. This is not universal discovery coverage or model accuracy. |
| `FINALIZED` | A validated, frozen selection Receipt. Coverage may still be `PARTIAL`. **FINALIZED != execution success.** |
| `ExecutionAttempt` | A separate Host execution record; it cannot be inferred from the Receipt. |

A batch with no response remains `PARTIAL`; do not substitute staged count for considered count. Host batch decisions bind task and sweep fingerprints plus batch index. Missing whole batches remain PARTIAL; missing items within a response or contradictory choices are rejected.

## Safety boundaries and limitations

- **Read-only Router.** It does not execute tools, install capabilities, perform network discovery, or authorize the Host. It should not emit private capability inventory, credentials, private paths, or hidden reasoning.
- **Trusted sources only.** Explicit roots, the bounded `.system` child, resolved active Plugin paths, and trusted Host snapshots. No unbounded recursive scanning.
- **One targeted Skill freshness recovery.** Handoff checks the selected authoritative source. At most one refresh; changed public metadata or identity requires `SELECTION_REVALIDATION_REQUIRED`. A further mismatch returns `HANDOFF_REJECTION_AFTER_ONE_REFRESH`.
- **caller/session-owned cache.** The caller owns `RootPlanSnapshot` and `SkillInventorySnapshot` lifetimes. The Router provides no persistent preference learning or background learning of user preferences.
- **Host integration has limits.** Presence does not guarantee readiness. Complete inventory, semantic accuracy, real Provider execution, and hardware outcomes require their own evidence.

## Maintenance and verification

```bash
python -m unittest discover -s tests -q
python -m compileall -q codex_capability_router tests
python scripts/verify_release.py
```

Use `python3` instead of `python` where that is your macOS/Linux interpreter command.

The current behavior baseline is beta.10. Historical `0.1.0` compatibility and beta records remain available; legacy fields do not replace the current selection contract.

[CHANGELOG](CHANGELOG.md) · [Stable validation guide](docs/validation/v1.0.0-validation.md) · [Release notes](docs/releases/v1.0.0.md) · [Discovery](references/discovery-and-provenance.md) · [Routing contract](references/routing-policy.md) · [MIT License](LICENSE)
