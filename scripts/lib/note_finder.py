"""data/notes/ 用の全文検索ヘルパー。

使い方（CLI）:
    python3 scripts/lib/note_finder.py "keyword1 keyword2"
    python3 scripts/lib/note_finder.py --top 10 --recency "topic"

使い方（Python）:
    from scripts.lib.note_finder import find
    hits = find("keyword")   # [(path, score, title, preview), ...]

ランキング:
  - ファイル名ヒット: キーワードごと +5
  - H1/H2 見出しヒット: マッチごと +3
  - 本文ヒット: マッチごと +1 × 長さ正規化（log）
  - 全キーワードがヒット: 1.5 倍ボーナス
  - 直近更新（3ヶ月以内）: 1.15 倍（--recency で 1.30 倍）
"""

from __future__ import annotations

import argparse
import math
import os
import re
import time
from pathlib import Path

NOTES_DIR = Path(os.environ.get("NOTES_DIR", os.path.expanduser("~/secretary/data/notes")))
_LENGTH_NORM_BASE = 2000


def _extract_title(content: str) -> str:
    for line in content.split("\n")[:20]:
        if line.startswith("# "):
            return line[2:].strip()
    return ""


def _preview(content: str, max_chars: int = 120) -> str:
    lines = content.split("\n")
    skipped_title = False
    for line in lines[:30]:
        line = line.strip()
        if not line:
            continue
        if not skipped_title and line.startswith("# "):
            skipped_title = True
            continue
        if line.startswith("#") or line.startswith("---"):
            continue
        return line[:max_chars]
    return ""


def _length_factor(content_length: int) -> float:
    if content_length <= _LENGTH_NORM_BASE:
        return 1.0
    return 1.0 / (1.0 + math.log(content_length / _LENGTH_NORM_BASE))


def _recency_factor(mtime_epoch: float, recency_boost: float = 0.15, strong: bool = False) -> float:
    age_days = (time.time() - mtime_epoch) / 86400
    boost = recency_boost * (2.0 if strong else 1.0)
    if age_days < 90:
        return 1.0 + boost
    if age_days < 180:
        return 1.0 + boost * 0.33
    return 1.0


def find(
    query: str,
    top: int = 5,
    notes_dir: Path = NOTES_DIR,
    *,
    recency_strong: bool = False,
    include_explain: bool = False,
) -> list[tuple[str, int, str, str]]:
    keywords = [k.strip().lower() for k in re.split(r"[\s\u3000]+", query) if k.strip()]
    if not keywords:
        return []

    results: list[tuple[str, int, str, str]] = []

    if not notes_dir.exists():
        return []

    for md in notes_dir.rglob("*.md"):
        if md.name == "README.md":
            continue
        try:
            content = md.read_text(encoding="utf-8")
        except OSError:
            continue

        content_lower = content.lower()
        name_lower = md.stem.lower()
        length_factor = _length_factor(len(content))

        score = 0.0
        hits_found = 0
        explain_bits: list[str] = []
        for kw in keywords:
            name_hits = name_lower.count(kw)
            headline_hits = sum(
                1
                for line in content.split("\n")[:80]
                if line.startswith("#") and kw in line.lower()
            )
            body_hits = content_lower.count(kw)

            kw_score = name_hits * 5.0 + headline_hits * 3.0 + body_hits * 1.0 * length_factor
            if kw_score > 0:
                score += kw_score
                hits_found += 1
                if include_explain:
                    explain_bits.append(
                        f"{kw}: name={name_hits}x5 head={headline_hits}x3 "
                        f"body={body_hits}x{length_factor:.2f}"
                    )

        if score == 0:
            continue

        if hits_found == len(keywords) and len(keywords) > 1:
            score *= 1.5

        try:
            mtime = md.stat().st_mtime
            score *= _recency_factor(mtime, strong=recency_strong)
        except OSError:
            pass

        try:
            rel_path = str(md.relative_to(notes_dir.parent.parent))
        except ValueError:
            rel_path = str(md)
        title = _extract_title(content) or md.stem
        preview = _preview(content)
        if include_explain and explain_bits:
            preview = preview + f" | score: {' / '.join(explain_bits)}"
        results.append((rel_path, int(round(score)), title, preview))

    results.sort(key=lambda x: -x[1])
    return results[:top]


def format_results(hits: list[tuple[str, int, str, str]]) -> str:
    if not hits:
        return "関連 note なし"
    lines = [f"## 関連 note (上位 {len(hits)} 件)", ""]
    for rel_path, score, title, preview in hits:
        lines.append(f"**{title}** (score={score})")
        lines.append(f"  `{rel_path}`")
        if preview:
            lines.append(f"  > {preview}")
        lines.append("")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("query", nargs="*")
    parser.add_argument("--query", "-q", dest="q")
    parser.add_argument("--top", "-n", type=int, default=5)
    parser.add_argument("--raw", action="store_true")
    parser.add_argument("--recency", action="store_true")
    parser.add_argument("--explain", action="store_true")
    args = parser.parse_args()

    q = args.q or " ".join(args.query)
    if not q:
        parser.error("キーワードを指定してください")

    hits = find(
        q,
        top=args.top,
        recency_strong=args.recency,
        include_explain=args.explain,
    )
    if args.raw:
        for path, _, _, _ in hits:
            print(path)
    else:
        print(format_results(hits))


if __name__ == "__main__":
    main()
