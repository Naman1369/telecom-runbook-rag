"""Text extraction clean-up: strip boilerplate, normalise whitespace and encoding."""

from __future__ import annotations

import re
import unicodedata

# Lines that are navigation/legal chrome rather than documentation content.
BOILERPLATE_PATTERNS = [
    re.compile(p, re.IGNORECASE)
    for p in (
        r"^(home\s*\|.*)$",
        r"^.*\b(cookie settings|sign in|log in)\b.*$",
        r"^.*\b(privacy|terms)\s*\|.*$",
        r"^©.*$",
        r"^page \d+ of \d+$",
        r"^(back to top|table of contents|print this page)$",
    )
]

# ASCII control characters (except \t and \n), zero-width space and byte-order mark.
_CONTROL_CHARS = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f\x7f\u200b\ufeff]")
# Runs of spaces, tabs and non-breaking spaces.
_MULTI_SPACE = re.compile("[ \t\u00a0]{2,}")


def is_boilerplate(line: str) -> bool:
    stripped = line.strip()
    return bool(stripped) and any(p.match(stripped) for p in BOILERPLATE_PATTERNS)


def clean_text(text: str) -> str:
    """Normalise text while keeping the line count unchanged, so chunk line numbers still
    point at the right lines in the source file. Boilerplate lines become blank lines."""
    text = unicodedata.normalize("NFC", text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = _CONTROL_CHARS.sub("", text)

    lines = []
    fence = None
    for line in text.split("\n"):
        marker = re.match(r"^ {0,3}(`{3,}|~{3,})(.*)$", line)
        if fence is not None:
            lines.append(line)
            if (marker and marker[1][0] == fence[0] and len(marker[1]) >= len(fence)
                    and not marker[2].strip()):
                fence = None
            continue
        if marker and (marker[1][0] != "`" or "`" not in marker[2]):
            fence = marker[1]
            lines.append(line)
            continue
        if is_boilerplate(line):
            lines.append("")
            continue
        # Keep leading indentation (code / command blocks) but squash runs of inner spaces.
        indent = len(line) - len(line.lstrip(" "))
        body = _MULTI_SPACE.sub(" ", line.strip())
        lines.append((" " * indent + body) if body else "")
    return "\n".join(lines)
