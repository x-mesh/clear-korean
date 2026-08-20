from __future__ import annotations

import io
import unittest
from pathlib import Path
from unittest.mock import patch

from clear_korean.wizard import collect_setup


class WizardTests(unittest.TestCase):
    def test_summary_uses_labels_and_resolved_paths(self) -> None:
        answers = iter(("general", "polite", "install", "all", "project", "preview"))
        output = io.StringIO()

        with patch("clear_korean.wizard.select_option", side_effect=lambda *args, **kwargs: next(answers)):
            choices = collect_setup(Path("/work/project"), output=output)

        self.assertEqual("preview", choices.action)
        rendered = output.getvalue()
        self.assertIn("일반 사용자용 · 정중한 존댓말", rendered)
        self.assertIn("Codex와 Claude Code · 현재 프로젝트", rendered)
        self.assertIn("/work/project/AGENTS.md", rendered)
        self.assertIn("/work/project/CLAUDE.md", rendered)

    def test_restart_collects_all_choices_again(self) -> None:
        answers = iter((
            "developer", "plain", "install", "codex", "project", "restart",
            "general", "polite", "install", "claude", "user", "install",
        ))
        output = io.StringIO()

        with patch("clear_korean.wizard.select_option", side_effect=lambda *args, **kwargs: next(answers)):
            choices = collect_setup(Path("/work/project"), output=output)

        self.assertEqual(("general", "polite", "claude", "user", "install"), (
            choices.preset, choices.tone, choices.agent, choices.scope, choices.action,
        ))
        self.assertIn("선택을 다시 시작합니다.", output.getvalue())

    def test_print_skips_agent_and_scope(self) -> None:
        answers = iter(("developer", "plain", "print"))
        prompts = []

        def choose(question, *args, **kwargs):
            prompts.append(question)
            return next(answers)

        with patch("clear_korean.wizard.select_option", side_effect=choose):
            choices = collect_setup(Path("/work/project"), output=io.StringIO())

        self.assertEqual("print", choices.action)
        self.assertIsNone(choices.agent)
        self.assertIsNone(choices.scope)
        self.assertEqual(["용도를 선택하세요", "말투를 선택하세요", "사용 방법을 선택하세요"], prompts)

    def test_header_shows_version(self) -> None:
        output = io.StringIO()
        answers = iter(("developer", "plain", "print"))

        with patch("clear_korean.wizard.select_option", side_effect=lambda *args, **kwargs: next(answers)):
            collect_setup(Path("/work/project"), output=output)

        self.assertTrue(output.getvalue().startswith(
            "Clear Korean 0.2.6\nAI가 한국어로 짧고 명확하게 답하도록 돕습니다.\n"
        ))


if __name__ == "__main__":
    unittest.main()
