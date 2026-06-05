#!/usr/bin/env python3
"""session_watchdog.py — GPT版秘書 (codex harness) の固着検知。

Claude Code 版との違い [codex レビュー反映]:
    Claude Code 版は screen の hardcopy を正規表現で見て TUI の詰まりを検知していた。
    codex 版は TUI を常駐させない (job ごとに codex exec) ので、TUI hardcopy ではなく
    **codex_queue_worker.py が書く heartbeat (data/codex_worker_state.json) の鮮度**を
    見る。これが堅い [TUI パターンのメンテ不要]。

検知ロジック:
    1. worker プロセスが生きているか (pgrep)。死んでいたら再起動を通知。
    2. queue に未処理が積まれているのに state.updated_at が一定時間古い → 固着。
    3. state.status == "running" のまま TURN_STALE_SEC 以上 → ターンがハング。

cron 例: */2 * * * * /usr/bin/python3 ~/secretary-gpt/scripts/session_watchdog.py
"""
from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime, timezone, timedelta
from pathlib import Path

import requests

JST = timezone(timedelta(hours=9))
SECRETARY_HOME = Path(os.environ.get("SECRETARY_HOME", str(Path(__file__).resolve().parents[1])))
STATE_FILE = Path(os.environ.get("CODEX_WORKER_STATE", str(SECRETARY_HOME / "data" / "codex_worker_state.json")))
QUEUE_FILE = Path(os.environ.get("CODEX_QUEUE_FILE", "/tmp/codex_queue.txt"))
PROCESSED_FILE = Path(os.environ.get("CODEX_QUEUE_PROCESSED", "/tmp/codex_queue_processed.txt"))

TURN_STALE_SEC = int(os.environ.get("WATCHDOG_TURN_STALE", "1800"))   # running のまま 30 分
IDLE_BACKLOG_SEC = int(os.environ.get("WATCHDOG_IDLE_BACKLOG", "180"))  # 未処理あるのに 3 分無更新
NOTIFY_CH = os.environ.get("WATCHDOG_NOTIFY_CHANNEL", "")
DRY_RUN = os.environ.get("WATCHDOG_DRY_RUN", "0") == "1"


def log(msg: str) -> None:
    print(f"[{datetime.now(JST):%Y-%m-%d %H:%M:%S}] {msg}")


def notify(text: str) -> None:
    log(f"NOTIFY: {text}")
    if DRY_RUN or not NOTIFY_CH:
        return
    try:
        import sys
        sys.path.insert(0, str(SECRETARY_HOME / "scripts"))
        from discord_send import send  # type: ignore
        send(NOTIFY_CH, f"🔧 secretary-gpt watchdog: {text}")
    except Exception as e:
        log(f"通知失敗: {e}")


def worker_alive() -> bool:
    r = subprocess.run(["pgrep", "-f", "codex_queue_worker.py"], capture_output=True)
    return r.returncode == 0


def restart_worker() -> None:
    log("worker 再起動を試行")
    start = SECRETARY_HOME / "start_server.sh"
    if start.exists() and not DRY_RUN:
        subprocess.run(["bash", str(start)], check=False)


def main() -> int:
    now = datetime.now(JST)

    if not worker_alive():
        notify("codex_queue_worker が落ちている。再起動する")
        restart_worker()
        return 0

    if not STATE_FILE.exists():
        log("state file 未生成 (起動直後?)、skip")
        return 0

    try:
        state = json.loads(STATE_FILE.read_text())
    except Exception as e:
        log(f"state 読込失敗: {e}")
        return 0

    updated = state.get("updated_at")
    if not updated:
        return 0
    try:
        ts = datetime.fromisoformat(updated)
    except ValueError:
        return 0
    age = (now - ts).total_seconds()
    status = state.get("status", "?")

    # ケース1: ターンが running のまま長時間ハング
    if status == "running" and age > TURN_STALE_SEC:
        notify(f"ターンが running のまま {int(age)}s ハング。worker 再起動")
        subprocess.run(["pkill", "-f", "codex_queue_worker.py"], check=False)
        restart_worker()
        return 0

    # ケース2: 未処理 backlog があるのに idle のまま更新が止まっている
    try:
        q = len(QUEUE_FILE.read_text().splitlines()) if QUEUE_FILE.exists() else 0
        p = len(PROCESSED_FILE.read_text().splitlines()) if PROCESSED_FILE.exists() else 0
    except OSError:
        q = p = 0
    if q > p and age > IDLE_BACKLOG_SEC:
        notify(f"未処理 {q - p} 件あるのに {int(age)}s 無更新。worker 再起動")
        subprocess.run(["pkill", "-f", "codex_queue_worker.py"], check=False)
        restart_worker()
        return 0

    log(f"healthy (status={status}, age={int(age)}s, backlog={max(0, q - p)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
