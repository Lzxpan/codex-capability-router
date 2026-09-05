# Discovery, provenance, and registry fields

Current contract: `v0.2.0-beta.10`. Historical release scope lives in CHANGELOG.md
and explicitly marked historical documents, not in current selection gates.

## Trusted roots and bounded traversal

The controller builds a `RootPlanSnapshot` from fixed global roots
(`$HOME/.agents/skills`, `$CODEX_HOME/skills`), the managed root's known
`.system` child, known project roots, explicit runtime roots, and resolved
active Plugin manifest paths. The scanner reads a direct Skill or immediate
children; it never recursively walks unknown subtrees or a PluginStore ancestor.

Compression removes a child only when the parent's actual traversal covers its
declared scope. A direct immediate child may be covered by a container; nested
containers and deeper direct Skills remain explicit roots. Distinct Plugin
identities are not collapsed across ancestors. Known `.system` traversal is
bounded and does not authorize arbitrary hidden directories.

A missing/unreadable root emits its own `unreadable_root` diagnostic and does
not erase readable sources. Permission-error fixtures prove exception handling;
they are not Windows ACL or hardware acceptance.

## Sources and identity

Runtime and supported read-only CLI evidence, trusted filesystem roots, Plugin
declarations, and caller-provided descriptive inventory retain provenance.
Same-identity conflicts are diagnostic; physical-source binding for a canonical
Skill is deterministic. Profile and handoff bind the same selected source.

Metadata quality is diagnostic. `SUFFICIENT`, `SPARSE`, and `OPAQUE` are
staged when existence and identity are resolved. Unknown existence is diagnostic,
not an inferred installation. Presence does not imply callability, authorization,
connection, or execution success.

Inventory and context preparation do not receive LLM decisions. Their semantic
decision counts start at zero; stage counts and Host batch evidence are separate.
See [routing policy](routing-policy.md) for the current receipt contract.

## Host capability snapshot

Only a controller-owned envelope normalized into `HostCapabilitySnapshot` is
accepted by the typed channel. The trust marker is not cryptographic origin proof.
Public namespace, action, display metadata, hierarchy, parent identity, provenance,
and exposure hints are sufficient; no secret or raw arguments belong here.

`host_native` entries map to `builtin_tool`; explicit App/MCP children group
under their formal Provider. Unknown hierarchy remains `host_tool` with
`hierarchy_state=UNKNOWN`. Plugin is a provenance container.

## CLI compatibility

The existing fixed probe allowlist contains `codex plugin list --json` and
`codex mcp list --json`. Allowlisting is not evidence that the installed Host
supports a command. Verify support before choosing a probe.

Missing commands, unsupported subcommands, nonzero exits, timeout, malformed JSON,
and schema failures remain partial diagnostics. They never mean an empty installed
inventory. Probes use fixed arguments, `shell=False`, bounded time and parsing;
no arbitrary shell, marketplace lookup, credentials, or auth probing is allowed
inside Router discovery.

## Public fields and privacy

Canonical IDs, names, kinds, status, descriptions, versions, provenance, conflicts,
and bounded evidence remain public contract metadata. Historical category,
trigger, priority, and overlap fields do not authorize keyword-based selection.
Localized Function metadata has an explicit unavailable fallback when absent.

Source labels are abstract. Do not emit private absolute paths, credentials,
tokens, raw private task inputs, or hidden reasoning. Inventory persistence and
Host/controller preference storage are outside this library's read-only scope.
