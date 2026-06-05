"""シークレット（.env / 環境変数）の中央ローダー。

使い方:

    from scripts.lib.secrets import get, get_or_die, env_file

    token = get("DISCORD_BOT_TOKEN")           # 無ければ None
    token = get_or_die("DISCORD_BOT_TOKEN")    # 無ければ例外

シークレットはリポジトリルートの .env から読み込む。将来 Vault や AWS
Secrets Manager に差し替える場合はこのモジュールを置き換えればよい。
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
ENV_FILE = REPO_ROOT / ".env"

# import 時に一度だけ .env をロード（冪等）
load_dotenv(ENV_FILE)


def env_file() -> Path:
    """.env ファイルのパスを返す（デバッグ用）"""
    return ENV_FILE


def get(key: str, default: str | None = None) -> str | None:
    """シークレットを取得。環境変数が .env より優先される"""
    return os.environ.get(key, default)


def get_or_die(key: str) -> str:
    """必須シークレットを取得。無ければ RuntimeError"""
    val = os.environ.get(key)
    if not val:
        raise RuntimeError(
            f"必須シークレット '{key}' が未設定です。{ENV_FILE} か環境変数を確認してください。"
        )
    return val


def all_env_keys() -> list[str]:
    """.env に定義されている全キーを返す（値は返さない）"""
    keys = []
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                keys.append(line.split("=", 1)[0])
    return keys
