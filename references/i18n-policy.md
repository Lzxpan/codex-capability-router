# Bilingual Output 與 i18n Policy

支援的明確語言是 `en` 與 `zh-TW`；`auto` 僅依 user request 是否含繁中文字元選擇，無法判定時保守使用 `en`。

輸出規則：

- structural labels、rationale、status 說明依 locale 翻譯。
- capability ID、enum value、`overlap_group` 與 source label 保留 canonical 原值，方便比對與追溯。
- 空結果要明確輸出 no-recommendation，不以通用 capability 湊數。
- English 與 Traditional Chinese catalog 必須從同一份 registry 產生，ID 集合與排序一致。
- 顯示選用、判斷覆蓋與 Host 執行回報，三者分開；`FINALIZED` 不代表已執行或已驗證成功。
- 依既有 TaskAnalysis 區分結構化路由與相容呼叫；相容呼叫不宣稱已驗證批次，結構化路由仍不代表候選覆蓋完整。
- `render_recommendations` 的選填 `execution_attempts` 只接受綁定本 Receipt、已選 Provider 與原始需求的 `ExecutionAttempt`；保留各次失敗與重試結果。
- Provider 選用狀態直接讀取 `supporting_selection_status`，保留 `not_required`、`selected`、`no_present_supporting_provider`、`no_matching_supporting_capability`；不由缺少覆蓋資料推算。
- 沒有回報時顯示「Host 未回報執行結果」，不能推定沒有執行。缺少 coverage metrics 時顯示「未提供」，不能補成 `COMPLETE`。
- 執行欄位是 Host 回報，不是工具呼叫或硬體驗證的獨立證據；不得由選用清單推定執行、安裝或 physical acceptance。

詳細 catalog generator 與 deterministic UTF-8 artifact 驗證位於 `codex_capability_router/catalog.py` 及 `tests/test_catalog_phase4.py`。
