from __future__ import annotations

import os
import stat
import tempfile
import unittest
from pathlib import Path

from clear_korean.installer import (
    END_MARKER,
    InstallError,
    apply_change,
    install_content,
    imports_project_agents,
    load_preset,
    remove_content,
    resolve_targets,
    status_for,
)


class ContentTests(unittest.TestCase):
    def test_presets_are_bundled(self) -> None:
        self.assertIn("개발자용 추가 원칙", load_preset("developer"))
        self.assertIn("일반 사용자용 추가 원칙", load_preset("general"))
        self.assertIn("정중한 존댓말", load_preset("developer", "polite"))

    def test_unknown_preset_and_tone_are_rejected(self) -> None:
        with self.assertRaisesRegex(InstallError, "지원하지 않는 preset"):
            load_preset("unknown")
        with self.assertRaisesRegex(InstallError, "지원하지 않는 tone"):
            load_preset("developer", "formal")

    def test_install_preserves_existing_content(self) -> None:
        before = "# Existing rules\n\n- Keep this.\n"
        after, action = install_content(before, "developer", created=False)
        self.assertEqual("installed", action)
        self.assertTrue(after.startswith(before))
        self.assertIn("clear-korean:start preset=developer", after)
        self.assertIn(END_MARKER, after)

    def test_install_is_idempotent(self) -> None:
        once, _ = install_content("", "developer", created=True)
        twice, action = install_content(once, "developer")
        self.assertEqual("unchanged", action)
        self.assertEqual(once, twice)
        self.assertEqual(1, twice.count("clear-korean:start"))

    def test_install_switches_preset_without_duplication(self) -> None:
        developer, _ = install_content("# Existing\n", "developer", created=False)
        general, action = install_content(developer, "general")
        self.assertEqual("switched", action)
        self.assertNotIn("preset=developer", general)
        self.assertIn("preset=general", general)
        self.assertEqual(1, general.count("clear-korean:start"))

    def test_install_switches_tone_without_duplication(self) -> None:
        plain, _ = install_content("", "developer", "plain", created=True)
        polite, action = install_content(plain, "developer", "polite")
        self.assertEqual("switched", action)
        self.assertIn("tone=polite", polite)
        self.assertIn("정중한 존댓말", polite)
        self.assertEqual(1, polite.count("clear-korean:start"))

    def test_remove_preserves_existing_content(self) -> None:
        for before in ("# Existing", "# Existing\n", "# Existing\n\n", ""):
            with self.subTest(before=repr(before)):
                installed, _ = install_content(before, "developer", created=False)
                removed, action, created = remove_content(installed)
                self.assertEqual("removed", action)
                self.assertFalse(created)
                self.assertEqual(before, removed)

    def test_remove_marks_cli_created_file_for_deletion(self) -> None:
        installed, _ = install_content("", "developer", created=True)
        removed, action, created = remove_content(installed)
        self.assertEqual("removed", action)
        self.assertEqual("", removed)
        self.assertTrue(created)

    def test_malformed_markers_are_rejected(self) -> None:
        with self.assertRaises(InstallError):
            install_content("<!-- clear-korean:start preset=developer version=0.1.0 join=0 created=1 -->\n", "developer")
        with self.assertRaises(InstallError):
            remove_content(f"{END_MARKER}\n")

    def test_agents_import_detection(self) -> None:
        self.assertTrue(imports_project_agents("@AGENTS.md\n"))
        self.assertTrue(imports_project_agents("# Rules\n@./AGENTS.md\n"))
        self.assertFalse(imports_project_agents("`@AGENTS.md`\n"))
        self.assertFalse(imports_project_agents("```md\n@AGENTS.md\n```\n"))
        self.assertFalse(imports_project_agents("~~~md\n@AGENTS.md\n~~~\n"))

    def test_remove_without_managed_block_is_unchanged(self) -> None:
        content = "# Existing rules\n"
        self.assertEqual((content, "not-installed", False), remove_content(content))


class FileTests(unittest.TestCase):
    def test_write_creates_backup_and_preserves_mode(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "AGENTS.md"
            path.write_text("# Existing\n", encoding="utf-8")
            path.chmod(0o600)
            after, action = install_content(path.read_text(encoding="utf-8"), "developer", created=False)
            change = apply_change(path, after, action, dry_run=False)
            self.assertIsNotNone(change.backup)
            self.assertTrue(change.backup and change.backup.exists())
            self.assertEqual("# Existing\n", change.backup.read_text(encoding="utf-8"))
            self.assertEqual(0o600, stat.S_IMODE(path.stat().st_mode))

    def test_dry_run_does_not_write(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "AGENTS.md"
            after, action = install_content("", "developer", created=True)
            change = apply_change(path, after, action, dry_run=True)
            self.assertEqual("installed", change.action)
            self.assertFalse(path.exists())

    def test_symlink_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.md"
            link = root / "AGENTS.md"
            source.write_text("source\n", encoding="utf-8")
            link.symlink_to(source)
            with self.assertRaises(InstallError):
                status_for(link)

    def test_broken_symlink_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            link = Path(directory) / "AGENTS.md"
            link.symlink_to(Path(directory) / "missing.md")
            with self.assertRaises(InstallError):
                status_for(link)

    def test_directory_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(InstallError, "일반 파일이 아닌 경로"):
                status_for(Path(directory))

    def test_status_reports_preset(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "CLAUDE.md"
            content, _ = install_content("", "general", created=True)
            path.write_text(content, encoding="utf-8")
            self.assertEqual(("installed", "general", "plain"), status_for(path))


class TargetTests(unittest.TestCase):
    def test_project_targets(self) -> None:
        directory = Path("/tmp/project")
        targets = resolve_targets("all", "project", directory)
        self.assertEqual(directory / "AGENTS.md", targets[0].path)
        self.assertEqual(directory / "CLAUDE.md", targets[1].path)

    def test_user_targets_honor_codex_home(self) -> None:
        home = Path("/tmp/home")
        codex_home = Path("/tmp/custom-codex")
        targets = resolve_targets("all", "user", Path.cwd(), home=home, codex_home=codex_home)
        self.assertEqual(codex_home / "AGENTS.md", targets[0].path)
        self.assertEqual(home / ".claude" / "CLAUDE.md", targets[1].path)


if __name__ == "__main__":
    unittest.main()
