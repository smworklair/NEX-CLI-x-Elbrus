"""NNL AI («есть ли что улучшать») и TINY AI рядом: правило границы, панель, контекст агента, блоки файла."""

from __future__ import annotations

import asyncio
import io
import unittest
from contextlib import redirect_stdout
from pathlib import Path

try:
    import textual  # noqa: F401

    HAS_TEXTUAL = True
except Exception:  # pragma: no cover
    HAS_TEXTUAL = False

from vliw import ai_hints, cli
from vliw.agent import context

ROOT = Path(__file__).resolve().parent.parent
ASM = ROOT / "real_candidates_100_400" / "asm" / "poly_jacobi2d.s"


def _session(scenario="slotclash"):
    s = cli.Session(args=cli._build_parser().parse_args([]))
    s.set_scenario(scenario)
    return s


class TestBoundaryRule(unittest.TestCase):
    def test_rule_is_exact_on_builtin_scenarios(self):
        """Если NNL AI ссылается на правило («baseline на границе»), оракул и правда не лучше baseline."""
        for sc in cli.SCENARIOS:
            s = _session(sc)
            base, orc, _ = s.results()
            nn = ai_hints.nnl_ai(s.dag_obj, s.model(), base.schedule.makespan)
            self.assertIsNotNone(nn, sc)
            if nn.rule:
                self.assertEqual(nn.verdict, "нет", sc)
                self.assertEqual(orc.schedule.makespan, base.schedule.makespan, sc)

    def test_gap_means_model_is_asked(self):
        s = _session("slotclash")
        base, _orc, _ = s.results()
        nn = ai_hints.nnl_ai(s.dag_obj, s.model(), base.schedule.makespan)
        self.assertFalse(nn.rule)
        self.assertGreater(nn.gap, 0)
        self.assertTrue(0.0 <= nn.p_есть <= 1.0)

    def test_tiny_ai_is_never_worse_than_baseline(self):
        for sc in ("slotclash", "memstream", "loadchain"):
            s = _session(sc)
            base, orc, _ = s.results()
            t = ai_hints.tiny_ai(s.dag_obj, s.model(), base.schedule.makespan, orc.schedule.makespan)
            self.assertTrue(t.legal)
            self.assertLessEqual(t.tiny, t.baseline, sc)


class TestAgentFacts(unittest.TestCase):
    def test_context_has_nnl_line(self):
        s = _session("slotclash")
        s.results()
        text = context.build(s)
        self.assertIn("NNL AI", text)

    def test_rule_line_says_it_is_not_an_estimate(self):
        s = _session("simple4")
        s.results()
        line = " ".join(ai_hints.nnl_facts(s))
        self.assertIn("доказано", line)
        self.assertIn("не оценка", line)


@unittest.skipUnless(ASM.exists(), "нет файла .s")
class TestBlocks(unittest.TestCase):
    def test_blocks_proven_by_rule_go_last(self):
        s = _session()
        rows, total = ai_hints.block_rows(ASM.read_text(encoding="utf-8"), s.model(), limit=50)
        self.assertGreater(total, 0)
        flags = [bool(r.nnl and r.nnl.rule) for r in rows]
        self.assertEqual(flags, sorted(flags), "блоки на границе должны идти после остальных")
        for r in rows:
            self.assertLessEqual(r.tiny, r.baseline)


@unittest.skipUnless(HAS_TEXTUAL, "textual не установлен")
class TestPanel(unittest.TestCase):
    def test_lab_shows_both_nets(self):
        from tests.test_tui_smoke import _make_app

        async def go():
            app, session = _make_app("lab")
            session.set_scenario("slotclash")
            with redirect_stdout(io.StringIO()):
                async with app.run_test(size=(170, 56)) as pilot:
                    for _ in range(12):
                        await pilot.pause(0.5)
                    body = app.screen.query_one("#ai-body")
                    return str(body.render())

        text = asyncio.run(go())
        self.assertIn("TINY AI", text)
        self.assertIn("NNL AI", text)


if __name__ == "__main__":
    unittest.main()
