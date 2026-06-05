#!/bin/bash
# nightly_restart.sh — handoff を残してから秘書(codex)をコールドリスタートする。
#
# Claude 版の daily_handoff + restart 相当を GPT 版に移植したもの。
#   1. 現セッションに「次の自分への引き継ぎを書け」と投げ、出力を data/handoff.md に保存
#   2. codex セッションをリセット (文脈肥大を断つ)
#   3. start_server.sh で screen を立て直す
# 起動後、AGENTS.md のセッション開始手順で data/handoff.md を読むので、文脈が継続する。
#
# cron 例: 0 4 * * * SECRETARY_HOME=$HOME/secretary /bin/bash $HOME/secretary/scripts/nightly_restart.sh >> /tmp/nightly_restart.log 2>&1

set -u
export HOME="$(getent passwd "$(id -un)" | cut -d: -f6)"
export PATH="$HOME/.local/bin:$HOME/.npm-global/bin:$PATH"

SECRETARY_DIR="${SECRETARY_HOME:-$HOME/secretary}"
export SECRETARY_HOME="$SECRETARY_DIR"
SESSION_FILE="${CODEX_SESSION_FILE:-/tmp/codex_secretary_session.txt}"
HANDOFF="$SECRETARY_DIR/data/handoff.md"
STAMP="$(date '+%Y-%m-%d %H:%M JST')"

echo "[$STAMP] nightly_restart 開始"

# --- 1. handoff 生成 (現セッションがあれば文脈を要約させる) ---
HANDOFF_PROMPT="あなたの今のセッションは間もなくリセットされる。次に起動する『あなた自身』が文脈を引き継げるよう、引き継ぎメモを書け。出力はメモ本文のみ(前置き・コードフェンス不要)。含める: 進行中タスク / 直近の重要な会話の要点 / 約束した未完了事項 / ユーザーが今気にしていること。簡潔に、箇条書き中心で。"

if [ -f "$SESSION_FILE" ] && [ -s "$SESSION_FILE" ]; then
  SID="$(cat "$SESSION_FILE")"
  echo "[$STAMP] handoff 生成中 (session=$SID)"
  # resume で現文脈を引き継いで要約。失敗しても再起動は続行する。
  SUMMARY="$(cd "$SECRETARY_DIR" && timeout 240 codex exec resume --json --skip-git-repo-check \
      -c approval_policy='"never"' -c sandbox_mode='"read-only"' \
      "$SID" "$HANDOFF_PROMPT" 2>/dev/null \
      | python3 -c "import sys,json
out=[]
for l in sys.stdin:
    l=l.strip()
    if not l: continue
    try: d=json.loads(l)
    except: continue
    if d.get('type')=='item.completed' and (d.get('item') or {}).get('type')=='agent_message':
        out.append((d['item'].get('text') or '').strip())
print(out[-1] if out else '')" 2>/dev/null)"
  if [ -n "$SUMMARY" ]; then
    mkdir -p "$SECRETARY_DIR/data"
    {
      echo "# handoff ($STAMP 自動生成)"
      echo
      echo "$SUMMARY"
    } > "$HANDOFF"
    echo "[$STAMP] handoff 保存: $HANDOFF (${#SUMMARY} 文字)"
  else
    echo "[$STAMP] handoff 生成が空。既存 handoff.md を保持して続行"
  fi
else
  echo "[$STAMP] セッション無し。handoff 生成スキップ"
fi

# --- 2. セッションリセット ---
rm -f "$SESSION_FILE"
echo "[$STAMP] セッションリセット"

# --- 3. 立て直し ---
bash "$SECRETARY_DIR/start_server.sh"
echo "[$STAMP] nightly_restart 完了"
