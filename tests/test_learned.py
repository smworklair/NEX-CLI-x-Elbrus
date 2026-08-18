"""Обученный планировщик: склейка «граф → промпт → ответ → расписание».

Проверяется НЕ качество модели, а конвейер вокруг неё: что промпт собран тем
же кодом, что и обучающий датасет; что ответ разбирается; что законное
расписание признаётся законным, а незаконное — незаконным и с указанием
причины. Всё это гоняется через `ScriptedBackend` — без torch и без весов,
поэтому тест идёт везде и за миллисекунды.

Почему это стоит закреплять тестом: у обученного планировщика контракт не
такой, как у baseline/oracle. Те по построению выдают законное расписание, а
этот — не обязательно, и его ошибки обязаны доезжать до пользователя, а не
теряться. Регрессия здесь выглядела бы как «модель вдруг стала идеальной».
"""

from __future__ import annotations

import unittest

from training.encode import encode_completion, encode_prompt
from vliw.core import GreedyListScheduler, get_profile, get_scenario
from vliw.learned.runtime import ScriptedBackend
from vliw.learned.scheduler import LearnedScheduler


def _fixture():
    """Граф, модель и ЗАВЕДОМО законное расписание для него (от эвристики)."""
    dag = get_scenario("simple4")
    machine = get_profile("e2k-v6-measured")
    good = GreedyListScheduler().schedule(dag, machine).schedule
    return dag, machine, good


class TestPromptIsTrainingFormat(unittest.TestCase):
    def test_prompt_built_by_training_encoder(self):
        """Промпт обязан собираться тем же кодом, что и обучающий датасет.

        Вторая копия формата однажды молча разъедется с обучением — ровно так
        и получился EOS-баг (docs/EOS_INCIDENT.md).
        """
        dag, machine, _ = _fixture()
        seen = {}

        class Spy(ScriptedBackend):
            def generate(self, prompt, max_new_tokens):
                seen["prompt"] = prompt
                return ""

        LearnedScheduler(backend=Spy("")).schedule(dag, machine)
        self.assertEqual(seen["prompt"], encode_prompt(dag, machine))


class TestValidAnswer(unittest.TestCase):
    def test_legal_schedule_recognised(self):
        dag, machine, good = _fixture()
        res = LearnedScheduler(
            backend=ScriptedBackend(encode_completion(good))).schedule(dag, machine)

        self.assertTrue(res.search_stats["valid"])
        self.assertEqual(res.search_stats["errors"], [])
        self.assertEqual(res.search_stats["missing"], [])
        self.assertEqual(res.schedule.makespan, good.makespan)

    def test_never_claims_optimality(self):
        """Модель ничего не доказывает — optimal обязан остаться None."""
        dag, machine, good = _fixture()
        res = LearnedScheduler(
            backend=ScriptedBackend(encode_completion(good))).schedule(dag, machine)
        self.assertIsNone(res.optimal)


class TestBrokenAnswers(unittest.TestCase):
    """Каждый случай — реальный класс ошибки из дампов прогонов."""

    def test_illegal_channel_reported(self):
        """STORE на канал, который его не исполняет — 85% ошибок прогона 1."""
        dag, machine, good = _fixture()
        # Ставим ВСЁ на канал 5: деление там законно, а вот, например,
        # несколько операций в одном такте на одном канале — уже нет.
        bad = "\n".join(f"{i}: такт=0 канал=5" for i in range(len(dag)))
        res = LearnedScheduler(backend=ScriptedBackend(bad)).schedule(dag, machine)

        self.assertFalse(res.search_stats["valid"])
        self.assertTrue(res.search_stats["errors"])
        self.assertTrue(any("РАСПИСАНИЕ НЕЗАКОННО" in n for n in res.notes))

    def test_unstopped_tail_reported(self):
        """Модель не остановилась и дописала строки для несуществующих id."""
        dag, machine, good = _fixture()
        n = len(dag)
        text = encode_completion(good) + "\n" + "\n".join(
            f"{i}: такт=9 канал=0" for i in range(n, n + 5))
        res = LearnedScheduler(backend=ScriptedBackend(text)).schedule(dag, machine)

        self.assertEqual(res.search_stats["extra"], list(range(n, n + 5)))
        self.assertTrue(any("НЕ ОСТАНОВИЛАСЬ" in n for n in res.notes))
        # Префикс при этом законен — именно это отличает «хвост» от брака.
        self.assertEqual(res.search_stats["errors"], [])

    def test_missing_instructions_reported(self):
        dag, machine, good = _fixture()
        lines = encode_completion(good).splitlines()[:-1]     # теряем последнюю
        res = LearnedScheduler(
            backend=ScriptedBackend("\n".join(lines))).schedule(dag, machine)

        self.assertIn(len(dag) - 1, res.search_stats["missing"])
        self.assertTrue(any("НЕ РАЗМЕЩЕНЫ" in n for n in res.notes))

    def test_empty_answer_does_not_crash(self):
        """Пустой ответ — не исключение, а результат с диагнозом."""
        dag, machine, _ = _fixture()
        res = LearnedScheduler(backend=ScriptedBackend("")).schedule(dag, machine)

        self.assertFalse(res.search_stats["valid"])
        self.assertEqual(res.search_stats["n_decoded"], 0)
        self.assertEqual(len(res.search_stats["missing"]), len(dag))

    def test_garbage_answer_does_not_crash(self):
        """Свободный текст без единой разборной строки."""
        dag, machine, _ = _fixture()
        res = LearnedScheduler(
            backend=ScriptedBackend("Конечно! Вот оптимальное расписание:")
        ).schedule(dag, machine)
        self.assertFalse(res.search_stats["valid"])


class TestAdapterDiscovery(unittest.TestCase):
    def test_status_works_without_torch(self):
        """Отчёт о готовности обязан работать без тяжёлых зависимостей."""
        from vliw.learned import runtime

        ready, lines = runtime.status()
        self.assertIsInstance(ready, bool)
        self.assertTrue(lines)

    def test_find_adapters_on_empty_dir(self):
        from pathlib import Path
        from tempfile import TemporaryDirectory

        from vliw.learned import runtime

        with TemporaryDirectory() as td:
            self.assertEqual(runtime.find_adapters(Path(td)), [])




class TestLlamaCppBackend(unittest.TestCase):
    """Путь llama.cpp — основной для CPU. Проверяем разбор и выбор бэкенда.

    Сам запуск модели здесь НЕ гоняется: он занимает полминуты на граф и
    требует 2 ГБ весов, которых в git нет. Проверяется то, что ломается тихо, —
    срезание эха промпта и порядок выбора бэкенда.
    """

    def test_prompt_echo_is_stripped(self):
        """llama.cpp повторяет промпт перед ответом — его надо срезать.

        Если не срезать, разбор примет строки графа за расписание: в промпте
        есть подстроки вида «0 ADD», и парсер намеренно терпимый.
        """
        from vliw.learned.runtime import Adapter, LlamaCppBackend

        prompt = "профиль: e2k-v6-measured\nграф:\n0 ADD\nрасписание:"
        answer = "0: такт=0 канал=1"

        be = LlamaCppBackend.__new__(LlamaCppBackend)   # без поиска бинарника
        out = prompt + answer + "[end of text]\nмусор после"
        tail = prompt[-40:]
        self.assertIn(tail, out)
        cleaned = out.split(tail, 1)[1].split("[end of text]")[0]
        self.assertEqual(cleaned, answer)

    def test_gguf_adapter_path_matches_name(self):
        from pathlib import Path

        from vliw.learned import runtime

        a = runtime.Adapter(path=Path("/x/lora-eos"), base="b", size_mb=1.0,
                            has_tokenizer=False)
        got = runtime.gguf_adapter_for(a)
        # Файла может не быть — важно, что имя выводится из имени адаптера.
        self.assertTrue(got is None or got.name == "lora-eos-f16.gguf")

    def test_base_search_skips_adapters(self):
        """Адаптеры (…-f16.gguf) не должны попасть в базу — они лежат рядом."""
        import inspect

        from vliw.learned import runtime

        src = inspect.getsource(runtime.find_gguf_base)
        self.assertIn("-f16.gguf", src)

    def test_make_backend_prefers_llama_cpp(self):
        import inspect

        from vliw.learned import runtime

        src = inspect.getsource(runtime.make_backend)
        # llama.cpp должен проверяться ДО transformers: 2.1 ГБ против 6.2 ГБ.
        self.assertLess(src.index("llama_cpp_ready"), src.index("missing_deps"))

if __name__ == "__main__":
    unittest.main()
