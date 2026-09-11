"""Metadata-only Skill preferences. The Host owns learning and semantic matching."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import hashlib
import json
from pathlib import PureWindowsPath
import re
from collections.abc import Mapping, Sequence

MAX_PREFERENCES = 256
MAX_PREFERENCE_BYTES = 256 * 1024
PREFERENCE_SCHEMA_VERSION = 1
USER_SOURCES = frozenset({"USER_SPECIFIED", "USER_MANUALLY_ADDED"})
_PATTERN = re.compile(r"[a-z][a-z0-9]*(?:_[a-z0-9]+)*")
_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]*")
_HASH = re.compile(r"[0-9a-f]{64}")
_SECRET = re.compile(r"(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,}|sk-(?:proj-)?[A-Za-z0-9_-]{24,})")
_FIELDS = frozenset({"task_pattern", "preferred_skill_id", "learned_from", "use_count", "last_used", "enabled"})
DIAGNOSTIC_CODES = frozenset({
    "MEMORY_UNREADABLE", "MEMORY_INVALID", "MEMORY_TOO_LARGE", "MEMORY_VERSION_UNSUPPORTED",
    "MEMORY_BUSY", "MEMORY_WRITE_FAILED", "MEMORY_LOCK_CLEANUP_FAILED", "MEMORY_CAPACITY",
    "MEMORY_INVALID_LEARNING", "MEMORY_KEY_MISSING", "MEMORY_DISABLED", "MEMORY_STALE",
    "MEMORY_USER_EXCLUDED", "MEMORY_SKILL_MISSING", "MEMORY_SKILL_INELIGIBLE", "MEMORY_NEEDS_DETAIL",
    "MEMORY_HANDOFF_REJECTED", "SELECTION_REVALIDATION_REQUIRED", "HANDOFF_REJECTION_AFTER_ONE_REFRESH",
})
PreferenceKey = tuple[str, str]


def validate_skill_id(value: object) -> str:
    if (not isinstance(value, str) or not 1 <= len(value) <= 256
            or _ID.fullmatch(value) is None or PureWindowsPath(value).drive or _SECRET.search(value)):
        raise ValueError("preference Skill ID is invalid")
    return value


def validate_pattern(value: object) -> str:
    if (not isinstance(value, str) or not 1 <= len(value) <= 64
            or _PATTERN.fullmatch(value) is None or _SECRET.search(value)):
        raise ValueError("preference task pattern is invalid")
    return value


def validate_date(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError("preference date must be an ISO date")
    try:
        valid = date.fromisoformat(value).isoformat() == value
    except ValueError:
        valid = False
    if not valid:
        raise ValueError("preference date must be an ISO date")
    return value


def bounded_sequence(value: object) -> tuple:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence) or len(value) > MAX_PREFERENCES:
        raise ValueError("preference sequence is invalid or too large")
    return tuple(value)


def preference_key(value: object) -> PreferenceKey:
    parts = bounded_sequence(value)
    if len(parts) != 2:
        raise ValueError("preference key must contain a pattern and Skill ID")
    return validate_pattern(parts[0]), validate_skill_id(parts[1])


@dataclass(frozen=True)
class SkillPreference:
    task_pattern: str
    preferred_skill_id: str
    learned_from: str
    use_count: int
    last_used: str
    enabled: bool = True

    def __post_init__(self) -> None:
        validate_pattern(self.task_pattern)
        validate_skill_id(self.preferred_skill_id)
        if not isinstance(self.learned_from, str) or self.learned_from not in USER_SOURCES:
            raise ValueError("preference learning requires a user source")
        if type(self.use_count) is not int or not 1 <= self.use_count <= 2**31 - 1:
            raise ValueError("preference use count is invalid")
        validate_date(self.last_used)
        if type(self.enabled) is not bool:
            raise ValueError("preference enabled must be boolean")

    @property
    def key(self) -> PreferenceKey:
        return self.task_pattern, self.preferred_skill_id

    def to_mapping(self) -> dict[str, object]:
        return {name: getattr(self, name) for name in sorted(_FIELDS)}

    @classmethod
    def from_mapping(cls, value: object) -> SkillPreference:
        if not isinstance(value, Mapping) or set(value) != _FIELDS:
            raise ValueError("preference record fields are invalid")
        return cls(**value)


@dataclass(frozen=True)
class PreferenceSnapshot:
    preferences: tuple[SkillPreference, ...] = ()
    diagnostics: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        records = bounded_sequence(self.preferences)
        if any(not isinstance(item, SkillPreference) for item in records):
            raise ValueError("preference snapshot requires validated records")
        if len({item.key for item in records}) != len(records):
            raise ValueError("duplicate preference keys")
        diagnostics = bounded_sequence(self.diagnostics)
        if any(not isinstance(code, str) or code not in DIAGNOSTIC_CODES for code in diagnostics):
            raise ValueError("invalid preference diagnostic")
        object.__setattr__(self, "preferences", tuple(sorted(records, key=lambda item: item.key)))
        object.__setattr__(self, "diagnostics", tuple(sorted(set(diagnostics))))

    def to_mapping(self) -> dict[str, object]:
        """Only this allowlisted projection is persisted; diagnostics stay transient."""
        return {"schema_version": PREFERENCE_SCHEMA_VERSION,
                "preferences": [item.to_mapping() for item in self.preferences]}

    @property
    def fingerprint(self) -> str:
        payload = json.dumps(self.to_mapping(), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class SkillPreferenceInput:
    """Host-selected memory keys, never a Python semantic query or file path."""

    task_patterns: tuple[str, ...]
    snapshot: PreferenceSnapshot
    matched_preferences: tuple[PreferenceKey, ...]
    task_fingerprint: str
    sweep_fingerprint: str
    memory_fingerprint: str
    excluded_skill_ids: tuple[str, ...] = ()
    enabled: bool = True

    def __post_init__(self) -> None:
        if not isinstance(self.snapshot, PreferenceSnapshot):
            raise TypeError("preference input requires a PreferenceSnapshot")
        patterns = tuple(validate_pattern(item) for item in bounded_sequence(self.task_patterns))
        matches = tuple(preference_key(item) for item in bounded_sequence(self.matched_preferences))
        excluded = tuple(validate_skill_id(item) for item in bounded_sequence(self.excluded_skill_ids))
        if matches and not patterns:
            raise ValueError("matched preferences require Host task patterns")
        for value in (self.task_fingerprint, self.sweep_fingerprint, self.memory_fingerprint):
            if not isinstance(value, str) or _HASH.fullmatch(value) is None:
                raise ValueError("preference binding must be a SHA-256 fingerprint")
        if type(self.enabled) is not bool:
            raise ValueError("preference input enabled must be boolean")
        object.__setattr__(self, "task_patterns", tuple(sorted(set(patterns))))
        object.__setattr__(self, "matched_preferences", tuple(sorted(set(matches))))
        object.__setattr__(self, "excluded_skill_ids", tuple(sorted(set(excluded))))
