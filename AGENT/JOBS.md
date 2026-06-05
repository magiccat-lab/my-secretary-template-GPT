# JOBS.md — 定期実行ジョブ

秘書に「いつ何をさせるか」を記述するファイル。1ジョブ1行にまとめて、
詳細はスクリプトやスキルファイルに寄せるのが推奨。

## タイムゾーンのルール

ここに書く時刻はすべて JST（Asia/Tokyo）。`cron` や `at` も JST で指定。
詳細は `docs/cron.md` 参照。

---

## コアジョブ（テンプレートに同梱）

### タスクリマインダー
- スクリプト: `scripts/task_remind.py`
- Cron: `30 6,22 * * *`（1日2回 — 好みで調整）
- `data/pending_tasks.json` をスキャンして未完了分を `DISCORD_CHANNEL_RANDOM` に投稿。

### 死活監視
- スクリプト: `scripts/health_check.sh`
- Cron: `*/5 * * * *`
- webhook / screen / claude のどれかが落ちていたら再起動。

### デイリー handoff
- スクリプト: `scripts/daily_handoff.py`
- Cron: `0 3 * * *`（または停止前に手動実行）
- `data/handoff.md` を書いて、次のセッションが引き継げるようにする。

### 定期コールドリスタート（推奨）
- スクリプト: `scripts/restart.sh`
- Cron: `0 3 * * *`（毎日 03:00 の nightly を推奨。週1なら `10 3 * * 0`）
- handoff を残してから screen セッションをコールドスタートし直す。会話コンテキストの
  肥大で重く/不安定になるのを防ぐ。24/7 稼働ならほぼ必須。

### セッションハング watchdog（推奨）
- スクリプト: `scripts/session_watchdog.py`
- Cron: `*/2 * * * *`（2 分おき）
- screen バッファを覗いて「固まった」状態（使用量上限/選択肢プロンプト/MCP 認証待ち/
  キュー詰まり）を検出し、`screen -X stuff` で適切なキーを送って自動復帰。`health_check.sh`
  が拾う「落ちた」と相補。`WATCHDOG_DRY_RUN=1` で送信せず検出のみ。
- 24h で 8 回超 fire したらループとみなし停止 + 通知（手動確認を促す）。

---

## オプションのインテグレーション

`.env` で有効化し、cron の行をコメントアウトから戻す。

### カレンダーリマインド（Google Calendar）
- スクリプト: `integrations/gcal/gcal_remind.py`
- Cron: `* * * * *`（毎分）
- Env: `GCAL_REMIND_ENABLED=true`, `GCAL_CALENDAR_ID=...`
- 予定の30分前に random チャンネルへ通知。

### Gmail モニター
- スクリプト: `integrations/gmail/gmail_monitor.py`
- Cron: `* * * * *`
- Env: `GMAIL_ENABLED=true`, `DISCORD_CHANNEL_MAIL`（通知先。未設定なら random）
- 新着メールは webhook 経由でエージェントに渡り、`DISCORD_CHANNEL_MAIL` に reply で通知する。
- 自動返信のフィルタ、Google Docs のサイレントアーカイブ付き。
- 監視は `GOOGLE_TOKEN_PATH` の 1 アカウント。別アカウントは「監視アカウントへ転送」か
  「そのアカウントの token を足してモニターを増設」で対応。

### Notion 同期（Tasks）
- スクリプト: `scripts/integrations/notion/sync_pending_to_notion.py`
- Cron: `*/5 * * * *`
- Env: `NOTION_TOKEN`, `NOTION_DB_TASKS`
- `data/pending_tasks.json` を Notion DB に片方向同期（5 分間隔）。
- セットアップは `SETUP.md` G2 / 詳細 `docs/notion.md` 参照。

### Discord ログ → Log Library（必須・日次）
- スクリプト: `scripts/integrations/notion/discord_log_to_library.py`
- Cron: `50 23 * * *`（コア cron セット）
- Env: `NOTION_TOKEN`, `NOTION_DB_LOG_LIBRARY`, `DISCORD_CHANNEL_*`
- その日の Discord ログ（24h）を Notion Log Library DB に 1 ページで投下。Notion 未設定なら skip。
- まとめ資料も md でなく Log Library に集約する方針（AGENT/AGENTS.md「まとめ資料・ログは Notion Log Library へ」）。

### Wishlist 追加（オンデマンド）
- スクリプト: `scripts/integrations/notion/wishlist_add.py`
- Cron: なし（会話駆動。エージェントが「〇〇記録して」を受けたら CLI 実行）
- Env: `NOTION_TOKEN`, `NOTION_DB_WISHLIST`

---

## サンプルジョブ（実装例・コピペして使う）

新しいジョブを追加するときのパターン例。下のスクリプトは**未実装**なので、
必要になったら以下の流れで組み立てる:

1. `scripts/` に実スクリプトを Write
2. 下の crontab 行を `crontab -e` に追加（または `docs/cron.md` の heredoc パターンで一括登録）
3. 手動で1回叩いて成功確認
4. このファイルの「コアジョブ」節に1行足す

### [SAMPLE] 朝のダイジェスト
- script: `scripts/morning_digest.py`（未実装・例として）
- crontab: `0 8 * * 1-5 /usr/bin/python3 /home/YOUR_USER/secretary/scripts/morning_digest.py >> /tmp/morning_digest.log 2>&1`
- 動作: 平日 08:00 に「天気 + 今日のタスク一覧」をまとめて `DISCORD_CHANNEL_RANDOM` に投稿
- 追加時に秘書がやること:
  (1) `scripts/morning_digest.py` を Write（weather API + `scripts/lib/task_store.py` から未完了タスク取得）
  (2) `crontab -l` に1行追加
  (3) 動作確認のため手動で1回実行

### [SAMPLE] 週次振り返りテンプレ
- script: `scripts/weekly_review.py`（未実装・例として）
- crontab: `0 10 * * MON /usr/bin/python3 /home/YOUR_USER/secretary/scripts/weekly_review.py >> /tmp/weekly_review.log 2>&1`
- 動作: 毎週月曜 10:00 に「先週やったこと/今週やること」テンプレを自分用チャンネルに投稿（空欄を返信で埋める運用）
- 追加時に秘書がやること:
  (1) `scripts/weekly_review.py` を Write（定型文を `discord_post.post` で送るだけ）
  (2) crontab 追加 (3) 初回手動実行でフォーマット確認

### [SAMPLE] 食事記録の自動追記
- script: `scripts/lib/meal_log.py`（未実装・例として）
- トリガー: cron ではなく**会話中のキーワード** — メッセージに「食事記録」が含まれたら `data/meals.md` に `YYYY-MM-DD HH:MM <本文>` を追記
- 実装: エージェントが会話ルールとして処理するパターン（cron不要）。`AGENT/AGENTS.md` に1行足すか、本スクリプトを webhook 経由で `/log_meal` エンドポイントから叩いてもよい
- 追加時に秘書がやること:
  (1) `scripts/lib/meal_log.py` を Write（`data/meals.md` に追記する関数）
  (2) 会話ルールを `AGENT/AGENTS.md` に追記、または `docs/webhook.md` を参照して `/log_meal` エンドポイントを追加

### [SAMPLE] タスク件数メトリクス記録
- script: `scripts/metrics_pending_tasks.py`（未実装・例として）
- crontab: `0 * * * * /usr/bin/python3 /home/YOUR_USER/secretary/scripts/metrics_pending_tasks.py >> /tmp/metrics_pending.log 2>&1`
- 動作: 毎時00分に `pending_tasks.json` の未完了件数を `scripts/lib/metrics_db.py` に記録（後で推移を可視化できる）
- 追加時に秘書がやること:
  (1) `scripts/metrics_pending_tasks.py` を Write（`track_metrics` デコレータ付き、`data/pending_tasks.json` の `done=False` を数える）
  (2) crontab 追加 (3) `python3 scripts/lib/metrics_db.py stats --hours 24` で翌日に蓄積を確認

---

## 自分のジョブを追加

以下のテーブル形式で追加してください:

| トリガー | スクリプト | 動作 |
|---------|--------|--------|
| `cron: 0 9 * * MON` | `scripts/weekly_news.py` | 週次ニュースを #random に投稿 |
| キーワード "log mood" | 会話 | `data/mood.md` に追記 |

追加方法:
1. **チャットで頼む**: 「X を Y の頻度でやるジョブを追加して」と言えば、
   秘書がスクリプトと crontab エントリを起こしてくれる。
2. **先にここに書く**: 秘書はこのファイルをジョブ仕様として読む。
3. **自分で書く**: `scripts/` にスクリプトを作って、`crontab -e` に
   エントリを追加し、上のテーブルに1行足す。
