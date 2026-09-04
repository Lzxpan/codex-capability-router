"""固定 Skill 搜尋根、壓縮規則與 immutable root-plan snapshot。"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
import hashlib
import json
import os
from pathlib import Path


# 修改紀錄（2026-09-03，Steve Peng）
# 原始內容：Skill discovery 每次只接受未帶來源語意的 roots，且 global/system 與
# Plugin container 沒有可重用的 non-overlapping plan。
# 修改原因：beta.7 要在初始化/明確 refresh 時固定 authoritative roots，保留 scope，
# 並讓 ordinary route 直接重用 Skill inventory snapshot，不重做 filesystem analysis。
# 修改後功能：提供固定 global、known project、runtime-declared、Plugin-declared 四類
# root spec；只在已知 coverage 規則成立時做 same-path/ancestor compression。

KNOWN_SYSTEM_CHILD = ".system"
ROOT_KIND_FIXED_GLOBAL = "FIXED_GLOBAL_ROOT"
ROOT_KIND_FIXED_PROJECT = "FIXED_PROJECT_RULE"
ROOT_KIND_RUNTIME_EXTRA = "EXPLICIT_RUNTIME_ROOT"
ROOT_KIND_PLUGIN_DECLARED = "PLUGIN_DECLARED_ROOT"

TRAVERSAL_IMMEDIATE = "immediate-skill-directories"
TRAVERSAL_KNOWN_SYSTEM = "known-system-child"
TRAVERSAL_PLUGIN_CONTAINER = "plugin-declared-container"
TRAVERSAL_DIRECT_SKILL = "direct-skill-root"
TRAVERSAL_BOUNDED_SUBTREE = "bounded-declared-subtree"


@dataclass(frozen=True)
class SkillRootSpec:
    """一個 filesystem root node 的 authoritative traversal contract。"""

    path: Path
    source_kind: str
    root_kind: str
    traversal_mode: str = TRAVERSAL_IMMEDIATE
    scope: str = "managed"
    provenance: tuple[str, ...] = ()
    known_children: tuple[str, ...] = ()
    plugin_identity: str | None = None

    def __post_init__(self) -> None:
        """固定 path/metadata 型別，拒絕未定義的 traversal。"""

        object.__setattr__(self, "path", Path(self.path))
        object.__setattr__(self, "provenance", tuple(self.provenance))
        object.__setattr__(self, "known_children", tuple(self.known_children))
        if self.traversal_mode not in {
            TRAVERSAL_IMMEDIATE,
            TRAVERSAL_KNOWN_SYSTEM,
            TRAVERSAL_PLUGIN_CONTAINER,
            TRAVERSAL_DIRECT_SKILL,
            TRAVERSAL_BOUNDED_SUBTREE,
        }:
            raise ValueError("unsupported Skill root traversal mode")
        if not self.source_kind.strip() or not self.root_kind.strip() or not self.scope.strip():
            raise ValueError("Skill root metadata is required")
        if any(not isinstance(child, str) or not child.strip() for child in self.known_children):
            raise ValueError("known Skill root children must be non-empty names")
        if self.traversal_mode == TRAVERSAL_KNOWN_SYSTEM and KNOWN_SYSTEM_CHILD not in self.known_children:
            raise ValueError("known-system traversal requires .system child")


@dataclass(frozen=True)
class RootPlanSnapshot:
    """初始化/refresh 產生的 deterministic、immutable Skill root plan。"""

    roots: tuple[SkillRootSpec, ...]
    fingerprint: str
    input_root_count: int = 0
    duplicate_roots_removed: int = 0
    descendant_roots_removed: int = 0

    def __post_init__(self) -> None:
        """驗證 fingerprint 與 root-plan counter，避免 route 私下改 plan。"""

        roots = tuple(self.roots)
        if any(not isinstance(root, SkillRootSpec) for root in roots):
            raise TypeError("RootPlanSnapshot roots must contain SkillRootSpec values")
        object.__setattr__(self, "roots", roots)
        if len(self.fingerprint) != 64 or any(char not in "0123456789abcdef" for char in self.fingerprint):
            raise ValueError("RootPlanSnapshot requires a SHA-256 fingerprint")
        if self.fingerprint != _fingerprint_specs(roots):
            raise ValueError("RootPlanSnapshot fingerprint does not match its roots")
        for value in (self.input_root_count, self.duplicate_roots_removed, self.descendant_roots_removed):
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError("RootPlanSnapshot counters must be non-negative integers")

    @property
    def root_count(self) -> int:
        """回傳 plan node count；不等於 Skill entity count。"""

        return len(self.roots)

    def to_mapping(self) -> dict[str, object]:
        """輸出只含 public contract metadata 的 deterministic mapping。"""

        return {
            "roots": [
                {
                    "path": str(root.path),
                    "source_kind": root.source_kind,
                    "root_kind": root.root_kind,
                    "traversal_mode": root.traversal_mode,
                    "scope": root.scope,
                    "provenance": list(root.provenance),
                    "known_children": list(root.known_children),
                    "plugin_identity": root.plugin_identity,
                }
                for root in self.roots
            ],
            "fingerprint": self.fingerprint,
            "input_root_count": self.input_root_count,
            "duplicate_roots_removed": self.duplicate_roots_removed,
            "descendant_roots_removed": self.descendant_roots_removed,
        }


def build_skill_root_plan(
    *,
    home: Path | None = None,
    codex_home: Path | None = None,
    project_scope: Path | None = None,
    runtime_extra_roots: Sequence[Path | SkillRootSpec] = (),
    plugin_roots: Sequence[SkillRootSpec] = (),
    plugin_manifests: Sequence[Mapping[str, object]] = (),
    additional_roots: Sequence[SkillRootSpec] = (),
    include_fixed_global: bool = True,
) -> RootPlanSnapshot:
    """建立最小 authoritative Skill root plan。

    呼叫時機：session/process initialization 或明確 refresh；ordinary route 不應
    呼叫本函式。輸入只接受固定 global、controller 已知 project scope、runtime
    明確宣告 root 與 Plugin manifest 產生的 root。函式不搜尋 filesystem 來猜 root，
    也不把 PluginStore parent 當成 recursive root。
    """

    specs: list[SkillRootSpec] = []
    if include_fixed_global:
        home_root = _canonical(home if home is not None else Path.home()) / ".agents" / "skills"
        codex_root = _canonical(codex_home if codex_home is not None else _codex_home(home_root)) / "skills"
        specs.extend(
            (
                SkillRootSpec(
                    home_root,
                    "OFFICIAL_SKILL_ROOT",
                    ROOT_KIND_FIXED_GLOBAL,
                    scope="user",
                    provenance=("fixed:$HOME/.agents/skills",),
                ),
                SkillRootSpec(
                    codex_root,
                    "OFFICIAL_SKILL_ROOT",
                    ROOT_KIND_FIXED_GLOBAL,
                    traversal_mode=TRAVERSAL_KNOWN_SYSTEM,
                    scope="managed",
                    provenance=("fixed:$CODEX_HOME/skills",),
                    known_children=(KNOWN_SYSTEM_CHILD,),
                ),
            )
        )
    if project_scope is not None:
        project_root = _canonical(project_scope) / ".agents" / "skills"
        if project_root.is_dir():
            specs.append(
                SkillRootSpec(
                    project_root,
                    "PROJECT_SKILL_ROOT",
                    ROOT_KIND_FIXED_PROJECT,
                    scope="project",
                    provenance=("known-project-scope",),
                )
            )
    for root in runtime_extra_roots:
        specs.append(_coerce_runtime_root(root))
    specs.extend(plugin_roots)
    if plugin_manifests:
        # 延遲 import 避免 skill_plan 與 discovery 的 module cycle；這仍是
        # manifest-declared exact path resolver，不是 PluginStore scan。
        from .discovery import discover_plugin_skill_root_specs

        specs.extend(discover_plugin_skill_root_specs(plugin_manifests))
    specs.extend(additional_roots)
    return _compress_specs(specs)


def _codex_home(home_root: Path) -> Path:
    """只讀取既有 CODEX_HOME 宣告；未宣告時使用 user home 的 .codex。"""

    declared = os.environ.get("CODEX_HOME")
    return Path(declared).expanduser() if declared else home_root.parent.parent / ".codex"


def _coerce_runtime_root(root: Path | SkillRootSpec) -> SkillRootSpec:
    """將 runtime 明確宣告 root 正規化，不接受未帶 path 的任意物件。"""

    if isinstance(root, SkillRootSpec):
        return root
    if not isinstance(root, Path):
        raise TypeError("runtime extra roots must be explicit Path values or SkillRootSpec values")
    return SkillRootSpec(
        root,
        "TRUSTED_RUNTIME_DECLARED_ROOT",
        ROOT_KIND_RUNTIME_EXTRA,
        scope="runtime",
        provenance=("runtime-declared",),
    )


def _compress_specs(specs: Sequence[SkillRootSpec]) -> RootPlanSnapshot:
    """在 filesystem traversal 前做 exact dedupe 與有 coverage 證據的壓縮。"""

    normalized: dict[str, list[SkillRootSpec]] = {}
    for spec in specs:
        if not isinstance(spec, SkillRootSpec):
            raise TypeError("Skill root plan requires SkillRootSpec values")
        path = _canonical(spec.path)
        normalized.setdefault(_path_key(path), []).append(
            SkillRootSpec(
                path,
                spec.source_kind,
                spec.root_kind,
                spec.traversal_mode,
                spec.scope,
                spec.provenance,
                spec.known_children,
                spec.plugin_identity,
            )
        )
    input_count = sum(len(items) for items in normalized.values())
    duplicate_count = sum(max(0, len(items) - 1) for items in normalized.values())
    unique = [_merge_same_path(items) for items in normalized.values()]
    unique.sort(key=_spec_sort_key)
    retained: list[SkillRootSpec] = []
    descendant_removed = 0
    for spec in unique:
        if any(_covers(parent, spec) for parent in retained):
            descendant_removed += 1
            continue
        retained.append(spec)
    fingerprint = _fingerprint_specs(retained)
    return RootPlanSnapshot(
        tuple(retained),
        fingerprint,
        input_count,
        duplicate_count,
        descendant_removed,
    )


def _merge_same_path(items: Sequence[SkillRootSpec]) -> SkillRootSpec:
    """選擇 coverage 最完整的同路徑 spec，並合併 provenance。"""

    selected = min(items, key=_spec_preference_key)
    provenance = tuple(sorted({value for item in items for value in item.provenance}))
    known_children = tuple(sorted({value for item in items for value in item.known_children}))
    return SkillRootSpec(
        selected.path,
        selected.source_kind,
        selected.root_kind,
        selected.traversal_mode,
        selected.scope,
        provenance,
        known_children,
        selected.plugin_identity,
    )


def _spec_preference_key(spec: SkillRootSpec) -> tuple[object, ...]:
    coverage_rank = {
        TRAVERSAL_KNOWN_SYSTEM: 0,
        TRAVERSAL_PLUGIN_CONTAINER: 1,
        TRAVERSAL_BOUNDED_SUBTREE: 2,
        TRAVERSAL_DIRECT_SKILL: 3,
        TRAVERSAL_IMMEDIATE: 4,
    }
    return (
        coverage_rank[spec.traversal_mode],
        spec.root_kind,
        spec.source_kind,
        spec.scope,
        spec.plugin_identity or "",
        spec.provenance,
    )


def _spec_sort_key(spec: SkillRootSpec) -> tuple[object, ...]:
    return (_path_key(spec.path), _spec_preference_key(spec))


def _covers(parent: SkillRootSpec, child: SkillRootSpec) -> bool:
    """只依 explicit traversal coverage 判斷 descendant 是否可移除。"""

    if parent.path == child.path:
        return False
    if parent.root_kind == ROOT_KIND_PLUGIN_DECLARED or child.root_kind == ROOT_KIND_PLUGIN_DECLARED:
        if parent.plugin_identity != child.plugin_identity:
            return False
    try:
        relative = child.path.relative_to(parent.path)
    except ValueError:
        return False
    if parent.traversal_mode in {TRAVERSAL_PLUGIN_CONTAINER, TRAVERSAL_BOUNDED_SUBTREE}:
        return True
    if parent.traversal_mode == TRAVERSAL_KNOWN_SYSTEM:
        return bool(relative.parts) and relative.parts[0] in parent.known_children
    return False


def _canonical(path: Path) -> Path:
    """建立 deterministic canonical path；不以 path search 取得 capability。"""

    return Path(path).expanduser().resolve(strict=False)


def _path_key(path: Path) -> str:
    """Windows/Unix 都使用 case-insensitive key 做 exact path dedupe。"""

    return str(path).casefold()


def _spec_mapping(spec: SkillRootSpec) -> dict[str, object]:
    return {
        "path": str(spec.path),
        "source_kind": spec.source_kind,
        "root_kind": spec.root_kind,
        "traversal_mode": spec.traversal_mode,
        "scope": spec.scope,
        "provenance": list(spec.provenance),
        "known_children": list(spec.known_children),
        "plugin_identity": spec.plugin_identity,
    }


def _fingerprint_specs(specs: Sequence[SkillRootSpec]) -> str:
    """以 canonical root metadata 計算 plan fingerprint。"""

    encoded = json.dumps(
        [_spec_mapping(spec) for spec in specs],
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
