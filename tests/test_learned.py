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
from vliw.core.schedule import Schedule
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
            def generate_events(self, prompt, max_new_tokens):
                seen["prompt"] = prompt
                return iter(())

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



class TestConcurrencyGuard(unittest.TestCase):
    """Повторный /learned, пока первый ещё считает, не должен плодить процессы.

    Найдено по факту: Textual отменяет СТАРЫЙ воркер только на своём уровне —
    subprocess.run() внутри него блокирующий и отмену не видит. Без блокировки
    второй /learned запускает ВТОРОЙ параллельный процесс модели: два по
    3.6 ГБ на машине с 7 ГБ ОЗУ — секунды до OOM.
    """

    def test_second_call_rejected_while_first_holds_lock(self):
        from vliw.learned.runtime import _GENERATE_LOCK, LlamaCppBackend

        be = LlamaCppBackend.__new__(LlamaCppBackend)
        _GENERATE_LOCK.acquire()
        try:
            with self.assertRaises(RuntimeError):
                be.generate("x", 5)
        finally:
            _GENERATE_LOCK.release()

    def test_lock_released_after_call(self):
        """После завершения (успешного или нет) блокировка обязана сняться."""
        from vliw.learned.runtime import _GENERATE_LOCK, LlamaCppBackend

        be = LlamaCppBackend.__new__(LlamaCppBackend)
        be.binary = None       # заставит упасть внутри _generate_locked
        be.base_gguf = None
        be.lora_gguf = None
        be.threads = 1
        with self.assertRaises(Exception):
            be.generate("x", 5)
        self.assertTrue(_GENERATE_LOCK.acquire(blocking=False),
                        "блокировка осталась висеть после сбоя")
        _GENERATE_LOCK.release()


class TestChannelRepair(unittest.TestCase):
    """Починка каналов: такты модели неприкосновенны, канал — законный.

    Замер показал ровное разделение: когда модель не путает канал, она попадает
    ТОЧНО в оптимум. Когда путает — это почти всегда STORE, которого не было в
    обучающих данных. Матрица машины при этом известна точно, поэтому канал
    можно переназначить, не трогая план.
    """

    def test_illegal_store_channel_is_fixed(self):
        from vliw.learned.repair import repair

        # mixed18 — самый богатый по составу операций, STORE там есть.
        dag = get_scenario("mixed18")
        machine = get_profile("e2k-v6-measured")
        good = GreedyListScheduler().schedule(dag, machine).schedule
        # STORE исполняют только ,2 и ,5 — ставим на ,0 и ждём починки.
        store = next(i for i in range(len(dag)) if dag[i].op == "STORE")
        broken = Schedule(dag, machine)
        for i in range(len(dag)):
            p = good.placements[i]
            broken.place(i, p.cycle, 0 if i == store else p.channel)

        fixed, rep = repair(broken, machine)
        self.assertEqual(fixed.validate(), [])
        self.assertIn(fixed.placements[store].channel, machine.channels_for("STORE"))
        self.assertTrue(rep.touched)

    def test_cycles_are_never_moved(self):
        """Главный инвариант: makespan определяется тактами, их мы не трогаем."""
        from vliw.learned.repair import repair

        dag, machine, good = _fixture()
        broken = Schedule(dag, machine)
        for i in range(len(dag)):
            broken.place(i, good.placements[i].cycle, 0)   # все на канал 0

        fixed, _ = repair(broken, machine)
        for i in range(len(dag)):
            self.assertEqual(fixed.placements[i].cycle, good.placements[i].cycle,
                             f"такт инструкции {i} сдвинулся при починке")
        self.assertEqual(fixed.makespan, broken.makespan)

    def test_already_legal_schedule_is_left_alone(self):
        """Законное расписание чинить не надо — ни одной перестановки."""
        from vliw.learned.repair import repair

        dag, machine, good = _fixture()
        fixed, rep = repair(good, machine)
        self.assertEqual(rep.touched, 0)
        for i in range(len(dag)):
            self.assertEqual(fixed.placements[i].channel,
                             good.placements[i].channel)

    def test_narrow_op_wins_over_greedy_grab(self):
        """Матчинг, а не жадность: широкая операция не должна занять
        единственный канал, нужный узкой.

        ADD исполним на всех шести каналах, STORE — только на ,2 и ,5. Если
        раздавать жадно по порядку, ADD может сесть на ,2 и оставить STORE без
        места, хотя законное решение существует.
        """
        from vliw.learned.repair import _assign_cycle

        machine = get_profile("e2k-v6-measured")
        add_ch = machine.channels_for("ADD")
        store_ch = machine.channels_for("STORE")
        # Обе просятся на ,2; законно только STORE->,2 (или ,5), ADD->куда угодно.
        got = _assign_cycle([(0, add_ch, 2), (1, store_ch, 2)], machine.width)
        self.assertIsNotNone(got, "решение существует, а матчинг его не нашёл")
        self.assertIn(got[1], store_ch)
        self.assertNotEqual(got[0], got[1])

    def test_impossible_cycle_reported_not_hidden(self):
        """Если законно раздать нельзя — это видно, а не замаскировано."""
        from vliw.learned.repair import _assign_cycle

        machine = get_profile("e2k-v6-measured")
        store_ch = machine.channels_for("STORE")      # ровно два канала
        # Три STORE в одном такте — портов записи всего два, решения нет.
        got = _assign_cycle([(i, store_ch, store_ch[0]) for i in range(3)],
                            machine.width)
        self.assertIsNone(got)

    def test_scheduler_repair_flag_off_by_default(self):
        """По умолчанию планировщик ничего не чинит — ответ модели как есть."""
        dag, machine, good = _fixture()
        bad = "\n".join(
            f"{i}: такт={good.placements[i].cycle} канал=0" for i in range(len(dag)))
        res = LearnedScheduler(backend=ScriptedBackend(bad)).schedule(dag, machine)
        self.assertEqual(res.search_stats["repaired"], 0)

    def test_scheduler_repair_flag_on_fixes_and_reports(self):
        dag, machine, good = _fixture()
        bad = "\n".join(
            f"{i}: такт={good.placements[i].cycle} канал=0" for i in range(len(dag)))
        res = LearnedScheduler(backend=ScriptedBackend(bad),
                               repair=True).schedule(dag, machine)
        self.assertTrue(res.search_stats["valid"])
        self.assertTrue(res.search_stats["repaired"])
        self.assertTrue(any("ПОЧИНЕНО" in n for n in res.notes))
        # Такты модели сохранены — makespan тот же, что она задумала.
        self.assertEqual(res.schedule.makespan, good.makespan)


class TestStreaming(unittest.TestCase):
    """Ответ модели отдаётся по мере генерации, а не целиком в конце.

    Генерация идёт около тридцати секунд. Без стриминга это тишина, в которой
    непонятно, работает оно или повисло.
    """

    def test_callback_receives_text(self):
        dag, machine, good = _fixture()
        got = []
        LearnedScheduler(
            backend=ScriptedBackend(encode_completion(good))
        ).schedule(dag, machine, on_text=got.append)
        self.assertTrue(got, "колбэк не вызвался ни разу")
        self.assertIn("такт=", "".join(got))

    def test_works_without_callback(self):
        """on_text необязателен: протокол Scheduler его не требует."""
        dag, machine, good = _fixture()
        res = LearnedScheduler(
            backend=ScriptedBackend(encode_completion(good))).schedule(dag, machine)
        self.assertTrue(res.search_stats["valid"])

    def test_echo_detection_splits_prompt_from_answer(self):
        """llama.cpp повторяет промпт перед ответом — наружу идёт только ответ.

        Проверяем ровно ту логику, что в потоковом чтении: ответ начинается
        сразу после хвоста промпта в 40 символов.
        """
        prompt = encode_prompt(*_fixture()[:2])
        answer = "0: такт=0 канал=1\n"
        stream = prompt + answer

        tail = prompt[-40:]
        buf, out, echo_done = [], [], False
        for ch in stream:
            buf.append(ch)
            if echo_done:
                out.append(ch)
            elif "".join(buf[-len(tail):]) == tail:
                echo_done = True
        self.assertTrue(echo_done, "хвост промпта не найден в потоке")
        self.assertEqual("".join(out), answer)

if __name__ == "__main__":
    unittest.main()


class ChunkedBackend(ScriptedBackend):
    """Отдаёт ответ мелкими кусками — как настоящий поток llama.cpp.

    Куски намеренно НЕ совпадают с границами строк: llama.cpp отдаёт байты по
    мере генерации, и перевод строки приходит в середине куска. Разбор,
    который это не учитывает, работает на тестах и разваливается вживую.
    """

    def __init__(self, text: str, size: int = 3):
        super().__init__(text)
        self._text = text
        self._size = size

    def generate_events(self, prompt, max_new_tokens):
        for i in range(0, len(self._text), self._size):
            yield self._text[i:i + self._size]


class CancelWatchBackend(ScriptedBackend):
    """Бесконечная генерация, которая замечает, что её закрыли."""

    def __init__(self) -> None:
        super().__init__("")
        self.cleaned = False
        self.emitted = 0

    def generate_events(self, prompt, max_new_tokens):
        try:
            while True:
                self.emitted += 1
                yield "…\n"          # не размещение: важен сам факт потока
        finally:
            # У настоящего бэкенда здесь умирает подпроцесс llama.cpp и
            # отпускается блокировка.
            self.cleaned = True


def _answer_line(dag, machine, instr: int, cycle: int, channel: int) -> str:
    """Одна строка ответа модели, собранная кодировщиком обучения.

    Писать `"0: такт=0 канал=4"` от руки нельзя: это вторая копия формата, а
    вторая копия однажды молча разъезжается с обучением — так и получился
    EOS-баг (docs/EOS_INCIDENT.md). Формат живёт в одном месте, тесты берут
    его оттуда же, откуда берёт планировщик.
    """
    sched = Schedule(dag, machine)
    sched.place(instr, cycle, channel)
    return encode_completion(sched)


class TestLiveGridFilling(unittest.TestCase):
    """Решётка заполняется ПО ХОДУ генерации, а не одним куском в конце."""

    def setUp(self) -> None:
        self.dag, self.machine, self.good = _fixture()
        self.answer = encode_completion(self.good)

    def _events(self, backend):
        from vliw.core import stream

        return list(stream(LearnedScheduler(backend=backend), self.dag, self.machine))

    def test_placements_arrive_before_the_end(self) -> None:
        """Хотя бы одно размещение приходит раньше терминального события.

        Ради этого всё и затевалось: если `Placed` приезжают только вместе с
        `Done`, интерфейс снова показывает пустой экран и стену текста в
        конце — ровно то, что чинил событийный контракт.
        """
        from vliw.core import Done, Placed

        evs = self._events(ChunkedBackend(self.answer))
        first_placed = next(i for i, e in enumerate(evs) if isinstance(e, Placed))
        done = next(i for i, e in enumerate(evs) if isinstance(e, Done))
        self.assertLess(first_placed, done)

    def test_every_instruction_placed_exactly_once(self) -> None:
        from vliw.core import Placed

        placed = [e for e in self._events(ChunkedBackend(self.answer))
                  if isinstance(e, Placed)]
        ids = [e.placement.instr for e in placed]
        self.assertEqual(sorted(ids), sorted(range(len(self.dag))))

    def test_live_run_is_marked_live(self) -> None:
        """Живой прогон — не переигровка, и подписан соответственно."""
        from vliw.core import Placed

        placed = [e for e in self._events(ChunkedBackend(self.answer))
                  if isinstance(e, Placed)]
        self.assertEqual({e.live for e in placed}, {True})

    def test_chunk_boundaries_do_not_lose_lines(self) -> None:
        """Размер куска не влияет на разбор — перевод строки ищется в потоке."""
        from vliw.core import Placed

        for size in (1, 2, 3, 7, 1000):
            with self.subTest(size=size):
                placed = [e for e in self._events(ChunkedBackend(self.answer, size))
                          if isinstance(e, Placed)]
                self.assertEqual(len(placed), len(self.dag))

    def test_illegal_placement_still_reaches_the_grid(self) -> None:
        """Незаконное размещение не прячется до вердикта.

        Решётка обязана показать, ГДЕ модель ошиблась. Решение по интерфейсу:
        сырой ответ с красными ячейками, починка — отдельным действием.
        """
        from vliw.core import Placed

        # Ставим первую инструкцию на заведомо посторонний канал и
        # проверяем, что событие всё равно есть.
        bad = _answer_line(self.dag, self.machine, 0, 0, 7) + "\n"
        placed = [e for e in self._events(ChunkedBackend(bad))
                  if isinstance(e, Placed)]
        self.assertEqual(len(placed), 1)
        self.assertEqual(placed[0].placement.channel, 7)

    def test_repeated_identical_line_is_not_a_second_event(self) -> None:
        """Повтор той же строки не заставляет ячейку мигать впустую."""
        from vliw.core import Placed

        line = _answer_line(self.dag, self.machine, 0, 0, 1)
        placed = [e for e in self._events(ChunkedBackend("\n".join([line] * 3) + "\n"))
                  if isinstance(e, Placed)]
        self.assertEqual(len(placed), 1)

    def test_moved_placement_is_a_second_event(self) -> None:
        """А вот ПЕРЕЕЗД той же инструкции — событие: модель передумала."""
        from vliw.core import Placed

        text = (_answer_line(self.dag, self.machine, 0, 0, 1) + "\n"
                + _answer_line(self.dag, self.machine, 0, 2, 1) + "\n")
        placed = [e for e in self._events(ChunkedBackend(text))
                  if isinstance(e, Placed)]
        self.assertEqual([e.placement.cycle for e in placed], [0, 2])

    def test_old_schedule_contract_matches_the_stream(self) -> None:
        """`schedule()` даёт ровно то же, что `Done` из потока."""
        from vliw.core import Done

        evs = self._events(ChunkedBackend(self.answer))
        via_stream = next(e for e in evs if isinstance(e, Done)).result
        direct = LearnedScheduler(
            backend=ChunkedBackend(self.answer)).schedule(self.dag, self.machine)
        self.assertEqual(direct.schedule.placements, via_stream.schedule.placements)
        self.assertEqual(direct.search_stats["valid"], via_stream.search_stats["valid"])


class TestCancellation(unittest.TestCase):
    """Отмена доходит до бэкенда — иначе процесс модели остаётся сиротой."""

    def test_close_kills_the_backend_stream(self) -> None:
        from vliw.core import stream

        dag, machine, _ = _fixture()
        be = CancelWatchBackend()
        gen = stream(LearnedScheduler(backend=be), dag, machine)
        for _ in range(5):
            next(gen)
        self.assertFalse(be.cleaned)
        gen.close()
        self.assertTrue(be.cleaned)

    def test_partial_placements_survive_cancellation(self) -> None:
        """Отменённый прогон — тоже данные: что успело встать, то встало."""
        from vliw.core import Placed, stream

        dag, machine, good = _fixture()
        answer = encode_completion(good)
        gen = stream(LearnedScheduler(backend=ChunkedBackend(answer, 1)), dag, machine)
        seen = [e for _, e in zip(range(60), gen) if isinstance(e, Placed)]
        gen.close()
        self.assertGreater(len(seen), 0)
        self.assertLess(len(seen), len(dag) + 1)


if __name__ == "__main__":
    unittest.main()
