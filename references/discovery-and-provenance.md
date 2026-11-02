# Discovery, provenance, and registry fields

Current contract: `v1.1.4`. Historical release scope lives in CHANGELOG.md
and explicitly marked historical documents, not in current selection gates.

## Trusted roots and bounded traversal

The controller builds a `RootPlanSnapshot` from fixed global roots
(`$HOME/.agents/skills`, `$CODEX_HOME/skills`), the managed root's known
`.system` child, known project roots, explicit runtime roots, and resolved
active Plugin manifest paths. The scanner reads a direct Skill or immediate
children; it never recursively walks unknown subtrees or a PluginStore ancestor.

For each resolved installed Plugin, manifest lookup checks the portable root,
then the Codex or Claude location. An unrelated root format does not displace
an existing Codex manifest; unsupported Agent Plugins schemas are rejected.
Portable and Claude manifests must match the Plugin identity; portable manifests
require the supported schema. A portable OpenAI extension replaces the Codex
overlay; otherwise the overlay can supply supported App and MCP declarations.
Portable Plugins use the standard `skills/` directory; unknown manifest fields
are reported and ignored. Claude Plugins use the standard `skills/` directory
alongside paths declared by `skills`. Layout roots are labeled separately from
declared paths and remain contained by the resolved Plugin root.

Test Skill documents are stored as `SKILL.fixture.md`, not discoverable entrypoints.
Compatibility tests materialize `SKILL.md` only in temporary directories outside
the installed Skill tree; packaged fixtures must not supply production handoffs.

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

The default `probe_cli()` timeout is two seconds. A live Plugin list can take
longer, so pass `timeout_seconds=90` when checking the current installation.
First complete the [installed runtime bootstrap](routing-policy.md#load-the-selected-installed-runtime)
in the same Python process, then run:

<!-- host-workflow:plugin-probe -->
```python
import json
import subprocess
from codex_capability_router.discovery import probe_cli

captured = []

def capture_cli(command, **kwargs):
    result = subprocess.run(command, **kwargs)
    captured.append(result)
    return result

plugin_probe = probe_cli(
    ("codex", "plugin", "list", "--json"), runner=capture_cli, timeout_seconds=90,
)
plugin_payload = None
plugin_rows = None
invalid_row_count = 0
if captured and captured[0].returncode == 0:
    try:
        parsed = json.loads(captured[0].stdout)
    except (TypeError, ValueError):
        parsed = None
    if isinstance(parsed, dict) and isinstance(parsed.get("installed"), list):
        plugin_payload = parsed
        plugin_rows = [row for row in parsed["installed"] if isinstance(row, dict)]
        invalid_row_count = len(parsed["installed"]) - len(plugin_rows)
```

The Host must inspect `plugin_probe.diagnostics` and handle a timeout or error as
partial evidence. `plugin_rows` is `None` when a raw list was not obtained; this
does not mean there are no installed Plugins. A nonzero `invalid_row_count` is
also partial evidence, even when valid rows remain. Pass those original valid
rows to `resolve_plugin_store_inventory()` with the verified PluginStore root;
retain and report its diagnostics or errors. Do not reconstruct rows from probe
records or exclude installed Plugins only because they are disabled. Enabled
state remains separate from presence and execution. Keep the raw payload in the
Host, not in a public Receipt.

## Public fields and privacy

Canonical IDs, names, kinds, status, descriptions, versions, provenance, conflicts,
and bounded evidence remain public contract metadata. Historical category,
trigger, priority, and overlap fields do not authorize keyword-based selection.
Localized Function metadata has an explicit unavailable fallback when absent.

Source labels are abstract. Do not emit private absolute paths, credentials,
tokens, raw private task inputs, or hidden reasoning. Inventory persistence and
Host/controller preference storage are outside this library's read-only scope.
