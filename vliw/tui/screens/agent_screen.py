"""AGENT — dialog with visible grounding.

Instead of mixing chat prose into the same log as command reports, this screen
separates the answer from its evidence: the streaming conversation sits on the
left, while the right column shows the exact numbers passed to the agent and
the trace of actions it ran (loading files, switching blocks, scheduling) so
every claim can be verified directly.
"""

from __future__ import annotations

from rich.text import Text
from textual.binding import Binding
from textual.containers import Horizontal, ItemGrid, Vertical, VerticalScroll
from textual.widgets import Input, Static

from .. import palette
from ..widgets import (Chip, Panel, PromptBar, Tool, plural)
from .base import ModeScreen

QUESTIONS = [
    "why is this block slow?",
    "where are cycles lost and what should I change?",
    "compare baseline with exact search",
    "what is the exclusive ,5 port?",
    "load examples/probe.s and analyze it",
    "what is the lower bound for this block?",
]


def _wrap(text: str, width: int, indent: int) -> str:
    """Wrap text with a hanging indent for narrow sidebar columns."""
    import textwrap

    pad = " " * indent
    return ("\n" + pad).join(textwrap.wrap(text, max(12, width - indent)) or [""])


class AgentScreen(ModeScreen):
    mode = "mind"
    mode_title = "AGENT"
    mode_subtitle = "dialog"
    placeholder = "ask in plain language"
    key_placeholder = "paste API key and press Enter…"
    hint = "/clear — clear   ·   paste key here"
    SIDE_ID = "#mind-right"
    TIPS_ID = "#p-questions"

    def __init__(self, **kw) -> None:
        super().__init__(**kw)
        self._answer: Static | None = None
        self._buf = ""
        self._actions: list[str] = []
        self._model: tuple[bool | None, str] = (None, "checking…")
        self._wide = ""
        #: Waiting for a pasted API key instead of a question (see _maybe_ask_key).
        self._awaiting_key = False
        #: Show the key prompt at most once per screen lifetime.
        self._key_offered = False
        # Question history with timing and action count (shown on left when
        # DIALOG is maximized; clicking repeats the question).
        self._asked: list[dict] = []
        self._last_q = ""
        self._t0 = 0.0
        #: Number of shared `session.dialog` entries already mounted.
        self._shown = 0
        #: Session-only model catalog state: selected provider, filter, note.
        self._model_prov: str | None = None
        self._model_filter = ""
        self._model_note = ""
        #: HQ missions on verified connections (session memory only):
        #: [{id, conn, area, script, question, status, answer}].
        self._hq_tasks: list[dict] = []
        self._hq_seq = 0
        self._hq_conn = 0
        self._hq_area = "doctor"
        #: Suppress programmatic writes to the search input.
        self._mute_filter = False

    # --- layout -----------------------------------------------------------

    def compose_body(self):
        with Horizontal(id="mind-body"):
            with Vertical(id="mind-left"):
                with Panel(title="DIALOG", id="p-chat", topic="chat"):
                    with Horizontal(id="chat-body"):
                        yield Vertical(VerticalScroll(id="chat-hist"),
                                       id="chat-hist-col")
                        yield VerticalScroll(id="chat")
                yield Panel(ItemGrid(id="question-chips", min_column_width=34),
                            title="SUGGESTED QUESTIONS", id="p-questions")
            with Vertical(id="mind-right"):
                yield Panel(Static(id="hq-mini"),
                            Input(placeholder="mission for HQ… (Enter to send)",
                                  id="hq-task"),
                            VerticalScroll(id="hq-wide"),
                            title="HQ", id="p-hq", topic="hq")
                with Panel(title="CONNECTION", id="p-model", topic="model"):
                    yield Static(id="model")
                    with Vertical(id="model-mini"):
                        yield ItemGrid(id="model-provs-mini",
                                       min_column_width=12)
                        with Horizontal(id="model-mini-row"):
                            yield Input(
                                placeholder="API key… (Enter to connect)",
                                password=True, id="model-key-mini")
                            yield Tool("connect", "mconnect-mini",
                                       id="model-go")
                    yield VerticalScroll(id="model-wide")
                yield Panel(Static(id="seen"),
                            VerticalScroll(Static(id="seen-full"),
                                           id="seen-wide"),
                            title="AGENT CONTEXT", id="p-seen", topic="seen")
                yield Panel(VerticalScroll(Static(id="trace")),
                            VerticalScroll(Static(id="trace-full"),
                                           id="trace-wide"),
                            title="TRACE", id="p-trace", topic="trace")

    BINDINGS = ModeScreen.BINDINGS + [
        Binding("ctrl+l", "dialog_clear", "clear dialog", show=False),
        Binding("ctrl+r", "dialog_repeat", "repeat question", show=False),
    ]

    def action_dialog_clear(self) -> None:
        """^L — clear the dialog transcript while keeping question history."""
        if self._wide == "chat":
            self.submit_line("/clear")

    def action_dialog_repeat(self) -> None:
        """^R — re-ask the last question."""
        if self._wide != "chat":
            return
        q = self._last_q or (self._asked[-1]["q"] if self._asked else "")
        if q:
            import time as _time

            self._t0 = _time.monotonic()
            self.submit_line(q)

    def on_screen_resume(self) -> None:
        """Pick up dialog messages added from other views (e.g., CODE dock)."""
        try:
            self._sync_dialog()
        except Exception:
            pass

    def on_ready(self) -> None:
        grid = self.query_one("#question-chips", ItemGrid)
        for q in QUESTIONS:
            grid.mount(Chip("> " + q, q, classes="chip chip-question"))
        self._draw_seen()
        self._draw_trace()
        self._draw_model()
        self._draw_hq()
        self._greet()
        self._maybe_ask_key()
        self._check_model()
        self._watch_warmup()
        self._take_pending_question()

    def _maybe_ask_key(self) -> None:
        """Prompt once for a session-only API key if none is configured."""
        from ...agent import llm

        if self._key_offered or llm.has_session_key():
            return
        self._key_offered = True
        self._awaiting_key = True
        try:
            bar = self.query_one("#prompt", PromptBar)
            bar.input.placeholder = self.key_placeholder
        except Exception:
            pass
        t = Text()
        t.append("paste an API key here and press Enter — then ask away.\n",
                 style=palette.role_hex("title"))
        t.append("The key lives in memory for this session only and is never "
                 "saved to disk.\n",
                 style=palette.role_hex("dim"))
        t.append("You can also ask without a key to get answers from computed "
                 "numbers.\n",
                 style=palette.role_hex("dim"))
        hint = llm.key_source_hint(llm.provider())
        if hint:
            t.append(hint, style=palette.role_hex("faint"))
        self._bubble(Static(t, classes="msg-note"))
        self.chat.scroll_end(animate=False)

    def _stop_awaiting_key(self) -> None:
        """Restore normal question placeholder on the input bar."""
        self._awaiting_key = False
        try:
            bar = self.query_one("#prompt", PromptBar)
            bar.input.placeholder = self.placeholder
        except Exception:
            pass

    def _adopt_key(self, raw: str) -> None:
        """Accept a pasted API key without logging or saving the raw secret."""
        from ...agent import llm

        line = raw.strip()
        try:
            bar = self.query_one("#prompt", PromptBar)
            bar.history = [h for h in bar.history if h != line]
        except Exception:
            pass
        try:
            label, shown, repaired = llm.adopt_pasted_key(line)
        except llm.LLMError as e:
            t = Text()
            t.append("does not look like a key: ", style=palette.role_hex("warning"))
            t.append(str(e)[:120], style=palette.role_hex("dim"))
            self._bubble(Static(t, classes="msg-note"))
            return
        self._stop_awaiting_key()
        t = Text()
        t.append("key accepted: ", style=palette.role_hex("success"))
        t.append(f"{label} · {shown}", style=palette.role_hex("title"))
        if repaired:
            t.append("\ncleaned paste: " + "; ".join(repaired),
                     style=palette.role_hex("warning"))
        t.append("\nsession-only: closing the terminal drops the key. "
                 "Ask away.",
                 style=palette.role_hex("dim"))
        self._bubble(Static(t, classes="msg-note"))
        self.chat.scroll_end(animate=False)
        self._check_model()
        self.refresh_context()

    def _take_pending_question(self) -> None:
        """Pre-fill a bridged question from the journal without auto-sending."""
        q = getattr(self.app.session, "pending_question", "")
        if not q:
            return
        self.app.session.pending_question = ""
        try:
            bar = self.query_one("#prompt", PromptBar)
        except Exception:
            return
        bar.focus_input()
        bar.set_value(q)

    def _watch_warmup(self) -> None:
        """Poll local model warmup state until ready or failed, then stop."""
        from ...agent import llm

        if not llm.is_local():
            return

        def tick() -> None:
            from ...agent import local

            self._draw_seen()
            if local.warm_state()[0] in ("ready", "failed"):
                timer.stop()

        timer = self.set_interval(0.7, tick)

    def hint_pairs(self):
        out = [("Enter", "ask"), ("/", "commands"),
               ("Esc", "mode picker")]
        if self._wide == "chat":
            out.append(("/clear", "clear dialog"))
        return out

    # --- input ------------------------------------------------------------

    def submit_line(self, raw: str) -> None:
        """In AGENT, `/clear` clears the dialog transcript instead of exiting."""
        import time as _time

        line = raw.strip()
        if line.lstrip("/").lower() in ("clear", "cls"):
            self.clear_dialog()
            self._t0 = _time.monotonic()
            return
        super().submit_line(raw)

    def clear_dialog(self) -> None:
        self.chat.remove_children()
        self._buf = ""
        self._answer = None
        self.app.session.dialog.clear()
        self._shown = 0
        self._greet()
        self._bubble(Static(Text("— transcript cleared, question history kept on left —",
                                 style=palette.role_hex("faint")),
                            classes="msg-note"))
        self._draw_chat()
        self.chat.scroll_end(animate=False)

    def context_bits(self) -> str:
        from ...agent import llm

        base = super().context_bits()
        return f"{base}   ·   {llm.describe()}"

    # --- transcript -------------------------------------------------------

    @property
    def chat(self) -> VerticalScroll:
        return self.query_one("#chat", VerticalScroll)

    def _bubble(self, widget: Static) -> None:
        self.chat.mount(widget)
        self.chat.scroll_end(animate=False)

    def _greet(self) -> None:
        dim = palette.role_hex("dim")
        t = Text()
        t.append("core computes the numbers, agent explains them.\n",
                 style=palette.role_hex("text"))
        t.append("actions taken before answering appear in TRACE on the right; "
                 "every answer can be verified with a command.", style=dim)
        self._bubble(Static(t, classes="msg-note"))
        self._sync_dialog()

    def _sync_dialog(self) -> None:
        """Append any new entries from shared `session.dialog` incrementally."""
        for msg in self.app.session.dialog[self._shown:]:
            if msg["role"] == "you":
                head = Text()
                head.append("▌ ", style=palette.role_hex("faint"))
                head.append("you", style=palette.role_hex("dim"))
                head.append("\n")
                head.append(msg["text"], style=palette.role_hex("title"))
                self._bubble(Static(head, classes="msg-you"))
                continue
            mark = Text()
            mark.append("▌ ", style=palette.role_hex("mind"))
            mark.append("nex", style=f"{palette.role_hex('mind')} bold")
            self._bubble(Static(mark, classes="msg-mark"))
            body = (self._render_answer(msg["text"]) if msg["text"]
                    else Text("…", style=palette.role_hex("faint")))
            widget = Static(body, classes="msg-nex")
            self._bubble(widget)
            self._answer = widget
        self._shown = len(self.app.session.dialog)

    def _check_model(self) -> None:
        self.run_worker(self._model_worker, thread=True, group="mind")

    def _model_worker(self) -> None:
        from ...agent import agent as agent_mod

        try:
            ok, detail = agent_mod.status()
        except Exception as e:
            ok, detail = False, str(e)
        self.app.call_from_thread(self._model_done, ok, detail)

    def _model_done(self, ok: bool, detail: str) -> None:
        self._model = (ok, detail)
        self._draw_seen()
        self._draw_model()
        self._draw_hq()

    # --- input handling ---------------------------------------------------

    def handle_line(self, line: str) -> None:
        from ...agent import llm

        if line.startswith("/"):
            self.run_core(line)
            return
        if self._awaiting_key:
            if llm.looks_like_key_text(line):
                self._adopt_key(line)
                return
            self._stop_awaiting_key()
        self._ask(line)

    def _ask(self, question: str) -> None:
        import time

        self._last_q = question
        self._t0 = time.monotonic()
        self.app.session.dialog.append({"role": "you", "text": question,
                                        "facts": []})
        self.app.session.dialog.append({"role": "nex", "text": "",
                                        "facts": [], "waiting": True})
        self._buf = ""
        self._actions = []
        self._sync_dialog()
        self.set_busy(True)
        self.run_worker(lambda: self._ask_worker(question), thread=True,
                        exclusive=True, group="mind")

    def _ask_worker(self, question: str) -> None:
        try:
            for kind, value in self.app.session.agent().ask_stream(question):
                self.app.call_from_thread(self._chunk, kind, value)
        except Exception as e:
            self.app.call_from_thread(self._chunk, "error", str(e))
        self.app.call_from_thread(self._ask_done)

    def _chunk(self, kind: str, value: str) -> None:
        if kind == "action":
            self._actions.append(value)
            self._draw_trace()
            return
        if kind == "error":
            t = Text()
            t.append("no model: ", style=palette.role_hex("warning"))
            t.append(value[:160], style=palette.role_hex("dim"))
            self._bubble(Static(t, classes="msg-note"))
            return
        self._buf += value
        dialog = self.app.session.dialog
        if dialog and dialog[-1]["role"] == "nex":
            dialog[-1]["text"] = self._buf
            dialog[-1]["waiting"] = False
        if self._answer is not None:
            self._answer.update(self._render_answer(self._buf))
            self.chat.scroll_end(animate=False)

    def _render_answer(self, text: str) -> Text:
        """Lightweight inline formatting: **bold**, `code`, and bullet lists."""
        from ...ui import agent_view

        out = Text()
        for i, line in enumerate(text.split("\n")):
            if i:
                out.append("\n")
            body = line.strip()
            if body.startswith(("- ", "* ")):
                body = "— " + body[2:]
            out.append_text(Text.from_ansi(agent_view.markup(body)))
        return out

    def _ask_done(self) -> None:
        import time

        self.set_busy(False)
        if self._answer is not None and not self._buf.strip():
            self._answer.update(Text("no response",
                                     style=palette.role_hex("warning")))
        if self._last_q:
            self._asked.append({"q": self._last_q,
                                "seconds": time.monotonic() - self._t0,
                                "acts": len(self._actions)})
            self._last_q = ""
        self._draw_seen()
        self._draw_chat()
        self.refresh_context()
        self.chat.scroll_end(animate=False)

    def after_command(self) -> None:
        self._draw_seen()
        self._draw_model()
        self._draw_hq()

    def _core_done(self, out: str, err: str) -> None:
        """Render slash-command output as a dialog bubble (no separate console)."""
        self.set_busy(False)
        t = Text()
        if out.strip():
            try:
                t.append_text(Text.from_ansi(out.rstrip("\n")))
            except Exception:
                t.append(out.rstrip("\n"))
        if err.strip():
            if out.strip():
                t.append("\n")
            t.append(err.strip()[:500], style=palette.role_hex("warning"))
        if not out.strip() and not err.strip():
            t.append("(empty)", style=palette.role_hex("faint"))
        self._bubble(Static(t, classes="msg-note"))
        self.chat.scroll_end(animate=False)
        self.app.reload_palette()
        self.refresh_context()
        self.after_command()

    def redraw(self) -> None:
        self._draw_seen()
        self._draw_trace()
        self._draw_model()
        self._draw_hq()

    # --- right column & maximized panels ----------------------------------

    def _draw_chat(self) -> None:
        """Maximized DIALOG: clickable question history on left, transcript on right."""
        wide = self._wide == "chat"
        try:
            self.query_one("#chat-hist-col").display = wide
        except Exception:
            return
        panel = self.query_one("#p-chat", Panel)
        if not wide:
            panel.set_title("DIALOG")
            return
        n = len(self._asked)
        panel.set_title(f"DIALOG   ·   {n} "
                        f"{plural(n, 'question', 'questions', 'questions')}"
                        f"   ·   /clear — clear transcript")
        hist = self.query_one("#chat-hist", VerticalScroll)
        hist.remove_children()
        faint = palette.role_hex("faint")
        if not n:
            hist.mount(Static(Text("  ask your first question — it will "
                                   "appear here\n  so you can repeat it "
                                   "with a click", style=faint)))
            return
        accent = palette.role_hex("mind")
        title = palette.role_hex("title")
        for i, it in enumerate(self._asked, 1):
            row = Text()
            row.append(f"{i:>2}  ", style=faint)
            row.append(_wrap(it["q"], 40, 5), style=title)
            row.append("\n     ")
            row.append(f"{it['seconds']:.0f} s", style=faint)
            if it["acts"]:
                row.append(f"   ·   * {it['acts']} "
                           + plural(it["acts"], "action", "actions",
                                    "actions"), style=accent)
            row.append("\n")
            chip = Chip(row, value=it["q"], classes="hist-item")
            chip.tooltip = (f"{it['q']}\n{it['seconds']:.0f} s  ·  "
                            f"{it['acts']} actions\nclick — ask again")
            hist.mount(chip)

    def on_panel_expanded(self, event) -> None:
        topic = getattr(event.panel, "topic", "")
        self._wide = topic
        self._draw_seen()
        self._draw_trace()
        self._draw_chat()
        self._draw_model()
        self._draw_hq()
        if topic == "model":
            try:
                self.query_one("#model-filter", Input).focus()
            except Exception:
                pass
        elif topic == "hq":
            try:
                self.query_one("#hq-task", Input).focus()
            except Exception:
                pass
        self.refresh_hints()

    def on_panel_collapsed(self, event) -> None:
        self._wide = ""
        self._draw_seen()
        self._draw_trace()
        self._draw_chat()
        self._draw_model()
        self._draw_hq()
        self.refresh_hints()

    def panel_facts(self, topic: str) -> list[str]:
        """Facts scoped to the active maximized panel."""
        s = self.app.session
        base = [f"Block {s.scenario}, {len(s.dag_obj)} ops, "
                f"machine {s.model().name}."]
        cached = s.peek()
        if cached is not None:
            b, o, met = cached
            base.append(f"baseline {b.schedule.makespan} cyc, "
                        f"oracle {o.schedule.makespan} cyc, "
                        f"lower bound {met.lower_bound} cyc.")
        if topic == "trace":
            return base + (["Agent did: " + a for a in self._actions[-8:]]
                           or ["Agent has not run any actions yet."])
        if topic == "chat":
            asked = self._asked
            lines = [f"Dialog has {len(list(self.chat.children))} messages, "
                     f"{len(asked)} questions asked."]
            if asked:
                lines.append("Last question: " + asked[-1]["q"])
                lines.append("Click any question in the left history to repeat it.")
            return base + lines
        if topic == "hq":
            from ...agent import hq as hq_mod

            lines = [f"Connections: {len(self.headquarters_connections())}, "
                     f"missions: {len(self._hq_tasks)}."]
            for task in self._hq_tasks[-5:]:
                mark = {"working": "…", "done": "+",
                        "error": "-"}.get(task["status"], "·")
                lines.append(
                    f"{mark} {task['conn']} · "
                    f"{hq_mod.AREA_LABEL.get(task['area'], task['area'])}: "
                    f"{task['question'][:80]}")
            return base + lines
        if topic == "model":
            from ...agent import llm

            prov = self._model_provider()
            state = self._catalog_connection(prov)
            return base + [f"Provider: {llm._label(prov)}.",
                           f"Catalog: {state['status']}, "
                           f"rows: {len(state['rows'])}."]
        return base

    def panel_chips(self, topic: str) -> list[str]:
        from ...agent import hq as hq_mod

        return {
            "seen": ["which parts are computed vs inferred?",
                     "what numbers do you see right now?",
                     "what information is missing for an exact answer?"],
            "trace": ["why did you run that?",
                      "which command verifies this?",
                      "what will you check next?"],
            "chat": ["summarize more briefly",
                     "where should I start analyzing this block?",
                     "what should I ask next?"],
            "hq": [q for _, _, q in hq_mod.AREAS if q],
            "model": ["which provider should I pick for analysis?",
                      "how does cloud differ from a local server?",
                      "what if my API key is rejected?"],
        }.get(topic, [])

    def _section(self, label: str, note: str = "") -> Text:
        """Section rule: lowercase label with horizontal line to the edge."""
        width = max(40, self.app.size.width - 8)
        t = Text()
        t.append("  " + label + "  ", style=palette.role_hex("title") + " bold")
        used = len(label) + 4
        if note:
            t.append(note + "  ", style=palette.role_hex("faint"))
            used += len(note) + 2
        t.append("─" * max(0, width - used), style=palette.role_hex("line"))
        return t

    def _draw_seen_full(self) -> None:
        """Maximized AGENT CONTEXT: verbatim facts sent to the model."""
        target = self.query_one("#seen-full", Static)
        panel = self.query_one("#p-seen", Panel)
        from ...agent import context, llm

        s = self.app.session
        dim, faint = palette.role_hex("dim"), palette.role_hex("faint")
        title = palette.role_hex("title")
        try:
            facts = (context.machine_facts(s.model())
                     + context.schedule_facts(s)
                     + context.doctor_facts(s))
        except Exception:
            facts = self.panel_facts("seen")
        chars = sum(len(f) for f in facts)
        panel.set_title(f"AGENT CONTEXT   ·   verbatim facts   ·   "
                        f"{len(facts)} {plural(len(facts), 'fact', 'facts', 'facts')}")
        t = Text()
        t.append_text(self._section("model"))
        t.append("\n\n")
        ok, detail = self._model
        t.append("    " + ("checking…" if ok is None else
                           (llm.describe() if ok else "no model: " + detail)),
                 style=(faint if ok is None else
                        (palette.role_hex("success") if ok
                         else palette.role_hex("warning"))))
        t.append("\n\n")
        t.append_text(self._section(
            "facts sent to the model",
            f"{chars} chars  ·  ~{max(1, chars // 3)} tokens"))
        t.append("\n\n")
        for i, f in enumerate(facts, 1):
            t.append(f"    {i:>2}  ", style=faint)
            t.append(_wrap(f, max(40, self.app.size.width - 14), 8),
                     style=dim)
            t.append("\n")
        t.append("\n")
        t.append_text(self._section("what is not sent"))
        t.append("\n\n")
        t.append("    The model cannot see your source, the schedule grid, or\n"
                 "    compute schedules itself. It only explains the lines above.\n"
                 "    Verify any number not listed here with /doctor, /bounds,\n"
                 "    or /compare.",
                 style=faint)
        target.update(t)

    def _draw_trace_full(self) -> None:
        """Maximized TRACE: step-by-step agent actions and verification commands."""
        target = self.query_one("#trace-full", Static)
        panel = self.query_one("#p-trace", Panel)
        dim, faint = palette.role_hex("dim"), palette.role_hex("faint")
        n = len(self._actions)
        panel.set_title(f"TRACE   ·   agent actions   ·   "
                        f"{n} {plural(n, 'step', 'steps', 'steps')}")
        t = Text()
        t.append_text(self._section("what the agent ran",
                                    "before answering"))
        t.append("\n\n")
        if not self._actions:
            t.append("    The agent has not run any actions yet. When it loads\n"
                     "    a file, switches blocks, or runs the scheduler, each\n"
                     "    step is recorded here.", style=faint)
        else:
            for i, note in enumerate(self._actions, 1):
                t.append(f"    {i:>2}  ", style=palette.role_hex("mind"))
                t.append(_wrap(note, max(40, self.app.size.width - 14), 8),
                         style=dim)
                t.append("\n")
        t.append("\n")
        t.append_text(self._section("verify"))
        t.append("\n\n")
        for cmd, note in (("/doctor", "where cycles are lost"),
                          ("/compare", "both schedules side by side"),
                          ("/bounds", "block lower bound"),
                          ("/ai", "model status")):
            t.append("    " + cmd.ljust(12), style=palette.role_hex("mind"))
            t.append(note + "\n", style=faint)
        t.append("\n    Core computes the numbers. Trace lets you replay\n"
                 "    the agent's steps manually instead of taking its word.",
                 style=faint)
        target.update(t)

    def _draw_seen(self) -> None:
        wide = self._wide == "seen"
        self.query_one("#seen-wide").display = wide
        self.query_one("#seen", Static).display = not wide
        if wide:
            self._draw_seen_full()
            return
        self.query_one("#p-seen", Panel).set_title("AGENT CONTEXT")
        target = self.query_one("#seen", Static)
        s = self.app.session
        dim = palette.role_hex("dim")
        title = palette.role_hex("title")
        t = Text()

        def row(key: str, value: str, style: str = "") -> None:
            t.append(key.ljust(13), style=dim)
            t.append(value, style=style or title)
            t.append("\n")

        from ...agent import llm

        ok, detail = self._model
        if ok is None:
            row("model", detail, palette.role_hex("faint"))
        elif ok:
            row("model", llm.describe(), palette.role_hex("success"))
            if llm.is_local():
                from ...agent import local

                state, note = local.warm_state()
                if state == "warming":
                    row("", f"warming up — {note}", palette.role_hex("warning"))
                elif state == "ready":
                    row("", "warmed up, first reply is fast",
                        palette.role_hex("faint"))
                elif state == "failed":
                    row("", "warmup failed, first reply will be slower",
                        palette.role_hex("faint"))
        else:
            row("model", "offline", palette.role_hex("warning"))
            t.append(_wrap(detail, 40, 13), style=palette.role_hex("faint"))
            t.append("\n")
        row("block", s.scenario)
        row("ops", str(len(s.dag_obj)))
        row("machine", s.model().name)
        cached = s.peek()
        if cached is None:
            t.append("\n")
            t.append("not scheduled yet — the agent will run it\n"
                     "before answering", style=palette.role_hex("faint"))
            target.update(t)
            return
        base, orc, met = cached
        t.append("\n")
        row("baseline", f"{base.schedule.makespan} cyc")
        row("oracle", f"{orc.schedule.makespan} cyc",
            f"{palette.role_hex('success')} bold")
        row("bound", f"{met.lower_bound} cyc")
        t.append("same numbers as in LAB", style=palette.role_hex("faint"))
        target.update(t)

    def _draw_trace(self) -> None:
        wide = self._wide == "trace"
        self.query_one("#trace-wide").display = wide
        self.query_one("#trace", Static).display = not wide
        if wide:
            self._draw_trace_full()
            return
        self.query_one("#p-trace", Panel).set_title("TRACE")
        target = self.query_one("#trace", Static)
        if not self._actions:
            target.update(Text("no agent actions yet",
                               style=palette.role_hex("faint")))
            return
        t = Text()
        for i, note in enumerate(self._actions):
            if i:
                t.append("\n")
            t.append("· ", style=palette.role_hex("mind"))
            t.append(_wrap(note, 40, 2), style=palette.role_hex("dim"))
        target.update(t)

    # --- CONNECTION panel: compact + full catalog -------------------------

    #: Max catalog rows displayed before asking the user to narrow the filter.
    _MODEL_LIST_CAP = 80

    #: Catalog provider tab order (`custom` and internal `local` are hidden).
    CATALOG_ORDER = ("mistral", "gemini", "openai", "deepseek", "qwen",
                     "kimi", "grok", "anthropic", "glm", "muse",
                     "openrouter", "vercel", "gigachat", "yandex",
                     "local-server")

    #: Compact CONNECTION buttons (remaining providers appear when maximized).
    MINI_PROVS = ("mistral", "gemini", "openai", "deepseek", "local-server")

    def _model_provider(self) -> str:
        """Return the active catalog provider (defaulting to current)."""
        from ...agent import llm

        allowed = set(llm.PROVIDERS) - {"custom", "local"}
        if self._model_prov in allowed:
            return self._model_prov
        cur = llm.provider()
        return cur if cur in allowed else "mistral"

    def _draw_model(self) -> None:
        wide = self._wide == "model"
        try:
            self.query_one("#model-wide").display = wide
            self.query_one("#model-mini").display = not wide
            self.query_one("#model", Static).display = not wide
        except Exception:
            return
        if wide:
            self._draw_model_full()
            return
        self.query_one("#p-model", Panel).set_title(
            "CONNECTION   ·   2xclick for catalog")
        target = self.query_one("#model", Static)
        from ...agent import llm

        t = Text()
        dim, title = palette.role_hex("dim"), palette.role_hex("title")
        t.append("provider".ljust(13), style=dim)
        t.append(llm.describe(), style=title)
        t.append("\n")
        t.append("key".ljust(13), style=dim)
        if llm.has_session_key():
            t.append("set (session)", style=palette.role_hex("success"))
        else:
            t.append("none — paste below", style=palette.role_hex("warning"))
        target.update(t)
        self._redraw_model_provs_mini()

    def _redraw_model_provs_mini(self) -> None:
        """Highlight the selected provider in the compact CONNECTION block."""
        from ...agent import llm

        try:
            bar = self.query_one("#model-provs-mini", ItemGrid)
        except Exception:
            return
        if not bar.children:
            for p in self.MINI_PROVS:
                bar.mount(Tool(llm._label(p), f"mprov:{p}"))
        cur = self._model_provider()
        for tool in bar.query(Tool):
            name = tool.tool[6:] if tool.tool.startswith("mprov:") else ""
            mark = "* " if name == cur else ""
            label = llm._label(name) if name else ""
            tool.update(f"{mark}{label or name}")

    def _catalog_connection(self, prov: str | None = None) -> dict:
        from ...agent import llm

        prov = prov or self._model_provider()
        if not hasattr(self, "_catalog_connections"):
            self._catalog_connections: dict[str, dict] = {}
        if prov not in self._catalog_connections:
            key = llm.setting(llm.KEY_VAR.get(prov, ""), "")
            if prov == "gigachat":
                cid = llm.setting("GIGACHAT_CLIENT_ID", "")
                secret = llm.setting("GIGACHAT_SECRET", "") or llm.setting(
                    "GIGACHAT_CLIENT_SECRET", "")
                key = f"{cid}:{secret}" if cid and secret else ""
            self._catalog_connections[prov] = {
                "key": key, "url": llm.setting("NEX_LOCAL_URL",
                    "http://localhost:11434/v1") if prov == "local-server" else "",
                "folder": llm.setting("YANDEX_FOLDER_ID", "") if prov == "yandex" else "",
                "rows": [], "status": "locked", "note": "",
                "generation": 0, "selected": "", "backend": None,
                "draft_key": "", "verified": "",
            }
        return self._catalog_connections[prov]

    def _catalog_snapshot(self, prov: str) -> tuple[str, str, str, str]:
        state = self._catalog_connection(prov)
        return prov, state["key"], state["url"], state["folder"]

    def _invalidate_catalog(self, prov: str | None = None) -> None:
        state = self._catalog_connection(prov)
        state.update(rows=[], status="locked", note="", selected="", backend=None,
                     verified="", generation=state["generation"] + 1)

    def _refresh_catalog(self) -> None:
        if self._wide == "model" and self.is_mounted:
            self._draw_model_full()

    def _model_rows(self) -> tuple[list, str]:
        state = self._catalog_connection()
        return state["rows"], state["status"]

    _LOCAL_PRESETS = {"ollama": ("Ollama", "http://localhost:11434/v1"),
                      "studio": ("LM Studio", "http://localhost:1234/v1"),
                      "llama": ("llama.cpp", "http://localhost:8080/v1")}

    def _draw_model_full(self) -> None:
        wide = self.query_one("#model-wide", VerticalScroll)
        panel = self.query_one("#p-model", Panel)
        panel.set_title("CONNECTION   ·   provider → key → catalog")
        from ...agent import llm

        if not wide.children:
            wide.mount(Static("1 · provider", id="model-sec-prov"))
            provs = ItemGrid(id="model-provs", min_column_width=14)
            wide.mount(provs)
            for p in self.CATALOG_ORDER:
                provs.mount(Tool(llm._label(p), f"mprov:{p}"))
            wide.mount(Static("2 · key → connect", id="model-sec-key"))
            wide.mount(Input(placeholder="key · Enter loads models",
                             password=True, id="model-key"))
            wide.mount(Tool("connect / refresh catalog", "mconnect"))
            wide.mount(Static(id="model-status"))
            wide.mount(Static("local server: preset or custom URL",
                              id="model-sec-local"))
            presets = ItemGrid(id="model-presets", min_column_width=16)
            wide.mount(presets)
            for name, (label, _) in self._LOCAL_PRESETS.items():
                presets.mount(Tool(label, f"mpreset:{name}"))
            wide.mount(Input(placeholder="Local URL · http://localhost:11434/v1",
                             id="model-url"))
            wide.mount(Input(placeholder="Yandex folder ID", id="model-folder"))
            wide.mount(Static(
                "Start the server manually: Ollama — ollama serve; LM Studio — Start Server; "
                "llama.cpp — llama-server -m <path to existing GGUF>. "
                "Load an installed model on the server and click connect. "
                "Models are not downloaded automatically and TINY is not started here.",
                id="model-local-help"))
            wide.mount(Static("3 · catalog: click applies model for this session",
                              id="model-sec-list"))
            wide.mount(Static("search filters the list below: "
                              "type to filter, Enter picks the first match",
                              id="model-filter-help"))
            wide.mount(Input(placeholder="filter catalog…", id="model-filter"))
            wide.mount(VerticalScroll(id="model-list"))
            wide.mount(Static(id="model-note"))
            wide.mount(Static("not listed? enter model ID manually",
                              id="model-sec-manual"))
            wide.mount(Input(placeholder="model ID · Enter checks API (billed request)",
                             id="model-manual"))
            wide.mount(Tool("verify model (billed API request)", "mcheck"))
            wide.mount(Tool("activate verified ID", "mactivate", id="model-activate"))
        self._redraw_model_provs()
        self._sync_catalog_fields()
        self._draw_model_status()
        self._redraw_model_list()
        self._redraw_model_note()

    def _sync_catalog_fields(self) -> None:
        prov = self._model_provider()
        state = self._catalog_connection(prov)
        local = prov == "local-server"
        for wid in ("model-url", "model-presets"):
            self.query_one(f"#{wid}").display = local
        self.query_one("#model-folder").display = prov == "yandex"
        self.query_one("#model-manual").display = state["status"] in ("unsupported", "text")
        self.query_one("#model-key", Input).placeholder = (
            "key optional · Enter connects Local" if local else
            "key · Enter loads models")
        if getattr(self, "_catalog_field_provider", None) != prov:
            self._catalog_field_provider = prov
            for wid, value in (("model-url", state["url"]),
                               ("model-folder", state["folder"]),
                               ("model-key", state["draft_key"] or ""),
                               ("model-manual", ""),
                               ("model-filter", "")):
                field = self.query_one(f"#{wid}", Input)
                with field.prevent(Input.Changed):
                    field.value = value

    def _draw_model_status(self) -> None:
        try:
            target = self.query_one("#model-status", Static)
        except Exception:
            return
        prov = self._model_provider()
        state = self._catalog_connection(prov)
        from ...agent import llm

        t = Text()
        label = llm._label(prov)
        status = state["status"]
        if status == "live":
            style = palette.role_hex("success")
            t.append(f"{label}: catalog loaded", style=style)
        elif status == "error":
            t.append(f"{label}: {state['note'] or 'error'}",
                     style=palette.role_hex("warning"))
        elif status in ("unsupported", "text"):
            t.append(f"{label}: no catalog — enter ID and verify via API",
                     style=palette.role_hex("dim"))
        elif status == "locked":
            hint = llm.key_source_hint(prov)
            t.append(f"{label}: key required", style=palette.role_hex("warning"))
            if hint:
                t.append(f" — {hint}", style=palette.role_hex("faint"))
        else:
            t.append(f"{label}: loading catalog…",
                     style=palette.role_hex("dim"))
        target.update(t)

    def _redraw_model_provs(self) -> None:
        from ...agent import llm

        try:
            bar = self.query_one("#model-provs", ItemGrid)
        except Exception:
            return
        cur = self._model_provider()
        for tool in bar.query(Tool):
            name = tool.tool[6:] if tool.tool.startswith("mprov:") else ""
            mark = "* " if name == cur else ""
            label = llm._label(name) if name else ""
            tool.update(f"{mark}{label or name}")

    def _visible_model_rows(self) -> list:
        rows, _src = self._model_rows()
        q = self._model_filter.strip().lower()
        if not q:
            return rows
        return [r for r in rows
                if q in r.id.lower() or q in r.label.lower()]

    def _redraw_model_list(self) -> None:
        try:
            box = self.query_one("#model-list", VerticalScroll)
        except Exception:
            return
        box.remove_children()
        rows = self._visible_model_rows()
        for r in rows[:self._MODEL_LIST_CAP]:
            mark = "  [free]" if r.free else ""
            label = f"{r.label} · {r.id}" if r.label != r.id else r.id
            tool = Tool(Text(f"{label}{mark}"), f"model:{r.id}")
            tool.tooltip = r.id
            box.mount(tool)
        if len(rows) > self._MODEL_LIST_CAP:
            box.mount(Static(
                Text(f"… {len(rows) - self._MODEL_LIST_CAP} more — narrow filter",
                     style=palette.role_hex("faint"))))
        if not rows:
            _rows, src = self._model_rows()
            hints = {"live": "",
                     "error": "server did not respond — check network or URL",
                     "locked": "paste key above — list appears after connecting",
                     "unsupported": "enter model ID in the field above",
                     "text": "no catalog — enter model ID above"}
            hint = hints.get(src, "")
            box.mount(Static(Text(
                "no models found" + (f" ({hint})" if hint else ""),
                style=palette.role_hex("faint"))))

    def _redraw_model_note(self, text: str = "") -> None:
        state = self._catalog_connection()
        if text:
            state["note"] = text
        try:
            self.query_one("#model-note", Static).update(
                Text(state["note"], style=palette.role_hex("dim")))
        except Exception:
            pass

    def _apply_catalog_model(self, mid: str, verify: bool = False) -> None:
        """Apply a selected catalog model for the current session and close."""
        from ...agent import llm

        prov = self._model_provider()
        state = self._catalog_connection(prov)
        listed = state["status"] == "live" and any(
            row.id == mid for row in state["rows"])
        manual = state["status"] in ("unsupported", "text") and state["verified"] == mid
        if not mid or not (listed or manual):
            self._redraw_model_note("pick a catalog row or verify the ID via API first")
            return
        snapshot = self._catalog_snapshot(prov)
        try:
            if prov == "yandex" and not state["folder"]:
                raise llm.LLMError("Yandex: specify folder ID")
            backend = llm.configured_backend(prov, mid, *snapshot[1:])
            updates = llm.provider_updates(prov, {
                "model": mid, "key": snapshot[1], "url": snapshot[2],
                "folder": snapshot[3]})
            if prov == "local-server":
                updates["NEX_LOCAL_KEY"] = snapshot[1]
        except Exception:
            self._redraw_model_note("could not apply model — check key, URL, and folder ID")
            return
        import os as _os

        for k, v in updates.items():
            if v is None:
                _os.environ.pop(k, None)
            else:
                _os.environ[k] = v
        self._model_prov = prov
        state["selected"] = mid
        state["backend"] = backend
        t = Text()
        t.append("model: ", style=palette.role_hex("success"))
        t.append(f"{prov} · {mid} (session)", style=palette.role_hex("title"))
        self._bubble(Static(t, classes="msg-note"))
        self.chat.scroll_end(animate=False)
        self.refresh_context()
        self._check_model()
        self._draw_model()
        self._redraw_hq()
        if verify:
            self._check_catalog_model()
        try:
            panel = self.query_one("#p-model", Panel)
            self.screen.minimize()
            panel.post_message(Panel.Collapsed())
        except Exception:
            pass

    def _build_verified_backend(self, prov: str, mid: str):
        from ...agent import llm

        state = self._catalog_connection(prov)
        folder = state["folder"] if prov == "yandex" else ""
        try:
            return llm.configured_backend(prov, mid, state["key"],
                                          state["url"], folder)
        except llm.LLMError:
            return None

    def headquarters_connections(self) -> list[tuple[str, object]]:
        """Return `(label, backend)` pairs for verified HQ connections."""
        from ...agent import llm

        if not hasattr(self, "_catalog_connections"):
            return []
        out: list[tuple[str, object]] = []
        for prov, state in self._catalog_connections.items():
            backend = state.get("backend")
            if backend is not None and state.get("selected"):
                out.append((f"{llm._label(prov)} · {state['selected']}", backend))
        return out

    # --- HQ: primary right-column block -----------------------------------

    def _draw_hq(self) -> None:
        wide = self._wide == "hq"
        try:
            self.query_one("#hq-wide").display = wide
        except Exception:
            return
        if wide:
            self._draw_hq_full()
        else:
            self.query_one("#p-hq", Panel).set_title("HQ")
        self._draw_hq_mini()

    def _draw_hq_full(self) -> None:
        from ...agent import llm

        wide = self.query_one("#hq-wide", VerticalScroll)
        n_conns = len(self.headquarters_connections())
        n_tasks = len(self._hq_tasks)
        self.query_one("#p-hq", Panel).set_title(
            f"HQ   ·   connections: {n_conns}   ·   missions: {n_tasks}")
        if not wide.children:
            wide.mount(Static("connection — runs the mission "
                              "(configured in CONNECTION)", id="hq-sec-conn"))
            wide.mount(ItemGrid(id="hq-conns", min_column_width=22))
            wide.mount(Static("focus area", id="hq-sec-area"))
            wide.mount(ItemGrid(id="hq-areas", min_column_width=14))
            wide.mount(Static(id="hq-area-desc"))
            wide.mount(Static("script — extra prompt instructions (optional)",
                              id="hq-sec-script"))
            wide.mount(Input(placeholder="agent script… (optional)",
                             id="hq-script"))
            wide.mount(Static(id="hq-note"))
            wide.mount(Horizontal(
                Tool("dispatch agent", "hqrun"),
                Tool("clear completed", "hqclear"),
                id="hq-actions"))
            wide.mount(Static("missions", id="hq-sec-list"))
            wide.mount(VerticalScroll(id="hq-list"))
        self._redraw_hq()

    def _draw_hq_mini(self) -> None:
        try:
            target = self.query_one("#hq-mini", Static)
        except Exception:
            return
        t = Text()
        dim, title = palette.role_hex("dim"), palette.role_hex("title")
        n_conns = len(self.headquarters_connections())
        working = sum(1 for task in self._hq_tasks
                      if task["status"] == "working")
        if not n_conns:
            t.append("no connections", style=palette.role_hex("warning"))
            t.append(" — pick an API and paste key in CONNECTION",
                     style=dim)
        else:
            t.append(f"connections: {n_conns}", style=title)
            t.append(f"   ·   missions: {len(self._hq_tasks)}", style=dim)
            if working:
                t.append(f"   ·   running: {working}",
                         style=palette.role_hex("mind"))
        if self._hq_tasks:
            last = self._hq_tasks[-1]
            mark = {"working": "… ", "done": "+ ", "error": "- "}.get(
                last["status"], "· ")
            t.append(f"\n{mark}{last['question'][:30]}", style=dim)
        else:
            t.append("\ntype a mission below, Enter dispatches",
                     style=palette.role_hex("faint"))
        target.update(t)

    def _hq_note(self, text: str) -> None:
        try:
            self.query_one("#hq-note", Static).update(
                Text(text, style=palette.role_hex("dim")))
        except Exception:
            self._redraw_model_note(text)
        self._draw_hq_mini()

    def _redraw_hq(self) -> None:
        from ...agent import hq as hq_mod

        self._draw_hq_mini()
        try:
            conns = self.query_one("#hq-conns", ItemGrid)
            areas = self.query_one("#hq-areas", ItemGrid)
            box = self.query_one("#hq-list", VerticalScroll)
        except Exception:
            return
        labels = self.headquarters_connections()
        if self._hq_conn >= len(labels):
            self._hq_conn = 0
        conns.remove_children()
        if not labels:
            conns.mount(Static(Text("no connections — select a model "
                                    "in CONNECTION",
                                    style=palette.role_hex("faint"))))
        for i, (label, _be) in enumerate(labels):
            mark = "* " if i == self._hq_conn else ""
            conns.mount(Tool(f"{mark}{label}", f"hqconn:{i}"))
        areas.remove_children()
        for aid, alabel, _q in hq_mod.AREAS:
            mark = "* " if aid == self._hq_area else ""
            areas.mount(Tool(f"{mark}{alabel}", f"hqarea:{aid}"))
        try:
            desc = next(q for aid, _, q in hq_mod.AREAS
                        if aid == self._hq_area)
            self.query_one("#hq-area-desc", Static).update(
                Text(desc or "custom question — taken from the mission field",
                     style=palette.role_hex("faint")))
        except Exception:
            pass
        box.remove_children()
        for task in self._hq_tasks[-20:]:
            box.mount(Static(self._hq_task_text(task)))
            tools = Horizontal()
            box.mount(tools)
            tools.mount(Tool("retry", f"hqretry:{task['id']}"))
            tools.mount(Tool("remove", f"hqdel:{task['id']}"))

    def _hq_task_text(self, task: dict) -> Text:
        from ...agent import hq as hq_mod

        t = Text()
        mark = {"working": "… ", "done": "+ ", "error": "- "}.get(
            task["status"], "· ")
        t.append(f"{mark}{task['conn']} · "
                 f"{hq_mod.AREA_LABEL.get(task['area'], task['area'])}",
                 style=palette.role_hex("title"))
        t.append(f"\nmission: {task['question']}",
                 style=palette.role_hex("dim"))
        if task.get("script"):
            t.append(f"\nscript: {task['script']}",
                     style=palette.role_hex("faint"))
        if task.get("answer"):
            t.append(f"\n{task['answer']}",
                     style=palette.role_hex("text"))
        return t

    def _hq_run(self, retry: dict | None = None) -> None:
        from ...agent import hq as hq_mod

        labels = self.headquarters_connections()
        if not labels:
            self._hq_note("HQ: connect a model first in CONNECTION below")
            return
        if self._hq_conn >= len(labels):
            self._hq_conn = 0
        try:
            script = self.query_one("#hq-script", Input).value or ""
        except Exception:
            script = ""
        try:
            asked = self.query_one("#hq-task", Input).value or ""
        except Exception:
            asked = ""
        if retry is not None:
            area = retry["area"]
            script = script or retry.get("script", "")
            asked = asked or retry.get("question", "")
        else:
            area = self._hq_area
        question = asked.strip() or hq_mod.AREA_QUESTION.get(area, "")
        if not question:
            self._hq_note("HQ: enter a mission for the agent")
            return
        try:
            system = hq_mod.mission_system(self.app.session, area, script)
        except Exception as e:  # noqa: BLE001
            self._hq_note(f"HQ: no data — {e}"[:160])
            return
        label, backend = labels[self._hq_conn]
        self._hq_seq += 1
        task = {"id": self._hq_seq, "conn": label, "area": area,
                "script": script.strip(), "question": question,
                "status": "working", "answer": "",
                "backend": backend, "system": system}
        self._hq_tasks.append(task)
        self._redraw_hq()
        tid = task["id"]
        self.run_worker(lambda: self._hq_worker(tid), thread=True,
                        group=f"hq:{tid}", exclusive=True)

    def _hq_worker(self, tid: int) -> None:
        from ...agent import hq as hq_mod

        task = next((t for t in self._hq_tasks if t["id"] == tid), None)
        if task is None:
            return
        try:
            answer = hq_mod.run_mission(task["backend"], task["system"],
                                        task["question"])
            self.app.call_from_thread(self._hq_done, tid, True, answer)
        except Exception as e:  # noqa: BLE001
            self.app.call_from_thread(self._hq_done, tid, False, str(e)[:400])

    def _hq_done(self, tid: int, ok: bool, text: str) -> None:
        task = next((t for t in self._hq_tasks if t["id"] == tid), None)
        if task is None:
            return
        task["status"] = "done" if ok else "error"
        task["answer"] = text.strip()[:4000]
        task.pop("backend", None)
        task.pop("system", None)
        if self.is_mounted:
            self._redraw_hq()

    def _adopt_catalog_key(self, raw: str) -> None:
        """Bind a pasted catalog key explicitly to the selected provider."""
        from ...agent import llm

        prov = self._model_provider()
        state = self._catalog_connection(prov)
        state["draft_key"] = (raw or "").strip()
        self._connect_catalog()

    def _connect_catalog(self) -> None:
        from ...agent import llm

        prov = self._model_provider()
        state = self._catalog_connection(prov)
        raw = state["draft_key"]
        self._invalidate_catalog(prov)
        if raw:
            try:
                updates = llm.key_updates(prov, raw.split() if prov == "gigachat" else [raw])
            except llm.LLMError:
                state.update(status="error", note="check key format; GigaChat: id:secret")
                self._refresh_catalog()
                return
            import os as _os

            for k, v in updates.items():
                _os.environ[k] = v
            state["key"] = (f"{updates['GIGACHAT_CLIENT_ID']}:{updates['GIGACHAT_SECRET']}"
                            if prov == "gigachat" else raw)
            state["draft_key"] = ""
            for fid in ("#model-key", "#model-key-mini"):
                try:
                    field = self.query_one(fid, Input)
                except Exception:
                    continue
                with field.prevent(Input.Changed):
                    field.value = ""
        if not state["key"] and prov != "local-server":
            self._refresh_catalog()
            return
        state["status"] = "loading"
        snapshot = self._catalog_snapshot(prov)
        gen = state["generation"]
        self._refresh_catalog()
        self.run_worker(lambda: self._catalog_fetch_worker(snapshot, gen),
                        thread=True, group=f"catalog:{prov}", exclusive=True)

    @staticmethod
    def _catalog_error(error: Exception, snapshot: tuple) -> str:
        from ...agent import llm
        from urllib.parse import quote

        note = (str(error) if isinstance(error, llm.LLMError) else
                "connection failed — check key, URL, and network")
        secrets = [snapshot[1], snapshot[2], snapshot[3]]
        if snapshot[0] == "gigachat":
            secrets.extend(snapshot[1].split(":"))
        for secret in sorted(filter(None, secrets), key=len, reverse=True):
            note = note.replace(secret, "[redacted]").replace(quote(secret, safe=""), "[redacted]")
        return note[:240]

    def _catalog_fetch_worker(self, snapshot: tuple, gen: int) -> None:
        from ...agent import models as catalog

        prov, key, url, folder = snapshot
        status, note, rows = "error", "", []
        try:
            if prov == "local-server":
                url = catalog.local_base_url(url)
            rows, status = catalog.catalog(prov, key, url)
            if status not in ("locked", "live", "unsupported", "text", "error"):
                status = "error"
            if status != "live":
                rows = []
            if status == "error":
                note = "server returned no catalog — check key, URL, and network"
        except Exception as error:
            rows, status = [], "error"
            note = self._catalog_error(error, snapshot)
        out = {"rows": list(rows), "status": status, "note": note}
        self.app.call_from_thread(self._catalog_fetch_done, prov, gen, out)

    def _catalog_fetch_done(self, prov: str, gen: int, payload: dict) -> None:
        state = self._catalog_connection(prov)
        if gen != state["generation"]:
            return
        state.update(payload)
        if prov == self._model_provider():
            self._refresh_catalog()

    def _check_catalog_model(self, mid: str = "") -> None:
        prov = self._model_provider()
        state = self._catalog_connection(prov)
        manual = state["status"] in ("unsupported", "text")
        if not mid:
            mid = (self.query_one("#model-manual", Input).value.strip() if manual
                   else state["selected"])
        if not mid or (not manual and not any(
                row.id == mid for row in state["rows"])):
            self._redraw_model_note("pick a model or enter an ID for billed verification")
            return
        if prov == "yandex" and not state["folder"]:
            self._redraw_model_note("Yandex: specify folder ID and refresh catalog")
            return
        if state["status"] not in ("live", "unsupported", "text"):
            return
        state["generation"] += 1
        state["verified"] = ""
        snapshot, gen = self._catalog_snapshot(prov), state["generation"]
        self._redraw_model_note("verifying model via API — request may be billed…")
        self.run_worker(lambda: self._catalog_check_worker(snapshot, gen, mid),
                        thread=True, group=f"catalog:{prov}", exclusive=True)

    def _catalog_check_worker(self, snapshot: tuple, gen: int, mid: str) -> None:
        from ...agent import llm

        prov, key, url, folder = snapshot
        success = False
        try:
            be = llm.configured_backend(prov, mid, key, url, folder)
            be.complete("Reply with a single word.", "Say 'ready'.", temperature=0.0)
            success, note = True, "model is reachable — ready to activate"
        except Exception as error:
            note = self._catalog_error(error, snapshot)
        self.app.call_from_thread(self._catalog_note_done, prov, gen, mid, success, note)

    def _catalog_note_done(self, prov: str, gen: int, mid: str,
                           success: bool, note: str) -> None:
        state = self._catalog_connection(prov)
        if gen != state["generation"]:
            return
        state.update(verified=mid if success else "", note=note)
        if prov == self._model_provider():
            self._refresh_catalog()

    def on_input_changed(self, event) -> None:
        wid = getattr(event, "input", None)
        if wid is None:
            return
        iid = getattr(wid, "id", "")
        if iid == "model-filter":
            event.stop()
            if self._mute_filter:
                return
            self._model_filter = wid.value or ""
            self._redraw_model_list()
        elif iid in ("model-url", "model-folder"):
            event.stop()
            state = self._catalog_connection()
            field = "url" if iid == "model-url" else "folder"
            value = (wid.value or "").strip()
            if state[field] or value:
                state[field] = value
                self._invalidate_catalog()
        elif iid in ("model-key", "model-key-mini"):
            event.stop()
            state = self._catalog_connection()
            state["draft_key"] = (wid.value or "").strip()
            if state["draft_key"]:
                self._invalidate_catalog()

    def on_input_submitted(self, event) -> None:
        wid = getattr(event, "input", None)
        if wid is None:
            return
        iid = getattr(wid, "id", "")
        if iid in ("model-key", "model-key-mini"):
            event.stop()
            self._adopt_catalog_key(wid.value or "")
        elif iid == "model-url":
            event.stop()
            self._connect_catalog()
        elif iid == "model-manual":
            event.stop()
            mid = (wid.value or "").strip()
            if mid:
                self._apply_catalog_model(mid, verify=True)
        elif iid == "model-filter":
            event.stop()
            rows = self._visible_model_rows()
            if rows:
                self._apply_catalog_model(rows[0].id)
        elif iid == "hq-task":
            event.stop()
            self._hq_run()

    def panel_tool(self, tool: str) -> None:
        """Handle CONNECTION catalog, HQ, and base panel tools."""
        if tool.startswith("mprov:"):
            self._model_prov = tool[6:]
            self._model_filter = ""
            self._catalog_field_provider = None
            try:
                self._mute_filter = True
                self.query_one("#model-filter", Input).value = ""
            except Exception:
                pass
            finally:
                self._mute_filter = False
            if self._wide == "model":
                self._draw_model_full()
            else:
                self._draw_model()
            self._draw_hq()
            state = self._catalog_connection()
            if state["status"] in ("", "locked") and state["key"]:
                self._connect_catalog()
            return
        if tool.startswith("mpreset:"):
            preset = self._LOCAL_PRESETS.get(tool[8:])
            if preset:
                url_input = self.query_one("#model-url", Input)
                url_input.value = preset[1]
                self._connect_catalog()
            return
        if tool.startswith("model:"):
            self._apply_catalog_model(tool[6:])
            return
        if tool in ("mconnect", "mconnect-mini"):
            self._connect_catalog()
            return
        if tool == "mcheck":
            self._check_catalog_model()
            return
        if tool == "mactivate":
            state = self._catalog_connection()
            if state["verified"]:
                self._apply_catalog_model(state["verified"])
            else:
                self._redraw_model_note("verify the model via API before activating")
            return
        if tool.startswith("hqconn:"):
            try:
                self._hq_conn = int(tool[7:])
            except ValueError:
                pass
            self._redraw_hq()
            return
        if tool.startswith("hqarea:"):
            self._hq_area = tool[7:]
            self._redraw_hq()
            return
        if tool == "hqrun":
            self._hq_run()
            return
        if tool == "hqclear":
            self._hq_tasks = [t for t in self._hq_tasks
                              if t["status"] == "working"]
            self._redraw_hq()
            return
        if tool.startswith("hqretry:"):
            try:
                tid = int(tool[8:])
            except ValueError:
                return
            task = next((t for t in self._hq_tasks if t["id"] == tid), None)
            if task is not None:
                self._hq_run(retry=task)
            return
        if tool.startswith("hqdel:"):
            try:
                tid = int(tool[6:])
            except ValueError:
                return
            self._hq_tasks = [t for t in self._hq_tasks if t["id"] != tid]
            self._redraw_hq()
            return
        super().panel_tool(tool)
