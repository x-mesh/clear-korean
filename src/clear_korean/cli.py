from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from . import __version__
from .console import BOLD, RED, YELLOW, action_label, colorize_diff, style
from .installer import (
    AGENTS,
    PRESETS,
    SCOPES,
    TONES,
    InstallError,
    apply_change,
    diff_text,
    find_managed_span,
    imports_project_agents,
    install_content,
    load_preset,
    read_text,
    remove_content,
    resolve_targets,
    status_for,
)
from .interactive import WizardCancelled
from .wizard import DISPLAY_LABELS, collect_setup


class KoreanHelpFormatter(argparse.HelpFormatter):
    def start_section(self, heading: str) -> None:
        headings = {
            "options": "옵션",
            "optional arguments": "옵션",
            "positional arguments": "명령",
        }
        super().start_section(headings.get(heading, heading))


class KoreanArgumentParser(argparse.ArgumentParser):
    def __init__(self, *args, **kwargs) -> None:
        kwargs["add_help"] = False
        kwargs.setdefault("formatter_class", KoreanHelpFormatter)
        super().__init__(*args, **kwargs)
        self.add_argument("-h", "--help", action="help", help="도움말을 표시하고 종료합니다.")

    def format_help(self) -> str:
        return super().format_help().replace("usage:", "사용법:", 1)

    def format_usage(self) -> str:
        return super().format_usage().replace("usage:", "사용법:", 1)

    def error(self, message: str) -> None:
        required = "the following arguments are required: "
        unrecognized = "unrecognized arguments: "
        if message.startswith(required):
            message = f"다음 인자가 필요합니다: {message[len(required):]}"
        elif message.startswith(unrecognized):
            message = f"인식할 수 없는 인자입니다: {message[len(unrecognized):]}"
        else:
            match = re.fullmatch(r"argument ([^:]+): invalid choice: (.+) \(choose from (.+)\)", message)
            if match:
                argument, value, choices = match.groups()
                message = f"{argument}에 지원하지 않는 값을 지정했습니다: {value} (가능한 값: {choices})"
        self.print_usage(sys.stderr)
        self.exit(2, f"오류: {message}\n")


def parser() -> argparse.ArgumentParser:
    root = KoreanArgumentParser(
        prog="clear-korean",
        description="명확하고 간결한 한국어 출력 지침을 출력하거나 설치합니다.",
    )
    root.add_argument("--version", action="version", version=f"%(prog)s {__version__}", help="버전을 표시하고 종료합니다.")
    commands = root.add_subparsers(dest="command", title="명령", parser_class=KoreanArgumentParser)

    setup_command = commands.add_parser("setup", help="단계별 화면에서 설정을 선택합니다.")
    setup_command.add_argument(
        "--directory",
        type=Path,
        default=Path.cwd(),
        help="project scope의 기준 디렉터리입니다.",
    )

    print_command = commands.add_parser("print", help="지침을 표준 출력으로 보냅니다.")
    print_command.add_argument("--preset", choices=PRESETS, default="developer", help="지침 용도입니다. 기본값: developer")
    print_command.add_argument("--tone", choices=TONES, default="plain", help="답변 말투입니다. 기본값: plain")

    for name, help_text in (
        ("install", "지침을 파일에 안전하게 삽입하거나 갱신합니다."),
        ("status", "설치 상태를 확인합니다."),
        ("remove", "Clear Korean 관리 블록만 제거합니다."),
    ):
        command = commands.add_parser(name, help=help_text)
        command.add_argument("--agent", choices=(*AGENTS, "all"), required=True, help="적용할 AI 환경입니다.")
        command.add_argument("--scope", choices=SCOPES, required=True, help="사용자 전역 또는 현재 프로젝트에 적용합니다.")
        command.add_argument(
            "--directory",
            type=Path,
            default=Path.cwd(),
            help="project scope의 기준 디렉터리입니다. 기본값은 현재 디렉터리입니다.",
        )
        if name == "install":
            command.add_argument("--preset", choices=PRESETS, default="developer", help="지침 용도입니다. 기본값: developer")
            command.add_argument("--tone", choices=TONES, default="plain", help="답변 말투입니다. 기본값: plain")
            command.add_argument("--dry-run", action="store_true", help="파일을 바꾸지 않고 차이만 표시합니다.")
        elif name == "remove":
            command.add_argument("--dry-run", action="store_true", help="파일을 바꾸지 않고 차이만 표시합니다.")
    return root


def warning_for_override(target) -> str | None:
    if target.override_path and target.override_path.exists():
        return f"{target.override_path}가 우선하므로 설치한 AGENTS.md가 적용되지 않을 수 있습니다."
    return None


def run_install(args: argparse.Namespace) -> int:
    targets = resolve_targets(args.agent, args.scope, args.directory)
    inherit_agents = args.agent == "all" and args.scope == "project"
    for target in targets:
        existed = target.path.exists()
        before = read_text(target.path)
        if target.agent == "claude" and inherit_agents and imports_project_agents(before):
            if find_managed_span(before) is not None:
                after, _, created = remove_content(before)
                change = apply_change(
                    target.path,
                    after,
                    "deduplicated",
                    args.dry_run,
                    delete_empty=created,
                )
                shown_action = "preview" if args.dry_run and change.action != "unchanged" else change.action
                print(f"{action_label(shown_action, sys.stdout)}: {change.path} (AGENTS.md를 사용합니다)")
                if change.backup:
                    print(f"백업: {change.backup}")
                if args.dry_run:
                    print(colorize_diff(diff_text(change), sys.stdout), end="")
            else:
                print(f"{action_label('inherited', sys.stdout)}: {target.path} (AGENTS.md를 사용합니다)")
            continue
        after, action = install_content(
            before,
            args.preset,
            args.tone,
            created=not existed,
        )
        change = apply_change(target.path, after, action, args.dry_run)
        shown_action = "preview" if args.dry_run and change.action != "unchanged" else change.action
        print(f"{action_label(shown_action, sys.stdout)}: {change.path}")
        if change.backup:
            print(f"백업: {change.backup}")
        warning = warning_for_override(target)
        if warning:
            print(f"{style('경고', BOLD, YELLOW, stream=sys.stderr)}: {warning}", file=sys.stderr)
        if args.dry_run:
            print(colorize_diff(diff_text(change), sys.stdout), end="")
    return 0


def run_remove(args: argparse.Namespace) -> int:
    inherit_agents = args.agent == "all" and args.scope == "project"
    for target in resolve_targets(args.agent, args.scope, args.directory):
        before = read_text(target.path)
        if (
            target.agent == "claude"
            and inherit_agents
            and imports_project_agents(before)
            and find_managed_span(before) is None
        ):
            print(f"{action_label('inherited', sys.stdout)}: {target.path} (AGENTS.md를 사용하므로 별도 블록이 없습니다)")
            continue
        after, action, created = remove_content(before)
        change = apply_change(
            target.path,
            after,
            action,
            args.dry_run,
            delete_empty=created,
        )
        shown_action = "preview" if args.dry_run and change.action != "unchanged" else change.action
        print(f"{action_label(shown_action, sys.stdout)}: {change.path}")
        if change.backup:
            print(f"백업: {change.backup}")
        if args.dry_run:
            print(colorize_diff(diff_text(change), sys.stdout), end="")
    return 0


def run_status(args: argparse.Namespace) -> int:
    exit_code = 0
    targets = resolve_targets(args.agent, args.scope, args.directory)
    codex_installed = False
    if args.agent == "all" and args.scope == "project":
        codex_status, _, _ = status_for(targets[0].path)
        codex_installed = codex_status == "installed"
    for target in targets:
        if target.agent == "claude" and codex_installed:
            content = read_text(target.path)
            if imports_project_agents(content) and find_managed_span(content) is None:
                print(f"{action_label('inherited', sys.stdout)}: {target.path} (AGENTS.md를 사용합니다)")
                continue
        status, preset, tone = status_for(target.path)
        detail = f" ({DISPLAY_LABELS[preset]} · {DISPLAY_LABELS[tone]})" if preset and tone else ""
        print(f"{action_label(status, sys.stdout)}: {target.path}{detail}")
        warning = warning_for_override(target)
        if warning:
            print(f"{style('경고', BOLD, YELLOW, stream=sys.stderr)}: {warning}", file=sys.stderr)
        if status != "installed":
            exit_code = 1
    return exit_code


def run_setup(directory: Path) -> int:
    choices = collect_setup(directory)
    if choices.action == "cancel":
        print("설정을 취소했습니다.")
        return 0
    if choices.action == "print":
        print(load_preset(choices.preset, choices.tone), end="")
        return 0
    if choices.agent is None or choices.scope is None:
        raise InstallError("설치 대상과 범위를 선택해 주세요.")

    args = argparse.Namespace(
        agent=choices.agent,
        scope=choices.scope,
        directory=choices.directory,
        preset=choices.preset,
        tone=choices.tone,
        dry_run=choices.action == "preview",
    )
    return run_install(args)


def main(argv: list[str] | None = None) -> int:
    arguments = sys.argv[1:] if argv is None else argv
    args = parser().parse_args(arguments)
    try:
        if args.command is None:
            if not sys.stdin.isatty() or not sys.stdout.isatty():
                parser().print_help(sys.stderr)
                print("\n오류: 인자 없이 실행하려면 터미널이 필요합니다. 자동화 환경에서는 하위 명령을 지정해 주세요.", file=sys.stderr)
                return 2
            return run_setup(Path.cwd())
        if args.command == "setup":
            return run_setup(args.directory)
        if args.command == "print":
            print(load_preset(args.preset, args.tone), end="")
            return 0
        if args.command == "install":
            return run_install(args)
        if args.command == "remove":
            return run_remove(args)
        if args.command == "status":
            return run_status(args)
    except WizardCancelled:
        print("\n설정을 취소했습니다.")
        return 130
    except KeyboardInterrupt:
        print("\n설정을 취소했습니다.", file=sys.stderr)
        return 130
    except (InstallError, OSError, UnicodeError) as error:
        print(f"{style('오류', BOLD, RED, stream=sys.stderr)}: {error}", file=sys.stderr)
        return 2
    return 2
