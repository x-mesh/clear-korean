from __future__ import annotations

import io
import os
import unittest
from unittest.mock import patch

from clear_korean.interactive import (
    InstallError,
    Option,
    WizardCancelled,
    _read_key_posix,
    select_option,
)


class TtyBuffer(io.StringIO):
    def isatty(self) -> bool:
        return True


class InteractiveTests(unittest.TestCase):
    def reader(self, *keys: str):
        iterator = iter(keys)
        return lambda: next(iterator)

    def test_down_and_enter_select_second_option(self) -> None:
        output = TtyBuffer()
        value = select_option(
            "질문",
            (Option("첫째", "first"), Option("둘째", "second")),
            output=output,
            key_reader=self.reader("down", "enter"),
        )
        self.assertEqual("second", value)
        self.assertIn("↑/↓로 선택", output.getvalue())
        self.assertIn("✓ 질문  둘째", output.getvalue())

    def test_step_is_shown_in_prompt_and_selection(self) -> None:
        output = TtyBuffer()
        select_option(
            "용도를 선택하세요",
            (Option("개발자용", "developer"),),
            output=output,
            key_reader=self.reader("enter"),
            step=(1, 5),
        )
        self.assertIn("1/5  용도를 선택하세요", output.getvalue())
        self.assertIn("✓ 1/5  용도를 선택하세요  개발자용", output.getvalue())

    @patch("shutil.get_terminal_size")
    def test_long_description_is_truncated_to_terminal_width(self, terminal_size) -> None:
        terminal_size.return_value = os.terminal_size((30, 24))
        output = TtyBuffer()
        select_option(
            "질문",
            (Option("현재 프로젝트", "project", "/very/long/project/path/that/wraps"),),
            output=output,
            key_reader=self.reader("enter"),
        )
        self.assertIn("…", output.getvalue())

    def test_up_wraps_to_last_option(self) -> None:
        value = select_option(
            "질문",
            (Option("첫째", "first"), Option("둘째", "second")),
            output=TtyBuffer(),
            key_reader=self.reader("up", "enter"),
        )
        self.assertEqual("second", value)

    def test_down_wraps_to_first_option(self) -> None:
        value = select_option(
            "질문",
            (Option("첫째", "first"), Option("둘째", "second")),
            output=TtyBuffer(),
            key_reader=self.reader("down", "down", "enter"),
        )
        self.assertEqual("first", value)

    def test_unknown_key_is_ignored(self) -> None:
        value = select_option(
            "질문",
            (Option("첫째", "first"), Option("둘째", "second")),
            output=TtyBuffer(),
            key_reader=self.reader("other", "enter"),
        )
        self.assertEqual("first", value)

    def test_escape_cancels(self) -> None:
        with self.assertRaises(WizardCancelled):
            select_option(
                "질문",
                (Option("첫째", "first"),),
                output=TtyBuffer(),
                key_reader=self.reader("escape"),
            )

    def test_empty_options_are_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "선택 항목이 없습니다"):
            select_option("질문", (), output=TtyBuffer(), key_reader=self.reader("enter"))

    def test_non_tty_is_rejected_without_custom_reader(self) -> None:
        with self.assertRaisesRegex(InstallError, "터미널이 필요합니다"):
            select_option(
                "질문",
                (Option("첫째", "first"),),
                input_stream=io.StringIO(),
                output=io.StringIO(),
            )

    @unittest.skipIf(os.name == "nt", "POSIX 전용 키 처리")
    def test_posix_reads_buffered_arrow_sequence_from_file_descriptor(self) -> None:
        input_stream = unittest.mock.Mock()
        input_stream.fileno.return_value = 7
        with (
            patch("os.read", side_effect=(b"\x1b", b"[", b"B")),
            patch("select.select", return_value=([7], [], [])),
            patch("termios.tcgetattr", return_value=[]),
            patch("termios.tcsetattr"),
            patch("tty.setraw"),
        ):
            self.assertEqual("down", _read_key_posix(input_stream))
        input_stream.read.assert_not_called()


if __name__ == "__main__":
    unittest.main()
