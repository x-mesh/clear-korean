#!/usr/bin/env python3
"""Capture the interactive start screen as a deterministic SVG terminal."""

from __future__ import annotations

import argparse
import html
import os
import pty
import re
import select
import struct
import sys
import termios
import time
import unicodedata
from dataclasses import dataclass
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = PROJECT_DIR / "docs" / "assets" / "terminal-setup.svg"
END_MARKER = "↑/↓로 선택 · Enter로 확인 · Esc로 취소"
ANSI_PATTERN = re.compile(r"\x1b\[([0-9;]*)([A-Za-z])")


@dataclass(frozen=True)
class CellStyle:
    bold: bool = False
    dim: bool = False
    color: str = "#e6edf3"


@dataclass(frozen=True)
class Run:
    column: int
    text: str
    style: CellStyle


def display_width(text: str) -> int:
    return sum(2 if unicodedata.east_asian_width(char) in "WFA" else 1 for char in text)


def capture() -> str:
    pid, descriptor = pty.fork()
    if pid == 0:
        os.chdir(PROJECT_DIR)
        os.environ.pop("NO_COLOR", None)
        os.environ["TERM"] = "xterm-256color"
        os.environ["PYTHONPATH"] = str(PROJECT_DIR / "src")
        os.execv(sys.executable, [sys.executable, "-m", "clear_korean"])

    columns, rows = 80, 24
    size = struct.pack("HHHH", rows, columns, 0, 0)
    import fcntl

    fcntl.ioctl(descriptor, termios.TIOCSWINSZ, size)
    output = bytearray()
    deadline = time.monotonic() + 10
    marker = END_MARKER.encode()
    try:
        while marker not in output:
            if time.monotonic() > deadline:
                raise TimeoutError("CLI 시작 화면을 10초 안에 읽지 못했습니다.")
            ready, _, _ = select.select([descriptor], [], [], 0.1)
            if ready:
                output.extend(os.read(descriptor, 4096))
        os.write(descriptor, b"\x1b")
    finally:
        os.close(descriptor)
        os.waitpid(pid, 0)

    text = output.decode("utf-8", errors="replace")
    title_start = text.index("Clear Korean")
    start = text.rfind("\x1b[", 0, title_start)
    if start == -1:
        start = title_start
    end = text.index(END_MARKER, start) + len(END_MARKER)
    return text[start:end]


def parse_screen(capture_text: str) -> list[list[Run]]:
    lines: list[list[Run]] = [[]]
    column = 0
    style = CellStyle()
    position = 0

    def append_text(text: str) -> None:
        nonlocal column
        if not text:
            return
        lines[-1].append(Run(column, text, style))
        column += display_width(text)

    for match in ANSI_PATTERN.finditer(capture_text):
        chunk = capture_text[position : match.start()]
        for part_index, part in enumerate(re.split(r"([\r\n])", chunk)):
            if part == "\r":
                column = 0
            elif part == "\n":
                lines.append([])
                column = 0
            elif part:
                append_text(part)
        params, command = match.groups()
        if command == "m":
            codes = [int(value) for value in params.split(";") if value] or [0]
            if 0 in codes:
                style = CellStyle()
            else:
                color = style.color
                if 32 in codes:
                    color = "#3fb950"
                elif 36 in codes:
                    color = "#58a6ff"
                style = CellStyle(1 in codes or style.bold, 2 in codes or style.dim, color)
        elif command == "K" and params in ("", "0", "2"):
            lines[-1] = []
            column = 0
        position = match.end()

    append_text(capture_text[position:])
    while lines and not lines[-1]:
        lines.pop()
    return lines


def render_svg(lines: list[list[Run]]) -> str:
    cell_width = 9
    line_height = 26
    padding_x = 28
    chrome_height = 46
    padding_bottom = 25
    content_columns = max(60, max((run.column + display_width(run.text) for line in lines for run in line), default=0))
    width = padding_x * 2 + content_columns * cell_width
    height = chrome_height + len(lines) * line_height + padding_bottom
    elements = []
    for row, line in enumerate(lines):
        y = chrome_height + 20 + row * line_height
        for run in line:
            opacity = "0.62" if run.style.dim else "1"
            weight = "700" if run.style.bold else "400"
            elements.append(
                f'<text x="{padding_x + run.column * cell_width}" y="{y}" '
                f'fill="{run.style.color}" fill-opacity="{opacity}" font-weight="{weight}">'
                f'{html.escape(run.text)}</text>'
            )
    body = "\n    ".join(elements)
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-labelledby="title description">
  <title id="title">Clear Korean 대화형 설정 시작 화면</title>
  <desc id="description">개발자용과 일반 사용자용 중 하나를 선택하는 터미널 화면</desc>
  <rect width="{width}" height="{height}" rx="14" fill="#0d1117"/>
  <path d="M14 0h{width - 28}a14 14 0 0 1 14 14v32H0V14A14 14 0 0 1 14 0Z" fill="#161b22"/>
  <circle cx="23" cy="23" r="6" fill="#f85149"/>
  <circle cx="43" cy="23" r="6" fill="#d29922"/>
  <circle cx="63" cy="23" r="6" fill="#3fb950"/>
  <text x="{width / 2}" y="28" text-anchor="middle" fill="#8b949e" font-family="ui-monospace, SFMono-Regular, Menlo, Consolas, 'Liberation Mono', monospace" font-size="13">clear-korean</text>
  <g font-family="ui-monospace, SFMono-Regular, Menlo, Consolas, 'Liberation Mono', 'Noto Sans Mono CJK KR', monospace" font-size="16" xml:space="preserve">
    {body}
  </g>
</svg>
"""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    lines = parse_screen(capture())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(render_svg(lines), encoding="utf-8")
    print(args.output.relative_to(PROJECT_DIR))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
