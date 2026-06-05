#!/usr/bin/env python3
"""gcal_cli.py — Google Calendar 操作の薄い CLI (GPT版秘書用)。

codex (脳) が bash でこれを叩いて予定を読み書きする。操作を限定し、
作成は確認ゲート付き (codex レビュー: 操作を narrow にして権限を明確に)。

使い方:
    python3 gcal_cli.py list [--days 7] [--max 20]
    python3 gcal_cli.py create --summary "打合せ" --start 2026-06-10T15:00 \
        --end 2026-06-10T16:00 [--desc "..."] --yes

注意:
    --yes が無いと create は dry-run (内容を表示するだけ)。
    タイムゾーンは既定 Asia/Tokyo。
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, __file__.rsplit("/", 1)[0])
from google_auth import service  # noqa: E402

JST = timezone(timedelta(hours=9))
TZ_NAME = "Asia/Tokyo"


def cmd_list(args) -> int:
    svc = service("calendar", "v3")
    now = datetime.now(JST)
    end = now + timedelta(days=args.days)
    res = (
        svc.events()
        .list(
            calendarId=args.calendar,
            timeMin=now.isoformat(),
            timeMax=end.isoformat(),
            singleEvents=True,
            orderBy="startTime",
            maxResults=args.max,
        )
        .execute()
    )
    items = res.get("items", [])
    if not items:
        print(f"今後 {args.days} 日に予定なし")
        return 0
    for ev in items:
        start = ev["start"].get("dateTime", ev["start"].get("date"))
        print(f"- {start}  {ev.get('summary', '(無題)')}  [{ev.get('id')}]")
    return 0


def cmd_create(args) -> int:
    body = {
        "summary": args.summary,
        "start": {"dateTime": args.start, "timeZone": TZ_NAME},
        "end": {"dateTime": args.end, "timeZone": TZ_NAME},
    }
    if args.desc:
        body["description"] = args.desc
    if not args.yes:
        print("[dry-run] 以下を作成予定 (--yes で実行):")
        print(f"  {args.summary}  {args.start} → {args.end}  cal={args.calendar}")
        return 0
    svc = service("calendar", "v3")
    ev = svc.events().insert(calendarId=args.calendar, body=body).execute()
    print(f"作成: {ev.get('htmlLink')}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Google Calendar CLI")
    ap.add_argument("--calendar", default="primary")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_list = sub.add_parser("list", help="今後の予定を一覧")
    p_list.add_argument("--days", type=int, default=7)
    p_list.add_argument("--max", type=int, default=20)
    p_list.set_defaults(func=cmd_list)

    p_create = sub.add_parser("create", help="予定を作成 (--yes で実行)")
    p_create.add_argument("--summary", required=True)
    p_create.add_argument("--start", required=True, help="ISO8601 例 2026-06-10T15:00")
    p_create.add_argument("--end", required=True)
    p_create.add_argument("--desc", default="")
    p_create.add_argument("--yes", action="store_true", help="実行 (無ければ dry-run)")
    p_create.set_defaults(func=cmd_create)

    args = ap.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
