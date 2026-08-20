# Clear Korean 저장소 작업 지침

- `instructions/`의 공통 규칙과 대상별 규칙이 정본이다.
- `presets/`의 파일을 직접 수정하지 않는다. `./scripts/build.sh`로 생성한다.
- CLI에 포함되는 `src/clear_korean/presets/`의 파일도 직접 수정하지 않는다. `./scripts/build.sh`로 생성한다.
- 공통 동작은 `instructions/core.md`에 두고, 개발자 또는 일반 사용자에게만 필요한 규칙은 해당 파일에 둔다.
- 지침을 변경하면 `./scripts/check.sh`를 실행한다.
- CLI 동작을 변경하면 `tests/unit/`의 단위 테스트와 `uvx --from . clear-korean` smoke test를 실행한다.
- 행동 변화가 있는 규칙을 추가하면 `tests/cases.tsv`에 대표 사례를 추가한다.
- 지침 자체도 Clear Korean의 원칙에 맞게 간결한 평서형으로 작성한다.
- 플랫폼 전용 기능을 공통 지침에 넣지 않는다. 설치와 로딩 방법은 README에서 다룬다.
