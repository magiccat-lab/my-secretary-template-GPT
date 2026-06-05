#!/bin/bash
# GPT版秘書 (codex harness) の起動スクリプト
# 使い方: bash ~/secretary-gpt/start_server.sh
#
# Claude Code 版との違い:
#   - 脳を screen TUI 常駐させない。codex_queue_worker.py が job ごとに
#     `codex exec` を叩く [codex 公式の自動化パス]。
#   - screen には webhook と worker をウィンドウで持たせ、運用コンソールとして使う。

export HOME="$(getent passwd "$(id -un)" | cut -d: -f6)"
export PATH="$HOME/.bun/bin:$HOME/.local/bin:$PATH"

SECRETARY_DIR="${SECRETARY_HOME:-$HOME/secretary}"
export SECRETARY_HOME="$SECRETARY_DIR"

# 既存セッション / プロセスを落とす
screen -S secretary-gpt -X quit 2>/dev/null
pkill -f webhook_server.py 2>/dev/null
pkill -f codex_queue_worker.py 2>/dev/null
pkill -f discord_listener.py 2>/dev/null
lsof -ti:8781 2>/dev/null | xargs kill -9 2>/dev/null
sleep 1

# codex の疎通確認 (auth 切れ / 未 install の早期検知)
if ! command -v codex >/dev/null 2>&1; then
  echo "❌ codex CLI が見つからない。npm i -g @openai/codex してから再実行"
  exit 1
fi

# screen セッションを作り、worker をウィンドウ0で常駐
screen -dmS secretary-gpt bash -c "cd $SECRETARY_DIR && SECRETARY_HOME=$SECRETARY_DIR python3 $SECRETARY_DIR/scripts/codex_queue_worker.py 2>&1 | tee -a /tmp/codex_worker.log"
sleep 1

SECRETARY_SESSION=$(screen -ls | grep secretary-gpt | head -1 | awk '{print $1}')
echo "$SECRETARY_SESSION" > /tmp/secretary_gpt_session.txt

# webhook サーバーを別ウィンドウで起動 (cron/HTTP イベント受信)
screen -S secretary-gpt -X screen -t webhook bash -c "cd $SECRETARY_DIR && SECRETARY_HOME=$SECRETARY_DIR python3 $SECRETARY_DIR/scripts/webhook_server.py 2>&1 | tee -a /tmp/codex_webhook.log"

# Discord listener を別ウィンドウで起動 (Discord メッセージ受信 → queue)
screen -S secretary-gpt -X screen -t discord bash -c "cd $SECRETARY_DIR && SECRETARY_HOME=$SECRETARY_DIR python3 $SECRETARY_DIR/scripts/discord_listener.py 2>&1 | tee -a /tmp/codex_discord.log"

echo "GPT版秘書を起動しました (session: $SECRETARY_SESSION)"
echo "  - window 0: codex_queue_worker (脳)"
echo "  - window 1: webhook_server (cron/HTTP 受信)"
echo "  - window 2: discord_listener (Discord 受信)"
screen -list | grep secretary-gpt
