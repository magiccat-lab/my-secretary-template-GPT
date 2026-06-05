#!/usr/bin/env python3
"""discord_listener.py — Discord 受信ゲートウェイ (GPT版秘書)。

Claude 版は Discord plugin が Gateway 接続して受信していたが、codex にその plugin は
無い。本リスナーが discord.py で Gateway に接続し、許可チャンネルのメッセージを
queue に積む。worker (codex_queue_worker.py) がそれを codex に渡し、codex は
discord_send.py で返信する。これで受信↔送信が閉じる。

allowlist:
    DISCORD_ALLOWED_CHANNELS  (カンマ区切りの channel_id)。未設定なら全チャンネル無視。
自分の bot 発言と、他 bot 発言は無視 (ループ防止)。

enqueue 形式 (worker が decode して codex に渡すプロンプト):
    [Discord] channel_id=<cid> from <user>: <本文>

必要: pip install discord.py / .env に DISCORD_BOT_TOKEN
起動: python3 scripts/discord_listener.py  (start_server.sh が screen で常駐させる)
"""
from __future__ import annotations

import base64
import os
import sys
from pathlib import Path

SECRETARY_HOME = Path(os.environ.get("SECRETARY_HOME", str(Path(__file__).resolve().parents[1])))
QUEUE_FILE = Path(os.environ.get("CODEX_QUEUE_FILE", "/tmp/codex_queue.txt"))

# .env を環境に読み込む (DISCORD_BOT_TOKEN / DISCORD_ALLOWED_CHANNELS 等)
try:
    from dotenv import load_dotenv
    load_dotenv(SECRETARY_HOME / ".env")
except ImportError:
    pass


def _load_token() -> str:
    tok = os.environ.get("DISCORD_BOT_TOKEN")
    if tok:
        return tok
    for p in [SECRETARY_HOME / ".env",
              Path(os.path.expanduser("~/.codex/channels/discord/.env"))]:
        if p.exists():
            for line in p.read_text().splitlines():
                if line.startswith("DISCORD_BOT_TOKEN="):
                    return line.split("=", 1)[1].strip().strip('"').strip("'")
    raise RuntimeError("DISCORD_BOT_TOKEN not found (env / $SECRETARY_HOME/.env)")


def _allowed() -> set[int]:
    # DISCORD_ALLOWED_CHANNELS (カンマ区切り) を主に使う。
    # SETUP が立てる .env の DISCORD_CHANNEL_RANDOM / DISCORD_CHANNEL_MAIL も拾う (後方互換)。
    out: set[int] = set()
    sources = [os.environ.get("DISCORD_ALLOWED_CHANNELS", "")]
    for key in ("DISCORD_CHANNEL_RANDOM", "DISCORD_CHANNEL_MAIL"):
        v = os.environ.get(key)
        if v:
            sources.append(v)
    for raw in sources:
        for c in raw.split(","):
            c = c.strip()
            if c.isdigit():
                out.add(int(c))
    return out


def enqueue(channel_id: int, user: str, content: str) -> None:
    prompt = f"[Discord] channel_id={channel_id} from {user}: {content}"
    encoded = base64.b64encode(prompt.encode("utf-8")).decode()
    with open(QUEUE_FILE, "a") as f:
        f.write(encoded + "\n")


def main() -> int:
    try:
        import discord
    except ImportError:
        print("discord.py 未インストール。`pip install discord.py` を実行", file=sys.stderr)
        return 1

    token = _load_token()
    allowed = _allowed()
    if not allowed:
        print("⚠️ DISCORD_ALLOWED_CHANNELS 未設定。全チャンネルを無視する (安全側)", file=sys.stderr)

    intents = discord.Intents.default()
    intents.message_content = True  # Developer Portal で MESSAGE CONTENT INTENT を有効化すること
    client = discord.Client(intents=intents)

    @client.event
    async def on_ready():
        print(f"discord_listener 接続: {client.user} / 監視 ch={sorted(allowed)}", flush=True)

    @client.event
    async def on_message(message):
        # 自分 / 他 bot は無視 (ループ防止)
        if message.author.bot or (client.user and message.author.id == client.user.id):
            return
        if allowed and message.channel.id not in allowed:
            return
        content = message.content or ""
        if not content.strip():
            return
        enqueue(message.channel.id, str(message.author.display_name), content)
        print(f"enqueue: ch={message.channel.id} from={message.author.display_name} "
              f"len={len(content)}", flush=True)

    client.run(token, log_handler=None)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
