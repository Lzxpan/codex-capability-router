"""Explicit Host-owned local persistence; route() never calls this module."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
import json
import os
from pathlib import Path
import tempfile

from .inventory import SkillInventory
from .selection import _eligible_record
from .preferences import (
    MAX_PREFERENCE_BYTES, MAX_PREFERENCES, PREFERENCE_SCHEMA_VERSION, USER_SOURCES,
    PreferenceSnapshot, SkillPreference, bounded_sequence, preference_key,
    validate_date, validate_skill_id,
)


@dataclass(frozen=True)
class PreferenceWriteResult:
    snapshot: PreferenceSnapshot
    written: bool = False
    diagnostics: tuple[str, ...] = ()


def _path(path: Path | None) -> Path:
    if path is None:
        directory = Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex")
        path = directory / "capability-router" / "skill-preferences.json"
    if not isinstance(path, Path) or str(path).startswith(("\\\\", "//")):
        raise ValueError("preference storage requires a local Path")
    return path


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result = dict(pairs)
    if len(result) != len(pairs):
        raise ValueError("duplicate JSON fields")
    return result


def load_preferences(path: Path | None = None) -> PreferenceSnapshot:
    """Bounded read; errors contain codes, never paths or rejected contents."""
    try:
        with _path(path).open("rb") as stream:
            raw = stream.read(MAX_PREFERENCE_BYTES + 1)
    except FileNotFoundError:
        return PreferenceSnapshot()
    except (OSError, ValueError):
        return PreferenceSnapshot(diagnostics=("MEMORY_UNREADABLE",))
    if len(raw) > MAX_PREFERENCE_BYTES:
        return PreferenceSnapshot(diagnostics=("MEMORY_TOO_LARGE",))
    if not raw.strip():
        return PreferenceSnapshot()
    try:
        payload = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_object)
        if not isinstance(payload, dict) or set(payload) != {"schema_version", "preferences"}:
            raise ValueError("invalid memory fields")
        if type(payload["schema_version"]) is not int or payload["schema_version"] != PREFERENCE_SCHEMA_VERSION:
            return PreferenceSnapshot(diagnostics=("MEMORY_VERSION_UNSUPPORTED",))
        records = tuple(SkillPreference.from_mapping(item) for item in bounded_sequence(payload["preferences"]))
        return PreferenceSnapshot(records)
    except (ValueError, TypeError, UnicodeError, RecursionError):
        return PreferenceSnapshot(diagnostics=("MEMORY_INVALID",))


def _mutate(path: Path | None, transform, *, clear_all: bool = False) -> PreferenceWriteResult:
    temporary = None
    owned_lock = False
    current = PreferenceSnapshot()
    result = PreferenceWriteResult(current)
    try:
        target = _path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        lock = target.with_name(target.name + ".lock")
        # ponytail: one local writer; contention skips learning instead of adding a retry service.
        with lock.open("xb"):
            owned_lock = True
        current = load_preferences(target)
        if current.diagnostics and not clear_all:
            result = PreferenceWriteResult(current, diagnostics=current.diagnostics)
        else:
            updated, diagnostics = transform(current)
            if updated.to_mapping() == current.to_mapping() and not current.diagnostics:
                result = PreferenceWriteResult(updated, diagnostics=diagnostics)
            else:
                raw = (json.dumps(updated.to_mapping(), ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")
                if len(raw) > MAX_PREFERENCE_BYTES:
                    raise ValueError("memory exceeds byte limit")
                with tempfile.NamedTemporaryFile(mode="wb", dir=target.parent, prefix=".skill-preferences-", delete=False) as stream:
                    temporary = Path(stream.name)
                    stream.write(raw)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(temporary, target)
                temporary = None
                result = PreferenceWriteResult(updated, written=True, diagnostics=diagnostics)
    except FileExistsError:
        result = PreferenceWriteResult(current, diagnostics=("MEMORY_BUSY",))
    except (OSError, ValueError):
        result = PreferenceWriteResult(current, diagnostics=("MEMORY_WRITE_FAILED",))
    finally:
        if temporary is not None:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                result = replace(result, diagnostics=(*result.diagnostics, "MEMORY_WRITE_FAILED"))
        if owned_lock:
            try:
                lock.unlink()
            except OSError:
                result = replace(result, diagnostics=(*result.diagnostics, "MEMORY_LOCK_CLEANUP_FAILED"))
    return result


# 修改人：Steve Peng；修改日期：2026-09-11。
# 修改原因：控制流程 Skill 可能被誤學；修改前只檢查使用者來源，修改後依正式 eligibility 逐項拒絕。
# 功能：以當輪 inventory 查核學習與使用確認；回傳 snapshot、寫入狀態與不含私密資料的診斷。
# 參數：path 為本機位置，learning_decision／confirmed_memory_uses 為有界鍵值，observed_on 為 UTC 日期。
# 使用範例：update_preferences(path, skill_inventory=current_inventory, observed_on=utc_date, ...)。
# 注意：未提供 inventory 就保留既有資料；Host 負責 user_observations 來源與 pattern 的通用語意。
def update_preferences(
    path: Path | None = None, *, learning_decision=(), user_observations=(),
    confirmed_memory_uses=(), observed_on: str, skill_inventory: SkillInventory | None = None,
) -> PreferenceWriteResult:
    """Host supplies selected pairs and observed {preferred_skill_id, source} metadata.

    The Host supplies current trusted inventory and certifies user-channel origin,
    generic patterns, actual memory use and once-per-task delivery. No prompt/history
    is accepted; inventory metadata is checked in memory and never persisted.
    """
    try:
        if skill_inventory is not None and not isinstance(skill_inventory, SkillInventory):
            raise ValueError("learning requires a SkillInventory")
        today = validate_date(observed_on)
        learning = tuple(sorted({preference_key(item) for item in bounded_sequence(learning_decision)}))
        used = tuple(sorted({preference_key(item) for item in bounded_sequence(confirmed_memory_uses)}))
        observations: dict[str, str] = {}
        for item in bounded_sequence(user_observations):
            if not isinstance(item, Mapping) or set(item) != {"preferred_skill_id", "source"}:
                raise ValueError("invalid user observation")
            skill_id = validate_skill_id(item["preferred_skill_id"])
            source = item["source"]
            if not isinstance(source, str) or source not in USER_SOURCES:
                raise ValueError("learning requires a user observation")
            observations[skill_id] = min(source, observations.get(skill_id, source))
        if any(skill_id not in observations for _, skill_id in learning):
            raise ValueError("learning decision lacks user evidence")
    except (ValueError, TypeError):
        return PreferenceWriteResult(PreferenceSnapshot(), diagnostics=("MEMORY_INVALID_LEARNING",))

    # ponytail: 每次更新只查當輪 inventory；未提供 metadata 就拒絕該項，不建立另一份名稱黑名單。
    inventory_records = {record.id: record for record in skill_inventory.records} if skill_inventory else {}
    present_ids = {record.id for record in skill_inventory.present_records} if skill_inventory else set()
    rejected_targets = {}
    for _, skill_id in (*learning, *used):
        record = inventory_records.get(skill_id)
        if record is not None and not _eligible_record(record):
            rejected_targets[skill_id] = "MEMORY_SKILL_INELIGIBLE"
        elif record is None or skill_id not in present_ids:
            rejected_targets[skill_id] = "MEMORY_SKILL_MISSING"

    def transform(current):
        records = {item.key: item for item in current.preferences}
        diagnostics = set()
        for key in learning:
            # 逐項拒絕；同批合法偏好仍能新增或更新，診斷不帶入來源內容或路徑。
            if key[1] in rejected_targets:
                diagnostics.add(rejected_targets[key[1]])
                continue
            previous = records.get(key)
            if previous is not None:
                records[key] = replace(previous, use_count=min(previous.use_count + 1, 2**31 - 1),
                                       last_used=max(today, previous.last_used))
            elif len(records) < MAX_PREFERENCES:
                records[key] = SkillPreference(*key, observations[key[1]], 1, today)
            else:
                diagnostics.add("MEMORY_CAPACITY")
        for key in used:
            previous = records.get(key)
            if previous is None:
                diagnostics.add("MEMORY_KEY_MISSING")
            elif key[1] in rejected_targets:
                diagnostics.add(rejected_targets[key[1]])
            elif previous.enabled:
                records[key] = replace(previous, last_used=max(today, previous.last_used))
        return PreferenceSnapshot(tuple(records.values())), tuple(sorted(diagnostics))

    return _mutate(path, transform)


def set_preference_enabled(path: Path | None, key, enabled: bool) -> PreferenceWriteResult:
    key = preference_key(key)
    if type(enabled) is not bool:
        raise ValueError("preference enabled must be boolean")

    def transform(current):
        if key not in {item.key for item in current.preferences}:
            return current, ("MEMORY_KEY_MISSING",)
        return PreferenceSnapshot(tuple(replace(item, enabled=enabled) if item.key == key else item
                                        for item in current.preferences)), ()

    return _mutate(path, transform)


def clear_preferences(path: Path | None = None, key=None) -> PreferenceWriteResult:
    """Explicit clear-all also replaces corrupt data; ordinary updates never do."""
    key = None if key is None else preference_key(key)

    def transform(current):
        if key is None:
            return PreferenceSnapshot(), ()
        if key not in {item.key for item in current.preferences}:
            return current, ("MEMORY_KEY_MISSING",)
        return PreferenceSnapshot(tuple(item for item in current.preferences if item.key != key)), ()

    return _mutate(path, transform, clear_all=key is None)
