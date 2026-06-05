"""SQLite ベースの cron ジョブメトリクス（軽量な Prometheus 代替）。

各実行のステータスと所要時間を記録し、成功率・平均レイテンシ・p95 を集計する。

## 使い方

デコレータ（推奨）:

    from scripts.lib.metrics_db import track_metrics

    @track_metrics("task_remind")
    def main():
        ...

集計:

    from scripts.lib.metrics_db import job_stats
    stats = job_stats(hours=24)
"""

from __future__ import annotations

import contextlib
import functools
import os
import sqlite3
import sys
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

_DEFAULT_DB = os.path.expanduser("~/secretary/data/metrics.db")
DB_PATH = Path(os.environ.get("METRICS_DB_PATH", _DEFAULT_DB))

_SCHEMA = """
CREATE TABLE IF NOT EXISTS job_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    job_name TEXT NOT NULL,
    status TEXT NOT NULL,
    duration_ms INTEGER NOT NULL,
    error TEXT
);
CREATE INDEX IF NOT EXISTS idx_runs_ts ON job_runs(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_runs_job ON job_runs(job_name, timestamp DESC);
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


def record_run(
    job_name: str,
    status: str,
    duration_ms: int,
    error: str | None = None,
    *,
    db_path: Path = DB_PATH,
) -> int:
    with _connect(db_path) as conn:
        cur = conn.execute(
            "INSERT INTO job_runs (timestamp, job_name, status, duration_ms, error) "
            "VALUES (?, ?, ?, ?, ?)",
            (_now_jst_iso(), job_name, status, int(duration_ms), error),
        )
        return cur.lastrowid or 0


def recent_runs(
    hours: int = 24,
    *,
    job: str | None = None,
    limit: int = 200,
    db_path: Path = DB_PATH,
) -> list[dict[str, Any]]:
    from datetime import datetime, timedelta

    from_time = (datetime.fromisoformat(_now_jst_iso()) - timedelta(hours=hours)).isoformat()

    query = "SELECT * FROM job_runs WHERE timestamp >= ?"
    params: list[Any] = [from_time]
    if job:
        query += " AND job_name = ?"
        params.append(job)
    query += " ORDER BY timestamp DESC LIMIT ?"
    params.append(limit)

    with _connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(query, params).fetchall()
    return [dict(r) for r in rows]


def job_stats(hours: int = 24, *, db_path: Path = DB_PATH) -> dict[str, dict[str, Any]]:
    from datetime import datetime, timedelta

    from_time = (datetime.fromisoformat(_now_jst_iso()) - timedelta(hours=hours)).isoformat()

    with _connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT job_name, status, duration_ms, timestamp "
            "FROM job_runs WHERE timestamp >= ? "
            "ORDER BY job_name, timestamp DESC",
            (from_time,),
        ).fetchall()

    by_job: dict[str, list[dict[str, Any]]] = {}
    for r in rows:
        by_job.setdefault(r["job_name"], []).append(dict(r))

    result: dict[str, dict[str, Any]] = {}
    for job, runs in by_job.items():
        total = len(runs)
        ok = sum(1 for r in runs if r["status"] == "ok")
        durations = sorted(r["duration_ms"] for r in runs)
        avg = int(sum(durations) / total) if total else 0
        p95 = durations[int(total * 0.95)] if total > 0 else 0
        last = runs[0]
        result[job] = {
            "runs": total,
            "success": ok,
            "success_rate": round(ok / total, 3) if total else 0,
            "avg_ms": avg,
            "p95_ms": p95,
            "last_status": last["status"],
            "last_run": last["timestamp"],
        }
    return result


def cleanup_old(retention_days: int = 30, db_path: Path = DB_PATH) -> int:
    from datetime import datetime, timedelta

    cutoff = (
        datetime.fromisoformat(_now_jst_iso()) - timedelta(days=retention_days)
    ).isoformat()
    with _connect(db_path) as conn:
        cur = conn.execute("DELETE FROM job_runs WHERE timestamp < ?", (cutoff,))
        return cur.rowcount


def track_metrics(job_name: str, *, db_path: Path | None = None) -> Callable:
    def decorator(fn: Callable) -> Callable:
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            start = time.time()
            status = "ok"
            error: str | None = None
            try:
                return fn(*args, **kwargs)
            except SystemExit as e:
                status = "ok" if (e.code == 0 or e.code is None) else f"exit_{e.code}"
                raise
            except BaseException as e:
                status = "error"
                error = f"{type(e).__name__}: {e}"[:500]
                raise
            finally:
                duration_ms = int((time.time() - start) * 1000)
                try:
                    path = db_path if db_path is not None else DB_PATH
                    record_run(job_name, status, duration_ms, error, db_path=path)
                except Exception as rec_exc:
                    print(
                        f"[metrics_db] record_run failed: {rec_exc}",
                        file=sys.stderr,
                    )

        return wrapper

    return decorator


def format_stats_markdown(stats: dict[str, dict[str, Any]]) -> str:
    if not stats:
        return "_データなし_"
    lines = [
        "| job | runs | success | avg_ms | p95_ms | last |",
        "|-----|------|---------|--------|--------|------|",
    ]
    sorted_items = sorted(stats.items(), key=lambda x: (x[1]["success_rate"], -x[1]["runs"]))
    for job, s in sorted_items:
        ts = s["last_run"][11:16]
        lines.append(
            f"| {job} | {s['runs']} | {int(s['success_rate'] * 100)}% "
            f"| {s['avg_ms']} | {s['p95_ms']} | {ts} `{s['last_status']}` |"
        )
    return "\n".join(lines)


def _cli_main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_stats = sub.add_parser("stats")
    p_stats.add_argument("--hours", type=int, default=24)

    p_recent = sub.add_parser("recent")
    p_recent.add_argument("--hours", type=int, default=24)
    p_recent.add_argument("--job")
    p_recent.add_argument("--limit", type=int, default=30)

    p_clean = sub.add_parser("cleanup")
    p_clean.add_argument("--days", type=int, default=30)

    args = parser.parse_args()

    if args.cmd == "stats":
        print(format_stats_markdown(job_stats(hours=args.hours)))
        return 0

    if args.cmd == "recent":
        runs = recent_runs(hours=args.hours, job=args.job, limit=args.limit)
        for r in runs:
            print(
                f"[{r['timestamp']}] {r['job_name']}: {r['status']} "
                f"({r['duration_ms']}ms) {r.get('error') or ''}"
            )
        return 0

    if args.cmd == "cleanup":
        deleted = cleanup_old(retention_days=args.days)
        print(f"削除: {deleted}")
        return 0

    return 1


if __name__ == "__main__":
    sys.exit(_cli_main())
