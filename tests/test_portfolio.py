"""CAB: портфель законных расписаний из одного ответа модели.

Что здесь закрепляется и почему именно это. Ценность CAB держится на одном
утверждении — «расписание законно по построению, а не по удаче». Утверждение
сильное, и проверять его надо на ЗАВЕДОМО испорченном ответе: если модель
выдала операции на каналах, которые их не исполняют, портфель обязан всё
равно выдать законное расписание, а не почти законное.

Второе, что тут стережётся, — честность отбора. При равенстве тактов
побеждать обязан ответ самой модели, иначе портфель будет приписывать
алгоритму победы там, где модель справилась сама и её лишь пересчитали в то
же число тактов. Такая регрессия молчаливая: цифры в отчёте не изменятся,
изменится только подпись под ними, — поэтому без теста её никто не заметит.
"""

from __future__ import annotations

import unittest

from training.encode import encode_completion
from vliw.core import GreedyListScheduler, get_profile, get_scenario
from vliw.core.dag import compute_metrics
from vliw.core.schedule import Schedule
from vliw.learned import portfolio as P
from vliw.learned.runtime import ScriptedBackend
from vliw.learned.scheduler import LearnedScheduler


def _fixture(scenario: str = "slotclash"):
    dag = get_scenario(scenario)
    machine = get_profile("e2k-v6-measured")
    return dag, machine


def _as_answer(dag, machine, placements) -> str:
    """Расстановка → текст ответа модели в обучающем формате."""
    sched = Schedule(dag, machine)
    for i, (c, ch) in sorted(placements.items()):
        sched.place(i, c, ch)
    return encode_completion(sched)


def _all_on_channel_zero(dag, machine):
    """Ответ модели, где такты разумны, а канал у всех один — нулевой.

    Это не выдумка ради теста: ровно так выглядел самый частый провал в
    `docs/DIAG3.md` — STORE на канале `,0` (194 раза), потому что в данных
    прогона 1 не было ни одной записи в память.
    """
    good = GreedyListScheduler().schedule(dag, machine).schedule
    return {p.instr: (p.cycle, 0) for p in good.placements.values()}


class TestOrderFromModel(unittest.TestCase):
    def test_placed_ops_keep_model_order(self):
        """Порядок — по (такт, канал) модели, а не по номерам инструкций."""
        placements = {0: (5, 0), 1: (0, 3), 2: (0, 1)}
        prio = P.order_from_model(placements, 3, height=[0, 0, 0])
        # 1 стоит в такте 0 на канале 1... нет: канал 3. Раньше всех — тот,
        # у кого меньше (такт, канал): это 2, потом 1, потом 0.
        self.assertGreater(prio[2], prio[1])
        self.assertGreater(prio[1], prio[0])

    def test_unplaced_go_last_by_height(self):
        """О чём модель не высказалась — в хвост, и там по правилу baseline."""
        placements = {1: (0, 0)}
        prio = P.order_from_model(placements, 3, height=[7, 0, 2])
        self.assertGreater(prio[1], prio[0], "размещённая обязана идти раньше")
        self.assertGreater(prio[0], prio[2], "в хвосте — по убыванию height")

    def test_empty_answer_degrades_to_height(self):
        """Пустой ответ — это ровно baseline, а не случайный порядок."""
        dag, machine = _fixture()
        height = compute_metrics(dag, machine).height
        prio = P.order_from_model({}, len(dag), height)
        by_prio = sorted(range(len(dag)), key=lambda i: -prio[i])
        by_height = sorted(range(len(dag)), key=lambda i: (-int(height[i]), i))
        self.assertEqual(by_prio, by_height)


class TestFloorFromModel(unittest.TestCase):
    def test_hallucinated_cycle_is_dropped(self):
        """Такт за пределами потолка — сбой формата, а не мнение о планировании.

        Без отсечения одно число «такт 900» растянуло бы расписание на 900
        тактов — совершенно законно и совершенно бессмысленно.
        """
        floor = P.floor_from_model({0: (3, 0), 1: (900, 0)}, limit=25)
        self.assertEqual(floor, {0: 3})

    def test_zero_cycle_needs_no_floor(self):
        """Запрет «не раньше нулевого такта» — не запрет, и в карту не идёт."""
        self.assertEqual(P.floor_from_model({0: (0, 0)}, limit=25), {})


class TestVariantsAreLegalByConstruction(unittest.TestCase):
    def test_broken_answer_still_yields_legal_schedules(self):
        dag, machine = _fixture()
        broken = _all_on_channel_zero(dag, machine)

        raw = Schedule(dag, machine)
        for i, (c, ch) in broken.items():
            raw.place(i, c, ch)
        self.assertTrue(raw.validate(), "фикстура обязана быть незаконной")

        cands = P.variants(dag, machine, broken)
        self.assertTrue(cands)
        for c in cands:
            with self.subTest(variant=c.name):
                self.assertTrue(c.legal, f"{c.name}: {c.errors}")
                self.assertTrue(c.schedule.complete)

    def test_winner_never_worse_than_greedy(self):
        """Портфель обязан быть не хуже эвристики: она сама в нём лежит."""
        dag, machine = _fixture()
        broken = _all_on_channel_zero(dag, machine)
        cands = P.variants(dag, machine, broken)
        greedy = next(c for c in cands if c.name == "жадный")
        self.assertLessEqual(P.choose(cands).makespan, greedy.makespan)


class TestChooseIsHonest(unittest.TestCase):
    def test_tie_goes_to_the_earlier_candidate(self):
        """При равенстве тактов побеждает тот, кто раньше в списке.

        Первым идёт ответ самой модели — значит алгоритму не приписывается
        победа там, где он ничего не улучшил.
        """
        dag, machine = _fixture("simple4")
        good = GreedyListScheduler().schedule(dag, machine).schedule
        mine = P.Variant("модель", "сырой ответ", good, ())
        clone = P.Variant("порядок", "порядок от модели", good, ())
        self.assertEqual(P.choose([mine, clone]).name, "модель")
        self.assertEqual(P.choose([clone, mine]).name, "порядок")

    def test_illegal_never_wins_over_legal(self):
        dag, machine = _fixture("simple4")
        good = GreedyListScheduler().schedule(dag, machine).schedule
        short = Schedule(dag, machine)
        for p in good.placements.values():
            short.place(p.instr, 0, 0)          # всё в один такт на один канал
        cands = [P.Variant("модель", "сырой", short, tuple(short.validate())),
                 P.Variant("жадный", "baseline", good, ())]
        self.assertEqual(P.choose(cands).name, "жадный")


class TestWiredIntoScheduler(unittest.TestCase):
    def test_cab_off_by_default_keeps_model_answer(self):
        """Без флага поведение обязано остаться прежним, до строчки.

        Все прежние замеры сняты без портфеля, и менять их смысл молча
        нельзя — это ровно та ошибка, из-за которой 84% из DIAG3 жили только
        в отчёте.
        """
        dag, machine = _fixture()
        broken = _all_on_channel_zero(dag, machine)
        text = _as_answer(dag, machine, broken)
        res = LearnedScheduler(backend=ScriptedBackend(text)).schedule(dag, machine)
        self.assertFalse(res.search_stats["valid"])
        self.assertIsNone(res.search_stats.get("cab_winner"))

    def test_cab_on_makes_the_result_legal(self):
        dag, machine = _fixture()
        broken = _all_on_channel_zero(dag, machine)
        text = _as_answer(dag, machine, broken)
        res = LearnedScheduler(backend=ScriptedBackend(text),
                               cab=True).schedule(dag, machine)
        self.assertEqual(res.schedule.validate(), [])
        self.assertTrue(res.schedule.complete)
        self.assertIsNotNone(res.search_stats["cab_winner"])
        rows = res.search_stats["cab"]
        self.assertTrue(any(r["won"] for r in rows))
        self.assertTrue(any("порядок" in r["name"] for r in rows))


if __name__ == "__main__":
    unittest.main()


class TestMetricsFollowTheFinalSchedule(unittest.TestCase):
    """Инструкция, не выданная моделью, но размещённая портфелем.

    Стережёт конкретную ошибку проводки: `valid` считался по `missing` от
    СЫРОГО ответа, и полное законное расписание из портфеля всё равно
    попадало в замер как провал. Такая регрессия тихая — она не ломает
    ничего, только занижает все числа замера разом.
    """

    def test_valid_is_about_the_result_not_the_raw_answer(self):
        dag, machine = _fixture()
        placements = _all_on_channel_zero(dag, machine)
        del placements[max(placements)]          # модель оборвалась на последней
        res = LearnedScheduler(backend=ScriptedBackend(
            _as_answer(dag, machine, placements)), cab=True).schedule(dag, machine)

        self.assertTrue(res.search_stats["missing"], "фикстура: строка потеряна")
        self.assertTrue(res.schedule.complete)
        self.assertTrue(res.search_stats["valid"])


class TestTieIsNotAWin(unittest.TestCase):
    """Победа вничью — не улучшение, и в отчёте это обязано различаться.

    Ответ модели стоит в портфеле первым и забирает равенство себе — так и
    задумано, иначе алгоритму приписывались бы чужие заслуги. Но обратная
    ошибка не менее вредна: замер на трудном эвале показал семь побед
    кандидатов модели при пяти реальных улучшениях, и без этого разделения
    отчёт записывал бы две ничьи в заслугу.
    """

    def test_matching_the_heuristic_is_not_beating_it(self):
        dag, machine = _fixture()
        greedy = GreedyListScheduler().schedule(dag, machine).schedule
        answer = {p.instr: (p.cycle, p.channel) for p in greedy.placements.values()}
        res = LearnedScheduler(backend=ScriptedBackend(
            _as_answer(dag, machine, answer)), cab=True).schedule(dag, machine)

        self.assertEqual(res.search_stats["cab_winner"], "модель")
        self.assertFalse(res.search_stats["cab_beat_greedy"],
                         "совпадение с эвристикой записано как выигрыш у неё")

    def test_strictly_shorter_counts_as_a_win(self):
        """`slotclash`: жадный даёт 23, оптимум 22 — есть что обыгрывать."""
        from vliw.core.oracle import OracleScheduler

        dag, machine = _fixture()
        orc = OracleScheduler().schedule(dag, machine)
        # Такты оптимума, каналы намеренно сломаны: так выглядел провал DIAG3.
        answer = {p.instr: (p.cycle, 0) for p in orc.schedule.placements.values()}
        res = LearnedScheduler(backend=ScriptedBackend(
            _as_answer(dag, machine, answer)), cab=True).schedule(dag, machine)

        self.assertEqual(res.schedule.validate(), [])
        self.assertEqual(res.schedule.makespan, orc.schedule.makespan)
        self.assertTrue(res.search_stats["cab_beat_greedy"])
        self.assertNotEqual(res.search_stats["cab_winner"], "жадный")
