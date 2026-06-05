"""Brave Search API のラッパー。

環境（.env）に BRAVE_API_KEY が必要。

使い方:

    from scripts.lib.brave_search import search

    results = search("python asyncio tutorial", count=10)
    # [{"title": ..., "url": ..., "description": ...}, ...]
"""

from __future__ import annotations

import os
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
load_dotenv(_REPO_ROOT / ".env")

BRAVE_API_KEY = os.environ.get("BRAVE_API_KEY", "")
BRAVE_ENDPOINT = "https://api.search.brave.com/res/v1/web/search"


class BraveSearchError(RuntimeError):
    """Brave Search API のエラー"""


def search(
    query: str,
    count: int = 20,
    *,
    timeout: int = 15,
    retries: int = 3,
    country: str | None = None,
    search_lang: str | None = None,
) -> list[dict]:
    """Brave 検索を実行して結果の dict リストを返す"""
    if not BRAVE_API_KEY:
        raise BraveSearchError("環境に BRAVE_API_KEY が設定されていません")

    headers = {"Accept": "application/json", "X-Subscription-Token": BRAVE_API_KEY}
    params: dict = {"q": query, "count": count}
    if country:
        params["country"] = country
    if search_lang:
        params["search_lang"] = search_lang

    last_err: Exception | None = None
    for attempt in range(retries):
        try:
            r = requests.get(BRAVE_ENDPOINT, headers=headers, params=params, timeout=timeout)
            if r.status_code == 429:
                time.sleep(2**attempt)
                continue
            r.raise_for_status()
            data = r.json()
            return data.get("web", {}).get("results", [])
        except Exception as e:
            last_err = e
            if attempt < retries - 1:
                time.sleep(2**attempt)
    raise BraveSearchError(f"Brave Search が {retries} 回リトライ後に失敗: {last_err}")
