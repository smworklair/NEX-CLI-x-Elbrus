"""Shared foundation for workspace screens.

Each mode is its own workspace with a dedicated layout. They share only what is
needed to feel like one tool: the top mode bar, the bottom input dock, a
uniform way to run commands, and `/clear` to return to the mode picker.

There are intentionally no global hotkeys to switch modes: the full keyboard
belongs to the input line and editor.
"""

from __future__ import annotations

from rich.text import Text
from textual import work
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import Screen

from .. import palette
from ..widgets import (Console, ConsoleJournal, HintBar, Panel, PanelChat,
                        PanelPrompt, PromptBar, Tool, TopBar)


class ModeScreen(Screen):
    """Mode scaffold: header, mode-specific body, and input dock."""

    mode = "lab"
    mode_title = ""
    mode_subtitle = ""
    placeholder = ""
    hint = ""

    # Collapsible panels: the sidebar takes a third of width and the tips bar
    # is only needed while learning commands. Both toggle via keyboard.
    SIDE_ID = ""
    TIPS_ID = ""

    BINDINGS = [
        # Esc always steps back one level. priority=True prevents focused child
        # widgets from intercepting Esc inconsistently; see action_back.
        Binding("escape", "back", "back", priority=True),
        # Tab toggles the AI helper on a maximized panel (priority=True so it
        # beats input completion when maximized; outside maximize it still
        # completes commands — see action_ai_or_complete).
        Binding("tab", "ai_or_complete", "AI helper", priority=True),
        ("ctrl+b", "toggle_side", "sidebar"),
        ("ctrl+t", "toggle_tips", "tips bar"),
        ("ctrl+o", "to_picker", "mode picker"),
        ("ctrl+q", "quit_app", "quit"),
    ]

    def __init__(self, **kw) -> None:
        super().__init__(**kw)
        self.busy = False
        self.side_shown = True
        self.tips_shown = True

    # --- layout -----------------------------------------------------------

    def compose(self):
        yield TopBar(self.mode, self.mode_title, self.mode_subtitle, id="topbar")
        yield from self.compose_body()
        with Vertical(id="dock"):
            yield PromptBar(self.mode, self.placeholder,
                            list(self.app.commands) + self.extra_commands(),
                            hint=self.hint, id="prompt")
            yield HintBar(id="hints")

    def extra_commands(self) -> list[dict]:
        """Screen-specific commands added to the `/` command palette."""
        return []

    def compose_body(self):
        """Mode layout. Overridden by each screen."""
        yield Vertical(id="body")

    #: Widgets kept visible when a panel is maximized. Including `#dock` keeps
    #: the prompt and hint bar visible in full-screen panel view.
    ALLOW_IN_MAXIMIZED_VIEW = ("PanelChat, PanelPrompt, PromptBar, HintBar, "
                               "Footer, #dock, TopBar")

    #: Disable Textual's built-in Esc-to-minimize so `action_back` handles the
    #: full cascade in order and always emits `Panel.Collapsed`.
    ESCAPE_TO_MINIMIZE = False

    _chat_panel = None
    _chat_facts: list[str] = []
    _chat_offer = None
    _prompt_panel = None
    _expanded_panel = None

    def on_mount(self) -> None:
        self.app.set_mode_theme(self.mode)
        self._apply_width(self.size.width or 120)
        self.query_one("#prompt", PromptBar).focus_input()
        self.refresh_hints()
        self.refresh_context()
        self.on_ready()

    def on_ready(self) -> None:
        """Initial panel population. Overridden by each screen."""

    # --- window sizing ----------------------------------------------------
    #
    # Sidebars stay visible while the main grid/tape has enough room; on narrow
    # terminals auxiliary hint strips drop first to preserve the workspace.

    NARROW = 124
    TIGHT = 100

    # Height breakpoints so lower panels (e.g., MACHINE in LAB) stay above the
    # fold on shorter terminals.
    LOW = 34
    VERY_LOW = 28
    ROOMY = 50

    def on_resize(self, event) -> None:
        self._apply_width(event.size.width)
        self._apply_height(event.size.height)

    def _apply_width(self, width: int) -> None:
        self.set_class(width < self.NARROW, "narrow")
        self.set_class(width < self.TIGHT, "tight")

    def _apply_height(self, height: int) -> None:
        self.set_class(height < self.LOW, "low")
        self.set_class(height < self.VERY_LOW, "very-low")
        self.set_class(height >= self.ROOMY, "roomy")

    # --- header & hints ---------------------------------------------------

    def context_bits(self) -> str:
        s = self.app.session
        model = s.model()
        bits = [f"block {s.scenario}", f"{len(s.dag_obj)} ops", model.name]
        cached = s.peek()
        if cached is not None:
            base, orc, _ = cached
            b, o = base.schedule.makespan, orc.schedule.makespan
            bits.append(f"{b}→{o}" if b != o else f"{b} cycles")
        return "   ·   ".join(bits)

    def refresh_context(self) -> None:
        try:
            self.query_one("#topbar", TopBar).context = self.context_bits()
        except Exception:
            pass

    def hint_pairs(self) -> list[tuple[str, str]]:
        return [("/", "commands"), ("Esc", "back"), ("/exit", "quit")]

    def toggle_hints(self) -> list[tuple[str, str]]:
        """Shared hints for toggleable panels across all modes."""
        out = []
        if self.screen is self and self.screen.maximized is not None:
            out.append(("Esc", "restore panel"))
        else:
            out.append(("2xclick", "maximize panel"))
        if (self.screen is self and self.maximized is not None
                and self._expanded_panel is not None):
            out.append(("Tab", "AI helper"
                        if not list(self.query(PanelPrompt)) else "close"))
        if self.SIDE_ID:
            out.append(("^B", "sidebar" if self.side_shown else "sidebar ←"))
        if self.TIPS_ID:
            out.append(("^T", "tips" if self.tips_shown else "tips ←"))
        return out

    def refresh_hints(self) -> None:
        try:
            self.query_one("#hints", HintBar).set_hint(
                self.hint_pairs() + self.toggle_hints())
        except Exception:
            pass

    # --- input ------------------------------------------------------------

    def on_prompt_bar_submitted(self, event: PromptBar.Submitted) -> None:
        event.stop()
        self.submit_line(event.value)

    def on_console_journal_run_requested(self, event) -> None:
        """Handle commands typed directly inside the maximized output journal."""
        event.stop()
        self.submit_line(event.line)

    def submit_line(self, raw: str) -> None:
        line = raw.strip()
        low = line.lower().lstrip("/")
        if low in ("exit", "quit"):
            self.app.exit(0)
            return
        if low in ("clear", "cls"):
            self.app.to_picker()
            return
        if low.split(" ")[0] == "mode":
            # Modes are separate workspaces; `/mode` stays in core for line
            # mode and here simply points the user to `/clear`.
            if self.console is not None:
                self.console.note(
                    "  switch modes via /clear — opens the mode picker",
                    "warning")
            return
        self.handle_line(line)

    def handle_line(self, line: str) -> None:
        """Handle a submitted input line. Overridden by each screen."""
        self.run_core(line)

    def on_chip_picked(self, event) -> None:
        """Clicking a suggestion chip populates and runs it immediately."""
        event.stop()
        bar = self.query_one("#prompt", PromptBar)
        bar.focus_input()
        bar.history.append(event.value)
        self.handle_line(event.value)

    def on_nex_input_pasted(self, event) -> None:
        """Route multi-line pastes into the CODE buffer from any mode."""
        event.stop()
        self.app.session.code_text = event.text
        lines = [l for l in event.text.splitlines() if l.strip()]
        con = self.console
        if con is not None:
            con.note(f"  pasted {len(lines)} "
                     f"lines → CODE buffer   ·   CODE mode (key 1) — "
                     "editor, /code run — run", "warning")

    # --- maximized panel tools --------------------------------------------

    def on_tool_picked(self, event: Tool.Picked) -> None:
        """Clicking a panel toolbar action executes it immediately."""
        event.stop()
        self.panel_tool(event.tool)

    def panel_tool(self, tool: str) -> None:
        """Handle a panel toolbar action. Overridden by each screen.

        Base implementation handles journal bridge actions (`@lab`/`@agent`/
        `@work`/`@code`), `@restore`, and slash commands.
        """
        if tool in ("@lab", "@agent", "@work", "@code"):
            self._bridge_run(tool[1:])
        elif tool == "@restore":
            self._restore_run()
        elif tool.startswith("/"):
            self.handle_line(tool)
        else:
            self.app.bell()

    # --- bridge: journal run -> another mode ------------------------------

    def _bridge_run(self, dest: str) -> None:
        """Send the selected journal run to another mode."""
        con = self.console
        if con is None or not con.runs:
            self.app.bell()
            return
        rec = con.runs[min(self._bridge_index(con), len(con.runs) - 1)]
        if dest == "lab":
            dag = rec.get("dag")
            if dag is None:
                self.app.bell()
                return
            self.app.session.set_dag(dag, rec.get("scenario") or "run")
            self.app.open_mode("lab")
        elif dest == "agent":
            scenario = rec.get("scenario") or "—"
            self.app.session.pending_question = (
                f"run \"{rec['cmd']}\" on block {scenario} — what did it "
                "show and where are cycles being lost?")
            self.app.open_mode("mind")
        elif dest == "work":
            self.app.session.pending_note = (
                f"from journal: run \"{rec['cmd']}\" on block "
                f"{rec.get('scenario') or '—'}")
            self.app.open_mode("work")
        elif dest == "code":
            src = rec.get("code")
            if src:
                # Buffer runs carry their original source; restore it to CODE.
                self.app.session.code_text = src
                self.app.session.pending_note = (
                    f"from journal: source for \"{rec['cmd']}\" loaded into buffer")
            else:
                self.app.session.pending_note = (
                    f"from journal: run \"{rec['cmd']}\" on block "
                    f"{rec.get('scenario') or '—'} — no source recorded, "
                    "buffer unchanged")
            self.app.open_mode("code")

    def _restore_run(self) -> None:
        """Restore the selected journal run's session state in place."""
        con = self.console
        if con is None or not con.runs:
            self.app.bell()
            return
        pos = min(self._bridge_index(con), len(con.runs) - 1)
        rec = con.runs[pos]
        dag = rec.get("dag")
        code = rec.get("code")
        snap = rec.get("ws")
        if dag is None and code is None and snap is None:
            self.app.bell()
            return
        if snap is not None:
            # Checkout the full CORE interpreter state (names, memory, graph).
            self.app.session.workspace().restore(snap)
        if dag is not None:
            self.app.session.set_dag(dag, rec.get("scenario") or "run")
        if code:
            self.app.session.code_text = code
        con.note(f"  restored state #{pos + 1}: "
                 f"{rec.get('scenario') or '—'}"
                 + ("  ·  CORE machine restored" if snap is not None else "")
                 + (f"  ·  source in buffer" if code else ""),
                 "success")
        self.refresh_context()
        self.after_command()

    def _bridge_index(self, con) -> int:
        """Return the selected run index in the journal, or the latest run."""
        try:
            journal = self.query_one(ConsoleJournal)
            if 0 <= journal.pos < len(con.runs):
                return journal.pos
        except Exception:
            pass
        return len(con.runs) - 1

    # --- Esc: one step back -----------------------------------------------

    def action_back(self) -> None:
        """Step out one UI level on Esc, all the way back to the mode picker."""
        bar = None
        try:
            bar = self.query_one("#prompt", PromptBar)
        except Exception:
            pass
        # 1. Close the command palette overlay if open.
        if bar is not None and bar.palette_widget.display:
            bar.set_value("")
            return
        # 2. Close the AI helper bar on a maximized panel.
        if list(self.query(PanelPrompt)):
            self.close_panel_prompt()
            self.refresh_hints()
            return
        # 3. Restore a maximized panel back to normal layout.
        if self.maximized is not None:
            panel = self.maximized
            self.minimize()
            panel.post_message(Panel.Collapsed())
            return
        # 4. Exit the mode screen back to caller or picker.
        self.app.back_out()

    def action_ai_or_complete(self) -> None:
        """Tab: toggle AI helper when a panel is maximized, else complete input."""
        if self.maximized is not None and self._expanded_panel is not None:
            self.action_toggle_panel_prompt()
            return
        try:
            self.query_one("#prompt", PromptBar).tab()
        except Exception:
            pass

    # --- core command execution -------------------------------------------

    @property
    def console(self) -> Console | None:
        try:
            return self.query_one("#console", Console)
        except Exception:
            return None

    def run_core(self, line: str) -> None:
        """Run a core command and display its output in the screen console."""
        con = self.console
        if con is not None:
            con.echo(line, self.mode)
        self.set_busy(True)
        self._core_worker(line)

    @work(thread=True, exclusive=True, group="core")
    def _core_worker(self, line: str) -> None:
        from .. import bridge

        con = self.console
        width = con.size.width - 2 if con is not None and con.size.width else 96

        # Stream scheduler events live to the UI instead of buffering them
        # until the command finishes.
        session = self.app.session
        session.event_sink = bridge.EventPump(
            self.app, self.on_scheduler_text, self.on_scheduler_event)
        try:
            out, err = bridge.run_command(self.app.execute, line, width)
        finally:
            session.event_sink = None
        self.app.call_from_thread(self._core_done, out, err)

    # --- scheduler events -------------------------------------------------
    #
    # Delivered on the main UI thread. Default behavior logs text to EVENTS;
    # screens with a live grid override these to update cells directly.

    def on_scheduler_text(self, text: str) -> None:
        """Append live scheduler text (model tokens, notes) to EVENTS."""
        clean = "  " + text.replace("[end of text]", "").rstrip()
        self.app.session.journal_events.append(
            Text(clean, style=palette.role_hex("dim")))
        try:
            journal = self.query_one("#journal", ConsoleJournal)
        except Exception:
            return
        journal.append_event(Text(clean, style=palette.role_hex("dim")))

    def on_scheduler_event(self, ev) -> None:
        """Non-text scheduler event: placement, repair, verdict, or failure."""

    def _core_done(self, out: str, err: str) -> None:
        con = self.console
        if con is not None:
            if out.strip():
                con.ansi(out.rstrip("\n"))
            if err:
                con.note("  " + err, "error")
            con.write("")
            # Attach bridge metadata to the latest run so it can be sent to
            # LAB or AGENT from the journal.
            if con.runs:
                rec = con.runs[-1]
                rec["scenario"] = self.app.session.scenario
                rec["dag"] = self.app.session.dag_obj
                rec["profile"] = self.app.session.profile
        self.set_busy(False)
        self.app.reload_palette()   # command may have switched theme
        self.refresh_context()
        self.after_command()
        self._refresh_journal()

    def _refresh_journal(self) -> None:
        """Reload the visible journal from in-memory session runs."""
        try:
            journal = self.query_one("#journal", ConsoleJournal)
        except Exception:
            return
        if not journal.display:
            return
        journal.load(self.app.session.journal_runs, self.mode,
                     list(self.app.commands) + self.extra_commands(),
                     self.app.session.journal_events)

    # --- panel AI helper --------------------------------------------------

    def panel_facts(self, topic: str) -> list[str]:
        """Facts about the maximized panel for the AI helper. Overridden per screen."""
        return []

    def panel_chips(self, topic: str) -> list[str]:
        """Suggested questions for the panel's floating prompt bar."""
        return []

    def on_panel_expanded(self, event) -> None:
        event.stop()
        panel = event.panel
        # Remember the maximized panel so Tab can open the AI helper on demand.
        self._expanded_panel = panel if getattr(panel, "topic", "") else None
        self.refresh_hints()

    def on_panel_collapsed(self, event) -> None:
        event.stop()
        self._expanded_panel = None
        self.close_panel_prompt()
        self.close_panel_chat()
        self.refresh_hints()

    # --- floating question bar --------------------------------------------

    def action_toggle_panel_prompt(self) -> None:
        """Toggle the AI helper bar on a maximized panel (Tab)."""
        if list(self.query(PanelPrompt)):
            self.close_panel_prompt()
            self.refresh_hints()
            return
        panel = getattr(self, "_expanded_panel", None)
        if panel is not None:
            self.open_panel_prompt(panel)
            self.refresh_hints()

    def open_panel_prompt(self, panel) -> None:
        """Open the bottom question bar for a maximized panel."""
        topic = getattr(panel, "topic", "")
        facts = self.panel_facts(topic)
        chips = self.panel_chips(topic)
        if not facts and not chips:
            return
        # Textual's remove() is deferred; wait a refresh before remounting the
        # same widget id to avoid duplicate-id collisions.
        for old in self.query(PanelPrompt):
            old.remove()
            self._prompt_panel = None
            return self.call_after_refresh(self.open_panel_prompt, panel)
        full = getattr(panel, "_title", "") or topic
        title = full.split("   ")[0].strip() or topic
        prompt = PanelPrompt(title=title, chips=chips, facts=facts,
                             mode=self.mode, id="panel-prompt")
        self.mount(prompt)
        self._prompt_panel = panel

    def close_panel_prompt(self) -> None:
        for p in self.query(PanelPrompt):
            p.remove()
        self._prompt_panel = None

    def on_panel_prompt_closed(self, event) -> None:
        event.stop()
        self.close_panel_prompt()
        self.refresh_hints()

    def on_panel_prompt_asked(self, event) -> None:
        event.stop()
        prompts = list(self.query(PanelPrompt))
        if not prompts:
            return
        pp = prompts[0]
        pp.echo(event.question)
        pp.start_answer()
        self._panel_prompt_worker(event.question)

    @work(thread=True, exclusive=True, group="panel-prompt")
    def _panel_prompt_worker(self, question: str) -> None:
        """Run the full session Agent with panel facts appended as context."""
        import time

        panel = getattr(self, "_prompt_panel", None)
        full = getattr(panel, "_title", "") if panel is not None else ""
        title = full.split("   ")[0].strip() or "panel"
        prompts = list(self.query(PanelPrompt))
        facts = list(prompts[0].facts) if prompts else []
        agent = self.app.session.agent()
        t0 = time.monotonic()
        acted = False
        try:
            for kind, value in agent.ask_stream(question, panel=(title, facts)):
                if kind == "action":
                    acted = True
                    self.app.call_from_thread(self._pp_action, value)
                elif kind == "text":
                    self.app.call_from_thread(self._pp_piece, value)
                elif kind == "error":
                    self.app.call_from_thread(self._pp_fail, value)
        except Exception as e:
            self.app.call_from_thread(self._pp_fail, str(e))
        self.app.call_from_thread(self._pp_done, time.monotonic() - t0, acted)

    def _pp_action(self, note: str) -> None:
        for p in self.query(PanelPrompt):
            p.action(note)
            return

    def _pp_piece(self, piece: str) -> None:
        for p in self.query(PanelPrompt):
            p.first_piece()
            p.append(piece)
            return

    def _pp_done(self, seconds: float, acted: bool = False) -> None:
        for p in self.query(PanelPrompt):
            p.finish(seconds)
            break
        if acted:
            # Call after_command() rather than redraw(): an agent action may
            # have switched the scenario/DAG, so cached schedules must be
            # recomputed before repainting.
            self.refresh_context()
            self.after_command()

    def _pp_fail(self, message: str) -> None:
        for p in self.query(PanelPrompt):
            p.note("failed: " + message[:160], "error")
            return

    def open_panel_chat(self, panel) -> None:
        facts = self.panel_facts(getattr(panel, "topic", ""))
        if not facts:
            return
        self.close_panel_chat()
        full = getattr(panel, "_title", "") or panel.topic
        title = full.split("   ")[0].strip() or panel.topic
        chat = PanelChat(title=title, facts=facts, id="panel-chat")
        chat.add_class("left" if getattr(panel, "has_own_input", False)
                       else "right")
        self.mount(chat)
        panel.add_class("with-chat")
        self._chat_panel = panel
        self._chat_facts = facts
        self.refresh_hints()

    def close_panel_chat(self) -> None:
        for chat in self.query(PanelChat):
            chat.remove()
        panel = getattr(self, "_chat_panel", None)
        if panel is not None:
            panel.remove_class("with-chat")
        self._chat_panel = None
        self._chat_facts = []
        self._chat_offer = None

    def on_panel_chat_asked(self, event) -> None:
        event.stop()
        chats = list(self.query(PanelChat))
        if not chats:
            return
        chat = chats[0]
        chat.echo(event.question)
        chat.start_answer()
        self._panel_chat_worker(event.question)

    @work(thread=True, exclusive=True, group="panel-chat")
    def _panel_chat_worker(self, question: str) -> None:
        from ...agent import context, llm

        panel = self._chat_panel
        full = getattr(panel, "_title", "") if panel is not None else ""
        title = full.split("   ")[0].strip() or "panel"
        system = context.panel_prompt(title, list(self._chat_facts))
        import time

        t0 = time.monotonic()
        try:
            for piece in llm.stream(system, question, None):
                self.app.call_from_thread(self._panel_chat_piece, piece)
        except Exception as e:
            self.app.call_from_thread(self._panel_chat_fail, str(e))
        self.app.call_from_thread(self._panel_chat_done, time.monotonic() - t0)

    def _panel_chat_piece(self, piece: str) -> None:
        chats = list(self.query(PanelChat))
        if not chats:
            return
        chats[0].first_piece()
        chats[0].append(piece)

    def _panel_chat_done(self, seconds: float) -> None:
        chats = list(self.query(PanelChat))
        if chats:
            chats[0].finish(seconds)

    def _panel_chat_fail(self, message: str) -> None:
        chats = list(self.query(PanelChat))
        if chats:
            chats[0].note("failed: " + message[:160], "error")

    def after_command(self) -> None:
        """Refresh panels after a command completes. Overridden per screen."""

    # --- repaint (theme switch) -------------------------------------------

    def repaint(self) -> None:
        """Repaint theme-dependent elements without rebuilding widgets."""
        self.query_one("#topbar", TopBar).refresh_bar()
        self.query_one("#prompt", PromptBar).repaint()
        self.refresh_hints()
        self.refresh_context()
        self.redraw()

    def redraw(self) -> None:
        """Redraw screen panel contents. Overridden per screen."""

    def set_busy(self, busy: bool) -> None:
        self.busy = busy
        try:
            bar = self.query_one("#prompt", PromptBar)
        except Exception:
            return
        if busy:
            bar.set_side(Text("running…", style=palette.role_hex("warning")))
        else:
            bar.set_side("")

    # --- actions ----------------------------------------------------------

    def _toggle(self, selector: str, shown: bool) -> bool:
        if not selector:
            return shown
        try:
            self.query_one(selector).display = not shown
        except Exception:
            return shown
        self.refresh_hints()
        return not shown

    def action_toggle_side(self) -> None:
        self.side_shown = self._toggle(self.SIDE_ID, self.side_shown)

    def action_toggle_tips(self) -> None:
        self.tips_shown = self._toggle(self.TIPS_ID, self.tips_shown)

    def action_to_picker(self) -> None:
        self.app.to_picker()

    def action_quit_app(self) -> None:
        self.app.exit(0)
