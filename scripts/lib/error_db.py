"""SQLite ベースの軽量エラートラッカー（Sentry の代替）。

cron / webhook スクリプトから例外を data/errors.db に記録し、後から検索できる。
外部サービスは不要。

## 使い方

手動:

    from scripts.lib.error_db import record_error
    try:
        do_something()
    except Exception as e:
        record_error("my_script", e, context={"query": q})
        raise

デコレータ（推奨）:

    from scripts.lib.error_db import track_errors

    @track_errors("my_script")
    def main():
        ...

デイリー通知用のサマリー:

    from scripts.lib.error_db import recent_errors, error_summary

    errs = recent_errors(hours=24)
    print(error_summary(errs))
"""

from __future__ import annotations

import contextlib
import functools
import json
import os
import sqlite3
import sys
import traceback as _tb
from collections import Counter
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any

_DEFAULT_DB = os.path.expanduser("~/secretary/data/errors.db")
DB_PATH = Path(os.environ.get("ERROR_DB_PATH", _DEFAULT_DB))

_SCHEMA = """
CREATE TABLE IF NOT EXISTS errors (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    module TEXT NOT NULL,
    error_type TEXT NOT NULL,
    message TEXT NOT NULL,
    traceback TEXT,
    context TEXT
);
CREATE INDEX IF NOT EXISTS idx_errors_ts ON errors(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_errors_module ON errors(module);
"""


def _now_jst_iso() -> str:
    try:
        from scripts.lib.jst import now_jst

        return now_jst().isoformat()
    except Exception:
        from datetime import datetime, timedelta, timezone

        return datetime.now(timezone(timedelta(hours=9))).isoformat()


@contextlib.contextmanager
def _connect(db_path: Path = DB_PATH):
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    try:
        conn.executescript(_SCHEMA)
        yield conn
        conn.commit()
    finally:
        conn.close()


def record_error(
    module: str,
    exc: BaseException | None = None,
    *,
    message: str | None = None,
    context: dict | None = None,
    traceback_text: str | None = None,
    db_path: Path = DB_PATH,
) -> int:
    error_type = type(exc).__name__ if exc is not None else "ManualEntry"
    msg = message or (str(exc) if exc is not None else "")
    tb = traceback_text
    if tb is None and exc is not None:
        tb = _tb.format_exc()
        if tb.strip() in ("None", "NoneType: None"):
            tb = None

    ctx_json = json.dumps(context, ensure_ascii=False) if context else None

    with _connect(db_path) as conn:
        cur = conn.execute(
            """
            INSERT INTO errors (timestamp, module, error_type, message, traceback, context)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (_now_jst_iso(), module, error_type, msg, tb, ctx_json),
        )
        return cur.lastrowid or 0


def recent_errors(
    hours: int = 24,
    *,
    module: str | None = None,
    limit: int = 50,
    db_path: Path = DB_PATH,
) -> list[dict[str, Any]]:
    from datetime import datetime, timedelta

    from_time = (datetime.fromisoformat(_now_jst_iso()) - timedelta(hours=hours)).isoformat()

    query = "SELECT * FROM errors WHERE timestamp >= ?"
    params: list[Any] = [from_time]
    if module:
        query += " AND module = ?"
        params.append(module)
    query += " ORDER BY timestamp DESC LIMIT ?"
    params.append(limit)

    with _connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(query, params).fetchall()
    return [dict(r) for r in rows]


def error_summary(errs: Iterable[dict[str, Any]]) -> str:
    errs = list(errs)
    if not errs:
        return "エラーなし"
    total = len(errs)
    by_module: Counter[str] = Counter(e["module"] for e in errs)
    top = by_module.most_common(5)
    parts = [f"{m}: {c}" for m, c in top]
    return f"エラー {total} 件 ({', '.join(parts)})"


def cleanup_old(retention_days: int = 30, db_path: Path = DB_PATH) -> int:
    from datetime import datetime, timedelta

    cutoff = (
        datetime.fromisoformat(_now_jst_iso()) - timedelta(days=retention_days)
    ).isoformat()
    with _connect(db_path) as conn:
        cur = conn.execute("DELETE FROM errors WHERE timestamp < ?", (cutoff,))
        return cur.rowcount


def track_errors(module: str, *, reraise: bool = True, db_path: Path | None = None) -> Callable:
    def decorator(fn: Callable) -> Callable:
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            try:
                return fn(*args, **kwargs)
            except SystemExit:
                raise
            except Exception as e:
                try:
                    path = db_path if db_path is not None else DB_PATH
                    record_error(module, e, context={"args": repr(args)[:200]}, db_path=path)
                except Exception as rec_exc:
                    print(
                        f"[error_db] record_error failed: {rec_exc}",
                        file=sys.stderr,
                    )
                if reraise:
                    raise
                return None

        return wrapper

    return decorator


def _cli_main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_recent = sub.add_parser("recent")
    p_recent.add_argument("--hours", type=int, default=24)
    p_recent.add_argument("--module")
    p_recent.add_argument("--limit", type=int, default=20)

    p_summary = sub.add_parser("summary")
    p_summary.add_argument("--hours", type=int, default=24)

    p_clean = sub.add_parser("cleanup")
    p_clean.add_argument("--days", type=int, default=30)

    args = parser.parse_args()

    if args.cmd == "recent":
        errs = recent_errors(hours=args.hours, module=args.module, limit=args.limit)
        for e in errs:
            print(f"[{e['timestamp']}] {e['module']}: {e['error_type']}: {e['message']}")
        return 0

    if args.cmd == "summary":
        errs = recent_errors(hours=args.hours, limit=1000)
        print(error_summary(errs))
        return 0

    if args.cmd == "cleanup":
        deleted = cleanup_old(retention_days=args.days)
        print(f"削除: {deleted} 行")
        return 0

    return 1


if __name__ == "__main__":
    sys.exit(_cli_main())
