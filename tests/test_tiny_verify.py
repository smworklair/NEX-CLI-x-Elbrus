"""Быстрый CI-инвариант крошки: валидность + never-worse на малом наборе.

Полная батарея (1317+ графов, ~2 мин) — отдельно:
    python -m vliw.tiny.verify --weights vliw/tiny/weights.json
Здесь — то, что должно лететь за секунды на каждый коммит.
"""

import json
import unittest
from pathlib import Path

from vliw.core.baseline import GreedyListScheduler
from vliw.core.dag import SCENARIOS, get_scenario, random_dag
from vliw.core.model import get_profile
from vliw.tiny.features import build_dag, parse_graph_entries
from vliw.tiny.scheduler import TinyScheduler

ROOT = Path(__file__).resolve().parent.parent
WEIGHTS = str(ROOT / "vliw" / "tiny" / "weights.json")


class TestTinyVerifyFast(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.prof = get_profile("e2k-v6-measured")
        cls.sched = TinyScheduler(WEIGHTS)
        cls.base = GreedyListScheduler()

    def _assert_never_worse_and_valid(self, dag, tag):
        res = self.sched.schedule(dag, self.prof)
        self.assertEqual(res.schedule.validate(), [], f"невалид: {tag}")
        self.assertTrue(res.schedule.complete, f"неполно: {tag}")
        b = self.base.schedule(dag, self.prof).schedule.makespan
        self.assertLessEqual(res.schedule.makespan, b, f"хуже baseline: {tag}")

    def test_scenarios(self):
        for key, dag in SCENARIOS.items():
            self._assert_never_worse_and_valid(dag, f"scenario/{key}")

    def test_dev_sample(self):
        p = ROOT / "eval_hard_dev.jsonl"
        if not p.exists():
            self.skipTest("нет eval_hard_dev.jsonl")
        with open(p, encoding="utf-8") as f:
            lines = f.readlines()[:20]
        for i, line in enumerate(lines):
            ex = json.loads(line)
            dag = build_dag(parse_graph_entries(ex["prompt"]))
            self._assert_never_worse_and_valid(dag, f"dev/{i}")

    def test_fuzz_small(self):
        import random
        rnd = random.Random(99)
        for k in range(20):
            dag = random_dag(rnd.randrange(1 << 30),
                             n=rnd.choice([8, 12, 16, 20, 24]))
            self._assert_never_worse_and_valid(dag, f"fuzz/{k}")

    def test_slotclash_regress(self):
        # Ловушка монополиста: крошка обязана не проиграть baseline.
        dag = get_scenario("slotclash")
        res = self.sched.schedule(dag, self.prof)
        b = self.base.schedule(dag, self.prof).schedule.makespan
        self.assertLessEqual(res.schedule.makespan, b)


if __name__ == "__main__":
    unittest.main()
