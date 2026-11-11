"""TINY AI рядом с инструментом: честность против baseline, блоки файла, панель, контекст агента.

NNL AI из CLI убран (он оценивал «есть ли что улучшать» и в самой CLI был лишним),
поэтому здесь проверяется только TINY AI — крошки, которые строят расписание.
"""

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


class TestTinyAI(unittest.TestCase):
    def test_tiny_ai_is_never_worse_than_baseline(self):
        for sc in ("slotclash", "memstream", "loadchain"):
            s = _session(sc)
            base, orc, _ = s.results()
            t = ai_hints.tiny_ai(s.dag_obj, s.model(), base.schedule.makespan, orc.schedule.makespan)
            self.assertIsNotNone(t, sc)
            self.assertTrue(t.legal, sc)
            self.assertLessEqual(t.tiny, t.baseline, sc)

    def test_collect_returns_tiny_and_no_nnl_field(self):
        s = _session("slotclash")
        base, orc, _ = s.results()
        h = ai_hints.collect(s, base, orc, with_blocks=False)
        self.assertIsNotNone(h.tiny)
        self.assertFalse(hasattr(h, "nnl"), "NNL AI из CLI убран")
        self.assertEqual(h.blocks, [])


class TestAgentFacts(unittest.TestCase):
    def test_context_has_tiny_line(self):
        s = _session("slotclash")
        s.results()
        text = context.build(s)
        self.assertIn("крошки", text)

    def test_context_has_no_nnl_ai(self):
        s = _session("slotclash")
        s.results()
        self.assertNotIn("NNL AI", context.build(s))

    def test_ai_hints_module_has_no_nnl_ai(self):
        self.assertFalse(hasattr(ai_hints, "nnl_ai"))
        self.assertFalse(hasattr(ai_hints, "nnl_facts"))
        self.assertFalse(hasattr(ai_hints, "NnlAI"))


@unittest.skipUnless(ASM.exists(), "нет файла .s")
class TestBlocks(unittest.TestCase):
    def test_blocks_sorted_by_tiny_gain(self):
        s = _session()
        rows, total = ai_hints.block_rows(ASM.read_text(encoding="utf-8"), s.model(), limit=50)
        self.assertGreater(total, 0)
        gains = [(r.tiny_gain, r.n) for r in rows]
        self.assertEqual(gains, sorted(gains, key=lambda g: (-g[0], -g[1])),
                         "блоки идут по убыванию выигрыша крошек")
        for r in rows:
            self.assertLessEqual(r.tiny, r.baseline)


@unittest.skipUnless(HAS_TEXTUAL, "textual не установлен")
class TestPanel(unittest.TestCase):
    def test_lab_shows_tiny_but_not_nnl(self):
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
        self.assertIn("TINY Flash", text)
        self.assertNotIn("NNL AI", text)


if __name__ == "__main__":
    unittest.main()
