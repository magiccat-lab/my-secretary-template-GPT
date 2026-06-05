#!/usr/bin/env python3
"""
Discordチャンネルに直接メッセージを送信するヘルパー
脳 (codex/Claude) を介さず、ボットトークンで直接Discord APIを叩く。
GPT版秘書ではエージェント (codex) が返信のたびにこれを bash で呼ぶ:
    python3 scripts/discord_send.py <channel_id> "本文"
"""
import os
import sys
import requests

def load_token() -> str:
    # 解決順: 環境変数 → $SECRETARY_HOME/.env → 各種 .env。
    # codex 版は ~/.claude に依存しない (auth 保存場所を混ぜない)。
    tok = os.environ.get("DISCORD_BOT_TOKEN")
    if tok:
        return tok
    home = os.environ.get("SECRETARY_HOME", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    candidates = [
        os.path.join(home, ".env"),
        os.path.expanduser("~/.codex/channels/discord/.env"),
        os.path.expanduser("~/.claude/channels/discord/.env"),
    ]
    for env_path in candidates:
        if not os.path.exists(env_path):
            continue
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line.startswith("DISCORD_BOT_TOKEN="):
                    return line.split("=", 1)[1].strip().strip('"').strip("'")
    raise RuntimeError("DISCORD_BOT_TOKEN not found (env / $SECRETARY_HOME/.env / ~/.codex / ~/.claude)")

def send(channel_id: str, message: str) -> bool:
    token = load_token()
    r = requests.post(
        f"https://discord.com/api/v10/channels/{channel_id}/messages",
        headers={
            "Authorization": f"Bot {token}",
            "Content-Type": "application/json"
        },
        json={"content": message},
        timeout=10
    )
    if r.status_code == 200:
        return True
    else:
        print(f"Discord送信エラー: {r.status_code} {r.text}", file=sys.stderr)
        return False

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: discord_send.py <channel_id> <message>")
        sys.exit(1)
    channel_id = sys.argv[1]
    message = sys.argv[2]
    ok = send(channel_id, message)
    sys.exit(0 if ok else 1)
