from fastapi import FastAPI, Request
import base64
import logging
import asyncio
import requests as http_requests
from concurrent.futures import ThreadPoolExecutor
import os
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))
JST = timezone(timedelta(hours=9))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()
executor = ThreadPoolExecutor(max_workers=4)

QUEUE_FILE = os.environ.get('CODEX_QUEUE_FILE', '/tmp/codex_queue.txt')
DISCORD_ENV = os.path.expanduser("~/.claude/channels/discord/.env")
SCRIPTS_DIR = os.path.join(os.path.dirname(__file__))

CH_RANDOM = os.getenv('DISCORD_CHANNEL_RANDOM', '')
# メール通知の宛先。未設定なら random にフォールバック。
CH_MAIL = os.getenv('DISCORD_CHANNEL_MAIL', '') or CH_RANDOM
DISCORD_USER_ID = os.getenv('DISCORD_USER_ID', '')


def _load_discord_token() -> str:
    with open(DISCORD_ENV) as f:
        for line in f:
            line = line.strip()
            if line.startswith("DISCORD_BOT_TOKEN="):
                return line.split("=", 1)[1]
    raise RuntimeError("DISCORD_BOT_TOKEN not found")


def discord_send(channel_id: str, message: str) -> bool:
    """Claude を通さず定型メッセージを Discord API で直接送信"""
    try:
        token = _load_discord_token()
        r = http_requests.post(
            f"https://discord.com/api/v10/channels/{channel_id}/messages",
            headers={"Authorization": f"Bot {token}", "Content-Type": "application/json"},
            json={"content": message},
            timeout=10
        )
        if r.status_code == 200:
            logger.info(f"Discord直接送信完了: #{channel_id}")
            return True
        logger.error(f"Discord送信エラー: {r.status_code} {r.text}")
        return False
    except Exception as e:
        logger.error(f"Discord送信例外: {e}")
        return False


def _enqueue_for_brain(message: str):
    encoded = base64.b64encode(message.encode()).decode()
    with open(QUEUE_FILE, 'a') as f:
        f.write(encoded + '\n')
    logger.info(f"キューに追加: {len(message)}文字")


async def enqueue_for_brain(message: str):
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(executor, _enqueue_for_brain, message)


# ============================================================
# コアエンドポイント
# ============================================================

@app.post("/remind")
async def remind(request: Request):
    """リマインダー送信 + オプションでタスク追加"""
    import json
    body = await request.json()
    logger.info(f"リマインド受信: {body}")
    msg = body.get("message", "")
    channel = body.get("channel") or body.get("channel_id", CH_RANDOM)
    task_title = body.get("task", "")
    if not msg:
        return {"status": "error"}
    discord_send(channel, msg)
    if task_title:
        tasks_file = os.path.expanduser("~/secretary/data/pending_tasks.json")
        try:
            if os.path.exists(tasks_file):
                with open(tasks_file) as f:
                    data = json.load(f)
            else:
                data = {"primary": []}
            target = data.get("primary", data.setdefault("tasks", []))
            if not any(t.get("title") == task_title and not t.get("done") for t in target):
                target.append({"title": task_title, "done": False})
                with open(tasks_file, "w") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                logger.info(f"タスク追加: {task_title}")
        except Exception as e:
            logger.error(f"タスク追加エラー: {e}")
    return {"status": "ok"}


@app.post("/gmail_notify")
async def gmail_notify(request: Request):
    """新着メール通知（integrations/gmail/gmail_monitor.py から叩かれる）"""
    body = await request.json()
    logger.info(f"gmail: {body.get('subject', '')}")
    sender = body.get('sender', '')
    subject = body.get('subject', '')
    mail_body = body.get('body', '')

    prompt = (
        f"新着メール — メールチャンネル({CH_MAIL})に reply で通知して。"
        f"From: {sender} / 件名: {subject} / 抜粋: {mail_body[:300]}"
    )
    await enqueue_for_brain(prompt)
    return {"status": "ok"}


@app.get("/health")
async def health():
    return {"status": "ok", "ts": datetime.now(JST).isoformat()}


# ============================================================
# カスタムエンドポイント（以下に自分の機能を追加）
# ============================================================
# 例: 音声入力の中継、位置情報の通知、起床トリガー、センサー連携など、
# Tasker / Home Assistant / その他から HTTP POST を受けてここで処理する。
#
# @app.post("/my_feature")
# async def my_feature(request: Request):
#     body = await request.json()
#     # 定型メッセージだけ流すなら discord_send() で直送
#     discord_send(CH_RANDOM, f"受信: {body}")
#     # Claude に処理させたいなら send_to_claude() でキューに投入
#     await enqueue_for_brain(f"以下を処理して: {body}")
#     return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("WEBHOOK_PORT", "8781")))
