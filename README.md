# secretary-template-gpt

Claude Code 版秘書テンプレ ([my-secretary-template](https://github.com/magiccat-lab/my-secretary-template)) の
**脳を GPT (codex CLI) に差し替えた版**。数学者向けに Lean / GeoGebra / TeX の MCP を同梱する。

## Claude Code 版との設計差分

| 層 | Claude Code 版 | GPT (codex) 版 |
| --- | --- | --- |
| 脳 | `claude` を screen 内 TUI 常駐 | `codex exec --json` を job ごとに起動 (TUI 常駐しない) |
| 受信 | webhook → queue → `screen -X stuff` で TUI 注入 | webhook → queue → **codex_queue_worker** が exec 投入 (流用) |
| 文脈継続 | TUI セッション | `codex exec resume <session_id>` で毎ターン継続 |
| 送信 | Discord plugin の reply tool | `discord_send.py` を bash で叩く (plugin 無し) |
| identity | `CLAUDE.md` + `@AGENT/*` import | `AGENTS.md` + `~/.codex/config.toml` |
| 承認 | `--dangerously-skip-permissions` | `approval_policy="never"` + `sandbox_mode="workspace-write"` |
| 固着検知 | screen hardcopy の regex | worker の **heartbeat state file** の鮮度 |
| MCP | Claude Code MCP 設定 | `~/.codex/config.toml [mcp_servers]` |

> なぜ TUI 常駐をやめたか: codex では TUI + `screen -X stuff` 注入は承認モーダル /
> paste 検出 / TUI 更新で壊れやすく、長時間で context も劣化する。`codex exec` が
> codex 公式の自動化パス。([codex 自身のレビューに基づく設計判断 2026-06-05])

## 構成

```
start_server.sh              起動 (screen に worker + webhook)
config.codex.toml.template   ~/.codex/config.toml の雛形 (承認policy + 数学MCP)
AGENTS.md                    codex が読む唯一の指示書 (人格・返信方法・安全ルール)
AGENT/IDENTITY.md            人格 (SETUP で記入)
AGENT/USER.md                ユーザー情報 (SETUP で記入)
scripts/
  codex_queue_worker.py      ★中核: queue → codex exec → resume で文脈継続 + heartbeat
  webhook_server.py          受信 (Discord/cron → queue)。流用
  discord_send.py            送信。token 解決を harness 非依存化
  session_watchdog.py        heartbeat ベースの固着検知。codex 用に書き直し
```

## SETUP

`SETUP.md` を参照。要点:
1. `npm i -g @openai/codex` → `codex login` (ChatGPT アカウント / 課金API不要)
2. `cp config.codex.toml.template ~/.codex/config.toml` → MCP パスを環境に合わせる
3. `.env` に `DISCORD_BOT_TOKEN` を記入
4. `AGENT/IDENTITY.md` / `AGENT/USER.md` に人格・ユーザー情報を記入
5. `bash start_server.sh` で起動、cron に `session_watchdog.py` を登録

## ステータス

🚧 雛形段階 (2026-06-05)。codex exec 経路・MCP 同梱・watchdog を実装済。
本番投入前に実機での疎通テスト (codex exec resume の挙動 / sandbox network / MCP 起動) が必要。
