"""TINY Flash fast scheduler tests: exact parity with TinyScheduler at lower latency.

Verifies:
  * FastNet computes bit-exact identical scores to TinyPriority.scores (pure Python & numpy);
  * TinyFlashScheduler matches TinyScheduler makespan in "exact" mode and never trails greedy;
  * schedules are complete and legal, with `optimal=True` iff `makespan == lower_bound`;
  * "asm" mode is legal and never worse than greedy.
"""

import json
import random
import threading
import unittest
from pathlib import Path

from vliw.core.baseline import GreedyListScheduler
from vliw.core.dag import SCENARIOS, compute_metrics, random_dag
from vliw.core.model import get_profile
from vliw.tiny import fast
from vliw.tiny.features import build_dag, featurize, parse_graph_entries
from vliw.tiny.model import TinyPriority
from vliw.tiny.scheduler import TinyScheduler

_TINY = Path(__file__).resolve().parent.parent / "vliw" / "tiny"
_HAVE_WEIGHTS = all((_TINY / f).exists()
                    for f in ("weights.json", "weights_defer.json", "weights_hold.json"))
MODEL = get_profile("e2k-v6-measured")


def _graphs(n_random=24):
    gs = list(SCENARIOS.items())
    for seed in range(n_random):
        gs.append((f"rand{seed}", random_dag(seed, n=10 + (seed * 5) % 30)))
    return gs


@unittest.skipUnless(_HAVE_WEIGHTS, "weights not present — available after training")
class TestFastNet(unittest.TestCase):
    def setUp(self):
        self.nets = {n: TinyPriority.load(str(_TINY / f)) for n, f in
                     (("prio", "weights.json"), ("defer", "weights_defer.json"),
                      ("hold", "weights_hold.json"))}
        self.Xs = [featurize(dag, MODEL) for _, dag in _graphs(12)]

    def _variants(self, net):
        yield "pure", fast.FastNet(net)
        yield "pure/no-memo", fast.FastNet(net, 0)
        yield "pure/memo-5", fast.FastNet(net, 5)
        if fast._np is not None:
            yield "numpy", fast.FastNetNp(net)
            yield "numpy/no-memo", fast.FastNetNp(net, 0)
            yield "numpy/memo-5", fast.FastNetNp(net, 5)

    def test_bit_identical(self):
        for name, net in self.nets.items():
            refs = [net.scores(X) for X in self.Xs]
            for label, f in self._variants(net):
                for rep in range(2):  # second pass hits memo cache
                    for X, ref in zip(self.Xs, refs):
                        got = f.scores(X)
                        self.assertEqual(len(got), len(ref))
                        for a, b in zip(ref, got):
                            self.assertTrue(a == b, f"{name}/{label}: {a!r} != {b!r}")

    def test_empty_input(self):
        for _, f in self._variants(self.nets["prio"]):
            self.assertEqual(f.scores([]), [])

    def test_memo_is_bounded(self):
        f = fast.FastNet(self.nets["prio"], 50)
        for X in self.Xs:
            f.scores(X)
            self.assertLessEqual(len(f._memo), 50 + max(len(x) for x in self.Xs))
        f.clear_memo()
        self.assertEqual(len(f._memo), 0)

    def test_duplicates_inside_one_call(self):
        X = self.Xs[0]
        doubled = X + X
        f = fast.FastNet(self.nets["prio"], 0)
        got = f.scores(doubled)
        ref = self.nets["prio"].scores(doubled)
        self.assertEqual(got, ref)

    def test_make_fast_none(self):
        self.assertIsNone(fast.make_fast(None))


@unittest.skipUnless(_HAVE_WEIGHTS, "weights not present — available after training")
class TestTinyFast(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ref = TinyScheduler()
        cls.graphs = _graphs()
        cls.refs = {k: cls.ref.schedule(d, MODEL) for k, d in cls.graphs}

    def _check(self, sched, label):
        for key, dag in self.graphs:
            res = sched.schedule(dag, MODEL)
            r0 = self.refs[key]
            ms = res.schedule.makespan
            with self.subTest(label=label, graph=key):
                self.assertEqual(res.schedule.validate(), [])
                self.assertTrue(res.schedule.complete)
                self.assertEqual(ms, r0.schedule.makespan, "makespan must match TinyScheduler")
                g = GreedyListScheduler().schedule(dag, MODEL).schedule.makespan
                self.assertLessEqual(ms, g)
                lb = compute_metrics(dag, MODEL).lower_bound
                if res.optimal:
                    self.assertEqual(ms, lb, "optimal=True iff makespan == lower_bound")
                self.assertEqual(res.search_stats["lower_bound"], lb)

    def test_exact_default(self):
        self._check(fast.TinyFlashScheduler(), "exact")

    def test_exact_without_numpy(self):
        self._check(fast.TinyFlashScheduler(use_numpy=False), "exact/no-numpy")

    def test_exact_without_stop(self):
        self._check(fast.TinyFlashScheduler(stop_at_bound=False), "exact/no-early-stop")

    def test_exact_without_trace_and_memo(self):
        self._check(fast.TinyFlashScheduler(with_trace=False, memo_limit=0), "exact/no-trace-no-memo")

    def test_custom_order_keeps_result(self):
        """Portfolio group order must not change the final makespan on a full pass."""
        s = fast.TinyFlashScheduler(order=("defer", "hold", "prio", "bt", "rule", "bh"),
                                   stop_at_bound=False)
        self._check(s, "reversed-order")

    def test_asm_mode_legal_not_worse_than_greedy(self):
        s = fast.TinyFlashScheduler(mode="asm")
        for key, dag in self.graphs:
            res = s.schedule(dag, MODEL)
            g = GreedyListScheduler().schedule(dag, MODEL).schedule.makespan
            with self.subTest(graph=key):
                self.assertEqual(res.schedule.validate(), [])
                self.assertTrue(res.schedule.complete)
                self.assertLessEqual(res.schedule.makespan, g)
                self.assertNotIn("hold", res.search_stats["groups_run"])
                self.assertNotIn("defer", res.search_stats["groups_run"])

    def test_greedy_on_bound_skips_search(self):
        s = fast.TinyFlashScheduler()
        hit = 0
        for key, dag in self.graphs:
            res = s.schedule(dag, MODEL)
            st = res.search_stats
            if st["bound_hit_at"] == "greedy":
                hit += 1
                self.assertEqual(st["groups_run"], [])
                self.assertTrue(res.optimal)
                self.assertEqual(st["tiny_winner"], "greedy")
                self.assertEqual(res.schedule.makespan, st["baseline_makespan"])
        self.assertGreater(hit, 0, "expected at least one graph where greedy already meets the lower bound")

    def test_trace_matches_when_same_winner(self):
        s = fast.TinyFlashScheduler()
        same = 0
        for key, dag in self.graphs:
            res = s.schedule(dag, MODEL)
            r0 = self.refs[key]
            if res.search_stats["tiny_winner"] == r0.search_stats["tiny_winner"]:
                same += 1
                self.assertEqual(res.trace, r0.trace, key)
        self.assertGreater(same, 0)

    def test_no_trace_is_empty(self):
        s = fast.TinyFlashScheduler(with_trace=False)
        res = s.schedule(SCENARIOS["slotclash"], MODEL)
        self.assertEqual(res.trace, [])
        self.assertEqual(res.schedule.validate(), [])

    def test_fallback_without_weights_same_as_parent(self):
        parent = TinyScheduler(weights="/nonexistent/weights.json")
        child = fast.TinyFlashScheduler(weights="/nonexistent/weights.json")
        self.assertIsNone(child.tiny)
        for key, dag in self.graphs:
            a = parent.schedule(dag, MODEL).schedule.makespan
            res = child.schedule(dag, MODEL)
            with self.subTest(graph=key):
                self.assertEqual(res.schedule.makespan, a)
                self.assertEqual(res.schedule.validate(), [])

    def test_instance_reuse_has_no_state_leak(self):
        s = fast.TinyFlashScheduler()
        order = list(self.graphs)
        random.Random(1).shuffle(order)
        for key, dag in order + order[:5]:
            res = s.schedule(dag, MODEL)
            self.assertEqual(res.schedule.makespan, self.refs[key].schedule.makespan, key)

    def test_threads(self):
        s = fast.TinyFlashScheduler()
        out: dict[str, int] = {}
        errs: list[str] = []

        def work(items):
            try:
                for key, dag in items:
                    out[key] = s.schedule(dag, MODEL).schedule.makespan
            except Exception as e:  # noqa: BLE001
                errs.append(repr(e))

        gs = self.graphs
        ts = [threading.Thread(target=work, args=(gs[i::4],)) for i in range(4)]
        for t in ts:
            t.start()
        for t in ts:
            t.join()
        self.assertEqual(errs, [])
        for key, _ in gs:
            self.assertEqual(out[key], self.refs[key].schedule.makespan, key)

    def test_bad_arguments(self):
        with self.assertRaises(ValueError):
            fast.TinyFlashScheduler(mode="turbo")
        with self.assertRaises(ValueError):
            fast.TinyFlashScheduler(order=("bh", "nope"))


@unittest.skipUnless(_HAVE_WEIGHTS, "weights not present — available after training")
class TestTinyFastHardSample(unittest.TestCase):
    """Hard graphs from eval_hard.jsonl: sensitive to every portfolio group, ensuring exact parity."""

    N = 100

    @classmethod
    def setUpClass(cls):
        p = Path(__file__).resolve().parent.parent / "eval_hard.jsonl"
        if not p.exists():
            raise unittest.SkipTest("eval_hard.jsonl not present")
        with open(p, encoding="utf-8") as f:
            lines = f.readlines()[:cls.N]
        cls.graphs = [(f"eval_hard#{i}", build_dag(parse_graph_entries(json.loads(l)["prompt"])))
                      for i, l in enumerate(lines)]
        ref = TinyScheduler()
        cls.refs = {k: ref.schedule(d, MODEL).schedule.makespan for k, d in cls.graphs}

    def _same(self, sched, label):
        for key, dag in self.graphs:
            res = sched.schedule(dag, MODEL)
            with self.subTest(label=label, graph=key):
                self.assertEqual(res.schedule.validate(), [])
                self.assertEqual(res.schedule.makespan, self.refs[key])

    def test_exact_equals_full_portfolio(self):
        self._same(fast.TinyFlashScheduler(), "exact")

    def test_exact_without_stop_and_numpy(self):
        self._same(fast.TinyFlashScheduler(stop_at_bound=False, use_numpy=False), "no-early-stop-no-numpy")

    def test_beam_calls_match_parent(self):
        """Must use the exact same fan-out seeds as TinyScheduler so candidate sets match."""
        def record(sched):
            calls = []
            o_orders, o_holds = sched._beam_orders, sched._beam_holds

            def orders(base, k, seed):
                calls.append(("orders", k, seed))
                return o_orders(base, k, seed)

            def holds(base, n, k, seed, limit):
                calls.append(("holds", k, seed))
                return o_holds(base, n, k, seed, limit)

            sched._beam_orders, sched._beam_holds = orders, holds
            return calls

        parent, child = TinyScheduler(), fast.TinyFlashScheduler(stop_at_bound=False)
        pc, cc = record(parent), record(child)
        seen = set()
        for key, dag in self.graphs[:40]:
            pc.clear()
            cc.clear()
            parent.schedule(dag, MODEL)
            child.schedule(dag, MODEL)
            self.assertEqual(sorted(pc), sorted(cc), key)
            seen.update(pc)
        self.assertEqual({(a, c) for a, _, c in seen} & {("orders", 1000), ("orders", 2000)},
                         {("orders", 1000), ("orders", 2000)})
        self.assertIn(("holds", 16, 3000), seen)

    def test_asm_mode_never_worse_than_greedy(self):
        s = fast.TinyFlashScheduler(mode="asm")
        for key, dag in self.graphs:
            g = GreedyListScheduler().schedule(dag, MODEL).schedule.makespan
            res = s.schedule(dag, MODEL)
            with self.subTest(graph=key):
                self.assertLessEqual(res.schedule.makespan, g)
                self.assertEqual(res.schedule.validate(), [])
                # asm mode trades full-portfolio optimality for speed
                self.assertGreaterEqual(res.schedule.makespan, self.refs[key])


class TestFastNoWeightsNeeded(unittest.TestCase):
    def test_constructs_and_runs_without_weights(self):
        s = fast.TinyFlashScheduler(weights="/nonexistent/a.json",
                                   defer_weights="/nonexistent/b.json",
                                   hold_weights="/nonexistent/c.json")
        for key in ("simple4", "slotclash", "memstream", "loadchain", "mixed18"):
            dag = SCENARIOS[key]
            res = s.schedule(dag, MODEL)
            self.assertEqual(res.schedule.validate(), [])
            self.assertLessEqual(
                res.schedule.makespan,
                GreedyListScheduler().schedule(dag, MODEL).schedule.makespan)


class TestRenameCompat(unittest.TestCase):
    """Legacy name TinyFastScheduler remains an alias after renaming to TINY Flash."""

    def test_old_name_is_alias(self):
        self.assertIs(fast.TinyFastScheduler, fast.TinyFlashScheduler)


if __name__ == "__main__":
    unittest.main()
