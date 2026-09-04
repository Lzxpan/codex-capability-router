# Codex Capability Router

繁體中文 | [English](README.en.md)

![Codex Capability Router hero](docs/assets/readme-v2/router-hero.png)

> 讓 Codex 先理解完整任務，再找出真正有幫助的 Skills 與 Supporting Providers。

[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-2ea44f)](LICENSE)
[![Release: 0.2.0-beta.9](https://img.shields.io/badge/release-0.2.0--beta.9-f59e0b)](pyproject.toml)

Codex Capability Router 是一個 local-first、context-first、read-only 的能力路由器。它把自然語言任務整理成可稽核的 <code>TaskAnalysis</code>，發現可信的 Skills，辨識目前 session 暴露的 Supporting Providers，並透過正式 <code>route(SelectionRouteInput(...))</code> 產生不可被執行結果偷偷改寫的 <code>FINALIZED</code> Receipt。

目前版本：<code>0.2.0-beta.9</code>。相容性基線：<code>0.1.0</code>；Phase 1 維持 <code>read-only</code>，不做 network discovery，也不輸出 private capability inventory。

beta9 另外固定了 Skill source binding 與 handoff freshness：同一 canonical Skill 可以保留多個 authoritative provenance，但每次 logical routing 只選一個 deterministic physical source；profile、fingerprint 與 handoff 都綁定同一份 source。selected Skill 的 fingerprint 若在 handoff 時改變，Router 只做一次 targeted refresh，建立新的 immutable snapshot 並重試一次；仍不一致就回報 <code>HANDOFF_REJECTION</code>，若 selection-visible semantic digest 改變則交回 Host controller 重新驗證。

![Codex Capability Router mascot](docs/assets/readme-v2/router-mascot.png)

## Why Capability Router?

一個複合任務通常同時需要文件、程式碼檢查、視覺產出、流程圖與 repository 驗證。若先用舊式流程：

~~~text
discovered → top-k shortlist → selected
~~~

尾端但重要的 capability 可能永遠沒有進入語意判斷。新版 Router 改採：

~~~text
trusted discovery inventory
        ↓
deterministic bounded semantic sweep
        ↓
每個 resolved present capability 至少被 consideration 一次
        ↓
任何 plausibly task-relevant capability 進入 selection
~~~

設計不變量是：

- <code>skill_never_considered_total = 0</code>
- <code>provider_never_considered_total = 0</code>

這是降低 discovery 與 consideration miss 的設計目標，不是宣稱「任何任務永遠 100% 不會漏選」。Router 會在可信且可 formal discover 的 inventory 上，保留可稽核的發現、考量、選擇與限制證據。

核心原則很簡單：

**DISCOVER BROADLY**：先完整取得可信 inventory。
**CONSIDER BROADLY**：讓每個 resolved present capability 都有語意考量機會。
**SELECT GENEROUSLY**：只要有任何合理的 task-relevant value，就不因重複、overlap 或另一個 Skill 已經足夠而排除。
**EXECUTE CAREFULLY**：selection 是建議與路由，不等於自動執行、安裝、登入或授權。

## 核心功能

| 能力 | 說明 |
| --- | --- |
| <code>TaskAnalysis</code> | 將任務拆成 work items、material deliverables、constraints 與 quality expectations。 |
| Skill routing | 從 trusted roots 發現 Skills，進行 full inventory semantic sweep，再選出方法型能力。 |
| Supporting Provider routing | 透過 <code>HostCapabilitySnapshot</code> 辨識 App、MCP、<code>builtin_tool</code> 與 <code>host_tool</code> 等正式 Provider。 |
| High-recall selection | 不使用固定 top-k，也沒有固定 Skill count；任何 plausibly task-relevant 的能力可一起入選。 |
| Auditable Receipt | <code>route(SelectionRouteInput(...))</code> 回傳 <code>FINALIZED</code>、fingerprint 與選擇依據。 |
| Read-only boundary | Router 不執行 endpoint、不做 network discovery、不自動安裝或授權，也不讀 hidden prompt 或 chain-of-thought。 |

## 四個原則，四個畫面

### Discover broadly：先把能力找齊

![Discover broadly comic](docs/assets/readme-v2/discover-broadly.png)

貓咪用放大鏡檢查從四面八方進來的 capability cards，代表完整 inventory 與尾端能力也要被看見。這一步的結果是「已發現」；只要 identity resolved 且存在，metadata quality 就只作診斷，不會阻擋語意考量。

### Select generously：保留真正有價值的能力

![Select generously comic](docs/assets/readme-v2/select-generously.png)

狗狗把多個可能有幫助的能力留在工作台；只有明確不相關、exact duplicate 或安全邊界不允許的項目才被放到旁邊。selection 不追求最小數量，而追求不漏掉合理需要的能力。

### Multi-provider + safe execution：選到不代表立即執行

![Safe execution comic](docs/assets/readme-v2/safe-execution.png)

多個 Provider 可以同時 selected；真正的 execution 仍需要外部執行層、權限與錯誤處理。盾牌和 Receipt 表達 <code>selected ≠ auto executed</code>，也表達 <code>SELECT GENEROUSLY</code> 與 <code>EXECUTE CAREFULLY</code> 的邊界。

### Architecture：從任務到 Receipt

![Router architecture workflow](docs/assets/readme-v2/router-architecture.svg)

完整流程如下：

~~~text
User Task
  ↓
TaskAnalysis
  ↓
Trusted Skill Discovery
  ↓
Full Inventory Semantic Sweep
  ↓
Skill Selection
  ↓
Skill Coverage Check
  ↓
Execution Needs
  ↓
Host Capability Snapshot
  ↓
Provider Discovery
  ↓
Full Provider Semantic Sweep
  ↓
Provider Selection
  ↓
Supporting Coverage Check
  ↓
route(SelectionRouteInput(...))
  ↓
FINALIZED Receipt
  ↓
ExecutionAttempt
~~~

## Skill、Provider、Plugin 有什麼不同？

| 名稱 | 角色 | 本 Router 的邊界 |
| --- | --- | --- |
| Skill | 描述「如何完成工作」的方法與品質規範，例如 technical writing、verification 或 image generation。 | 由 trusted skill discovery 找到，經語意考量後可被選入。 |
| Provider | 實際可支援某個 execution need 的 formal capability，例如 App、MCP、<code>builtin_tool</code> 或 <code>host_tool</code>。 | 由 runtime/provider discovery 找到；presence、identity 與 metadata 進入 consideration，readiness 只記錄執行狀態。 |
| Plugin | 套件與 provenance 的來源資訊。 | 不是 formal Provider，不應被當成可直接執行的 endpoint。 |

正式 Provider kinds 是 <code>app</code>、<code>mcp</code>、<code>builtin_tool</code>、<code>host_tool</code>。Generic execution capability 不會自動排掉 specialized image、diagram 或 verification Provider；只要各自有 plausible task-relevant value，就可以 multi-select，重複與 overlap 不是排除理由。Plugin 仍然只是 package/provenance container，不是 formal Provider。

App runtime evidence 依目前 Host/runtime source 是否可取得而定；package declaration 可以保留 existence evidence，但 Router 不保證每個 Host 都能取得 runtime app/list，也不把 package declaration 直接誇大成目前 UI 或 endpoint 已可用。

## Discovery roots、Plugin 路徑與 Skill inventory cache

Skill discovery 只使用 authoritative known roots。固定 global roots 是 <code>$HOME/.agents/skills</code> 與 <code>$CODEX_HOME/skills</code>；<code>$CODEX_HOME/skills/.system</code> 是第二個 root 下唯一明確合法的 SYSTEM known child，不是第三個獨立 global root，也不代表允許遞迴所有 hidden directories。

Plugin discovery 依 logical Plugin inventory 解析 deterministic exact package root，再讀 exact manifest，只走 manifest-declared Skill container 或 direct Skill path。共同的 Plugin cache ancestor 不會被當成 recursive search root；container 下的 Skill directory 是 inventory entity，不會各自膨脹成 root-plan node。

初始化或明確 source/plugin/project/runtime invalidation 時，controller 建立 <code>RootPlanSnapshot</code> 並 refresh <code>SkillInventorySnapshot</code>。在同一 caller/session 的 source state 沒有變化時，ordinary route 重用 snapshot，不重新 build root plan、不重新掃 Skill filesystem、不重新開 Plugin manifests，也不重新開全部 <code>SKILL.md</code>。這是 caller/session-owned cache，不是跨 process 的永久 persistent cache。

## Host Capability Snapshot

Codex controller 本來就知道目前 session 暴露哪些 public capabilities。Router 透過 typed <code>HostCapabilitySnapshot</code> 取得這些 metadata，讓「Host 看得到」與「Router 能正式考量」使用同一個公開能力邊界。

Snapshot 可以描述 capability ID、kind、display name、summary、readiness 與 provenance。它不讀 hidden prompt，不讀 chain-of-thought，也不假裝擁有 cryptographic trust proof；<code>trusted_host_snapshot</code> 只是目前輸入 envelope 的信任標記。

常見 readiness：

| Readiness | 意義 | 可否進入 selection |
| --- | --- | --- |
| <code>VERIFIED_READY</code> | 已有可用性驗證證據。 | 可以 |
| <code>PRESENT_UNVERIFIED</code> | Host 明確暴露且 metadata 足夠，但本輪沒有 endpoint readiness proof。 | 可以 |
| <code>KNOWN_UNAVAILABLE</code> | 已知目前不可執行；狀態保留給 execution boundary。 | 可以先進入 semantic consideration，執行時如實回報不可用。 |

因此 <code>PRESENT_UNVERIFIED</code> 不是 discovery miss，也不是自動成功保證；它是可稽核、可被選擇、但需要 execution 層如實記錄結果的狀態。

Disabled、<code>callable=false</code>、auth-required、disconnected、readiness unknown，以及 metadata sparse/opaque，都不能在 semantic consideration 前把已存在且 identity-resolved 的能力藏起來。Unknown Host hierarchy 以 <code>host_tool</code> 保留，不猜成 App、MCP 或其他 Host kind。

Codex / Host main model 負責 TaskAnalysis、semantic Skill selection、Execution Needs 與 semantic Provider selection。Python Router 負責 deterministic discovery、identity normalization、validation、fingerprint、handoff safety 與 Receipt finalization；Python 不從 raw prompt 自行呼叫 LLM，也不以 keyword mapping、semantic ranking 或 overlap winner 代替 Host reasoning。

## High-recall discovery 與 selection

新版流程用 deterministic、bounded 的 sweep 批次處理 inventory，而不是先截斷成舊式 top-k shortlist。每筆 resolved present Skill 與 formal Provider 都至少接受一次 semantic consideration；metadata quality 與 readiness 是診斷欄位，接受 consideration 不代表一定 selected。

selection policy：

- Skill 沒有固定數量。
- 任何對任務一部分具有合理可能幫助的 Skill 都可 selected；weakly relevant、redundant、overlapping，或另一個 Skill 已經足夠，都不是排除理由。
- 沒有固定 Skill maximum，也沒有 top-k semantic truncation；只要各自可能對任務有幫助，就可以同時選入多個 Skills。
- uncertain-but-plausibly-useful 的能力，tie-break 取 SELECT。
- <code>Skill Coverage Check</code> 最多執行一次，也可以補入與既有 Skill 重疊但仍可能有幫助的能力。
- 不用 keyword-to-ID mapping、手寫 selection、synthetic record 或 Python 代替語意 selection。

Selection policy 是 <code>ANY PLAUSIBLE TASK-RELEVANT VALUE → SELECT</code>，但不是 blind select everything；明確不相關、exact canonical duplicate、明確 constraint 或安全邊界不允許的能力仍可排除。Semantic redundancy 只作 diagnostic，不作 semantic dedupe。

## Skill source binding 與 freshness recovery

同一 canonical Skill 可以有多個 authoritative physical sources。beta9 會保留 multiple provenance，但建立一個 deterministic selected source，並讓 current logical profile、profile fingerprint、handoff path、handoff instructions 與 handoff fingerprint 全部來自同一個 source，避免 profile 使用 Source A 而 handoff 使用 Source B。

普通 route 不會因 freshness policy 而重新 polling 全部 Skills。只有 selected Skill 在 full handoff 時發生 fingerprint mismatch，才進入一次 bounded targeted refresh：重新驗證該 Skill 的已知 authoritative source，建立新的 immutable inventory snapshot，然後 retry 一次。第二次仍 mismatch 就是 <code>HANDOFF_REJECTION</code>；如果 selection-visible semantic digest 改變，則回報 <code>SELECTION_REVALIDATION_REQUIRED</code>，交回 Host controller，不由 Python 靜默重新選擇。

### Capability miss 分類

Router 不把所有失敗都簡化成 <code>NO MATCH</code>：

| 分類 | 意義 |
| --- | --- |
| <code>DISCOVERY_MISS</code> | 可信 inventory 沒有發現本來應可 formal discover 的記錄。 |
| <code>SEMANTIC_CONSIDERATION_MISS</code> | 已發現、identity resolved 且存在，但沒有進入 semantic consideration。 |
| <code>BASE_SELECTION_MISS</code> | 已被考量，卻錯過本來 plausible 的 base selection。 |
| <code>COVERAGE_CHECK_MISS</code> | coverage check 沒補上明確、必要的 coverage gap。 |
| <code>HANDOFF_REJECTION</code> | 後續 handoff 或 execution 邊界拒絕了選擇。 |
| <code>EXPLICIT_NEGATIVE</code> | 使用者或任務明確否定該能力。 |
| <code>CONSTRAINT_EXCLUSION</code> | 由安全、環境或其他明確 constraint 排除。 |

本次 acceptance 對目前可信、可 formal discover 的 inventory 要求 <code>Relevant Skill Miss = 0</code>、<code>Relevant Provider Miss = 0</code>、<code>Discovery Miss = 0</code>、<code>Semantic Consideration Miss = 0</code>。這個要求不會把「明確不相關」誤算成 miss。

## 安裝

### Windows / PowerShell

以下指令可直接貼到 PowerShell。它會使用目前使用者的 <code>~/.agents/skills</code>，不包含任何私人絕對路徑：

~~~powershell
$skillRoot = Join-Path $HOME ".agents\skills\codex-capability-router"
if (Test-Path $skillRoot) {
    if (-not (Test-Path (Join-Path $skillRoot ".git"))) {
        throw "Target exists and is not a Git checkout: $skillRoot"
    }
    git -C $skillRoot pull --ff-only
} else {
    New-Item -ItemType Directory -Force -Path (Split-Path $skillRoot) | Out-Null
    git clone https://github.com/Lzxpan/codex-capability-router.git $skillRoot
}
python -m unittest discover -s (Join-Path $skillRoot "tests") -p "test_*.py"
python -m compileall -q (Join-Path $skillRoot "codex_capability_router") (Join-Path $skillRoot "tests")
~~~

### macOS / Linux

以下指令可直接貼到 POSIX shell。<code>${HOME}</code> 會由 shell 展開成目前使用者的 home directory：

~~~bash
skill_root="${HOME}/.agents/skills/codex-capability-router"
if [ -e "$skill_root" ]; then
    if [ ! -d "$skill_root/.git" ]; then
        printf '%s\n' "Target exists and is not a Git checkout: $skill_root" >&2
        exit 1
    fi
    git -C "$skill_root" pull --ff-only
else
    mkdir -p "$(dirname "$skill_root")"
    git clone https://github.com/Lzxpan/codex-capability-router.git "$skill_root"
fi
python -m unittest discover -s "$skill_root/tests" -p "test_*.py"
python -m compileall -q "$skill_root/codex_capability_router" "$skill_root/tests"
~~~

需求：Python 3.11 或更新版本。套件本身沒有 runtime dependency；測試使用 Python standard library。若既有目錄不是 Git checkout，安裝指令會停止，不會覆寫它。

## Quick Start

### A. 簡單任務

~~~text
請把這段 release note 改寫成三個清楚、適合使用者閱讀的重點。
保留版本號與 API 名稱，最後列出任何不確定處。
~~~

Router 會先建立單一任務理解，選出對任務任何部分具有合理可能幫助的 Skill。明確不相關的能力仍可排除；重複與 overlap 不再是排除理由。

### B. 複合工程任務

~~~text
請檢查這個 repository 的設定檔解析流程，補上缺少的 regression test，
確認 Python 語法與測試，並說明尚未執行的外部工具鏈驗證。
~~~

這類任務可能同時 selected repository survey、implementation-aware verification、testing 與 technical explanation 等多個 Skills；只要各 Skill 對任務有合理可能的幫助，就可以一起入選，重疊與 redundancy 不限制數量。

### C. 圖像 + 文件 + repository validation

~~~text
請重新製作中英文 README，產生一致角色風格的原創 hero、功能漫畫與 architecture diagram，
檢查 local links、圖片引用、UTF-8、U+FFFD、privacy 與測試結果，
最後回報 sanitized FINALIZED Receipt 與尚未完成的硬體或外部驗證。
~~~

這類任務可以 multi-Skill + multi-Provider：例如 technical writing、visual explanation、image generation、repository verification 與目前 session 的 <code>builtin_tool</code>。範例不需要也不應該手動指定 capability ID。

## Sanitized Receipt 範例

以下是移除私人路徑、credential、hidden prompt 與 chain-of-thought 後的 illustrative/sanitized 結構示例；數字不是 live inventory，也不是 UI expected constants：

~~~json
{
  "selection_state": "FINALIZED",
  "task_analysis": {
    "work_items": 5,
    "material_deliverables": 9,
    "constraints": 5,
    "quality_expectations": 5
  },
  "skills": {
    "discovered": 550,
    "available": 549,
    "semantically_considered": 549,
    "never_considered": 0,
    "plausible": 8,
    "selected": 8
  },
  "supporting_providers": [
    {"kind": "builtin_tool", "readiness": "PRESENT_UNVERIFIED"},
    {"kind": "builtin_tool", "readiness": "PRESENT_UNVERIFIED"},
    {"kind": "builtin_tool", "readiness": "PRESENT_UNVERIFIED"},
    {"kind": "builtin_tool", "readiness": "PRESENT_UNVERIFIED"}
  ],
  "provider_metrics": {
    "host_snapshot_capabilities": 4,
    "discovered": 4,
    "metadata_sufficient": 4,
    "semantically_considered": 4,
    "never_considered": 0,
    "plausible": 4,
    "selected": 4
  },
  "receipt": {
    "fingerprint": "481ac81362e19674a5fbc1023cefdeb74377d4de002e4a43f9f9cb48ab8d32d0"
  }
}
~~~

<code>FINALIZED</code> 表示 selection route 已完成且 receipt 可追溯；它不表示四個 Provider 的 endpoint 在所有環境都已成功執行。

Selection Receipt 只由 <code>route()</code> finalize 一次；外部執行層的 <code>ExecutionAttempt</code> 是獨立且 immutable 的結果證據，不可改寫已 finalized 的 Receipt。

## Safety 與執行邊界

- Router 是 read-only routing library，不是 workflow engine。
- <code>route(SelectionRouteInput(...))</code> 只建立 selection 與 receipt，不直接呼叫選定 endpoint。
- 不自動 network discovery、OAuth、login、install、flash、release 或 publish。
- 可信 discovery、metadata sufficiency、readiness 與 execution outcome 分開記錄。
- 外部執行層若實際嘗試能力，應建立 <code>ExecutionAttempt</code>，如實保存 success、failure、blocked 或 unavailable，不可把失敗藏在 selection receipt 裡。
- Router 不讀取 hidden prompt、chain-of-thought、credential 或 private capability inventory。

## Current limitations

- Router 目前是 beta；selection 與 receipt schema 仍可能演進。
- <code>PRESENT_UNVERIFIED</code> 代表能力被公開暴露且 metadata 足夠，不代表 endpoint、權限、網路或第三方服務已可用。
- Router 不會替你執行外部工具，也不會替你做硬體、燒錄、GPIO、UART、sensor 或實機驗收。
- <code>never_considered = 0</code> 的保證範圍是本次可信、identity-resolved、可 formal discover 的 present inventory 與 bounded sweep；metadata quality 只作診斷，不是普遍保證，也不是對未知外部世界的宣稱。
- <code>RootPlanSnapshot</code> 與 <code>SkillInventorySnapshot</code> 是 caller/session-owned cache；source 或明確 controller state 改變時會 refresh，不是跨 process 永久 cache。
- selected Skill 的 freshness mismatch 只觸發 targeted refresh 一次，不會把 ordinary route 變成全量 Skill polling。
- Plugin 是 package/provenance only，不應被寫成 formal Provider。
- 圖片與 README 的 GitHub 最終呈現仍受 repository theme、網路資源與使用者環境影響。

## Validation / testing

在 repository root 執行：

~~~powershell
python -m unittest discover -s tests -p "test_*.py"
python -m compileall -q codex_capability_router tests
git diff --check
~~~

README V2 的文件 QA 還應檢查：

- README.md 與 README.en.md 的 local links、image references 都指向存在的檔案。
- 六個主要視覺資產可讀、無裁切、無 watermark、無既有 IP 角色，且貓狗角色與色彩語言一致。
- architecture diagram 節點完整、順序正確、沒有文字重疊或裁切；<code>Host Capability Snapshot</code> 位於 <code>Execution Needs</code> 後、Provider sweep 前，<code>ExecutionAttempt</code> 位於 <code>FINALIZED Receipt</code> 後。
- 所有文字檔以 UTF-8 解碼，沒有 <code>U+FFFD</code>；不含私人絕對路徑、credential 或 token。
- 測試、compileall 與 diff check 的結果要分開回報，不把 host/static 證據寫成 formal external build 或 hardware PASS。

目前專案的測試屬於 host/static evidence。沒有實際 target hardware、flashing、外部 endpoint 或 GitHub browser rendering 時，請標記 <code>NOT_VERIFIED</code> 或 <code>HARDWARE_PENDING</code>。

## Source map

- <code>codex_capability_router/routing.py</code>：正式 <code>route(SelectionRouteInput(...))</code> 與 <code>FINALIZED</code> receipt。
- <code>codex_capability_router/skill_plan.py</code>：固定 authoritative Skill roots、known-child coverage 與 immutable root-plan snapshot。
- <code>codex_capability_router/plugin_store.py</code>：logical Plugin 到 deterministic exact package root 的 bounded resolution。
- <code>codex_capability_router/inventory.py</code>：Skill inventory、source binding、profile fingerprint 與 targeted freshness snapshot。
- <code>codex_capability_router/inventory_sweep.py</code>：bounded full inventory semantic sweep。
- <code>codex_capability_router/host_snapshot.py</code>：typed <code>HostCapabilitySnapshot</code>。
- <code>codex_capability_router/provider_adapters.py</code>：formal Provider discovery 與 readiness。
- <code>codex_capability_router/supporting_context.py</code>：Supporting Provider selection context 與 <code>ExecutionAttempt</code> 邊界。
- <code>references/</code>：discovery/provenance、routing policy 與語系規範。
- <code>tests/</code>：foundation、provider、coverage-first、high-recall 與 host snapshot regression tests。

## License

MIT
