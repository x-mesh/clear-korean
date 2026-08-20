from __future__ import annotations

import csv
import unittest
from pathlib import Path


CASES_PATH = Path(__file__).parents[1] / "cases.tsv"
EXPECTED_FIELDS = ("id", "preset", "principle", "prompt", "expectation")
REQUIRED_PRINCIPLES = {
    "answer-completeness",
    "artifact-style",
    "audience",
    "brevity",
    "choice-quality",
    "complete-sentence",
    "direct-verbs",
    "error-reporting",
    "explicit-relations",
    "explanation-depth",
    "language-boundary",
    "literal-language",
    "plain-tone",
    "polite-tone",
    "possessive-chain",
    "punctuation",
    "quotation-boundary",
    "requested-style",
    "result-first",
    "source-boundary",
    "uncertainty",
    "user-tone",
}


def load_cases() -> tuple[list[str], list[dict[str, str]]]:
    with CASES_PATH.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        return list(reader.fieldnames or ()), list(reader)


class BehaviorCaseTests(unittest.TestCase):
    def test_schema_and_required_values(self) -> None:
        fields, cases = load_cases()
        self.assertEqual(list(EXPECTED_FIELDS), fields)
        self.assertGreaterEqual(len(cases), 20)
        for case in cases:
            with self.subTest(case=case.get("id")):
                self.assertEqual(set(EXPECTED_FIELDS), set(case))
                self.assertTrue(all(case[field].strip() for field in EXPECTED_FIELDS))
                self.assertRegex(case["id"], r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
                self.assertIn(case["preset"], {"developer", "general"})

    def test_ids_are_unique(self) -> None:
        _, cases = load_cases()
        ids = [case["id"] for case in cases]
        self.assertEqual(len(ids), len(set(ids)))

    def test_core_principles_have_behavior_cases(self) -> None:
        _, cases = load_cases()
        principles = {case["principle"] for case in cases}
        self.assertEqual(set(), REQUIRED_PRINCIPLES - principles)

    def test_both_presets_have_substantial_coverage(self) -> None:
        _, cases = load_cases()
        counts = {preset: 0 for preset in ("developer", "general")}
        for case in cases:
            counts[case["preset"]] += 1
        self.assertGreaterEqual(counts["developer"], 7)
        self.assertGreaterEqual(counts["general"], 10)

    def test_prompts_and_expectations_contain_korean(self) -> None:
        _, cases = load_cases()
        for case in cases:
            with self.subTest(case=case["id"]):
                self.assertRegex(case["prompt"], r"[가-힣]")
                self.assertRegex(case["expectation"], r"[가-힣]")


if __name__ == "__main__":
    unittest.main()
