"""Законность переписывания: короче — оставляем, иначе исходный граф."""

from __future__ import annotations

import unittest

from nnl_rewrite.приёмы import применить, правило
from vliw.core.baseline import GreedyListScheduler
from vliw.core.dag import DAG, DagBuilder, Instr, get_scenario
from vliw.core.model import E2K_V6_MEASURED as M

_G = GreedyListScheduler()


def _ms(dag: DAG) -> int:
    res = _G.schedule(dag, M)
    errs = res.schedule.validate()
    if errs:
        raise AssertionError(errs[0])
    return res.schedule.makespan


class TestRewrite(unittest.TestCase):
    def test_seqreduce_matches_treereduce(self):
        src = get_scenario("seqreduce")
        it = применить(src, M)
        self.assertEqual(it.приём, "дерево ADD")
        self.assertEqual(it.было, 14)
        self.assertEqual(it.стало, 11)
        self.assertEqual(it.стало, _ms(get_scenario("treereduce")))
        self.assertEqual(правило(src, M), "дерево ADD")

    def test_const_chain_is_shorter_and_legal(self):
        b = DagBuilder("addr", "addr")
        a = b.op("ADD", "p0", args="p0 = 0x0")
        for i in range(1, 4):
            a = b.op("ADD", f"p{i}", a, args=f"p{i} = prev + 0x8")
        dag = b.build()
        it = применить(dag, M)
        self.assertEqual(it.приём, "цепочка адресов")
        self.assertLess(it.стало, it.было)
        self.assertEqual(it.стало, _ms(it.dag))

    def test_udiv_pow2_becomes_shift(self):
        dag = DAG("u", "u", "", [
            Instr(0, "q", "DIV", (), "udivs,5 %r1, 0x8, %r2"),
            Instr(1, "s", "ADD", (0,), "addd,0 %r2, %r3, %r4"),
        ])
        it = применить(dag, M)
        self.assertEqual(it.приём, "сдвиг вместо деления")
        self.assertLess(it.стало, it.было)
        self.assertIn("SHL", {i.op for i in it.dag})
        self.assertEqual(_ms(it.dag), it.стало)

    def test_sdiv_pow2_is_forbidden(self):
        dag = DAG("s", "s", "", [
            Instr(0, "q", "DIV", (), "sdivs,5 %r1, 0x8, %r2"),
        ])
        it = применить(dag, M)
        self.assertIsNone(it.приём)
        self.assertEqual(it.стало, it.было)
        self.assertEqual(it.dag.instrs[0].op, "DIV")

    def test_register_div_is_not_a_shift(self):
        dag = DAG("r", "r", "", [
            Instr(0, "q", "DIV", (), "udivs,5 %r1, %r2, %r3"),
        ])
        it = применить(dag, M)
        self.assertIsNone(it.приём)

    def test_fadd_chain_stays_without_permission(self):
        b = DagBuilder("fp", "fp")
        loads = [b.op("LOAD", f"v{i}") for i in range(4)]
        acc = b.op("FADD", "a0", loads[0], loads[1])
        acc = b.op("FADD", "a1", acc, loads[2])
        b.op("FADD", "a2", acc, loads[3])
        dag = b.build()
        it = применить(dag, M, fp=False)
        self.assertIsNone(it.приём)
        self.assertTrue(any(i.op == "FADD" for i in it.dag))
        allowed = применить(dag, M, fp=True)
        self.assertEqual(allowed.приём, "дерево FADD (разрешено)")
        self.assertLess(allowed.стало, allowed.было)
        self.assertEqual(_ms(allowed.dag), allowed.стало)

    def test_untouched_scenario_is_not_worse(self):
        dag = get_scenario("slotclash")
        it = применить(dag, M)
        self.assertIsNone(it.приём)
        self.assertEqual(it.стало, _ms(dag))
        self.assertIsNone(правило(dag, M))

    def test_engine_never_returns_a_longer_graph(self):
        for key in ("divpressure", "memstream", "ptrchase", "unroll4", "ifconv"):
            it = применить(get_scenario(key), M)
            self.assertLessEqual(it.стало, it.было, key)
            self.assertEqual(_ms(it.dag), it.стало, key)


if __name__ == "__main__":
    unittest.main()
