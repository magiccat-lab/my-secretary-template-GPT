#!/usr/bin/env python3
"""data/notes/README.md のカテゴリインデックスを自動生成する。

使い方:
    python3 scripts/lib/generate_notes_index.py           # 書き込み
    python3 scripts/lib/generate_notes_index.py --check   # 差分チェック（CI 向け）
    python3 scripts/lib/generate_notes_index.py --dry     # 新しい中身を表示

README には以下のマーカーが必要:
    <!-- NOTES-INDEX-AUTO-BEGIN -->
    ...自動生成される...
    <!-- NOTES-INDEX-AUTO-END -->

説明文の抽出の優先順位:
1. 最初の20行にある `> reference: xxx` 行
2. H1 配下の最初の非空段落（frontmatter の後）
3. 空
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

NOTES_DIR = Path(os.environ.get("NOTES_DIR", os.path.expanduser("~/secretary/data/notes")))
README = NOTES_DIR / "README.md"

MARKER_BEGIN = "<!-- NOTES-INDEX-AUTO-BEGIN -->"
MARKER_END = "<!-- NOTES-INDEX-AUTO-END -->"

# デフォルトのカテゴリ。必要なサブディレクトリをここに追加。
CATEGORIES = {
    "tech": "tech/ — 技術メモ",
    "work": "work/ — 仕事 / プロジェクト",
    "hobby": "hobby/ — 趣味 / 娯楽",
    "reading": "reading/ — 読書メモ",
}


def _extract_description(content: str) -> str:
    lines = content.split("\n")

    for line in lines[:20]:
        stripped = line.strip()
        if stripped.startswith("> reference:") or stripped.startswith("> ref:"):
            return stripped.lstrip("> ").split(":", 1)[1].strip()

    in_fm = False
    past_title = False
    for line in lines[:40]:
        stripped = line.strip()
        if stripped == "---":
            in_fm = not in_fm
            continue
        if in_fm:
            continue
        if not stripped:
            continue
        if stripped.startswith("# "):
            past_title = True
            continue
        if past_title:
            if stripped.startswith("#"):
                continue
            if stripped.startswith(">"):
                return stripped.lstrip("> ").strip()[:100]
            return stripped[:100]

    return ""


def _escape_md_table(s: str) -> str:
    return s.replace("|", "\\|").replace("\n", " ").strip()


def gen_index() -> str:
    sections = []
    for cat_key, cat_label in CATEGORIES.items():
        cat_dir = NOTES_DIR / cat_key
        if not cat_dir.exists():
            continue
        mds = sorted(cat_dir.glob("*.md"))
        if not mds:
            continue

        lines = [f"## {cat_label}", "", "| file | 説明 |", "|------|------|"]
        for md in mds:
            try:
                content = md.read_text(encoding="utf-8")
            except OSError:
                continue
            desc = _escape_md_table(_extract_description(content))
            relpath = md.relative_to(NOTES_DIR)
            lines.append(f"| [{md.name}]({relpath}) | {desc} |")
        lines.append("")
        sections.append("\n".join(lines))

    return "\n\n".join(sections)


def rebuild(content: str) -> str:
    if MARKER_BEGIN not in content or MARKER_END not in content:
        return content.rstrip() + f"\n\n{MARKER_BEGIN}\n\n{gen_index()}\n\n{MARKER_END}\n"

    pattern = re.compile(
        re.escape(MARKER_BEGIN) + r".*?" + re.escape(MARKER_END),
        re.DOTALL,
    )
    return pattern.sub(f"{MARKER_BEGIN}\n\n{gen_index()}\n\n{MARKER_END}", content)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--dry", action="store_true")
    args = parser.parse_args()

    if not README.exists():
        print(f"README が見つかりません: {README}", file=sys.stderr)
        return 2

    current = README.read_text(encoding="utf-8")
    new_content = rebuild(current)

    if args.dry:
        sys.stdout.write(new_content)
        return 0

    if args.check:
        if new_content == current:
            print("変更なし")
            return 0
        print("notes インデックスに差分あり — --check を外して再実行してください")
        return 1

    if new_content == current:
        print("変更なし")
        return 0

    README.write_text(new_content, encoding="utf-8")
    print(f"更新: {README}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
