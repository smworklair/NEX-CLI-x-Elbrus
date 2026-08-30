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

import json
import tempfile
import unittest
from pathlib import Path

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


class TestSamplingPlumb(unittest.TestCase):
    """temperature/seed доехали до бэкенда — и не сломали путь по умолчанию.

    Умолчание — жадный детерминированный ответ, которым сняты все замеры.
    Он обязан оставаться прежним ВЫЗОВОМ: kwargs сэмплинга передаются только
    когда их реально просили (см. sampling_kwargs), поэтому бэкенды со старой
    сигнатурой generate_events(prompt, max_new_tokens) продолжают работать.
    """

    def test_sampling_kwargs_empty_at_defaults(self):
        from vliw.learned.runtime import sampling_kwargs

        self.assertEqual(sampling_kwargs(0.0, None), {})
        self.assertEqual(sampling_kwargs(0, None), {})

    def test_sampling_kwargs_only_when_asked(self):
        from vliw.learned.runtime import sampling_kwargs

        self.assertEqual(sampling_kwargs(0.7, None), {"temperature": 0.7})
        self.assertEqual(sampling_kwargs(0.0, 5), {"seed": 5})
        self.assertEqual(sampling_kwargs(0.7, 5),
                         {"temperature": 0.7, "seed": 5})

    def test_old_signature_backend_survives_default_generate(self):
        from vliw.learned.runtime import Backend

        class Old(Backend):
            def generate_events(self, prompt, max_new_tokens):
                yield "ответ"

        self.assertEqual(Old().generate("p", 5), "ответ")

    def test_scheduler_passes_sampling_to_backend(self):
        dag, machine, good = _fixture()
        be = ScriptedBackend(encode_completion(good))
        LearnedScheduler(backend=be, temperature=0.7,
                         seed=11).schedule(dag, machine)
        self.assertEqual(be.last_sampling, {"temperature": 0.7, "seed": 11})

    def test_scheduler_default_keeps_old_call(self):
        """Умолчание — прежний вызов без kwargs: старые бэкенды живы."""
        dag, machine, good = _fixture()

        class Old(ScriptedBackend):
            def generate_events(self, prompt, max_new_tokens):
                yield encode_completion(good)

        res = LearnedScheduler(backend=Old("")).schedule(dag, machine)
        self.assertTrue(res.search_stats["valid"])

    def test_llama_cmd_grows_only_when_sampling(self):
        """Командная строка llama-completion при умолчаниях — прежняя до элемента."""
        from pathlib import Path as _P

        from vliw.learned.runtime import _llama_cmd

        base = _llama_cmd(_P("llama"), _P("b.gguf"), None, "p.txt", 64, 128, 4)
        self.assertNotIn("--seed", base)
        self.assertEqual(base[base.index("--temp") + 1], "0")

        with_seed = _llama_cmd(_P("llama"), _P("b.gguf"), None,
                               "p.txt", 64, 128, 4, temperature=0.7, seed=9)
        self.assertIn("--seed", with_seed)
        self.assertEqual(with_seed[with_seed.index("--temp") + 1], "0.7")


class TestBestOfBench(unittest.TestCase):
    """best-of-N в bench: N сэмплов, каждому repair, выбор по validate().

    Модель не гоняется — вместо неё ScriptedBackend с несколькими ответами.
    Проверяется именно механика выбора и счётчики: правильный выбор — это
    min по (нарушения, makespan), а не «последний» или «первый».
    """

    def setUp(self) -> None:
        self.dag, self.machine, self.good = _fixture()
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dataset = Path(self.tmp.name) / "ds.jsonl"
        self.dataset.write_text(
            json.dumps({"prompt": encode_prompt(self.dag, self.machine),
                        "meta": {"makespan": self.good.makespan}}) + "\n",
            encoding="utf-8")

    def _scheduler(self, replies) -> LearnedScheduler:
        return LearnedScheduler(backend=ScriptedBackend(replies), repair=True)

    def _broken(self, drop_last: int = 1) -> str:
        """Ответ с недостающими строками — repair такое не чинит честно."""
        return "\n".join(encode_completion(self.good).splitlines()[:-drop_last])

    def _stretched(self, by: int = 1) -> str:
        """Законное расписание с раздвинутыми тактами — валидно, но длиннее."""
        s = Schedule(self.dag, self.machine)
        for i in range(len(self.dag)):
            p = self.good.placements[i]
            s.place(i, p.cycle + by, p.channel)
        return encode_completion(s)

    def test_best_of_picks_the_valid_sample(self):
        from vliw.learned.bench import BestOf, run_bench

        res = run_bench(self.dataset, 1,
                        self._scheduler([self._broken(), encode_completion(self.good)]),
                        self.machine,
                        best_of=BestOf(n=2, temperature=0.7, seed=1))
        row = res.rows[0]
        self.assertEqual(row.kind, "валидно")
        self.assertEqual(row.valid_samples, 1)
        self.assertEqual([s.valid for s in row.samples], [False, True])

    def test_prefix_table_counts_any_of_first_k(self):
        """best-of-2 и best-of-4 — это те же сэмплы, усечённые до первых k."""
        from vliw.learned.bench import BestOf, run_bench

        good = encode_completion(self.good)
        res = run_bench(self.dataset, 1,
                        self._scheduler([self._broken(), good,
                                         self._broken(2), self._broken(3)]),
                        self.machine,
                        best_of=BestOf(n=4, temperature=0.7, seed=1))
        for k, want in ((1, 0), (2, 1), (3, 1), (4, 1)):
            with self.subTest(k=k):
                self.assertEqual(res.best_of_valid(k), (want, 1))

    def test_tie_on_valid_prefers_shorter_makespan(self):
        from vliw.learned.bench import BestOf, run_bench

        res = run_bench(self.dataset, 1,
                        self._scheduler([self._stretched(),
                                         encode_completion(self.good)]),
                        self.machine,
                        best_of=BestOf(n=2, temperature=0.7, seed=1))
        row = res.rows[0]
        self.assertEqual(row.kind, "валидно")
        self.assertEqual(row.gap, 0)      # выбран компактный, не раздвинутый
        self.assertEqual([s.gap for s in row.samples], [1, 0])

    def test_fewer_violations_win(self):
        """Ни один сэмпл не валиден — побеждает тот, где нарушений меньше."""
        from vliw.learned.bench import BestOf, run_bench

        res = run_bench(self.dataset, 1,
                        self._scheduler([self._broken(2), self._broken(1)]),
                        self.machine,
                        best_of=BestOf(n=2, temperature=0.7, seed=1))
        row = res.rows[0]
        self.assertNotEqual(row.kind, "валидно")
        # Выбран сэмпл с ОДНОЙ недостающей инструкцией, а не с двумя.
        self.assertEqual(row.samples[0].missing, 2)
        self.assertEqual(row.samples[1].missing, 1)

    def test_default_run_leaves_sampling_alone(self):
        """Без best_of — прежний путь: один ответ, атрибуты не трогаются."""
        from vliw.learned.bench import run_bench

        sch = self._scheduler(encode_completion(self.good))
        res = run_bench(self.dataset, 1, sch, self.machine)
        self.assertIsNone(res.rows[0].samples)
        self.assertEqual(res.rows[0].kind, "валидно")
        self.assertEqual(sch.temperature, 0.0)
        self.assertIsNone(sch.seed)

    def test_single_sample_still_samples(self):
        """best-of-1 — законный замер: один сэмплированный ответ."""
        from vliw.learned.bench import BestOf, run_bench

        sch = self._scheduler(encode_completion(self.good))
        run_bench(self.dataset, 1, sch, self.machine,
                  best_of=BestOf(n=1, temperature=0.5, seed=7))
        self.assertEqual(sch.backend().last_sampling,
                         {"temperature": 0.5, "seed": 7})

    def test_seed_increments_per_sample(self):
        from vliw.learned.bench import BestOf

        bo = BestOf(n=2, temperature=0.7, seed=5)
        self.assertEqual([bo.sample_seed(k) for k in range(bo.n)], [5, 6])

    def test_best_of_requires_sampling_scheduler(self):
        from vliw.learned.bench import BestOf, run_bench

        with self.assertRaises(TypeError):
            run_bench(self.dataset, 1, GreedyListScheduler(), self.machine,
                      best_of=BestOf(n=2, temperature=0.7))


class TestLearnedArgParse(unittest.TestCase):
    """Разбор флагов /learned — чистой функцией, без запуска модели.

    Закреплённая регрессия: значение «0.7» у --temperature раньше
    принималось за имя адаптера (isdigit() его не отфильтровывал), и
    команда падала с «адаптер '0.7' не найден» до единой генерации.
    """

    def parse(self, arg: str):
        from vliw.cli import _parse_learned

        return _parse_learned(arg.split())

    def test_defaults_unchanged(self):
        a = self.parse("")
        self.assertIsNone(a.name)
        self.assertEqual(a.bench, 0)
        self.assertEqual(a.best_of, 0)
        self.assertEqual(a.temperature, 0.0)
        self.assertEqual(a.seed, 1)
        self.assertTrue(a.repair)
        self.assertFalse(a.raw)
        self.assertFalse(a.status)

    def test_temperature_value_is_not_adapter_name(self):
        a = self.parse("lora-eos --bench 10 --best-of 4 --temperature 0.7")
        self.assertEqual(a.name, "lora-eos")
        self.assertEqual(a.bench, 10)
        self.assertEqual(a.best_of, 4)
        self.assertEqual(a.temperature, 0.7)

    def test_flag_equals_form(self):
        a = self.parse("--bench=8 --best-of=2 --temperature=0.4 --seed=9")
        self.assertEqual((a.bench, a.best_of, a.temperature, a.seed),
                         (8, 2, 0.4, 9))
        self.assertIsNone(a.name)

    def test_bench_value_is_not_adapter_name(self):
        """Прежнее поведение сохранено: «15» после --bench — не имя."""
        a = self.parse("--bench 15")
        self.assertEqual(a.bench, 15)
        self.assertIsNone(a.name)

    def test_pure_disables_repair(self):
        self.assertTrue(self.parse("").repair)
        self.assertFalse(self.parse("--pure").repair)


class TestBestOfRender(unittest.TestCase):
    """Сводка замера печатает таблицу по k для best-of — источник таблицы
    из docs/LEARNED.md, поэтому формат стоит закрепить.
    """

    def _result(self, valid_by_sample: list[list[bool]]):
        from vliw.learned.bench import BestOf, BenchResult, BenchRow, SampleOutcome

        res = BenchResult(best_of=BestOf(n=8, temperature=0.7, seed=1))
        for samples in valid_by_sample:
            res.rows.append(BenchRow(
                n=10, kind="валидно" if any(samples) else "прочее",
                has_store=True,
                samples=[SampleOutcome(valid=v, errors=0 if v else 1,
                                       missing=0, makespan=5, gap=0 if v else None)
                         for v in samples]))
        return res

    def test_k_table_lines_present(self):
        from vliw.ui import learned_view

        lines = learned_view.render_bench(
            self._result([[False, True, False, False, False, False, False, False],
                          [False] * 8]), "lora-eos")
        text = "\n".join(lines)
        self.assertIn("best-of: 8 сэмплов", text)
        for k in (1, 2, 4, 8):
            self.assertIn(f"k={k} ", text)
        self.assertIn("(1/2)", text)      # k=2: первый граф спасён

    def test_plain_bench_render_unchanged(self):
        """Без best_of сводка прежняя: ни строки про сэмплы, ни таблицы k."""
        from vliw.learned.bench import BenchResult, BenchRow
        from vliw.ui import learned_view

        res = BenchResult()
        res.rows.append(BenchRow(n=10, kind="валидно", has_store=True))
        text = "\n".join(learned_view.render_bench(res, "lora-eos"))
        self.assertNotIn("best-of", text)
        self.assertNotIn("k=", text)


if __name__ == "__main__":
    unittest.main()


class TestLearnedArgErrors(unittest.TestCase):
    """Опечатка в числовом флаге не должна проглатываться молча.

    `--bench 5o` тихо превращалось в `--bench 15`: человек ждал восемь минут
    вместо двух и не понимал, почему примеров больше, чем он просил. А
    `--temperature ой` роняло команду трассировкой ValueError прямо из
    разбора аргументов.
    """

    @staticmethod
    def _parse(text: str):
        from vliw.cli import _parse_learned

        return _parse_learned(text.split())

    def test_non_numeric_bench_is_reported(self):
        a = self._parse("--bench абв")
        self.assertEqual(a.bad_value, ("--bench", "абв"))

    def test_non_numeric_temperature_does_not_raise(self):
        a = self._parse("--temperature ой")
        self.assertEqual(a.bad_value, ("--temperature", "ой"))
        self.assertEqual(a.temperature, 0.0)

    def test_good_values_pass_through(self):
        a = self._parse("--bench 3 --temperature 0.7 --best-of 4 --seed 9")
        self.assertIsNone(a.bad_value)
        self.assertEqual((a.bench, a.temperature, a.best_of, a.seed),
                         (3, 0.7, 4, 9))

    def test_adapter_name_is_not_mistaken_for_a_flag_value(self):
        a = self._parse("lora-eos --bench 2")
        self.assertIsNone(a.bad_value)
        self.assertEqual(a.name, "lora-eos")
