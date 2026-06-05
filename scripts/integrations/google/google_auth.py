#!/usr/bin/env python3
"""google_auth.py — Google API の OAuth 認証ヘルパー (GPT版秘書 共通)。

codex (脳) が直接トークン文字列を触らずに済むよう、認証は本ヘルパーに閉じる。
トークンは repo 外の secret パスに置く (codex レビュー: token を repo に置かない)。

環境変数:
    GOOGLE_TOKEN_PATH       OAuth ユーザートークン JSON のパス
                            (既定: ~/.codex/secrets/google_token.json)
    GOOGLE_CREDENTIALS_PATH OAuth クライアントシークレット JSON のパス
                            (初回認可時のみ必要。既定: 同 dir の credentials.json)

スコープは用途最小限。必要に応じて足す。
セットアップ手順は docs/google_setup.md を参照。
"""
from __future__ import annotations

import os
from pathlib import Path

# 必要最小スコープ。Drive を使うなら drive.readonly 等を足す。
SCOPES = [
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/gmail.modify",
]

SECRET_DIR = Path(os.environ.get("GOOGLE_SECRET_DIR", os.path.expanduser("~/.codex/secrets")))
TOKEN_PATH = Path(os.environ.get("GOOGLE_TOKEN_PATH", str(SECRET_DIR / "google_token.json")))
CREDENTIALS_PATH = Path(os.environ.get("GOOGLE_CREDENTIALS_PATH", str(SECRET_DIR / "credentials.json")))


def get_credentials():
    """保存済みトークンを読み、期限切れなら refresh。無ければ初回認可フローを促す。"""
    try:
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request
    except ImportError as e:
        raise RuntimeError(
            "google-auth 系が未インストール。`pip install -r requirements.txt` を実行"
        ) from e

    creds = None
    if TOKEN_PATH.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)

    if creds and creds.valid:
        return creds

    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
        _save(creds)
        return creds

    # 未認可: 初回のみブラウザ認可フロー (人間が一度だけ実行する)
    if not CREDENTIALS_PATH.exists():
        raise RuntimeError(
            f"トークンが無く、クライアントシークレットも見つからない: {CREDENTIALS_PATH}\n"
            "docs/google_setup.md に従って OAuth クライアントを作成し credentials.json を配置"
        )
    from google_auth_oauthlib.flow import InstalledAppFlow

    flow = InstalledAppFlow.from_client_secrets_file(str(CREDENTIALS_PATH), SCOPES)
    creds = flow.run_local_server(port=0)
    _save(creds)
    return creds


def _save(creds) -> None:
    SECRET_DIR.mkdir(parents=True, exist_ok=True)
    TOKEN_PATH.write_text(creds.to_json())
    try:
        os.chmod(TOKEN_PATH, 0o600)
    except OSError:
        pass


def service(api: str, version: str):
    """認証済み Google API サービスクライアントを返す。"""
    from googleapiclient.discovery import build

    return build(api, version, credentials=get_credentials(), cache_discovery=False)


if __name__ == "__main__":
    # 初回認可 / 疎通確認用: python3 google_auth.py
    try:
        get_credentials()
        print(f"OK: トークン有効 ({TOKEN_PATH})")
    except Exception as e:
        print(f"NG: {e}")
        raise SystemExit(1)
