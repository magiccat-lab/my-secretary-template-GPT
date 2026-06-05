"""シークレット redaction helper

ログ出力・エラー記録前にトークン / API キー / password を伏せ字化して機密漏洩を防ぐ。
webhook_server.py や cron スクリプトの stderr キャプチャ時に通すと安全。
"""

import re

_PATTERNS = [
    (re.compile(r"sk-ant-[\w\-]+"), "sk-ant-****"),
    (re.compile(r"sk-[a-zA-Z0-9]{20,}"), "sk-****"),
    (re.compile(r"Bearer\s+[\w\-_=\.]+", re.IGNORECASE), "Bearer ****"),
    (
        re.compile(
            r"(api[_-]?key|bearer[_-]?token|secret[_-]?key|access[_-]?token|token|secret|password)[=:\"]{1,3}\s*[\w\-_=\.]+",
            re.IGNORECASE,
        ),
        r"\1=****",
    ),
    (re.compile(r"AKIA[0-9A-Z]{16}"), "AKIA****"),
    (re.compile(r"ghp_[\w]+"), "ghp_****"),
    (re.compile(r"github_pat_[\w]+"), "github_pat_****"),
    (re.compile(r"xox[baprs]-[\w\-]+"), "xox****"),
    (re.compile(r"ya29\.[\w\-]+"), "ya29.****"),  # Google OAuth access token
    (re.compile(r"AIza[0-9A-Za-z\-_]{35}"), "AIza****"),  # Google API key
    (re.compile(r"ntn_[a-zA-Z0-9]{20,}"), "ntn_****"),  # Notion API key
    (re.compile(r"GOCSPX-[a-zA-Z0-9_-]{20,}"), "GOCSPX-****"),  # Google OAuth client secret
]


def redact(text: str | None) -> str:
    """テキストから既知の機密パターンを伏せ字化して返す"""
    if not text:
        return text or ""
    for pattern, repl in _PATTERNS:
        text = pattern.sub(repl, text)
    return text
