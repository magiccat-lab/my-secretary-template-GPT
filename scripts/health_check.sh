#!/bin/bash
# health_check.sh - 秘書(GPT版)の死活監視 + 自動復旧
# cron: */5 * * * *
#
# session_watchdog.py が「脳の固着」を heartbeat で見るのに対し、こちらは
# 「プロセス/サーバが落ちた」を見て start_server.sh で立て直す相補役。
# 監視対象: webhook(8781) / screen(secretary-gpt) / codex_queue_worker / discord_listener

export HOME="$(getent passwd "$(id -un)" | cut -d: -f6)"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SECRETARY_DIR="${SECRETARY_HOME:-$(cd "$SCRIPT_DIR/.." && pwd)}"
export SECRETARY_HOME="$SECRETARY_DIR"
[ -f "$SECRETARY_DIR/.env" ] && set -a && . "$SECRETARY_DIR/.env" && set +a

LOG=/tmp/health_check.log
WEBHOOK_URL="http://localhost:${WEBHOOK_PORT:-8781}/health"
DISCORD_CHANNEL="${WATCHDOG_NOTIFY_CHANNEL:-${DISCORD_CHANNEL_RANDOM:-}}"
MAX_FAILURES=2
FAILURE_FILE=/tmp/health_check_failures.txt

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" >> "$LOG"; }

notify() {
    [ -z "$DISCORD_CHANNEL" ] && return
    python3 "$SECRETARY_DIR/scripts/discord_send.py" "$DISCORD_CHANNEL" "$1" >/dev/null 2>&1
}

failures=0
[ -f "$FAILURE_FILE" ] && failures=$(cat "$FAILURE_FILE")

# 1. webhook 応答
webhook_ok=false
[ "$(curl -s -o /dev/null -w '%{http_code}' --max-time 5 "$WEBHOOK_URL")" = "200" ] && webhook_ok=true
# 2. screen
screen_ok=false
screen -list 2>/dev/null | grep -q "secretary-gpt" && screen_ok=true
# 3. 脳(worker)
worker_ok=false
pgrep -f "codex_queue_worker.py" > /dev/null 2>&1 && worker_ok=true
# 4. 受信(listener)
listener_ok=false
pgrep -f "discord_listener.py" > /dev/null 2>&1 && listener_ok=true

log "webhook=$webhook_ok screen=$screen_ok worker=$worker_ok listener=$listener_ok failures=$failures"

# すべて正常 → リセット + heartbeat
if $webhook_ok && $screen_ok && $worker_ok && $listener_ok; then
    echo 0 > "$FAILURE_FILE"
    date '+%Y-%m-%dT%H:%M:%S' > /tmp/secretary_last_alive.txt
    exit 0
fi

failures=$((failures + 1))
echo "$failures" > "$FAILURE_FILE"
log "異常検知 (failures=$failures)"

if [ "$failures" -ge "$MAX_FAILURES" ]; then
    log "再起動開始"
    echo 0 > "$FAILURE_FILE"
    for attempt in 1 2 3; do
        screen -S secretary-gpt -X quit 2>/dev/null
        sleep 2
        bash "$SECRETARY_DIR/start_server.sh" >> "$LOG" 2>&1
        sleep 10
        if [ "$(curl -s -o /dev/null -w '%{http_code}' --max-time 5 "$WEBHOOK_URL")" = "200" ] \
           && pgrep -f "codex_queue_worker.py" > /dev/null 2>&1; then
            log "再起動成功 (attempt $attempt)"
            notify "⚡ secretary が落ちてたので自動再起動した。今は正常"
            break
        fi
        log "再起動試行 $attempt 失敗"
        [ "$attempt" -eq 3 ] && notify "🚨 secretary 再起動が3回失敗。手動確認して"
    done
fi
