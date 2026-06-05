#!/usr/bin/env python3
"""codex_queue_worker.py — GPT版秘書の「脳」を駆動するキューワーカー。

設計 [codex レビュー反映 2026-06-05]:
    Claude Code 版は TUI を screen 常駐させ `screen -X stuff` でプロンプト注入していたが、
    codex CLI では TUI 常駐 + stuff は脆い [承認モーダル / paste 検出 / TUI 更新で壊れる、
    長時間で context 劣化]。代わりに **job ごとに `codex exec --json` を叩く** のが
    codex 公式の自動化パス。セッション継続は `codex exec resume <session_id>` で行う。

フロー:
    webhook_server.py → /tmp/codex_queue.txt に base64 1行追記
        → 本ワーカーが tail → 未処理行を decode → codex exec で 1 ターン実行
        → codex 内のエージェントが discord_send.py を bash で叩いて返信する
    返信送信はエージェント [codex] 側の責務。ワーカーは投入と監視に徹する。

監視:
    1 ターンごとに STATE_FILE に last_activity / last_session_id / status を書く。
    session_watchdog 系はこのファイルの鮮度を見れば固着検知できる [TUI hardcopy 不要]。
"""
from __future__ import annotations

import base64
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

JST = timezone(timedelta(hours=9))

SECRETARY_HOME = Path(os.environ.get("SECRETARY_HOME", str(Path(__file__).resolve().parents[1])))
QUEUE_FILE = Path(os.environ.get("CODEX_QUEUE_FILE", "/tmp/codex_queue.txt"))
PROCESSED_FILE = Path(os.environ.get("CODEX_QUEUE_PROCESSED", "/tmp/codex_queue_processed.txt"))
STATE_FILE = Path(os.environ.get("CODEX_WORKER_STATE", str(SECRETARY_HOME / "data" / "codex_worker_state.json")))
SESSION_FILE = Path(os.environ.get("CODEX_SESSION_FILE", "/tmp/codex_secretary_session.txt"))

CODEX_BIN = os.environ.get("CODEX_BIN", "codex")
# 無人運用: 承認なし + workspace 書込可。--dangerously-skip-permissions 相当。
# config.toml 側で approval_policy/sandbox_mode を設定済なら CLI フラグは省略可。
EXTRA_FLAGS = os.environ.get("CODEX_EXEC_FLAGS", "").split()
POLL_SECONDS = float(os.environ.get("CODEX_QUEUE_POLL", "2"))
TURN_TIMEOUT = int(os.environ.get("CODEX_TURN_TIMEOUT", "1800"))  # 30 分/ターン上限

# 脳の切替レバー [非常用]。通常は codex (GPT)。codex が使えない緊急時のみ claude に。
#   BRAIN=codex (既定) | claude
# claude パスは degraded: identity hook / 口調強制は無く、AGENTS.md を素の指示として渡すだけ。
# 二脳を常時保守しないための「作らずに済むフォールバック」の最小実装。
BRAIN = os.environ.get("BRAIN", "codex").lower()
CLAUDE_BIN = os.environ.get("CLAUDE_BIN", "claude")
CLAUDE_FLAGS = os.environ.get("CLAUDE_FLAGS", "--dangerously-skip-permissions").split()


def log(msg: str) -> None:
    print(f"[{datetime.now(JST):%Y-%m-%d %H:%M:%S}] {msg}", flush=True)


def write_state(**kw) -> None:
    state = {"updated_at": datetime.now(JST).isoformat()}
    state.update(kw)
    try:
        STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2))
    except OSError as e:
        log(f"state 書込失敗: {e}")


def load_session_id() -> str | None:
    if SESSION_FILE.exists():
        sid = SESSION_FILE.read_text(encoding="utf-8").strip()
        return sid or None
    return None


def save_session_id(sid: str) -> None:
    try:
        SESSION_FILE.write_text(sid)
    except OSError as e:
        log(f"session id 保存失敗: {e}")


def build_command(prompt: str, session_id: str | None) -> list[str]:
    """脳のコマンドを組む。BRAIN で codex / claude を切替。既存 session は継続。

    codex 実機検証 (0.137.0, 2026-06-05) で確定した仕様:
      - session 識別子は thread.started イベントの `thread_id` (UUID)。
      - `exec resume` サブコマンドは `-s/--sandbox` を受け付けない (exec 専用)。
        sandbox/approval は config.toml か `-c key=value` 上書きで渡す。
      - フラグは positional (SESSION_ID/PROMPT) より前に置く。
    """
    if BRAIN == "claude":
        # 非常用フォールバック。claude -p の stream-json (JSONL) で session_id を拾い継続。
        # stream-json は session_id を含む JSONL を吐くので既存の行パーサで処理できる。
        cmd = [CLAUDE_BIN, "-p", "--output-format", "stream-json", "--verbose", *CLAUDE_FLAGS]
        if session_id:
            cmd += ["--resume", session_id]
        cmd.append(prompt)
        return cmd
    # 通常: codex
    if session_id:
        return [CODEX_BIN, "exec", "resume", "--json", "--skip-git-repo-check",
                *EXTRA_FLAGS, session_id, prompt]
    return [CODEX_BIN, "exec", "--json", "--skip-git-repo-check", *EXTRA_FLAGS, prompt]


def run_turn(prompt: str) -> None:
    session_id = load_session_id()
    cmd = build_command(prompt, session_id)
    log(f"codex exec 開始 (resume={'yes' if session_id else 'no'}, {len(prompt)}文字)")
    write_state(status="running", last_prompt_len=len(prompt), last_session_id=session_id)

    try:
        proc = subprocess.Popen(
            cmd,
            cwd=str(SECRETARY_HOME),
            stdin=subprocess.DEVNULL,  # stdin を閉じる (prompt は引数渡し。開いたままだと待機する)
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
    except FileNotFoundError:
        log(f"codex バイナリが見つからない: {CODEX_BIN}。CODEX_BIN を確認")
        write_state(status="error", error="codex binary not found")
        return

    new_session: str | None = None
    last_err: str | None = None
    start = time.monotonic()
    assert proc.stdout is not None
    for line in proc.stdout:
        line = line.strip()
        if not line:
            continue
        # JSONL event をなめて thread_id / 完了 / 失敗を拾う。
        # codex 0.137.0 の event 形式 (実機確認):
        #   {"type":"thread.started","thread_id":"<uuid>"}
        #   {"type":"item.completed","item":{"type":"agent_message","text":"..."}}
        #   {"type":"turn.completed","usage":{...}}  / 失敗時は turn.failed
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        sid = ev.get("thread_id") or ev.get("session_id") or (ev.get("session") or {}).get("id")
        if sid:
            new_session = sid
        # エージェントの発話を運用ログに残す (返信自体は codex が discord_send.py で送る)
        if ev.get("type") == "item.completed":
            item = ev.get("item") or {}
            if item.get("type") == "agent_message" and item.get("text"):
                log(f"  agent: {item['text'][:200]}")
        etype = ev.get("type") or ev.get("event") or ""
        if "fail" in etype or etype == "error":
            last_err = ev.get("message") or ev.get("error") or etype
        write_state(status="running", last_event=etype,
                    last_session_id=new_session or session_id)
        if time.monotonic() - start > TURN_TIMEOUT:
            log("ターンが TURN_TIMEOUT 超過、kill")
            proc.kill()
            last_err = "turn timeout"
            break

    rc = proc.wait()
    if new_session:
        save_session_id(new_session)
    if rc == 0 and not last_err:
        log("codex exec 正常終了")
        write_state(status="idle", last_session_id=new_session or session_id)
    else:
        log(f"codex exec 異常終了 rc={rc} err={last_err}")
        write_state(status="error", error=last_err or f"rc={rc}",
                    last_session_id=new_session or session_id)


def main() -> int:
    QUEUE_FILE.touch(exist_ok=True)
    PROCESSED_FILE.touch(exist_ok=True)
    log(f"codex_queue_worker 起動: BRAIN={BRAIN} / {QUEUE_FILE} を監視 (SECRETARY_HOME={SECRETARY_HOME})")
    write_state(status="idle")

    while True:
        try:
            queue_lines = QUEUE_FILE.read_text(encoding="utf-8").splitlines()
            processed = PROCESSED_FILE.read_text(encoding="utf-8").splitlines()
            n_proc = len(processed)
            new = queue_lines[n_proc:]
            for encoded in new:
                encoded = encoded.strip()
                if encoded:
                    try:
                        prompt = base64.b64decode(encoded).decode("utf-8")
                    except Exception as e:
                        log(f"decode 失敗、skip: {e}")
                        prompt = None
                    if prompt:
                        run_turn(prompt)
            if new:
                # 処理済みカーソルを進める [queue 全体をコピー]
                PROCESSED_FILE.write_text("\n".join(queue_lines) + "\n")
        except Exception as e:
            log(f"ループ例外: {e}")
            write_state(status="loop_error", error=str(e))
        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    sys.exit(main())
