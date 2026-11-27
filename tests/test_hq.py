"""Agent HQ: focus areas, prompt assembly, and connection snapshot dispatch.

Runs offline: the backend is replaced with a call recorder, while `cli.Session`
is real so prompts are built from the same scheduling facts as live dialogue.
"""

from __future__ import annotations

import unittest

from vliw import cli
from vliw.agent import hq


class FakeBackend:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def complete(self, system: str, question: str, temperature: float = 0.3) -> str:
        self.calls.append((system, question))
        return "done"


def _session():
    args = cli._build_parser().parse_args([])
    return cli.Session(args=args)


class TestAreas(unittest.TestCase):
    def test_areas_have_defaults_except_free(self) -> None:
        by_id = {aid: q for aid, _, q in hq.AREAS}
        self.assertTrue(by_id["doctor"])
        self.assertTrue(by_id["compare"])
        self.assertEqual(by_id["free"], "")
        self.assertEqual(len(by_id), len(hq.AREAS), "area IDs must be unique")

    def test_mission_system_appends_area_and_script(self) -> None:
        system = hq.mission_system(_session(), "doctor", "reply as a bullet list")
        self.assertIn("losses", system)
        self.assertIn("reply as a bullet list", system)
        plain = hq.mission_system(_session(), "free", "")
        self.assertNotIn("MISSION SCRIPT", plain)

    def test_run_mission_routes_to_backend_snapshot(self) -> None:
        be = FakeBackend()
        out = hq.run_mission(be, "SYS", "what is slow?")
        self.assertEqual(out, "done")
        self.assertEqual(be.calls, [("SYS", "what is slow?")])


try:
    import textual  # noqa: F401

    HAS_TEXTUAL = True
except Exception:  # pragma: no cover
    HAS_TEXTUAL = False


@unittest.skipUnless(HAS_TEXTUAL, "textual is not installed")
class TestHQDispatch(unittest.TestCase):
    def test_run_sends_task_and_shows_answer(self) -> None:
        import asyncio
        import io
        import unittest.mock as mock
        from contextlib import redirect_stdout

        from textual.widgets import Input

        from tests.test_tui_smoke import _make_app
        from vliw.tui.widgets import Panel, Tool

        async def go():
            from tests.test_tui_smoke import TestModelCatalogPanel

            tmp, a, b, c = TestModelCatalogPanel._isolated()
            with a, b, c, \
                    mock.patch("vliw.agent.hq.run_mission",
                               return_value="analysis ready") as mission:
                app, session = _make_app("mind")
                with redirect_stdout(io.StringIO()):
                    async with app.run_test(size=(120, 40)) as pilot:
                        await pilot.pause()
                        sc = app.screen
                        panel = sc.query_one("#p-hq", Panel)
                        await TestModelCatalogPanel._click_center(
                            pilot, panel, times=2)
                        await pilot.pause()
                        be = FakeBackend()
                        with mock.patch.object(
                                sc, "headquarters_connections",
                                return_value=[("le chat · m", be)]):
                            sc._redraw_hq()
                            await pilot.pause()
                            task = sc.query_one("#hq-task", Input)
                            await pilot.click(task, offset=(2, 0))
                            await pilot.pause()
                            await pilot.press(*"what is slow?", "enter")
                            await app.workers.wait_for_complete()
                            await pilot.pause()
                            return (list(sc._hq_tasks),
                                    mission.call_args.args[2]
                                    if mission.called else "")

        tasks, question = asyncio.run(go())
        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0]["status"], "done")
        self.assertEqual(tasks[0]["answer"], "analysis ready")
        self.assertIn("what is slow?", question)


if __name__ == "__main__":
    unittest.main()
