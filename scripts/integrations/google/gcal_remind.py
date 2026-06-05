#!/usr/bin/env python3
"""Google Calendar の30分前リマインダー。

毎分 cron で起動する。約30分後に始まる予定を見つけて、webhook サーバー経由で
random チャンネルにリマインドを投稿する。

環境変数:
    GOOGLE_TOKEN_PATH   token.json のパス（デフォルト: integrations/google/token.json）
    GCAL_CALENDAR_ID    対象カレンダー ID（デフォルト: "primary"）
    WEBHOOK_URL         webhook エンドポイント（デフォルト: http://localhost:8781/remind）

cron の例:
    * * * * * /usr/bin/python3 ~/secretary/integrations/gcal/gcal_remind.py \\
        >> /tmp/gcal_remind.log 2>&1
"""

from __future__ import annotations

import datetime
import os
import sys

import requests
from dotenv import load_dotenv

# このファイルは scripts/integrations/google/ 配下なので repo root は 4 階層上
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(__file__)))))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

# 認証は google_auth.py に集約 (token は ~/.codex/secrets)
sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))
import google_auth  # noqa: E402

from scripts.lib.state_store import load_state, save_state  # noqa: E402

load_dotenv(os.path.join(_REPO_ROOT, ".env"))

CALENDAR_ID = os.getenv("GCAL_CALENDAR_ID", "primary")
STATE_FILE = "/tmp/gcal_remind_state.json"
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "http://localhost:8781/remind")
DISCORD_CHANNEL = os.getenv("DISCORD_CHANNEL_RANDOM", "")
REMIND_MINUTES = 30


def main() -> None:
    service = google_auth.service("calendar", "v3")

    jst = datetime.timezone(datetime.timedelta(hours=9))
    now = datetime.datetime.now(jst)
    target_start = now + datetime.timedelta(minutes=REMIND_MINUTES - 2)
    target_end = now + datetime.timedelta(minutes=REMIND_MINUTES + 3)

    events_result = (
        service.events()
        .list(
            calendarId=CALENDAR_ID,
            timeMin=target_start.isoformat(),
            timeMax=target_end.isoformat(),
            singleEvents=True,
            orderBy="startTime",
        )
        .execute()
    )

    events = events_result.get("items", [])
    state = load_state(STATE_FILE, default={})

    for event in events:
        event_id = event["id"]
        if event_id in state:
            continue

        start_str = event["start"].get("dateTime", event["start"].get("date"))
        if "T" not in start_str:
            continue  # 終日予定はスキップ

        dt = datetime.datetime.fromisoformat(start_str)
        time_str = dt.astimezone(jst).strftime("%H:%M")
        summary = event.get("summary", "(タイトルなし)")

        msg = f"30分後に予定があります\n**{time_str} {summary}**"

        try:
            requests.post(
                WEBHOOK_URL,
                json={"message": msg, "channel": DISCORD_CHANNEL},
                timeout=5,
            )
            state[event_id] = now.isoformat()
            print(f"リマインド送信: {summary} ({time_str})")
        except Exception as e:
            print(f"失敗: {e}")

    cutoff = (now - datetime.timedelta(days=1)).isoformat()
    state = {k: v for k, v in state.items() if v > cutoff}
    save_state(STATE_FILE, state)


if __name__ == "__main__":
    main()
