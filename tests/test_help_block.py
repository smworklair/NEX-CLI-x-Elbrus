# -*- coding: utf-8 -*-
"""NNL help block: linter, weights, answers, and off-topic rejection."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from vliw import help_answers, help_nnl

ROOT = Path(__file__).resolve().parent.parent
BLOCK = ROOT / "nnl_vliw" / "блоки_помощь" / "Помощь_ассистент"
ARCHITECTURES = ROOT / "nnl_vliw" / "архитектуры"
PASSPORT = json.loads((BLOCK / "паспорт.json").read_text(encoding="utf-8"))
LIGHTWEIGHT = json.loads((ROOT / "vliw" / "help_weights.json").read_text(encoding="utf-8"))


class TestBlock(unittest.TestCase):
    def test_linter_accepts_block(self):
        from nnl_vliw.NNL import линтер

        report = линтер.проверить_блок(str(BLOCK), str(ARCHITECTURES))
        self.assertEqual(report["статус"], "УСПЕХ", report["ошибки"])
        self.assertEqual(report["имя_блока"], "Помощь_ассистент")
        self.assertEqual(report["чисел"], PASSPORT["веса"]["чисел"])

    def test_passport_declares_same_topics_as_weights(self):
        import numpy as np

        with np.load(BLOCK / "веса.npz", allow_pickle=False) as z:
            answers = [str(x) for x in z["ответы"]]
            self.assertEqual(int(z["E"].shape[0]), PASSPORT["настройки"]["корзины"])
            self.assertEqual(int(z["E"].shape[1]), PASSPORT["настройки"]["размер"])
            self.assertEqual(list(z["пишет"]), [])
            self.assertEqual(list(z["читает"]), [])
        self.assertEqual(answers, PASSPORT["ответы"])

    def test_light_copy_is_the_same_block(self):
        """Pure-Python JSON weights must match the trained npz block exactly."""
        import numpy as np

        with np.load(BLOCK / "веса.npz", allow_pickle=False) as z:
            for key in ("E", "U", "b"):
                np.testing.assert_allclose(
                    z[key].astype("float64"),
                    np.asarray(LIGHTWEIGHT[key], dtype="float64"),
                    rtol=0, atol=1e-4, err_msg=key,
                )
        self.assertEqual(LIGHTWEIGHT["ответы"], PASSPORT["ответы"])
        self.assertEqual(LIGHTWEIGHT["sha256"], PASSPORT["веса"]["sha256"])
        self.assertEqual(LIGHTWEIGHT["соль"], PASSPORT["настройки"]["соль"])

    def test_block_says_what_it_can(self):
        info = help_nnl.сведения()
        self.assertIn("Help_assistant", info)
        self.assertIn("4096", info)
        self.assertTrue(help_nnl.доступно())
        self.assertNotIn(help_nnl.НЕ_ТЕМА, help_nnl.темы())


class TestAssistant(unittest.TestCase):
    def test_typical_installation_questions(self):
        # The underlying NNL classifier weights are trained on Russian phrasings
        # and topic IDs, so we test the trained routing vocabulary directly.
        expected = {
            "как установить": "установка",
            "как поставить nex cli на новый компьютер": "установка",
            "что такое textual": "textual",
            "нет pip": "venv",
            "почему не запускается интерфейс": "проблема",
            "как создать venv": "venv",
            "как проверить установку": "проверка",
            "как обновить": "обновление",
            "как удалить": "удаление",
            "как настроить агента": "агент",
            "что такое slotclash": "данные",
            "какая версия python": "требования",
            "зачем нужен nex cli": "зачем",
            "как на windows": "система",
            "как запустить": "запуск",
            "как работает NNL": "nnl",
            "привет": "беседа",
            "йоу": "беседа",
            "хай": "беседа",
            "hello": "беседа",
        }
        for question, topic in expected.items():
            with self.subTest(question=question):
                result = help_nnl.спросить(question)
                self.assertIsNotNone(result, question)
                self.assertEqual(result[0], topic)

    def test_nnl_answer_explains_no_dialogue_memory(self):
        answer = " ".join(help_answers.ответ("nnl") or [])
        self.assertIn("trained", answer.lower())
        self.assertIn("dialogue context", answer.lower())

    def test_off_topic_questions_are_rejected(self):
        for question in (
            "сколько будет два плюс два",
            "расскажи про погоду",
            "как приготовить борщ",
            "кто такой пушкин",
            "посоветуй фильм на вечер",
            "какая столица франции",
        ):
            with self.subTest(question=question):
                self.assertIsNone(help_nnl.спросить(question))

    def test_every_topic_has_an_answer(self):
        for topic in help_nnl.темы():
            with self.subTest(topic=topic):
                answer = help_answers.ответ(topic)
                self.assertTrue(answer, f"no answer for topic {topic}")
                self.assertTrue(any(line.strip() for line in answer))

    def test_every_topic_has_a_short_answer(self):
        """The assistant replies concisely first; full details are behind 'More'."""
        for topic in help_nnl.темы():
            with self.subTest(topic=topic):
                short = help_answers.кратко(topic)
                full = help_answers.ответ(topic) or []
                self.assertTrue(short, f"no short answer for topic {topic}")
                self.assertLessEqual(len(short), max(2, len(full)),
                                     "short answer must not exceed full answer")

    def test_short_answer_for_launch_is_actionable(self):
        text = " ".join(help_answers.кратко("запуск"))
        self.assertIn("NEX CLI", text)
        self.assertLessEqual(len(text.splitlines()), 2)

    def test_fallback_does_not_leave_user_without_options(self):
        text = "\n".join(help_answers.не_понял())
        self.assertIn("not sure", text.lower())
        self.assertIn("menu", text.lower())


if __name__ == "__main__":
    unittest.main()
