#!/bin/bash
# startup_check.sh - 再起動後の自己診断 + 落ちてた間の失敗ジョブ検出
# start-secretary.sh から呼ばれる

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
source "$SCRIPT_DIR/../.env"

DISCORD_CHANNEL="${DISCORD_CHANNEL_RANDOM}"
LOG=/tmp/startup_check.log
LAST_ALIVE=/tmp/secretary_last_alive.txt

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" >> "$LOG"
}

notify() {
    curl -s -X POST http://localhost:8781/remind \
        -H "Content-Type: application/json" \
        -d "{\"message\": \"$1\", \"channel\": \"$DISCORD_CHANNEL\"}" > /dev/null 2>&1
}

log "startup_check 開始"

# --- 1. 前回の生存記録を確認 ---
if [ -f "$LAST_ALIVE" ]; then
    last=$(cat "$LAST_ALIVE")
    now=$(date +%s)
    last_ts=$(date -d "$last" +%s 2>/dev/null || echo 0)
    down_seconds=$((now - last_ts))
    down_minutes=$((down_seconds / 60))

    if [ $down_minutes -gt 10 ]; then
        log "ダウン時間: ${down_minutes}分 (前回生存: $last)"

        # --- 2. その間に実行されたはずのcronジョブを特定 ---
        missed=""
        last_hour=$(date -d "$last" +%H 2>/dev/null || echo "??")
        now_hour=$(date +%H)

        # syslogから落ちてた期間のcron実行ログを取得
        missed_jobs=$(grep "CMD" /var/log/syslog 2>/dev/null | \
            awk -v from="$last" -v to="$(date '+%Y-%m-%dT%H:%M')" '
            $0 >= from && $0 <= to {print}
            ' | grep -v "gmail_monitor\|health_check" | tail -20)

        if [ -n "$missed_jobs" ]; then
            job_count=$(echo "$missed_jobs" | wc -l)
            msg="⚡ secretaryが再起動しました（ダウン: 約${down_minutes}分）\\nその間に ${job_count}件のcronが実行されましたが結果が未配信の可能性があります\\n確認が必要なら「落ちてた間のジョブ確認して」と言ってください"
        else
            msg="⚡ secretaryが再起動しました（ダウン: 約${down_minutes}分）"
        fi

        # webhookが起動してから通知（少し待つ）
        sleep 5
        notify "$msg"
        log "通知送信: $msg"
    fi
fi

# --- 3. 今回の起動時刻を記録 ---
date '+%Y-%m-%dT%H:%M:%S' > "$LAST_ALIVE"

# --- 4. 各コンポーネントの動作確認 ---
errors=""

# webhookサーバー確認
sleep 3
response=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 http://localhost:8781/health)
if [ "$response" != "200" ]; then
    errors="${errors}webhookサーバーが応答しない\n"
    log "ERROR: webhook応答なし (${response})"
fi

# 脳(worker)確認
if ! pgrep -f "codex_queue_worker.py" > /dev/null 2>&1; then
    errors="${errors}codex_queue_worker(脳)が起動していない\n"
    log "ERROR: codex_queue_worker未起動"
fi
# 受信(listener)確認
if ! pgrep -f "discord_listener.py" > /dev/null 2>&1; then
    errors="${errors}discord_listener(受信)が起動していない\n"
    log "ERROR: discord_listener未起動"
fi

if [ -n "$errors" ]; then
    notify "⚠️ 起動後チェックで問題が見つかりました:\\n${errors}"
    log "起動チェック失敗: $errors"
else
    log "起動チェック: 全て正常"
fi
