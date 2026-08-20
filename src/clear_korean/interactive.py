from __future__ import annotations

import os
import shutil
import sys
import unicodedata
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import TextIO

from .console import BOLD, CYAN, DIM, GREEN, style
from .installer import InstallError


class WizardCancelled(Exception):
    pass


@dataclass(frozen=True)
class Option:
    label: str
    value: str
    description: str = ""


def _read_key_windows() -> str:
    import msvcrt

    character = msvcrt.getwch()
    if character in ("\x00", "\xe0"):
        code = msvcrt.getwch()
        return {"H": "up", "P": "down"}.get(code, "other")
    if character in ("\r", "\n"):
        return "enter"
    if character == "\x03":
        raise KeyboardInterrupt
    if character == "\x1b":
        return "escape"
    return {"k": "up", "j": "down"}.get(character.lower(), "other")


def _read_key_posix(input_stream: TextIO) -> str:
    import select
    import termios
    import tty

    descriptor = input_stream.fileno()
    previous = termios.tcgetattr(descriptor)
    try:
        tty.setraw(descriptor)
        character = os.read(descriptor, 1)
        if character == b"\x1b":
            ready, _, _ = select.select([descriptor], [], [], 0.05)
            if not ready:
                return "escape"
            second = os.read(descriptor, 1)
            if second == b"[":
                ready, _, _ = select.select([descriptor], [], [], 0.05)
                if not ready:
                    return "escape"
                third = os.read(descriptor, 1)
                return {b"A": "up", b"B": "down"}.get(third, "other")
            return "escape"
        if character in (b"\r", b"\n"):
            return "enter"
        if character == b"\x03":
            raise KeyboardInterrupt
        return {b"k": "up", b"j": "down"}.get(character.lower(), "other")
    finally:
        termios.tcsetattr(descriptor, termios.TCSADRAIN, previous)


def read_key(input_stream: TextIO = sys.stdin) -> str:
    if os.name == "nt":
        return _read_key_windows()
    return _read_key_posix(input_stream)


def _display_width(text: str) -> int:
    return sum(2 if unicodedata.east_asian_width(character) in "WFA" else 1 for character in text)


def _truncate(text: str, width: int) -> str:
    if width <= 0:
        return ""
    if _display_width(text) <= width:
        return text
    if width == 1:
        return "…"
    result = []
    used = 0
    for character in text:
        character_width = 2 if unicodedata.east_asian_width(character) in "WFA" else 1
        if used + character_width > width - 1:
            break
        result.append(character)
        used += character_width
    return f"{''.join(result)}…"


def _option_parts(option: Option, width: int) -> tuple[str, str]:
    label = _truncate(option.label, width)
    if not option.description or _display_width(label) >= width:
        return label, ""
    description_width = width - _display_width(label) - 2
    if description_width < 8:
        return label, ""
    return label, _truncate(option.description, description_width)


def _render(
    question: str,
    options: Sequence[Option],
    selected: int,
    output: TextIO,
    redraw: bool,
    step: tuple[int, int] | None,
) -> None:
    line_count = len(options) + 2
    terminal_width = max(20, shutil.get_terminal_size(fallback=(80, 24)).columns)
    if redraw:
        output.write(f"\x1b[{line_count}A")
    output.write("\r\x1b[2K")
    step_label = f"{step[0]}/{step[1]}  " if step else ""
    heading = _truncate(f"{step_label}{question}", terminal_width)
    output.write(f"{style(heading, BOLD, CYAN, stream=output)}\n")
    for index, option in enumerate(options):
        output.write("\r\x1b[2K")
        marker = "❯" if index == selected else " "
        visible_label, visible_description = _option_parts(option, terminal_width - 3)
        label = style(visible_label, BOLD, GREEN, stream=output) if index == selected else visible_label
        suffix = f"  {style(visible_description, DIM, stream=output)}" if visible_description else ""
        output.write(f"{style(marker, GREEN, stream=output)} {label}{suffix}\n")
    output.write("\r\x1b[2K")
    output.write(f"{style('↑/↓로 선택 · Enter로 확인 · Esc로 취소', DIM, stream=output)}\n")
    output.flush()


def select_option(
    question: str,
    options: Sequence[Option],
    *,
    input_stream: TextIO = sys.stdin,
    output: TextIO = sys.stdout,
    key_reader: Callable[[], str] | None = None,
    step: tuple[int, int] | None = None,
) -> str:
    if not options:
        raise ValueError("선택 항목이 없습니다.")
    if key_reader is None:
        if not input_stream.isatty() or not output.isatty():
            raise InstallError("대화형 설정에는 터미널이 필요합니다. 자동화 환경에서는 install 또는 print 명령을 사용해 주세요.")
        key_reader = lambda: read_key(input_stream)

    selected = 0
    redraw = False
    while True:
        _render(question, options, selected, output, redraw, step)
        redraw = True
        key = key_reader()
        if key == "up":
            selected = (selected - 1) % len(options)
        elif key == "down":
            selected = (selected + 1) % len(options)
        elif key == "enter":
            line_count = len(options) + 2
            step_label = f"{step[0]}/{step[1]}  " if step else ""
            output.write(f"\x1b[{line_count}A\r\x1b[2K")
            output.write(style("✓", BOLD, GREEN, stream=output))
            output.write(f" {style(step_label + question, DIM, stream=output)}  ")
            output.write(style(options[selected].label, BOLD, stream=output))
            output.write("\x1b[J\n")
            output.flush()
            return options[selected].value
        elif key == "escape":
            raise WizardCancelled
