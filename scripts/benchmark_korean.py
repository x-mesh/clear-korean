#!/usr/bin/env python3
from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import math
import os
import re
import statistics
import subprocess
import threading
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROJECT_DIR = Path(__file__).resolve().parents[1]
DIMENSIONS = ("naturalness", "clarity", "style_fit", "concision", "fidelity")
CRITICAL_FAILURES = ("none", "missing_answer", "fabrication", "format", "tone")
STATUS_ONLY_RE = re.compile(
    r"^(?:요청한 |해당 )?(?:작업|답변|설명|비교|작성).{0,20}(?:완료|마쳤|제공했).{0,30}$"
)


@dataclass(frozen=True)
class BenchmarkCase:
    id: str
    preset: str
    tone: str
    genre: str
    prompt: str
    reference: str
    criteria: tuple[str, ...]
    required: tuple[tuple[str, ...], ...]
    forbidden: tuple[str, ...]


def load_cases(path: Path) -> list[BenchmarkCase]:
    cases = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            data = json.loads(line)
        except json.JSONDecodeError as error:
            raise ValueError(f"{path}:{line_number}: {error}") from error
        cases.append(BenchmarkCase(
            id=data["id"],
            preset=data["preset"],
            tone=data["tone"],
            genre=data["genre"],
            prompt=data["prompt"],
            reference=data["reference"],
            criteria=tuple(data["criteria"]),
            required=tuple(tuple(group) for group in data.get("required", ())),
            forbidden=tuple(data.get("forbidden", ())),
        ))
    return cases


def corpus_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def portable_path(path: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(PROJECT_DIR).as_posix() or "."
    except ValueError:
        return path.as_posix()


def run_codex(
    workdir: Path, prompt: str, output_path: Path, *, model: str | None = None,
) -> str:
    command = [
        str(PROJECT_DIR / "scripts/codex-isolated"),
        "--workdir", str(workdir), "-s", "read-only", "-o", str(output_path), prompt,
    ]
    last_error = ""
    for _ in range(3):
        output_path.unlink(missing_ok=True)
        environment = os.environ.copy()
        if model is not None:
            environment["CODEX_ISOLATED_MODEL"] = model
        completed = subprocess.run(
            command, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True, timeout=300,
            env=environment,
        )
        if completed.returncode == 0 and output_path.exists():
            response = output_path.read_text(encoding="utf-8").strip()
            if response:
                return response
        last_error = completed.stderr[-2000:]
    raise RuntimeError(last_error or "Codex가 빈 응답을 반환했습니다.")


def check_response(case: BenchmarkCase, response: str) -> dict[str, Any]:
    checks = []
    for index, alternatives in enumerate(case.required, 1):
        checks.append({
            "name": f"required_{index}",
            "passed": any(re.search(pattern, response, re.IGNORECASE) for pattern in alternatives),
        })
    for index, pattern in enumerate(case.forbidden, 1):
        checks.append({
            "name": f"forbidden_{index}",
            "passed": re.search(pattern, response, re.IGNORECASE) is None,
        })
    checks.append({"name": "has_answer", "passed": len(response.strip()) >= 10})
    checks.append({"name": "not_status_only", "passed": STATUS_ONLY_RE.fullmatch(response.strip()) is None})
    passed = sum(check["passed"] for check in checks)
    return {
        "score": 100.0 * passed / len(checks),
        "passed": passed,
        "total": len(checks),
        "checks": checks,
    }


def judge_prompt(case: BenchmarkCase, response: str) -> str:
    tone = (
        "간결한 평서형이 기본이다. 존댓말이 아니라는 이유만으로 감점하지 않는다."
        if case.tone == "plain"
        else "정중한 존댓말이 기본이다. 사용자가 별도 말투를 지정했다면 그 요청을 우선한다."
    )
    criteria = "\n".join(f"- {item}" for item in case.criteria)
    return f"""다음 답변의 한국어 문체 품질을 절대 기준으로 평가하세요.
기준 답안은 필요한 정보량과 품질의 기준이며, 표현이 다르다는 이유만으로 감점하지 마세요.

사용자 요청:
{case.prompt}

기준 답안:
{case.reference}

사례별 기준:
{criteria}

기본 말투:
{tone}

평가할 답변:
{response}

각 항목을 1점부터 5점까지 평가하세요.
- naturalness: 번역체, 전보식 문장, 어색한 조사와 어미가 없는가
- clarity: 대상, 조건, 원인, 결과와 문장 관계가 분명한가
- style_fit: 장르, 독자, 높임법과 요청한 형식을 지켰는가
- concision: 필수 정보를 보존하면서 군더더기와 반복이 없는가
- fidelity: 주어진 사실을 보존하고 없는 사실이나 원인을 만들지 않았는가

치명적 실패도 하나 고르세요.
- none: 치명적 실패 없음
- missing_answer: 요청한 답이나 결과물 자체가 없음
- fabrication: 핵심 사실이나 원인을 지어냄
- format: 요청한 형식을 심하게 위반해 사용할 수 없음
- tone: 요청한 높임법이나 말투를 심하게 위반함

최종 답변은 설명이나 마크다운 없이 정확히 세 줄만 출력하세요.
SCORES<TAB>naturalness<TAB>clarity<TAB>style_fit<TAB>concision<TAB>fidelity
CRITICAL<TAB>none 또는 missing_answer 또는 fabrication 또는 format 또는 tone
REASON<TAB>판정 이유 한 문장"""


def parse_judgment(response: str) -> dict[str, Any]:
    scores = None
    critical = None
    reason = None
    for line in (line.strip() for line in response.splitlines() if line.strip()):
        fields = line.split("\t")
        if len(fields) == 6 and fields[0] == "SCORES":
            values = []
            for dimension, value in zip(DIMENSIONS, fields[1:], strict=True):
                if "=" in value:
                    name, value = value.split("=", 1)
                    if name != dimension:
                        raise ValueError(f"점수 항목 순서가 올바르지 않습니다: {name}")
                values.append(int(value))
            if not all(1 <= value <= 5 for value in values):
                raise ValueError("점수가 범위를 벗어났습니다.")
            scores = dict(zip(DIMENSIONS, values, strict=True))
        elif len(fields) == 2 and fields[0] == "CRITICAL" and fields[1] in CRITICAL_FAILURES:
            critical = fields[1]
        elif len(fields) == 2 and fields[0] == "REASON":
            reason = fields[1]
    if scores is None or critical is None or not reason:
        raise ValueError(f"판정 형식이 올바르지 않습니다: {response[:300]}")
    return {"scores": scores, "critical": critical, "reason": reason}


def aggregate_results(
    cases: list[BenchmarkCase],
    generations: list[dict[str, Any]],
    judgments: list[dict[str, Any]],
) -> dict[str, Any]:
    samples = []
    for generation in generations:
        rows = [
            row for row in judgments
            if row["case"] == generation["case"] and row["repetition"] == generation["repetition"]
        ]
        mean_scores = {
            dimension: statistics.mean(row["scores"][dimension] for row in rows)
            for dimension in DIMENSIONS
        }
        critical_counts = Counter(row["critical"] for row in rows)
        critical = critical_counts.most_common(1)[0][0]
        judge_score = statistics.mean(mean_scores.values()) * 20
        composite = judge_score * 0.8 + generation["checks"]["score"] * 0.2
        if critical != "none":
            composite = min(composite, 50.0)
        samples.append({
            **generation,
            "scores": mean_scores,
            "judge_score": judge_score,
            "composite": composite,
            "critical": critical,
            "critical_counts": dict(critical_counts),
            "judge_reasons": [row["reason"] for row in rows],
        })

    case_map = {case.id: case for case in cases}
    case_scores = []
    for case in cases:
        rows = [row for row in samples if row["case"] == case.id]
        composites = [row["composite"] for row in rows]
        standard_deviation = statistics.stdev(composites) if len(composites) > 1 else 0.0
        case_scores.append({
            "case": case.id,
            "genre": case.genre,
            "composite": statistics.mean(composites),
            "sample_count": len(composites),
            "standard_deviation": standard_deviation,
            "standard_error": standard_deviation / math.sqrt(len(composites)),
            "checks": statistics.mean(row["checks"]["score"] for row in rows),
            "scores": {
                dimension: statistics.mean(row["scores"][dimension] for row in rows)
                for dimension in DIMENSIONS
            },
            "critical_failures": sum(row["critical"] != "none" for row in rows),
        })

    by_genre: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in case_scores:
        by_genre[row["genre"]].append(row)
    genre_scores = {
        genre: statistics.mean(row["composite"] for row in rows)
        for genre, rows in sorted(by_genre.items())
    }
    return {
        "overall": {
            "composite": statistics.mean(row["composite"] for row in samples),
            "checks": statistics.mean(row["checks"]["score"] for row in samples),
            "scores": {
                dimension: statistics.mean(row["scores"][dimension] for row in samples)
                for dimension in DIMENSIONS
            },
            "critical_failures": sum(row["critical"] != "none" for row in samples),
        },
        "genres": genre_scores,
        "cases": case_scores,
        "samples": samples,
    }


def compare_summaries(current: dict[str, Any], baseline: dict[str, Any]) -> dict[str, Any]:
    current_score = current["aggregate"]["overall"]
    baseline_score = baseline["aggregate"]["overall"]
    dimensions = {
        dimension: current_score["scores"][dimension] - baseline_score["scores"][dimension]
        for dimension in DIMENSIONS
    }
    genre_deltas = {
        genre: current["aggregate"]["genres"][genre] - score
        for genre, score in baseline["aggregate"]["genres"].items()
        if genre in current["aggregate"]["genres"]
    }
    regressions = []
    warnings = []
    composite_delta = current_score["composite"] - baseline_score["composite"]
    if composite_delta < -1.0:
        regressions.append(f"전체 점수가 {composite_delta:.2f}점 하락했습니다.")
    for dimension, delta in dimensions.items():
        if delta < -0.15:
            regressions.append(f"{dimension} 점수가 {delta:.2f}점 하락했습니다.")
    for genre, delta in genre_deltas.items():
        if delta < -3.0:
            current_rows = [
                row for row in current["aggregate"].get("cases", ()) if row["genre"] == genre
            ]
            baseline_rows = [
                row for row in baseline["aggregate"].get("cases", ()) if row["genre"] == genre
            ]
            errors_available = current_rows and baseline_rows and all(
                "standard_error" in row for row in current_rows + baseline_rows
            )
            if errors_available:
                standard_error = math.sqrt(
                    sum(row["standard_error"] ** 2 for row in current_rows + baseline_rows)
                )
                upper_bound = delta + 1.645 * standard_error
                if upper_bound < -3.0:
                    regressions.append(
                        f"{genre} 점수가 {delta:.2f}점 하락했습니다"
                        f"(95% 단측 상한 {upper_bound:.2f}점)."
                    )
                else:
                    warnings.append(
                        f"{genre} 점수가 {delta:.2f}점 낮지만 표본 변동 범위에 있습니다"
                        f"(95% 단측 상한 {upper_bound:.2f}점). 반복 평가가 필요합니다."
                    )
            else:
                regressions.append(f"{genre} 점수가 {delta:.2f}점 하락했습니다.")
    critical_delta = current_score["critical_failures"] - baseline_score["critical_failures"]
    if critical_delta > 0:
        regressions.append(f"치명적 실패가 {critical_delta}건 늘었습니다.")
    return {
        "baseline_id": baseline["run"]["id"],
        "composite_delta": composite_delta,
        "dimension_deltas": dimensions,
        "genre_deltas": genre_deltas,
        "critical_failure_delta": critical_delta,
        "warnings": warnings,
        "regressions": regressions,
        "passed": not regressions,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--suite", type=Path, default=PROJECT_DIR / "tests/benchmark/v1/cases.jsonl")
    parser.add_argument("--candidate-root", type=Path, default=PROJECT_DIR)
    parser.add_argument(
        "--condition", choices=("candidate", "unguided", "reference"), default="candidate",
        help="candidate는 지정한 preset, unguided는 지침 없음, reference는 사람 기준 답안을 평가합니다.",
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--repetitions", type=int, default=5)
    parser.add_argument("--judge-repetitions", type=int, default=5)
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--case", action="append", dest="selected_cases")
    parser.add_argument("--compare", type=Path)
    parser.add_argument("--enforce", action="store_true")
    args = parser.parse_args()

    env_key = os.environ.get("CODEX_ISOLATED_ENV_KEY", "CODEX_ISOLATED_API_KEY")
    if not os.environ.get("CODEX_ISOLATED_BASE_URL"):
        parser.error("CODEX_ISOLATED_BASE_URL이 필요합니다.")
    if not os.environ.get(env_key):
        parser.error(f"{env_key}가 필요합니다.")
    cases = load_cases(args.suite)
    if args.selected_cases:
        selected = set(args.selected_cases)
        cases = [case for case in cases if case.id in selected]
        missing = selected - {case.id for case in cases}
        if missing:
            parser.error(f"알 수 없는 사례입니다: {', '.join(sorted(missing))}")

    args.output.mkdir(parents=True, exist_ok=True)
    raw_dir = args.output / "raw"
    raw_dir.mkdir(exist_ok=True)
    generation_model = os.environ.get("CODEX_ISOLATED_MODEL", "gpt-5.6-sol")
    judge_model = os.environ.get("CODEX_ISOLATED_JUDGE_MODEL", generation_model)
    lock = threading.Lock()
    completed = 0

    jobs = [(case, repetition) for case in cases for repetition in range(1, args.repetitions + 1)]

    def generate(job: tuple[BenchmarkCase, int]) -> dict[str, Any]:
        nonlocal completed
        case, repetition = job
        workdir = raw_dir / case.id / str(repetition) / "candidate"
        workdir.mkdir(parents=True, exist_ok=True)
        preset_hash = None
        if args.condition == "candidate":
            preset = args.candidate_root / "presets" / case.preset / case.tone / "AGENTS.md"
            if not preset.is_file():
                raise FileNotFoundError(preset)
            preset_content = preset.read_text(encoding="utf-8")
            (workdir / "AGENTS.md").write_text(preset_content, encoding="utf-8")
            preset_hash = hashlib.sha256(preset_content.encode()).hexdigest()
        else:
            (workdir / "AGENTS.md").unlink(missing_ok=True)
        prompt = (
            f"{case.prompt}\n\n"
            f"[내부 benchmark 식별자: {case.id}-{repetition}. 답변에는 이 식별자를 포함하지 마세요.]"
        )
        input_data = {
            "case": case.id, "prompt": prompt,
            "condition": args.condition,
            "generation_model": generation_model,
            "preset_hash": preset_hash,
            "corpus_hash": corpus_hash(args.suite),
        }
        input_path = workdir / "input.json"
        output_path = workdir / "response.txt"
        existing = json.loads(input_path.read_text(encoding="utf-8")) if input_path.exists() else None
        if args.condition == "reference":
            response = case.reference
            output_path.write_text(response, encoding="utf-8")
            input_path.write_text(json.dumps(input_data, ensure_ascii=False, indent=2), encoding="utf-8")
        elif existing == input_data and output_path.exists() and output_path.read_text(encoding="utf-8").strip():
            response = output_path.read_text(encoding="utf-8").strip()
        else:
            response = run_codex(workdir, prompt, output_path)
            input_path.write_text(json.dumps(input_data, ensure_ascii=False, indent=2), encoding="utf-8")
        result = {
            "case": case.id, "genre": case.genre, "repetition": repetition,
            "response": response, "checks": check_response(case, response),
        }
        with lock:
            completed += 1
            print(f"생성 {completed}/{len(jobs)}: {case.id} {repetition}", flush=True)
        return result

    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as executor:
        generations = list(executor.map(generate, jobs))

    judge_jobs = [
        (case, repetition, judge_repetition)
        for case in cases
        for repetition in range(1, args.repetitions + 1)
        for judge_repetition in range(1, args.judge_repetitions + 1)
    ]
    responses = {(row["case"], row["repetition"]): row["response"] for row in generations}
    completed = 0

    def judge(job: tuple[BenchmarkCase, int, int]) -> dict[str, Any]:
        nonlocal completed
        case, repetition, judge_repetition = job
        response = responses[(case.id, repetition)]
        workdir = raw_dir / case.id / str(repetition) / "judge" / str(judge_repetition)
        workdir.mkdir(parents=True, exist_ok=True)
        prompt = judge_prompt(case, response)
        input_data = {
            "case": case.id, "response_hash": hashlib.sha256(response.encode()).hexdigest(),
            "prompt_hash": hashlib.sha256(prompt.encode()).hexdigest(),
            "judge_model": judge_model,
        }
        input_path = workdir / "input.json"
        parsed_path = workdir / "parsed.json"
        existing = json.loads(input_path.read_text(encoding="utf-8")) if input_path.exists() else None
        if existing == input_data and parsed_path.exists():
            parsed = json.loads(parsed_path.read_text(encoding="utf-8"))
        else:
            last_error: Exception | None = None
            for _ in range(3):
                try:
                    parsed = parse_judgment(run_codex(
                        workdir, prompt, workdir / "response.txt", model=judge_model,
                    ))
                    parsed_path.write_text(json.dumps(parsed, ensure_ascii=False, indent=2), encoding="utf-8")
                    input_path.write_text(json.dumps(input_data, ensure_ascii=False, indent=2), encoding="utf-8")
                    break
                except (RuntimeError, ValueError) as error:
                    last_error = error
            else:
                raise RuntimeError(f"판정 실패: {case.id} {repetition}-{judge_repetition}: {last_error}")
        with lock:
            completed += 1
            print(f"판정 {completed}/{len(judge_jobs)}: {case.id} {repetition}-{judge_repetition}", flush=True)
        return {
            "case": case.id, "repetition": repetition, "judge_repetition": judge_repetition,
            **parsed,
        }

    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as executor:
        judgments = list(executor.map(judge, judge_jobs))

    result = {
        "run": {
            "id": args.output.name, "evaluated_at": datetime.now(timezone.utc).isoformat(),
            "suite": portable_path(args.suite), "corpus_hash": corpus_hash(args.suite),
            "candidate_root": portable_path(args.candidate_root),
            "condition": args.condition,
            "model": generation_model,
            "judge_model": judge_model,
            "provider": os.environ.get("CODEX_ISOLATED_PROVIDER", "custom-provider"),
            "reasoning_effort": os.environ.get("CODEX_ISOLATED_EFFORT", "xhigh"),
            "repetitions": args.repetitions, "judge_repetitions": args.judge_repetitions,
        },
        "aggregate": aggregate_results(cases, generations, judgments),
    }
    if args.compare:
        baseline = json.loads(args.compare.read_text(encoding="utf-8"))
        if baseline["run"]["corpus_hash"] != result["run"]["corpus_hash"]:
            parser.error("benchmark corpus hash가 기준점과 다릅니다. suite 버전을 확인하세요.")
        for key in ("model", "provider", "reasoning_effort", "repetitions", "judge_repetitions"):
            if baseline["run"][key] != result["run"][key]:
                parser.error(f"{key}가 기준점과 다릅니다. 같은 실행 조건을 사용하세요.")
        result["comparison"] = compare_summaries(result, baseline)
    output_path = args.output / "summary.json"
    output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(output_path)
    if args.enforce and result.get("comparison", {}).get("regressions"):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
