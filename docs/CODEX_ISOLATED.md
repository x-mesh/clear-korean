# Codex 격리 실행

`codex-isolated`는 지정한 provider 설정만 유지하고 다음 전역 상태를 제외한 채 `codex exec`를 실행한다.

- 사용자 `AGENTS.md`
- Codex 훅과 MCP
- 사용자 설정의 기본 프롬프트와 모델 옵션
- 기존 세션 기록

기본 작업 디렉터리는 매번 새로 만드는 빈 임시 디렉터리다. `--workdir`를 지정하면 해당 디렉터리의 `AGENTS.md`는 의도적으로 로드된다.

## 전역 설치

```bash
install -m 755 scripts/codex-isolated ~/.local/bin/codex-isolated
```

`~/.local/bin`이 `PATH`에 포함돼 있으면 어느 디렉터리에서든 실행할 수 있다.

```bash
codex-isolated "DNS 캐시를 두 문장으로 설명해줘"
codex-isolated --workdir /tmp/test-project "프로젝트 지침을 적용해 답해줘"
```

provider URL과 API 키를 환경 변수로 지정한다. 모델과 reasoning effort도 바꿀 수 있다.

```bash
export CODEX_ISOLATED_BASE_URL=https://provider.example/v1
export CODEX_ISOLATED_API_KEY=your-api-key
CODEX_ISOLATED_MODEL=gpt-5.6-sol \
CODEX_ISOLATED_EFFORT=high \
codex-isolated "질문"
```

지원하는 환경 변수와 전달 명령은 `codex-isolated --help`와 `codex-isolated --show-command`로 확인할 수 있다. API 키 값은 명령에 출력하지 않는다.
