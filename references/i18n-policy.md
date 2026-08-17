# Bilingual Output 與 i18n Policy

支援的明確語言是 `en` 與 `zh-TW`；`auto` 僅依 user request 是否含繁中文字元選擇，無法判定時保守使用 `en`。

輸出規則：

- structural labels、rationale、status 說明依 locale 翻譯。
- capability ID、enum value、`overlap_group` 與 source label 保留 canonical 原值，方便比對與追溯。
- 空結果要明確輸出 no-recommendation，不以通用 capability 湊數。
- English 與 Traditional Chinese catalog 必須從同一份 registry 產生，ID 集合與排序一致。
- 顯示文字不得宣稱 capability 已執行、安裝、硬體通過或 physical acceptance。

詳細 catalog generator 與 deterministic UTF-8 artifact 驗證位於 `codex_capability_router/catalog.py` 及 `tests/test_catalog_phase4.py`。
