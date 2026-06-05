#!/usr/bin/env python3
"""gmail_cli.py — Gmail 操作の薄い CLI (GPT版秘書用)。

codex (脳) が bash で叩く。送信は二重の安全弁:
  1. --yes が無ければ dry-run (送らず内容表示)
  2. 宛先は GMAIL_ALLOWLIST (カンマ区切り) に含まれるアドレスのみ許可
     (codex レビュー: 送信系は dry-run / allowlist を script 側に持たせる)

使い方:
    python3 gmail_cli.py list [--query "is:unread"] [--max 10]
    python3 gmail_cli.py read --id <message_id>
    python3 gmail_cli.py send --to a@b.com --subject "件名" --body "本文" --yes
"""
from __future__ import annotations

import argparse
import base64
import os
import sys
from email.mime.text import MIMEText

sys.path.insert(0, __file__.rsplit("/", 1)[0])
from google_auth import service  # noqa: E402


def _allowlist() -> set[str]:
    raw = os.environ.get("GMAIL_ALLOWLIST", "")
    return {a.strip().lower() for a in raw.split(",") if a.strip()}


def cmd_list(args) -> int:
    svc = service("gmail", "v1")
    res = svc.users().messages().list(userId="me", q=args.query, maxResults=args.max).execute()
    msgs = res.get("messages", [])
    if not msgs:
        print("該当メッセージなし")
        return 0
    for m in msgs:
        full = svc.users().messages().get(userId="me", id=m["id"], format="metadata",
                                          metadataHeaders=["From", "Subject", "Date"]).execute()
        h = {x["name"]: x["value"] for x in full.get("payload", {}).get("headers", [])}
        print(f"- [{m['id']}] {h.get('Date','?')} | {h.get('From','?')} | {h.get('Subject','(無題)')}")
    return 0


def cmd_read(args) -> int:
    svc = service("gmail", "v1")
    full = svc.users().messages().get(userId="me", id=args.id, format="full").execute()
    h = {x["name"]: x["value"] for x in full.get("payload", {}).get("headers", [])}
    print(f"From: {h.get('From')}\nSubject: {h.get('Subject')}\nDate: {h.get('Date')}\n")
    print(full.get("snippet", ""))
    return 0


def cmd_send(args) -> int:
    to = args.to.strip().lower()
    allow = _allowlist()
    if not allow:
        print("✋ GMAIL_ALLOWLIST 未設定。安全のため送信を拒否 (環境変数に許可宛先を設定)")
        return 1
    if to not in allow:
        print(f"✋ 宛先 {to} は allowlist 外。送信拒否 (許可: {sorted(allow)})")
        return 1
    if not args.yes:
        print("[dry-run] 以下を送信予定 (--yes で実行):")
        print(f"  To: {args.to}\n  Subject: {args.subject}\n  Body: {args.body[:200]}")
        return 0
    msg = MIMEText(args.body)
    msg["to"] = args.to
    msg["subject"] = args.subject
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    svc = service("gmail", "v1")
    sent = svc.users().messages().send(userId="me", body={"raw": raw}).execute()
    print(f"送信完了: id={sent.get('id')}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Gmail CLI")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_list = sub.add_parser("list", help="メッセージ一覧")
    p_list.add_argument("--query", default="is:unread")
    p_list.add_argument("--max", type=int, default=10)
    p_list.set_defaults(func=cmd_list)

    p_read = sub.add_parser("read", help="本文表示")
    p_read.add_argument("--id", required=True)
    p_read.set_defaults(func=cmd_read)

    p_send = sub.add_parser("send", help="送信 (allowlist + --yes 必須)")
    p_send.add_argument("--to", required=True)
    p_send.add_argument("--subject", required=True)
    p_send.add_argument("--body", required=True)
    p_send.add_argument("--yes", action="store_true")
    p_send.set_defaults(func=cmd_send)

    args = ap.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
