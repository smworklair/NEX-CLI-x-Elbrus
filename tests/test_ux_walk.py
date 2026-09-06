"""Прогулка инженера: настоящий .s → F5 → законное расписание.

Зачем этот тест
----------------
Инженер открывает НАСТОЯЩИЙ .s (например poly_gemm.s, 190 узлов), жмёт F5
и быстро получает законное расписание. Раньше это было сломано двумя
независимыми багами, и каждый из них этот тест ловит:

1. Клавиша `/` сносила набранную команду: `action_slash` при фокусе НЕ в
   редакторе звал `action_command()` → `set_value("/")`, и из
   `/code load /home/.../poly_gemm.s` оставалось `/poly_gemm.s`. Набрать
   путь со слэшами с клавиатуры было невозможно.

2. F5 висел мимо бюджета на реальных графах: проверка дедлайна `ctx.tick()`
   была во внешнем цикле комбинаций `_candidate_subsets`, но НЕ во
   внутреннем переборе `_count_vectors` — `budget_s=10` не ограничивал этот
   путь, `session.results()` не возвращался, фолбэк на портфель не срабатывал.

Правила headless (иначе тест врёт)
----------------------------------
* Никаких ассертов на скриншоты/пиксели/координаты: headless-регионы нулевые.
  Только стейт: `.value` виджетов, `app.focused`, `session.code_text`,
  `session.peek()`, makespan, `validate()`.
* Печать с паузами (~0.05 с/символ) и проверкой длины ДО Enter: быстрая
  печать headless теряет символы (артефакт харнесса, не продукта).
* Фокус проверяем чтением `app.focused` после каждого перехода.
* Не печатаем в `#core-input` (даёт «странный символ» — ошибка харнесса),
  не пишем напрямую в `session.code_text` (воюет с редактором как источником
  правды — F5 посчитает демо-буфер).
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
except Exception:  # pragma: no cover - зависит от окружения
    HAS_TEXTUAL = False

from vliw import cli


def _make_app(start_mode):
    """Приложение и сессия — как в `cli.run_tui()` (образец: test_tui_smoke)."""
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
    return str(p.resolve())


@unittest.skipUnless(HAS_TEXTUAL, "textual не установлен — полноэкранный режим не проверяем")
class TestUxWalk(unittest.TestCase):
    """Инженер: набрать путь со слэшами → F5 на 190 узлах → законно и быстро."""

    def test_type_path_with_slashes_then_f5_on_real_graph(self):
        poly = _poly_gemm_path()
        self.assertTrue(Path(poly).exists(), f"нет файла {poly}")
        # Путь обязан содержать слэши — иначе тест не про тот баг.
        self.assertIn("/", poly)

        full_cmd = f"/code load {poly}"
        # После ^P префилл уже "/", допечатываем остаток.
        rest = full_cmd[1:]

        async def run():
            app, session = _make_app("code")
            with redirect_stdout(io.StringIO()):
                async with app.run_test(size=(150, 46)) as pilot:
                    await pilot.pause()
                    await pilot.pause()
                    screen = app.screen
                    self.assertEqual(screen.__class__.__name__, "CodeScreen")

                    # 1. Стартовый фокус — редактор (так задумано).
                    focused_id = getattr(app.focused, "id", "")
                    self.assertEqual(focused_id, "code-edit",
                                     f"стартовый фокус {focused_id!r}, а не code-edit")

                    # 2. Штатный путь к строке команд — ^P (фокус + префилл "/").
                    await pilot.press("ctrl+p")
                    await pilot.pause()
                    await pilot.pause()
                    focused_id = getattr(app.focused, "id", "")
                    self.assertEqual(focused_id, "prompt-input",
                                     f"после ^P фокус {focused_id!r}, а не prompt-input")
                    bar = screen.query_one("#prompt")
                    self.assertEqual(bar.input.value, "/",
                                     "префилл ^P обязан быть '/'")

                    # 3. Печатаем остаток медленно, как человек.
                    # "/" жмём как "slash": именно эта клавиша раньше сносила
                    # команду через action_slash → set_value("/").
                    for ch in rest:
                        if ch == "/":
                            await pilot.press("slash")
                        else:
                            await pilot.press(ch)
                        await pilot.pause(0.05)
                    await pilot.pause()
                    await pilot.pause()

                    # 4. Проверка длины ДО Enter (быстрая печать headless
                    # теряет символы — это артефакт харнесса, ловим его здесь,
                    # а не в ложном «баге ввода»).
                    typed = screen.query_one("#prompt").input.value
                    self.assertEqual(
                        typed, full_cmd,
                        f"ввод со слэшами дошёл не целиком: {typed!r} != {full_cmd!r}. "
                        "На незафикшенном коде здесь остаётся '/poly_gemm.s'.")

                    # 5. Выполняем загрузку штатным путём.
                    await pilot.press("enter")
                    try:
                        await asyncio.wait_for(app.workers.wait_for_complete(),
                                               timeout=20)
                    except asyncio.TimeoutError:
                        self.fail("воркеры не завершились за 20с после /code load")
                    await pilot.pause()
                    await pilot.pause()

                    self.assertEqual(session.code_path, poly,
                                     f"code_path {session.code_path!r} != {poly!r}")
                    self.assertTrue(session.code_text.strip(),
                                    "буфер пуст после /code load")
                    edit = screen.query_one("#code-edit")
                    self.assertEqual(edit.text, session.code_text,
                                     "редактор не подхватил загруженный файл")

                    # Граф настоящий: ≥100 узлов (poly_gemm — 190).
                    from vliw.core import asm_parser

                    parsed = asm_parser.parse_asm(session.code_text,
                                                  source="<буфер>")
                    n_ops = len(parsed.ops)
                    self.assertGreaterEqual(
                        n_ops, 100,
                        f"граф {n_ops} узлов — тест обязан идти на ≥100")

                    # 6. F5 — прогнать буфер. Замеряем стену.
                    t0 = time.monotonic()
                    await pilot.press("f5")
                    try:
                        await asyncio.wait_for(app.workers.wait_for_complete(),
                                               timeout=55)
                    except asyncio.TimeoutError:
                        self.fail(
                            "F5 висел дольше 55с: бюджет oracle не сработал, "
                            "фолбэк на портфель не наступил (баг _candidate_subsets)")
                    await pilot.pause()
                    await pilot.pause()
                    elapsed = time.monotonic() - t0

                    cached = session.peek()
                    self.assertIsNotNone(cached, "после F5 нет кэша session.peek()")
                    base, orc, met = cached
                    errs = list(orc.schedule.validate())
                    self.assertEqual(errs, [],
                                     f"расписание незаконно: {errs[:5]}")
                    self.assertTrue(getattr(orc.schedule, "complete", True),
                                    "расписание неполное")
                    self.assertGreater(orc.schedule.makespan, 0)
                    self.assertGreaterEqual(len(orc.schedule.dag), 100)
                    return elapsed, orc.schedule.makespan, n_ops

        elapsed, makespan, n_ops = asyncio.run(run())
        self.assertLess(
            elapsed, 60,
            f"F5 на {n_ops} узлах занял {elapsed:.1f}с — ориентир секунды, не минуты")
        self.assertGreater(makespan, 0)
