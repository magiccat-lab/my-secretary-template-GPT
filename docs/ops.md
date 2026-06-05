# ops.md — 運用（死活監視・再起動・ログ・トラブル）GPT版

24/7 稼働を回すための運用情報と、壊れたときのランブック。秘書（codex）自身もこれを
読みながら自己診断する。

## 構成のおさらい

screen セッション `secretary-gpt` に 3 プロセスが常駐:
- **codex_queue_worker.py**（脳）… queue を読んで `codex exec` を起動、`exec resume`
  で文脈継続、毎ターン `data/codex_worker_state.json` に heartbeat を書く
- **webhook_server.py**（cron/HTTP 受信）… port 8781
- **discord_listener.py**（Discord 受信）… Gateway 接続、allowlist ch を queue へ

## 死活・固着監視

`scripts/session_watchdog.py` を cron `*/2` で回す。判定は heartbeat ベース:
- worker プロセスが死んでいれば再起動
- `status=running` のまま `WATCHDOG_TURN_STALE`(既定1800s) 超なら固着とみなし再起動
- queue に未処理があるのに `IDLE_BACKLOG`(既定180s) 無更新なら再起動

手動で見る:
```bash
cat ~/secretary/data/codex_worker_state.json   # updated_at / status
screen -list                                    # secretary-gpt
curl -s http://localhost:8781/health            # webhook
```

手動再起動:
```bash
bash ~/secretary/start_server.sh
# 脳だけ蹴り直す:
pkill -f codex_queue_worker.py && bash ~/secretary/start_server.sh
```

## 再起動 / セッションリセット

`codex exec resume` の文脈が長期で肥大するのを防ぐため、cron で毎日 04:00 に
セッションファイルを消して fresh 起動する（`docs/cron.md`）:
```bash
rm -f /tmp/codex_secretary_session.txt && bash ~/secretary/start_server.sh
```

## ログの場所

```bash
tail -n 50 /tmp/codex_worker.log       # 脳: exec 開始/終了/agent 発話
tail -n 50 /tmp/codex_discord.log      # 受信: enqueue
tail -n 50 /tmp/codex_webhook.log      # cron/HTTP 受信
tail -n 50 /tmp/session_watchdog.log   # watchdog 判定
```

## ランブック（壊れたとき）

### 返信しない
1. `screen -list` に `secretary-gpt` が居るか
2. `/tmp/codex_worker.log` で `codex exec` が回っているか
3. `/tmp/codex_discord.log` で `enqueue` が出ているか（出てなければ受信側＝listener の問題）
4. 直らなければ `bash ~/secretary/start_server.sh`

### 脳が認証エラー
```bash
codex login          # 再ログイン
codex exec --skip-git-repo-check "echo ok"
```
`not supported when using Codex with a ChatGPT account` は CLI 旧版 →
`sudo npm install -g @openai/codex@latest`

### 受信しない（喋るが聞こえない）
- Developer Portal の MESSAGE CONTENT INTENT が ON か
- `.env` の `DISCORD_ALLOWED_CHANNELS` に対象 ch があるか
- `pip install discord.py` 済か / `DISCORD_BOT_TOKEN` 正しいか

### MCP が使えない
```bash
codex mcp list
```
`~/.codex/config.toml` の command/args パス、`required=false`、Lean+mathlib の RAM 不足
（12GB プラン以上）、`startup_timeout_sec` を確認。

### トークン
- codex 認証は CLI が自動 refresh（再ログイン基本不要）
- Google は `google_auth.py` が refresh。OAuth 同意画面を **In production** にしないと
  refresh token が 7 日で切れる（`docs/google_setup.md`）
