from __future__ import annotations

import difflib
import os
import re
import shutil
import stat
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from importlib import resources
from pathlib import Path

from . import __version__

PRESETS = ("developer", "general")
TONES = ("plain", "polite")
AGENTS = ("codex", "claude")
SCOPES = ("user", "project")

START_RE = re.compile(
    r"^<!-- clear-korean:start preset=(developer|general)(?: tone=(plain|polite))? version=([^ ]+) join=([0-9]+) created=([01]) -->$",
    re.MULTILINE,
)
END_MARKER = "<!-- clear-korean:end -->"
AGENTS_IMPORT_RE = re.compile(r"^\s*@(?:\./)?AGENTS\.md\s*$")
FENCE_RE = re.compile(r"^\s*(`{3,}|~{3,})")


class InstallError(RuntimeError):
    pass


@dataclass(frozen=True)
class Target:
    agent: str
    scope: str
    path: Path
    override_path: Path | None = None


@dataclass(frozen=True)
class Change:
    action: str
    path: Path
    before: str
    after: str
    backup: Path | None = None


def load_preset(preset: str, tone: str = "plain") -> str:
    if preset not in PRESETS:
        raise InstallError(f"지원하지 않는 preset입니다: {preset}")
    if tone not in TONES:
        raise InstallError(f"지원하지 않는 tone입니다: {tone}")
    preset_file = resources.files("clear_korean.presets").joinpath(f"{preset}-{tone}.md")
    return preset_file.read_text(encoding="utf-8").rstrip() + "\n"


def managed_block(preset: str, tone: str, join: int, created: bool) -> str:
    body = load_preset(preset, tone).rstrip()
    return (
        f"<!-- clear-korean:start preset={preset} tone={tone} version={__version__} join={join} created={int(created)} -->\n"
        f"{body}\n"
        f"{END_MARKER}"
    )


def resolve_targets(
    agent: str,
    scope: str,
    directory: Path,
    home: Path | None = None,
    codex_home: Path | None = None,
) -> list[Target]:
    if agent not in (*AGENTS, "all"):
        raise InstallError(f"지원하지 않는 agent입니다: {agent}")
    if scope not in SCOPES:
        raise InstallError(f"지원하지 않는 scope입니다: {scope}")

    selected = AGENTS if agent == "all" else (agent,)
    user_home = (home or Path.home()).expanduser().resolve()
    project_dir = directory.expanduser().resolve()
    targets: list[Target] = []

    for selected_agent in selected:
        if scope == "project":
            filename = "AGENTS.md" if selected_agent == "codex" else "CLAUDE.md"
            path = project_dir / filename
            override = project_dir / "AGENTS.override.md" if selected_agent == "codex" else None
        elif selected_agent == "codex":
            base = (codex_home or Path(os.environ.get("CODEX_HOME", user_home / ".codex"))).expanduser().resolve()
            path = base / "AGENTS.md"
            override = base / "AGENTS.override.md"
        else:
            path = user_home / ".claude" / "CLAUDE.md"
            override = None
        targets.append(Target(selected_agent, scope, path, override))
    return targets


def find_managed_span(content: str) -> tuple[int, int, str, str, int, bool] | None:
    starts = list(START_RE.finditer(content))
    end_positions = [match.start() for match in re.finditer(re.escape(END_MARKER), content)]
    if not starts and not end_positions:
        return None
    if len(starts) != 1 or len(end_positions) != 1:
        raise InstallError("Clear Korean 관리 마커가 손상됐거나 중복됐습니다. 파일을 직접 확인해 주세요.")

    start = starts[0]
    end_start = end_positions[0]
    if end_start <= start.start():
        raise InstallError("Clear Korean 관리 마커의 순서가 올바르지 않습니다.")
    end = end_start + len(END_MARKER)
    return (
        start.start(),
        end,
        start.group(1),
        start.group(2) or "plain",
        int(start.group(4)),
        start.group(5) == "1",
    )


def imports_project_agents(content: str) -> bool:
    fence_character: str | None = None
    fence_length = 0
    for line in content.splitlines():
        fence = FENCE_RE.match(line)
        if fence:
            marker = fence.group(1)
            if fence_character is None:
                fence_character = marker[0]
                fence_length = len(marker)
            elif marker[0] == fence_character and len(marker) >= fence_length:
                fence_character = None
                fence_length = 0
            continue
        if fence_character is None and AGENTS_IMPORT_RE.fullmatch(line):
            return True
    return False


def install_content(
    content: str,
    preset: str,
    tone: str = "plain",
    created: bool = False,
) -> tuple[str, str]:
    span = find_managed_span(content)
    if span is None:
        separator = "" if not content else ("\n" if content.endswith("\n") else "\n\n")
        block = managed_block(preset, tone, len(separator), created)
        return f"{content}{separator}{block}\n", "installed"

    start, end, current_preset, current_tone, join, originally_created = span
    block = managed_block(preset, tone, join, originally_created)
    after = f"{content[:start]}{block}{content[end:]}"
    if not after.endswith("\n"):
        after += "\n"
    action = "unchanged" if after == content else "updated"
    if (current_preset != preset or current_tone != tone) and action == "updated":
        action = "switched"
    return after, action


def remove_content(content: str) -> tuple[str, str, bool]:
    span = find_managed_span(content)
    if span is None:
        return content, "not-installed", False
    start, end, _, _, join, created = span
    before = content[:start]
    expected_separator = "\n" * join
    if join and not before.endswith(expected_separator):
        raise InstallError("Clear Korean 관리 블록 앞의 구분 문자가 변경됐습니다. 파일을 직접 확인해 주세요.")
    if join:
        before = before[:-join]
    after = content[end:]
    if after.startswith("\n"):
        after = after[1:]
    return before + after, "removed", created


def read_text(path: Path) -> str:
    if path.is_symlink():
        raise InstallError(f"심볼릭 링크는 자동으로 수정하지 않습니다: {path}")
    if not path.exists():
        return ""
    if not path.is_file():
        raise InstallError(f"일반 파일이 아닌 경로는 수정할 수 없습니다: {path}")
    return path.read_text(encoding="utf-8")


def backup_path(path: Path) -> Path:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    candidate = path.with_name(f"{path.name}.clear-korean.{timestamp}.bak")
    index = 1
    while candidate.exists():
        candidate = path.with_name(f"{path.name}.clear-korean.{timestamp}.{index}.bak")
        index += 1
    return candidate


def atomic_write(path: Path, content: str, previous_mode: int | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temp_path = Path(temp_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temp_path, previous_mode if previous_mode is not None else 0o644)
        os.replace(temp_path, path)
    finally:
        if temp_path.exists():
            temp_path.unlink()


def apply_change(
    path: Path,
    after: str,
    action: str,
    dry_run: bool,
    delete_empty: bool = True,
) -> Change:
    existed = path.exists()
    before = read_text(path)
    if before == after:
        return Change(action, path, before, after)

    if dry_run:
        return Change(action, path, before, after)

    backup = None
    previous_mode = None
    if existed:
        previous_mode = stat.S_IMODE(path.stat().st_mode)
        backup = backup_path(path)
        shutil.copy2(path, backup)

    if not after and delete_empty:
        if existed:
            path.unlink()
    else:
        atomic_write(path, after, previous_mode)
    return Change(action, path, before, after, backup)


def diff_text(change: Change) -> str:
    before_name = str(change.path) if change.before else "/dev/null"
    after_name = str(change.path) if change.after else "/dev/null"
    return "".join(
        difflib.unified_diff(
            change.before.splitlines(keepends=True),
            change.after.splitlines(keepends=True),
            fromfile=before_name,
            tofile=after_name,
        )
    )


def status_for(path: Path) -> tuple[str, str | None, str | None]:
    if path.is_symlink():
        raise InstallError(f"심볼릭 링크는 자동으로 수정하지 않습니다: {path}")
    if not path.exists():
        return "missing", None, None
    content = read_text(path)
    span = find_managed_span(content)
    if span is None:
        return "not-installed", None, None
    return "installed", span[2], span[3]
