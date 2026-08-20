from __future__ import annotations

import unittest

from clear_korean.installer import load_preset


class PresetContentTests(unittest.TestCase):
    def test_every_preset_contains_natural_sentence_rules(self) -> None:
        required_phrases = (
            "비교 요청에는 비교 내용을, 작성 요청에는 작성한 글을 제공한다",
            "간결하게 쓰기 위해 필수 내용을 생략하지 않는다",
            "여러 명사를 이어 붙이기보다 조사와 서술어로 관계를 밝힌다",
            "일반 문장은 서술어와 종결어미로 끝낸다",
            "설정을 바꾸면 오류가 발생할 수 있다",
            "검토를 진행한다",
            "`~에 대한`, `~을 통해`, `~의 경우`",
            "확인한 사실과 추측을 구분한다",
        )
        for preset in ("developer", "general"):
            for tone in ("plain", "polite"):
                with self.subTest(preset=preset, tone=tone):
                    content = load_preset(preset, tone)
                    for phrase in required_phrases:
                        self.assertIn(phrase, content)

    def test_target_specific_rules_do_not_leak_between_presets(self) -> None:
        developer = load_preset("developer")
        general = load_preset("general")
        self.assertIn("### 코드와 기술 용어", developer)
        self.assertIn("영어로 등장했다는 사실만으로 사용자가 그 용어에 익숙하다고 판단하지 않는다", developer)
        self.assertIn("로그와 작업 메모의 내부 상태명, Git 상태와 `diff`, 모델 선택과 평가 절차", developer)
        self.assertNotIn("### 대화와 문서", developer)
        self.assertIn("### 대화와 문서", general)
        self.assertNotIn("### 코드와 기술 용어", general)
        self.assertNotIn("영어로 등장했다는 사실만으로 사용자가 그 용어에 익숙하다고 판단하지 않는다", general)
        self.assertNotIn("로그와 작업 메모의 내부 상태명, Git 상태와 `diff`, 모델 선택과 평가 절차", general)

    def test_tone_rules_are_mutually_exclusive(self) -> None:
        for preset in ("developer", "general"):
            with self.subTest(preset=preset):
                plain = load_preset(preset, "plain")
                polite = load_preset(preset, "polite")
                self.assertIn("## 말투: 간결한 평서형", plain)
                self.assertNotIn("## 말투: 정중한 존댓말", plain)
                self.assertIn("## 말투: 정중한 존댓말", polite)
                self.assertNotIn("## 말투: 간결한 평서형", polite)


if __name__ == "__main__":
    unittest.main()
