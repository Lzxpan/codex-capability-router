"""Known Plugin entity 到官方 physical package root 的 bounded resolver。

本模組只接受 caller 已取得的 logical Plugin inventory；它不從 cache 反向
發現 Plugin，也不遞迴搜尋任何 package。成功解析後只讀取 exact
``.codex-plugin/plugin.json``，再把 manifest 交給既有 declared-child adapters。
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
import json
from pathlib import Path
import re


# 修改紀錄（2026-09-03，Steve Peng）
# 原始內容：Plugin CLI 缺少 source.path 時沒有官方 per-entity root resolver，114 個 logical Plugin 的 child declaration 無法解析。
# 修改原因：beta.6 必須先由 logical Plugin inventory 定位官方 PluginStore，再沿 exact manifest declared paths 完成 child discovery。
# 修改後功能：依 CLI exact path、validated version root 或單一直接版本目錄 fallback 解析；不掃整個 plugins/cache，且保留 unresolved Plugin entity 診斷。


PLUGIN_STORE_RELATIVE_ROOT = Path("plugins") / "cache"
PLUGIN_MANIFEST_RELATIVE_PATH = Path(".codex-plugin") / "plugin.json"
PLUGIN_ROOT_RESOLUTION_STATES = frozenset(
    {"CLI_EXACT_PATH", "VERSION_DIRECT_ROOT", "ACTIVE_ROOT_FALLBACK", "UNRESOLVED"}
)
PLUGIN_ROOT_STATUS = frozenset(
    {"RESOLVED", "MISSING", "MANIFEST_MISSING", "MANIFEST_UNREADABLE", "UNRESOLVED"}
)
_STORE_SEGMENT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+\-]*$")


@dataclass(frozen=True)
class PluginIdentity:
    """目前 CLI row 的 logical Plugin identity，不把 raw ID 當 filesystem path。"""

    raw_plugin_id: str
    plugin_name: str
    marketplace_name: str
    version: str | None = None

    @classmethod
    def from_cli_row(cls, row: Mapping[str, object]) -> "PluginIdentity":
        """驗證現行 `pluginId`/`name`/`marketplaceName` 欄位並建立 identity。

        呼叫時機：只在 caller 已完成 `codex plugin list --json` 且選定
        `installed` rows 後使用。回傳值只保存 public identity；欄位缺漏、
        ID 與分欄不一致或 path-like segment 會拒絕，不以字串猜測 marketplace。
        """

        if not isinstance(row, Mapping):
            raise ValueError("Plugin inventory row must be an object")
        raw_plugin_id = _required_text(row.get("pluginId", row.get("plugin_id", row.get("id"))), "pluginId")
        plugin_name = _store_segment(row.get("name"), "Plugin name")
        marketplace_name = _store_segment(
            row.get("marketplaceName", row.get("marketplace_name")),
            "Plugin marketplace name",
        )
        # CLI 已同時提供結構化欄位；用欄位一致性驗證取代對 @ 的自行切割。
        if raw_plugin_id != f"{plugin_name}@{marketplace_name}":
            raise ValueError("Plugin identity fields are inconsistent")
        raw_version = row.get("version")
        version = None if raw_version is None else _store_segment(raw_version, "Plugin version")
        return cls(raw_plugin_id, plugin_name, marketplace_name, version)


@dataclass(frozen=True)
class PluginRootResolution:
    """單一 logical Plugin 的 root/manifest resolution 結果。"""

    raw_plugin_id: str | None
    identity: PluginIdentity | None
    resolution: str
    package_root: Path | None = field(default=None, repr=False, compare=False)
    manifest_path: Path | None = field(default=None, repr=False, compare=False)
    status: str = "UNRESOLVED"
    manifest: Mapping[str, object] | None = field(default=None, repr=False, compare=False)

    def __post_init__(self) -> None:
        """限制 resolver 的有限狀態，避免把未解析 row 誤當成 package。"""

        if self.resolution not in PLUGIN_ROOT_RESOLUTION_STATES:
            raise ValueError("unsupported Plugin root resolution state")
        if self.status not in PLUGIN_ROOT_STATUS:
            raise ValueError("unsupported Plugin root status")
        if self.status == "RESOLVED" and (self.package_root is None or self.manifest is None):
            raise ValueError("resolved Plugin root requires package manifest")

    @property
    def resolved(self) -> bool:
        """回傳 exact package manifest 是否已成功取得。"""

        return self.status == "RESOLVED"

    def to_mapping(self) -> dict[str, object]:
        """輸出不含 private absolute path 的 public audit mapping。"""

        return {
            "plugin_id": self.raw_plugin_id,
            "resolution": self.resolution,
            "status": self.status,
            "manifest_loaded": self.manifest is not None,
            "version": None if self.identity is None else self.identity.version,
        }


@dataclass(frozen=True)
class PluginStoreMetrics:
    """PluginStore per-entity lookup 的 source-derived cost/count metrics。"""

    plugin_logical_total: int = 0
    plugin_cli_exact_path_total: int = 0
    plugin_version_direct_root_total: int = 0
    plugin_active_root_resolved_total: int = 0
    plugin_root_unresolved_total: int = 0
    plugin_root_missing_total: int = 0
    plugin_base_roots_visited: int = 0
    plugin_version_entries_visited: int = 0
    plugin_physical_roots_visited: int = 0
    plugin_manifests_opened: int = 0
    unreferenced_plugin_cache_roots_visited: int = 0

    def __post_init__(self) -> None:
        """拒絕負數，避免 audit metrics 被手動調整成看似完整。"""

        fields = (
            self.plugin_logical_total,
            self.plugin_cli_exact_path_total,
            self.plugin_version_direct_root_total,
            self.plugin_active_root_resolved_total,
            self.plugin_root_unresolved_total,
            self.plugin_root_missing_total,
            self.plugin_base_roots_visited,
            self.plugin_version_entries_visited,
            self.plugin_physical_roots_visited,
            self.plugin_manifests_opened,
            self.unreferenced_plugin_cache_roots_visited,
        )
        if any(isinstance(value, bool) or not isinstance(value, int) or value < 0 for value in fields):
            raise ValueError("PluginStore metrics must be non-negative integers")

    def to_mapping(self) -> dict[str, int]:
        """輸出 deterministic source-derived metrics。"""

        return {
            "plugin_logical_total": self.plugin_logical_total,
            "plugin_cli_exact_path_total": self.plugin_cli_exact_path_total,
            "plugin_version_direct_root_total": self.plugin_version_direct_root_total,
            "plugin_active_root_resolved_total": self.plugin_active_root_resolved_total,
            "plugin_root_unresolved_total": self.plugin_root_unresolved_total,
            "plugin_root_missing_total": self.plugin_root_missing_total,
            "plugin_base_roots_visited": self.plugin_base_roots_visited,
            "plugin_version_entries_visited": self.plugin_version_entries_visited,
            "plugin_physical_roots_visited": self.plugin_physical_roots_visited,
            "plugin_manifests_opened": self.plugin_manifests_opened,
            "unreferenced_plugin_cache_roots_visited": self.unreferenced_plugin_cache_roots_visited,
        }


@dataclass(frozen=True)
class PluginStoreInventory:
    """Logical Plugin inventory 與已解析 manifest 的 bounded projection。"""

    resolutions: tuple[PluginRootResolution, ...] = ()
    manifests: tuple[Mapping[str, object], ...] = ()
    diagnostics: tuple[str, ...] = ()
    metrics: PluginStoreMetrics = field(default_factory=PluginStoreMetrics)

    def __post_init__(self) -> None:
        """固定順序與 manifest container，供既有 discovery adapters 重用。"""

        object.__setattr__(self, "resolutions", tuple(self.resolutions))
        object.__setattr__(self, "manifests", tuple(self.manifests))
        object.__setattr__(self, "diagnostics", tuple(self.diagnostics))
        if not isinstance(self.metrics, PluginStoreMetrics):
            raise TypeError("PluginStoreInventory requires PluginStoreMetrics")

    @property
    def resolved_count(self) -> int:
        """回傳已取得 exact package manifest 的 Plugin logical count。"""

        return sum(item.resolved for item in self.resolutions)

    def to_mapping(self) -> dict[str, object]:
        """輸出不帶 package absolute path 的 audit projection。"""

        return {
            "resolutions": [item.to_mapping() for item in self.resolutions],
            "diagnostics": list(self.diagnostics),
            "metrics": self.metrics.to_mapping(),
        }


def resolve_plugin_store_inventory(
    payload: Mapping[str, object] | Sequence[Mapping[str, object]],
    *,
    plugin_store_root: Path,
) -> PluginStoreInventory:
    """依 current CLI PluginStore contract 解析 known logical Plugins。

    `payload` 必須是 `codex plugin list --json` 的 object，僅使用其
    `installed` rows；測試與已正規化 caller 也可直接傳 rows sequence。
    Root resolution 順序是 CLI exact path、validated version direct root、
    或該 Plugin 自己 base root 下「只有一個」直接版本目錄的保守 fallback。
    多版本時不猜 latest/mtime，保留 Plugin entity 並標記 unresolved。

    回傳的 `manifests` 可直接傳入既有 `discover_plugin_skill_roots()`、
    `discover_plugin_skill_declarations()` 與 `discover_active_plugin_children()`。
    函式不做 package-wide glob、recursive cache scan 或 readiness filtering。
    """

    if isinstance(payload, Mapping):
        rows = payload.get("installed")
        if not isinstance(rows, list):
            raise ValueError("Plugin CLI payload must contain an installed array")
    elif isinstance(payload, Sequence) and not isinstance(payload, (str, bytes)):
        rows = list(payload)
    else:
        raise ValueError("Plugin inventory payload must be an object or row sequence")
    if not all(isinstance(row, Mapping) for row in rows):
        raise ValueError("Plugin installed rows must be objects")
    store_root = Path(plugin_store_root).resolve()
    if not store_root.is_dir():
        raise ValueError("PluginStore root is unavailable")

    resolutions: list[PluginRootResolution] = []
    manifests: list[Mapping[str, object]] = []
    diagnostics: list[str] = []
    counters = {
        "plugin_cli_exact_path_total": 0,
        "plugin_version_direct_root_total": 0,
        "plugin_active_root_resolved_total": 0,
        "plugin_root_unresolved_total": 0,
        "plugin_root_missing_total": 0,
        "plugin_base_roots_visited": 0,
        "plugin_version_entries_visited": 0,
        "plugin_physical_roots_visited": 0,
        "plugin_manifests_opened": 0,
    }

    valid_rows: dict[str, list[Mapping[str, object]]] = {}
    invalid_row_count = 0
    for row_index, row in enumerate(rows):
        raw_plugin_id = _optional_text(row.get("pluginId", row.get("plugin_id", row.get("id"))))
        try:
            identity = PluginIdentity.from_cli_row(row)
        except ValueError as error:
            invalid_row_count += 1
            diagnostics.append(f"plugin_identity_unresolved:{row_index}:{_diagnostic_code(error)}")
            continue
        valid_rows.setdefault(identity.raw_plugin_id, []).append(row)

    for row_index, (raw_plugin_id, candidate_rows) in enumerate(sorted(valid_rows.items())):
        # 同一 logical Plugin 若有多筆 physical evidence，依 root priority
        # 選一筆代表；不把 materialization 數量膨脹成 Plugin entity。相同優先級
        # 仍依 public path 的 deterministic ordering，不使用 mtime/latest 猜測。
        row = min(candidate_rows, key=_row_priority)
        identity = PluginIdentity.from_cli_row(row)

        exact_path = _exact_source_path(row)
        if exact_path is not None:
            counters["plugin_cli_exact_path_total"] += 1
            resolution = _load_manifest(
                identity,
                "CLI_EXACT_PATH",
                exact_path,
                diagnostics,
                counters,
            )
        elif identity.version is not None:
            counters["plugin_version_direct_root_total"] += 1
            base = _store_base_root(store_root, identity)
            counters["plugin_base_roots_visited"] += 1
            if base is None:
                counters["plugin_root_unresolved_total"] += 1
                resolution = PluginRootResolution(
                    identity.raw_plugin_id,
                    identity,
                    "UNRESOLVED",
                    status="UNRESOLVED",
                )
                diagnostics.append(f"plugin_root_unresolved:{identity.raw_plugin_id}")
            else:
                package_root = _contained_path(base / identity.version, base, store_root)
                if package_root is None:
                    counters["plugin_root_unresolved_total"] += 1
                    resolution = PluginRootResolution(
                        identity.raw_plugin_id,
                        identity,
                        "UNRESOLVED",
                        status="UNRESOLVED",
                    )
                    diagnostics.append(f"plugin_root_escape:{identity.raw_plugin_id}")
                else:
                    resolution = _load_manifest(
                        identity,
                        "VERSION_DIRECT_ROOT",
                        package_root,
                        diagnostics,
                        counters,
                    )
        else:
            base = _store_base_root(store_root, identity)
            counters["plugin_base_roots_visited"] += 1
            package_root = _resolve_single_active_root(
                base,
                store_root,
                counters,
            )
            if package_root is None:
                counters["plugin_root_unresolved_total"] += 1
                resolution = PluginRootResolution(
                    identity.raw_plugin_id,
                    identity,
                    "UNRESOLVED",
                    status="UNRESOLVED",
                )
                diagnostics.append(f"plugin_active_root_unresolved:{identity.raw_plugin_id}")
            else:
                counters["plugin_active_root_resolved_total"] += 1
                resolution = _load_manifest(
                    identity,
                    "ACTIVE_ROOT_FALLBACK",
                    package_root,
                    diagnostics,
                    counters,
                )

        resolutions.append(resolution)
        if resolution.manifest is not None:
            manifests.append(resolution.manifest)

    if invalid_row_count:
        counters["plugin_root_unresolved_total"] += invalid_row_count
    metrics = PluginStoreMetrics(
        plugin_logical_total=len(valid_rows),
        **counters,
        unreferenced_plugin_cache_roots_visited=0,
    )
    resolutions.sort(key=lambda item: ((item.raw_plugin_id or "").casefold(), item.raw_plugin_id or ""))
    manifests.sort(key=lambda item: (str(item.get("plugin_id", "")).casefold(), str(item.get("plugin_id", ""))))
    diagnostics.sort()
    return PluginStoreInventory(tuple(resolutions), tuple(manifests), tuple(diagnostics), metrics)


def _load_manifest(
    identity: PluginIdentity,
    resolution: str,
    package_root: Path,
    diagnostics: list[str],
    counters: dict[str, int],
) -> PluginRootResolution:
    """只讀 exact manifest，將 root missing 與 manifest failure 分開記錄。"""

    if not package_root.is_dir():
        counters["plugin_root_missing_total"] += 1
        diagnostics.append(f"plugin_root_missing:{identity.raw_plugin_id}")
        return PluginRootResolution(
            identity.raw_plugin_id,
            identity,
            resolution,
            package_root=package_root,
            status="MISSING",
        )
    counters["plugin_physical_roots_visited"] += 1
    manifest_path = package_root / PLUGIN_MANIFEST_RELATIVE_PATH
    if not manifest_path.is_file():
        diagnostics.append(f"plugin_manifest_missing:{identity.raw_plugin_id}")
        return PluginRootResolution(
            identity.raw_plugin_id,
            identity,
            resolution,
            package_root=package_root,
            manifest_path=manifest_path,
            status="MANIFEST_MISSING",
        )
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        diagnostics.append(f"plugin_manifest_unreadable:{identity.raw_plugin_id}")
        return PluginRootResolution(
            identity.raw_plugin_id,
            identity,
            resolution,
            package_root=package_root,
            manifest_path=manifest_path,
            status="MANIFEST_UNREADABLE",
        )
    if not isinstance(payload, Mapping):
        diagnostics.append(f"plugin_manifest_unreadable:{identity.raw_plugin_id}")
        return PluginRootResolution(
            identity.raw_plugin_id,
            identity,
            resolution,
            package_root=package_root,
            manifest_path=manifest_path,
            status="MANIFEST_UNREADABLE",
        )
    counters["plugin_manifests_opened"] += 1
    normalized = dict(payload)
    normalized.update(
        {
            "plugin_id": identity.raw_plugin_id,
            "plugin_name": identity.plugin_name,
            "marketplace_name": identity.marketplace_name,
            "plugin_version": identity.version,
            "present": True,
            "package_root": str(package_root),
            "manifest_path": str(manifest_path),
            "plugin_root_resolution": resolution,
        }
    )
    return PluginRootResolution(
        identity.raw_plugin_id,
        identity,
        resolution,
        package_root=package_root,
        manifest_path=manifest_path,
        status="RESOLVED",
        manifest=normalized,
    )


def _store_base_root(store_root: Path, identity: PluginIdentity) -> Path | None:
    """建立單一 Plugin 的 base root，並驗證沒有離開 PluginStore。"""

    base = _contained_path(
        store_root / identity.marketplace_name / identity.plugin_name,
        store_root,
        store_root,
    )
    return base if base is not None else None


def _resolve_single_active_root(
    base: Path | None,
    store_root: Path,
    counters: dict[str, int],
) -> Path | None:
    """只檢查已知 Plugin base 下的直接子目錄；多版本時不猜選哪一個。"""

    if base is None or not base.is_dir():
        return None
    try:
        entries = tuple(sorted(base.iterdir(), key=lambda item: (item.name.casefold(), item.name)))
    except OSError:
        return None
    counters["plugin_version_entries_visited"] += len(entries)
    directories = tuple(
        entry
        for entry in entries
        if entry.is_dir() and not entry.is_symlink()
    )
    if len(directories) != 1:
        return None
    return _contained_path(directories[0], base, store_root)


def _contained_path(path: Path, parent: Path, store_root: Path) -> Path | None:
    """resolve 後限制在預期 parent 與 PluginStore 內，拒絕 symlink escape。"""

    resolved = path.resolve()
    for boundary in (parent.resolve(), store_root.resolve()):
        try:
            resolved.relative_to(boundary)
        except ValueError:
            return None
    return resolved


def _exact_source_path(row: Mapping[str, object]) -> Path | None:
    """取得 CLI 明確提供的 exact source.path，不搜尋其他候選路徑。"""

    source = row.get("source")
    if not isinstance(source, Mapping):
        return None
    value = source.get("path")
    if not isinstance(value, str) or not value.strip():
        return None
    return Path(value.strip()).resolve()


def _row_priority(row: Mapping[str, object]) -> tuple[int, str]:
    """依官方 resolution priority 選 logical Plugin 的 deterministic evidence。"""

    exact = _exact_source_path(row)
    if exact is not None:
        return (0, str(exact).casefold())
    version = row.get("version")
    if isinstance(version, str) and version.strip():
        return (1, version.strip().casefold())
    return (2, "")


def _store_segment(value: object, field: str) -> str:
    """驗證 marketplace/name/version 是單一 safe path segment。"""

    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} is required")
    result = value.strip()
    if _STORE_SEGMENT.fullmatch(result) is None or result in {".", ".."}:
        raise ValueError(f"{field} is not a safe path segment")
    return result


def _required_text(value: object, field: str) -> str:
    """驗證 non-empty public identity text。"""

    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} is required")
    return value.strip()


def _optional_text(value: object) -> str | None:
    """將 diagnostic 用的 raw identity 限制為 bounded text。"""

    return value.strip() if isinstance(value, str) and value.strip() else None


def _diagnostic_code(error: ValueError) -> str:
    """只輸出固定錯誤分類，不回顯 identity/path 值。"""

    message = str(error)
    if "identity" in message.casefold():
        return "invalid_identity"
    if "version" in message.casefold():
        return "invalid_version"
    if "marketplace" in message.casefold():
        return "invalid_marketplace"
    return "invalid_name"
