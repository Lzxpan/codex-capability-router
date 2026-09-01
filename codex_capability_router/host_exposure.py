"""同一 Host session 的 Skill exposure evidence 與 freshness 驗證。

這個模組只處理 Host adapter 提供的 typed observation；它不執行 Skill、
不決定 Skill formal availability，也不保存 session state。
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re


_CANONICAL_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]*$")
_FINGERPRINT = re.compile(r"^[0-9a-f]{64}$")
_HOST_ADAPTER_TOKEN = object()

# 修改紀錄（2026-08-31，Steve Peng）
# 原始內容：Router 沒有 Host-trusted Skill exposure/freshness observation contract。
# 修改原因：Skill formal availability 改由 trusted-root discovery/handoff 決定，Host evidence 僅保留稽核觀測價值。
# 修改後功能：提供只由 designated adapter 建立的 typed envelope、path/content binding、snapshot fingerprint 與 A/B observation；不保存 session state，也不成為 Skill availability gate。


class HostExposureError(ValueError):
    """Host exposure evidence 不符合 trusted adapter contract。"""


def canonicalize_host_path(value: str | Path) -> str:
    """以 platform-safe 方式正規化 Host path，僅供內部 binding 比對。

    使用方式：adapter 在建立 envelope 時呼叫；結果不得寫入 Receipt 或
    public diagnostic。無法安全取得 absolute/resolved path 時直接失敗。
    """

    if isinstance(value, Path):
        candidate = value
    elif isinstance(value, str) and value.strip():
        candidate = Path(value)
    else:
        raise HostExposureError("Host path must be a non-empty path")
    try:
        resolved = candidate.resolve(strict=False)
    except (OSError, RuntimeError) as error:
        raise HostExposureError("Host path could not be safely canonicalized") from error
    normalized = os.path.normpath(os.path.normcase(str(resolved)))
    if not os.path.isabs(normalized):
        raise HostExposureError("Host path must be absolute after canonicalization")
    return normalized


def _require_id(value: object) -> str:
    if not isinstance(value, str) or _CANONICAL_ID.fullmatch(value.strip()) is None:
        raise HostExposureError("Host Skill ID must be canonical")
    return value.strip()


def _require_fingerprint(value: object, field: str) -> str:
    if not isinstance(value, str) or _FINGERPRINT.fullmatch(value) is None:
        raise HostExposureError(f"{field} must be a SHA-256 fingerprint")
    return value


def _require_opaque(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > 256:
        raise HostExposureError(f"{field} must be bounded opaque text")
    if "/" in value or "\\" in value:
        raise HostExposureError(f"{field} must not contain a path")
    if any(marker in value.casefold() for marker in ("api_key=", "password=", "secret=", "token=")):
        raise HostExposureError(f"{field} must not contain secret-like text")
    return value.strip()


@dataclass(frozen=True)
class HostSkillExposureRecord:
    """單一 Host `skills/list` record 的 typed、非 public-path projection。"""

    id: str
    enabled: bool
    source: str
    session_id: str
    workspace: str | Path
    cwd: str | Path
    path: str | Path
    content_fingerprint: str
    declaration_fingerprint: str | None = None

    def __post_init__(self) -> None:
        """驗證 canonical ID、boolean exposure 與內部 binding evidence。"""

        object.__setattr__(self, "id", _require_id(self.id))
        if not isinstance(self.enabled, bool):
            raise HostExposureError("Host enabled must be boolean")
        object.__setattr__(self, "source", _require_opaque(self.source, "source"))
        object.__setattr__(self, "session_id", _require_opaque(self.session_id, "session_id"))
        workspace = canonicalize_host_path(self.workspace)
        cwd = canonicalize_host_path(self.cwd)
        path = canonicalize_host_path(self.path)
        if not _path_is_within(path, workspace):
            raise HostExposureError("Skill path is outside the Host workspace")
        object.__setattr__(self, "workspace", workspace)
        object.__setattr__(self, "cwd", cwd)
        object.__setattr__(self, "path", path)
        object.__setattr__(self, "content_fingerprint", _require_fingerprint(self.content_fingerprint, "content_fingerprint"))
        expected = _declaration_fingerprint(
            id=self.id,
            enabled=self.enabled,
            source=self.source,
            session_id=self.session_id,
            workspace=workspace,
            cwd=cwd,
            path=path,
        )
        if self.declaration_fingerprint is not None:
            _require_fingerprint(self.declaration_fingerprint, "declaration_fingerprint")
            if self.declaration_fingerprint != expected:
                raise HostExposureError("declaration fingerprint does not match Host record")
        object.__setattr__(self, "declaration_fingerprint", expected)

    def internal_mapping(self) -> dict[str, object]:
        """回傳只供 internal fingerprint/revalidation 使用的 mapping。"""

        return {
            "id": self.id,
            "enabled": self.enabled,
            "source": self.source,
            "session_id": self.session_id,
            "workspace": self.workspace,
            "cwd": self.cwd,
            "path": self.path,
            "content_fingerprint": self.content_fingerprint,
            "declaration_fingerprint": self.declaration_fingerprint,
        }


@dataclass(frozen=True, init=False)
class HostSkillExposureEnvelope:
    """只可由 designated Host adapter 建立的 fresh exposure snapshot。"""

    session_id: str
    workspace: str
    cwd: str
    records: tuple[HostSkillExposureRecord, ...]
    semantics_certified: bool
    generation: str | None
    snapshot_fingerprint: str
    _trusted: object

    def __init__(
        self,
        *,
        session_id: str,
        workspace: str,
        cwd: str,
        records: tuple[HostSkillExposureRecord, ...],
        semantics_certified: bool,
        generation: str | None,
        snapshot_fingerprint: str,
        _trusted: object,
    ) -> None:
        """私有 constructor；一般 caller 不可直接建立 envelope。"""

        if _trusted is not _HOST_ADAPTER_TOKEN:
            raise TypeError("HostSkillExposureEnvelope requires designated Host adapter")
        if not isinstance(records, tuple) or not all(isinstance(item, HostSkillExposureRecord) for item in records):
            raise TypeError("Host exposure records must be typed HostSkillExposureRecord values")
        if not isinstance(semantics_certified, bool) or not semantics_certified:
            raise HostExposureError("Host enabled semantics must be certified")
        if generation is not None:
            generation = _require_opaque(generation, "generation")
        session = _require_opaque(session_id, "session_id")
        workspace_value = canonicalize_host_path(workspace)
        cwd_value = canonicalize_host_path(cwd)
        if len({item.id for item in records}) != len(records):
            raise HostExposureError("Host exposure IDs must be unique")
        if any(item.session_id != session or item.workspace != workspace_value or item.cwd != cwd_value for item in records):
            raise HostExposureError("Host exposure records do not share the envelope binding")
        expected = _snapshot_fingerprint(session, workspace_value, cwd_value, records, generation)
        if snapshot_fingerprint != expected:
            raise HostExposureError("Host exposure snapshot fingerprint is invalid")
        object.__setattr__(self, "session_id", session)
        object.__setattr__(self, "workspace", workspace_value)
        object.__setattr__(self, "cwd", cwd_value)
        object.__setattr__(self, "records", tuple(records))
        object.__setattr__(self, "semantics_certified", semantics_certified)
        object.__setattr__(self, "generation", generation)
        object.__setattr__(self, "snapshot_fingerprint", snapshot_fingerprint)
        object.__setattr__(self, "_trusted", _HOST_ADAPTER_TOKEN)

    @property
    def exposed_records(self) -> tuple[HostSkillExposureRecord, ...]:
        """回傳 Host declaration 中 enabled/exposed 的 records。"""

        return tuple(record for record in self.records if record.enabled)

    @property
    def exposed_ids(self) -> tuple[str, ...]:
        """回傳穩定排序的 Host-exposed canonical IDs。"""

        return tuple(sorted((record.id for record in self.exposed_records), key=lambda value: (value.casefold(), value)))

    def record(self, skill_id: str) -> HostSkillExposureRecord | None:
        """依 canonical ID 取得 Host record，不回傳 public path。"""

        return next((record for record in self.records if record.id == skill_id), None)


class HostSkillExposureAdapter:
    """Designated Host adapter；每次 route 只建立 fresh envelope，不保存狀態。"""

    @staticmethod
    def create_envelope(
        *,
        session_id: str,
        workspace: str | Path,
        cwd: str | Path,
        records: Sequence[HostSkillExposureRecord],
        generation: str | None = None,
        semantics_certified: bool = False,
    ) -> HostSkillExposureEnvelope:
        """將 typed Host response 建立為 trusted envelope。"""

        tuple_records = tuple(records)
        workspace_value = canonicalize_host_path(workspace)
        cwd_value = canonicalize_host_path(cwd)
        session_value = _require_opaque(session_id, "session_id")
        fingerprint = _snapshot_fingerprint(session_value, workspace_value, cwd_value, tuple_records, generation)
        if not semantics_certified:
            raise HostExposureError("Host enabled semantics require explicit P0 certification")
        return HostSkillExposureEnvelope(
            session_id=session_value,
            workspace=workspace_value,
            cwd=cwd_value,
            records=tuple_records,
            semantics_certified=True,
            generation=generation,
            snapshot_fingerprint=fingerprint,
            _trusted=_HOST_ADAPTER_TOKEN,
        )

    @staticmethod
    def from_skills_list(
        payload: Mapping[str, object],
        *,
        session_id: str,
        workspace: str | Path,
        cwd: str | Path,
        canonical_ids: Mapping[str, str],
        generation: str | None = None,
        semantics_certified: bool = False,
    ) -> HostSkillExposureEnvelope:
        """將 Host typed `skills/list` response 轉成 envelope。

        `canonical_ids` 必須是 Host adapter 已認證的 exact name-to-ID binding；
        不會由 display name、目錄名稱或 path 猜測 canonical ID。
        """

        if not isinstance(payload, Mapping) or not isinstance(canonical_ids, Mapping):
            raise HostExposureError("skills/list adapter requires typed mappings")
        groups = payload.get("data")
        if not isinstance(groups, Sequence) or isinstance(groups, (str, bytes)):
            raise HostExposureError("skills/list response data is invalid")
        records: list[HostSkillExposureRecord] = []
        for group in groups:
            if not isinstance(group, Mapping):
                raise HostExposureError("skills/list group is invalid")
            if group.get("errors"):
                raise HostExposureError("skills/list response contains errors")
            skills = group.get("skills")
            if not isinstance(skills, Sequence) or isinstance(skills, (str, bytes)):
                raise HostExposureError("skills/list skills is invalid")
            for skill in skills:
                if not isinstance(skill, Mapping):
                    raise HostExposureError("skills/list Skill record is invalid")
                name = skill.get("name")
                identifier = skill.get("id", skill.get("canonical_id"))
                if identifier is None and isinstance(name, str):
                    identifier = canonical_ids.get(name)
                if not isinstance(identifier, str) or identifier not in canonical_ids.values():
                    raise HostExposureError("skills/list record lacks an exact canonical ID binding")
                # 修改紀錄（2026-08-31，Steve Peng）
                # 原始內容：只在 name 恰好出現在 mapping 時檢查 ID，一個未知 name 仍可攜帶合法 value 混入。
                # 修改原因：Host skills/list 的 display/name 與 canonical ID 必須是 adapter 已認證的 exact binding。
                # 修改後功能：name 存在時必須能由 canonical_ids 精確解析；不接受任意 caller 組合。
                if name is not None:
                    if not isinstance(name, str) or name not in canonical_ids or canonical_ids[name] != identifier:
                        raise HostExposureError("skills/list name and canonical ID binding disagree")
                enabled = skill.get("enabled")
                path = skill.get("path")
                if not isinstance(enabled, bool) or not isinstance(path, (str, Path)):
                    raise HostExposureError("skills/list record lacks typed enabled/path fields")
                skill_path = Path(path)
                if skill_path.is_dir():
                    skill_path = skill_path / "SKILL.md"
                try:
                    content_fingerprint = hashlib.sha256(skill_path.read_bytes()).hexdigest()
                except (OSError, UnicodeError) as error:
                    raise HostExposureError("skills/list Skill content cannot be safely bound") from error
                records.append(
                    HostSkillExposureRecord(
                        id=identifier,
                        enabled=enabled,
                        source="runtime:host-skills-list",
                        session_id=session_id,
                        workspace=workspace,
                        cwd=cwd,
                        path=skill_path,
                        content_fingerprint=content_fingerprint,
                    )
                )
        return HostSkillExposureAdapter.create_envelope(
            session_id=session_id,
            workspace=workspace,
            cwd=cwd,
            records=records,
            generation=generation,
            semantics_certified=semantics_certified,
        )


def revalidate_host_exposure(
    prepared: HostSkillExposureEnvelope,
    fresh: HostSkillExposureEnvelope,
    selected_skill_ids: Iterable[str],
) -> None:
    """供觀測 consumers deterministic 比對 Envelope A/B；不決定 Skill formal availability。"""

    if not isinstance(prepared, HostSkillExposureEnvelope) or not isinstance(fresh, HostSkillExposureEnvelope):
        raise HostExposureError("fresh Host exposure evidence is required")
    if prepared.session_id != fresh.session_id or prepared.workspace != fresh.workspace or prepared.cwd != fresh.cwd:
        raise HostExposureError("Host exposure session/workspace binding is stale")
    if prepared.snapshot_fingerprint != fresh.snapshot_fingerprint:
        raise HostExposureError("Host exposure declaration is stale")
    for skill_id in selected_skill_ids:
        before = prepared.record(skill_id)
        after = fresh.record(skill_id)
        if before is None or after is None or not after.enabled:
            raise HostExposureError("selected Skill is no longer Host-exposed")
        if before.declaration_fingerprint != after.declaration_fingerprint:
            raise HostExposureError("selected Skill declaration fingerprint is stale")
        if before.content_fingerprint != after.content_fingerprint:
            raise HostExposureError("selected Skill content fingerprint is stale")


def _path_is_within(path: str, parent: str) -> bool:
    """判斷 canonical path 是否位於 workspace 內。"""

    try:
        Path(path).relative_to(Path(parent))
    except ValueError:
        return False
    return True


def _declaration_fingerprint(**values: object) -> str:
    encoded = json.dumps(values, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _snapshot_fingerprint(
    session_id: str,
    workspace: str,
    cwd: str,
    records: Sequence[HostSkillExposureRecord],
    generation: str | None,
) -> str:
    payload = {
        "session_id": session_id,
        "workspace": workspace,
        "cwd": cwd,
        "generation": generation,
        "records": [record.internal_mapping() for record in sorted(records, key=lambda item: (item.id.casefold(), item.id))],
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
