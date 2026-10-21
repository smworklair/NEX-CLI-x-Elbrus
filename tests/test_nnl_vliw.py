"""nnl_vliw: язык графов, два ядра NNL, обучение, загрузка через Матплату, перекрёстная проверка."""

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from nnl_vliw import данные as Д  # noqa: E402
from nnl_vliw import обучить as О  # noqa: E402
from nnl_vliw import оценка as Оц  # noqa: E402
from nnl_vliw import ядра as Я  # noqa: E402
from nnl_vliw.NNL import линтер as Л  # noqa: E402
from nnl_vliw.NNL.матплата import Матплата  # noqa: E402
from nnl_vliw.NNL.процессор import Процессор  # noqa: E402
from nnl_vliw.обучение import сеть as С  # noqa: E402
from nnl_vliw.язык import ВСЕ_ПОНЯТИЯ, ЯзыкГрафов, корзина, понятия_графа  # noqa: E402
from tools import portfolio_labels as PL  # noqa: E402

EVAL = ROOT / "eval_hard.jsonl"
АРХ = ROOT / "nnl_vliw" / "архитектуры"


def prompts(n):
    out = []
    with open(EVAL, encoding="utf-8") as f:
        for line in f:
            out.append(json.loads(line)["prompt"])
            if len(out) == n:
                break
    return out


class TestЯзык(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.я = ЯзыкГрафов()
        cls.p = prompts(30)

    def test_buckets_are_monotone_and_exact_when_small(self):
        v = [корзина(x) for x in range(0, 300)]
        self.assertEqual(v, sorted(v))
        self.assertEqual([корзина(x) for x in range(0, 17)], list(range(17)))
        self.assertGreaterEqual(min(корзина(x) - x for x in range(17, 300)), 0)   # корзина не меньше значения
        self.assertLessEqual(max(корзина(x) - x for x in range(17, 300)), 7)

    def test_translate_is_deterministic_and_nonempty(self):
        a = self.я.перевести(self.p[0])
        b = self.я.перевести(self.p[0])
        self.assertEqual(a, b)
        self.assertGreater(len(a["токены"]), 10)
        self.assertIn("n:", "".join(a["токены"]))

    def test_each_partition_has_exactly_one_side(self):
        for p in self.p:
            c = self.я.перевести(p)["понятия"]
            self.assertEqual(set(c), set(ВСЕ_ПОНЯТИЯ))
            self.assertEqual(c["деления:есть"] + c["деления:нет"], 1.0)
            self.assertEqual(c["память:много"] + c["память:мало"], 1.0)

    def test_division_concept_follows_ops(self):
        from vliw.tiny.features import build_dag, parse_graph_entries
        for p in self.p:
            dag = build_dag(parse_graph_entries(p))
            has = any(i.op in ("DIV", "FDIV") for i in dag)
            self.assertEqual(понятия_графа(dag)["деления:есть"], 1.0 if has else 0.0)

    def test_float_division_counts_as_division(self):
        from vliw.tiny.features import build_dag, parse_graph_entries
        p = "профиль: e2k-v6-measured\nграф:\n0 FDIV\n1 ADD <- 0\n2 LOAD\n3 STORE <- 1 2\nрасписание:"
        dag = build_dag(parse_graph_entries(p))
        c = понятия_графа(dag)
        self.assertEqual(c["деления:есть"], 1.0)
        self.assertEqual(c["память:много"], 1.0)               # LOAD+STORE = 2 из 4
        q = p.replace("FDIV", "ADD")
        self.assertEqual(понятия_графа(build_dag(parse_graph_entries(q)))["деления:есть"], 0.0)
        toks = ЯзыкГрафов().перевести(p)["токены"]
        self.assertTrue(any(t.startswith("оп:FDIV:") for t in toks), toks)

    def test_language_does_not_see_the_answer(self):
        """Токены не меняются, если дописать к prompt любое расписание: язык читает только граф."""
        base = self.p[0]
        with_sched = base + "\n0: такт=0 канал=1\n1: такт=5 канал=2"
        self.assertEqual(self.я.перевести(base)["токены"], self.я.перевести(with_sched)["токены"])


class TestЯдра(unittest.TestCase):
    def test_block_sizes_are_about_100k_and_200k(self):
        for я in Я.ЯДРА:
            оп = Я.описание_блоков(я)
            self.assertEqual(len(оп), 2)
            размеры = sorted(o["корзины"] * o["размер"] for o in оп)
            self.assertTrue(95_000 <= размеры[0] <= 105_000, размеры)
            self.assertTrue(190_000 <= размеры[1] <= 205_000, размеры)

    def test_blocks_read_each_others_concept_and_answers_are_disjoint(self):
        for я in Я.ЯДРА:
            a, b = Я.описание_блоков(я)
            self.assertEqual(a["читает"], b["пишет"])
            self.assertEqual(b["читает"], a["пишет"])
            self.assertFalse(set(a["ответы"]) & set(b["ответы"]))
            self.assertEqual(len(a["ответы"]), len(Я.ГРУППЫ))

    def test_cores_split_differently(self):
        self.assertNotEqual({o["область"] for o in Я.описание_блоков("А")},
                            {o["область"] for o in Я.описание_блоков("Б")})

    def test_answer_ids_roundtrip(self):
        for g in Я.ГРУППЫ:
            self.assertEqual(Я.группа_из_ответа(Я.ответ_id("деления:есть", g)), g)

    def test_row_area_matches_concepts(self):
        c = {"деления:есть": 1.0, "деления:нет": 0.0, "память:много": 0.0, "память:мало": 1.0}
        self.assertEqual(Я.область_строки("А", c), "деления:есть")
        self.assertEqual(Я.область_строки("Б", c), "память:мало")
        with self.assertRaises(ValueError):
            Я.область_строки("А", {})


class TestРазбиение(unittest.TestCase):
    def mk(self, hard, easy):
        base = []
        for i in range(hard):
            base.append({"ключ": f"h{i}", "дешёвая": ("rule", "beam", "prio")[i % 3], "токены": ["a"], "понятия": {}})
        for i in range(easy):
            base.append({"ключ": f"e{i}", "дешёвая": "greedy", "токены": ["a"], "понятия": {}})
        return base

    def test_all_hard_are_used_and_easy_are_capped(self):
        base = self.mk(60, 500)
        tr, dv = Д.разбить(base, доля_жадных=1.0, доля_dev=0.2, зерно=3)
        ключи = [r["ключ"] for r in tr + dv]
        self.assertEqual(len(ключи), len(set(ключи)))
        self.assertEqual(sum(k.startswith("h") for k in ключи), 60)
        self.assertEqual(sum(k.startswith("e") for k in ключи), 60)

    def test_train_and_dev_do_not_overlap_and_dev_sees_every_group(self):
        tr, dv = Д.разбить(self.mk(60, 500), доля_dev=0.2, зерно=1)
        self.assertFalse({r["ключ"] for r in tr} & {r["ключ"] for r in dv})
        self.assertEqual({r["дешёвая"] for r in dv}, {"rule", "beam", "prio", "greedy"})

    def test_split_is_reproducible(self):
        a = Д.разбить(self.mk(30, 100), зерно=7)
        b = Д.разбить(self.mk(30, 100), зерно=7)
        self.assertEqual([r["ключ"] for r in a[0]], [r["ключ"] for r in b[0]])


class TestОбучениеЗагрузкаОценка(unittest.TestCase):
    """Один раз обучаем маленькие ядра на 80 графах eval_hard и проверяем всё, что от них требуется."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp())
        PL._init()
        cls.язык = ЯзыкГрафов()
        метки = [PL.строка((f"t#{i}", p)) for i, p in enumerate(prompts(80))]
        cls.база = Д.с_токенами(метки, cls.язык)
        tr, dv = Д.разбить(cls.база, доля_жадных=1.0, доля_dev=0.2, зерно=1)
        cls.tr, cls.dv = tr, dv
        cls.старые = dict(О.НАСТРОЙКИ_ОБУЧЕНИЯ)
        О.НАСТРОЙКИ_ОБУЧЕНИЯ.update({"эпох": 3, "терпение": 3})
        import contextlib
        import io
        for i, я in enumerate(("А", "Б")):
            with contextlib.redirect_stdout(io.StringIO()):
                О.обучить_ядро(я, tr, dv, 5 + i, cls.tmp, {"тест": True})
        cls.A = Оц.загрузить_ядро(cls.tmp / "А", cls.язык)
        cls.Б = Оц.загрузить_ядро(cls.tmp / "Б", cls.язык)

    @classmethod
    def tearDownClass(cls):
        О.НАСТРОЙКИ_ОБУЧЕНИЯ.clear()
        О.НАСТРОЙКИ_ОБУЧЕНИЯ.update(cls.старые)
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_files_and_passport_hashes(self):
        for я in ("А", "Б"):
            for bd in (self.tmp / я).iterdir():
                if not bd.is_dir():
                    continue
                пасп = json.loads((bd / "паспорт.json").read_text(encoding="utf-8"))
                self.assertEqual(пасп["веса"]["sha256"], О.sha256_файла(bd / "веса.npz"))
                self.assertEqual(пасп["архитектура"], "мешок_шина")
                self.assertEqual(len(пасп["ответы"]), len(Я.ГРУППЫ))
                self.assertIn("проекции", пасп)

    def test_linter_accepts_every_block(self):
        for я in ("А", "Б"):
            for bd in sorted((self.tmp / я).iterdir()):
                if bd.is_dir():
                    r = Л.проверить_блок(str(bd), str(АРХ))
                    self.assertEqual(r["статус"], "УСПЕХ", r["ошибки"])

    def test_parameter_counts(self):
        самые = sorted(b.чисел for b in self.A.блоки.values())
        self.assertTrue(95_000 <= самые[0] <= 105_000 and 190_000 <= самые[1] <= 205_000, самые)

    def test_probabilities_are_a_distribution_over_nothing_and_all_answers(self):
        p = Оц.вероятности(self.A, self.база[0]["токены"])
        self.assertAlmostEqual(sum(p.values()), 1.0, places=9)
        self.assertEqual(len(p), 1 + 2 * len(Я.ГРУППЫ))
        self.assertIn("ничего", p)

    def test_inference_matches_the_trainer_forward(self):
        """Композиция из сохранённых весов (через архитектуру мешок_шина) = прямой проход обучающего кода."""
        опис = Я.описание_блоков("А")
        блоки = []
        for i, о in enumerate(опис):
            P = dict(np.load(self.tmp / "А" / о["имя"] / "веса.npz"))
            init = {k: P[k] for k in ("E", "A", "a", "U", "V", "b")}
            блоки.append(С.БлокУч(о["имя"], о["ответы"], о["пишет"], о["читает"], корзины=о["корзины"], размер=о["размер"],
                                  граница=8.0, соль=о["соль"], seed=1, init=init, область=о["область"], свёртка="корень",
                                  масштаб_чтения=8.0))
        rows = Д.строки_ядра("А", self.база[:25])
        набор = С.Набор(rows, блоки, ВСЕ_ПОНЯТИЯ)
        сеть = С.Сеть(блоки, проходов=2, смешивание="среднее", градиент_через_шину=False)
        p_train = сеть.предсказать(набор)
        for k, r in enumerate(rows):
            p = Оц.вероятности(self.A, r["токены"])
            vec = np.array([p["ничего"]] + [p[a] for a in сеть.все_ответы])
            self.assertTrue(np.allclose(vec, p_train[k], atol=2e-4), (k, np.abs(vec - p_train[k]).max()))

    def test_tampered_weights_are_rejected_by_the_motherboard(self):
        копия = self.tmp / "копия"
        shutil.copytree(self.tmp / "А" / "А_без_делений", копия)
        w = копия / "веса.npz"
        P = dict(np.load(w))
        P["b"] = P["b"] + 1.0
        np.savez(w, **P)
        ok, err = Матплата(self.язык, str(АРХ)).подключить(str(копия))
        self.assertFalse(ok)
        self.assertTrue(any("sha256" in e for e in err), err)

    def test_removing_a_block_removes_only_its_answers(self):
        плата = Оц.загрузить_ядро(self.tmp / "А", self.язык)
        имя = "А_с_делениями"
        self.assertTrue(плата.снять(имя))
        p = Оц.вероятности(плата, self.база[0]["токены"])
        self.assertAlmostEqual(sum(p.values()), 1.0, places=9)
        self.assertEqual(len(p), 1 + len(Я.ГРУППЫ))
        self.assertFalse(any(k.startswith("деления:есть/") for k in p))

    def test_decision_abstains_on_nothing_and_below_threshold(self):
        self.assertEqual(Оц.решение({"ничего": 0.6, "деления:есть/rule": 0.4})[0], None)
        self.assertEqual(Оц.решение({"ничего": 0.1, "деления:есть/rule": 0.9})[0], "rule")
        self.assertEqual(Оц.решение({"ничего": 0.1, "деления:есть/rule": 0.9}, порог=0.95)[0], None)

    def test_makespan_helper_never_worse_than_greedy_and_falls_back(self):
        r = {"по_группам": {"greedy": 10, "prio": 12, "rule": 8, "hold": None}}
        self.assertEqual(Оц.мс(r, "prio"), 10)
        self.assertEqual(Оц.мс(r, "rule"), 8)
        self.assertEqual(Оц.мс(r, "hold"), 10)

    def test_policies_are_consistent(self):
        o = Оц.политики(self.база, self.A, self.Б)
        self.assertEqual(o["графов"], len(self.база))
        self.assertEqual(o["оракул"]["лишних_тактов"], 0)
        ожид = sum(r["по_группам"]["greedy"] - r["лучший"] for r in self.база)
        self.assertEqual(o["жадный"]["лишних_тактов"], ожид)
        self.assertEqual(o["жадный"]["полный_портфель"], 0.0)
        for k in ("ядро А", "ядро Б", "перекрёсток", "эвристика"):
            self.assertGreaterEqual(o[k]["лишних_тактов"], 0)
            self.assertLessEqual(o[k]["лишних_тактов"], ожид)      # лучшее из жадного и группы не хуже жадного
        c = o["согласие"]
        self.assertLessEqual(c["согласны"] + c["расходятся"], o["графов"])

    def test_random_abstention_baseline_and_confidence_curve(self):
        o = Оц.политики(self.база, self.A, self.Б)
        сл = o["случайный отказ"]
        self.assertEqual(сл["полный_портфель"], o["перекрёсток"]["полный_портфель"])
        self.assertAlmostEqual(сл["лишних_тактов"], (1 - сл["полный_портфель"]) * o["ядро А"]["лишних_тактов"], delta=0.06)
        к = o["уверенность ядра А"]
        доли = [x["полный_портфель"] for x in к]
        лишних = [x["лишних_тактов"] for x in к]
        self.assertEqual(доли, sorted(доли))                       # выше порог — чаще отказ
        self.assertEqual(лишних, sorted(лишних, reverse=True))     # отказ не добавляет лишних тактов

    def test_crosscheck_policy_exact_on_scripted_cores(self):
        """Ядра, отвечающие по сценарию: перекрёсток обязан брать группу только при согласии и без «ничего»."""
        база = self.база
        A, Б = object(), object()
        скрипт = {}
        for k, r in enumerate(база):
            pa = {"ничего": 0.1, "деления:есть/rule": 0.9}
            if k % 7 == 0:
                pb = {"ничего": 0.6, "деления:есть/rule": 0.4}       # Б не знает
            elif k % 3 == 0:
                pb = {"ничего": 0.1, "деления:есть/rule": 0.9}       # Б согласен
            else:
                pb = {"ничего": 0.1, "деления:есть/beam": 0.9}       # Б расходится
            скрипт[(id(A), id(r["токены"]))] = pa
            скрипт[(id(Б), id(r["токены"]))] = pb
        исходная = Оц.вероятности
        Оц.вероятности = lambda плата, токены: скрипт[(id(плата), id(токены))]
        try:
            o = Оц.политики(база, A, Б)
        finally:
            Оц.вероятности = исходная
        согласны = [k for k in range(len(база)) if k % 7 != 0 and k % 3 == 0]
        ex_cross = sum(Оц.мс(база[k], "rule") - база[k]["лучший"] for k in согласны)
        self.assertEqual(o["перекрёсток"]["лишних_тактов"], ex_cross)
        self.assertAlmostEqual(o["перекрёсток"]["полный_портфель"], 1 - len(согласны) / len(база), places=4)
        self.assertEqual(o["ядро А"]["лишних_тактов"], sum(Оц.мс(r, "rule") - r["лучший"] for r in база))
        self.assertEqual(o["согласие"]["согласны"], len(согласны))
        # Б ответил «ничего» на k % 7 == 0: там и ядро Б отдаёт портфель целиком
        self.assertAlmostEqual(o["ядро Б"]["полный_портфель"], sum(1 for k in range(len(база)) if k % 7 == 0) / len(база), places=4)

    def test_crosscheck_runs_full_portfolio_exactly_when_cores_disagree_or_abstain(self):
        o = Оц.политики(self.база, self.A, self.Б)
        n_full = 0
        for r in self.база:
            a, _ = Оц.решение(Оц.вероятности(self.A, r["токены"]))
            b, _ = Оц.решение(Оц.вероятности(self.Б, r["токены"]))
            n_full += int(not (a is not None and a == b))
        self.assertAlmostEqual(o["перекрёсток"]["полный_портфель"], n_full / len(self.база), places=4)

    def test_processor_runs_the_core_and_lego_insertion_check_passes(self):
        плата = Оц.загрузить_ядро(self.tmp / "А", self.язык)
        proc = Процессор(плата)
        res = proc.выполнить(prompts(1)[0])
        self.assertEqual(set(res["такт1"]), set(плата.блоки))
        # вставка блока ядра Б в работающую плату ядра А: соседи не меняются
        proc2 = Процессор(Оц.загрузить_ядро(self.tmp / "А", self.язык))
        rep = Л.проверить_вставку(proc2, str(self.tmp / "Б" / "Б_много_памяти"), prompts(15))
        self.assertEqual(rep["статус"], "УСПЕХ", rep["ошибки"])
        self.assertEqual(rep["такт1_соседей_изменилось"], 0)


if __name__ == "__main__":
    unittest.main()
