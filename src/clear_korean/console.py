from __future__ import annotations

import os
from typing import TextIO

RESET = "\x1b[0m"
BOLD = "1"
DIM = "2"
RED = "31"
GREEN = "32"
YELLOW = "33"
CYAN = "36"

ACTION_LABELS = {
    "deduplicated": "중복 제거됨",
    "inherited": "상속됨",
    "installed": "설치됨",
    "missing": "설치되지 않음",
    "not-installed": "설치되지 않음",
    "preview": "변경 예정",
    "removed": "제거됨",
    "switched": "설정 변경됨",
    "unchanged": "변경 없음",
    "updated": "갱신됨",
}

ACTION_COLORS = {
    "deduplicated": CYAN,
    "inherited": CYAN,
    "installed": GREEN,
    "missing": YELLOW,
    "not-installed": YELLOW,
    "preview": CYAN,
    "removed": GREEN,
    "switched": GREEN,
    "unchanged": CYAN,
    "updated": GREEN,
}


def supports_color(stream: TextIO) -> bool:
    return (
        "NO_COLOR" not in os.environ
        and os.environ.get("TERM") != "dumb"
        and bool(getattr(stream, "isatty", lambda: False)())
    )


def style(text: str, *codes: str, stream: TextIO) -> str:
    if not codes or not supports_color(stream):
        return text
    return f"\x1b[{';'.join(codes)}m{text}{RESET}"


def action_label(action: str, stream: TextIO) -> str:
    label = ACTION_LABELS.get(action, action)
    color = ACTION_COLORS.get(action, CYAN)
    return style(label, BOLD, color, stream=stream)


def colorize_diff(diff: str, stream: TextIO) -> str:
    if not supports_color(stream):
        return diff
    rendered = []
    for line in diff.splitlines(keepends=True):
        if line.startswith(("+++", "---")):
            rendered.append(style(line.rstrip("\n"), BOLD, stream=stream) + ("\n" if line.endswith("\n") else ""))
        elif line.startswith("+"):
            rendered.append(style(line.rstrip("\n"), GREEN, stream=stream) + ("\n" if line.endswith("\n") else ""))
        elif line.startswith("-"):
            rendered.append(style(line.rstrip("\n"), RED, stream=stream) + ("\n" if line.endswith("\n") else ""))
        elif line.startswith("@@"):
            rendered.append(style(line.rstrip("\n"), CYAN, stream=stream) + ("\n" if line.endswith("\n") else ""))
        else:
            rendered.append(line)
    return "".join(rendered)
