# Discovery、Provenance 與 Registry 欄位

這份 reference 保存 `codex-capability-router` v0.1.0 的詳細 discovery 規則；`SKILL.md` 只保留 operational contract。

## 來源與權威順序

1. `runtime:*`：目前執行環境直接宣告的 capability，最高權威。
2. `cli:*`：核准的 verified read-only CLI probe。
3. `skill-root:*`：呼叫端明確 allowlist 的 skill root。
4. `manual:*`：呼叫端提供的描述性 inventory，不能當作執行授權。

同一 `id` 由最高順位 record 勝出。不同 status、`last_verified` 或其他可比對宣告不得靜默丟棄；合併結果保留 `provenance`、`conflicts`、`evidence`，並輸出 `source_conflict` diagnostic。

## 公開欄位

`id`、`name`、`kind`、`status`、`categories`、`triggers`、`priority`、`overlap_group`、`preferred_for`、`requires`、`source`、`last_verified` 是 canonical 欄位。可選的 `provenance`、`confidence`、`conflicts`、`evidence`、`recommendation_only` 用來保留本次 runtime merge 的可追溯資訊。

缺少可靠 status 時使用 `unknown`；不得從名稱、目錄或命令輸出推測 `installed`。`confidence` 僅接受 `0.0..1.0`。

## 核准 CLI probes

只允許：

- `codex plugin list --json`
- `codex mcp list --json`

adapter 使用 `shell=False`、固定 timeout 與 bounded JSON parsing。命令不存在、non-zero、timeout、malformed JSON 或 schema 不符時，回傳 `partial=true`、warning/evidence 與 `unknown` record；不得 crash，也不得把失敗轉成 available。不得執行任意 shell、marketplace query、credential/auth probing。

## 隱私邊界

`source` 是 abstract label。拒絕 secret-like fields、API keys、tokens、credentials、private inventory 與不必要的 absolute paths；diagnostic 也不得回顯被拒絕的值。Discovery 只讀取 caller 傳入的 explicit roots，不猜測 home 或其他 filesystem 路徑。
