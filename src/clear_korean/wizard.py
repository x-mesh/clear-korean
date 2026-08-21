from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sys
from typing import TextIO

from . import __version__
from .console import BOLD, CYAN, DIM, style
from .installer import resolve_targets
from .interactive import Option, select_option


DISPLAY_LABELS = {
    "developer": "개발자용",
    "general": "일반 사용자용",
    "plain": "간결한 평서형",
    "polite": "정중한 존댓말",
    "all": "Codex와 Claude Code",
    "codex": "Codex",
    "claude": "Claude Code",
    "project": "현재 프로젝트",
    "user": "사용자 전역",
}


@dataclass(frozen=True)
class SetupChoices:
    preset: str
    tone: str
    agent: str | None
    scope: str | None
    action: str
    directory: Path


def collect_setup(directory: Path, *, output: TextIO | None = None) -> SetupChoices:
    if output is None:
        output = sys.stdout
    print(style(f"Clear Korean {__version__}", BOLD, CYAN, stream=output), file=output)
    print(style("AI가 한국어로 짧고 명확하게 답하도록 돕습니다.", DIM, stream=output), file=output)
    print(file=output)

    while True:
        preset = select_option(
            "용도를 선택하세요",
            (
                Option("개발자용", "developer", "코딩 · 기술 설명 · 작업 보고"),
                Option("일반 사용자용", "general", "질문 · 조사 · 문서 작성"),
            ), output=output, step=(1, 5),
        )
        tone = select_option(
            "말투를 선택하세요",
            (
                Option("간결한 평서형", "plain", "존댓말을 기본으로 사용하지 않음"),
                Option("정중한 존댓말", "polite", "간결한 존댓말을 유지"),
            ), output=output, step=(2, 5),
        )
        mode = select_option(
            "사용 방법을 선택하세요",
            (
                Option("파일에 설치", "install", "기존 파일에 관리 블록으로 추가"),
                Option("지침만 출력", "print", "파일을 바꾸지 않고 표준 출력에 표시"),
            ), output=output, step=(3, 5),
        )
        if mode == "print":
            return SetupChoices(preset, tone, None, None, "print", directory)

        agent = select_option(
            "적용 대상을 선택하세요",
            (
                Option("Codex와 Claude Code", "all", "두 환경에 함께 적용"),
                Option("Codex", "codex", "AGENTS.md"),
                Option("Claude Code", "claude", "CLAUDE.md"),
            ), output=output, step=(4, 5),
        )
        scope = select_option(
            "적용 범위를 선택하세요",
            (
                Option("사용자 전역", "user", "모든 프로젝트에 적용"),
                Option("현재 프로젝트", "project", str(directory.resolve())),
            ), output=output, step=(5, 5),
        )

        paths = [str(target.path) for target in resolve_targets(agent, scope, directory)]
        print(file=output)
        print(style("설정 확인", BOLD, CYAN, stream=output), file=output)
        print(f"  답변  {DISPLAY_LABELS[preset]} · {DISPLAY_LABELS[tone]}", file=output)
        print(f"  대상  {DISPLAY_LABELS[agent]} · {DISPLAY_LABELS[scope]}", file=output)
        for index, path in enumerate(paths):
            label = "파일" if index == 0 else "    "
            print(f"  {label}  {path}", file=output)
        print(file=output)

        action = select_option(
            "실행 방법을 선택하세요",
            (
                Option("설치하기", "install", "백업 후 관리 블록을 삽입하거나 갱신"),
                Option("먼저 미리보기", "preview", "파일을 바꾸지 않고 차이만 확인"),
                Option("선택 다시 하기", "restart"),
                Option("취소", "cancel"),
            ), output=output,
        )
        if action != "restart":
            return SetupChoices(preset, tone, agent, scope, action, directory)
        print(style("선택을 다시 시작합니다.", DIM, stream=output), file=output)
        print(file=output)
