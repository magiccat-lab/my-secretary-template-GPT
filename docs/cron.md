# cron 運用（GPT版）

秘書を安定運用するための cron。すべて JST 前提（§A で `timedatectl set-timezone
Asia/Tokyo` 済）。スクリプトは**フルパス**で呼ぶ（`python3` ではなく `/usr/bin/python3`）。

## コア cron

```cron
# 脳(worker)の固着を heartbeat で監視して自動復帰（2分おき）
*/2 * * * * SECRETARY_HOME=$HOME/secretary WATCHDOG_NOTIFY_CHANNEL=YOUR_CH_ID /usr/bin/python3 $HOME/secretary/scripts/session_watchdog.py >> /tmp/session_watchdog.log 2>&1

# プロセス/サーバが落ちたら start_server で復旧（5分おき）
*/5 * * * * SECRETARY_HOME=$HOME/secretary WATCHDOG_NOTIFY_CHANNEL=YOUR_CH_ID /bin/bash $HOME/secretary/scripts/health_check.sh >> /tmp/health_check.log 2>&1

# 未完了タスクを Discord にリマインド（1日2回）
30 6,22 * * * SECRETARY_HOME=$HOME/secretary /usr/bin/python3 $HOME/secretary/scripts/task_remind.py >> /tmp/task_remind.log 2>&1

# 毎日 04:00: handoff を書いてからセッションリセット + 再起動（文脈は handoff で継続）
0 4 * * * SECRETARY_HOME=$HOME/secretary /bin/bash $HOME/secretary/scripts/nightly_restart.sh >> /tmp/nightly_restart.log 2>&1

# その日の Discord ログを Notion Log Library に送る（Notion 未設定なら自動 skip）
50 23 * * * SECRETARY_HOME=$HOME/secretary /usr/bin/python3 $HOME/secretary/scripts/integrations/notion/discord_log_to_library.py >> /tmp/discord_log_to_library.log 2>&1
```

## 機能別 cron（有効化したものだけ足す）

```cron
# Notion タスク同期（5分おき。NOTION_TOKEN/NOTION_DB_TASKS 設定時）
*/5 * * * * SECRETARY_HOME=$HOME/secretary /usr/bin/python3 $HOME/secretary/scripts/integrations/notion/sync_pending_to_notion.py >> /tmp/notion_sync.log 2>&1
```

朝の挨拶・天気・予定通知などの定期メッセージは、秘書に「毎朝8時に〇〇送って」と
Discord で頼めば cron 行を作ってくれる（`webhook_server.py` の `/remind` 等を叩く形）。

## 確認・デバッグ

```bash
crontab -l                              # 登録内容
sudo grep CRON /var/log/syslog | tail   # 実行されているか
tail -n 100 /tmp/session_watchdog.log   # watchdog の判定ログ
```

- cron は最小限の環境変数しか持たない。`SECRETARY_HOME` を各行で明示している。
- `WATCHDOG_NOTIFY_CHANNEL` は通知先 channel_id に置換する。
- nightly リセットが不要なら `0 4 * * *` の行を削ってよい（codex は job 駆動なので
  Claude 版ほど常駐コンテキストが溜まらない）。
