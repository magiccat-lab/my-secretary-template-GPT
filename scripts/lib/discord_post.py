"""Discord 投稿用の薄いラッパー。

機能:
- 429（レート制限）時は指数バックオフでリトライ
- 構造化された dict を返す: {"ok": bool, "status_code": int, "error": str | None}
- DISCORD_DRY_RUN=1 で安全にテスト可能

使い方:

    from scripts.lib.discord_post import post

    result = post(channel_id="123...", text="hello")
    if not result["ok"]:
        print(result["error"])
"""

from __future__ import annotations

import os
import time

import requests

_TOKEN_CACHE: str | None = None
_TOKEN_FILE = os.path.expanduser("~/.claude/channels/discord/.env")


def get_token() -> str:
    """Discord bot トークンを取得（キャッシュ付き）"""
    global _TOKEN_CACHE
    if _TOKEN_CACHE:
        return _TOKEN_CACHE

    # 優先順位: 環境変数 > ~/.claude/channels/discord/.env
    env_token = os.environ.get("DISCORD_BOT_TOKEN")
    if env_token:
        _TOKEN_CACHE = env_token
        return env_token

    if os.path.exists(_TOKEN_FILE):
        with open(_TOKEN_FILE) as f:
            for line in f:
                if line.startswith("DISCORD_BOT_TOKEN="):
                    _TOKEN_CACHE = line.strip().split("=", 1)[1]
                    return _TOKEN_CACHE

    raise RuntimeError(
        "Discord bot トークンが env や ~/.claude/channels/discord/.env に見つかりません"
    )


def post(
    channel_id: str,
    text: str,
    *,
    timeout: int = 10,
    max_retries: int = 3,
) -> dict:
    """Discord チャンネルにメッセージを投稿する。

    Args:
        channel_id: 投稿先チャンネル ID
        text: 本文
        timeout: リクエストごとのタイムアウト（秒）
        max_retries: 429 レート制限時のリトライ回数

    Returns:
        キー ok, status_code, error, (dry_run) を持つ dict

    DISCORD_DRY_RUN=1 をセットすると送信せずログ出力のみ。
    """
    if os.environ.get("DISCORD_DRY_RUN") == "1":
        import logging

        logging.getLogger(__name__).info(
            f"[DRY_RUN] discord_post.post(channel={channel_id}, text={text[:80]}...)"
        )
        return {"ok": True, "status_code": 0, "error": None, "dry_run": True}

    try:
        token = get_token()
    except RuntimeError as e:
        return {"ok": False, "status_code": 0, "error": str(e)}

    url = f"https://discord.com/api/v10/channels/{channel_id}/messages"
    headers = {
        "Authorization": f"Bot {token}",
        "Content-Type": "application/json",
    }
    payload = {"content": text}

    for attempt in range(max_retries):
        try:
            r = requests.post(url, headers=headers, json=payload, timeout=timeout)
        except requests.RequestException as e:
            return {"ok": False, "status_code": 0, "error": str(e)}

        if r.status_code == 429:
            try:
                retry_after = r.json().get("retry_after", 1)
            except Exception:
                retry_after = 2**attempt
            time.sleep(float(retry_after))
            continue

        return {
            "ok": 200 <= r.status_code < 300,
            "status_code": r.status_code,
            "error": None if r.status_code < 400 else r.text[:200],
        }

    return {"ok": False, "status_code": 429, "error": "リトライ後もレート制限を超過しました"}
