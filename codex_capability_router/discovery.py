"""Phase 2 bounded local skill discovery 與 manual inventory import。"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path
import subprocess

from .models import CapabilityKind, CapabilityRecord, DiscoveryDiagnostic, DiscoveryResult
from .validation import record_from_mapping, validate_source_label


# 修改紀錄（2026-08-17，Steve Peng）
# 原始內容：只有 explicit roots 與 manual inventory，沒有 runtime envelope 或 approved CLI probe。
# 修改原因：Phase 5R 要求 runtime authority 與 codex plugin/mcp JSON probe 的 bounded failure handling；beta review 另要求 malformed manual input 明確標示 partial。strict registry validation 也必須與 SKILL.md description metadata 解耦。
# 修改後功能：加入 runtime declaration、固定兩個 read-only CLI commands，失敗時回 partial/unknown，manual diagnostics 不再誤稱完整結果，且合法 SKILL.md 不會因 description 欄位被誤拒。


_APPROVED_CLI_PROBES = {
    ("codex", "plugin", "list", "--json"): (
        "cli:codex-plugin-list",
        "codex.plugin-list",
        CapabilityKind.PLUGIN,
    ),
    ("codex", "mcp", "list", "--json"): (
        "cli:codex-mcp-list",
        "codex.mcp-list",
        CapabilityKind.MCP,
    ),
}


def import_runtime_envelope(
    payload: Mapping[str, object],
    *,
    source_id: str = "runtime:envelope",
) -> DiscoveryResult:
    """匯入 caller 提供的 runtime capability declaration，保留 malformed entry 證據。"""

    try:
        source = validate_source_label(source_id)
    except ValueError:
        return DiscoveryResult(
            diagnostics=(DiscoveryDiagnostic("invalid_source", "runtime source label is invalid", "runtime"),),
            partial=True,
        )
    if not isinstance(payload, Mapping):
        return DiscoveryResult(
            diagnostics=(DiscoveryDiagnostic("malformed_runtime", "runtime envelope must be an object", source),),
            partial=True,
        )

    entries = payload.get("capabilities", payload.get("records", ()))
    if not isinstance(entries, Sequence) or isinstance(entries, (str, bytes)):
        return DiscoveryResult(
            diagnostics=(DiscoveryDiagnostic("malformed_runtime", "runtime capabilities must be an array", source),),
            partial=True,
        )

    records: list[CapabilityRecord] = []
    diagnostics: list[DiscoveryDiagnostic] = []
    for entry in entries:
        if not isinstance(entry, Mapping):
            diagnostics.append(DiscoveryDiagnostic("malformed_runtime", "runtime capability entry must be an object", source))
            continue
        try:
            records.append(record_from_mapping(entry, source=source))
        except ValueError:
            diagnostics.append(DiscoveryDiagnostic("malformed_runtime", "runtime capability entry is invalid", source))
    return DiscoveryResult(tuple(records), tuple(diagnostics), partial=bool(diagnostics))


def probe_cli(
    command: Sequence[str],
    *,
    runner=None,
    timeout_seconds: float = 2.0,
) -> DiscoveryResult:
    """執行唯一核准的 codex JSON read-only probe，拒絕任意 shell command。

    使用方式：測試可注入 runner；正式執行使用 subprocess.run(shell=False)。
    command、timeout 與 JSON schema 均有界；任何失敗都回 partial/unknown，不 crash。
    """

    command_tuple = tuple(command)
    probe = _APPROVED_CLI_PROBES.get(command_tuple)
    if probe is None:
        return DiscoveryResult(
            diagnostics=(DiscoveryDiagnostic("probe_not_allowed", "CLI probe is not approved", "cli"),),
            partial=True,
        )
    source, fallback_id, default_kind = probe
    invoke = runner or subprocess.run
    try:
        completed = invoke(
            list(command_tuple),
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            shell=False,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as error:
        return DiscoveryResult(
            records=(_unknown_probe_record(fallback_id, default_kind, source),),
            diagnostics=(DiscoveryDiagnostic("probe_failed", "CLI probe could not be completed", source),),
            partial=True,
        )
    if getattr(completed, "returncode", 1) != 0:
        return DiscoveryResult(
            records=(_unknown_probe_record(fallback_id, default_kind, source),),
            diagnostics=(DiscoveryDiagnostic("probe_failed", "CLI probe returned a non-zero exit code", source),),
            partial=True,
        )

    try:
        payload = json.loads(getattr(completed, "stdout", ""))
        entries = _probe_entries(payload)
    except (json.JSONDecodeError, ValueError, TypeError):
        return DiscoveryResult(
            records=(_unknown_probe_record(fallback_id, default_kind, source),),
            diagnostics=(DiscoveryDiagnostic("malformed_probe_json", "CLI probe JSON schema is invalid", source),),
            partial=True,
        )

    records: list[CapabilityRecord] = []
    diagnostics: list[DiscoveryDiagnostic] = []
    for entry in entries:
        try:
            records.append(record_from_mapping(entry, source=source, default_kind=default_kind))
        except ValueError:
            diagnostics.append(DiscoveryDiagnostic("malformed_probe_entry", "CLI capability entry is invalid", source))
    if not records:
        records.append(_unknown_probe_record(fallback_id, default_kind, source))
    return DiscoveryResult(tuple(records), tuple(diagnostics), partial=bool(diagnostics))


def probe_codex_capabilities(*, runner=None, timeout_seconds: float = 2.0) -> DiscoveryResult:
    """依序查詢 plugin/mcp JSON probes，合併 partial records 與 warning evidence。"""

    results = tuple(
        probe_cli(command, runner=runner, timeout_seconds=timeout_seconds)
        for command in _APPROVED_CLI_PROBES
    )
    return DiscoveryResult(
        records=tuple(record for result in results for record in result.records),
        diagnostics=tuple(diagnostic for result in results for diagnostic in result.diagnostics),
        partial=any(result.partial for result in results),
    )


def _probe_entries(payload: object) -> Sequence[Mapping[str, object]]:
    """接受 bounded list/capabilities/plugins/servers root，不對 schema 缺口做猜測。"""

    if isinstance(payload, list):
        entries = payload
    elif isinstance(payload, Mapping):
        entries = payload.get("capabilities", payload.get("plugins", payload.get("servers")))
    else:
        entries = None
    if not isinstance(entries, list) or not all(isinstance(entry, Mapping) for entry in entries):
        raise ValueError("unsupported probe JSON schema")
    return entries


def _unknown_probe_record(identifier: str, kind: CapabilityKind, source: str) -> CapabilityRecord:
    """建立失敗 probe 的 unknown record；不得將 command failure 推導為可用。"""

    return record_from_mapping(
        {
            "id": identifier,
            "name": identifier,
            "kind": kind.value,
            "status": "unknown",
            "categories": ["capability discovery"],
            "triggers": [],
            "priority": 0,
            "overlap_group": None,
            "preferred_for": [],
            "requires": [],
            "source": source,
            "last_verified": None,
            "confidence": 0.0,
            "evidence": ["probe failure; availability unknown"],
        }
    )


def discover_skill_roots(roots: Sequence[Path]) -> DiscoveryResult:
    """只掃描呼叫者明確傳入的 roots 及其直接子目錄。

    使用方式：傳入 repo-local 或其他 allowlisted skill roots；函式不會
    猜測 home、filesystem、credentials 或任何未傳入的目錄。
    """

    records: list[CapabilityRecord] = []
    diagnostics: list[DiscoveryDiagnostic] = []
    for root_index, root in enumerate(roots):
        source = f"skill-root:{root_index}"
        try:
            candidates = [root] if (root / "SKILL.md").is_file() else sorted(root.iterdir(), key=lambda path: (path.name.casefold(), path.name))
        except OSError:
            diagnostics.append(DiscoveryDiagnostic("unreadable_root", "skill root could not be read", source))
            continue

        for candidate in candidates:
            skill_file = candidate / "SKILL.md"
            if candidate.is_symlink() or not candidate.is_dir() or not skill_file.exists() or skill_file.is_symlink():
                continue
            record, diagnostic = _read_skill(candidate, source)
            if record is not None:
                records.append(record)
            if diagnostic is not None:
                diagnostics.append(diagnostic)

    records.sort(key=lambda record: (record.id.casefold(), record.id, record.source))
    diagnostics.sort(key=lambda diagnostic: (diagnostic.code, diagnostic.source, diagnostic.message))
    return DiscoveryResult(tuple(records), tuple(diagnostics))


def _read_skill(directory: Path, source: str) -> tuple[CapabilityRecord | None, DiscoveryDiagnostic | None]:
    """讀取單一明確 skill directory 的 allowlisted frontmatter。"""

    try:
        text = (directory / "SKILL.md").read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return None, DiscoveryDiagnostic("unreadable_skill", "skill metadata could not be read", source)

    metadata = _frontmatter(text)
    if metadata is None:
        return None, DiscoveryDiagnostic("malformed_skill", "skill metadata is malformed", source)
    # 修改紀錄（2026-08-19，Steve Peng）
    # 原始內容：discovery adapter 會移除 SKILL.md 的 description，且無法保留合法 multiline scalar。
    # 修改原因：Phase 5G-A 要讓合法 skill description 進入 Phase 5F 已支援的 canonical record。
    # 修改後功能：保留經 bounded parser 驗證的 description；未知結構仍由 record validation 拒絕。
    metadata.setdefault("kind", CapabilityKind.SKILL.value)
    metadata.setdefault("status", "unknown")
    try:
        return record_from_mapping(metadata, source=source, default_kind=CapabilityKind.SKILL), None
    except ValueError:
        return None, DiscoveryDiagnostic("malformed_skill", "skill metadata is invalid", source)


def _frontmatter(text: str) -> dict[str, object] | None:
    """解析不依賴第三方 YAML parser 的 bounded frontmatter subset。"""

    # ponytail: 只支援 repo/runtime 已出現的 scalar 與兩個 skill section；其他 YAML 結構維持 malformed，需求出現時再擴充。
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return None
    try:
        end = next(index for index, line in enumerate(lines[1:], start=1) if line.strip() == "---")
    except StopIteration:
        return None

    metadata: dict[str, object] = {}
    seen_keys: set[str] = set()
    index = 1
    while index < end:
        line = lines[index]
        if not line.strip():
            return None
        key, separator, value = line.partition(":")
        if not separator:
            return None
        normalized_key = key.strip()
        if not normalized_key or normalized_key in seen_keys:
            return None
        seen_keys.add(normalized_key)
        scalar = value.strip()
        if normalized_key in {"allowed-tools", "metadata"} and not scalar:
            index = _skip_ignored_frontmatter_section(lines, index + 1, end, normalized_key)
            if index is None:
                return None
            continue
        if scalar in {"|", ">"}:
            parsed, next_index = _frontmatter_block_scalar(lines, index + 1, end, scalar)
            if parsed is None:
                return None
            metadata[normalized_key] = parsed
            index = next_index
            continue
        metadata[normalized_key] = _frontmatter_value(scalar)
        index += 1
    if not metadata.get("name"):
        return None
    return metadata


def _frontmatter_block_scalar(
    lines: list[str],
    start: int,
    end: int,
    indicator: str,
) -> tuple[str | None, int]:
    """解析 `|` literal 或 `>` folded 的固定縮排 scalar，不猜測其他 YAML 規則。"""

    values: list[str] = []
    content_indent: int | None = None
    index = start
    while index < end:
        line = lines[index]
        if not line.strip():
            if content_indent is not None:
                values.append("")
            index += 1
            continue
        if line.startswith("\t"):
            return None, index
        indent = len(line) - len(line.lstrip(" "))
        if indent == 0:
            break
        if content_indent is None:
            content_indent = indent
        if indent < content_indent:
            return None, index
        values.append(line[content_indent:])
        index += 1

    if content_indent is None:
        return None, index
    while values and values[-1] == "":
        values.pop()
    if indicator == "|":
        return "\n".join(values), index

    folded: list[str] = []
    for value in values:
        if not folded or value == "":
            folded.append(value)
        elif folded[-1] == "":
            folded.append(value)
        else:
            folded[-1] += f" {value}"
    return "\n".join(folded), index


def _skip_ignored_frontmatter_section(
    lines: list[str],
    start: int,
    end: int,
    section: str,
) -> int | None:
    """驗證並略過目前 skill runtime 會使用、但不進 canonical record 的 section。"""

    content_indent: int | None = None
    index = start
    seen_keys: set[str] = set()
    while index < end:
        line = lines[index]
        if not line.strip():
            index += 1
            continue
        if line.startswith("\t"):
            return None
        indent = len(line) - len(line.lstrip(" "))
        if indent == 0:
            break
        if content_indent is None:
            content_indent = indent
        if indent < content_indent:
            return None
        content = line[content_indent:]
        if section == "allowed-tools":
            if not content.startswith("- ") or not content[2:].strip():
                return None
        else:
            nested_key, separator, nested_value = content.partition(":")
            normalized_key = nested_key.strip()
            if not separator or not normalized_key or normalized_key in seen_keys or not nested_value.strip():
                return None
            seen_keys.add(normalized_key)
        index += 1
    if content_indent is None:
        return None
    return index


def _frontmatter_value(value: str) -> object:
    """將 frontmatter 的簡單 scalar/list 轉為 validation 可接受型別。"""

    if value.startswith("[") and value.endswith("]"):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return value
        return parsed
    return value.strip().strip('"\'')


def import_manual_inventory(inventory: Mapping[str, object] | Path, *, source_id: str) -> DiscoveryResult:
    """匯入呼叫者提供的 machine-readable inventory，未提供 status 則保持 unknown。"""

    try:
        source = validate_source_label(source_id)
    except ValueError:
        return DiscoveryResult(
            diagnostics=(DiscoveryDiagnostic("invalid_source", "manual source label is invalid", "manual"),),
            partial=True,
        )

    try:
        payload = _load_inventory(inventory)
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError):
        return DiscoveryResult(
            diagnostics=(DiscoveryDiagnostic("malformed_inventory", "manual inventory could not be read", source),),
            partial=True,
        )

    entries = payload.get("capabilities")
    if not isinstance(entries, Sequence) or isinstance(entries, (str, bytes)):
        return DiscoveryResult(
            diagnostics=(DiscoveryDiagnostic("malformed_inventory", "manual inventory capabilities must be an array", source),),
            partial=True,
        )

    records: list[CapabilityRecord] = []
    diagnostics: list[DiscoveryDiagnostic] = []
    for entry in entries:
        if not isinstance(entry, Mapping):
            diagnostics.append(DiscoveryDiagnostic("malformed_inventory", "manual capability entry must be an object", source))
            continue
        try:
            records.append(record_from_mapping(entry, source=source))
        except ValueError:
            diagnostics.append(DiscoveryDiagnostic("malformed_inventory", "manual capability entry is invalid", source))

    records.sort(key=lambda record: (record.id.casefold(), record.id, record.source))
    diagnostics.sort(key=lambda diagnostic: (diagnostic.code, diagnostic.source, diagnostic.message))
    return DiscoveryResult(tuple(records), tuple(diagnostics), partial=bool(diagnostics))


def _load_inventory(inventory: Mapping[str, object] | Path) -> Mapping[str, object]:
    """讀取 mapping 或明確指定的 JSON file，不進行目錄搜尋。"""

    if isinstance(inventory, Path):
        parsed = json.loads(inventory.read_text(encoding="utf-8"))
    else:
        parsed = inventory
    if not isinstance(parsed, Mapping):
        raise ValueError("manual inventory must be an object")
    return parsed
