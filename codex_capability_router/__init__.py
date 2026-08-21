"""Codex Capability Router 的 package metadata 與新版 selection exports。"""

# 修改紀錄（2026-08-17，Steve Peng）
# 原始內容：package 尚不存在，後續版本為 0.1.0。
# 修改原因：公開 release 目標改為 v0.1.0-beta.1，package metadata 必須與 beta tag 一致。
# 修改後功能：公開 beta.1 版本與唯一新版 Skill selection entry point，不進行 capability execution。

__version__ = "0.1.0-beta.1"

from .registry import classify_capability, deduplicate_registry
from .routing import SelectionRouteInput, route

__all__ = [
    "__version__",
    "classify_capability",
    "deduplicate_registry",
    "SelectionRouteInput",
    "route",
]
