# Codex Capability Router

繁體中文 | [English](README.en.md)

![Codex Capability Router](docs/assets/readme-v2/router-hero.png)

[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-2ea44f)](LICENSE)
[![Release: 0.2.0-beta.10](https://img.shields.io/badge/release-0.2.0--beta.10-f59e0b)](https://github.com/Lzxpan/codex-capability-router/releases/tag/v0.2.0-beta.10)

**目前版本：`v0.2.0-beta.10`，Beta / Pre-release。**

Codex Capability Router 是提供給 Codex / Host controller 的唯讀 Python library。Host 的 LLM 負責理解任務、判斷哪些 Skills 與 Providers 有幫助；Python 負責可信來源 discovery、canonical identity、完整指令 handoff、輸入驗證與不可變的 selection Receipt。

安裝 Skill 提供的是指令層整合。每個新 task 都自動觸發、完整本機 inventory、自動套用與 real Provider 執行，仍需要 Host 接線與各自的驗證；單靠安裝或 `FINALIZED` 不代表這些能力已成立。

相容性基線：`0.1.0`；保留 read-only 邊界，不輸出 private capability inventory。

## beta.10 修正

- **Nested roots**：root compression 依實際 scanner 深度判斷，保留 parent 掃不到的明確 child root；不擴大成遞迴掃描。
- **Unreadable roots**：不存在或無法讀取的 root 產生自己的 `unreadable_root` diagnostic，其他可讀來源繼續回傳。
- **Selected Skill freshness**：一次 recovery 刷新真正變更的 canonical Skill，不再固定刷新第一筆。metadata 或 identity 改變要求 `SELECTION_REVALIDATION_REQUIRED`；再次 mismatch 仍拒絕為 `HANDOFF_REJECTION_AFTER_ONE_REFRESH`。
- **Decision coverage**：排入批次、收到 Host 判斷、完成判斷與 selected 分開計數。500 個 digests、0 個回覆就是 staged 500、decision received 0、`PARTIAL`。
- **目前規則**：Skills 與 Providers 都保留 plausible relevance、overlap、SPARSE/OPAQUE 與 presence/readiness 分離；舊 primary/optional contract 僅供歷史相容資料。

## 執行流程與分工

![Conceptual Router architecture](docs/assets/readme-v2/router-architecture.svg)

圖示是流程概念；Host 必須實際提供每個候選的判斷證據。

```text
Host TaskAnalysis
  -> trusted Skill discovery + digest batches
  -> Host Skill decisions + full handoff + one Skill Coverage Check
  -> Host Execution Needs
  -> Provider discovery + digest batches (only when needs are non-empty)
  -> Host Provider decisions + one Supporting Coverage Check
  -> route(SelectionRouteInput(...)) -> FINALIZED Receipt
  -> Host application/invocation -> separate ExecutionAttempt
```

| 名稱 | 作用 |
| --- | --- |
| Skill | 工作方法與品質規則；讀取完整指令後，由 Host 實際套用。 |
| Provider | `app`、`mcp`、`builtin_tool` 或 `host_tool`；由 Host 實際呼叫。 |
| Plugin | 套件與 provenance container；本身不是可呼叫的 Provider。 |
| Router | 驗證與交接；不自行呼叫 LLM 或選定 endpoint。 |

不使用 top-k 截斷、不設固定選取數量、不因 overlap 排除 plausible task-relevant 能力。`SUFFICIENT`、`SPARSE`、`OPAQUE` 都可進入候選池。已確認 presence 與 identity 的能力，即使 readiness 未知或不可用，仍可被考慮；執行時保留原本的權限與安全邊界。未知 Host hierarchy 保留為 `host_tool`，不猜成 App 或 MCP。

## Coverage 的正確讀法

| 欄位 / 狀態 | 證明範圍 |
| --- | --- |
| `*_staged_total` | 已排入 deterministic digest batches 的候選數。 |
| `*_decision_received_total` | Host 已回傳且通過 schema / task / snapshot 驗證的候選數。 |
| `*_semantically_considered_total` | 回覆已給出 `selected` 或 `not_selected`，沒有停在 `needs_detail` 的候選數。 |
| `*_never_considered_total` | 尚未收到 Host 回覆的候選數。 |
| `*_unresolved_total` | 沒有回覆或仍為 `needs_detail` 的候選數。 |
| `*_semantic_coverage_status=COMPLETE` | 本次已提供候選池全部有最終 disposition；不證明 LLM 判斷正確，也不證明 discovery 找到外界所有能力。 |
| `selection_state=FINALIZED` | selection Receipt 已完成；可以同時是 coverage `PARTIAL`。 |

Host 從 `skill_context.inventory_sweep` 與 `supporting_context.inventory_sweep` 取得 batches，將逐批結果透過 `SelectionRouteInput.skill_batch_decisions` / `supporting_batch_decisions` 交回。每批需包含相同 Skill context 的 `task_fingerprint`、對應 sweep 的 `sweep_fingerprint`、零起算 `batch_index` 與完整 `dispositions` mapping。漏回整批保留 PARTIAL；批內缺項、額外 IDs、重複批次、矛盾選擇與跨 task / snapshot 回覆會被拒絕。Provider sweep 另綁定 Execution Needs。

這是 Host 回報的公開 disposition，不是 Python 自行完成語意理解，也不要求 hidden chain-of-thought。詳見 [目前 routing contract](references/routing-policy.md) 與 [使用指南](docs/v0.2_user_guide.zh-TW.md)。

## Discovery 與 cache

固定 global roots 為 `$HOME/.agents/skills` 與 `$CODEX_HOME/skills`；後者只額外支援明確的 `.system` child。Plugin 僅走已解析的 active package 與 manifest-declared paths。未知 subtree、共同 Plugin cache ancestor 與全磁碟不在搜尋範圍。

`RootPlanSnapshot` / `SkillInventorySnapshot` 是 caller/session-owned cache。Host 在來源改變時 invalidates / refreshes；普通 route 可重用 snapshot，selected Skill handoff 仍檢查 authoritative bytes。這不是 persistent cache，也沒有偏好記憶或背景學習。

CLI probes 必須先確認 Host 支援。命令不存在、unsupported、timeout 或不可讀會回報 partial，不能解讀為「沒有安裝能力」。

## 安裝與本機檢查

需要 Python 3.11+；runtime dependencies 為空，測試使用 standard library。

### Windows / PowerShell

```powershell
$skillRoot = Join-Path $HOME ".agents\skills\codex-capability-router"
if (Test-Path -LiteralPath $skillRoot) {
    if (-not (Test-Path -LiteralPath (Join-Path $skillRoot ".git"))) {
        throw "Target exists and is not a Git checkout: $skillRoot"
    }
    git -C $skillRoot pull --ff-only
} else {
    New-Item -ItemType Directory -Force -Path (Split-Path $skillRoot) | Out-Null
    git clone https://github.com/Lzxpan/codex-capability-router.git $skillRoot
}
if ($LASTEXITCODE -ne 0) { throw "Git update failed" }
Push-Location $skillRoot
try {
    python -m unittest discover -s tests -q
    if ($LASTEXITCODE -ne 0) { throw "Tests failed" }
    python -m compileall -q codex_capability_router tests
} finally {
    Pop-Location
}
```

### macOS / Linux

```bash
skill_root="${HOME}/.agents/skills/codex-capability-router"
if [ -e "$skill_root" ]; then
    [ -d "$skill_root/.git" ] || { printf '%s\n' "Target is not a Git checkout" >&2; exit 1; }
    git -C "$skill_root" pull --ff-only || exit 1
else
    mkdir -p "$(dirname "$skill_root")" || exit 1
    git clone https://github.com/Lzxpan/codex-capability-router.git "$skill_root" || exit 1
fi
(cd "$skill_root" && python -m unittest discover -s tests -q &&
 python -m compileall -q codex_capability_router tests)
```

安裝指令不覆寫非 Git checkout 的既有目錄。更新此 source repository 不會自動更新其他 global Skill 安裝副本。

## 驗證與限制

本次 local regression 結果與修改範圍見 [beta.10 驗證紀錄](docs/validation/v0.2.0-beta.10-validation.md)。在 repository root 可重跑：

```powershell
python -m unittest discover -s tests -q
python -m compileall -q codex_capability_router tests
git diff --check
```

Local tests 驗證 deterministic contract、temporary fixture discovery、一次 freshness recovery、Host 回覆驗證與正式 route。Host 每次自動觸發、自然語言盲測準確率、完整 App/MCP inventory、real Provider、production、hardware 與 GitHub browser rendering 仍為 `NOT VERIFIED`。

Router 不自行 network-discover、安裝、OAuth、授權、寫入、刪除、發布或執行外部能力。`ExecutionAttempt` 與 selection Receipt 分開保存，不能把 selected 當成已成功執行。

## 文件

- [English README](README.en.md)
- [使用指南與歷史 v0.2 範例](docs/v0.2_user_guide.zh-TW.md)
- [Routing policy](references/routing-policy.md)
- [Discovery / provenance](references/discovery-and-provenance.md)
- [Changelog](CHANGELOG.md)
- [MIT License](LICENSE)
