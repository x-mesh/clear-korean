#!/usr/bin/env python3
from __future__ import annotations

import argparse
import concurrent.futures
import csv
import hashlib
import json
import os
import subprocess
import threading
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROJECT_DIR = Path(__file__).resolve().parents[1]
SCORE_NAMES = ("naturalness", "clarity", "style_fit", "concision", "fidelity")


@dataclass(frozen=True)
class Case:
    id: str
    preset: str
    tone: str
    genre: str
    prompt: str
    criteria: str


def load_cases(path: Path) -> list[Case]:
    with path.open(encoding="utf-8", newline="") as handle:
        return [Case(**row) for row in csv.DictReader(handle, delimiter="\t")]


def run_codex(
    workdir: Path,
    prompt: str,
    output_path: Path,
) -> str:
    command = [
        str(PROJECT_DIR / "scripts/codex-isolated"),
        "--workdir", str(workdir), "-s", "read-only", "-o", str(output_path),
    ]
    command.append(prompt)
    last_error = ""
    for _ in range(3):
        output_path.unlink(missing_ok=True)
        completed = subprocess.run(
            command,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
            timeout=300,
        )
        if completed.returncode == 0 and output_path.exists():
            response = output_path.read_text(encoding="utf-8").strip()
            if response:
                return response
        last_error = completed.stderr[-2000:]
    raise RuntimeError(last_error or "Codex가 빈 응답을 반환했습니다.")


def judge_prompt(case: Case, a: str, b: str) -> str:
    tone_requirement = (
        "간결한 평서형이 기본입니다. 존댓말이 아니라는 이유로 감점하지 마세요. 다만 사용자 요청과 장르상 존댓말이 필요한 결과물은 예외입니다."
        if case.tone == "plain"
        else "정중한 존댓말이 기본입니다. 사용자가 반말 등 다른 말투를 명시한 결과물은 그 요청을 우선합니다."
    )
    return f"""다음 두 답변을 출처를 추측하지 말고 독립적으로 평가하세요.

사용자 요청:
{case.prompt}

이 문체의 핵심 기준:
{case.criteria}

적용한 기본 말투:
{tone_requirement}

답변 A:
{a}

답변 B:
{b}

각 답변을 다음 기준으로 1점부터 5점까지 평가하세요.
- naturalness: 번역체, 전보식 표현, 어색한 조사·어미 없이 한국어가 자연스러운가
- clarity: 대상, 조건, 원인과 결과가 분명한가
- style_fit: 요청한 장르, 독자, 높임법과 형식을 지켰는가
- concision: 중요한 의미를 보존하면서 군더더기와 반복이 없는가
- fidelity: 주어진 사실을 보존하고 없는 사실이나 원인을 만들지 않았는가

전체 품질이 실질적으로 같은 경우에만 tie를 선택하세요. 길거나 화려하다는 이유만으로 높은 점수를 주지 마세요.

최종 답변은 설명이나 마크다운 없이 정확히 다음 네 줄만 출력하세요. 점수는 1부터 5까지의 정수입니다.
A<TAB>naturalness<TAB>clarity<TAB>style_fit<TAB>concision<TAB>fidelity
B<TAB>naturalness<TAB>clarity<TAB>style_fit<TAB>concision<TAB>fidelity
WINNER<TAB>A 또는 B 또는 tie
REASON<TAB>판정 이유 한 문장"""


def parse_judgment(response: str) -> dict[str, Any]:
    lines = [line.strip() for line in response.splitlines() if line.strip()]
    score_lines = {}
    winner = None
    reason = None
    for line in lines:
        fields = line.split("\t")
        if len(fields) == 6 and fields[0] in {"A", "B"}:
            scores = [int(value) for value in fields[1:]]
            if not all(1 <= score <= 5 for score in scores):
                raise ValueError("점수가 범위를 벗어났습니다.")
            score_lines[fields[0]] = dict(zip(SCORE_NAMES, scores, strict=True))
        elif len(fields) == 2 and fields[0] == "WINNER" and fields[1] in {"A", "B", "tie"}:
            winner = fields[1]
        elif len(fields) == 2 and fields[0] == "REASON":
            reason = fields[1]
    if set(score_lines) != {"A", "B"} or winner is None or not reason:
        raise ValueError(f"판정 형식이 올바르지 않습니다: {response[:300]}")
    return {"a": score_lines["A"], "b": score_lines["B"], "winner": winner, "reason": reason}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", type=Path, default=PROJECT_DIR / "tests/style_cases.tsv")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--repetitions", type=int, default=3)
    parser.add_argument("--judge-repetitions", type=int, default=3)
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--case", action="append", dest="selected_cases")
    args = parser.parse_args()

    env_key = os.environ.get("CODEX_ISOLATED_ENV_KEY", "CODEX_ISOLATED_API_KEY")
    if not os.environ.get("CODEX_ISOLATED_BASE_URL"):
        parser.error("CODEX_ISOLATED_BASE_URL이 필요합니다.")
    if not os.environ.get(env_key):
        parser.error(f"{env_key}가 필요합니다.")

    cases = load_cases(args.cases)
    if args.selected_cases:
        selected = set(args.selected_cases)
        cases = [case for case in cases if case.id in selected]
        missing = selected - {case.id for case in cases}
        if missing:
            parser.error(f"알 수 없는 사례입니다: {', '.join(sorted(missing))}")
    args.output.mkdir(parents=True, exist_ok=True)
    raw_dir = args.output / "raw"
    raw_dir.mkdir(exist_ok=True)
    lock = threading.Lock()
    completed_count = 0

    generation_jobs: list[tuple[Case, int, str]] = []
    for case in cases:
        for repetition in range(1, args.repetitions + 1):
            for condition in ("baseline", "treatment"):
                generation_jobs.append((case, repetition, condition))

    def generate(job: tuple[Case, int, str]) -> dict[str, Any]:
        nonlocal completed_count
        case, repetition, condition = job
        job_dir = raw_dir / case.id / str(repetition) / condition
        job_dir.mkdir(parents=True, exist_ok=True)
        if condition == "treatment":
            preset = PROJECT_DIR / "presets" / case.preset / case.tone / "AGENTS.md"
            (job_dir / "AGENTS.md").write_text(preset.read_text(encoding="utf-8"), encoding="utf-8")
            preset_hash = hashlib.sha256(preset.read_bytes()).hexdigest()
        else:
            preset_hash = None
        output_path = job_dir / "response.txt"
        evaluation_prompt = (
            f"{case.prompt}\n\n"
            f"[내부 평가 식별자: {case.id}-{repetition}-{condition}. "
            "답변에는 이 식별자를 포함하지 마세요.]"
        )
        input_path = job_dir / "input.json"
        input_data = {
            "prompt": case.prompt,
            "evaluation_prompt": evaluation_prompt,
            "condition": condition,
            "preset_hash": preset_hash,
        }
        current_input = json.loads(input_path.read_text(encoding="utf-8")) if input_path.exists() else None
        if current_input == input_data and output_path.exists() and output_path.read_text(encoding="utf-8").strip():
            response = output_path.read_text(encoding="utf-8").strip()
        else:
            response = run_codex(job_dir, evaluation_prompt, output_path)
            input_path.write_text(json.dumps(input_data, ensure_ascii=False, indent=2), encoding="utf-8")
        with lock:
            completed_count += 1
            print(f"생성 {completed_count}/{len(generation_jobs)}: {case.id} {repetition} {condition}", flush=True)
        return {"case": case.id, "repetition": repetition, "condition": condition, "response": response}

    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as executor:
        generations = list(executor.map(generate, generation_jobs))

    responses = {(row["case"], row["repetition"], row["condition"]): row["response"] for row in generations}
    case_map = {case.id: case for case in cases}
    judge_jobs = [
        (case, repetition, judge_repetition)
        for case in cases
        for repetition in range(1, args.repetitions + 1)
        for judge_repetition in range(1, args.judge_repetitions + 1)
    ]
    completed_count = 0

    def judge(job: tuple[Case, int, int]) -> dict[str, Any]:
        nonlocal completed_count
        case, repetition, judge_repetition = job
        baseline = responses[(case.id, repetition, "baseline")]
        treatment = responses[(case.id, repetition, "treatment")]
        digest = hashlib.sha256(f"{case.id}:{repetition}:{judge_repetition}".encode()).digest()
        a_condition = "baseline" if digest[0] % 2 == 0 else "treatment"
        a = baseline if a_condition == "baseline" else treatment
        b = treatment if a_condition == "baseline" else baseline
        judge_dir = raw_dir / case.id / str(repetition) / "judge" / str(judge_repetition)
        judge_dir.mkdir(parents=True, exist_ok=True)
        output_path = judge_dir / "result.json"
        parsed_path = judge_dir / "parsed.json"
        judge_input_path = judge_dir / "input.json"
        judge_input = {"prompt": case.prompt, "criteria": case.criteria, "a": a, "b": b}
        current_judge_input = json.loads(judge_input_path.read_text(encoding="utf-8")) if judge_input_path.exists() else None
        if current_judge_input == judge_input and parsed_path.exists():
            result = json.loads(parsed_path.read_text(encoding="utf-8"))
        else:
            last_error: Exception | None = None
            for _ in range(3):
                try:
                    result = parse_judgment(run_codex(judge_dir, judge_prompt(case, a, b), output_path))
                    parsed_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
                    judge_input_path.write_text(json.dumps(judge_input, ensure_ascii=False, indent=2), encoding="utf-8")
                    break
                except (RuntimeError, ValueError) as error:
                    last_error = error
            else:
                raise RuntimeError(f"판정 실패: {case.id} {repetition}: {last_error}")
        with lock:
            completed_count += 1
            print(
                f"판정 {completed_count}/{len(judge_jobs)}: {case.id} {repetition}-{judge_repetition}",
                flush=True,
            )
        return {
            "case": case.id,
            "genre": case.genre,
            "repetition": repetition,
            "judge_repetition": judge_repetition,
            "a_condition": a_condition,
            "baseline": result["a"] if a_condition == "baseline" else result["b"],
            "treatment": result["b"] if a_condition == "baseline" else result["a"],
            "winner": (a_condition if result["winner"] == "A" else ("treatment" if a_condition == "baseline" else "baseline")) if result["winner"] != "tie" else "tie",
            "reason": result["reason"],
        }

    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as executor:
        judgments = list(executor.map(judge, judge_jobs))

    consensus = []
    for case in cases:
        for repetition in range(1, args.repetitions + 1):
            rows = [
                row for row in judgments
                if row["case"] == case.id and row["repetition"] == repetition
            ]
            winner_counts = Counter(row["winner"] for row in rows)
            most_common = winner_counts.most_common()
            winner = most_common[0][0] if len(most_common) == 1 or most_common[0][1] > most_common[1][1] else "tie"
            consensus.append({
                "case": case.id,
                "genre": case.genre,
                "repetition": repetition,
                "winner": winner,
                "winner_counts": dict(winner_counts),
                "baseline": {
                    metric: sum(row["baseline"][metric] for row in rows) / len(rows)
                    for metric in SCORE_NAMES
                },
                "treatment": {
                    metric: sum(row["treatment"][metric] for row in rows) / len(rows)
                    for metric in SCORE_NAMES
                },
                "reasons": [row["reason"] for row in rows],
            })

    result = {
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
        "model": "gpt-5.6-sol",
        "provider": os.environ.get("CODEX_ISOLATED_PROVIDER", "custom-provider"),
        "reasoning_effort": "xhigh",
        "repetitions": args.repetitions,
        "judge_repetitions": args.judge_repetitions,
        "cases": [case.__dict__ for case in cases],
        "generations": generations,
        "judgments": judgments,
        "consensus": consensus,
    }
    (args.output / "results.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(args.output / "results.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
