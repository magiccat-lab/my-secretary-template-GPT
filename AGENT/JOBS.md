# JOBS.md — 定期実行ジョブ

秘書に「いつ何をさせるか」を記述するファイル。1ジョブ1行にまとめて、
詳細はスクリプトやスキルファイルに寄せるのが推奨。

## タイムゾーンのルール

ここに書く時刻はすべて JST（Asia/Tokyo）。`cron` や `at` も JST で指定。
詳細は `docs/cron.md` 参照。

---

## コアジョブ（テンプレートに同梱）

### 死活・固着 watchdog（必須）
- スクリプト: `scripts/session_watchdog.py`
- Cron: `*/2 * * * *`（2 分おき）
- 脳(worker)が書く heartbeat（`data/codex_worker_state.json`）の鮮度を見て、
  落ちた / 固まった（`status=running` のまま長時間 / 未処理 backlog があるのに無更新）
  を検出し `start_server.sh` で自動再起動。`WATCHDOG_NOTIFY_CHANNEL` に通知先 ch_id。
- Claude 版のような screen hardcopy 監視ではなく heartbeat ベース（TUI 非依存で堅い）。

### 定期セッションリセット（推奨）
- Cron: `0 4 * * *`（毎日 04:00。週1なら `10 4 * * 0`）
- `/tmp/codex_secretary_session.txt` を消して `start_server.sh` で fresh 起動。
  `codex exec resume` の文脈肥大を防ぐ。codex は job 駆動なので Claude 版ほど常駐
  コンテキストは溜まらず、無くても可。

### Discord ログ → Notion Log Library
- スクリプト: `scripts/integrations/notion/discord_log_to_library.py`
- Cron: `50 23 * * *`
- その日の Discord ログを Notion に送る（Notion 未設定なら自動 skip）。

### Notion タスク同期（任意）
- スクリプト: `scripts/integrations/notion/sync_pending_to_notion.py`
- Cron: `*/5 * * * *`（`NOTION_TOKEN` / `NOTION_DB_TASKS` 設定時）
- `data/pending_tasks.json` と Notion Tasks DB を同期。

---

## オプションのインテグレーション

`.env` で有効化し、cron の行をコメントアウトから戻す。

### Google Calendar / Gmail（薄い CLI、pull 型）
- スクリプト: `scripts/integrations/google/gcal_cli.py` / `gmail_cli.py`
- トリガー: cron ではなく**会話駆動**。秘書が必要時に bash で叩く（予定確認・メール確認・送信）
- Env: `GCAL_CALENDAR_ID`, `GMAIL_ALLOWLIST`（送信許可宛先）。認証は `google_auth.py`
- 定期通知が欲しければ cron 化も可（例: 毎朝 `gcal_cli.py list` の結果を discord_send で投げる
  ジョブを下の「サンプル」要領で作る）。セットアップは `docs/google_setup.md`。
- ⚠️ Claude 版の常駐 Gmail モニター / 予定リマインド daemon は GPT 版には未同梱
  （pull 型の CLI に置き換え）。daemon が要るなら同様に自作する。

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
- まとめ資料も md でなく Log Library に集約する方針（AGENTS.md「まとめ資料・ログは Notion Log Library へ」）。

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
- 実装: エージェントが会話ルールとして処理するパターン（cron不要）。`AGENTS.md` に1行足すか、本スクリプトを webhook 経由で `/log_meal` エンドポイントから叩いてもよい
- 追加時に秘書がやること:
  (1) `scripts/lib/meal_log.py` を Write（`data/meals.md` に追記する関数）
  (2) 会話ルールを `AGENTS.md` に追記、または `scripts/webhook_server.py` にエンドポイント `/log_meal` を追加

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
