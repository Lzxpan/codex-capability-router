# Codex Capability Router

版本：`v0.1.0-beta.1`
狀態：**Beta / Pre-release（公開測試版）**

Codex Capability Router v0.1.0-beta.1 是 local-first、context-first、read-only 的 capability
recommendation skill，提供有界 local discovery、deterministic routing 與雙語輸出。

本版本已通過 deterministic functional validation suite：**42/42 tests
pass**，包含 12 個 routing scenarios（`zh-TW` 6 個、`en` 6 個）。Plugin Eval
目前回報較高的 static deferred-context estimate；該估計包含 repository
artifacts，並不是 measured runtime token consumption。正式升級為 stable
`v0.1.0` 前，仍必須取得 empirical runtime token measurement。

## 目前 v0.1.0 邊界

目前實作只接受呼叫端提供的 skill roots、manual inventory、canonical registry
records 與 user task。系統會驗證 records、執行 deterministic advisory routing，
並輸出 `en` 或 `zh-TW` catalog/recommendation。不執行 capability、不安裝或管理
Plugin、不掃描未指定路徑、不使用 network discovery、不存取 Marketplace、不變更
permission，也不持久化 private inventory。

本階段不儲存或輸出 private capability inventory、帳戶資料、credentials、
secrets 或不必要的 personal absolute paths。

## 這個專案是什麼

本專案提供一個只使用 Python standard library 的小型實作與 Codex
`SKILL.md` entrypoint，將呼叫端提供的 capability 描述整理成 runtime-scoped
registry 與可解釋的 advisory recommendations。

## Skill 會做什麼

- 讀取 runtime capability envelope、核准的 read-only CLI probe、明確提供的
  skill roots 與 manual inventory。
- 正規化 records、依穩定 identifier 去除重複，並保留 provenance、confidence、
  evidence 與 conflicts。
- 套用 runtime > CLI > explicit skill root > manual 的來源優先順序。
- 產生 deterministic 的主要/可選建議，以及 `en` 或 `zh-TW` catalog/output。
- 新增簡潔的已選能力說明，顯示 capability 類型、PRIMARY/OPTIONAL 層級、registry
  提供的 Function metadata，以及由 deterministic reason codes 產生的使用者可讀理由。

## Skill 不會做什麼

不執行 capability，不安裝、更新或移除 Plugin/skill，不變更 permission，不存取
Marketplace，不進行 network discovery，不掃描未指定路徑，不保存 private
inventory，也不處理 credentials、API keys、tokens、OAuth 或帳戶資料。

## 支援語言

明確支援 English（`en`）與 Traditional Chinese（`zh-TW`）。`auto` 只有在 request
含有繁體中文字元時選擇 `zh-TW`，否則保守選擇 English。

## 安裝、更新與移除

本 repository 本身就是可安裝的 skill checkout；不提供 package-index installer，
也不會自動變更 permission。

1. 將本 repository clone 或複製到 local skill checkout。
2. 透過 host 原本的 local-skill 機制指向其中的 `SKILL.md`。
3. 只把該 checkout 放在呼叫端明確核准的 skill root。

Git checkout 可在該目錄執行 `git pull --ff-only` 更新；複製版本則以已審查的
release copy 替換。移除時只刪除當初安裝的 local checkout；本 skill 不會刪除其他
skills、plugins、permissions 或 user data。

## Capability discovery 行為

Runtime envelope 是最高權威。兩個有界 CLI probe 是 `codex plugin list --json`
與 `codex mcp list --json`；probe 失敗時會回傳 partial result 與 `unknown` record，
不會猜測能力可用。只掃描 caller 提供的 skill roots；manual inventory 只是描述
輸入，不是驗證或執行授權。

## Registry 位置與行為

Runtime registry 是 canonical 且以單次 runtime 為範圍，只存在於目前 routing operation，
不會持久化成 private inventory。公開 schema 位於
`schema/capability-registry.schema.json`；固定測試 registry 位於
`tests/fixtures/routing_registry.json`，不是實際 user inventory。雙語 catalog 為
`docs/CATALOG.en.md` 與 `docs/CATALOG.zh-TW.md`。

可選的雙語 Function metadata 使用 registry 的 `function` object，包含 `en` 與
`zh-TW` 值。Machine-readable route output 保留 `selection_evidence`，包含 capability
ID、selection level、reason codes 與 matched evidence。

## Routing 行為

Routing 是 deterministic 且 advisory-only。它排除 `unavailable` 與一般 `unknown`，
防止 Router 自我路由，最多保留 3 個 installed primary 與 2 個 available optional
recommendations，並回報 rationale 與 rejected-candidate provenance。只有 trusted 且
明確標記的 `unknown` 才能出現在獨立的 recommendation-only 區段。

Routing 完成後，human-readable output 會包含「已選能力」，若有 skill 則另外顯示
「已選技能」。每筆會顯示名稱、類型、選擇層級、功能與選用理由；理由只來自既有
trigger match、requirement coverage、specialist match、availability 或 optional coverage
等 routing evidence。缺少 Function metadata 時會使用明確 fallback，不會從 category
自行推測功能。

## 安全與隱私模型

所有輸入在邊界驗證。Source 使用 abstract label；explicit roots 是 allowlist；probe
使用有界、非 shell 的執行方式；diagnostic 不回顯被拒絕的敏感值。實作不保存或輸出
API keys、tokens、passwords、OAuth credentials、private account data、raw personal
absolute paths 或 private Plugin inventory。

## 已知限制與 v0.1 scope

Beta scope 包含 read-only local discovery、canonical registry merge、deterministic
routing、provenance/conflict handling、雙語 catalog 與 bounded validation。固定驗證
集合恰好是 12 個 scenarios：`zh-TW` 6 個、`en` 6 個。

Plugin Eval 回報 estimated-static deferred context cost。這不是 measured runtime
token usage；repository documentation、tests、fixtures 與 implementation artifacts
都包含在 static estimate 中。目前 measured runtime token usage 仍不可得。Local
software evidence 也不代表外部 capability execution、hardware behavior 或 physical
acceptance 已通過。

Deferred features 包含 capability execution、安裝/管理、permission mutation、remote
discovery、private inventory persistence、account integration、telemetry、GUI/service
deployment、MCP hosting 與 automatic routing-policy learning。

## 使用範例

在 repository root 執行 deterministic suite，並從同一份 registry 重新產生雙語 catalog：

```powershell
python -m unittest discover -s tests -v
python -m codex_capability_router.catalog --input tests/fixtures/routing_registry.json --output docs
```

例如任務為「請修正 React 元件的介面錯誤」時，說明會包含：

```text
## 已選能力
### 已選技能
#### PRIMARY
- 名稱：React UI Debugging
  類型：skill
  選擇層級：PRIMARY
  功能：診斷 React 介面回歸問題。
  選用理由：目前任務符合 React、UI 與 debugging 相關觸發條件，且此能力屬於專門能力。
```

理由由 deterministic routing evidence 渲染，不是 hidden reasoning trace。

## Stable release requirement

Stable `v0.1.0` 除了 beta functional 與 privacy gates 外，還需要 empirical runtime
token measurement；或由獨立證據證明實際 loading model 並建立可接受的 bounded budget。

## Repository 結構

```text
SKILL.md
README.md
README.zh-TW.md
LICENSE
CHANGELOG.md
pyproject.toml
codex_capability_router/
schema/
references/
scripts/
tests/
examples/
```

`schema/`、`references/`、`scripts/` 與 `examples/` 維持精簡，不代表取得執行或
安裝權限。

## Phase 5 證據邊界

有界評估固定包含十二個 routing cases。Local software tests 不證明硬體、實體
water-path、外部 capability 或生物效能驗收。

## Local verification

使用 Python 3.11 以上版本與 standard library only：

```powershell
python -m unittest discover -s tests -v
python -m compileall -q codex_capability_router tests
git diff --check
```

本 repository 是 skill checkout，不是 network service，也不是 package
Marketplace submission。

<!--
修改紀錄（2026-08-17，Steve Peng）
原始內容：README 仍標示 Phase 1，並否認目前 source 已存在的 discovery/routing。
修改原因：同步公開說明與實際 v0.1.0 source，避免錯誤觸發與錯誤能力承諾。
修改後功能：文件說明目前唯讀功能、Phase 5 軟體證據邊界與完整 local test command。
修改紀錄（2026-08-18，Steve Peng）：補充 Phase 5D 已選能力說明、Function metadata 與 deterministic 理由範例。
-->
