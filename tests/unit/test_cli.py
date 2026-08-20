from __future__ import annotations

import contextlib
import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from clear_korean.cli import main, parser
from clear_korean.wizard import SetupChoices


class CliTests(unittest.TestCase):
    def run_cli(self, *args: str) -> tuple[int, str, str]:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = main(list(args))
        return code, stdout.getvalue(), stderr.getvalue()

    def test_print(self) -> None:
        code, stdout, stderr = self.run_cli("print", "--preset", "general")
        self.assertEqual(0, code)
        self.assertIn("일반 사용자용 추가 원칙", stdout)
        self.assertEqual("", stderr)

    def test_help_uses_polite_korean_labels(self) -> None:
        help_text = parser().format_help()
        self.assertIn("명확하고 간결한 한국어 출력 지침을 출력하거나 설치합니다.", help_text)
        self.assertIn("명령:", help_text)
        self.assertIn("옵션:", help_text)
        self.assertIn("도움말을 표시하고 종료합니다.", help_text)
        self.assertTrue(help_text.startswith("사용법:"))
        self.assertNotIn("positional arguments", help_text)
        self.assertNotIn("options:", help_text)

    def test_print_polite(self) -> None:
        code, stdout, stderr = self.run_cli(
            "print", "--preset", "general", "--tone", "polite",
        )
        self.assertEqual(0, code)
        self.assertIn("말투: 정중한 존댓말", stdout)
        self.assertEqual("", stderr)

    def test_install_status_remove_project(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            existing = "# Project rules\n"
            (root / "AGENTS.md").write_text(existing, encoding="utf-8")

            code, stdout, _ = self.run_cli(
                "install", "--agent", "all", "--scope", "project",
                "--directory", str(root), "--preset", "developer",
            )
            self.assertEqual(0, code)
            self.assertIn("설치됨", stdout)
            self.assertTrue((root / "AGENTS.md").read_text(encoding="utf-8").startswith(existing))
            self.assertTrue((root / "CLAUDE.md").exists())

            code, stdout, _ = self.run_cli(
                "status", "--agent", "all", "--scope", "project",
                "--directory", str(root),
            )
            self.assertEqual(0, code)
            self.assertEqual(2, stdout.count("설치됨:"))

            code, _, _ = self.run_cli(
                "remove", "--agent", "all", "--scope", "project",
                "--directory", str(root),
            )
            self.assertEqual(0, code)
            self.assertEqual(existing, (root / "AGENTS.md").read_text(encoding="utf-8"))
            self.assertFalse((root / "CLAUDE.md").exists())

    def test_dry_run_only_prints_diff(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            code, stdout, _ = self.run_cli(
                "install", "--agent", "codex", "--scope", "project",
                "--directory", str(root), "--preset", "developer", "--dry-run",
            )
            self.assertEqual(0, code)
            self.assertIn("변경 예정:", stdout)
            self.assertNotIn("설치됨:", stdout)
            self.assertIn("+++", stdout)
            self.assertFalse((root / "AGENTS.md").exists())

    def test_remove_preserves_preexisting_empty_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "AGENTS.md"
            path.touch()
            code, _, _ = self.run_cli(
                "install", "--agent", "codex", "--scope", "project",
                "--directory", str(root), "--preset", "developer",
            )
            self.assertEqual(0, code)
            code, _, _ = self.run_cli(
                "remove", "--agent", "codex", "--scope", "project",
                "--directory", str(root),
            )
            self.assertEqual(0, code)
            self.assertTrue(path.exists())
            self.assertEqual("", path.read_text(encoding="utf-8"))

    def test_status_missing_is_nonzero(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            code, stdout, _ = self.run_cli(
                "status", "--agent", "codex", "--scope", "project",
                "--directory", directory,
            )
            self.assertEqual(1, code)
            self.assertIn("설치되지 않음:", stdout)

    def test_setup_applies_selected_tone(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            choices = SetupChoices(
                preset="general",
                tone="polite",
                agent="codex",
                scope="project",
                action="install",
                directory=root,
            )
            with patch("clear_korean.cli.collect_setup", return_value=choices):
                code, stdout, stderr = self.run_cli("setup", "--directory", str(root))
            self.assertEqual(0, code)
            self.assertIn("설치됨:", stdout)
            self.assertEqual("", stderr)
            content = (root / "AGENTS.md").read_text(encoding="utf-8")
            self.assertIn("preset=general tone=polite", content)
            self.assertIn("정중한 존댓말", content)

    def test_setup_preview_does_not_write(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            choices = SetupChoices(
                preset="developer",
                tone="plain",
                agent="all",
                scope="project",
                action="preview",
                directory=root,
            )
            with patch("clear_korean.cli.collect_setup", return_value=choices):
                code, stdout, _ = self.run_cli("setup", "--directory", str(root))
            self.assertEqual(0, code)
            self.assertIn("변경 예정:", stdout)
            self.assertIn("+++", stdout)
            self.assertFalse((root / "AGENTS.md").exists())
            self.assertFalse((root / "CLAUDE.md").exists())

    def test_setup_print_outputs_selected_preset_without_writing(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            choices = SetupChoices(
                preset="general",
                tone="polite",
                agent=None,
                scope=None,
                action="print",
                directory=root,
            )
            with patch("clear_korean.cli.collect_setup", return_value=choices):
                code, stdout, stderr = self.run_cli("setup", "--directory", str(root))
            self.assertEqual(0, code)
            self.assertIn("일반 사용자용 추가 원칙", stdout)
            self.assertIn("정중한 존댓말", stdout)
            self.assertEqual("", stderr)
            self.assertEqual([], list(root.iterdir()))

    def test_setup_cancel_returns_success_without_writing(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            choices = SetupChoices(
                preset="developer",
                tone="plain",
                agent="codex",
                scope="project",
                action="cancel",
                directory=root,
            )
            with patch("clear_korean.cli.collect_setup", return_value=choices):
                code, stdout, stderr = self.run_cli("setup", "--directory", str(root))
            self.assertEqual(0, code)
            self.assertEqual("설정을 취소했습니다.\n", stdout)
            self.assertEqual("", stderr)
            self.assertEqual([], list(root.iterdir()))

    def test_project_override_prints_warning(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "AGENTS.override.md").write_text("# Override\n", encoding="utf-8")
            code, stdout, stderr = self.run_cli(
                "install", "--agent", "codex", "--scope", "project",
                "--directory", str(root),
            )
            self.assertEqual(0, code)
            self.assertIn("설치됨:", stdout)
            self.assertIn("AGENTS.override.md가 우선하므로", stderr)

    def test_remove_dry_run_preserves_installed_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.run_cli(
                "install", "--agent", "codex", "--scope", "project",
                "--directory", str(root),
            )
            path = root / "AGENTS.md"
            installed = path.read_text(encoding="utf-8")
            code, stdout, stderr = self.run_cli(
                "remove", "--agent", "codex", "--scope", "project",
                "--directory", str(root), "--dry-run",
            )
            self.assertEqual(0, code)
            self.assertIn("---", stdout)
            self.assertEqual("", stderr)
            self.assertEqual(installed, path.read_text(encoding="utf-8"))

    def test_all_project_reuses_claude_agents_import(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            claude = root / "CLAUDE.md"
            claude.write_text("@AGENTS.md\n", encoding="utf-8")
            code, stdout, _ = self.run_cli(
                "install", "--agent", "all", "--scope", "project",
                "--directory", str(root), "--preset", "developer",
            )
            self.assertEqual(0, code)
            self.assertIn("상속됨:", stdout)
            self.assertIn("clear-korean:start", (root / "AGENTS.md").read_text(encoding="utf-8"))
            self.assertEqual("@AGENTS.md\n", claude.read_text(encoding="utf-8"))

            code, stdout, _ = self.run_cli(
                "status", "--agent", "all", "--scope", "project",
                "--directory", str(root),
            )
            self.assertEqual(0, code)
            self.assertIn("상속됨:", stdout)

            code, stdout, _ = self.run_cli(
                "remove", "--agent", "all", "--scope", "project",
                "--directory", str(root),
            )
            self.assertEqual(0, code)
            self.assertIn("별도 블록이 없습니다", stdout)
            self.assertEqual("@AGENTS.md\n", claude.read_text(encoding="utf-8"))
            self.assertFalse((root / "AGENTS.md").exists())


if __name__ == "__main__":
    unittest.main()
