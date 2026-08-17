# Codex Capability Router v0.1.0 — Architecture / Design

**Skill ID:** `codex-capability-router`
**Target:** `v0.1.0`
**Status:** Approved design specification

## 1. Architecture summary

Codex Capability Router v0.1.0 使用 **context-first hybrid architecture**。
Router 先接收執行環境提供的 runtime capability envelope，再合併三類唯讀能力來源：

1. 唯讀 CLI probes
2. 明確指定的 skill roots
3. 使用者提供的 manual import

Runtime capability envelope 是最高權威。其他來源只能補充、描述或降低不確定性，不能覆寫 runtime envelope 對目前環境的可用性、限制或安全邊界判定。

Router 的輸出只有 advisory recommendations：根據目前 context 與已發現的 capability，產生可解釋的建議與來源資訊。Router 不執行 capability、不安裝 Plugin，也不變更 permission。

## 2. Repository architecture

v0.1.0 的 repository 先保存經核准的架構與設計規格；本階段不建立 implementation、discovery、routing、Plugin、MCP 或測試程式碼。

概念上的 runtime 邊界如下：

```text
runtime capability envelope
        +
read-only CLI probes
        +
explicit skill roots
        +
manual import
        |
        v
normalization and merge
        |
        v
runtime registry
        |
        v
advisory router
        |
        v
recommendations with rationale and provenance
```

各邊界的責任保持單一：

- **Context input：** 提供本次執行環境、限制與要求的能力描述。
- **Discovery sources：** 以唯讀方式取得外部能力描述，並標示來源。
- **Normalization and merge：** 將不同格式轉成一致的 capability record，保留來源與衝突資訊。
- **Runtime registry：** 保存本次執行可用的合併結果；v0.1.0 不建立跨執行的私人持久化 inventory。
- **Advisory router：** 只做匹配、排序與說明，不呼叫外部 capability。

## 3. Capability discovery strategy

Discovery 採混合來源，但所有來源在 v0.1.0 都是唯讀：

- **Runtime capability envelope：** 由目前執行上下文直接提供，描述實際可用能力、限制、來源可信度與安全邊界。此來源具有最高權威。
- **唯讀 CLI probes：** 只查詢明確允許的本機命令或工具資訊；probe 不修改檔案、設定、環境、權限或安裝狀態。Probe 失敗時保留失敗來源與原因，不把失敗誤判為 capability 可用。
- **Explicit skill roots：** 只掃描呼叫方明確指定的 skill 根目錄，讀取可辨識的描述與 metadata；不自行猜測私人目錄，也不掃描未授權位置。
- **Manual import：** 接受呼叫方明確提供的 capability 描述，要求其附帶來源標籤與必要的識別資訊。Manual import 是描述輸入，不等於驗證或授權。

Discovery 結果必須保留來源、讀取時間、版本或識別資訊、可用性狀態與限制。來源間出現衝突時，優先採用 runtime envelope；若仍無法判定，保留衝突並降低建議信心，不以猜測補值。

Discovery 不執行 skill 或 Plugin，不載入未明確指定的程式碼，不安裝相依套件，也不改變使用者權限。

## 4. Registry strategy

Registry 是本次執行的標準化 capability record 集合。每筆 record 至少描述：

- capability identifier 與人類可讀名稱
- capability 類型或用途標籤
- 來源與 provenance
- 版本或其他可比對的識別資訊（若來源有提供）
- 可用性、限制與相容 context
- 發現時間與信心資訊

Registry 的合併規則如下：

1. 先建立 runtime envelope 的權威 records。
2. 將 CLI probes、explicit skill roots 與 manual import 正規化後合併。
3. 以穩定 identifier 去除相同來源的重複項，保留可追溯的 provenance。
4. 不靜默覆寫衝突；衝突須成為 record 的狀態或診斷資訊。
5. 不把「被描述」視為「已驗證可執行」；registry 只描述能力狀態，不授予執行權。

v0.1.0 registry 以 runtime scope 為界，不保存 private plugin inventory、帳戶資料或 secrets，也不建立跨執行的自動同步目錄。

## 5. Routing strategy

Router 接收使用者 intent、目前 context 與 runtime registry，輸出零個或多個 advisory recommendations。每個 recommendation 應包含：

- 建議使用的 capability identifier
- 與 intent 或 context 的匹配理由
- capability 的來源與目前狀態
- 必要限制、未確認事項或信心資訊

匹配與排序採可解釋的規則：先排除與 runtime envelope 或明確限制不相容的項目，再依 context 相容性、用途匹配與來源可信度排序。無法安全判定時輸出無建議或低信心建議，並說明缺少的資訊。

Routing 僅產生資料與說明，不呼叫 capability、不執行命令、不安裝 Plugin、不修改設定、不提升權限，也不代替呼叫方做最終授權決定。

## 6. Security/privacy strategy

安全與隱私邊界以最小資料與唯讀為原則：

- 只接受完成基本格式與邊界驗證的 envelope、probe 結果、skill metadata 與 manual import。
- 不在 Design、registry 或 recommendation 中保存或輸出 API keys、tokens、credentials、private account data 或 private plugin inventory。
- 不把 personal absolute paths 寫入設計資料；來源路徑只能以呼叫方可控且必要的抽象識別表示。
- Explicit skill roots 是 allowlist 輸入；未列入的路徑不掃描。
- Probe 與 import 的輸入視為不可信描述；不得因描述內容直接取得執行、安裝或 permission 變更能力。
- Runtime capability envelope 的限制與拒絕結果優先於較低可信來源的宣告。
- 建議輸出需保留 provenance，讓呼叫方能追溯建議依據並自行決定是否採用。

v0.1.0 不處理 secrets 管理、帳戶驗證、遠端傳輸或跨使用者資料共享；這些事項不應由 Router 以隱含方式承擔。

## 7. v0.1 scope

v0.1.0 包含：

- 定義 runtime capability envelope 與其最高權威地位。
- 定義唯讀 CLI probes、explicit skill roots 與 manual import 三種 discovery 來源。
- 定義 capability record、provenance、可用性、限制與衝突表示方式。
- 定義三類來源與 runtime envelope 的正規化及合併原則。
- 定義以 context 與 intent 為輸入的可解釋 advisory routing 結果。
- 定義唯讀、安全、隱私與不改變 permission 的邊界。
- 保存本核准 Architecture / Design Specification。

v0.1.0 不包含任何 capability 執行或安裝行為。

## 8. Deferred scope

下列項目明確不屬於 v0.1.0：

- 執行 skill、Plugin、MCP 或任意外部 capability。
- 安裝、更新、移除或管理 Plugin、skill 或相依套件。
- 自動變更 permission、policy、環境設定或系統狀態。
- 未經明確指定的目錄掃描、遠端 discovery 或網路 registry。
- 跨執行、跨帳戶或跨使用者的 private capability inventory 持久化。
- API keys、tokens、credentials 的儲存、輪替、代理或驗證。
- 帳戶整合、身份驗證、審計平台與遠端資料共享。
- 以使用者回饋自動改寫 routing policy 或自動學習排序規則。
- GUI、公開 API、服務化部署、背景監控與自動修復。

這些項目若未來需要，必須另行核准其權限、資料、失敗處理與版本範圍，不由本規格推定為 v0.1.0 的隱含需求。

## 9. Design decisions

1. **Context-first：** runtime capability envelope 代表目前執行環境，故其判定高於靜態或手動來源。
2. **Hybrid discovery：** CLI probes、explicit skill roots 與 manual import 各自涵蓋不同描述來源，合併後仍保留 provenance。
3. **Read-only boundary：** v0.1.0 只觀察與整理能力，不改變外部狀態。
4. **Advisory-only routing：** Router 提供可解釋建議，不把推薦誤當成執行或授權。
5. **Runtime-scoped registry：** 先以本次執行的合併結果滿足需求，避免未被要求的私人 inventory 與持久化複雜度。
6. **Explicit inputs：** skill roots 與 manual import 必須由呼叫方明確提供，避免非預期資料收集。
7. **Fail conservatively：** 缺少資訊、來源衝突或 probe 失敗時保留不確定性，不以猜測宣告可用。
8. **No implicit expansion：** 執行、安裝、permission 變更與遠端整合均不由 v0.1.0 設計推導出來。
