"""アトミックな JSON ステートファイルハンドラー。

cron スクリプトで散らばりがちな load_state / save_state を置き換える。

使い方:

    from scripts.lib.state_store import load_state, save_state, update_state

    state = load_state("/tmp/foo.json", default={"seen_ids": []})
    state["seen_ids"].append("new_id")
    save_state("/tmp/foo.json", state)

    # 安全な read-modify-write:
    with update_state("/tmp/foo.json", default={"count": 0}) as state:
        state["count"] += 1
"""

from __future__ import annotations

import contextlib
import fcntl
import json
import os
from collections.abc import Iterator
from pathlib import Path
from typing import Any


def load_state(path: str | Path, default: Any | None = None) -> Any:
    """JSON ステートを読み込む。ファイルが無い / 壊れている場合は default"""
    p = Path(path)
    if not p.exists():
        return default
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return default


def save_state(path: str | Path, data: Any, *, use_lock: bool = True) -> None:
    """アトミックに JSON ステートを書く（tmp + rename、任意で flock）"""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")

    lock_path = p.with_suffix(p.suffix + ".lock")
    if use_lock:
        lock_fd = os.open(str(lock_path), os.O_CREAT | os.O_WRONLY)
        fcntl.flock(lock_fd, fcntl.LOCK_EX)
    try:
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(p)
    finally:
        if use_lock:
            fcntl.flock(lock_fd, fcntl.LOCK_UN)
            os.close(lock_fd)
            try:
                lock_path.unlink()
            except FileNotFoundError:
                pass


@contextlib.contextmanager
def update_state(path: str | Path, default: Any | None = None) -> Iterator[Any]:
    """read-modify-write のコンテキストマネージャ"""
    state = load_state(path, default=default)
    try:
        yield state
    except Exception:
        raise
    else:
        save_state(path, state)
