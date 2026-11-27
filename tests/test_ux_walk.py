"""End-to-end engineer UX walk: real `.s` file -> F5 -> legal VLIW schedule.

Guards two independent regressions:
1. Typing `/` in the command bar used to reset the input to `"/"`, making it
   impossible to type paths containing slashes (`/code load /.../poly_gemm.s`).
2. F5 on large real graphs (190 ops in `poly_gemm.s`) used to overrun the
   oracle time budget inside `_count_vectors` without falling back.

Headless testing rules: assert only widget/session state (never pixel coords),
type with small pauses, and verify input length before pressing Enter.
"""

from __future__ import annotations

import asyncio
import io
import time
import unittest
from contextlib import redirect_stdout
from pathlib import Path

try:
    import textual  # noqa: F401

    HAS_TEXTUAL = True
except Exception:  # pragma: no cover - environment-dependent
    HAS_TEXTUAL = False

from vliw import cli


def _make_app(start_mode):
    """Build app and session matching `cli.run_tui()` (mirrors test_tui_smoke)."""
    import tempfile

    from vliw.tui.app import NexApp
    from vliw.tui.screens.code_screen import CodeScreen

    CodeScreen.LAYOUT_FILE = Path(tempfile.mkdtemp(prefix="nex-test-")) / "layout.json"

    args = cli._build_parser().parse_args([])
    session = cli.Session(args=args)
    cli._apply_mode(session, start_mode or "lab")
    app = NexApp(session, lambda line: cli.handle_input(session, line),
                 cli.COMMANDS, start_mode=start_mode)
    return app, session


def _poly_gemm_path() -> str:
    root = Path(__file__).resolve().parent.parent
    p = root / "real_candidates_100_400" / "asm" / "poly_gemm.s"
    # Use forward slashes even on Windows to test slash input handling.
    return p.resolve().as_posix()


@unittest.skipUnless(HAS_TEXTUAL, "textual is not installed — skipping full-screen UX walk")
class TestUxWalk(unittest.TestCase):
    """Type a path with slashes -> press F5 on 190-op graph -> legal schedule within budget."""

    def test_type_path_with_slashes_then_f5_on_real_graph(self):
        poly = _poly_gemm_path()
        self.assertTrue(Path(poly).exists(), f"missing fixture file {poly}")
        # Path must contain slashes to exercise the slash-key regression.
        self.assertIn("/", poly)

        full_cmd = f"/code load {poly}"
        # Ctrl+P prefills "/"; type the remainder.
        rest = full_cmd[1:]

        async def run():
            app, session = _make_app("code")
            with redirect_stdout(io.StringIO()):
                async with app.run_test(size=(150, 46)) as pilot:
                    await pilot.pause()
                    await pilot.pause()
                    screen = app.screen
                    self.assertEqual(screen.__class__.__name__, "CodeScreen")

                    # 1. Initial focus is on the code editor.
                    focused_id = getattr(app.focused, "id", "")
                    self.assertEqual(focused_id, "code-edit",
                                     f"initial focus was {focused_id!r}, expected code-edit")

                    # 2. Standard command bar shortcut is Ctrl+P (focus + "/" prefill).
                    await pilot.press("ctrl+p")
                    await pilot.pause()
                    await pilot.pause()
                    focused_id = getattr(app.focused, "id", "")
                    self.assertEqual(focused_id, "prompt-input",
                                     f"focus after Ctrl+P was {focused_id!r}, expected prompt-input")
                    bar = screen.query_one("#prompt")
                    self.assertEqual(bar.input.value, "/",
                                     "Ctrl+P prefill must be '/'")

                    # 3. Type the command slowly; send "/" as "slash" to exercise action_slash.
                    for ch in rest:
                        if ch == "/":
                            await pilot.press("slash")
                        else:
                            await pilot.press(ch)
                        await pilot.pause(0.05)
                    await pilot.pause()
                    await pilot.pause()

                    # 4. Verify full command string before pressing Enter.
                    typed = screen.query_one("#prompt").input.value
                    self.assertEqual(
                        typed, full_cmd,
                        f"slash input truncated: {typed!r} != {full_cmd!r}")

                    # 5. Execute `/code load`.
                    await pilot.press("enter")
                    try:
                        await asyncio.wait_for(app.workers.wait_for_complete(),
                                               timeout=20)
                    except asyncio.TimeoutError:
                        self.fail("workers did not finish within 20s after /code load")
                    await pilot.pause()
                    await pilot.pause()

                    self.assertEqual(session.code_path, poly,
                                     f"code_path {session.code_path!r} != {poly!r}")
                    self.assertTrue(session.code_text.strip(),
                                    "code buffer is empty after /code load")
                    edit = screen.query_one("#code-edit")
                    self.assertEqual(edit.text, session.code_text,
                                     "editor did not load the file")

                    # Real graph: >=100 ops (poly_gemm has 190).
                    from vliw.core import asm_parser

                    parsed = asm_parser.parse_asm(session.code_text,
                                                  source="<buffer>")
                    n_ops = len(parsed.ops)
                    self.assertGreaterEqual(
                        n_ops, 100,
                        f"graph has {n_ops} ops — test requires >=100")

                    # 6. Press F5 and measure wall-clock time.
                    t0 = time.monotonic()
                    await pilot.press("f5")
                    try:
                        await asyncio.wait_for(app.workers.wait_for_complete(),
                                               timeout=55)
                    except asyncio.TimeoutError:
                        self.fail(
                            "F5 hung past 55s: oracle budget/fallback failed")
                    await pilot.pause()
                    await pilot.pause()
                    elapsed = time.monotonic() - t0

                    cached = session.peek()
                    self.assertIsNotNone(cached, "no cached result in session.peek() after F5")
                    base, orc, met = cached
                    errs = list(orc.schedule.validate())
                    self.assertEqual(errs, [],
                                     f"illegal schedule: {errs[:5]}")
                    self.assertTrue(getattr(orc.schedule, "complete", True),
                                    "incomplete schedule")
                    self.assertGreater(orc.schedule.makespan, 0)
                    self.assertGreaterEqual(len(orc.schedule.dag), 100)
                    return elapsed, orc.schedule.makespan, n_ops

        elapsed, makespan, n_ops = asyncio.run(run())
        self.assertLess(
            elapsed, 60,
            f"F5 on {n_ops} ops took {elapsed:.1f}s — expected seconds, not minutes")
        self.assertGreater(makespan, 0)
