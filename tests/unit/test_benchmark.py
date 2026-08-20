from __future__ import annotations

import importlib.util
import json
import sys
import unittest
from pathlib import Path


PROJECT_DIR = Path(__file__).parents[2]
SCRIPT_PATH = PROJECT_DIR / "scripts" / "benchmark_korean.py"
SPEC = importlib.util.spec_from_file_location("benchmark_korean", SCRIPT_PATH)
assert SPEC and SPEC.loader
benchmark = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = benchmark
SPEC.loader.exec_module(benchmark)
SUITE_PATH = PROJECT_DIR / "tests" / "benchmark" / "v1" / "cases.jsonl"
MANIFEST_PATH = SUITE_PATH.parent / "manifest.json"


class BenchmarkTests(unittest.TestCase):
    def test_manifest_matches_suite(self) -> None:
        manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        cases = benchmark.load_cases(SUITE_PATH)
        self.assertEqual(manifest["case_count"], len(cases))
        self.assertEqual(len(cases), len({case.id for case in cases}))
        self.assertGreaterEqual(len(cases), 24)
        self.assertGreaterEqual(len({case.genre for case in cases}), 20)
        self.assertEqual({"developer", "general"}, {case.preset for case in cases})
        self.assertEqual({"plain", "polite"}, {case.tone for case in cases})

    def test_reference_answers_pass_all_deterministic_checks(self) -> None:
        for case in benchmark.load_cases(SUITE_PATH):
            with self.subTest(case=case.id):
                result = benchmark.check_response(case, case.reference)
                failed = [check["name"] for check in result["checks"] if not check["passed"]]
                self.assertEqual([], failed)
                self.assertEqual(100.0, result["score"])

    def test_absolute_judgment_parser(self) -> None:
        parsed = benchmark.parse_judgment(
            "SCORES\t5\t4\t3\t2\t1\n"
            "CRITICAL\tnone\n"
            "REASON\t간결한 답변입니다.\n"
        )
        self.assertEqual(5, parsed["scores"]["naturalness"])
        self.assertEqual("none", parsed["critical"])

    def test_absolute_judgment_parser_accepts_named_scores(self) -> None:
        parsed = benchmark.parse_judgment(
            "SCORES\tnaturalness=5\tclarity=4\tstyle_fit=3\tconcision=2\tfidelity=1\n"
            "CRITICAL\tnone\n"
            "REASON\t간결한 답변입니다.\n"
        )
        self.assertEqual(4, parsed["scores"]["clarity"])

    def test_critical_failure_caps_composite_score(self) -> None:
        case = benchmark.load_cases(SUITE_PATH)[0]
        generation = {
            "case": case.id, "genre": case.genre, "repetition": 1,
            "response": "답변", "checks": {"score": 100.0},
        }
        judgment = {
            "case": case.id, "repetition": 1, "judge_repetition": 1,
            "scores": {dimension: 5 for dimension in benchmark.DIMENSIONS},
            "critical": "missing_answer", "reason": "답이 없습니다.",
        }
        aggregate = benchmark.aggregate_results([case], [generation], [judgment])
        self.assertEqual(50.0, aggregate["overall"]["composite"])
        self.assertEqual(1, aggregate["overall"]["critical_failures"])

    def test_comparison_detects_regressions(self) -> None:
        overall = {
            "composite": 90.0, "critical_failures": 0,
            "scores": {dimension: 4.5 for dimension in benchmark.DIMENSIONS},
        }
        baseline = {
            "run": {"id": "baseline"},
            "aggregate": {"overall": overall, "genres": {"공지": 90.0}},
        }
        current = {
            "aggregate": {
                "overall": {
                    "composite": 88.0, "critical_failures": 1,
                    "scores": {dimension: 4.2 for dimension in benchmark.DIMENSIONS},
                },
                "genres": {"공지": 85.0},
            }
        }
        comparison = benchmark.compare_summaries(current, baseline)
        self.assertFalse(comparison["passed"])
        self.assertGreaterEqual(len(comparison["regressions"]), 3)

    def test_uncertain_genre_drop_is_a_warning(self) -> None:
        def summary(score: float, standard_error: float) -> dict:
            return {
                "run": {"id": "run"},
                "aggregate": {
                    "overall": {
                        "composite": 90.0, "critical_failures": 0,
                        "scores": {dimension: 4.5 for dimension in benchmark.DIMENSIONS},
                    },
                    "genres": {"공지": score},
                    "cases": [{
                        "case": "notice", "genre": "공지", "composite": score,
                        "standard_error": standard_error,
                    }],
                },
            }

        comparison = benchmark.compare_summaries(summary(85.0, 4.0), summary(90.0, 1.0))
        self.assertTrue(comparison["passed"])
        self.assertEqual([], comparison["regressions"])
        self.assertEqual(1, len(comparison["warnings"]))


if __name__ == "__main__":
    unittest.main()
