"""Post-hoc UI inventory reconciliation。

這個模組只接受外部提供的 UI reference；它不是 discovery source，也不參與
blind inventory、identity resolution 或 semantic candidate construction。
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class CurrentUiInventoryReference:
    """外部提供的同一 scope logical entity reference。"""

    skills: int
    plugins: int
    apps: int
    mcp: int

    def __post_init__(self) -> None:
        """只接受非負計數；reference 不會被 discovery 讀取。"""

        for field_name in ("skills", "plugins", "apps", "mcp"):
            value = getattr(self, field_name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{field_name} must be a non-negative integer")


@dataclass(frozen=True)
class UiInventoryCategory:
    """單一 UI category 的 raw/unique/dedup/reconciliation 結果。"""

    category: str
    reference_count: int
    raw_count: int
    unique_count: int
    duplicate_count: int

    @property
    def status(self) -> str:
        """只比較同一 logical scope 的 unique entity count。"""

        return "PASS" if self.unique_count == self.reference_count else "COUNT_MISMATCH"


@dataclass(frozen=True)
class CurrentUiInventoryReconciliation:
    """Skills/Plugins/Apps/MCP 的 logical entity reconciliation。"""

    skills: UiInventoryCategory
    plugins: UiInventoryCategory
    apps: UiInventoryCategory
    mcp: UiInventoryCategory

    @property
    def passed(self) -> bool:
        """所有 category 都與外部 reference 一致時才通過。"""

        return all(item.status == "PASS" for item in (self.skills, self.plugins, self.apps, self.mcp))

    def to_mapping(self) -> dict[str, object]:
        """輸出 bounded reconciliation evidence，不輸出 entity payload。"""

        return {
            item.category: {
                "reference_count": item.reference_count,
                "raw_count": item.raw_count,
                "unique_count": item.unique_count,
                "duplicate_count": item.duplicate_count,
                "status": item.status,
            }
            for item in (self.skills, self.plugins, self.apps, self.mcp)
        }


def reconcile_current_ui_inventory(
    *,
    skills: Sequence[object],
    plugins: Sequence[object],
    apps: Sequence[object],
    mcp: Sequence[object],
    reference: CurrentUiInventoryReference,
) -> CurrentUiInventoryReconciliation:
    """以 logical identity 比較外部 UI reference，不依 readiness 篩選。

    這是 post-hoc 操作；呼叫者必須明確傳入 reference，避免 production discovery
    或 blind tests 取得固定 UI expected counts。
    """

    if not isinstance(reference, CurrentUiInventoryReference):
        raise TypeError("reference must be CurrentUiInventoryReference")

    def category(name: str, values: Sequence[object], expected: int) -> UiInventoryCategory:
        if isinstance(values, (str, bytes)) or not isinstance(values, Sequence):
            raise ValueError(f"{name} inventory must be a sequence")
        identities = tuple(_ui_entity_identity(item, name) for item in values)
        unique = frozenset(identities)
        return UiInventoryCategory(name, expected, len(identities), len(unique), len(identities) - len(unique))

    return CurrentUiInventoryReconciliation(
        skills=category("skills", skills, reference.skills),
        plugins=category("plugins", plugins, reference.plugins),
        apps=category("apps", apps, reference.apps),
        mcp=category("mcp", mcp, reference.mcp),
    )


def _ui_entity_identity(value: object, category: str) -> str:
    """取得 category-specific canonical identity；不讀 readiness 欄位。"""

    if isinstance(value, Mapping):
        keys = {
            "skills": ("id", "skill_id"),
            "plugins": ("plugin_id", "id"),
            "apps": ("id", "app_id"),
            "mcp": ("name", "server_id", "id"),
        }[category]
        identity = next((value.get(key) for key in keys if value.get(key) is not None), None)
    else:
        identity = getattr(value, "id", None)
        if identity is None and category == "plugins":
            identity = getattr(value, "plugin_id", None)
        if identity is None and category == "apps":
            identity = getattr(value, "provider_id", None)
        if identity is None and category == "mcp":
            identity = getattr(value, "provider_id", None)
    if not isinstance(identity, str) or not identity.strip():
        raise ValueError(f"{category} entity has no canonical identity")
    return identity.strip().casefold()
