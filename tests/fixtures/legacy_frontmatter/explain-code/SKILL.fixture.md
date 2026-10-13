---
name: explain-code
description: 使用於需要理解陌生程式碼、複雜邏輯、系統架構或程式流程時；協助用清楚結構說明程式如何運作、為何這樣設計，以及重要邊界條件。
allowed-tools: Read, Grep, Glob
metadata:
  short-description: 用清楚結構解釋陌生程式碼、複雜邏輯與系統設計。
  source_repo: zbruhnke/claude-code-starter
  source_path: .claude/skills/explain-code
  compatibility_note: 來源為 Claude skill，已將工具欄位轉為 Codex 相容 metadata。
  source_frontmatter:
    user-invocable: true
  source_tools: Read, Grep, Glob
---

Read the code before explaining it.
