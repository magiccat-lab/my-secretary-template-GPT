"""ロック付き pending_tasks.json + オプションの SQLite バックエンド。

## デフォルトバックエンド: JSON

パス: ~/secretary/data/pending_tasks.json（PENDING_TASKS_PATH で上書き可）
スキーマ: {"primary": [ {"title": "...", "done": false, "created_at": "..."}, ... ]}

## オプション: SQLite バックエンド

TASK_STORE_BACKEND=sqlite をセットすると data/pending_tasks.db を使う。
Google Sheets 同期や高並列のワークフロー向け。

## 使い方

```python
from scripts.lib.task_store import load_tasks, update_tasks, get_active, add_task, mark_done

data = load_tasks()
with update_tasks() as data:
    data.setdefault("primary", []).append(
        {"title": "groceries", "done": False, "created_at": "2026-04-14"}
    )
add_task("primary", "call dentist")
mark_done("primary", "call dentist")
active = get_active("primary")
```
"""

from __future__ import annotations

import contextlib
import datetime as dt
import fcntl
import json
import os
import sqlite3
from collections.abc import Iterator
from pathlib import Path

JSON_PATH = Path(
    os.environ.get(
        "PENDING_TASKS_PATH",
        os.path.expanduser("~/secretary/data/pending_tasks.json"),
    )
)
SQLITE_PATH = Path(
    os.environ.get(
        "PENDING_TASKS_DB",
        os.path.expanduser("~/secretary/data/pending_tasks.db"),
    )
)

PATH = JSON_PATH  # 後方互換のエイリアス

DEFAULT_SECTION = "primary"


def _backend() -> str:
    b = os.environ.get("TASK_STORE_BACKEND", "json").lower()
    return "sqlite" if b == "sqlite" else "json"


# ---------- JSON バックエンド ----------


def _ensure_json_exists() -> None:
    if not JSON_PATH.exists():
        JSON_PATH.parent.mkdir(parents=True, exist_ok=True)
        JSON_PATH.write_text(json.dumps({DEFAULT_SECTION: []}, ensure_ascii=False, indent=2))


@contextlib.contextmanager
def _locked_json(mode: str) -> Iterator:
    _ensure_json_exists()
    f = open(JSON_PATH, mode, encoding="utf-8")
    try:
        fcntl.flock(f.fileno(), fcntl.LOCK_EX)
        yield f
    finally:
        try:
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)
        finally:
            f.close()


def _json_load_tasks() -> dict:
    with _locked_json("r") as f:
        try:
            data = json.load(f)
        except json.JSONDecodeError:
            return {DEFAULT_SECTION: []}

    # 旧形式 {"tasks": [...]} はデフォルトセクションに移行
    if "tasks" in data and DEFAULT_SECTION not in data:
        data = {DEFAULT_SECTION: data["tasks"]}

    data.setdefault(DEFAULT_SECTION, [])
    return data


def _json_save_tasks(data: dict) -> None:
    tmp = JSON_PATH.with_suffix(".tmp")
    with _locked_json("r+") as _:
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2))
        tmp.replace(JSON_PATH)


# ---------- SQLite バックエンド ----------

_SQLITE_SCHEMA = """
CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    section TEXT NOT NULL,
    title TEXT NOT NULL,
    done INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    completed_at TEXT,
    remind_at TEXT,
    task_type TEXT,
    task_date TEXT,
    order_idx INTEGER NOT NULL,
    meta_json TEXT
);
CREATE INDEX IF NOT EXISTS idx_tasks_section ON tasks(section, done, order_idx);
"""


@contextlib.contextmanager
def _sqlite_conn(path: Path = SQLITE_PATH) -> Iterator[sqlite3.Connection]:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    try:
        conn.executescript(_SQLITE_SCHEMA)
        yield conn
        conn.commit()
    finally:
        conn.close()


def _row_to_task(row: sqlite3.Row) -> dict:
    t: dict = {"title": row["title"], "done": bool(row["done"])}
    if row["created_at"]:
        t["created_at"] = row["created_at"]
    if row["completed_at"]:
        t["completed_at"] = row["completed_at"]
    if row["remind_at"]:
        t["remind_at"] = row["remind_at"]
    if row["task_type"]:
        t["type"] = row["task_type"]
    if row["task_date"]:
        t["date"] = row["task_date"]
    if row["meta_json"]:
        try:
            extra = json.loads(row["meta_json"])
            if isinstance(extra, dict):
                t.update(extra)
        except json.JSONDecodeError:
            pass
    return t


def _task_to_params(section: str, t: dict, order_idx: int) -> tuple:
    known = {"title", "done", "created_at", "completed_at", "remind_at", "type", "date"}
    meta = {k: v for k, v in t.items() if k not in known}
    return (
        section,
        t.get("title", ""),
        1 if t.get("done") else 0,
        t.get("created_at", ""),
        t.get("completed_at"),
        t.get("remind_at"),
        t.get("type"),
        t.get("date"),
        order_idx,
        json.dumps(meta, ensure_ascii=False) if meta else None,
    )


def _sqlite_load_tasks() -> dict:
    data: dict = {DEFAULT_SECTION: []}
    with _sqlite_conn() as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM tasks ORDER BY section, order_idx").fetchall()
    for r in rows:
        data.setdefault(r["section"], []).append(_row_to_task(r))
    data.setdefault(DEFAULT_SECTION, [])
    return data


def _sqlite_save_tasks(data: dict) -> None:
    with _sqlite_conn() as conn:
        conn.execute("DELETE FROM tasks")
        for section, tasks in data.items():
            if not isinstance(tasks, list):
                continue
            for i, t in enumerate(tasks):
                if not isinstance(t, dict):
                    continue
                conn.execute(
                    "INSERT INTO tasks (section, title, done, created_at, completed_at, "
                    "remind_at, task_type, task_date, order_idx, meta_json) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    _task_to_params(section, t, i),
                )


# ---------- 公開 API ----------


def load_tasks() -> dict:
    if _backend() == "sqlite":
        return _sqlite_load_tasks()
    return _json_load_tasks()


def save_tasks(data: dict) -> None:
    if _backend() == "sqlite":
        _sqlite_save_tasks(data)
    else:
        _json_save_tasks(data)


@contextlib.contextmanager
def update_tasks() -> Iterator[dict]:
    data = load_tasks()
    try:
        yield data
    except Exception:
        raise
    else:
        save_tasks(data)


def get_active(section: str = DEFAULT_SECTION) -> list[dict]:
    data = load_tasks()
    tasks = data.get(section, [])
    today = dt.date.today().isoformat()

    def is_visible(t: dict) -> bool:
        if t.get("done"):
            return False
        remind_at = t.get("remind_at")
        if remind_at and remind_at > today:
            return False
        return True

    return [t for t in tasks if is_visible(t)]


def add_task(
    section: str = DEFAULT_SECTION,
    title: str = "",
    task_type: str | None = None,
    remind_at: str | None = None,
    skip_dupes: bool = True,
) -> bool:
    today = dt.date.today().isoformat()
    with update_tasks() as data:
        data.setdefault(section, [])
        if skip_dupes:
            for t in data[section]:
                if (
                    t.get("title") == title
                    and t.get("done") is False
                    and t.get("created_at") == today
                ):
                    return False
        entry: dict = {"title": title, "done": False, "created_at": today}
        if task_type:
            entry["type"] = task_type
        if remind_at:
            entry["remind_at"] = remind_at
        data[section].append(entry)
        return True


def mark_done(section: str, title_or_predicate) -> bool:
    today = dt.date.today().isoformat()
    with update_tasks() as data:
        for t in data.get(section, []):
            if t.get("done"):
                continue
            if callable(title_or_predicate):
                match = title_or_predicate(t)
            else:
                match = t.get("title") == title_or_predicate
            if match:
                t["done"] = True
                t["completed_at"] = today
                return True
    return False


def _cli_main() -> int:
    import argparse
    import sys

    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd")
    sub.add_parser("show")

    args = parser.parse_args()
    data = load_tasks()
    print(f"backend: {_backend()}")
    print(f"json path: {JSON_PATH}")
    if _backend() == "sqlite":
        print(f"sqlite path: {SQLITE_PATH}")
    for sec, tasks in data.items():
        active = len([t for t in tasks if not t.get("done")])
        print(f"{sec}: {len(tasks)} 件 (未完了 {active})")

    if args.cmd == "show":
        print()
        print(json.dumps(data, ensure_ascii=False, indent=2))

    return 0


if __name__ == "__main__":
    raise SystemExit(_cli_main())
