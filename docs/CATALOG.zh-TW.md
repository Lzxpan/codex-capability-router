# Codex Capability Router Catalog（繁體中文）

由單一 canonical registry 產生。Capability ID 與 enum value 保持不變。

## Capability: `codex-capability-router`

- ID: codex-capability-router
- 名稱: Codex Capability Router
- 類型: skill
- 狀態: installed
- 類別: 能力路由、Router 路由器
- 主要用途: 支援能力路由、Router 路由器相關能力建議。
- 適用時機: 任務提及：firmware, 韌體, react, ui, 介面, pull request, pr, code review, 研究, research, document, 文件, spreadsheet, 試算表, data analysis, design, 設計。
- 避免時機: 任務不符合類別或 triggers 時。
- 重疊群組: null
- 優先級: 100

## Capability: `figma`

- ID: figma
- 名稱: Figma
- 類型: tool
- 狀態: installed
- 類別: 設計、UI 介面、UI/UX 設計、UX 使用者體驗
- 主要用途: 支援設計、UI 介面、UI/UX 設計、UX 使用者體驗相關能力建議。
- 適用時機: 任務提及：ui, ux, design, prototype, 介面, 使用者體驗, 設計, 原型。
- 避免時機: 同一重疊群組已有更合適的能力時。
- 重疊群組: ui-ux-design
- 優先級: 10

## Capability: `firmware-debugging`

- ID: firmware-debugging
- 名稱: Firmware Debugging
- 類型: skill
- 狀態: installed
- 類別: 除錯、韌體、韌體除錯
- 主要用途: 支援除錯、韌體、韌體除錯相關能力建議。
- 適用時機: 任務提及：firmware, 韌體, microcontroller, mcu, embedded, 嵌入式, uart, serial, debug, 除錯, 故障。
- 避免時機: 同一重疊群組已有更合適的能力時。
- 重疊群組: debugging-tool
- 優先級: 10

## Capability: `generic-code-review`

- ID: generic-code-review
- 名稱: Generic Code Review
- 類型: tool
- 狀態: installed
- 類別: 程式碼審查、通用
- 主要用途: 支援程式碼審查、通用相關能力建議。
- 適用時機: 任務提及：review, code, 程式碼, 審查。
- 避免時機: 同一重疊群組已有更合適的能力時。
- 重疊群組: code-review
- 優先級: 1

## Capability: `generic-data-analysis`

- ID: generic-data-analysis
- 名稱: Generic Data Analysis
- 類型: tool
- 狀態: installed
- 類別: 資料分析、通用
- 主要用途: 支援資料分析、通用相關能力建議。
- 適用時機: 任務提及：data, analysis, 資料, 分析。
- 避免時機: 同一重疊群組已有更合適的能力時。
- 重疊群組: data-analysis
- 優先級: 1

## Capability: `generic-debugger`

- ID: generic-debugger
- 名稱: Generic Debugger
- 類型: tool
- 狀態: installed
- 類別: 除錯、通用
- 主要用途: 支援除錯、通用相關能力建議。
- 適用時機: 任務提及：debug, bug, 錯誤, 問題。
- 避免時機: 同一重疊群組已有更合適的能力時。
- 重疊群組: debugging-tool
- 優先級: 1

## Capability: `generic-search`

- ID: generic-search
- 名稱: Generic Search
- 類型: tool
- 狀態: available
- 類別: 通用、搜尋
- 主要用途: 支援通用、搜尋相關能力建議。
- 適用時機: 任務提及：search, 搜尋, 查詢。
- 避免時機: 同一重疊群組已有更合適的能力時。
- 重疊群組: research-search
- 優先級: 1

## Capability: `generic-ui-debugger`

- ID: generic-ui-debugger
- 名稱: Generic UI Debugger
- 類型: tool
- 狀態: installed
- 類別: 通用、UI 介面
- 主要用途: 支援通用、UI 介面相關能力建議。
- 適用時機: 任務提及：ui, bug, 錯誤, 問題。
- 避免時機: 同一重疊群組已有更合適的能力時。
- 重疊群組: ui-debugging
- 優先級: 1

## Capability: `offline-firmware-debugger`

- ID: offline-firmware-debugger
- 名稱: Offline Firmware Debugger
- 類型: tool
- 狀態: unavailable
- 類別: 韌體、韌體除錯
- 主要用途: 支援韌體、韌體除錯相關能力建議。
- 適用時機: 任務提及：firmware, 韌體, uart, debug, 除錯。
- 避免時機: 狀態為 unavailable 時。
- 重疊群組: debugging-tool
- 優先級: 50

## Capability: `pr-code-review`

- ID: pr-code-review
- 名稱: PR Code Review
- 類型: skill
- 狀態: installed
- 類別: 程式碼審查、PR 程式碼審查、審查
- 主要用途: 支援程式碼審查、PR 程式碼審查、審查相關能力建議。
- 適用時機: 任務提及：pull request, pr, code review, review, diff, 拉取請求, 程式碼審查。
- 避免時機: 同一重疊群組已有更合適的能力時。
- 重疊群組: code-review
- 優先級: 10

## Capability: `react-ui-debugging`

- ID: react-ui-debugging
- 名稱: React UI Debugging
- 類型: skill
- 狀態: installed
- 類別: React、React 介面錯誤、UI 介面
- 主要用途: 支援React、React 介面錯誤、UI 介面相關能力建議。
- 適用時機: 任務提及：react, component, frontend, ui, bug, css, 元件, 介面, 錯誤。
- 避免時機: 同一重疊群組已有更合適的能力時。
- 重疊群組: ui-debugging
- 優先級: 10

## Capability: `research-document-search`

- ID: research-document-search
- 名稱: Research Document Search
- 類型: skill
- 狀態: available
- 類別: 文件搜尋、研究、研究文件搜尋
- 主要用途: 支援文件搜尋、研究、研究文件搜尋相關能力建議。
- 適用時機: 任務提及：research, document, search, paper, 研究, 文件, 搜尋, 查資料。
- 避免時機: 同一重疊群組已有更合適的能力時。
- 重疊群組: research-search
- 優先級: 10

## Capability: `spreadsheet-data-analysis`

- ID: spreadsheet-data-analysis
- 名稱: Spreadsheet Data Analysis
- 類型: skill
- 狀態: installed
- 類別: 資料分析、試算表、試算表資料分析
- 主要用途: 支援資料分析、試算表、試算表資料分析相關能力建議。
- 適用時機: 任務提及：spreadsheet, csv, data analysis, excel, table, 試算表, 資料分析, 表格。
- 避免時機: 同一重疊群組已有更合適的能力時。
- 重疊群組: data-analysis
- 優先級: 10

## Capability: `ux-pilot`

- ID: ux-pilot
- 名稱: UX Pilot
- 類型: tool
- 狀態: available
- 類別: 設計、UI/UX 設計、UX 使用者體驗
- 主要用途: 支援設計、UI/UX 設計、UX 使用者體驗相關能力建議。
- 適用時機: 任務提及：ui, ux, design, prototype, 介面, 設計, 原型。
- 避免時機: 同一重疊群組已有更合適的能力時。
- 重疊群組: ui-ux-design
- 優先級: 8

## Capability: `visily`

- ID: visily
- 名稱: Visily
- 類型: tool
- 狀態: available
- 類別: 設計、UI 介面、UI/UX 設計
- 主要用途: 支援設計、UI 介面、UI/UX 設計相關能力建議。
- 適用時機: 任務提及：ui, design, prototype, 介面, 設計, 原型。
- 避免時機: 同一重疊群組已有更合適的能力時。
- 重疊群組: ui-ux-design
- 優先級: 7
