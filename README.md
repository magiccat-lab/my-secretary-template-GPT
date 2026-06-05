# my-secretary-template-GPT

GPT (OpenAI codex CLI) を脳にした、常駐型 AI 秘書のテンプレート。

Discord を窓口に、あなた専属の秘書エージェントが 24 時間動き続ける。予定・タスク・
メモを Notion で管理し、cron で定期処理を回し、必要なら自分で調べて返事をする。
数学者向けに **Lean (定理証明) / GeoGebra (作図・CAS) / TeX (数式組版)** の MCP を
標準同梱している。

> Claude 版が欲しい人へ: 脳を Claude にした姉妹テンプレ
> [my-secretary-template](https://github.com/magiccat-lab/my-secretary-template) がある。
> 本リポジトリはその**脳を GPT (codex) に差し替えた版**で、設計の要所が異なる (下表)。

## 何ができるか

- **Discord で会話**: メンションやメッセージにあなたの秘書が返事をする
- **タスク / 予定管理**: Notion DB と同期、リマインド
- **定期処理**: 朝の挨拶・天気・予定通知などを cron で自動実行
- **自律作業**: 調べもの・文書作成・ファイル整理を指示すると自分で進める
- **数学支援**: Lean で証明検証、GeoGebra で作図、TeX で数式入りの文書生成

## アーキテクチャ

```
Discord / cron
      │  (HTTP)
      ▼
webhook_server.py ──► /tmp/codex_queue.txt (base64 行追記)
                              │
                              ▼
                  codex_queue_worker.py        ← 中核
                   ├─ 1 行ごとに codex exec --json を起動
                   ├─ session_id を保存し、次ターンは exec resume で文脈継続
                   └─ 毎ターン heartbeat を state file に書く
                              │
                              ▼
                     codex (GPT) = 脳
                   ├─ AGENTS.md の人格で振る舞う
                   ├─ 返信は discord_send.py を bash で叩く
                   └─ Lean / GeoGebra / TeX MCP を使う
                              │
session_watchdog.py (cron */2) ─ heartbeat の鮮度を見て固着を自動復帰
```

## Claude 版との設計差分

| 層 | Claude 版 | GPT (codex) 版 |
| --- | --- | --- |
| 脳 | `claude` を screen 内 TUI で常駐 | `codex exec --json` を job ごとに起動 (TUI 常駐しない) |
| 文脈継続 | TUI セッション | `codex exec resume <session_id>` で毎ターン継続 |
| 受信 | webhook → queue → `screen -X stuff` で TUI 注入 | webhook → queue → worker が exec 投入 |
| 送信 | Discord plugin の reply tool | `discord_send.py` を bash で直接送信 |
| 人格 / 設定 | `CLAUDE.md` + `@AGENT/*` import | `AGENTS.md` + `~/.codex/config.toml` |
| 無人承認 | `--dangerously-skip-permissions` | `approval_policy="never"` + `sandbox_mode="workspace-write"` |
| 固着検知 | screen hardcopy の正規表現 | worker の heartbeat state file の鮮度 |
| MCP | Claude Code の MCP 設定 | `~/.codex/config.toml [mcp_servers]` |

### なぜ TUI 常駐をやめたか

codex で TUI を常駐させ `screen -X stuff` でプロンプトを流し込む方式は、承認モーダル・
paste 検出・TUI 再描画で壊れやすく、長時間運用では会話文脈も劣化する。`codex exec` は
codex 公式の自動化インターフェースで、stdin・JSONL イベント・固定 sandbox 設定をサポート
し、`codex exec resume` でセッションを継続できる。本テンプレはこの **job 駆動** を採用する。

## ディレクトリ構成

```
start_server.sh              起動 (screen に worker + webhook を立てる)
config.codex.toml.template   ~/.codex/config.toml の雛形 (承認policy + 数学MCP)
AGENTS.md                    codex が読む唯一の指示書 (人格・返信方法・安全ルール)
AGENT/
  IDENTITY.md                秘書の人格 (SETUP で記入)
  USER.md                    ユーザー情報 (SETUP で記入)
  JOBS.md                    インフラ・運用メモ
scripts/
  codex_queue_worker.py      中核: queue → codex exec → resume 継続 + heartbeat
  webhook_server.py          受信 (Discord/cron → queue)
  discord_send.py            送信 (token 解決は env / .env / ~/.codex の順、~/.claude 非依存)
  session_watchdog.py        heartbeat ベースの固着検知・自動復帰
  lib/discord_post.py        送信ヘルパー
  integrations/notion/       Notion 連携
data/
  handoff.md                 直近の引き継ぎ文脈
  pending_tasks.json         タスク
```

## セットアップ

[SETUP.md](SETUP.md) に全手順 (所要 30〜60 分) と smoke test がある。最短の流れ:

```bash
npm i -g @openai/codex && codex login        # 1. 脳 (ChatGPT 課金アカウント、API課金不要)
git clone https://github.com/magiccat-lab/my-secretary-template-GPT ~/secretary-gpt
cd ~/secretary-gpt && pip install -r requirements.txt
cp config.codex.toml.template ~/.codex/config.toml   # 2. 承認policy + MCP を編集
cp .env.template .env                                 # 3. DISCORD_BOT_TOKEN を記入
# 4. AGENT/IDENTITY.md と AGENT/USER.md に人格・ユーザー情報を記入
bash start_server.sh                                  # 5. 起動
```

## 必要なもの

- Linux / WSL、Python 3.10+、Node.js 18+、`screen`、`lsof`
- ChatGPT 課金アカウント (codex の認証用。OpenAI API キー課金は**不要**)
- Discord bot トークン

## ライセンス

[LICENSE](LICENSE) を参照。
