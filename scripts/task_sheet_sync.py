#!/usr/bin/env python3
"""data/pending_tasks.json <-> Google Sheets を同期する。

用途: Sheets のモバイルアプリからタスクを閲覧・編集できるようにする。
ローカル JSON が正。定期実行は `push`、`pull` は「シートを編集したから戻す」
時の手動操作として使う。

## セットアップ

1. OAuth トークンに `spreadsheets` スコープが入っていることを確認。
   そのスコープが追加される前に認可済みなら再認可:

       python3 integrations/google/reauth.py

2. 空の Google Sheet を作成。URL から ID をコピー:

       https://docs.google.com/spreadsheets/d/<SHEET_ID>/edit

3. .env に ID を追加:

       TASK_SHEET_ID=<SHEET_ID>

4. 初回同期（ヘッダ + 現在のタスクをシートに書き込む）:

       python3 scripts/task_sheet_sync.py push

5. （オプション）cron で定期実行 — このファイル末尾を参照。

## レイアウト

1行目はヘッダ:

    section | title | done | created_at | completed_at | remind_at

`done` は TRUE/FALSE で保存。

## コマンド

    push    data/pending_tasks.json を読んでシートを上書き
    pull    シートを読んで data/pending_tasks.json を上書き

## 環境変数

    TASK_SHEET_ID       Google Sheet ID（必須 — 未設定ならスクリプトは exit 0）
    GOOGLE_TOKEN_PATH   OAuth トークンのパス（デフォルト: integrations/google/token.json）
"""

from __future__ import annotations

import argparse
import os
import sys
from typing import Any

# スクリプトとして実行したときに `from scripts.lib...` でインポートできるようにする
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv  # noqa: E402

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(_REPO_ROOT, ".env"))

from scripts.lib.task_store import load_tasks, update_tasks  # noqa: E402

HEADERS = ["section", "title", "done", "created_at", "completed_at", "remind_at"]
SHEET_RANGE = "A1"


def _client() -> Any:
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build

    token_path = os.path.expanduser(
        os.getenv(
            "GOOGLE_TOKEN_PATH",
            os.path.join(_REPO_ROOT, "integrations/google/token.json"),
        )
    )
    if not os.path.exists(token_path):
        raise SystemExit(
            f"token not found: {token_path}\n"
            "run: python3 integrations/google/reauth.py"
        )
    creds = Credentials.from_authorized_user_file(token_path)
    return build("sheets", "v4", credentials=creds, cache_discovery=False)


def _sheet_id() -> str | None:
    sid = os.getenv("TASK_SHEET_ID", "").strip()
    return sid or None


def _tasks_to_rows(data: dict) -> list[list[Any]]:
    rows: list[list[Any]] = [list(HEADERS)]
    for section, tasks in data.items():
        if not isinstance(tasks, list):
            continue
        for t in tasks:
            if not isinstance(t, dict):
                continue
            rows.append(
                [
                    section,
                    t.get("title", ""),
                    bool(t.get("done", False)),
                    t.get("created_at", ""),
                    t.get("completed_at", ""),
                    t.get("remind_at", ""),
                ]
            )
    return rows


def _rows_to_tasks(rows: list[list[Any]]) -> dict:
    data: dict[str, list[dict]] = {}
    if not rows:
        return {"primary": []}

    # ヘッダ行を探す（大文字小文字は無視）、見つからなければ行0をデータ扱い
    header = [str(c).strip().lower() for c in rows[0]]
    if "section" not in header or "title" not in header:
        # ヘッダなし — シート全体をデフォルトレイアウトのデータとみなす
        header = list(HEADERS)
        body = rows
    else:
        body = rows[1:]

    idx = {name: header.index(name) for name in HEADERS if name in header}

    def cell(row: list[Any], name: str) -> str:
        i = idx.get(name)
        if i is None or i >= len(row):
            return ""
        v = row[i]
        return "" if v is None else str(v).strip()

    for row in body:
        if not row:
            continue
        section = cell(row, "section") or "primary"
        title = cell(row, "title")
        if not title:
            continue
        done_raw = cell(row, "done").lower()
        entry: dict[str, Any] = {
            "title": title,
            "done": done_raw in {"true", "1", "yes", "y", "x"},
        }
        for key in ("created_at", "completed_at", "remind_at"):
            v = cell(row, key)
            if v:
                entry[key] = v
        data.setdefault(section, []).append(entry)

    data.setdefault("primary", [])
    return data


def push() -> None:
    sheet_id = _sheet_id()
    if not sheet_id:
        print("TASK_SHEET_ID is not set. See docs/optional/tasks-sheet.md")
        return

    svc = _client()
    data = load_tasks()
    rows = _tasks_to_rows(data)

    # クリアしてから書き込む（タスクが減ったときに古い行を消すため）
    svc.spreadsheets().values().clear(
        spreadsheetId=sheet_id, range="A:Z"
    ).execute()
    svc.spreadsheets().values().update(
        spreadsheetId=sheet_id,
        range=SHEET_RANGE,
        valueInputOption="RAW",
        body={"values": rows},
    ).execute()
    print(f"pushed {len(rows) - 1} tasks to sheet {sheet_id}")


def pull() -> None:
    sheet_id = _sheet_id()
    if not sheet_id:
        print("TASK_SHEET_ID is not set. See docs/optional/tasks-sheet.md")
        return

    svc = _client()
    resp = (
        svc.spreadsheets()
        .values()
        .get(spreadsheetId=sheet_id, range="A:Z")
        .execute()
    )
    rows = resp.get("values", [])
    new_data = _rows_to_tasks(rows)

    with update_tasks() as data:
        data.clear()
        data.update(new_data)

    total = sum(len(v) for v in new_data.values() if isinstance(v, list))
    print(f"pulled {total} tasks from sheet {sheet_id}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["push", "pull"])
    args = ap.parse_args()

    if args.cmd == "push":
        push()
    else:
        pull()
    return 0


if __name__ == "__main__":
    sys.exit(main())


# cron の例（15分おき）:
# */15 * * * * cd /path/to/repo && /usr/bin/python3 scripts/task_sheet_sync.py push >> /tmp/task_sheet.log 2>&1
