from __future__ import annotations

import io
import os
import unittest
from unittest.mock import patch

from clear_korean.console import GREEN, action_label, colorize_diff, style, supports_color


class TtyBuffer(io.StringIO):
    def isatty(self) -> bool:
        return True


class ConsoleTests(unittest.TestCase):
    def test_color_is_used_for_tty(self) -> None:
        output = TtyBuffer()
        with patch.dict(os.environ, {}, clear=True):
            self.assertTrue(supports_color(output))
            self.assertEqual("\x1b[32m완료\x1b[0m", style("완료", GREEN, stream=output))

    def test_color_is_disabled_for_non_tty(self) -> None:
        output = io.StringIO()
        with patch.dict(os.environ, {}, clear=True):
            self.assertFalse(supports_color(output))
            self.assertEqual("완료", style("완료", GREEN, stream=output))

    def test_no_color_disables_color_for_tty(self) -> None:
        output = TtyBuffer()
        with patch.dict(os.environ, {"NO_COLOR": ""}, clear=True):
            self.assertFalse(supports_color(output))
            self.assertEqual("설치됨", action_label("installed", output))

    def test_dumb_terminal_disables_color(self) -> None:
        output = TtyBuffer()
        with patch.dict(os.environ, {"TERM": "dumb"}, clear=True):
            self.assertFalse(supports_color(output))

    def test_diff_colors_added_and_removed_lines(self) -> None:
        output = TtyBuffer()
        diff = "--- before\n+++ after\n@@ -1 +1 @@\n-old\n+new\n"
        with patch.dict(os.environ, {}, clear=True):
            rendered = colorize_diff(diff, output)
        self.assertIn("\x1b[31m-old\x1b[0m", rendered)
        self.assertIn("\x1b[32m+new\x1b[0m", rendered)


if __name__ == "__main__":
    unittest.main()
