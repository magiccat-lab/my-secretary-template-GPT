#!/usr/bin/env python3
"""sync_pending_to_notion.py — pending_tasks.json を Notion DB に片方向同期

このスクリプトの役割:
- ローカルの `data/pending_tasks.json` を「正」とみなし、Notion DB に反映する
- スマホや別 PC から Notion で見た / チェックを入れたとしても、ローカル側を
  上書きすることはない（双方向同期したい場合は `sync_notion_to_pending.py` を別途使う）
- SourceKey プロパティで upsert: 既存ページがあれば update、無ければ create

cron 例:
    */5 * * * * /usr/bin/python3 ~/secretary/scripts/integrations/notion/sync_pending_to_notion.py >> /tmp/sync_pending_to_notion.log 2>&1

必要な Notion DB プロパティ:
- Name        (title)
- Done        (checkbox)
- SourceKey   (rich_text)
- Created     (date)
- Completed   (date)
- Remind      (date)
- Detail      (rich_text)
- Type        (select) — 任意

詳細は docs/notion.md 参照。
"""

from __future__ import annotations

import hashlib
import json
import os
import random
import sys
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

# cron 同時起動の負荷分散ジッター（同じ秒に他 sync が走っているとレート制限に当たる）
time.sleep(random.uniform(0, 5))

SECRETARY_HOME = Path(os.environ.get("SECRETARY_HOME", str(Path(__file__).resolve().parents[3])))
load_dotenv(SECRETARY_HOME / ".env")

NOTION_TOKEN = os.environ.get("NOTION_TOKEN", "")
DB_ID = os.environ.get("NOTION_DB_TASKS", "")
PENDING_JSON = SECRETARY_HOME / "data" / "pending_tasks.json"

NOTION_API = "https://api.notion.com/v1"
NOTION_VERSION = "2022-06-28"
TIMEOUT_SEC = 30


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {NOTION_TOKEN}",
        "Notion-Version": NOTION_VERSION,
        "Content-Type": "application/json",
    }


def _request_with_retry(method: str, url: str, **kwargs) -> requests.Response:
    """timeout / 5xx / レート制限に対する単純リトライ（最大 3 回、指数バックオフ）"""
    last_exc: Exception | None = None
    for attempt in range(3):
        try:
            r = requests.request(method, url, timeout=TIMEOUT_SEC, **kwargs)
            if r.status_code < 500 and r.status_code != 429:
                return r
            last_exc = RuntimeError(f"HTTP {r.status_code}: {r.text[:200]}")
        except requests.RequestException as e:
            last_exc = e
        time.sleep(2 ** attempt)
    raise RuntimeError(f"notion request failed after retries: {last_exc}")


def task_source_key(task: dict) -> str:
    """SourceKey: title + created_at の SHA1 短縮（重複検知用）"""
    raw = f"{task.get('title', '')}|{task.get('created_at', '')}"
    return hashlib.sha1(raw.encode()).hexdigest()[:16]


def task_to_properties(task: dict) -> dict:
    """task dict → Notion プロパティ辞書"""
    props: dict = {
        "Name": {"title": [{"text": {"content": task.get("title", "")[:200]}}]},
        "Done": {"checkbox": bool(task.get("done", False))},
        "SourceKey": {"rich_text": [{"text": {"content": task_source_key(task)}}]},
    }
    if task.get("type"):
        props["Type"] = {"select": {"name": task["type"][:40]}}
    if task.get("created_at"):
        props["Created"] = {"date": {"start": task["created_at"]}}
    if task.get("completed_at"):
        props["Completed"] = {"date": {"start": task["completed_at"]}}
    if task.get("remind_at"):
        props["Remind"] = {"date": {"start": task["remind_at"]}}
    if task.get("detail"):
        props["Detail"] = {"rich_text": [{"text": {"content": task["detail"][:2000]}}]}
    return props


def find_existing_page_id(source_key: str) -> str | None:
    """SourceKey で既存ページを検索、見つかればその page_id を返す"""
    url = f"{NOTION_API}/databases/{DB_ID}/query"
    body = {
        "filter": {"property": "SourceKey", "rich_text": {"equals": source_key}},
        "page_size": 1,
    }
    r = _request_with_retry("POST", url, headers=_headers(), json=body)
    if r.status_code != 200:
        return None
    results = r.json().get("results", [])
    return results[0]["id"] if results else None


def create_page(props: dict) -> bool:
    body = {"parent": {"database_id": DB_ID}, "properties": props}
    r = _request_with_retry("POST", f"{NOTION_API}/pages", headers=_headers(), json=body)
    return r.status_code in (200, 201)


def update_page(page_id: str, props: dict) -> bool:
    body = {"properties": props}
    r = _request_with_retry("PATCH", f"{NOTION_API}/pages/{page_id}", headers=_headers(), json=body)
    return r.status_code == 200


def main() -> int:
    if not NOTION_TOKEN:
        print("❌ NOTION_TOKEN が .env に未設定", file=sys.stderr)
        return 1
    if not DB_ID:
        print("❌ NOTION_DB_TASKS が .env に未設定", file=sys.stderr)
        return 1
    if not PENDING_JSON.exists():
        print(f"❌ pending_tasks.json が無い: {PENDING_JSON}", file=sys.stderr)
        return 1

    data = json.loads(PENDING_JSON.read_text(encoding="utf-8"))
    # pending_tasks.json はセクション構造 {"primary": [...], ...}（docs/tasks.md 参照）。
    # 全セクション（list 値）を flatten して同期する。デフォルトは "primary" のみだが、
    # 任意のセクションを足しても拾えるようにしておく。
    tasks = [t for section in data.values() if isinstance(section, list) for t in section]

    created = updated = failed = 0
    for task in tasks:
        key = task_source_key(task)
        props = task_to_properties(task)
        try:
            existing_id = find_existing_page_id(key)
            if existing_id:
                ok = update_page(existing_id, props)
                updated += int(ok)
                if not ok:
                    failed += 1
            else:
                ok = create_page(props)
                created += int(ok)
                if not ok:
                    failed += 1
            time.sleep(0.4)  # Notion レート制限 (3 req/s) を超えないため
        except Exception as e:
            print(f"❌ sync 失敗: {task.get('title', '?')[:40]}: {e}", file=sys.stderr)
            failed += 1

    print(f"✅ sync 完了: created={created} / updated={updated} / failed={failed}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
