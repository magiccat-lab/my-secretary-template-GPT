"""JST タイムゾーンのユーティリティ。

一貫性のため、cron / at / タイムスタンプのロジックはすべて日本時間（UTC+9）を使う。

使い方:

    from scripts.lib.jst import JST, now_jst, today_jst, parse_iso_jst

    now = now_jst()
    today = today_jst()
    dt = parse_iso_jst("2026-04-11T08:00:00+09:00")
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

#: 固定の JST タイムゾーン
JST = timezone(timedelta(hours=9))


def now_jst() -> datetime:
    """JST 付きの現在時刻を返す"""
    return datetime.now(JST)


def today_jst() -> date:
    """JST の今日の日付"""
    return now_jst().date()


def today_iso() -> str:
    """今日の日付を ISO 文字列で返す（YYYY-MM-DD, JST）"""
    return today_jst().isoformat()


def parse_iso_jst(s: str) -> datetime:
    """ISO8601 文字列を JST 付き datetime にパースする。

    タイムゾーンなしの文字列は JST とみなす。あるものは JST に変換する。
    末尾の 'Z'（UTC）も受け付ける。
    """
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError as e:
        raise ValueError(f"不正な ISO datetime: {s!r}") from e
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=JST)
    return dt.astimezone(JST)
