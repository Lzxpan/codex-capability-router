# Codex Capability Router

版本：`v0.2.0-beta.1`
狀態：**Beta / Pre-release（公開測試版）**

Codex Capability Router v0.2.0-beta.1 是 local-first、context-first、read-only 的
Router，先由 Codex LLM TaskAnalysis 理解完整工作，再將方法型 Skill 與目前可直接
呼叫的 Supporting Provider 分層處理。

Deterministic implementation 與官方 Provider adapters 已完成：目前完整 suite 為
**160/160 PASS**。本次 Host 沒有提供可連線的官方 App Server surface，因此
App/MCP live acceptance 明確維持 blocked。

## v0.2.0-beta.1 新增內容

- LLM TaskAnalysis 以 immutable strict contract 產生 `task_summary`、`work_items`、
  `deliverables`、`constraints` 與 `quality_expectations`。
- Skill 回答「工作應該怎麼做」；Supporting Provider 回答「目前可直接呼叫的執行
  能力是什麼」。
- `prepare_route_context()` 是 read-only、stateless、deterministic、Skill-only；
  `execution_needs=[]` 時完全不掃描 Supporting Provider、不做 readiness normalization、
  不建立 digest。
- `prepare_supporting_context()` 只接受 typed、通過 runtime evidence certification 的
  exact instance。正式 selectable kind 為 App、MCP 與 builtin tool；Plugin 僅是
  package/provenance container。
- Provider 語意選擇由 Codex 決定；Python 只做 schema、identity、readiness、fingerprint、
  privacy 與 finalization validation。
- 只有一條 production `route()` 能建立 v0.2 Receipt 並進入 `FINALIZED`；完成後不可
  修改。Skill status 與 Supporting status 維持獨立，no-match 也是合法結果。
- `explain-code` legacy frontmatter 採 bounded compatibility normalization，不放寬
  malformed、sensitive 或 unavailable gate。

未 certification 的 App/MCP instance 與 builtin tool 都不是 formal production
scope。Plugin 不會被選為 Provider；只有可信 Host 暴露的 App 或 MCP 才能獨立
參與選擇。不會猜測、推薦、自動安裝、自動授權或 silent fallback。

## 文件 / v0.2

- [v0.2 圖文使用指南](docs/v0.2_user_guide.zh-TW.md)
- [Installed Skill Live Test Report](docs/v0.2_installed_skill_live_test_report.zh-TW.md)
- [v0.2 Architecture / Design](docs/v0.2_llm_task_analysis_supporting_capability_selection_design.zh-TW.md)

## Historical v0.1.0-beta.4 整合強化

本版本不取代 beta.3 的語意 Skill Selection 設計，只強化整合邊界：

- 正式 Selection Result 必須來自 `routing.route(SelectionRouteInput(...))`；外層不能偽造 production Receipt。
- 每次正式 route 自動產生有界、可稽核的 Selection Receipt，記錄 candidate、preliminary、full handoff、final selected、status、retrieval、correction 與 finalization evidence；不保存 private chain-of-thought 或敏感資料。
- machine path 全程使用 canonical Skill ID；display name 僅供人類顯示。
- Selection lifecycle 為 `OPEN` → `FINALIZED`；完成後 selection immutable。新工作必須建立新的 routing request。

beta.3 的 Codex 語意選擇、recall-first retrieval、Profile 與 Expanded Retrieval/Correction 次數上限保持不變。

## Historical v0.1.0 邊界

目前實作接受 runtime 可見的 inventory、核准的 skill roots、canonical registry
records 與 user task。系統會驗證 records、建立 inventory fingerprint 與
Basic/Enriched Profile、執行 recall-first candidate retrieval，並在輸出前驗證
Codex 的 final Skill selection。不執行 capability、不安裝或管理 Plugin、不掃描未
指定路徑、不使用 network discovery、不存取 Marketplace、不變更 permission，也不
持久化 private inventory。

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
- 建立 Basic/Enriched Profile，從目前 runtime inventory 執行 recall-first candidate
  retrieval；符合資格的 explicit Skill request 也會納入候選。
- 對 Codex 初選 Skill 完整讀取 `SKILL.md`，再執行 final applicability check；expanded
  retrieval 與 correction 各自有界且最多一次。
- 由 Codex 根據工作語意決定 final Skill。新版 contract 只包含 `selected_skills` 與
  `selection_status`（`selected` 或 `no_matching_skill`），不再有 keyword-to-Skill
  mapping、PRIMARY/OPTIONAL output 或 3+2 limit。
- 先建立 immutable TaskAnalysis，再於 Skill applicability 完成後產生 Execution Needs。
- 只有 Execution Needs 非空時才準備 Supporting Provider context；final Provider decision
  由 `route()` 驗證並 finalize。

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
`zh-TW` 值。Machine-readable selection output 包含 `task_summary`、帶有簡短理由的
`selected_skills` 與 `selection_status`，不輸出 PRIMARY/OPTIONAL level 或
recommendation-only final-selection semantics。正式 production routing 也會回傳上述
有界 Selection Receipt。

## Routing 行為

Routing 是 advisory-only。Discovery、normalization、availability filtering、profile
建立與 candidate retrieval 先準備 context；再由 Codex 主模型根據工作語意決定 final
Skill selection。只有確實 discovered、available 且通過完整 `SKILL.md` applicability
check 的 Skill 才能被選取。空結果回報 `no_matching_skill`，不等同
`native_model_sufficient`，也不加入 legacy 或 silent fallback。

Keyword、category 與 `provides` 可以協助 candidate retrieval，但不決定 final Skill ID。
正式 output 不再有 PRIMARY/OPTIONAL semantics，也沒有固定 3+2 selection limit。新增或
更新 Skill 不需要修改 Router production mapping。Expanded Retrieval 最多一次，
selection correction 最多一次。

Router controller 本身，以及標記為 internal routing support 的 records，永久排除於
downstream task selection。route-only mode 仍會選出 target-task capabilities，並以
`execution_allowed=false` 抑制執行；選擇不等於執行 capability。

Routing 完成後，human-readable output 會包含已選 Skill ID 與簡短 Codex selection reason，
或明確的空結果與 `no_matching_skill`。Selection 不會執行 Skill；Router controller 與
標記為 internal routing support 的 records 仍排除於 downstream task selection。

## 安全與隱私模型

所有輸入在邊界驗證。Source 使用 abstract label；explicit roots 是 allowlist；probe
使用有界、非 shell 的執行方式；diagnostic 不回顯被拒絕的敏感值。實作不保存或輸出
API keys、tokens、passwords、OAuth credentials、private account data、raw personal
absolute paths 或 private Plugin inventory。

## 已知限制與 v0.2.0-beta.1 scope

目前 pre-release 包含 read-only runtime discovery、canonical registry merge、immutable
TaskAnalysis、Skill-side context fingerprint、recall-first retrieval、Codex Skill
selection、lazy Supporting Provider context、bounded finalization、雙語 output 與 bounded
validation。Canonical fixture 包含 12 個 scenarios：`zh-TW` 6 個、`en` 6 個；完整 suite
包含 160 個 tests；官方 App/MCP live acceptance 取決於 Host surface。

本次 upgrade 的 live probe 期間 Host 沒有提供可連線的官方 App Server surface，
因此 App/MCP live acceptance 維持 Host-surface blocked。實作已依 Host 提供時的
typed `app/list`、`app/installed`、`app/read` 與 `mcpServerStatus/list` contract
建立 adapter；舊有 `node_repl` certification 仍保留作 compatibility。Detail
expansion 已由 deterministic tests 覆蓋。

Deferred features 包含 capability execution、安裝/管理、permission mutation、remote
discovery、private inventory persistence、account integration、telemetry、GUI/service
deployment、MCP hosting 與 automatic routing-policy learning。

## 使用範例

在 repository root 執行完整 suite，並從同一份 registry 重新產生雙語 catalog：

```powershell
python -m unittest discover -s tests -v
python -m codex_capability_router.catalog --input tests/fixtures/routing_registry.json --output docs
```

例如任務為「請修正 React 元件的介面錯誤」時，selection output 會包含：

```text
{"selected_skills":[{"id":"react-ui-debugging","reason":"Codex 判定此 Skill 適用於 UI debugging 工作。"}],"selection_status":"selected"}
```

理由是簡短且可稽核的 selection explanation，不是 hidden reasoning trace。

## 超越 beta 的後續條件

若要超越本 beta，仍需取得可供 Router 採信的 Skill availability runtime evidence，並
擴大 Provider certification；本版本不宣稱 stable `v0.2.0` 或 universal Provider support。

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

Canonical fixture 包含十二個 routing cases；完整 Python regression 包含 137 個 tests，
Codex Live Acceptance 包含五個 runtime cases。Local software tests 不證明硬體、實體
water-path、外部 capability 或生物效能驗收。

目前 runtime discovery 回報 139 個 malformed Skill diagnostics。這是記錄中的
non-blocking observation；beta.4 不因 release preparation 擴張 discovery scope 修正它。

## Real-world local acceptance

一個獨立 STM32G0 firmware workspace 已完成本 beta 的 acceptance case：

- Auto-trigger、explicit routing、workspace-specific specialist preference、
  overlap/deduplication、controller exclusion、internal support exclusion 與
  route-only semantics：PASS。
- Selected Capability Explanation、deterministic rationale、downstream skill
  execution，以及 PASS/FAIL/BLOCKED/HARDWARE_PENDING 邊界：PASS。

這些是公開 routing evidence；私有 source、絕對路徑與專案 inventory 不納入本 repository。

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
修改紀錄（2026-08-18，Steve Peng）
原始內容：README 仍標示 beta.1/42 tests，且未記錄 Phase 5E/5E-R 的 route-only 與 STM32G0 acceptance 結果。
修改原因：同步 beta.2 公開文件與已驗證的路由排除、execution suppression、46/46 deterministic suite 及 real-world evidence。
修改後功能：讀者可辨識目前 beta.2 行為、已選能力說明、recommendation-only 分離、無自動安裝/權限變更與公開驗收邊界。
修改紀錄（2026-08-21，Steve Peng）
原始內容：README 仍描述 beta.2 的固定 primary/optional routing 與 46/46 suite。
修改原因：同步 beta.3 的 Codex final Skill selection contract、81/81 regression 與 Phase 5 Full Live Acceptance。
修改後功能：文件反映 inventory/profile、recall-first retrieval、完整 SKILL.md applicability、兩種 selection status、無 legacy/silent fallback，以及 139 malformed diagnostics 的 non-blocking 邊界。
修改紀錄（2026-08-25，Steve Peng）
原始內容：README 仍標示 beta.3 與 beta.3 validation baseline。
修改原因：準備 beta.4 release metadata 與 Integration Hardening release notes。
修改後功能：文件反映 91/91 tests、Integration Live Acceptance 4/4 與 production route、Receipt、canonical ID、finalization 邊界；不改變 production behavior。
修改紀錄（2026-08-26，Steve Peng）
原始內容：README 仍以 beta.4 為 current release 說明。
修改原因：v0.2.0-beta.1 release preparation 需要公開 TaskAnalysis、lazy Supporting scope 與真實限制。
修改後功能：文件反映 137/137 regression、Live Acceptance A–E、正式 Provider instance scope 與 privacy/finalization 邊界。
-->
