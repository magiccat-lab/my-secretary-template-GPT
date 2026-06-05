# Google 連携セットアップ (GPT版秘書)

Claude 版は claude.ai のホスト Google コネクタを使うが、codex (GPT) では使えない。
代わりに **OAuth トークンで叩く薄い Python CLI** を秘書に使わせる
(`scripts/integrations/google/`)。操作を限定でき、権限が明確で安全。

## 1. Google Cloud で OAuth クライアントを作る

1. [Google Cloud Console](https://console.cloud.google.com/) でプロジェクト作成
2. 「API とサービス」→ 有効化: **Google Calendar API**、**Gmail API** (必要なら Drive)
3. 「OAuth 同意画面」を設定 (テスト ユーザーに自分のアドレスを追加)
4. 「認証情報」→「OAuth クライアント ID」→ アプリの種類: **デスクトップ アプリ**
5. JSON をダウンロード

## 2. シークレットを配置 (repo 外)

```bash
mkdir -p ~/.codex/secrets && chmod 700 ~/.codex/secrets
mv ~/Downloads/client_secret_*.json ~/.codex/secrets/credentials.json
```

> token / credentials は **repo に置かない**。`~/.codex/secrets/` に隔離する。
> パスを変える場合は `GOOGLE_SECRET_DIR` / `GOOGLE_TOKEN_PATH` / `GOOGLE_CREDENTIALS_PATH`
> で上書き可能。

## 3. 初回認可 (人間が一度だけ実行)

```bash
pip install -r requirements.txt
python3 scripts/integrations/google/google_auth.py
# ブラウザが開く → 自分の Google アカウントで許可 → google_token.json が保存される
```

`OK: トークン有効` が出れば成功。以降は refresh token で自動更新される。

## 4. 動作確認

```bash
python3 scripts/integrations/google/gcal_cli.py list --days 7
python3 scripts/integrations/google/gmail_cli.py list --query "is:unread" --max 5
```

## 5. 送信の安全弁 (Gmail)

`gmail_cli.py send` は二重ガード:
- `GMAIL_ALLOWLIST` (カンマ区切り) に含まれる宛先のみ許可。未設定なら全送信拒否
- `--yes` が無ければ dry-run

```bash
export GMAIL_ALLOWLIST="boss@example.com,self@example.com"
# dry-run (送らない)
python3 scripts/integrations/google/gmail_cli.py send --to boss@example.com --subject "test" --body "hi"
# 実送信
python3 scripts/integrations/google/gmail_cli.py send --to boss@example.com --subject "test" --body "hi" --yes
```

## 6. codex の sandbox 設定

`codex exec` 内からこれらを叩くには、ネットワークと token 書き込み (refresh) が要る:
- `~/.codex/config.toml` で `sandbox_mode = "workspace-write"` + `network_access = true`
- token は `~/.codex/secrets/` (workspace 外) に置くので、refresh 書き込み先が
  writable root に含まれるよう `--add-dir ~/.codex/secrets` を起動側に足すか、
  token パスを workspace 配下の gitignore 済 dir にする

## スコープを増やすには

`scripts/integrations/google/google_auth.py` の `SCOPES` に追記し、`google_token.json`
を一度削除してから手順 3 を再実行 (再認可)。
