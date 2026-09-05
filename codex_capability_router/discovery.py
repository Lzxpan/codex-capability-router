"""Phase 2 bounded local skill discovery 與 manual inventory import。"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
import re
import subprocess

from .models import CapabilityKind, CapabilityRecord, DiscoveryDiagnostic, DiscoveryResult
from .skill_plan import (
    ROOT_KIND_PLUGIN_DECLARED,
    RootPlanSnapshot,
    SkillRootSpec,
    TRAVERSAL_DIRECT_SKILL,
    TRAVERSAL_KNOWN_SYSTEM,
    TRAVERSAL_PLUGIN_CONTAINER,
    build_skill_root_plan,
)
from .supporting_context import canonicalize_external_identity
from .validation import record_from_mapping, validate_source_label


# 修改紀錄（2026-09-02，Steve Peng）
# 原始內容：CLI probe 只接受舊式 plugins/servers root，無法解析現行 Codex JSON。
# 修改原因：beta.3 live discovery 必須以目前 command output 的最小 identity schema 建立存在證據。
# 修改後功能：支援 plugin `installed` envelope 與 MCP list array；未知 optional 欄位忽略，缺少 identity 僅留下 entry diagnostic。
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

_LEGACY_METADATA_SCALAR_KEYS = frozenset(
    {
        "short-description",
        "source_repo",
        "source_path",
        "compatibility_note",
        "source_tools",
        "trigger",
        "source",
    }
)
_SENSITIVE_METADATA_KEYS = frozenset(
    {"api_key", "apikey", "credential", "credentials", "password", "secret", "token"}
)
_METADATA_KEY = re.compile(r"^[A-Za-z][A-Za-z0-9_.-]*$")
_CANONICAL_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]*$")
_SENSITIVE_METADATA_TEXT = re.compile(
    r"(?:api[_-]?key|password|secret|token|credential)\s*[:=]",
    re.IGNORECASE,
)
_RECORD_FRONTMATTER_FIELDS = frozenset(
    {
        "id",
        "name",
        "description",
        "kind",
        "status",
        "categories",
        "triggers",
        "priority",
        "overlap_group",
        "preferred_for",
        "requires",
        "source",
        "last_verified",
        "version",
        "limitations",
        "provenance",
        "confidence",
        "conflicts",
        "evidence",
        "recommendation_only",
        "function",
        "controller",
        "aliases",
        "routing_support",
        "provides",
    }
)


@dataclass(frozen=True)
class DiscoveryRootPlan:
    """描述一組由 caller 明確授權的 bounded filesystem discovery roots。"""

    roots: tuple[Path, ...]
    source_kind: str = "TRUSTED_RUNTIME_DECLARED_ROOT"
    authority: str = "caller-declared"
    scan_policy: str = "immediate-skill-directories"
    max_depth: int = 1
    provenance: str = "caller"

    def __post_init__(self) -> None:
        """拒絕無界 traversal 設定，並固定 root 順序與型別。"""

        roots = tuple(Path(root) for root in self.roots)
        if self.max_depth != 1:
            raise ValueError("skill discovery root plan permits only immediate-child traversal")
        if not self.source_kind.strip() or not self.authority.strip() or not self.provenance.strip():
            raise ValueError("discovery root plan metadata is required")
        object.__setattr__(self, "roots", roots)

    @classmethod
    def from_roots(
        cls,
        roots: Sequence[Path],
        *,
        source_kind: str = "TRUSTED_RUNTIME_DECLARED_ROOT",
        authority: str = "caller-declared",
        provenance: str = "caller",
    ) -> "DiscoveryRootPlan":
        """將 caller 明確提供的 roots 包成一層 traversal plan。"""

        if isinstance(roots, (str, bytes)) or not isinstance(roots, Sequence):
            raise ValueError("discovery roots must be a sequence")
        return cls(tuple(Path(root) for root in roots), source_kind, authority, "immediate-skill-directories", 1, provenance)


# 修改紀錄（2026-08-26，Steve Peng）
# 原始內容：legacy metadata 只要出現 metadata section 就被當成 malformed，導致真實 explain-code 無法 discovery。
# 修改原因：Phase 1 需要 bounded compatibility normalization，支援安全 legacy scalar、allowed-tools 與唯一一層 source_frontmatter，且不能把舊 metadata 推導成 routing/availability 語意。
# 修改後功能：先嚴格驗證有限 legacy 結構，再丟棄 compatibility-only metadata；未知 nested、深層結構、敏感值與 malformed input 仍拒絕。

# 修改紀錄（2026-08-25，Steve Peng）：缺少 machine-readable id 時使用明確 entry 名稱；display name 僅供人類顯示。


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
        entries = _probe_entries(payload, default_kind=default_kind)
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


def _probe_entries(
    payload: object,
    *,
    default_kind: CapabilityKind = CapabilityKind.UNKNOWN,
) -> Sequence[Mapping[str, object]]:
    """解析現行與 legacy CLI root，只抽取存在所需的最小 public identity。

    `codex plugin list --json` 的 `available` 是 marketplace inventory，不是已
    存在的 runtime package；只有 `installed` 可進本次 Plugin existence source。
    `codex mcp list --json` 的 server array 同樣只取 `name`，readiness 欄位不作
    selection gate。
    """

    if default_kind == CapabilityKind.PLUGIN and isinstance(payload, Mapping) and "installed" in payload:
        raw_entries = payload.get("installed")
        if not isinstance(raw_entries, list):
            raise ValueError("plugin installed root must be an array")
        entries: list[Mapping[str, object]] = []
        for item in raw_entries:
            if not isinstance(item, Mapping):
                entries.append({"id": "", "name": ""})
                continue
            raw_identity = item.get("pluginId", item.get("id"))
            if not isinstance(raw_identity, str) or not raw_identity.strip():
                entries.append({"id": "", "name": ""})
                continue
            internal_id = canonicalize_external_identity(raw_identity, "plugin")
            display_name = item.get("name")
            if not isinstance(display_name, str) or not display_name.strip():
                display_name = internal_id
            entries.append(
                {
                    "id": internal_id,
                    "name": display_name,
                    "kind": CapabilityKind.PLUGIN.value,
                    "status": "unknown",
                    "evidence": ["installed plugin entity"],
                }
            )
        return entries
    if default_kind == CapabilityKind.MCP and isinstance(payload, list) and all(
        isinstance(item, Mapping) and ("auth_status" in item or "transport" in item)
        for item in payload
    ):
        entries = []
        for item in payload:
            assert isinstance(item, Mapping)
            identity = item.get("name")
            if not isinstance(identity, str) or not identity.strip():
                entries.append({"id": "", "name": ""})
                continue
            entries.append(
                {
                    "id": identity.strip(),
                    "name": identity.strip(),
                    "kind": CapabilityKind.MCP.value,
                    "status": "unknown",
                    "evidence": ["configured MCP server entity"],
                }
            )
        return entries
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


def discover_skill_roots(
    roots: Sequence[Path] | DiscoveryRootPlan | RootPlanSnapshot,
    *,
    source_prefix: str = "skill-root",
) -> DiscoveryResult:
    """只掃描呼叫者明確傳入的 roots 及其直接子目錄。

    使用方式：傳入 repo-local 或其他 allowlisted skill roots；函式不會
    猜測 home、filesystem、credentials 或任何未傳入的目錄。
    """

    if isinstance(roots, RootPlanSnapshot):
        return _discover_skill_root_specs(roots.roots, source_prefix=source_prefix)
    plan = roots if isinstance(roots, DiscoveryRootPlan) else DiscoveryRootPlan.from_roots(roots)
    specs = tuple(
        SkillRootSpec(
            root,
            "CALLER_DECLARED_SKILL_ROOT",
            "TRUSTED_RUNTIME_DECLARED_ROOT",
            provenance=("caller",),
        )
        for root in plan.roots
    )
    return _discover_skill_root_specs(specs, source_prefix=source_prefix)


def _discover_skill_root_specs(
    specs: Sequence[SkillRootSpec],
    *,
    source_prefix: str,
) -> DiscoveryResult:
    """依已建立的 root plan 做 bounded immediate/known-child Skill discovery。"""

    records: list[CapabilityRecord] = []
    diagnostics: list[DiscoveryDiagnostic] = []
    metrics = {
        "filesystem_root_count": len(specs),
        "filesystem_directory_entries_visited": 0,
        "skill_files_opened": 0,
        "unreferenced_paths_skipped": 0,
        "whole_disk_scan_attempted": 0,
    }
    for root_index, spec in enumerate(specs):
        root = spec.path
        source = _skill_source_label(spec, source_prefix, root_index)
        candidates: list[Path] = []
        try:
            candidates.extend(_skill_candidates(spec))
            metrics["filesystem_directory_entries_visited"] += _candidate_entry_count(spec, candidates)
        except OSError:
            diagnostics.append(DiscoveryDiagnostic("unreadable_root", "skill root could not be read", source))
            continue

        for candidate in candidates:
            source = _skill_source_label(spec, source_prefix, root_index, candidate)
            skill_file = candidate / "SKILL.md"
            if candidate.is_symlink() or not candidate.is_dir() or not skill_file.exists() or skill_file.is_symlink():
                metrics["unreferenced_paths_skipped"] += 1
                continue
            metrics["skill_files_opened"] += 1
            record, diagnostic = _read_skill(candidate, source)
            if record is not None:
                records.append(record)
            if diagnostic is not None:
                diagnostics.append(diagnostic)

    records.sort(key=lambda record: (record.id.casefold(), record.id, record.source))
    diagnostics.sort(key=lambda diagnostic: (diagnostic.code, diagnostic.source, diagnostic.message))
    return DiscoveryResult(
        tuple(records),
        tuple(diagnostics),
        discovery_metrics=tuple(sorted(metrics.items())),
    )


def _skill_source_label(
    spec: SkillRootSpec,
    source_prefix: str,
    index: int,
    candidate: Path | None = None,
) -> str:
    """維持既有 inventory source prefix，同時保留 root scope/provenance 線索。"""

    if spec.root_kind == ROOT_KIND_PLUGIN_DECLARED:
        return f"plugin-skill-root:{spec.plugin_identity or index}"
    if spec.scope == "system" or (
        spec.traversal_mode == TRAVERSAL_KNOWN_SYSTEM
        and candidate is not None
        and any(
            candidate == spec.path / child or spec.path / child in candidate.parents
            for child in spec.known_children
        )
    ):
        return "skill-root:system"
    return f"{source_prefix}:{index}"


def _skill_candidates(spec: SkillRootSpec) -> tuple[Path, ...]:
    """只產生 root 自身或一層 legitimate child，絕不遞迴未知目錄。"""

    root = spec.path
    if spec.traversal_mode == TRAVERSAL_DIRECT_SKILL:
        return (root,) if (root / "SKILL.md").is_file() else ()
    candidates = list(_immediate_skill_candidates(root))
    if spec.traversal_mode == TRAVERSAL_KNOWN_SYSTEM:
        # 只支援官方明確合法的 .system child，不把所有 dot-directory 變成合法來源。
        for child_name in spec.known_children:
            child_root = root / child_name
            try:
                candidates.extend(_immediate_skill_candidates(child_root))
            except OSError:
                # 合法 known child 尚未建立時，不影響 parent root 的 normal Skills。
                continue
    return tuple(candidates)


def _immediate_skill_candidates(root: Path) -> tuple[Path, ...]:
    """讀取一個已授權 root 的自身或 immediate child。"""

    if (root / "SKILL.md").is_file():
        return (root,)
    return tuple(sorted(root.iterdir(), key=lambda path: (path.name.casefold(), path.name)))


def _candidate_entry_count(spec: SkillRootSpec, candidates: Sequence[Path]) -> int:
    """回報實際訪問的 directory entries；known child 只算其 bounded entries。"""

    count = len(candidates)
    if spec.traversal_mode == TRAVERSAL_KNOWN_SYSTEM:
        # parent listing 中的 .system 仍是一次 entry；其 children 已包含在 candidates。
        count += len(spec.known_children)
    return count


def discover_plugin_skill_root_specs(
    manifests: Sequence[Mapping[str, object]],
) -> tuple[SkillRootSpec, ...]:
    """把 Plugin manifest declared Skill paths 建成 root node，不展開 child Skills。"""

    if isinstance(manifests, (str, bytes)) or not isinstance(manifests, Sequence):
        raise ValueError("plugin manifests must be a sequence")
    specs: list[SkillRootSpec] = []
    for manifest in manifests:
        if not isinstance(manifest, Mapping):
            raise ValueError("plugin manifests must contain mappings")
        plugin_id = manifest.get("plugin_id", manifest.get("id"))
        if not isinstance(plugin_id, str) or not plugin_id.strip():
            raise ValueError("plugin manifest requires a plugin identity")
        if not _plugin_entity_present(manifest):
            continue
        package_root = _plugin_package_root(manifest)
        if package_root is None:
            continue
        for raw_path in _plugin_declared_skill_paths(manifest):
            if not _plugin_path_is_contained(package_root, raw_path):
                continue
            assert isinstance(raw_path, (str, Path))
            path = Path(raw_path)
            if not path.is_absolute():
                path = package_root / path
            path = path.resolve()
            if path.name.casefold() == "skill.md":
                skill_root = path.parent
                mode = TRAVERSAL_DIRECT_SKILL
            elif (path / "SKILL.md").is_file():
                skill_root = path
                mode = TRAVERSAL_DIRECT_SKILL
            elif path.is_dir():
                skill_root = path
                mode = TRAVERSAL_PLUGIN_CONTAINER
            else:
                continue
            specs.append(
                SkillRootSpec(
                    skill_root,
                    f"PLUGIN_MANIFEST_DECLARED_SKILL:{plugin_id}",
                    ROOT_KIND_PLUGIN_DECLARED,
                    traversal_mode=mode,
                    scope="plugin",
                    provenance=(f"plugin:{plugin_id}",),
                    plugin_identity=plugin_id,
                )
            )
    # 使用同一套 exact/ancestor compression，但不加 fixed global roots，也不跨 Plugin。
    return build_skill_root_plan(include_fixed_global=False, plugin_roots=tuple(specs)).roots


def _plugin_declared_skill_paths(manifest: Mapping[str, object]) -> tuple[object, ...]:
    """只收集 manifest 明確宣告的 Skill path，不搜尋 package。"""

    paths: list[object] = []
    for field_name in ("skill_roots", "skill_paths"):
        declared_roots = manifest.get(field_name, ())
        if isinstance(declared_roots, (str, Path)):
            paths.append(declared_roots)
        elif isinstance(declared_roots, Sequence):
            paths.extend(declared_roots)
        else:
            raise ValueError(f"plugin {field_name} must be a path or list")
    declared_skills = manifest.get("skills", ())
    if isinstance(declared_skills, (str, Path)):
        declared_skill_items = (declared_skills,)
    elif isinstance(declared_skills, Sequence):
        declared_skill_items = declared_skills
    else:
        raise ValueError("plugin skills must be a path or list")
    for child in declared_skill_items:
        if isinstance(child, Mapping):
            child_path = child.get("path", child.get("skill_path", child.get("source_root")))
            if child_path is not None:
                paths.append(child_path)
        elif isinstance(child, (str, Path)):
            paths.append(child)
    children = manifest.get("capabilities", manifest.get("children", ()))
    if not isinstance(children, Sequence) or isinstance(children, (str, bytes)):
        raise ValueError("plugin capabilities must be a list")
    for child in children:
        if isinstance(child, Mapping) and child.get("kind") == "skill":
            child_path = child.get("path", child.get("skill_path", child.get("source_root")))
            if child_path is not None:
                paths.append(child_path)
    return tuple(paths)


def discover_plugin_skill_roots(manifests: Sequence[Mapping[str, object]]) -> tuple[Path, ...]:
    """沿已確認 Plugin entity 的 declared paths 解析 bundled Skill roots。

    `.codex/plugins/cache` 在這裡只是 physical package store；只有 manifest
    已帶有 present/package evidence 且明確宣告 `skill_roots` 或 child `path`
    才會被讀取。函式不 recursive scan cache，也不使用 enabled 狀態。
    """

    if isinstance(manifests, (str, bytes)) or not isinstance(manifests, Sequence):
        raise ValueError("plugin manifests must be a sequence")
    result: list[Path] = []
    seen: set[str] = set()
    for manifest in manifests:
        if not isinstance(manifest, Mapping):
            raise ValueError("plugin manifests must contain mappings")
        plugin_id = manifest.get("plugin_id", manifest.get("id"))
        if not isinstance(plugin_id, str) or not plugin_id.strip():
            raise ValueError("plugin manifest requires a plugin identity")
        if not _plugin_entity_present(manifest):
            continue
        package_root_value = manifest.get("package_root", manifest.get("package_path"))
        package_root: Path | None = None
        if package_root_value is not None:
            if not isinstance(package_root_value, (str, Path)):
                raise ValueError("plugin package root must be a filesystem path")
            package_root = Path(package_root_value).resolve()
        paths: list[object] = []
        for field_name in ("skill_roots", "skill_paths"):
            declared_roots = manifest.get(field_name, ())
            if isinstance(declared_roots, (str, Path)):
                paths.append(declared_roots)
            elif isinstance(declared_roots, Sequence):
                paths.extend(declared_roots)
            else:
                raise ValueError(f"plugin {field_name} must be a path or list")
        declared_skills = manifest.get("skills", ())
        if isinstance(declared_skills, (str, Path)):
            declared_skill_items = (declared_skills,)
        elif isinstance(declared_skills, Sequence):
            declared_skill_items = declared_skills
        else:
            raise ValueError("plugin skills must be a path or list")
        for child in declared_skill_items:
            if isinstance(child, Mapping):
                child_path = child.get("path", child.get("skill_path", child.get("source_root")))
                if child_path is not None:
                    paths.append(child_path)
            elif isinstance(child, (str, Path)):
                paths.append(child)
        children = manifest.get("capabilities", manifest.get("children", ()))
        if not isinstance(children, Sequence) or isinstance(children, (str, bytes)):
            raise ValueError("plugin capabilities must be a list")
        for child in children:
            if isinstance(child, Mapping) and child.get("kind") == "skill":
                child_path = child.get("path", child.get("skill_path", child.get("source_root")))
                if child_path is not None:
                    paths.append(child_path)
        for raw_path in paths:
            for path in _resolve_plugin_skill_paths(package_root, raw_path):
                resolved = path.resolve()
                canonical = str(resolved).casefold()
                if canonical in seen:
                    continue
                seen.add(canonical)
                result.append(path)
    return tuple(result)


def discover_plugin_skill_declarations(
    manifests: Sequence[Mapping[str, object]],
) -> DiscoveryResult:
    """解析 Plugin manifest 的 package-declared Skill metadata。

    這條路徑只接受已確認存在的 Plugin entity；它不掃描 cache，也不把 package
    declaration 假裝成 runtime record。具備 identity 與 public metadata 的
    package-only Skill 仍可進入 existence union，之後由 semantic layer 考慮。
    """

    if isinstance(manifests, (str, bytes)) or not isinstance(manifests, Sequence):
        raise ValueError("plugin manifests must be a sequence")
    records: list[CapabilityRecord] = []
    diagnostics: list[DiscoveryDiagnostic] = []
    for manifest in manifests:
        if not isinstance(manifest, Mapping):
            raise ValueError("plugin manifests must contain mappings")
        plugin_id = manifest.get("plugin_id", manifest.get("id"))
        if not isinstance(plugin_id, str) or not plugin_id.strip():
            raise ValueError("plugin manifest requires a plugin identity")
        if not _plugin_entity_present(manifest):
            continue
        package_root = _plugin_package_root(manifest)
        for child in _plugin_skill_declarations(manifest):
            child_path = child.get("path", child.get("skill_path", child.get("source_root")))
            if child_path is not None and not _plugin_path_is_contained(package_root, child_path):
                diagnostics.append(
                    DiscoveryDiagnostic(
                        "plugin_path_escape",
                        "Plugin declaration escapes its package root",
                        f"plugin:{plugin_id}",
                    )
                )
                continue
            skill_id = child.get("skill_id", child.get("id"))
            if not isinstance(skill_id, str) or not skill_id.strip():
                continue
            name = child.get("name", child.get("title", skill_id))
            description = child.get("description")
            payload = {
                "id": skill_id,
                "name": name,
                "description": description,
                "kind": CapabilityKind.SKILL.value,
                "status": child.get("status", "unknown"),
                "provenance": [f"plugin:{plugin_id}"],
                "evidence": ["package manifest declared Skill"],
            }
            try:
                records.append(
                    record_from_mapping(
                        payload,
                        source=f"plugin-declared:{plugin_id}",
                        default_kind=CapabilityKind.SKILL,
                    )
                )
            except ValueError:
                diagnostics.append(
                    DiscoveryDiagnostic(
                        "invalid_plugin_skill_declaration",
                        "Plugin Skill declaration metadata is invalid",
                        f"plugin:{plugin_id}",
                    )
                )
    records.sort(key=lambda record: (record.id.casefold(), record.id, record.source))
    diagnostics.sort(key=lambda item: (item.code, item.source, item.message))
    return DiscoveryResult(tuple(records), tuple(diagnostics), partial=bool(diagnostics))


def _plugin_package_root(manifest: Mapping[str, object]) -> Path | None:
    """取得 Plugin package root；不把 manifest path 推導成 package root。"""

    value = manifest.get("package_root", manifest.get("package_path"))
    if value is None:
        return None
    if not isinstance(value, (str, Path)):
        raise ValueError("plugin package root must be a filesystem path")
    return Path(value).resolve()


def _plugin_skill_declarations(manifest: Mapping[str, object]) -> tuple[Mapping[str, object], ...]:
    """收集 manifest 宣告的 Skill child，不讀取未宣告的 package content。"""

    result: list[Mapping[str, object]] = []
    declared_skills = manifest.get("skills", ())
    if isinstance(declared_skills, (str, Path)):
        declared_skill_items = (declared_skills,)
    elif isinstance(declared_skills, Sequence):
        declared_skill_items = declared_skills
    else:
        raise ValueError("plugin skills must be a path or list")
    for child in declared_skill_items:
        if isinstance(child, Mapping):
            result.append(child)
        elif isinstance(child, (str, Path)):
            result.append({"path": child})
        else:
            raise ValueError("plugin Skill declaration must be an object or path")
    children = manifest.get("capabilities", manifest.get("children", ()))
    if not isinstance(children, Sequence) or isinstance(children, (str, bytes)):
        raise ValueError("plugin capabilities must be a list")
    for child in children:
        if not isinstance(child, Mapping):
            raise ValueError("plugin child capability must be an object")
        if child.get("kind") == "skill":
            result.append(child)
    return tuple(result)


def _plugin_path_is_contained(package_root: Path | None, raw_path: object) -> bool:
    """以 resolved path 驗證 Plugin declaration 不會離開 package root。"""

    if not isinstance(raw_path, (str, Path)):
        raise ValueError("plugin Skill path must be a filesystem path")
    path = Path(raw_path)
    # 沒有 package root 就沒有 containment proof；package-only declaration
    # 可以存在，但任何 physical path 都必須拒絕，避免把任意絕對路徑當成 Plugin source。
    if package_root is None:
        return False
    if package_root is not None and not path.is_absolute():
        path = package_root / path
    resolved = path.resolve()
    try:
        resolved.relative_to(package_root)
    except ValueError:
        return False
    return True


def _resolve_plugin_skill_paths(package_root: Path | None, raw_path: object) -> tuple[Path, ...]:
    """解析 direct Skill root 或 declared container 的一層 child。"""

    if not _plugin_path_is_contained(package_root, raw_path):
        return ()
    assert isinstance(raw_path, (str, Path))
    path = Path(raw_path)
    if package_root is not None and not path.is_absolute():
        path = package_root / path
    if path.name.casefold() == "skill.md":
        candidates = (path.parent,)
    elif path.is_dir() and (path / "SKILL.md").is_file():
        candidates = (path,)
    elif path.is_dir():
        try:
            candidates = tuple(
                child
                for child in sorted(path.iterdir(), key=lambda item: (item.name.casefold(), item.name))
                if child.is_dir() and child.name.casefold() != "__pycache__"
            )
        except OSError:
            return ()
    else:
        return ()
    valid: list[Path] = []
    for candidate in candidates:
        if candidate.is_symlink() or not candidate.is_dir():
            continue
        skill_file = candidate / "SKILL.md"
        if skill_file.is_symlink() or not skill_file.is_file():
            continue
        if not _plugin_path_is_contained(package_root, candidate):
            continue
        valid.append(candidate)
    return tuple(valid)


def _plugin_entity_present(manifest: Mapping[str, object]) -> bool:
    """以 logical Plugin presence/package evidence 判斷，不以 enabled 篩選。"""

    if "present" in manifest:
        if not isinstance(manifest["present"], bool):
            raise ValueError("plugin present must be boolean")
        return manifest["present"]
    if any(manifest.get(key) is not None for key in ("package_root", "package_path", "manifest_path")):
        return True
    # active_installed 是舊 envelope 的相容欄位；只有沒有新 package evidence
    # 時才使用它，避免把 enabled/active state 當成新的 selection gate。
    return manifest.get("active_installed") is True


def _read_skill(directory: Path, source: str) -> tuple[CapabilityRecord | None, DiscoveryDiagnostic | None]:
    """讀取單一明確 skill directory 的 allowlisted frontmatter。"""

    try:
        text = (directory / "SKILL.md").read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return None, DiscoveryDiagnostic("unreadable_skill", "skill metadata could not be read", source)

    return _parse_skill_text(text, directory, source)


def _parse_skill_text(text: str, directory: Path, source: str) -> tuple[CapabilityRecord | None, DiscoveryDiagnostic | None]:
    """Parse the same bytes used by discovery or selected-source recovery."""

    metadata = _frontmatter(text)
    if metadata is None:
        return _fallback_skill_record(directory, source, "skill metadata is malformed")
    # 修改紀錄（2026-08-19，Steve Peng）
    # 原始內容：discovery adapter 會移除 SKILL.md 的 description，且無法保留合法 multiline scalar。
    # 修改原因：Phase 5G-A 要讓合法 skill description 進入 Phase 5F 已支援的 canonical record。
    # 修改後功能：保留經 bounded parser 驗證的 description；未知結構仍由 record validation 拒絕。
    metadata.setdefault("kind", CapabilityKind.SKILL.value)
    metadata.setdefault("status", "unknown")
    # 修改紀錄（2026-08-21，Steve Peng）
    # 原始內容：discovery 將未知的 summary/requirements frontmatter 直接交給 canonical record validation。
    # 修改原因：Phase 2 Enriched Profile 需要保留這兩個 bounded 說明欄位，但它們不是 Basic Profile canonical fields。
    # 修改後功能：Skill discovery 忽略 enriched-only metadata，完整內容只在候選需要時由 inventory lazy reader 讀取。
    # 官方 Skill frontmatter 可帶 license/argument-hint 等非 Router 欄位；
    # 它們不是 existence 或 semantic metadata，不應讓合法 Skill 消失。
    metadata_for_record = {
        key: value for key, value in metadata.items() if key in _RECORD_FRONTMATTER_FIELDS
    }
    metadata_for_record.setdefault("id", _canonical_skill_id(metadata, directory))
    try:
        return record_from_mapping(metadata_for_record, source=source, default_kind=CapabilityKind.SKILL), None
    except ValueError:
        return _fallback_skill_record(directory, source, "skill metadata is invalid")


def _fallback_skill_record(
    directory: Path,
    source: str,
    reason: str,
) -> tuple[CapabilityRecord | None, DiscoveryDiagnostic]:
    """保留可建立 stable directory identity 的 malformed Skill 存在證據。"""

    fallback_id = directory.name
    if not isinstance(fallback_id, str) or _CANONICAL_ID.fullmatch(fallback_id) is None:
        return None, DiscoveryDiagnostic("malformed_skill_identity", "Skill identity cannot be resolved safely", source)
    try:
        record = record_from_mapping(
            {
                "id": fallback_id,
                "name": fallback_id,
                "kind": CapabilityKind.SKILL.value,
                "status": "unknown",
                "evidence": ["SKILL.md exists; metadata quality is OPAQUE"],
            },
            source=source,
            default_kind=CapabilityKind.SKILL,
        )
    except ValueError:
        return None, DiscoveryDiagnostic("malformed_skill_identity", "Skill identity cannot be resolved safely", source)
    return record, DiscoveryDiagnostic("malformed_skill", reason + "; retained as opaque Skill", source)


def _canonical_skill_id(metadata: Mapping[str, object], directory: Path) -> object:
    """取得 machine path 的 canonical ID；display name 僅保留為人類名稱。"""

    explicit_id = metadata.get("id")
    return directory.name if explicit_id is None else explicit_id


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
        duplicate_key = normalized_key.casefold()
        if not normalized_key or duplicate_key in seen_keys:
            return None
        seen_keys.add(duplicate_key)
        scalar = value.strip()
        if normalized_key == "allowed-tools":
            index = _parse_allowed_tools_section(lines, index + 1, end, scalar)
            if index is None:
                return None
            continue
        if normalized_key == "metadata":
            index = _parse_legacy_metadata_section(lines, index + 1, end, scalar)
            if index is None:
                return None
            continue
        if scalar and scalar[0] in "|>":
            parsed, next_index = _frontmatter_block_scalar(lines, index + 1, end, scalar[0])
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


def _parse_allowed_tools_section(
    lines: list[str],
    start: int,
    end: int,
    scalar: str,
) -> int | None:
    """驗證並略過 simple allowed-tools list，不把工具名帶入 Skill record。"""

    # 支援 bounded inline JSON list 或既有逗號分隔 legacy list；object、純 scalar 與 nested list 一律拒絕。
    if scalar:
        parsed = _frontmatter_value(scalar)
        if isinstance(parsed, list):
            items = parsed
        elif isinstance(parsed, str) and "," in parsed:
            items = [item.strip() for item in parsed.split(",")]
        elif isinstance(parsed, str) and parsed.strip():
            # 常見 Skill frontmatter 會用空白分隔非 Router tool names；
            # 它們只作 compatibility metadata，不進 capability record。
            items = parsed.split()
        else:
            return None
        if not items or not all(_safe_legacy_scalar(item) for item in items):
            return None
        return start

    if start >= end:
        return None

    content_indent: int | None = None
    index = start
    item_count = 0
    while index < end:
        line = lines[index]
        if not line.strip():
            index += 1
            continue
        if line.startswith("\t"):
            return None
        indent = len(line) - len(line.lstrip(" "))
        if indent == 0:
            if content_indent in (None, 0) and line.startswith("- "):
                if not _safe_legacy_scalar(line[2:].strip()):
                    return None
                content_indent = 0
                item_count += 1
                if item_count > 16:
                    return None
                index += 1
                continue
            break
        if content_indent is None:
            content_indent = indent
        if indent < content_indent:
            return None
        if indent != content_indent:
            return None
        content = line[content_indent:]
        if not content.startswith("- ") or not _safe_legacy_scalar(content[2:].strip()):
            return None
        item_count += 1
        if item_count > 16:
            return None
        index += 1
    if content_indent is None or item_count == 0:
        return None
    return index


def _parse_legacy_metadata_section(
    lines: list[str],
    start: int,
    end: int,
    scalar: str,
) -> int | None:
    """略過非 Router metadata，同時拒絕明顯敏感欄位與壞的 legacy scalar。"""

    if scalar:
        return None
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
        if _SENSITIVE_METADATA_TEXT.search(line) is not None:
            return None
        # Nested metadata is compatibility-only.  Its scalar/list structure is
        # not imported into Router, but sensitive keys are still rejected.
        if indent != content_indent:
            key = line.strip().partition(":")[0].strip()
            if _sensitive_metadata_key(key):
                return None
            index += 1
            continue
        content = line[content_indent:]
        key, separator, value = content.partition(":")
        normalized_key = key.strip()
        key_folded = normalized_key.casefold()
        if (
            not _METADATA_KEY.fullmatch(normalized_key)
            or key_folded in seen_keys
            or _sensitive_metadata_key(normalized_key)
        ):
            return None
        seen_keys.add(key_folded)
        nested_value = value.strip()
        if normalized_key in _LEGACY_METADATA_SCALAR_KEYS:
            if not nested_value or not _safe_legacy_scalar(_frontmatter_value(nested_value)):
                return None
            index += 1
            continue
        # 只要未知欄位本身是 bounded safe scalar，就忽略其 compatibility
        # metadata；空值欄位則略過它的 bounded indented subtree。這保留
        # Router 所需的 name/description，且不把第三方 metadata 當成能力語意。
        if nested_value:
            if not _safe_legacy_scalar(_frontmatter_value(nested_value)):
                return None
            index += 1
            continue
        next_index = _skip_indented_block(lines, index + 1, end, content_indent)
        if next_index is None:
            return None
        index = next_index
    return index if content_indent is not None else None


def _skip_indented_block(
    lines: list[str],
    start: int,
    end: int,
    parent_indent: int,
) -> int | None:
    """略過一個不進 Router record 的 bounded metadata subtree。"""

    index = start
    while index < end:
        line = lines[index]
        if not line.strip():
            index += 1
            continue
        if line.startswith("\t"):
            return None
        indent = len(line) - len(line.lstrip(" "))
        if indent <= parent_indent:
            break
        index += 1
    return index


def _parse_source_frontmatter_leaves(
    lines: list[str],
    start: int,
    end: int,
    parent_indent: int,
) -> int | None:
    """只接受 source_frontmatter 下一層的 scalar leaves，拒絕更深結構。"""

    leaf_indent: int | None = None
    index = start
    seen_keys: set[str] = set()
    leaf_count = 0
    while index < end:
        line = lines[index]
        if not line.strip():
            index += 1
            continue
        indent = len(line) - len(line.lstrip(" "))
        if indent <= parent_indent:
            break
        if leaf_indent is None:
            leaf_indent = indent
        if indent != leaf_indent:
            return None
        key, separator, value = line[leaf_indent:].partition(":")
        normalized_key = key.strip()
        key_folded = normalized_key.casefold()
        scalar = value.strip()
        if (
            not _METADATA_KEY.fullmatch(normalized_key)
            or key_folded in seen_keys
            or _sensitive_metadata_key(normalized_key)
            or not scalar
            or not _safe_legacy_scalar(_frontmatter_value(scalar))
        ):
            return None
        seen_keys.add(key_folded)
        leaf_count += 1
        if leaf_count > 16:
            return None
        index += 1
    return index if leaf_indent is not None and leaf_count else None


def _safe_legacy_scalar(value: object) -> bool:
    """限制 legacy compatibility 值為 bounded 非空 scalar，拒絕 list/object/secret。"""

    if not isinstance(value, (str, int, float, bool)) or isinstance(value, (bytes, list, dict)):
        return False
    text = str(value).strip()
    return bool(text) and len(text) <= 512 and "\x00" not in text and _SENSITIVE_METADATA_TEXT.search(text) is None


def _sensitive_metadata_key(value: str) -> bool:
    """辨識 nested metadata 的 secret-like key，不回顯其值。"""

    return value.casefold().replace("-", "_") in _SENSITIVE_METADATA_KEYS


def _frontmatter_value(value: str) -> object:
    """將 frontmatter 的簡單 scalar/list 轉為 validation 可接受型別。"""

    if value.startswith(("[", "{")) or value in {"true", "false", "null"}:
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return None
        if isinstance(parsed, (bool, int, float, list, dict)):
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
