#!/usr/bin/env python3
"""discord_log_to_library.py — Discord ログを日次で Notion Log Library DB に送る。

直近 24 時間の Discord メッセージ（DISCORD_CHANNEL_RANDOM / DISCORD_CHANNEL_MAIL /
DISCORD_CHANNEL_EXTRA）を集めて、Notion の Log Library DB に 1 ページとして投下する。
まとめ資料・ログは md でなく Notion Log Library に集約する方針（AGENT/AGENTS.md 参照）。

環境変数:
    NOTION_TOKEN             Notion Internal Integration Secret
    NOTION_DB_LOG_LIBRARY    Log Library DB の ID
    DISCORD_CHANNEL_RANDOM   主チャンネル（必須）
    DISCORD_CHANNEL_MAIL     メールチャンネル（任意）
    DISCORD_CHANNEL_EXTRA    追加チャンネル（カンマ区切り、任意）
    DISCORD_BOT_TOKEN        ~/.claude/channels/discord/.env から読む

cron の例（毎日 23:50 にその日の分を送る）:
    50 23 * * * /usr/bin/python3 ~/secretary/scripts/integrations/notion/discord_log_to_library.py >> /tmp/discord_log_to_library.log 2>&1
"""

from __future__ import annotations

import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests
from dotenv import load_dotenv

SECRETARY_HOME = Path(os.environ.get("SECRETARY_HOME", str(Path(__file__).resolve().parents[3])))
load_dotenv(SECRETARY_HOME / ".env")

JST = timezone(timedelta(hours=9))
NOTION_API = "https://api.notion.com/v1"
NOTION_VERSION = "2022-06-28"
DISCORD_API = "https://discord.com/api/v10"
TIMEOUT_SEC = 30
LOOKBACK_HOURS = 24
MAX_BLOCK_CHARS = 1900  # Notion rich_text の 2000 文字上限に余裕

NOTION_TOKEN = os.environ.get("NOTION_TOKEN", "")
DB_ID = os.environ.get("NOTION_DB_LOG_LIBRARY", "")


def _discord_token() -> str:
    p = Path.home() / ".claude" / "channels" / "discord" / ".env"
    if not p.exists():
        return ""
    for line in p.read_text(encoding="utf-8").splitlines():
        if line.startswith("DISCORD_BOT_TOKEN="):
            return line.split("=", 1)[1].strip()
    return ""


def _channels() -> list[tuple[str, str]]:
    """(label, channel_id) のリスト。空 ID は除外。"""
    out: list[tuple[str, str]] = []
    main = os.environ.get("DISCORD_CHANNEL_RANDOM", "").strip()
    mail = os.environ.get("DISCORD_CHANNEL_MAIL", "").strip()
    if main:
        out.append(("random", main))
    if mail and mail != main:
        out.append(("mail", mail))
    extra = os.environ.get("DISCORD_CHANNEL_EXTRA", "").strip()
    for c in (x.strip() for x in extra.split(",")):
        if c and c not in {cid for _, cid in out}:
            out.append((c, c))
    return out


def fetch_messages(token: str, channel_id: str, cutoff: datetime) -> list[dict]:
    """直近 cutoff 以降のメッセージを古い順で返す（最大 100 件）。"""
    headers = {"Authorization": f"Bot {token}"}
    r = requests.get(
        f"{DISCORD_API}/channels/{channel_id}/messages?limit=100",
        headers=headers,
        timeout=TIMEOUT_SEC,
    )
    if r.status_code != 200:
        print(f"⚠ ch {channel_id} 取得失敗: HTTP {r.status_code}", file=sys.stderr)
        return []
    msgs = []
    for m in r.json():
        ts = datetime.fromisoformat(m["timestamp"].replace("Z", "+00:00"))
        if ts >= cutoff:
            msgs.append(m)
    msgs.reverse()  # 古い順
    return msgs


def _chunk(text: str, size: int) -> list[str]:
    return [text[i : i + size] for i in range(0, len(text), size)] or [""]


def create_log_page(title: str, date_str: str, source: str, summary: str, body: str) -> bool:
    headers = {
        "Authorization": f"Bearer {NOTION_TOKEN}",
        "Notion-Version": NOTION_VERSION,
        "Content-Type": "application/json",
    }
    children = [
        {
            "object": "block",
            "type": "paragraph",
            "paragraph": {"rich_text": [{"type": "text", "text": {"content": chunk}}]},
        }
        for chunk in _chunk(body, MAX_BLOCK_CHARS)[:90]  # Notion children 上限 100 に余裕
    ]
    payload = {
        "parent": {"database_id": DB_ID},
        "properties": {
            "Title": {"title": [{"text": {"content": title[:200]}}]},
            "Date": {"date": {"start": date_str}},
            "Category": {"select": {"name": "discord-log"}},
            "Source": {"rich_text": [{"text": {"content": source[:200]}}]},
            "Summary": {"rich_text": [{"text": {"content": summary[:1900]}}]},
        },
        "children": children,
    }
    r = requests.post(
        f"{NOTION_API}/pages", headers=headers, json=payload, timeout=TIMEOUT_SEC
    )
    if r.status_code not in (200, 201):
        print(f"❌ Notion ページ作成失敗: HTTP {r.status_code}: {r.text[:200]}", file=sys.stderr)
        return False
    return True


def main() -> int:
    # Notion 未設定なら何もせず正常終了（Notion 連携をしていない構成では cron が
    # 毎日エラーにならないよう skip 扱い）。
    if not NOTION_TOKEN or not DB_ID:
        print("Notion 未設定（NOTION_TOKEN / NOTION_DB_LOG_LIBRARY）、skip")
        return 0
    token = _discord_token()
    if not token:
        print("DISCORD_BOT_TOKEN が無い、skip")
        return 0

    now = datetime.now(JST)
    cutoff = (now - timedelta(hours=LOOKBACK_HOURS)).astimezone(timezone.utc)
    date_str = now.strftime("%Y-%m-%d")

    lines: list[str] = []
    total = 0
    labels: list[str] = []
    for label, ch_id in _channels():
        msgs = fetch_messages(token, ch_id, cutoff)
        if not msgs:
            continue
        labels.append(label)
        lines.append(f"=== #{label} ({len(msgs)} 件) ===")
        for m in msgs:
            ts = datetime.fromisoformat(m["timestamp"].replace("Z", "+00:00")).astimezone(JST)
            author = m.get("author", {}).get("username", "?")
            content = (m.get("content") or "").replace("\n", " ")
            if not content:
                content = "[添付/埋め込みのみ]"
            lines.append(f"[{ts:%H:%M}] {author}: {content}")
        lines.append("")
        total += len(msgs)
        time.sleep(0.4)  # Discord レート制限に余裕

    if total == 0:
        print("メッセージなし（24h）、ページ作成スキップ")
        return 0

    body = "\n".join(lines)
    summary = f"{date_str} の Discord ログ {total} 件 / ch: {', '.join(labels)}"
    ok = create_log_page(
        title=f"Discord log {date_str}",
        date_str=date_str,
        source=", ".join(labels),
        summary=summary,
        body=body,
    )
    print(f"✅ Log Library に投下: {total} 件" if ok else "❌ 投下失敗")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
