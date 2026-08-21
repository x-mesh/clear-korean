# Clear Korean CLI

## 대화형 설정

터미널에서 인자 없이 실행하거나 `setup` 명령을 사용한다.

```text
clear-korean
clear-korean setup [--directory PATH]
```

시작 화면에서 CLI 버전을 확인할 수 있다. 단계 표시를 따라 다음 항목을 차례로 선택한다.

1. 개발자용 또는 일반 사용자용
2. 간결한 평서형 또는 정중한 존댓말
3. 파일에 설치 또는 지침만 출력
4. Codex, Claude Code 또는 둘 다(설치할 때만)
5. 사용자 전역(기본) 또는 현재 프로젝트(설치할 때만)

지침만 출력하면 대상과 범위를 묻지 않고 바로 표준 출력으로 보낸다. 파일에 설치하면 실제 대상 파일을 확인한 뒤 설치, 미리보기, 다시 선택 또는 취소 중 하나를 고른다.

위·아래 방향키 또는 `j`/`k`로 이동하고 Enter로 선택한다. Esc나 Ctrl+C로 취소한다. 각 선택 화면은 완료 후 한 줄로 접혀 이전 선택을 빠르게 확인할 수 있다. TTY가 아닌 자동화 환경에서는 `install` 또는 `print` 하위 명령을 사용한다.

대화형 화면과 상태, 경고, 오류에는 터미널 색상을 사용한다. 파이프나 파일로 출력을 보내면 색상 코드를 넣지 않는다. 색상을 끄려면 `NO_COLOR` 환경 변수를 설정한다.

```text
NO_COLOR=1 clear-korean status --agent all --scope user
```

## 명령

### `print`

파일을 수정하지 않고 완성된 지침을 표준 출력으로 보낸다.

```text
clear-korean print [--preset developer|general] [--tone plain|polite]
```

`--preset`의 기본값은 `developer`, `--tone`의 기본값은 `plain`이다.

### `install`

선택한 파일에 Clear Korean 관리 블록을 삽입한다. 관리 블록이 이미 있으면 내용과 preset을 갱신한다.

```text
clear-korean install --agent codex|claude|all \
  --scope user|project \
  [--preset developer|general] \
  [--tone plain|polite] \
  [--directory PATH] [--dry-run]
```

`--preset`의 기본값은 `developer`, `--tone`의 기본값은 `plain`이다.

대상 경로:

| agent | user scope | project scope |
| --- | --- | --- |
| Codex | `$CODEX_HOME/AGENTS.md` 또는 `~/.codex/AGENTS.md` | `<directory>/AGENTS.md` |
| Claude Code | `~/.claude/CLAUDE.md` | `<directory>/CLAUDE.md` |

`--directory`는 project scope에만 영향을 주며 기본값은 현재 디렉터리다.

project scope에서 `--agent all`을 사용하고 `CLAUDE.md`가 `@AGENTS.md`를 가져오고 있다면, CLI는 같은 지침을 `CLAUDE.md`에 다시 삽입하지 않는다. Codex와 Claude Code가 하나의 `AGENTS.md`를 공유하게 한다.

### `status`

설치 여부와 설치된 preset을 확인한다. 선택한 대상 중 하나라도 설치되지 않았으면 종료 코드 1을 반환한다.

```text
clear-korean status --agent codex|claude|all --scope user|project [--directory PATH]
```

### `remove`

Clear Korean 관리 블록만 제거한다. 기존 사용자가 작성한 내용은 보존한다.

```text
clear-korean remove --agent codex|claude|all \
  --scope user|project [--directory PATH] [--dry-run]
```

## 파일 안전 정책

- 기존 파일은 변경 전에 같은 디렉터리에 백업한다.
- 임시 파일을 완전히 기록한 뒤 원자적으로 교체한다.
- 기존 파일의 권한을 유지한다.
- Clear Korean 마커 밖의 내용은 수정하지 않는다.
- 중복 설치는 새 블록을 추가하지 않고 기존 블록을 갱신한다.
- 손상되거나 중복된 마커는 자동으로 복구하지 않고 오류를 반환한다.
- 심볼릭 링크는 대상이 예상과 다를 수 있으므로 수정하지 않는다.
- `--dry-run`은 파일을 쓰거나 백업하지 않고 unified diff만 출력한다.
