# docs/INDEX.md — ドキュメント索引（GPT版）

具体的なセットアップ・運用タスクが来たら、下の表から該当ファイルを Read して参照する。

> 人間向けの**初回セットアップ手順**はリポジトリ直下の `SETUP.md` が正
> （clone 直後〜Discord で会話できるまで）。本 `docs/` 以下は運用リファレンス。

## ルーティング表

| ユーザーが言いそうなこと | 読むファイル |
|---|---|
| 「cron追加して」「毎朝〇時にX」「定期実行」「時刻ずれてる」 | `docs/cron.md` |
| 「bot落ちた」「死活監視」「再起動」「ログ見たい」「何か壊れた」 | `docs/ops.md` |
| 「Googleカレンダー繋ぎたい」「Gmail監視」「OAuth通らない」 | `docs/google_setup.md` |
| 「Notion と繋ぎたい」「タスク Notion で見たい」「Wishlist 追加」 | `docs/notion.md` |
| 「キャラ作って」「口調決めたい」「IDENTITY埋め直して」 | `AGENT/IDENTITY.md` + `SETUP.md` §H |
| 「Discord bot作りたい」「チャンネルID」「返信こない」 | `SETUP.md` §D / §E / §I + `docs/ops.md` |
| 「脳をGPT/Claudeどっちで動かす」「codex設定」「MCP追加」 | `SETUP.md` §B + `config.codex.toml.template` |

## 既存ジョブ・追加するジョブ

cron で動いている定期ジョブ一覧・追加の流れは `AGENT/JOBS.md` / `docs/cron.md` を参照。
