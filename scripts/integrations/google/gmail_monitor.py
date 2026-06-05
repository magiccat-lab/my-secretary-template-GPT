#!/usr/bin/env python3
"""Gmail の新着メール監視。

毎分 cron で起動。未読メッセージを取得して分類し（自動返信 / サイレント
アーカイブ / 通常）、通常メールだけ webhook で通知する。

環境変数:
    GOOGLE_TOKEN_PATH  Google 共通 OAuth token.json のパス（デフォルト: integrations/google/token.json）
                       Calendar / Gmail / Sheets / Drive / Docs / Forms で同じトークンを共有する
    STATE_DIR          ステート保存ディレクトリ（デフォルト: ~/secretary/data）
    WEBHOOK_URL        通知先エンドポイント（デフォルト: http://localhost:8781/gmail_notify）
    CONCIERGE_DOMAIN   オプション: このドメインからのメールを "concierge" として扱う

cron の例:
    * * * * * /usr/bin/python3 ~/secretary/integrations/gmail/gmail_monitor.py \\
        >> /tmp/gmail_monitor.log 2>&1
"""

from __future__ import annotations

import base64
import os
import sys
from email import message_from_bytes
from email.header import decode_header

import requests

# `from scripts.lib.state_store import ...` を動かすためリポジトリルートを sys.path に追加。
# __file__ -> integrations/gmail/gmail_monitor.py なので dirname を3回でルートに到達。
# このファイルは scripts/integrations/google/ 配下なので repo root は 4 階層上
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(__file__)))))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

# 認証は google_auth.py に集約 (GPT版は token を ~/.codex/secrets に隔離)
sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))
import google_auth  # noqa: E402

from scripts.lib.state_store import load_state, save_state  # noqa: E402
STATE_FILE = os.path.join(
    os.getenv("STATE_DIR", os.path.expanduser("~/secretary/data")),
    "gmail_monitor_state.json",
)
WEBHOOK = os.getenv("WEBHOOK_URL", "http://localhost:8781/gmail_notify")
CONCIERGE_DOMAIN = os.getenv("CONCIERGE_DOMAIN", "")

SCOPES = [
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.modify",
]

SILENT_ARCHIVE_SENDERS = [
    "docs.google.com",
    "drive-shares-noreply@google.com",
]

AUTO_REPLY_KEYWORDS = [
    "auto reply",
    "auto-reply",
    "automatic reply",
    "out of office",
    "this is an auto",
    "automailer",
    "noreply",
    "no-reply",
]
AUTO_REPLY_SUBJECTS = [
    "auto reply",
    "automatic reply",
    "out of office",
]


def decode_str(s: str) -> str:
    parts = decode_header(s)
    result = ""
    for part, enc in parts:
        if isinstance(part, bytes):
            result += part.decode(enc or "utf-8", errors="replace")
        else:
            result += part
    return result


def get_body(msg) -> str:
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain":
                payload = part.get_payload(decode=True)
                charset = part.get_content_charset() or "utf-8"
                return payload.decode(charset, errors="replace")
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            charset = msg.get_content_charset() or "utf-8"
            return payload.decode(charset, errors="replace")
    return ""


def is_auto_reply(msg, body: str) -> bool:
    auto_submitted = msg.get("Auto-Submitted", "")
    if auto_submitted and auto_submitted != "no":
        return True
    subject = decode_str(msg.get("Subject", "")).lower()
    if any(kw in subject for kw in AUTO_REPLY_SUBJECTS):
        return True
    body_lower = body.lower()
    return any(kw in body_lower for kw in AUTO_REPLY_KEYWORDS)


def _load_state() -> dict:
    return load_state(STATE_FILE, default={"seen_ids": []})


def _save_state(state: dict) -> None:
    save_state(STATE_FILE, state)


def mark_read(service, mid: str) -> None:
    service.users().messages().modify(
        userId="me", id=mid, body={"removeLabelIds": ["UNREAD"]}
    ).execute()


def archive(service, mid: str) -> None:
    service.users().messages().modify(
        userId="me", id=mid, body={"removeLabelIds": ["UNREAD", "INBOX"]}
    ).execute()


def main() -> None:
    import time

    service = None
    for attempt in range(3):
        try:
            service = google_auth.service("gmail", "v1")
            service.users().getProfile(userId="me").execute()
            break
        except Exception as e:
            if attempt < 2:
                wait = 5 * (2**attempt)
                print(f"接続失敗 (試行 {attempt + 1}/3): {e} -> {wait}秒後にリトライ")
                time.sleep(wait)
            else:
                print(f"接続失敗 3回: {e} -> スキップ")
                return

    state = _load_state()
    seen_ids = set(state.get("seen_ids", []))
    first_run = len(seen_ids) == 0

    result = (
        service.users().messages().list(userId="me", q="is:unread", maxResults=20).execute()
    )
    messages = result.get("messages", [])

    new_seen = set()
    notifications = []

    for m in messages:
        mid = m["id"]
        new_seen.add(mid)
        if mid in seen_ids:
            continue

        detail = service.users().messages().get(userId="me", id=mid, format="raw").execute()
        raw = base64.urlsafe_b64decode(detail["raw"])
        msg = message_from_bytes(raw)

        sender = decode_str(msg.get("From", ""))
        subject = decode_str(msg.get("Subject", "(件名なし)"))
        body = get_body(msg).strip()[:1000]
        auto = is_auto_reply(msg, body)

        is_concierge = bool(CONCIERGE_DOMAIN) and CONCIERGE_DOMAIN in sender
        is_silent_archive = any(s in sender for s in SILENT_ARCHIVE_SENDERS)

        notifications.append(
            {
                "sender": sender,
                "subject": subject,
                "body": body,
                "is_concierge": is_concierge,
                "is_auto_reply": auto,
                "is_silent_archive": is_silent_archive,
                "mid": mid,
            }
        )

    if not first_run:
        for n in notifications:
            try:
                if n["is_silent_archive"]:
                    archive(service, n["mid"])
                    continue
                requests.post(WEBHOOK, json=n, timeout=10)
                mark_read(service, n["mid"])
                if n["is_auto_reply"]:
                    archive(service, n["mid"])
            except Exception as e:
                print(f"通知失敗（次回リトライします）: {e}")
                new_seen.discard(n["mid"])

    state["seen_ids"] = list(seen_ids | new_seen)[-200:]
    _save_state(state)
    print(f"完了: 新着 {len(notifications)} 件")


if __name__ == "__main__":
    main()
