# 행동 테스트

`cases.tsv`는 개발자용과 일반 사용자용 지침이 지켜야 할 대표 동작을 정의한다. `principle` 열은 각 사례가 검증하는 규칙을 나타낸다. 단위 테스트는 형식, 중복 ID와 핵심 규칙의 누락을 확인하고, 행동 테스트는 실제 모델의 응답을 사람이 평가한다.

## 실행 방법

1. 비어 있는 임시 디렉터리 두 개를 만든다.
2. 개발자용 또는 일반 사용자용 `AGENTS.md`를 해당 디렉터리에 복사한다.
3. 그 디렉터리에서 새 Codex 세션을 시작하고 `cases.tsv`에서 해당 preset의 프롬프트를 실행한다.
4. 응답이 `expectation`을 만족하는지 확인한다.

예시:

```bash
test_dir="$(mktemp -d)"
cp presets/developer/AGENTS.md "$test_dir/AGENTS.md"
codex exec --ephemeral --skip-git-repo-check \
  --cd "$test_dir" \
  "배포가 느리지만 원인은 아직 확인하지 못했다. 두 문장 이내로 보고해줘."
```

모델 응답은 비결정적이므로 한 번의 성공만으로 회귀가 없다고 단정하지 않는다. 릴리스 전에는 각 핵심 사례를 여러 번 실행하고, 모델·버전·실행일을 결과에 기록한다.

## 문체 비교 평가

`style_cases.tsv`에는 교정 요청이 아닌 실제 작성 과제가 있다. `scripts/evaluate_styles.py`는 지침 없는 기준군과 Clear Korean 적용군을 반복 생성하고, 출처를 가린 답변 쌍을 Codex가 세 번씩 판정한다. 실행법과 2026-08-20 결과는 [`docs/STYLE_EVALUATION.md`](../docs/STYLE_EVALUATION.md)에 정리했다.

평가기는 custom-provider provider만 유지하는 `scripts/codex-isolated`를 사용한다. 전역 설치와 격리 범위는 [`docs/CODEX_ISOLATED.md`](../docs/CODEX_ISOLATED.md)에서 설명한다.

## 고정 benchmark와 회귀 검사

`benchmark/v1/cases.jsonl`에는 26개 문체의 고정 과제, 사람 기준 답안과 사실 보존 검사가 있다. `scripts/benchmark_korean.py`는 자연스러움, 명확성, 문체 적합성, 간결성과 사실 보존을 반복 평가하고 이전 릴리스보다 나빠진 항목을 검사한다.

```bash
python3 -m unittest tests.unit.test_benchmark
python3 scripts/benchmark_korean.py \
  --condition candidate \
  --output tests/results/candidate-next \
  --repetitions 5 --judge-repetitions 5 --workers 8 \
  --compare tests/benchmark/v1/baselines/clear-korean-0.2.4-gpt-5.6-sol-r5.json \
  --enforce
```

기준점의 의미, 점수와 suite 갱신 규칙은 [`docs/BENCHMARK.md`](../docs/BENCHMARK.md)에 정리했다. 모델 실행 결과는 `tests/results/`에 보관하며 Git에는 넣지 않는다.

## 2026-08-19 초기 검증

- 환경: Codex CLI 0.148.0, GPT-5.6 Sol, reasoning effort xhigh
- 개발자용 오류 보고: 확인된 타입 불일치와 다음 조치만 한 문단으로 보고했다.
- 개발자용 숙련자 설명: overlay2의 기본 정의를 생략하고 첫 쓰기의 copy-up 비용부터 설명했다.
- 일반 사용자용 짧은 설명: DNS 캐시의 속도와 부하 감소 효과를 두 문장으로 설명했다.
- 일반 사용자용 문체 우선: 기본 평서형보다 사용자가 요청한 정중한 존댓말을 우선했다.
- 결과: 실행한 네 사례 모두 기대 동작을 만족했다.

세션과 핀 상태를 알리는 문구는 테스트 환경의 외부 훅에서 추가한 것이므로 Clear Korean의 출력으로 평가하지 않았다.
