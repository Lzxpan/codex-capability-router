"""Capability existence evidence shared by blind discovery scopes."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import re


class ExistenceEvidenceState(str, Enum):
    """可區分來源層級的存在證據，不代表 readiness 或可執行性。"""

    RUNTIME_ENTITY_PRESENT = "RUNTIME_ENTITY_PRESENT"
    FILESYSTEM_PRESENT = "FILESYSTEM_PRESENT"
    PACKAGE_DECLARED_PRESENT = "PACKAGE_DECLARED_PRESENT"
    HOST_SESSION_EXPOSED = "HOST_SESSION_EXPOSED"
    DECLARATION_ONLY = "DECLARATION_ONLY"


class MetadataQuality(str, Enum):
    """描述 metadata 的完整度；不決定 capability 是否可被考量。"""

    SUFFICIENT = "SUFFICIENT"
    SPARSE = "SPARSE"
    OPAQUE = "OPAQUE"


_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]*$")


def classify_metadata_quality(
    *,
    name: object = None,
    description: object = None,
    summaries: object = None,
) -> MetadataQuality:
    """只依可讀 public metadata 分類品質，不猜測 capability 用途。

    有 description 或 tool/action summary 時為 `SUFFICIENT`；只有名稱或其他
    bounded public label 時為 `SPARSE`；完全沒有可讀描述時為 `OPAQUE`。三者
    都可進 semantic consideration，品質僅作 digest 與診斷資訊。
    """

    if isinstance(description, str) and description.strip():
        return MetadataQuality.SUFFICIENT
    if isinstance(summaries, (list, tuple)) and any(
        isinstance(item, str) and item.strip() for item in summaries
    ):
        return MetadataQuality.SUFFICIENT
    if isinstance(name, str) and name.strip():
        return MetadataQuality.SPARSE
    return MetadataQuality.OPAQUE


@dataclass(frozen=True)
class ExistenceEvidence:
    """單筆 bounded public existence evidence。

    `source` 只保存 abstract source label；不保存 private path、raw manifest 或
    readiness。`metadata_sufficient` 僅表示能否讓 LLM 理解用途，並非 semantic
    relevance 判斷。
    """

    identity: str
    state: ExistenceEvidenceState
    source: str
    metadata_sufficient: bool = False
    resolved: bool = True
    metadata_quality: MetadataQuality | None = None

    def __post_init__(self) -> None:
        """驗證 canonical identity、evidence state 與 bounded source label。"""

        if not isinstance(self.identity, str) or _IDENTIFIER.fullmatch(self.identity.strip()) is None:
            raise ValueError("existence evidence identity must be canonical")
        object.__setattr__(self, "identity", self.identity.strip())
        if not isinstance(self.state, ExistenceEvidenceState):
            try:
                object.__setattr__(self, "state", ExistenceEvidenceState(self.state))
            except ValueError as error:
                raise ValueError("unsupported existence evidence state") from error
        if not isinstance(self.source, str) or not self.source.strip() or len(self.source) > 256:
            raise ValueError("existence evidence source must be bounded text")
        if "/" in self.source or "\\" in self.source:
            raise ValueError("existence evidence source must be an abstract label")
        if not isinstance(self.metadata_sufficient, bool) or not isinstance(self.resolved, bool):
            raise ValueError("existence evidence flags must be boolean")
        quality = self.metadata_quality
        if quality is None:
            quality = MetadataQuality.SUFFICIENT if self.metadata_sufficient else MetadataQuality.OPAQUE
        elif not isinstance(quality, MetadataQuality):
            try:
                quality = MetadataQuality(quality)
            except ValueError as error:
                raise ValueError("unsupported metadata quality") from error
        object.__setattr__(self, "metadata_quality", quality)

    def to_mapping(self) -> dict[str, object]:
        """輸出不含 filesystem path 的 public evidence。"""

        return {
            "identity": self.identity,
            "state": self.state.value,
            "source": self.source,
            "metadata_sufficient": self.metadata_sufficient,
            "resolved": self.resolved,
            "metadata_quality": self.metadata_quality.value,
        }
