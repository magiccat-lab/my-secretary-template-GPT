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
    """codex exec コマンドを組む。既存 session があれば resume で継続。"""
    cmd = [CODEX_BIN, "exec", "--json"]
    cmd += EXTRA_FLAGS
    if session_id:
        # resume: 直前ターンの会話文脈を引き継ぐ
        return [CODEX_BIN, "exec", "resume", session_id, "--json", *EXTRA_FLAGS, prompt]
    cmd.append(prompt)
    return cmd


def run_turn(prompt: str) -> None:
    session_id = load_session_id()
    cmd = build_command(prompt, session_id)
    log(f"codex exec 開始 (resume={'yes' if session_id else 'no'}, {len(prompt)}文字)")
    write_state(status="running", last_prompt_len=len(prompt), last_session_id=session_id)

    try:
        proc = subprocess.Popen(
            cmd,
            cwd=str(SECRETARY_HOME),
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
        # JSONL event をなめて session_id / 完了 / 失敗を拾う
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        sid = ev.get("session_id") or (ev.get("session") or {}).get("id")
        if sid:
            new_session = sid
        etype = ev.get("type") or ev.get("event") or ""
        if "fail" in etype or "error" in etype:
            last_err = ev.get("message") or etype
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
    log(f"codex_queue_worker 起動: {QUEUE_FILE} を監視 (SECRETARY_HOME={SECRETARY_HOME})")
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
