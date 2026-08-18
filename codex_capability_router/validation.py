"""Phase 2 canonical capability record 的最小邊界驗證。"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from pathlib import PurePosixPath, PureWindowsPath
import re

from .models import CapabilityKind, CapabilityRecord, CapabilityStatus


# 修改紀錄（2026-08-17，Steve Peng）
# 原始內容：Phase 1 沒有輸入 payload 驗證。
# 修改原因：避免 malformed、path 或不可靠狀態直接進入 registry。
# 修改後功能：只接受 canonical public fields，缺少狀態時保留 unknown。
# 修改紀錄（2026-08-18，Steve Peng）
# 原始內容：canonical record 沒有可驗證的雙語 Function metadata。
# 修改原因：Phase 5D explanation 必須只使用 registry 已提供的功能說明，不得從 category 或 trigger 幻想內容。
# 修改後功能：接受 optional function.en/function.zh-TW，嚴格限制欄位、文字與 private path。
# 修改紀錄（2026-08-18，Steve Peng）
# 原始內容：canonical record 無法標記 Router controller、router aliases 或 internal discovery support。
# 修改原因：Phase 5E 需要在 untrusted record 邊界明確驗證這些 selection exclusion metadata。
# 修改後功能：接受嚴格 boolean/文字序列 metadata，仍拒絕 unsupported、敏感值與 absolute path。

_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]*$")
_SENSITIVE_FIELD_NAMES = {"api_key", "apikey", "credential", "credentials", "password", "secret", "token"}
_ALLOWED_RECORD_FIELDS = {
    "id",
    "name",
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
}


def _require_text(value: object, field: str, *, identifier: bool = False) -> str:
    """驗證非空文字欄位，錯誤訊息不回傳原始值。"""

    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field}: must be a non-empty string")
    result = value.strip()
    if identifier and not _IDENTIFIER.fullmatch(result):
        raise ValueError(f"{field}: invalid identifier")
    if _is_absolute_path(result):
        raise ValueError(f"{field}: absolute paths are not allowed")
    return result


def _is_absolute_path(value: str) -> bool:
    """辨識 Windows 與 POSIX absolute path，不讀取該路徑。"""

    return PureWindowsPath(value).is_absolute() or PurePosixPath(value).is_absolute()


def _text_sequence(value: object, field: str) -> tuple[str, ...]:
    """驗證 canonical 陣列欄位並轉成 tuple。"""

    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise ValueError(f"{field}: must be a sequence of strings")
    values: list[str] = []
    for item in value:
        values.append(_require_text(item, field))
    return tuple(values)


def _enum_value(value: object, field: str, enum_type: type[CapabilityKind] | type[CapabilityStatus], default: str) -> CapabilityKind | CapabilityStatus:
    """將 enum input 正規化；省略狀態時只使用明確的 default。"""

    if value is None:
        value = default
    if isinstance(value, enum_type):
        return value
    if not isinstance(value, str):
        raise ValueError(f"{field}: invalid enum value")
    try:
        return enum_type(value)
    except ValueError as error:
        raise ValueError(f"{field}: invalid enum value") from error


def _last_verified(value: object) -> str | None:
    """驗證 ISO timestamp；未知或未提供時保持 None。"""

    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError("last_verified: must be an ISO timestamp or null")
    candidate = value.strip()
    try:
        datetime.fromisoformat(candidate.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError("last_verified: invalid ISO timestamp") from error
    return candidate


def record_from_mapping(
    payload: Mapping[str, object],
    *,
    source: str | None = None,
    default_kind: CapabilityKind = CapabilityKind.UNKNOWN,
) -> CapabilityRecord:
    """將 untrusted mapping 驗證成 canonical record。

    使用方式：discovery 只傳入明確允許的欄位，manual import 可用 source
    覆蓋輸入中的 source，避免使用者提供的 raw path 進入公開 record。
    """

    if not isinstance(payload, Mapping):
        raise ValueError("record: must be an object")
    if _SENSITIVE_FIELD_NAMES.intersection(str(key).lower() for key in payload):
        raise ValueError("record: sensitive fields are not accepted")
    unsupported = set(payload) - _ALLOWED_RECORD_FIELDS
    if unsupported:
        raise ValueError("record: unsupported fields are not accepted")

    record_source = source if source is not None else payload.get("source")
    function_en, function_zh_tw = _localized_function(payload.get("function"))
    return CapabilityRecord(
        id=_require_text(payload.get("id", payload.get("name")), "id", identifier=True),
        name=_require_text(payload.get("name"), "name"),
        kind=_enum_value(payload.get("kind"), "kind", CapabilityKind, default_kind.value),  # type: ignore[arg-type]
        status=_enum_value(payload.get("status"), "status", CapabilityStatus, CapabilityStatus.UNKNOWN.value),  # type: ignore[arg-type]
        categories=_text_sequence(payload.get("categories", ()), "categories"),
        triggers=_text_sequence(payload.get("triggers", ()), "triggers"),
        priority=_priority(payload.get("priority", 0)),
        overlap_group=_optional_text(payload.get("overlap_group"), "overlap_group"),
        preferred_for=_text_sequence(payload.get("preferred_for", ()), "preferred_for"),
        requires=_text_sequence(payload.get("requires", ()), "requires"),
        source=_require_text(record_source, "source"),
        last_verified=_last_verified(payload.get("last_verified")),
        version=_optional_text(payload.get("version"), "version"),
        limitations=_text_sequence(payload.get("limitations", ()), "limitations"),
        provenance=_text_sequence(payload.get("provenance", ()), "provenance"),
        confidence=_confidence(payload.get("confidence")),
        conflicts=_text_sequence(payload.get("conflicts", ()), "conflicts"),
        evidence=_text_sequence(payload.get("evidence", ()), "evidence"),
        recommendation_only=_boolean(payload.get("recommendation_only", False), "recommendation_only"),
        function_en=function_en,
        function_zh_tw=function_zh_tw,
        controller=_boolean(payload.get("controller", False), "controller"),
        aliases=_text_sequence(payload.get("aliases", ()), "aliases"),
        routing_support=_boolean(payload.get("routing_support", False), "routing_support"),
    )


def validate_source_label(value: object) -> str:
    """驗證 caller 提供的 abstract source label，避免 raw path 外洩。"""

    return _require_text(value, "source")


def _priority(value: object) -> int:
    """驗證 deterministic integer priority。"""

    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError("priority: must be an integer")
    return value


def _optional_text(value: object, field: str) -> str | None:
    """驗證可為 null 的文字欄位。"""

    if value is None:
        return None
    return _require_text(value, field)


def _localized_function(value: object) -> tuple[str | None, str | None]:
    """驗證 optional bilingual Function object；不接受未列出的 language key。"""

    if value is None:
        return None, None
    if not isinstance(value, Mapping):
        raise ValueError("function: must be an object")
    unsupported = set(value) - {"en", "zh-TW"}
    if unsupported:
        raise ValueError("function: unsupported language fields are not accepted")
    function_en = _optional_text(value.get("en"), "function.en")
    function_zh_tw = _optional_text(value.get("zh-TW"), "function.zh-TW")
    if function_en is None and function_zh_tw is None:
        raise ValueError("function: at least one locale value is required")
    return function_en, function_zh_tw


def _confidence(value: object) -> float | None:
    """驗證可選 confidence，拒絕 bool、NaN 與超出 0..1 的猜測值。"""

    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("confidence: must be a number between 0.0 and 1.0")
    if not 0.0 <= float(value) <= 1.0:
        raise ValueError("confidence: must be a number between 0.0 and 1.0")
    return float(value)


def _boolean(value: object, field: str) -> bool:
    """驗證明確 boolean 欄位，不將 truthy 值猜測為授權標記。"""

    if not isinstance(value, bool):
        raise ValueError(f"{field}: must be a boolean")
    return value
