"""Phase 1 的 LLM TaskAnalysis 結構化契約。"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import PurePosixPath, PureWindowsPath
import re


_TASK_ANALYSIS_FIELDS = frozenset(
    {
        "task_summary",
        "work_items",
        "deliverables",
        "constraints",
        "quality_expectations",
    }
)
_ITEM_FIELDS = (
    "work_items",
    "deliverables",
    "constraints",
    "quality_expectations",
)
_MAX_SUMMARY_LENGTH = 2048
_MAX_ITEM_LENGTH = 512
_MAX_ITEMS = 16
_SENSITIVE_TEXT = re.compile(r"(?:api[_-]?key|password|secret|token|credential)\s*[:=]", re.IGNORECASE)


@dataclass(frozen=True)
class TaskAnalysis:
    """已通過 strict schema 的 TaskAnalysis；集合欄位固定為 tuple。"""

    task_summary: str
    work_items: tuple[str, ...]
    deliverables: tuple[str, ...]
    constraints: tuple[str, ...]
    quality_expectations: tuple[str, ...]

    def __post_init__(self) -> None:
        """驗證並複製欄位，避免 caller 在 validated 後改寫內容。"""

        object.__setattr__(
            self,
            "task_summary",
            _bounded_text(self.task_summary, "task_summary", _MAX_SUMMARY_LENGTH),
        )
        for field_name in _ITEM_FIELDS:
            object.__setattr__(
                self,
                field_name,
                _bounded_items(getattr(self, field_name), field_name),
            )

    def to_mapping(self) -> dict[str, object]:
        """輸出新的 mapping/list 副本，不暴露 immutable contract 內部容器。"""

        return {
            "task_summary": self.task_summary,
            "work_items": list(self.work_items),
            "deliverables": list(self.deliverables),
            "constraints": list(self.constraints),
            "quality_expectations": list(self.quality_expectations),
        }


def validate_task_analysis(payload: Mapping[str, object]) -> TaskAnalysis:
    """驗證 LLM structured output，拒絕缺漏、額外欄位與未界定型別。"""

    if not isinstance(payload, Mapping) or set(payload) != _TASK_ANALYSIS_FIELDS:
        raise ValueError("task analysis has an invalid schema")
    return TaskAnalysis(
        task_summary=payload["task_summary"],  # type: ignore[arg-type]
        work_items=payload["work_items"],  # type: ignore[arg-type]
        deliverables=payload["deliverables"],  # type: ignore[arg-type]
        constraints=payload["constraints"],  # type: ignore[arg-type]
        quality_expectations=payload["quality_expectations"],  # type: ignore[arg-type]
    )


def _bounded_text(value: object, field_name: str, maximum: int) -> str:
    """限制自然語言欄位長度並拒絕明顯 secret/path 輸入。"""

    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be text")
    text = value.strip()
    if (
        not text
        or len(text) > maximum
        or "\x00" in text
        or PureWindowsPath(text).is_absolute()
        or PurePosixPath(text).is_absolute()
        or _SENSITIVE_TEXT.search(text) is not None
    ):
        raise ValueError(f"{field_name} must be bounded public text")
    return text


def _bounded_items(value: object, field_name: str) -> tuple[str, ...]:
    """將 bounded 字串陣列複製成 tuple，拒絕 nested/非字串資料。"""

    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise ValueError(f"{field_name} must be a list of strings")
    if len(value) > _MAX_ITEMS:
        raise ValueError(f"{field_name} cannot contain more than {_MAX_ITEMS} values")
    return tuple(
        _bounded_text(item, f"{field_name} item", _MAX_ITEM_LENGTH)
        for item in value
    )
