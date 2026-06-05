"""秘書スクリプト用の共通ユーティリティライブラリ。

リポジトリ内のスクリプトからの典型的な使い方:

    import sys, os
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from scripts.lib import task_store, jst, discord_post

または個別に:

    from scripts.lib.task_store import load_tasks, update_tasks
    from scripts.lib.jst import JST, now_jst
"""

from __future__ import annotations

__all__ = [
    "task_store",
    "jst",
    "channels",
    "discord_post",
    "secrets",
    "state_store",
    "error_db",
    "metrics_db",
    "note_finder",
    "generate_notes_index",
    "brave_search",
]
