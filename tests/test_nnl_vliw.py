"""nnl_vliw tests: DAG graph language, dual NNL cores, training, motherboard loading, and cross-check."""

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

from nnl_vliw import данные as D  # noqa: E402
from nnl_vliw import обучить as TR  # noqa: E402
from nnl_vliw import оценка as EV  # noqa: E402
from nnl_vliw import ядра as CORES  # noqa: E402
from nnl_vliw.NNL import линтер as LINTER  # noqa: E402
from nnl_vliw.NNL.матплата import Матплата  # noqa: E402
from nnl_vliw.NNL.процессор import Процессор  # noqa: E402
from nnl_vliw.обучение import сеть as NET  # noqa: E402
from nnl_vliw.язык import ВСЕ_ПОНЯТИЯ, ЯзыкГрафов, корзина, понятия_графа  # noqa: E402
from tools import portfolio_labels as PL  # noqa: E402

EVAL = ROOT / "eval_hard.jsonl"
ARCH_DIR = ROOT / "nnl_vliw" / "архитектуры"


def prompts(n):
    out = []
    with open(EVAL, encoding="utf-8") as f:
        for line in f:
            out.append(json.loads(line)["prompt"])
            if len(out) == n:
                break
    return out


class TestGraphLanguage(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lang = ЯзыкГрафов()
        cls.p = prompts(30)

    def test_buckets_are_monotone_and_exact_when_small(self):
        v = [корзина(x) for x in range(0, 300)]
        self.assertEqual(v, sorted(v))
        self.assertEqual([корзина(x) for x in range(0, 17)], list(range(17)))
        self.assertGreaterEqual(min(корзина(x) - x for x in range(17, 300)), 0)   # bucket >= value
        self.assertLessEqual(max(корзина(x) - x for x in range(17, 300)), 7)

    def test_translate_is_deterministic_and_nonempty(self):
        a = self.lang.перевести(self.p[0])
        b = self.lang.перевести(self.p[0])
        self.assertEqual(a, b)
        self.assertGreater(len(a["токены"]), 10)
        self.assertIn("n:", "".join(a["токены"]))

    def test_each_partition_has_exactly_one_side(self):
        for p in self.p:
            c = self.lang.перевести(p)["понятия"]
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
        self.assertEqual(c["память:много"], 1.0)               # LOAD+STORE = 2 of 4
        q = p.replace("FDIV", "ADD")
        self.assertEqual(понятия_графа(build_dag(parse_graph_entries(q)))["деления:есть"], 0.0)
        toks = ЯзыкГрафов().перевести(p)["токены"]
        self.assertTrue(any(t.startswith("оп:FDIV:") for t in toks), toks)

    def test_language_does_not_see_the_answer(self):
        """Tokens must not change when a schedule is appended to the prompt: the language reads only the DAG."""
        base = self.p[0]
        with_sched = base + "\n0: такт=0 канал=1\n1: такт=5 канал=2"
        self.assertEqual(self.lang.перевести(base)["токены"], self.lang.перевести(with_sched)["токены"])


class TestCores(unittest.TestCase):
    def test_block_sizes_are_about_100k_and_200k(self):
        for core in CORES.ЯДРА:
            specs = CORES.описание_блоков(core)
            self.assertEqual(len(specs), 2)
            sizes = sorted(o["корзины"] * o["размер"] for o in specs)
            self.assertTrue(95_000 <= sizes[0] <= 105_000, sizes)
            self.assertTrue(190_000 <= sizes[1] <= 205_000, sizes)

    def test_blocks_read_each_others_concept_and_answers_are_disjoint(self):
        for core in CORES.ЯДРА:
            a, b = CORES.описание_блоков(core)
            self.assertEqual(a["читает"], b["пишет"])
            self.assertEqual(b["читает"], a["пишет"])
            self.assertFalse(set(a["ответы"]) & set(b["ответы"]))
            self.assertEqual(len(a["ответы"]), len(CORES.ГРУППЫ))

    def test_cores_split_differently(self):
        self.assertNotEqual({o["область"] for o in CORES.описание_блоков("А")},
                            {o["область"] for o in CORES.описание_блоков("Б")})

    def test_answer_ids_roundtrip(self):
        for g in CORES.ГРУППЫ:
            self.assertEqual(CORES.группа_из_ответа(CORES.ответ_id("деления:есть", g)), g)

    def test_row_area_matches_concepts(self):
        c = {"деления:есть": 1.0, "деления:нет": 0.0, "память:много": 0.0, "память:мало": 1.0}
        self.assertEqual(CORES.область_строки("А", c), "деления:есть")
        self.assertEqual(CORES.область_строки("Б", c), "память:мало")
        with self.assertRaises(ValueError):
            CORES.область_строки("А", {})


class TestSplit(unittest.TestCase):
    def mk(self, hard, easy):
        base = []
        for i in range(hard):
            base.append({"ключ": f"h{i}", "дешёвая": ("rule", "beam", "prio")[i % 3], "токены": ["a"], "понятия": {}})
        for i in range(easy):
            base.append({"ключ": f"e{i}", "дешёвая": "greedy", "токены": ["a"], "понятия": {}})
        return base

    def test_all_hard_are_used_and_easy_are_capped(self):
        base = self.mk(60, 500)
        tr, dv = D.разбить(base, доля_жадных=1.0, доля_dev=0.2, зерно=3)
        keys = [r["ключ"] for r in tr + dv]
        self.assertEqual(len(keys), len(set(keys)))
        self.assertEqual(sum(k.startswith("h") for k in keys), 60)
        self.assertEqual(sum(k.startswith("e") for k in keys), 60)

    def test_train_and_dev_do_not_overlap_and_dev_sees_every_group(self):
        tr, dv = D.разбить(self.mk(60, 500), доля_dev=0.2, зерно=1)
        self.assertFalse({r["ключ"] for r in tr} & {r["ключ"] for r in dv})
        self.assertEqual({r["дешёвая"] for r in dv}, {"rule", "beam", "prio", "greedy"})

    def test_split_is_reproducible(self):
        a = D.разбить(self.mk(30, 100), зерно=7)
        b = D.разбить(self.mk(30, 100), зерно=7)
        self.assertEqual([r["ключ"] for r in a[0]], [r["ключ"] for r in b[0]])


class TestTrainLoadEvaluate(unittest.TestCase):
    """Train small dual cores once on 80 eval_hard graphs and verify all end-to-end invariants."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp())
        PL._init()
        cls.lang = ЯзыкГрафов()
        labels = [PL.строка((f"t#{i}", p)) for i, p in enumerate(prompts(80))]
        cls.base = D.с_токенами(labels, cls.lang)
        tr, dv = D.разбить(cls.base, доля_жадных=1.0, доля_dev=0.2, зерно=1)
        cls.tr, cls.dv = tr, dv
        cls.old_cfg = dict(TR.НАСТРОЙКИ_ОБУЧЕНИЯ)
        TR.НАСТРОЙКИ_ОБУЧЕНИЯ.update({"эпох": 3, "терпение": 3})
        import contextlib
        import io
        for i, core in enumerate(("А", "Б")):
            with contextlib.redirect_stdout(io.StringIO()):
                TR.обучить_ядро(core, tr, dv, 5 + i, cls.tmp, {"test": True})
        cls.A = EV.загрузить_ядро(cls.tmp / "А", cls.lang)
        cls.B = EV.загрузить_ядро(cls.tmp / "Б", cls.lang)

    @classmethod
    def tearDownClass(cls):
        TR.НАСТРОЙКИ_ОБУЧЕНИЯ.clear()
        TR.НАСТРОЙКИ_ОБУЧЕНИЯ.update(cls.old_cfg)
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_files_and_passport_hashes(self):
        for core in ("А", "Б"):
            for bd in (self.tmp / core).iterdir():
                if not bd.is_dir():
                    continue
                passport = json.loads((bd / "паспорт.json").read_text(encoding="utf-8"))
                self.assertEqual(passport["веса"]["sha256"], TR.sha256_файла(bd / "веса.npz"))
                self.assertEqual(passport["архитектура"], "мешок_шина")
                self.assertEqual(len(passport["ответы"]), len(CORES.ГРУППЫ))
                self.assertIn("проекции", passport)

    def test_linter_accepts_every_block(self):
        for core in ("А", "Б"):
            for bd in sorted((self.tmp / core).iterdir()):
                if bd.is_dir():
                    r = LINTER.проверить_блок(str(bd), str(ARCH_DIR))
                    self.assertEqual(r["статус"], "УСПЕХ", r["ошибки"])

    def test_parameter_counts(self):
        counts = sorted(b.чисел for b in self.A.блоки.values())
        self.assertTrue(95_000 <= counts[0] <= 105_000 and 190_000 <= counts[1] <= 205_000, counts)

    def test_probabilities_are_a_distribution_over_nothing_and_all_answers(self):
        p = EV.вероятности(self.A, self.base[0]["токены"])
        self.assertAlmostEqual(sum(p.values()), 1.0, places=9)
        self.assertEqual(len(p), 1 + 2 * len(CORES.ГРУППЫ))
        self.assertIn("ничего", p)

    def test_inference_matches_the_trainer_forward(self):
        """Saved-weight inference through the bus architecture must match the trainer's forward pass."""
        specs = CORES.описание_блоков("А")
        blocks = []
        for o in specs:
            P = dict(np.load(self.tmp / "А" / o["имя"] / "веса.npz"))
            init = {k: P[k] for k in ("E", "A", "a", "U", "V", "b")}
            blocks.append(NET.БлокУч(o["имя"], o["ответы"], o["пишет"], o["читает"], корзины=o["корзины"], размер=o["размер"],
                                     граница=8.0, соль=o["соль"], seed=1, init=init, область=o["область"], свёртка="корень",
                                     масштаб_чтения=8.0))
        rows = D.строки_ядра("А", self.base[:25])
        dataset = NET.Набор(rows, blocks, ВСЕ_ПОНЯТИЯ)
        net = NET.Сеть(blocks, проходов=2, смешивание="среднее", градиент_через_шину=False)
        p_train = net.предсказать(dataset)
        for k, r in enumerate(rows):
            p = EV.вероятности(self.A, r["токены"])
            vec = np.array([p["ничего"]] + [p[a] for a in net.все_ответы])
            self.assertTrue(np.allclose(vec, p_train[k], atol=2e-4), (k, np.abs(vec - p_train[k]).max()))

    def test_tampered_weights_are_rejected_by_the_motherboard(self):
        copy_dir = self.tmp / "copy"
        shutil.copytree(self.tmp / "А" / "А_без_делений", copy_dir)
        w = copy_dir / "веса.npz"
        P = dict(np.load(w))
        P["b"] = P["b"] + 1.0
        np.savez(w, **P)
        ok, err = Матплата(self.lang, str(ARCH_DIR)).подключить(str(copy_dir))
        self.assertFalse(ok)
        self.assertTrue(any("sha256" in e for e in err), err)

    def test_removing_a_block_removes_only_its_answers(self):
        board = EV.загрузить_ядро(self.tmp / "А", self.lang)
        name = "А_с_делениями"
        self.assertTrue(board.снять(name))
        p = EV.вероятности(board, self.base[0]["токены"])
        self.assertAlmostEqual(sum(p.values()), 1.0, places=9)
        self.assertEqual(len(p), 1 + len(CORES.ГРУППЫ))
        self.assertFalse(any(k.startswith("деления:есть/") for k in p))

    def test_decision_abstains_on_nothing_and_below_threshold(self):
        self.assertEqual(EV.решение({"ничего": 0.6, "деления:есть/rule": 0.4})[0], None)
        self.assertEqual(EV.решение({"ничего": 0.1, "деления:есть/rule": 0.9})[0], "rule")
        self.assertEqual(EV.решение({"ничего": 0.1, "деления:есть/rule": 0.9}, порог=0.95)[0], None)

    def test_makespan_helper_never_worse_than_greedy_and_falls_back(self):
        r = {"по_группам": {"greedy": 10, "prio": 12, "rule": 8, "hold": None}}
        self.assertEqual(EV.мс(r, "prio"), 10)
        self.assertEqual(EV.мс(r, "rule"), 8)
        self.assertEqual(EV.мс(r, "hold"), 10)

    def test_policies_are_consistent(self):
        o = EV.политики(self.base, self.A, self.B)
        self.assertEqual(o["графов"], len(self.base))
        self.assertEqual(o["оракул"]["лишних_тактов"], 0)
        expected = sum(r["по_группам"]["greedy"] - r["лучший"] for r in self.base)
        self.assertEqual(o["жадный"]["лишних_тактов"], expected)
        self.assertEqual(o["жадный"]["полный_портфель"], 0.0)
        for k in ("ядро А", "ядро Б", "перекрёсток", "эвристика"):
            self.assertGreaterEqual(o[k]["лишних_тактов"], 0)
            self.assertLessEqual(o[k]["лишних_тактов"], expected)  # min(greedy, group) <= greedy
        c = o["согласие"]
        self.assertLessEqual(c["согласны"] + c["расходятся"], o["графов"])

    def test_random_abstention_baseline_and_confidence_curve(self):
        o = EV.политики(self.base, self.A, self.B)
        rnd = o["случайный отказ"]
        self.assertEqual(rnd["полный_портфель"], o["перекрёсток"]["полный_портфель"])
        self.assertAlmostEqual(rnd["лишних_тактов"], (1 - rnd["полный_портфель"]) * o["ядро А"]["лишних_тактов"], delta=0.06)
        curve = o["уверенность ядра А"]
        rates = [x["полный_портфель"] for x in curve]
        excess = [x["лишних_тактов"] for x in curve]
        self.assertEqual(rates, sorted(rates))                      # higher threshold -> more abstentions
        self.assertEqual(excess, sorted(excess, reverse=True))      # abstaining never adds excess cycles

    def test_crosscheck_policy_exact_on_scripted_cores(self):
        """Scripted cores: cross-check must pick a group only on non-abstaining agreement."""
        base = self.base
        A, B = object(), object()
        script = {}
        for k, r in enumerate(base):
            pa = {"ничего": 0.1, "деления:есть/rule": 0.9}
            if k % 7 == 0:
                pb = {"ничего": 0.6, "деления:есть/rule": 0.4}       # B abstains
            elif k % 3 == 0:
                pb = {"ничего": 0.1, "деления:есть/rule": 0.9}       # B agrees
            else:
                pb = {"ничего": 0.1, "деления:есть/beam": 0.9}       # B disagrees
            script[(id(A), id(r["токены"]))] = pa
            script[(id(B), id(r["токены"]))] = pb
        orig = EV.вероятности
        EV.вероятности = lambda board, tokens: script[(id(board), id(tokens))]
        try:
            o = EV.политики(base, A, B)
        finally:
            EV.вероятности = orig
        agreed = [k for k in range(len(base)) if k % 7 != 0 and k % 3 == 0]
        ex_cross = sum(EV.мс(base[k], "rule") - base[k]["лучший"] for k in agreed)
        self.assertEqual(o["перекрёсток"]["лишних_тактов"], ex_cross)
        self.assertAlmostEqual(o["перекрёсток"]["полный_портфель"], 1 - len(agreed) / len(base), places=4)
        self.assertEqual(o["ядро А"]["лишних_тактов"], sum(EV.мс(r, "rule") - r["лучший"] for r in base))
        self.assertEqual(o["согласие"]["согласны"], len(agreed))
        # B abstained on k % 7 == 0, triggering full portfolio fallback
        self.assertAlmostEqual(o["ядро Б"]["полный_портфель"], sum(1 for k in range(len(base)) if k % 7 == 0) / len(base), places=4)

    def test_crosscheck_runs_full_portfolio_exactly_when_cores_disagree_or_abstain(self):
        o = EV.политики(self.base, self.A, self.B)
        n_full = 0
        for r in self.base:
            a, _ = EV.решение(EV.вероятности(self.A, r["токены"]))
            b, _ = EV.решение(EV.вероятности(self.B, r["токены"]))
            n_full += int(not (a is not None and a == b))
        self.assertAlmostEqual(o["перекрёсток"]["полный_портфель"], n_full / len(self.base), places=4)

    def test_processor_runs_the_core_and_lego_insertion_check_passes(self):
        board = EV.загрузить_ядро(self.tmp / "А", self.lang)
        proc = Процессор(board)
        res = proc.выполнить(prompts(1)[0])
        self.assertEqual(set(res["такт1"]), set(board.блоки))
        # Hot-plugging a block from core B into running core A must not alter neighbors' pass-1 outputs
        proc2 = Процессор(EV.загрузить_ядро(self.tmp / "А", self.lang))
        rep = LINTER.проверить_вставку(proc2, str(self.tmp / "Б" / "Б_много_памяти"), prompts(15))
        self.assertEqual(rep["статус"], "УСПЕХ", rep["ошибки"])
        self.assertEqual(rep["такт1_соседей_изменилось"], 0)


if __name__ == "__main__":
    unittest.main()
