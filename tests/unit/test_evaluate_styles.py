from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
import unittest
from pathlib import Path


PROJECT_DIR = Path(__file__).parents[2]
SCRIPT_PATH = PROJECT_DIR / "scripts" / "evaluate_styles.py"
SPEC = importlib.util.spec_from_file_location("evaluate_styles", SCRIPT_PATH)
assert SPEC and SPEC.loader
evaluate_styles = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = evaluate_styles
SPEC.loader.exec_module(evaluate_styles)


class EvaluationToolTests(unittest.TestCase):
    def test_judgment_parser(self) -> None:
        result = evaluate_styles.parse_judgment(
            "A\t5\t4\t3\t2\t1\n"
            "B\t1\t2\t3\t4\t5\n"
            "WINNER\tA\n"
            "REASON\tA가 더 자연스럽습니다.\n"
        )
        self.assertEqual(5, result["a"]["naturalness"])
        self.assertEqual(5, result["b"]["fidelity"])
        self.assertEqual("A", result["winner"])

    def test_judgment_parser_rejects_invalid_scores(self) -> None:
        with self.assertRaises(ValueError):
            evaluate_styles.parse_judgment(
                "A\t6\t4\t3\t2\t1\n"
                "B\t1\t2\t3\t4\t5\n"
                "WINNER\tA\n"
                "REASON\t이유\n"
            )

    def test_isolated_wrapper_show_command_uses_custom_provider_without_secret(self) -> None:
        environment = os.environ.copy()
        environment["CODEX_ISOLATED_BASE_URL"] = "https://provider.example/v1"
        environment["CODEX_ISOLATED_API_KEY"] = "secret-value"
        completed = subprocess.run(
            [str(PROJECT_DIR / "scripts" / "codex-isolated"), "--show-command", "질문"],
            env=environment,
            capture_output=True,
            text=True,
            check=True,
        )
        self.assertIn('model_provider=\"custom-provider\"', completed.stdout)
        self.assertIn("--ignore-user-config", completed.stdout)
        self.assertNotIn("secret-value", completed.stdout)


if __name__ == "__main__":
    unittest.main()
