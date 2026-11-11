# -*- coding: utf-8 -*-
"""NNL-блок помощи: линтер, веса, ответы и отказ от посторонних вопросов."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from vliw import help_answers, help_nnl

КОРЕНЬ = Path(__file__).resolve().parent.parent
БЛОК = КОРЕНЬ / "nnl_vliw" / "блоки_помощь" / "Помощь_ассистент"
АРХИТЕКТУРЫ = КОРЕНЬ / "nnl_vliw" / "архитектуры"
ПАСПОРТ = json.loads((БЛОК / "паспорт.json").read_text(encoding="utf-8"))
ЛЁГКИЕ = json.loads((КОРЕНЬ / "vliw" / "help_weights.json").read_text(encoding="utf-8"))


class TestBlock(unittest.TestCase):
    def test_linter_accepts_block(self):
        from nnl_vliw.NNL import линтер

        отчёт = линтер.проверить_блок(str(БЛОК), str(АРХИТЕКТУРЫ))
        self.assertEqual(отчёт["статус"], "УСПЕХ", отчёт["ошибки"])
        self.assertEqual(отчёт["имя_блока"], "Помощь_ассистент")
        self.assertEqual(отчёт["чисел"], ПАСПОРТ["веса"]["чисел"])

    def test_passport_declares_same_topics_as_weights(self):
        import numpy as np

        with np.load(БЛОК / "веса.npz", allow_pickle=False) as z:
            ответы = [str(x) for x in z["ответы"]]
            self.assertEqual(int(z["E"].shape[0]), ПАСПОРТ["настройки"]["корзины"])
            self.assertEqual(int(z["E"].shape[1]), ПАСПОРТ["настройки"]["размер"])
            self.assertEqual(list(z["пишет"]), [])
            self.assertEqual(list(z["читает"]), [])
        self.assertEqual(ответы, ПАСПОРТ["ответы"])

    def test_light_copy_is_the_same_block(self):
        """JSON для чистого Python — не «похожие» числа, а те же самые."""
        import numpy as np

        with np.load(БЛОК / "веса.npz", allow_pickle=False) as z:
            for ключ in ("E", "U", "b"):
                np.testing.assert_allclose(
                    z[ключ].astype("float64"),
                    np.asarray(ЛЁГКИЕ[ключ], dtype="float64"),
                    rtol=0, atol=1e-4, err_msg=ключ,
                )
        self.assertEqual(ЛЁГКИЕ["ответы"], ПАСПОРТ["ответы"])
        self.assertEqual(ЛЁГКИЕ["sha256"], ПАСПОРТ["веса"]["sha256"])
        self.assertEqual(ЛЁГКИЕ["соль"], ПАСПОРТ["настройки"]["соль"])

    def test_block_says_what_it_can(self):
        сведения = help_nnl.сведения()
        self.assertIn("Помощь_ассистент", сведения)
        self.assertIn("4096", сведения)
        self.assertTrue(help_nnl.доступно())
        self.assertNotIn(help_nnl.НЕ_ТЕМА, help_nnl.темы())


class TestAssistant(unittest.TestCase):
    def test_typical_installation_questions(self):
        ожидание = {
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
        for вопрос, тема in ожидание.items():
            with self.subTest(вопрос=вопрос):
                результат = help_nnl.спросить(вопрос)
                self.assertIsNotNone(результат, вопрос)
                self.assertEqual(результат[0], тема)

    def test_nnl_answer_explains_no_dialogue_memory(self):
        ответ = " ".join(help_answers.ответ("nnl") or [])
        self.assertIn("обучен", ответ)
        self.assertIn("контекст", ответ.lower())

    def test_off_topic_questions_are_rejected(self):
        for вопрос in (
            "сколько будет два плюс два",
            "расскажи про погоду",
            "как приготовить борщ",
            "кто такой пушкин",
            "посоветуй фильм на вечер",
            "какая столица франции",
        ):
            with self.subTest(вопрос=вопрос):
                self.assertIsNone(help_nnl.спросить(вопрос))

    def test_every_topic_has_an_answer(self):
        for тема in help_nnl.темы():
            with self.subTest(тема=тема):
                ответ = help_answers.ответ(тема)
                self.assertTrue(ответ, f"нет ответа для темы {тема}")
                self.assertTrue(any(строка.strip() for строка in ответ))

    def test_every_topic_has_a_short_answer(self):
        """Ассистент сначала говорит коротко, полный текст — за «Подробнее»."""
        for тема in help_nnl.темы():
            with self.subTest(тема=тема):
                кратко = help_answers.кратко(тема)
                полный = help_answers.ответ(тема) or []
                self.assertTrue(кратко, f"нет короткого ответа для темы {тема}")
                self.assertLessEqual(len(кратко), max(2, len(полный)),
                                     "короткий ответ не должен быть длиннее полного")

    def test_short_answer_for_launch_is_actionable(self):
        текст = " ".join(help_answers.кратко("запуск"))
        self.assertIn("NEX CLI", текст)
        self.assertLessEqual(len(текст.splitlines()), 2)

    def test_fallback_does_not_leave_user_without_options(self):
        текст = "\n".join(help_answers.не_понял())
        self.assertIn("Не уверен", текст)
        self.assertIn("меню", текст)


if __name__ == "__main__":
    unittest.main()
