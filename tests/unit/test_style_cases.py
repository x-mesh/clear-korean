from __future__ import annotations

import csv
import unittest
from pathlib import Path


CASES_PATH = Path(__file__).parents[1] / "style_cases.tsv"
FIELDS = ("id", "preset", "tone", "genre", "prompt", "criteria")


class StyleCaseTests(unittest.TestCase):
    def test_style_case_schema_and_coverage(self) -> None:
        with CASES_PATH.open(encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle, delimiter="\t")
            rows = list(reader)
        self.assertEqual(list(FIELDS), reader.fieldnames)
        self.assertGreaterEqual(len(rows), 12)
        self.assertEqual(len(rows), len({row["id"] for row in rows}))
        self.assertGreaterEqual(len({row["genre"] for row in rows}), 10)
        self.assertEqual({"developer", "general"}, {row["preset"] for row in rows})
        self.assertEqual({"plain", "polite"}, {row["tone"] for row in rows})
        for row in rows:
            with self.subTest(case=row["id"]):
                self.assertTrue(all(row[field].strip() for field in FIELDS))


if __name__ == "__main__":
    unittest.main()
