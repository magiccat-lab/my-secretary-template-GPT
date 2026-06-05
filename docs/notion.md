# notion.md — Notion 連携

タスク（`pending_tasks.json`）と Wishlist を Notion DB に同期する仕組みの
リファレンス。初回セットアップは `SETUP.md` G2 を参照。

---

## 1. アーキテクチャ

```
[Discord で会話] → エージェント → pending_tasks.json (正)
                                          ↓ */5 分ごとに cron
                                  Notion Tasks DB（読み専用ミラー）
```

- **正は常にローカル `data/pending_tasks.json`**
- Notion は片方向ミラー。スマホから Notion で `Done` をチェックしてもローカルは
  上書きされない（運用次第で双方向化可能、後述 §6）
- Wishlist DB はその場で `wishlist_add.py` で追加するだけ。同期不要

---

## 2. 認証

- **Internal Integration Token**: `NOTION_TOKEN` (`secret_xxxx`)
- 各 DB ページで `Add connections` から Integration を許可しないと API が 403
  → `SETUP.md` G2-3 を参照

トークンの再発行が必要になったら:

1. https://www.notion.so/my-integrations
2. 該当 Integration → `Show` → `Show secret` で表示
3. 漏らした場合は `Regenerate secret` → 新トークンを `.env` に貼り直し

---

## 3. DB スキーマ（Tasks）

> 💡 SETUP.md G2 の手順で公開テンプレを **複製**すれば、この通りのスキーマが
> 設定済みの Tasks / Wishlist DB が手に入ります。手作業でプロパティを作る必要は
> ありません。以下は中身の参照用（自分で DB を作り直す場合のみ照合に使う）。

| プロパティ | 型 | 役割 |
|---|---|---|
| `Name` | title | タスクの本文 |
| `Done` | checkbox | 完了フラグ。ローカル `done` と同期 |
| `SourceKey` | rich_text | upsert 用ハッシュ（`title + created_at` の SHA1 短縮） |
| `Created` | date | 作成日 |
| `Completed` | date | 完了日 |
| `Remind` | date | リマインド日（指定がある場合）|
| `Detail` | rich_text | 詳細メモ |
| `Type` | select | `diary` / `weekly_review` 等の分類（任意）|

> ⚠️ プロパティ名は **大文字小文字含めて完全一致** が必要。打ち間違えると同期で
> `validation_error` が出ます。

---

## 4. 運用

### 4.1 通常運用

`*/5 * * * *` で `sync_pending_to_notion.py` が回っているだけ。
追加で何もしなくてよい。

### 4.2 手動同期（変更を即反映したいとき）

```bash
python3 ~/secretary/scripts/integrations/notion/sync_pending_to_notion.py
```

### 4.3 Wishlist 追加

エージェントがユーザーの「〇〇って店記録して」を受けたら CLI を叩く:

```bash
python3 ~/secretary/scripts/integrations/notion/wishlist_add.py \
  --name "店名 or アイテム名" \
  --category "飲食店" \
  --area "渋谷" \
  --source "https://example.com" \
  --memo "備考"
```

`--source` に URL を渡すと URL プロパティ、テキストを渡すと rich_text プロパティ
として保存されます。

---

## 5. トラブルシューティング

### 5.1 `failed=N` が出る

```bash
tail -n 100 /tmp/sync_notion.log
```

代表的なエラー:

| エラー | 原因 | 対処 |
|---|---|---|
| `401 Unauthorized` | `NOTION_TOKEN` 未設定 or 失効 | `.env` 再確認、Integration を再発行 |
| `404 object_not_found` | `NOTION_DB_TASKS` の DB ID が間違い | URL から再取得（`SETUP.md` G2-4） |
| `validation_error` | プロパティ名 / 型が DB と不一致 | DB スキーマ §3 と照合 |
| `restricted_resource` | DB に Integration を許可してない | `Add connections` し直す |
| `rate_limited` | 短時間に叩きすぎ | スクリプト内 `time.sleep(0.4)` を増やす |

### 5.2 Notion 側で `Done` を入れたのにローカルに反映されない

これは仕様。本テンプレートの同期は **片方向（ローカル → Notion のみ）**。
双方向にしたい場合は §6 参照。

ローカル側で消したいなら Discord で「N番完了」と番号で言う運用が一番安全。

### 5.3 DB に同じタスクが 2 つ以上できた

`SourceKey` が空 or 古い形式のページが混ざっている可能性。

```bash
# Notion 上で重複ページを手動 archive、ローカル側で remove するなら
python3 ~/secretary/scripts/integrations/notion/sync_pending_to_notion.py
```

を再実行すると最新の `SourceKey` で upsert され直します。

---

## 6. 双方向同期にしたいとき

「Notion で `Done` をチェックしたらローカルも完了に倒す」運用にしたい場合は、
逆方向の同期スクリプトを別途書きます（テンプレ未同梱）:

```python
# scripts/integrations/notion/sync_notion_to_pending.py（実装例）
# 1. NOTION_DB_TASKS を query して全 page を取得
# 2. SourceKey でローカル task と突き合わせ
# 3. Notion 側 Done=true なら local task["done"] = True に更新
# 4. lib.task_store.update_tasks() で書き戻し
```

cron 例:

```
*/10 * * * * /usr/bin/python3 ~/secretary/scripts/integrations/notion/sync_notion_to_pending.py >> /tmp/sync_notion_to_pending.log 2>&1
```

ローカル → Notion sync と **5 分ずつ時刻ずらして** cron に並べると、書き合いに
なるリスクが減ります。
