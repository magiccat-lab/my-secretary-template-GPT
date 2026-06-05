#!/usr/bin/env python3
"""wishlist_add.py — Notion の Wishlist DB に新規ページを追加する CLI

エージェントが「〇〇って店記録して」「〇〇欲しい」「あとで読みたい」等と言われたら
このスクリプトを呼んで Notion DB に追加する。

使い方:
    python3 scripts/integrations/notion/wishlist_add.py \\
        --name "ラーメン二郎 三田本店" \\
        --category "飲食店" \\
        --area "三田" \\
        --memo "次の出張のついでに行く"

必要な Notion DB プロパティ（Wishlist DB を作るときの参考）:
- 名前      (title)
- カテゴリ  (select)   ※飲食店 / Tips / ショッピング 等
- ステータス(select)   ※未訪問 / 行った / 不要 等
- エリア    (select or rich_text)
- 情報源    (url or rich_text)
- メモ      (rich_text)
- 追加日    (date)
"""

from __future__ import annotations

import argparse
import datetime as dt
import os
import sys
from pathlib import Path

import requests
from dotenv import load_dotenv

SECRETARY_HOME = Path(os.environ.get("SECRETARY_HOME", str(Path(__file__).resolve().parents[3])))
load_dotenv(SECRETARY_HOME / ".env")

NOTION_TOKEN = os.environ.get("NOTION_TOKEN", "")
DB_ID = os.environ.get("NOTION_DB_WISHLIST", "")

NOTION_API = "https://api.notion.com/v1"
NOTION_VERSION = "2022-06-28"


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {NOTION_TOKEN}",
        "Notion-Version": NOTION_VERSION,
        "Content-Type": "application/json",
    }


def add_wishlist(
    name: str,
    category: str = "",
    area: str = "",
    source: str = "",
    memo: str = "",
) -> tuple[bool, str]:
    """Wishlist DB に 1 ページ追加。成功フラグと message を返す"""
    if not NOTION_TOKEN or not DB_ID:
        return False, "NOTION_TOKEN または NOTION_DB_WISHLIST が未設定"

    props: dict = {
        "名前": {"title": [{"text": {"content": name[:200]}}]},
        "追加日": {"date": {"start": dt.date.today().isoformat()}},
        "ステータス": {"select": {"name": "未訪問"}},
    }
    if category:
        props["カテゴリ"] = {"select": {"name": category[:40]}}
    if area:
        props["エリア"] = {"rich_text": [{"text": {"content": area}}]}
    if source:
        props["情報源"] = {"url": source} if source.startswith("http") else {
            "rich_text": [{"text": {"content": source}}]
        }
    if memo:
        props["メモ"] = {"rich_text": [{"text": {"content": memo[:2000]}}]}

    body = {"parent": {"database_id": DB_ID}, "properties": props}
    try:
        r = requests.post(f"{NOTION_API}/pages", headers=_headers(), json=body, timeout=30)
        if r.status_code in (200, 201):
            return True, f"追加成功: {name}"
        return False, f"Notion API エラー {r.status_code}: {r.text[:200]}"
    except requests.RequestException as e:
        return False, f"通信失敗: {e}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--name", required=True, help="アイテム名（必須）")
    parser.add_argument("--category", default="", help="カテゴリ（飲食店 / Tips 等）")
    parser.add_argument("--area", default="", help="エリア（三田 / 渋谷 等）")
    parser.add_argument("--source", default="", help="情報源（URL or テキスト）")
    parser.add_argument("--memo", default="", help="メモ")
    args = parser.parse_args()

    ok, msg = add_wishlist(
        name=args.name,
        category=args.category,
        area=args.area,
        source=args.source,
        memo=args.memo,
    )
    print(("✅ " if ok else "❌ ") + msg)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
