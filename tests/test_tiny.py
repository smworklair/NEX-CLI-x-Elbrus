"""Тесты крошки-1: размер, законность, фолбэк, никогда не хуже baseline."""

import unittest

from vliw.core.baseline import GreedyListScheduler
from vliw.core.dag import get_scenario
from vliw.core.model import get_profile
from vliw.tiny.features import N_FEATURES, featurize
from vliw.tiny.model import TinyPriority
from vliw.tiny.scheduler import TinyScheduler


class TestTiny(unittest.TestCase):
    def test_feature_dim(self):
        m = get_profile("e2k-v6-measured")
        dag = get_scenario("slotclash")
        X = featurize(dag, m)
        self.assertEqual(len(X), len(dag))
        self.assertEqual(len(X[0]), N_FEATURES)

    def test_param_budget(self):
        t = TinyPriority.init(hidden=(128, 64), seed=0)
        self.assertLessEqual(t.param_count(), 150_000)
        t2 = TinyPriority.init(hidden=(256, 128), seed=0)
        self.assertLessEqual(t2.param_count(), 150_000)

    def test_save_load_roundtrip(self):
        import tempfile, os
        t = TinyPriority.init(seed=1)
        m = get_profile("e2k-v6-measured")
        X = featurize(get_scenario("simple4"), m)
        s0 = t.scores(X)
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "w.json")
            t.save(p)
            t2 = TinyPriority.load(p)
        s1 = t2.scores(X)
        for a, b in zip(s0, s1):
            self.assertAlmostEqual(a, b)

    def test_fallback_without_weights_is_baseline(self):
        m = get_profile("e2k-v6-measured")
        dag = get_scenario("slotclash")
        s = TinyScheduler(weights="/nonexistent/weights.json")
        self.assertIsNone(s.tiny)
        res = s.schedule(dag, m)
        base = GreedyListScheduler().schedule(dag, m).schedule.makespan
        self.assertEqual(res.schedule.makespan, base)
        self.assertEqual(res.schedule.validate(), [])

    def test_never_worse_than_baseline(self):
        m = get_profile("e2k-v6-measured")
        s = TinyScheduler(weights="/nonexistent/weights.json")
        for key in ("simple4", "slotclash", "memstream", "loadchain", "mixed18"):
            dag = get_scenario(key)
            res = s.schedule(dag, m)
            base = GreedyListScheduler().schedule(dag, m).schedule.makespan
            self.assertEqual(res.schedule.validate(), [])
            self.assertLessEqual(res.schedule.makespan, base)

    def test_trained_weights_valid_if_present(self):
        from pathlib import Path
        p = Path(__file__).resolve().parent.parent / "vliw" / "tiny" / "weights.json"
        if not p.exists():
            self.skipTest("весов нет — только после обучения")
        s = TinyScheduler(str(p))
        self.assertIsNotNone(s.tiny)
        m = get_profile("e2k-v6-measured")
        dag = get_scenario("slotclash")
        res = s.schedule(dag, m)
        self.assertEqual(res.schedule.validate(), [])


class TestEvalFlags(unittest.TestCase):
    """Флаги эвала для абляции: --beam и --ignore-weights."""

    def _run_eval(self, argv):
        import contextlib
        import io
        import unittest.mock as mock

        from vliw.tiny import eval as tiny_eval

        buf = io.StringIO()
        with mock.patch("sys.argv", ["eval"] + argv), \
                contextlib.redirect_stdout(buf):
            tiny_eval.main()
        return buf.getvalue()

    def test_beam_zero_runs(self):
        out = self._run_eval(["--eval", "eval_hard.jsonl", "--limit", "2",
                              "--beam", "0"])
        self.assertIn("valid=2/2", out)

    def test_ignore_weights_runs(self):
        out = self._run_eval(["--eval", "eval_hard.jsonl", "--limit", "2",
                              "--ignore-weights"])
        self.assertIn("valid=2/2", out)


if __name__ == "__main__":
    unittest.main()
