# Deterministic Routing Policy

## 輸出層級

- `selected_primary`：最多 3 筆 `installed` capability。
- `selected_optional`：最多 2 筆 `available` capability。
- `recommendation_only`：只放明確標記的 trusted `unknown` advisory record；不等於 selected，也不代表可執行。
- `rejected_candidates`：保留 self-routing、unavailable、unknown、overlap 與 selection-limit 原因。
- `selection_evidence`：保留 selected/recommendation-only capability 的 level、reason codes、matched triggers 與 matched requirements，供雙語 explanation renderer 使用。

Router 是 advisory-only；不執行命令、載入 Plugin、安裝 capability、變更 permission 或替呼叫端授權。

## 必要排除

1. `codex-capability-router` 永遠不能推薦自己。
2. `unavailable` 永遠不能被選取。
3. `unknown` 永遠不能進 `selected_primary`、`selected_optional` 或 normal recommendation。
4. `unknown` 只有在 `source` 為 trusted runtime/manual，且輸入明確有 `recommendation_only=true` 時，才能進 `recommendation_only`。
5. 未找到可信候選時回傳空 selected tuple 與 `no_match` rationale，不湊數。

## 排序與界線

先以固定 task aliases 與 bounded phrase matching 判斷 relevance，再依 exact trigger、specialist、installed、preferred、evidence、priority、identifier 排序；同分以 `(id.casefold(), id)` 穩定決定。相同輸入必須產生相同 selected、rejected、rationale。

同一 `overlap_group` 只保留排序後第一筆。`unknown` 的 recommendation-only output 也依同一 deterministic key 排序。

Human-readable output 只將 `selection_evidence` 轉成短句 rationale；不輸出 hidden chain-of-thought，也不以未記錄的比較性宣稱補理由。
