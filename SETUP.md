# SETUP — GPT版秘書 (codex harness)

数学者向け秘書を codex CLI (GPT) で立ち上げる手順。所要 30〜60 分。

## 0. 前提

- Linux / WSL、Python 3.10+、Node.js 18+、`screen`、`lsof`
- ChatGPT 課金アカウント (codex の認証に使う。OpenAI API キー課金は不要)
- Discord bot トークン (秘書が喋るアカウント)

## 1. codex CLI

```bash
npm i -g @openai/codex
codex login          # ブラウザで ChatGPT アカウント認証
codex exec "echo ok" # 疎通確認 (ok が返れば成功)
```

`not supported when using Codex with a ChatGPT account` 等が出たら CLI が古い。
`npm i -g @openai/codex@latest` で更新。

## 2. リポジトリ配置

```bash
git clone <this-repo> ~/secretary-gpt
cd ~/secretary-gpt
pip install -r requirements.txt
export SECRETARY_HOME=~/secretary-gpt   # .bashrc にも追記推奨
```

## 3. codex 設定 (承認 + MCP)

```bash
mkdir -p ~/.codex
cp config.codex.toml.template ~/.codex/config.toml
```

`~/.codex/config.toml` を編集:
- `approval_policy="never"` / `sandbox_mode="workspace-write"` は無人運用前提。確認しながら
  使うなら緩める。
- `[mcp_servers.*]` の `command`/`args` を自分の環境のパスに直す。**使わない MCP は削る**。
- `required = false` のままにする (MCP 起動失敗で codex 全体が落ちるのを防ぐ)。

数学 MCP の入手:
- Lean: `uvx lean-lsp-mcp` (要 Lean4 / elan)
- GeoGebra: `npx -y @gebrai/gebrai` (GUI 依存。ヘッドレスは xvfb 検討)
- TeX: mcp-latex-server を clone & build (要 TeX Live)

## 4. シークレット

```bash
cp .env.template .env
# .env に DISCORD_BOT_TOKEN=... を記入 (codex 版は ~/.claude に依存しない)
```

## 5. 人格・ユーザー情報

- `AGENT/IDENTITY.md` … 秘書の名前・一人称・口調・性格
- `AGENT/USER.md` … ユーザー (数学者) の呼び方・専門・好み
- `AGENTS.md` の報告 channel ID を実際の Discord channel に合わせる

## 6. 起動

```bash
bash start_server.sh
screen -r secretary-gpt   # window0=worker, window1=webhook (Ctrl-a n で切替, Ctrl-a d で抜ける)
```

## 7. 固着検知 (cron)

```cron
*/2 * * * * SECRETARY_HOME=$HOME/secretary-gpt WATCHDOG_NOTIFY_CHANNEL=<CH_ID> /usr/bin/python3 $HOME/secretary-gpt/scripts/session_watchdog.py >> /tmp/codex_watchdog.log 2>&1
```

## 動作確認 (smoke test)

1. `codex exec "echo ok"` が通る
2. `python3 scripts/discord_send.py <CH_ID> "test"` が Discord に届く
3. webhook に POST → `/tmp/codex_queue.txt` に行が増える → worker ログに `codex exec 開始`
4. 秘書が `discord_send.py` 経由で返信する
5. `data/codex_worker_state.json` の `updated_at` が更新され続ける
6. worker を kill → 2 分以内に watchdog が再起動通知
