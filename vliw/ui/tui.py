"""Полноэкранный NEX CLI: выбор режима, затем одна вкладка.

Раскладка как раньше: вывод, в разборе — боковая панель контекста,
внизу полоса ввода с ▌. Три режима — вкладки, не три колонки.
"""

from __future__ import annotations

import contextlib
import io
import os
import sys

from . import ansi2curses as a2c
from . import context, launcher, logo, panes, render, slash

MIN_WIDTH = 60
SIDEBAR_WIDTH = 34
MAX_BUFFER = 5000
PALETTE_ROWS = 14
TAB_H = 1
DOCK_H = 2
HINT_H = 1

PANEL_BG = 236
HEAD_FG = 0
BAR = "▌"
PLACEHOLDERS = {
    "work": "2+2    a=10    sum 8    load 0",
    "lab":  "/  палитра команд    или    /run slotclash",
    "mind": "спросите обычным языком    /  команды",
}


def available(min_width: int = MIN_WIDTH) -> bool:
    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        return False
    try:
        import curses  # noqa: F401
    except Exception:
        return False
    return render.term_cols() >= min_width


def compute_layout(h: int, w: int, pal: int, picking: bool = False,
                   sidebar: bool = False) -> dict:
    """Геометрия: вкладки сверху, в разборе — боковая панель."""
    tab_h = 0 if picking else TAB_H
    bottom = pal + (1 if pal else 0) + DOCK_H + HINT_H
    body_y = tab_h
    body_h = max(3, h - body_y - bottom)
    side = SIDEBAR_WIDTH if (sidebar and not picking and w >= MIN_WIDTH + SIDEBAR_WIDTH) else 0
    main_w = max(20, w - side)
    # вкладки — текстовые, не на всю ширину
    tabs = {}
    x = 1
    for name in panes.PANES:
        tw = 14
        tabs[name] = (x, tw)
        x += tw
    return {
        "h": h, "w": w, "pal": pal,
        "body_y": body_y, "body_h": body_h,
        "tab_y": 0, "tabs": tabs,
        "side": side, "main_w": main_w,
        "dock_y": body_y + body_h + (pal + 1 if pal else 0),
    }


class _Buffer:
    def __init__(self) -> None:
        self.lines: list[str] = []
        self.scroll = 0
        self._partial = ""

    def write(self, text: str) -> None:
        data = self._partial + text
        parts = data.split("\n")
        self._partial = parts.pop()
        self.lines.extend(parts)
        if len(self.lines) > MAX_BUFFER:
            del self.lines[: len(self.lines) - MAX_BUFFER]

    def flush_partial(self) -> None:
        if self._partial:
            self.lines.append(self._partial)
            self._partial = ""

    def clear(self) -> None:
        self.lines.clear()
        self._partial = ""
        self.scroll = 0

    def load(self, rows: list[str]) -> None:
        self.clear()
        if rows:
            self.write("\n".join(rows) + "\n")
        self.flush_partial()
        self.scroll = 0

    @property
    def empty(self) -> bool:
        return not self.lines and not self._partial


class _Sink(io.TextIOBase):
    def __init__(self, buf: _Buffer, on_write) -> None:
        self._buf = buf
        self._on_write = on_write

    def write(self, s: str) -> int:
        self._buf.write(s)
        self._on_write()
        return len(s)

    def writable(self) -> bool:
        return True

    def flush(self) -> None:
        pass


class Tui:
    def __init__(self, curses_mod, stdscr, session, execute, commands, complete,
                 classify, pick_app: bool = True):
        self.curses = curses_mod
        self.stdscr = stdscr
        self.session = session
        self.execute = execute
        self.commands = commands
        self.complete = complete
        self.classify = classify
        self.bufs = {name: _Buffer() for name in panes.PANES}
        self.focus = getattr(session, "focus", None) or "lab"
        if self.focus not in panes.PANES:
            self.focus = "lab"
        session.focus = self.focus
        self.input = ""
        self.history: list[str] = []
        self.hist_pos: int | None = None
        self.note = ""
        self.running = False
        self.sel = 0
        self.picking = pick_app
        self.pick = next((i for i, a in enumerate(launcher.PANELS)
                          if a["id"] == self.focus), 1)
        if not pick_app:
            self._seed()
        else:
            self._cursor(False)

    # --- палитра ---------------------------------------------------------

    def palette_items(self) -> list[dict]:
        return slash.items_for(self.input, self.commands)

    def slash_open(self) -> bool:
        return self.input.startswith("/")

    # --- геометрия -------------------------------------------------------

    def layout(self) -> dict:
        h, w = self.stdscr.getmaxyx()
        if self.input.startswith("/"):
            n_pal = len(self.palette_items())
            pal = min(PALETTE_ROWS, max(1, n_pal))
        else:
            pal = 0
        return compute_layout(
            h, w, pal,
            picking=self.picking,
            sidebar=self.focus == "lab",
        )

    def _pane_box(self, name: str) -> tuple[int, int, int, int]:
        _ = name
        geo = self.layout()
        return geo["body_y"], 0, geo["body_h"], geo["main_w"]

    def _visible(self) -> tuple[str, ...]:
        return (self.focus,)

    def _color_ok(self, n: int) -> int:
        maxc = getattr(a2c, "_max_colors", 0) or 0
        if maxc >= 256:
            return n
        return 0

    # --- примитивы -------------------------------------------------------

    def _pair(self, fg: int, bg: int) -> int:
        return a2c.pair_fg_bg(self.curses, fg, bg)

    def _role_color(self, role: str) -> int:
        return render.THEME.role(role).color

    def _panel_attr(self, role: str = "text", bold: bool = False) -> int:
        fg = self._role_color(role)
        attr = self._pair(fg, self._color_ok(PANEL_BG))
        if bold:
            attr |= self.curses.A_BOLD
        return attr

    def _fill(self, y: int, x: int, width: int, attr: int) -> None:
        try:
            self.stdscr.addstr(y, x, " " * max(0, width), attr)
        except Exception:
            pass

    def _put(self, y: int, x: int, text: str, attr: int, limit: int) -> None:
        if not text or limit <= 0:
            return
        try:
            self.stdscr.addstr(y, x, text[:limit], attr)
        except Exception:
            pass

    # --- отрисовка -------------------------------------------------------

    def draw(self) -> None:
        try:
            self.stdscr.erase()
            geo = self.layout()
            if self.picking:
                self._draw_picker(geo)
                self._draw_hints(geo["dock_y"] + DOCK_H, geo["w"])
                self.stdscr.refresh()
                return
            vis = self._visible()
            if vis:
                pw = self._pane_box(vis[0])[3]
                render.W = max(24, min(render.W_MAX, pw - 3))
            self._draw_tabs(geo)
            for name in vis:
                y, x, h, w = self._pane_box(name)
                self._draw_pane(name, y, x, h, w)
            if geo["side"]:
                self._draw_sidebar(geo["body_h"], geo["w"] - geo["side"], geo["side"])
            if geo["pal"]:
                self._draw_palette(geo["dock_y"] - geo["pal"] - 1, geo["w"], geo["pal"])
            self._draw_dock(geo["dock_y"], geo["w"])
            self._draw_hints(geo["dock_y"] + DOCK_H, geo["w"])
            self._place_cursor(geo["dock_y"], geo["w"])
            self.stdscr.refresh()
        except Exception:
            pass

    def _draw_picker(self, geo: dict) -> None:
        """Стартовый выбор режима: логотип NEX и три карточки."""
        h, w = geo["h"], geo["w"]
        body_y, body_h = geo["body_y"], geo["body_h"]
        banner = logo.render_logo().split("\n")
        rows = launcher.render_choice(self.pick, w)
        block = len(banner) + 1 + len(rows)
        top = body_y + max(0, (body_h - block) // 4)
        bw = max((a2c.plain_len(l) for l in banner), default=1)
        left = max(0, (w - bw) // 2)
        for i, line in enumerate(banner):
            y = top + i
            if y >= body_y + body_h:
                break
            a2c.addstr(self.curses, self.stdscr, y, left, line, w - left)
        y = top + len(banner) + 1
        for line in rows:
            if y >= body_y + body_h:
                break
            a2c.addstr(self.curses, self.stdscr, y, left, line, w - left)
            y += 1
        _ = h

    def _draw_tabs(self, geo: dict) -> None:
        y = geo["tab_y"]
        w = geo["w"]
        acc = self._role_color("accent")
        dim = self._pair(self._role_color("dim"), -1 if self._color_ok(1) else 0)
        # -1 default bg: pair_fg_bg may not like -1. Use addstr ANSI instead.
        bits = panes.hud_bits(self.session)
        x = 1
        for i, name in enumerate(panes.PANES):
            meta = panes.META[name]
            label = f"{i + 1} {meta['title']}" if name == self.focus else f"{i + 1} {meta['title'].lower()}"
            if name == self.focus:
                text = render.paint("accent", "● " + label)
            else:
                text = render.Style.dim("  " + label)
            a2c.addstr(self.curses, self.stdscr, y, x, text, 16)
            geo["tabs"][name] = (x, 16)
            x += 16
        tail = f"{bits['scenario']}  ·  {bits['profile']}"
        if bits["metrics"]:
            tail += f"  ·  {bits['metrics']}"
        a2c.addstr(self.curses, self.stdscr, y, min(x + 2, w - 4),
                   render.Style.dim(tail), max(0, w - x - 4))
        _ = acc, dim

    def _draw_pane(self, name: str, y: int, x: int, h: int, w: int) -> None:
        if h < 1 or w < 4:
            return
        buf = self.bufs[name]
        inner_h = max(0, h)
        total = len(buf.lines)
        end = max(0, total - buf.scroll)
        start = max(0, end - inner_h)
        for i, line in enumerate(buf.lines[start:end]):
            a2c.addstr(self.curses, self.stdscr, y + i, x, line, w)

    def _draw_sidebar(self, main_h: int, x: int, side: int) -> None:
        bg = self._panel_attr("dim")
        head = self._panel_attr("accent", bold=True)
        for row in range(main_h):
            self._fill(row, x, side, bg)
        self._put(0, x, BAR, self._panel_attr("accent", bold=True), 1)
        self._put(0, x + 2, "КОНТЕКСТ", head, side - 3)
        self._put(1, x + 2, "─" * max(0, side - 5), self._panel_attr("faint"), side - 4)
        rows = context.context_rows(self.session, width=side - 4)
        for i, line in enumerate(rows[: max(0, main_h - 2)]):
            a2c.addstr(self.curses, self.stdscr, i + 2, x + 2, line, side - 3,
                       bg=self._color_ok(PANEL_BG))

    def _draw_palette(self, y: int, w: int, pal: int) -> None:
        items = self.palette_items()
        self.sel = max(0, min(self.sel, len(items) - 1)) if items else 0
        first = max(0, min(self.sel - pal + 1, len(items) - pal)) if len(items) > pal else 0
        kind = items[0].get("kind", "cmd") if items else "cmd"
        head = "команды" if kind != "arg" else "аргумент"
        more = f"  {len(items)}" if items else "  нет совпадений"
        bg = self._color_ok(PANEL_BG)
        dim = self._panel_attr("dim")
        acc = self._panel_attr("accent", bold=True)
        self._fill(y, 0, w - 1, dim)
        self._put(y, 0, BAR, acc, 1)
        self._put(y, 2, head + more, acc, w - 44)
        self._put(y, max(4, w - 40), "↑↓   tab   enter   esc", self._panel_attr("faint"), 38)
        y += 1
        if not items:
            self._fill(y, 0, w - 1, dim)
            self._put(y, 4, "ничего не подходит — поправьте имя",
                      self._panel_attr("warning"), w - 6)
            return
        for row in range(pal):
            it = items[first + row]
            chosen = (first + row) == self.sel
            if chosen:
                attr = self._pair(HEAD_FG, self._role_color("accent")) | self.curses.A_BOLD
            else:
                attr = self._panel_attr("text")
            self._fill(y + row, 0, w - 1, attr)
            mark = "▸" if chosen else " "
            label = ("/" + it["name"]) if it.get("kind") != "arg" else it["name"]
            self._put(y + row, 1, mark, attr, 2)
            self._put(y + row, 3, label, attr, 16)
            self._put(y + row, 20, it.get("arg") or "", attr, 12)
            self._put(y + row, 34, it.get("help") or "", attr, max(0, w - 36))

    def _draw_dock(self, y: int, w: int) -> None:
        base = self._panel_attr("text")
        accent = self._panel_attr("accent", bold=True)
        for row in (0, 1):
            self._fill(y + row, 0, w - 1, base)
            self._put(y + row, 0, BAR, accent, 1)
        self._put(y, 2, "nex ▸ ", accent, 8)
        if self.input:
            self._put(y, 2 + 7, self.input, base | self.curses.A_BOLD, w - 12)
        else:
            self._put(y, 2 + 7, PLACEHOLDERS.get(self.focus, PLACEHOLDERS["lab"]),
                      self._panel_attr("faint"), w - 12)
        if self.running:
            status = "выполняется…"
        else:
            mode = panes.META[self.focus]["title"].lower()
            m = self.session.model()
            status = f"{mode}  ·  {self.session.scenario}  ·  {m.name}"
        self._put(y + 1, 2, status, self._panel_attr("dim"), w - 4)

    def _draw_hints(self, y: int, w: int) -> None:
        h, _ = self.stdscr.getmaxyx()
        if y >= h:
            return
        left = self.note or f"{os.path.basename(os.getcwd())}   {_version()}"
        if self.picking:
            right = "1 2 3 выбрать   ↑↓   enter   q выход"
        elif self.slash_open():
            right = "режим /   ↑↓   tab   enter   esc"
        else:
            right = "F1 F2 F3 вкладка   tab   /clear выбор   ↑↓"
        a2c.addstr(self.curses, self.stdscr, y, 2,
                   render.Style.dim(left), max(0, w - 4))
        x = max(0, w - len(right) - 2)
        a2c.addstr(self.curses, self.stdscr, y, x, render.Style.dim(right), w - x - 1)

    def _place_cursor(self, y: int, w: int) -> None:
        col = min(w - 2, 2 + 7 + len(self.input))
        try:
            self.stdscr.move(y, col)
        except Exception:
            pass

    # --- содержимое панелей ----------------------------------------------

    def _seed(self) -> None:
        self._refresh_work()
        _, _, _, lw = self._safe_box("lab")
        self.bufs["lab"].load(panes.render_lab_seed(self.session, width=max(16, lw - 3)))
        _, _, _, mw = self._safe_box("mind")
        self.bufs["mind"].load(panes.render_mind_seed(width=max(16, mw - 3)))

    def _safe_box(self, name: str) -> tuple[int, int, int, int]:
        try:
            return self._pane_box(name)
        except Exception:
            return 1, 0, 10, 36

    def _refresh_work(self) -> None:
        _, _, _, ww = self._safe_box("work")
        self.bufs["work"].load(panes.render_work(self.session, width=max(16, ww - 3)))

    def _reset(self) -> None:
        self.input = ""
        self.sel = 0
        self.hist_pos = None
        self.note = ""
        self._seed()

    def _choose(self, index: int) -> None:
        index = max(0, min(len(launcher.PANELS) - 1, index))
        app = launcher.PANELS[index]
        self.pick = index
        self._set_focus(app["id"])
        self.picking = False
        self._cursor(True)
        self._seed()

    def _to_picker(self) -> None:
        ids = [a["id"] for a in launcher.PANELS]
        cur = getattr(self.session, "focus", "lab")
        self.pick = ids.index(cur) if cur in ids else 1
        for buf in self.bufs.values():
            buf.clear()
        self.input = ""
        self.sel = 0
        self.hist_pos = None
        self.note = ""
        self.picking = True
        self._cursor(False)

    # --- вывод -----------------------------------------------------------

    def run_command(self, line: str) -> None:
        dest = self.classify(self.session, line)
        if dest not in self.bufs:
            dest = "lab"
        self.focus = dest
        self.session.focus = dest
        self.running = True
        self.bufs[dest].scroll = 0
        self.draw()
        role = panes.META[dest]["role"]
        self.bufs[dest].write(panes.stamp(line, role) + "\n")
        if dest != "work":
            # дашборд ядра пересоберём после команды — граф мог смениться
            pass
        sink = _Sink(self.bufs[dest], self._live_redraw)
        old_w = render.W
        _, _, _, pw = self._pane_box(dest) if dest in self._visible() else self._safe_box(dest)
        render.W = max(24, min(render.W_MAX, pw - 3))
        try:
            with contextlib.redirect_stdout(sink):
                self.execute(line)
        except KeyboardInterrupt:
            self.bufs[dest].write(render.paint("warning", "  ^C команда прервана") + "\n")
        except SystemExit as e:
            self.bufs[dest].write(render.paint("error", f"  {e}") + "\n")
        except Exception as e:
            self.bufs[dest].write(render.paint("error", f"  ошибка команды: {e}") + "\n")
        finally:
            render.W = old_w
            self.bufs[dest].flush_partial()
            self.running = False
            want = getattr(self.session, "focus", dest)
            if want in panes.PANES:
                self.focus = want

    def _live_redraw(self) -> None:
        self.bufs[self.focus].flush_partial()
        self.draw()

    # --- ввод ------------------------------------------------------------

    def _do_complete(self) -> None:
        items = self.palette_items()
        if items:
            self.input = slash.apply_tab(self.input, items[self.sel])
            if not self.input.endswith(" ") and items[self.sel].get("kind") != "arg":
                if items[self.sel].get("arg"):
                    self.input += " "
            self.sel = 0
            return
        if not self.input.startswith("/"):
            self.input = "/"
            self.sel = 0
            return
        cands = self.complete(self.input)
        if len(cands) == 1:
            self.input = cands[0]
        elif cands:
            common = _common_prefix(cands)
            if len(common) > len(self.input):
                self.input = common
            self.note = "  ".join(c.split()[-1] for c in cands[:8])

    def _scroll(self, lines: int) -> None:
        buf = self.bufs[self.focus]
        _, _, h, _ = self._pane_box(self.focus)
        inner = max(1, h)
        top = max(0, len(buf.lines) - inner)
        buf.scroll = max(0, min(top, buf.scroll + lines))

    def _cycle_focus(self, delta: int) -> None:
        i = panes.PANES.index(self.focus)
        self.focus = panes.PANES[(i + delta) % len(panes.PANES)]
        self.session.focus = self.focus

    def _set_focus(self, name: str) -> None:
        if name in panes.PANES:
            self.focus = name
            self.session.focus = name

    def _on_mouse(self) -> None:
        cs = self.curses
        try:
            _, mx, my, _, state = cs.getmouse()
        except Exception:
            return
        geo = self.layout()
        step = max(1, geo["body_h"] // 4)
        up = getattr(cs, "BUTTON4_PRESSED", 0)
        down = getattr(cs, "BUTTON5_PRESSED", 0) or (1 << 21)
        left = getattr(cs, "BUTTON1_PRESSED", 0) | getattr(cs, "BUTTON1_CLICKED", 0)
        if state & up:
            self._scroll(step)
        elif state & down:
            self._scroll(-step)
        elif state & left:
            if my == geo.get("tab_y"):
                for name, (tx, tw) in geo["tabs"].items():
                    if tx <= mx < tx + tw:
                        self._set_focus(name)
                        return

    def _cursor(self, visible: bool) -> None:
        try:
            self.curses.curs_set(1 if visible else 0)
        except Exception:
            pass

    def _history_step(self, delta: int) -> None:
        if not self.history:
            return
        if self.hist_pos is None:
            self.hist_pos = len(self.history)
        self.hist_pos = max(0, min(len(self.history), self.hist_pos + delta))
        self.input = "" if self.hist_pos >= len(self.history) else self.history[self.hist_pos]

    def loop(self) -> int:
        cs = self.curses
        self.draw()
        key_btab = getattr(cs, "KEY_BTAB", 353)
        fkeys = {
            getattr(cs, "KEY_F1", -1): "work",
            getattr(cs, "KEY_F2", -1): "lab",
            getattr(cs, "KEY_F3", -1): "mind",
        }
        while True:
            try:
                ch = self.stdscr.get_wch()
            except KeyboardInterrupt:
                self.input = ""
                self.note = "^C — для выхода /exit"
                self.draw()
                continue
            except Exception:
                continue

            items = self.palette_items()
            geo = self.layout()

            if self.picking:
                if ch in ("1", "2", "3"):
                    self._choose(int(ch) - 1)
                elif ch == cs.KEY_UP:
                    self.pick = (self.pick - 1) % len(launcher.PANELS)
                elif ch == cs.KEY_DOWN:
                    self.pick = (self.pick + 1) % len(launcher.PANELS)
                elif ch in ("\n", "\r", cs.KEY_ENTER):
                    self._choose(self.pick)
                elif ch == "\x1b":
                    self._choose(self.pick)
                elif ch in ("q", "\x03", "\x04"):
                    return 0
                self.draw()
                continue

            if ch in fkeys:
                self._set_focus(fkeys[ch])
                self.draw()
                continue
            # Цифры принадлежат вводу: `2+2` в ядре начинается с двойки.
            # Панели переключаются F1–F3 и Tab, режим меняется через /clear.
            if ch == "\t":
                if self.input.startswith("/"):
                    self._do_complete()
                else:
                    self._cycle_focus(1)
                self.draw()
                continue
            if ch == key_btab:
                self._cycle_focus(-1)
                self.draw()
                continue

            if ch in ("\n", "\r", cs.KEY_ENTER):
                picked = items[self.sel] if items else None
                line = slash.apply_enter(self.input, picked) if self.input.startswith("/") \
                    else self.input.strip()
                self.input = ""
                self.sel = 0
                self.hist_pos = None
                self.note = ""
                if not line:
                    self.draw()
                    continue
                self.history.append(line)
                if line.lower() in ("/exit", "exit", "/quit", "quit"):
                    return 0
                if line.lower() in ("/clear", "clear", "/cls"):
                    self._to_picker()
                    self.draw()
                    continue
                self.run_command(line)
                self.draw()
            elif ch == "\x10":
                if not self.input.startswith("/"):
                    self.input = "/"
                    self.sel = 0
                self.draw()
            elif ch == "\x1b":
                if self.input.startswith("/"):
                    self.input = ""
                    self.sel = 0
                    self.note = ""
                self.draw()
            elif ch in ("\x7f", "\b", cs.KEY_BACKSPACE):
                self.input = self.input[:-1]
                self.sel = 0
                self.draw()
            elif ch == "\x04":
                return 0
            elif ch == "\x03":
                self.input = ""
                self.note = "^C — для выхода /exit"
                self.draw()
            elif ch == "\x0c":
                self.bufs[self.focus].clear()
                if self.focus == "work":
                    self._refresh_work()
                self.draw()
            elif ch == cs.KEY_UP:
                if items:
                    self.sel = max(0, self.sel - 1)
                else:
                    self._history_step(-1)
                self.draw()
            elif ch == cs.KEY_DOWN:
                if items:
                    self.sel = min(len(items) - 1, self.sel + 1)
                else:
                    self._history_step(1)
                self.draw()
            elif ch == cs.KEY_PPAGE:
                self._scroll(max(1, geo["body_h"] // 2))
                self.draw()
            elif ch == cs.KEY_NPAGE:
                self._scroll(-max(1, geo["body_h"] // 2))
                self.draw()
            elif ch == cs.KEY_HOME:
                buf = self.bufs[self.focus]
                _, _, ph, _ = self._pane_box(self.focus)
                buf.scroll = max(0, len(buf.lines) - max(1, ph))
                self.draw()
            elif ch == cs.KEY_END:
                self.bufs[self.focus].scroll = 0
                self.draw()
            elif ch == cs.KEY_RESIZE:
                self.draw()
            elif ch == cs.KEY_MOUSE:
                self._on_mouse()
                self.draw()
            elif isinstance(ch, str) and ch.isprintable():
                self.input += ch
                self.sel = 0
                self.note = ""
                self.draw()


def _version() -> str:
    try:
        from .. import VERSION_LABEL

        return VERSION_LABEL
    except Exception:
        return ""


def _common_prefix(items: list[str]) -> str:
    if not items:
        return ""
    first, last = min(items), max(items)
    i = 0
    while i < len(first) and i < len(last) and first[i] == last[i]:
        i += 1
    return first[:i]


def run(session, execute, commands, complete, intro_lines=None,
        pick_app: bool = True, classify=None) -> int:
    """Запустить workstation. Без --mode сначала экран выбора режима."""
    import curses

    _ = intro_lines
    if classify is None:
        classify = lambda _s, _line: "lab"

    def _main(stdscr):
        curses.curs_set(0 if pick_app else 1)
        stdscr.keypad(True)
        try:
            curses.mousemask(curses.ALL_MOUSE_EVENTS | curses.REPORT_MOUSE_POSITION)
            print("\033[?1000h\033[?1006h", end="", flush=True)
        except Exception:
            pass
        a2c.init(curses)
        tui = Tui(curses, stdscr, session, execute, commands, complete, classify,
                  pick_app=pick_app)
        return tui.loop()

    return curses.wrapper(_main)
