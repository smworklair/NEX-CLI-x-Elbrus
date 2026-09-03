"""Агент на локальной модели: выбор провайдера и маршрутизация.

Настоящая модель здесь не поднимается — 2.1 ГБ весов не место в тесте.
Проверяется выбор пути и то, что публичные функции `llm` действительно
уезжают в локальный клиент, а не в сеть. Ошибка здесь выглядела бы как
молчаливый поход в интернет с ключом, которого нет, — то есть как «агент не
работает» без объяснения причины.
"""

from __future__ import annotations

import unittest
import unittest.mock as mock

from vliw.agent import llm, local


class TestProviderChoice(unittest.TestCase):
    """Кто отвечает: локальная модель, Le Chat или Gemini."""

    def _with(self, env: dict, local_ready: bool = True, key: str = ""):
        return (mock.patch.dict(llm.os.environ, env, clear=False),
                mock.patch.object(local, "ready", lambda: local_ready),
                mock.patch.object(llm, "_raw_key", lambda: key))

    def _provider(self, env, local_ready=True, key=""):
        a, b, c = self._with(env, local_ready, key)
        with a, b, c:
            return llm.provider()

    def test_explicit_local_wins(self) -> None:
        self.assertEqual(self._provider({"NEX_PROVIDER": "local"}), "local")
        self.assertEqual(self._provider({"NEX_PROVIDER": "локально"}), "local")

    def test_no_key_falls_to_local_when_weights_are_here(self) -> None:
        """Без ключа — локальная модель, а не поход в сеть за отказом."""
        self.assertEqual(self._provider({"NEX_PROVIDER": ""}, local_ready=True),
                         "local")

    def test_no_key_and_no_weights_keeps_the_cloud_default(self) -> None:
        """Без весов остаёмся на прежнем поведении: облако и внятный отказ."""
        self.assertEqual(
            self._provider({"NEX_PROVIDER": ""}, local_ready=False),
            llm.DEFAULT_PROVIDER)

    def test_explicit_cloud_is_not_overridden_by_local_weights(self) -> None:
        """Попросили Mistral — идём в Mistral, даже если веса лежат рядом."""
        self.assertEqual(self._provider({"NEX_PROVIDER": "mistral"}), "mistral")
        self.assertEqual(self._provider({"NEX_PROVIDER": "gemini"}), "gemini")

    def test_key_present_means_cloud(self) -> None:
        """Ключ задан — прежнее поведение не меняется."""
        self.assertEqual(
            self._provider({"NEX_PROVIDER": ""}, local_ready=True, key="abc123"),
            llm.DEFAULT_PROVIDER)


class TestRouting(unittest.TestCase):
    """Публичные функции `llm` в локальном режиме не ходят в сеть."""

    def setUp(self) -> None:
        patcher = mock.patch.object(llm, "provider", lambda: "local")
        patcher.start()
        self.addCleanup(patcher.stop)
        # Если маршрутизация сломается, тест упадёт здесь, а не втихую уйдёт
        # в интернет.
        net = mock.patch.object(llm, "_call",
                                mock.Mock(side_effect=AssertionError(
                                    "локальный режим не должен ходить в сеть")))
        net.start()
        self.addCleanup(net.stop)

    def test_complete_goes_local(self) -> None:
        with mock.patch.object(local, "complete", lambda *a, **k: "локальный ответ"):
            self.assertEqual(llm.complete("сис", "вопрос"), "локальный ответ")

    def test_stream_goes_local(self) -> None:
        with mock.patch.object(local, "stream", lambda *a, **k: iter(["a", "б"])):
            self.assertEqual(list(llm.stream("сис", "вопрос")), ["a", "б"])

    def test_structured_goes_local(self) -> None:
        with mock.patch.object(local, "structured", lambda *a, **k: ("{}", 7)):
            self.assertEqual(llm.structured("сис", "вопрос", {}), ("{}", 7))

    def test_check_goes_local(self) -> None:
        with mock.patch.object(local, "check", lambda: (True, "готово")):
            self.assertEqual(llm.check(), (True, "готово"))

    def test_describe_says_where_it_runs(self) -> None:
        with mock.patch.object(local, "model_label", lambda: "qwen.gguf"):
            self.assertIn("локально", llm.describe())
            self.assertTrue(llm.is_local())


class TestSmallModelNudge(unittest.TestCase):
    """Добавка к промпту — только для вопросов по делу, не для реплик.

    Найдено вживую: с добавкой на КАЖДЫЙ вопрос (включая «привет») модель
    тащила числа из блока ФАКТЫ в любой ответ. ФАКТЫ есть всегда, даже когда
    расписание ещё не считалось, — и на 3B это давало не «ответь короче», а
    выдуманный технический разбор из ближайших похожих слов: «11 тактов»
    (на деле это latency DIV, а не длина расписания) и перевранный смысл
    заметки об участке. Без добавки на «привет» — обычное приветствие.
    """

    def test_nudge_on_by_default(self) -> None:
        msgs = local._messages("СИСТЕМА", "вопрос", None)
        self.assertEqual(msgs[0]["role"], "system")
        self.assertTrue(msgs[0]["content"].startswith("СИСТЕМА"))
        self.assertIn("Дальше:", msgs[0]["content"])
        self.assertEqual(msgs[-1], {"role": "user", "content": "вопрос"})

    def test_nudge_can_be_switched_off(self) -> None:
        """Для реплик не по делу добавка не едет вовсе, а не смягчается."""
        msgs = local._messages("СИСТЕМА", "привет", None, nudge=False)
        self.assertEqual(msgs[0]["content"], "СИСТЕМА")
        self.assertNotIn("Дальше:", msgs[0]["content"])

    def test_history_becomes_alternating_turns(self) -> None:
        msgs = local._messages("С", "новый", [("прошлый", "ответ")])
        self.assertEqual([m["role"] for m in msgs],
                         ["system", "user", "assistant", "user"])


class TestSmalltalkSkipsNudge(unittest.TestCase):
    """Агент решает по вопросу, а не по провайдеру: смолток — без добавки."""

    def setUp(self) -> None:
        patcher = mock.patch.object(llm, "provider", lambda: "local")
        patcher.start()
        self.addCleanup(patcher.stop)

    def _asked_nudge(self, question: str) -> bool:
        from vliw import cli
        from vliw.agent.agent import Agent

        session = cli.Session(args=cli._build_parser().parse_args([]))
        seen = {}

        def fake_stream(system, q, history=None, temperature=0.3, nudge=True):
            seen["nudge"] = nudge
            yield "ok"

        with mock.patch.object(llm, "stream", fake_stream):
            list(Agent(session).ask_stream(question))
        return seen["nudge"]

    def test_greeting_gets_no_nudge(self) -> None:
        self.assertFalse(self._asked_nudge("привет"))

    def test_real_question_gets_nudge(self) -> None:
        self.assertTrue(self._asked_nudge("почему этот участок медленный?"))
class TestCellAnswerGuard(unittest.TestCase):
    """Сторож на выдуманные числа в подписи под курсором.

    Появился не из осторожности, а по факту: локальная 3B на вопрос «почему
    операция здесь» сочинила «блокировала канал 2 на 21 такта» — таких чисел
    в разборе не было вовсе.
    """

    FACTS = ["выдана в такте 2, результат готов к 13, латентность 11",
             "ждала операндов: a0 готов к т.1"]

    def test_answer_within_the_facts_passes(self) -> None:
        from vliw.agent import context

        ok = context.cell_answer_is_grounded(
            "Ждала операнд a0 до такта 1, потому и вышла только в такте 2.",
            self.FACTS)
        self.assertTrue(ok)

    def test_invented_number_is_caught(self) -> None:
        from vliw.agent import context

        ok = context.cell_answer_is_grounded(
            "Блокировала канал 2 на 21 такта.", self.FACTS)
        self.assertFalse(ok, "21 в разборе нет — обязано отлавливаться")

    def test_answer_without_numbers_passes(self) -> None:
        """Фраза без чисел безопасна по построению — её пропускаем."""
        from vliw.agent import context

        self.assertTrue(context.cell_answer_is_grounded(
            "Операция ждала операнд и потому вышла позже.", self.FACTS))

    def test_guard_does_not_catch_wrong_relations(self) -> None:
        """ЧЕГО СТОРОЖ НЕ УМЕЕТ — записано, чтобы на него не полагались.

        Все числа взяты из разбора, а связаны неверно: латентность приписана
        не тому. Регуляркой это не ловится, только чтением — поэтому разбор
        ядра всегда висит НАД фразой, а не заменяется ею.
        """
        from vliw.agent import context

        self.assertTrue(context.cell_answer_is_grounded(
            "Вышла в такте 11, латентность 2.", self.FACTS))


if __name__ == "__main__":
    unittest.main()
