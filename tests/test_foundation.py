"""Codex Capability Router Phase 1 的最小結構驗證。

修改紀錄（2026-08-17，Steve Peng）
原始內容：檔案不存在。
修改原因：先以 TDD 建立可重複執行的 repository foundation 驗證。
修改後功能：驗證必要檔案、目錄、SKILL.md frontmatter、版本 metadata 與 Phase 1 邊界。
"""

from __future__ import annotations

import importlib
import re
import unittest
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
REQUIRED_FILES = (
    "SKILL.md",
    "README.md",
    "README.zh-TW.md",
    "LICENSE",
    "CHANGELOG.md",
)
REQUIRED_DIRECTORIES = (
    "schema",
    "references",
    "scripts",
    "tests",
    "examples",
)


def _read_utf8(relative_path: str) -> str:
    """以 UTF-8 讀取 repository 內的檔案，避免測試受主機編碼影響。"""

    return (REPOSITORY_ROOT / relative_path).read_text(encoding="utf-8")


def _skill_frontmatter() -> dict[str, str]:
    """解析 SKILL.md 的最小 frontmatter 欄位。

    ponytail: 只解析本階段需要的 name/description；需要完整 YAML 行為時再引入 parser。
    """

    lines = _read_utf8("SKILL.md").splitlines()
    if not lines or lines[0].strip() != "---":
        return {}

    fields: dict[str, str] = {}
    for line in lines[1:]:
        if line.strip() == "---":
            break
        key, separator, value = line.partition(":")
        if separator:
            fields[key.strip()] = value.strip()
    return fields


class FoundationStructureTests(unittest.TestCase):
    """驗證 Phase 1 的公開骨架，而不執行任何 capability。"""

    def test_required_files_exist(self) -> None:
        """必要公開檔案缺少時應立即被辨識。"""

        for relative_path in REQUIRED_FILES:
            with self.subTest(path=relative_path):
                self.assertTrue((REPOSITORY_ROOT / relative_path).is_file())

    def test_required_directories_exist(self) -> None:
        """必要目錄缺少時應立即被辨識。"""

        for relative_path in REQUIRED_DIRECTORIES:
            with self.subTest(path=relative_path):
                self.assertTrue((REPOSITORY_ROOT / relative_path).is_dir())

    def test_skill_md_contains_valid_name(self) -> None:
        """SKILL.md 必須提供合法且固定的 skill name。"""

        frontmatter = _skill_frontmatter()
        name = frontmatter.get("name", "")
        self.assertEqual(name, "codex-capability-router")
        self.assertRegex(name, re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$"))

    def test_skill_md_contains_when_description(self) -> None:
        """SKILL.md description 必須描述何時使用，且不能塞入完整 workflow。"""

        description = _skill_frontmatter().get("description", "")
        self.assertTrue(description.startswith("Use when "))
        self.assertIn("capability", description.lower())
        self.assertNotIn("step 1", description.lower())
        self.assertNotIn("workflow", description.lower())

    def test_readmes_are_bilingual_and_phase_one_scoped(self) -> None:
        """英文與繁中 README 必須存在並聲明 Phase 1 的安全邊界。"""

        english = _read_utf8("README.md")
        traditional_chinese = _read_utf8("README.zh-TW.md")
        for content in (english, traditional_chinese):
            self.assertIn("0.2.0-beta.1", content)
            self.assertIn("0.1.0", content)
            self.assertIn("read-only", content.lower())
            self.assertIn("network", content.lower())
            self.assertIn("private capability inventory", content.lower())

    def test_license_and_changelog_exist(self) -> None:
        """授權與變更紀錄檔案必須可供公開 repository 使用。"""

        self.assertIn("MIT License", _read_utf8("LICENSE"))
        self.assertIn("0.2.0-beta.1", _read_utf8("CHANGELOG.md"))
        self.assertIn("0.1.0", _read_utf8("CHANGELOG.md"))

    def test_package_metadata_has_no_runtime_dependency(self) -> None:
        """Phase 1 metadata 不得引入 runtime dependency。"""

        metadata = _read_utf8("pyproject.toml")
        self.assertIn('name = "codex-capability-router"', metadata)
        # 修改紀錄（2026-08-26，Steve Peng）
        # 原始內容：測試固定期待 beta.4 package metadata。
        # 修改原因：v0.2.0-beta.1 release preparation 更新版本 metadata 後，regression test 必須驗證同一版本。
        # 修改後功能：測試確認 pyproject 使用 v0.2.0-beta.1，且不改變 runtime dependency 邊界。
        self.assertIn('version = "0.2.0-beta.1"', metadata)
        self.assertIn("dependencies = []", metadata)

    def test_package_exports_version_without_execution(self) -> None:
        """package import 應提供版本 metadata，且不因 Phase 2 子模組而執行 capability。"""

        # 修改紀錄（2026-08-17，Steve Peng）
        # 原始內容：完整測試順序下只允許 __version__，忽略 Python submodule binding。
        # 修改原因：Phase 2/3/4 會載入 models、validation、discovery、registry、routing、catalog；
        # 匯出的純函式不代表執行 capability。
        # 修改後功能：保留 version 與 no-execution 驗證，同時允許已核准的 Phase 1/2/3/4 module binding 與 exports。
        # 修改紀錄（2026-08-21，Steve Peng）
        # 原始內容：測試固定期待 beta.1 package metadata。
        # 修改原因：beta.3 release preparation 更新版本 metadata 後，regression test 必須驗證同一版本。
        # 修改後功能：測試確認 package 匯出 v0.1.0-beta.3，且不改變 no-execution 邊界。
        # 修改紀錄（2026-08-26，Steve Peng）
        # 原始內容：測試固定期待 beta.4 package metadata。
        # 修改原因：v0.2.0-beta.1 release preparation 更新版本 metadata 後，regression test 必須驗證同一版本。
        # 修改後功能：測試確認 package 匯出 v0.2.0-beta.1，且不改變 no-execution 邊界。

        package = importlib.import_module("codex_capability_router")
        self.assertEqual(package.__version__, "0.2.0-beta.1")
        allowed_submodules = {
            "models",
            "validation",
            "discovery",
            "registry",
            "routing",
            "catalog",
            "inventory",
            "selection",
            # 修改紀錄（2026-08-26，Steve Peng）：Phase 1 新增 immutable TaskAnalysis contract module。
            # 修改原因：package import 會正常暴露已載入的 task_analysis 子模組，foundation allowlist 必須同步公開骨架而不放寬其他未知模組。
            # 修改後功能：接受 task_analysis module binding，維持 no-execution export boundary。
            "task_analysis",
            # 修改紀錄（2026-08-26，Steve Peng）：Phase 2 新增 Skill-only route_context contract module。
            # 修改原因：foundation export boundary 必須辨識正式 context module，但不允許 Provider 或第二 route module 偷渡。
            # 修改後功能：接受 route_context module binding，維持 package no-execution 邊界。
            "route_context",
            # 修改紀錄（2026-08-26，Steve Peng）：Phase 3 新增 lazy supporting_context contract module。
            # 修改原因：foundation export boundary 必須辨識 readiness/digest context，但不允許 Provider execution 或第二 route 偷渡。
            # 修改後功能：接受 supporting_context module binding，維持 package no-execution 邊界。
            "supporting_context",
            # 修改紀錄（2026-08-31，Steve Peng）：package allowlist 原本未辨識 Host exposure module。
            # 修改原因：新增 typed Host availability boundary 後，foundation test 必須允許該獨立 module binding。
            # 修改後功能：只接受 host_exposure module，維持 package no-execution export boundary。
            "host_exposure",
            "provider_adapters",
            # 修改紀錄（2026-08-31，Steve Peng）：Host adapter types 由 package import 暴露後，allowlist 尚未同步。
            # 修改原因：讓 designated Host orchestration 可使用 typed envelope，而不放寬其他執行能力匯出。
            # 修改後功能：明確允許 Host exposure validation exports。
            "HostExposureError",
            "HostSkillExposureAdapter",
            "HostSkillExposureEnvelope",
            "HostSkillExposureRecord",
            "canonicalize_host_path",
            "revalidate_host_exposure",
            "SelectionRouteInput",
            "__all__",
            "classify_capability",
            "classify_task",
            "deduplicate_registry",
            "route",
            "TaskAnalysis",
            "validate_task_analysis",
            "ValidatedDecisionPayloads",
            "prepare_route_context",
            "validate_decision_payloads",
            "ExecutionNeed",
            "FORMAL_SUPPORTING_PROVIDER_KINDS",
            "AppReadinessEvidence",
            "McpReadinessEvidence",
            # 修改紀錄（2026-08-26，Steve Peng）：Phase 4 新增 immutable Supporting decision protocol exports。
            # 修改原因：正式 route contract 與 synthetic tests 需要使用同一組 schema foundation。
            # 修改後功能：公開 decision/detail/final selection validators，不新增 execution 或第二 route。
            "SupportingCapabilitySelection",
            "UnmetExecutionNeed",
            "SupportingFinalSelection",
            "SupportingDetailRequest",
            "SupportingDecisionPayload",
            "SupportingToolDeclaration",
            "SupportingToolSummary",
            "SupportingProviderDeclaration",
            "ReadinessEvidenceCertificate",
            "ProviderDigest",
            "ProviderDetailReference",
            "SupportingRouteContext",
            "PROVIDER_PRESENCE_STATES",
            "PROVIDER_READINESS_STATES",
            "PROVIDER_METADATA_STATES",
            "EXECUTION_OUTCOMES",
            "ExecutionAttempt",
            "prepare_supporting_context",
            "normalize_execution_needs",
            "validate_supporting_decision",
            "validate_supporting_final_selection_payload",
            "supporting_selection_status",
            "APP_LIST_METHOD",
            "APP_INSTALLED_METHOD",
            "APP_READ_METHOD",
            "MCP_STATUS_LIST_METHOD",
            "MCP_STATUS_DETAIL",
            "ProviderAdapterInventory",
            "adapt_official_app_inventory",
            "adapt_official_mcp_inventory",
            "build_official_provider_requests",
        }
        self.assertEqual(
            set(package.__dict__)
            - {
                "__name__",
                "__doc__",
                "__package__",
                "__loader__",
                "__spec__",
                "__path__",
                "__file__",
                "__cached__",
                "__builtins__",
                "__version__",
            }
            - allowed_submodules,
            set(),
        )


if __name__ == "__main__":
    unittest.main()
