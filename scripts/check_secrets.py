#!/usr/bin/env python3
"""check_secrets.py — commit する差分にトークン/API キーが混入していないか検査。

公開リポジトリに push する前に、秘匿情報の漏洩を git pre-commit で止める。
他人が自分の GitHub に push する構成なので、.env や credentials.json の値を
うっかり commit する事故を防ぐ最後の砦。

使い方:
    python3 scripts/check_secrets.py            # staged 差分（git diff --cached）を検査
    python3 scripts/check_secrets.py --all      # tracked ファイル全体を検査

検出したら exit 2（pre-commit から呼べば commit がブロックされる）。
git pre-commit フックとして有効化する手順は SETUP.md / docs/ops.md 参照。
"""

from __future__ import annotations

import re
import subprocess
import sys

SECRET_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("Google OAuth client_secret", re.compile(r"GOCSPX-[a-zA-Z0-9_-]{20,}")),
    ("Google access token (ya29.xxx)", re.compile(r"ya29\.[a-zA-Z0-9_-]{30,}")),
    ("Google refresh token", re.compile(r"\"1//[a-zA-Z0-9_-]{40,}\"")),
    ("GitHub PAT (ghp_)", re.compile(r"ghp_[a-zA-Z0-9]{20,}")),
    ("GitHub PAT (github_pat_)", re.compile(r"github_pat_[a-zA-Z0-9_]{20,}")),
    ("Slack token", re.compile(r"xox[bporas]-[a-zA-Z0-9-]{20,}")),
    ("OpenAI API key", re.compile(r"sk-[a-zA-Z0-9]{30,}")),
    ("Anthropic API key", re.compile(r"sk-ant-[a-zA-Z0-9_-]{20,}")),
    ("Notion API key", re.compile(r"ntn_[a-zA-Z0-9]{20,}")),
    ("Brave Search API key", re.compile(r"BSA[a-zA-Z0-9_-]{20,}")),
    ("AWS Access Key", re.compile(r"AKIA[0-9A-Z]{16}")),
    ("Discord bot token", re.compile(r"[MN][\w-]{23}\.[\w-]{6}\.[\w-]{27,}")),
]

# プレースホルダ等は除外（誤検知防止）
EXCLUDE_SUBSTRINGS = (
    "your_", "YOUR_", "placeholder", "example", "REDACTED", "xxxxxx", "<insert", "paste_",
)
# 検出パターン定義を含むファイルは除外（自己検知防止）
EXCLUDE_FILES = (
    ".env.template",
    "scripts/check_secrets.py",
    "scripts/lib/secret_redact.py",
)


def _excluded_file(path: str) -> bool:
    return any(path.endswith(f) for f in EXCLUDE_FILES)


def _excluded_line(line: str) -> bool:
    return any(s in line for s in EXCLUDE_SUBSTRINGS)


def _run(args: list[str]) -> str:
    try:
        return subprocess.run(args, capture_output=True, text=True, timeout=30).stdout
    except Exception:
        return ""


def scan_staged() -> list[tuple[str, str, str]]:
    diff = _run(["git", "diff", "--cached", "--no-color"])
    findings: list[tuple[str, str, str]] = []
    current = ""
    for line in diff.split("\n"):
        if line.startswith("+++ b/"):
            current = line[6:]
            continue
        if line.startswith("+") and not line.startswith("+++"):
            if _excluded_file(current) or _excluded_line(line):
                continue
            for name, pat in SECRET_PATTERNS:
                if pat.search(line):
                    findings.append((name, current, line.strip()[:200]))
                    break
    return findings


def scan_all() -> list[tuple[str, str, str]]:
    files = [f for f in _run(["git", "ls-files"]).splitlines() if f and not _excluded_file(f)]
    findings: list[tuple[str, str, str]] = []
    for f in files:
        try:
            with open(f, encoding="utf-8", errors="ignore") as fh:
                for line in fh:
                    if _excluded_line(line):
                        continue
                    for name, pat in SECRET_PATTERNS:
                        if pat.search(line):
                            findings.append((name, f, line.strip()[:200]))
                            break
        except OSError:
            continue
    return findings


def main() -> int:
    findings = scan_all() if "--all" in sys.argv else scan_staged()
    if not findings:
        return 0
    out = ["🚨 秘匿情報の混入を検出しました（commit をブロック）:", ""]
    for name, path, line in findings[:5]:
        out.append(f"  - [{name}] {path}")
        out.append(f"    {line}")
    if len(findings) > 5:
        out.append(f"  ... 他 {len(findings) - 5} 件")
    out += [
        "",
        "誤検知なら check_secrets.py の EXCLUDE_SUBSTRINGS / EXCLUDE_FILES に追加。",
        "本物の漏洩なら .gitignore に追加 → git rm --cached <file> してから commit し直し。",
    ]
    print("\n".join(out), file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
