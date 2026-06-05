"""Discord チャンネル ID レジストリ（単一の情報源）。

チャンネル ID は全て .env に定義する。このモジュールはそれらを Python 定数と
名前→ID の引き当て関数として公開する。

使い方:

    from scripts.lib.channels import RANDOM, get_channel

    requests.post(..., json={"channel": RANDOM, ...})
    ch = get_channel("logch")    # 追加したチャンネル名を指定

新しいチャンネルは .env と下の `_NAME_MAP` に追加:

    .env:         DISCORD_CHANNEL_LOGCH=123...
    channels.py:  LOGCH = _ch("DISCORD_CHANNEL_LOGCH")
                  _NAME_MAP["logch"] = LOGCH
"""

from __future__ import annotations

import os

from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".env"))


def _ch(env_key: str, default: str = "") -> str:
    return os.environ.get(env_key, default)


# コアチャンネル。必要に応じて追加し、下の _NAME_MAP も更新する。
RANDOM = _ch("DISCORD_CHANNEL_RANDOM")

_NAME_MAP = {
    "random": RANDOM,
}


def get_channel(name: str) -> str:
    """名前からチャンネル ID を引く（大文字小文字無視）"""
    return _NAME_MAP[name.lower()]


def all_channels() -> dict[str, str]:
    """登録済みの全チャンネルを返す（デバッグ用）"""
    return dict(_NAME_MAP)


if __name__ == "__main__":
    for name, ch in _NAME_MAP.items():
        print(f"  {name}: {ch}")
