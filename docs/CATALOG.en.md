# Codex Capability Router Catalog

Generated from one canonical registry. Capability IDs and enum values are unchanged.

## Capability: `codex-capability-router`

- ID: codex-capability-router
- Name: Codex Capability Router
- Kind: skill
- Status: installed
- Category: capability routing, router
- Primary Purpose: Supports capability routing, router recommendations.
- Use When: Task mentions: firmware, 韌體, react, ui, 介面, pull request, pr, code review, 研究, research, document, 文件, spreadsheet, 試算表, data analysis, design, 設計.
- Avoid When: when the task does not match its category or triggers.
- Overlap Group: null
- Priority: 100

## Capability: `figma`

- ID: figma
- Name: Figma
- Kind: tool
- Status: installed
- Category: design, ui, ui ux design, ux
- Primary Purpose: Supports design, ui, ui ux design, ux recommendations.
- Use When: Task mentions: ui, ux, design, prototype, 介面, 使用者體驗, 設計, 原型.
- Avoid When: when another capability in the same overlap group is a better fit.
- Overlap Group: ui-ux-design
- Priority: 10

## Capability: `firmware-debugging`

- ID: firmware-debugging
- Name: Firmware Debugging
- Kind: skill
- Status: installed
- Category: debugging, firmware, firmware debugging
- Primary Purpose: Supports debugging, firmware, firmware debugging recommendations.
- Use When: Task mentions: firmware, 韌體, microcontroller, mcu, embedded, 嵌入式, uart, serial, debug, 除錯, 故障.
- Avoid When: when another capability in the same overlap group is a better fit.
- Overlap Group: debugging-tool
- Priority: 10

## Capability: `generic-code-review`

- ID: generic-code-review
- Name: Generic Code Review
- Kind: tool
- Status: installed
- Category: code review, generic
- Primary Purpose: Supports code review, generic recommendations.
- Use When: Task mentions: review, code, 程式碼, 審查.
- Avoid When: when another capability in the same overlap group is a better fit.
- Overlap Group: code-review
- Priority: 1

## Capability: `generic-data-analysis`

- ID: generic-data-analysis
- Name: Generic Data Analysis
- Kind: tool
- Status: installed
- Category: data analysis, generic
- Primary Purpose: Supports data analysis, generic recommendations.
- Use When: Task mentions: data, analysis, 資料, 分析.
- Avoid When: when another capability in the same overlap group is a better fit.
- Overlap Group: data-analysis
- Priority: 1

## Capability: `generic-debugger`

- ID: generic-debugger
- Name: Generic Debugger
- Kind: tool
- Status: installed
- Category: debugging, generic
- Primary Purpose: Supports debugging, generic recommendations.
- Use When: Task mentions: debug, bug, 錯誤, 問題.
- Avoid When: when another capability in the same overlap group is a better fit.
- Overlap Group: debugging-tool
- Priority: 1

## Capability: `generic-search`

- ID: generic-search
- Name: Generic Search
- Kind: tool
- Status: available
- Category: generic, search
- Primary Purpose: Supports generic, search recommendations.
- Use When: Task mentions: search, 搜尋, 查詢.
- Avoid When: when another capability in the same overlap group is a better fit.
- Overlap Group: research-search
- Priority: 1

## Capability: `generic-ui-debugger`

- ID: generic-ui-debugger
- Name: Generic UI Debugger
- Kind: tool
- Status: installed
- Category: generic, ui
- Primary Purpose: Supports generic, ui recommendations.
- Use When: Task mentions: ui, bug, 錯誤, 問題.
- Avoid When: when another capability in the same overlap group is a better fit.
- Overlap Group: ui-debugging
- Priority: 1

## Capability: `offline-firmware-debugger`

- ID: offline-firmware-debugger
- Name: Offline Firmware Debugger
- Kind: tool
- Status: unavailable
- Category: firmware, firmware debugging
- Primary Purpose: Supports firmware, firmware debugging recommendations.
- Use When: Task mentions: firmware, 韌體, uart, debug, 除錯.
- Avoid When: when status is unavailable.
- Overlap Group: debugging-tool
- Priority: 50

## Capability: `pr-code-review`

- ID: pr-code-review
- Name: PR Code Review
- Kind: skill
- Status: installed
- Category: code review, pr code review, review
- Primary Purpose: Supports code review, pr code review, review recommendations.
- Use When: Task mentions: pull request, pr, code review, review, diff, 拉取請求, 程式碼審查.
- Avoid When: when another capability in the same overlap group is a better fit.
- Overlap Group: code-review
- Priority: 10

## Capability: `react-ui-debugging`

- ID: react-ui-debugging
- Name: React UI Debugging
- Kind: skill
- Status: installed
- Category: react, react ui bug, ui
- Primary Purpose: Supports react, react ui bug, ui recommendations.
- Use When: Task mentions: react, component, frontend, ui, bug, css, 元件, 介面, 錯誤.
- Avoid When: when another capability in the same overlap group is a better fit.
- Overlap Group: ui-debugging
- Priority: 10

## Capability: `research-document-search`

- ID: research-document-search
- Name: Research Document Search
- Kind: skill
- Status: available
- Category: document search, research, research document search
- Primary Purpose: Supports document search, research, research document search recommendations.
- Use When: Task mentions: research, document, search, paper, 研究, 文件, 搜尋, 查資料.
- Avoid When: when another capability in the same overlap group is a better fit.
- Overlap Group: research-search
- Priority: 10

## Capability: `spreadsheet-data-analysis`

- ID: spreadsheet-data-analysis
- Name: Spreadsheet Data Analysis
- Kind: skill
- Status: installed
- Category: data analysis, spreadsheet, spreadsheet data analysis
- Primary Purpose: Supports data analysis, spreadsheet, spreadsheet data analysis recommendations.
- Use When: Task mentions: spreadsheet, csv, data analysis, excel, table, 試算表, 資料分析, 表格.
- Avoid When: when another capability in the same overlap group is a better fit.
- Overlap Group: data-analysis
- Priority: 10

## Capability: `ux-pilot`

- ID: ux-pilot
- Name: UX Pilot
- Kind: tool
- Status: available
- Category: design, ui ux design, ux
- Primary Purpose: Supports design, ui ux design, ux recommendations.
- Use When: Task mentions: ui, ux, design, prototype, 介面, 設計, 原型.
- Avoid When: when another capability in the same overlap group is a better fit.
- Overlap Group: ui-ux-design
- Priority: 8

## Capability: `visily`

- ID: visily
- Name: Visily
- Kind: tool
- Status: available
- Category: design, ui, ui ux design
- Primary Purpose: Supports design, ui, ui ux design recommendations.
- Use When: Task mentions: ui, design, prototype, 介面, 設計, 原型.
- Avoid When: when another capability in the same overlap group is a better fit.
- Overlap Group: ui-ux-design
- Priority: 7
