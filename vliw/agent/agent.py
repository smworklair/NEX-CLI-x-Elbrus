"""Agent: understands natural-language questions, inspects live data, and answers.

Single-turn flow:

    question -> (1) detect action -> (2) execute in core ->
    (3) assemble FACTS -> (4) LLM explains -> answer + next step

Steps 1–3 are deterministic: the parser loads files, exact search computes
schedules, and `core.doctor` pinpoints losses. The LLM only phrases and reasons
over verified numbers — so every answer can be cross-checked with a command and
never drifts between runs.

If offline or the key is rejected, the agent degrades gracefully and answers
deterministically from the same computed facts.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from . import context, llm

# --- action detection -----------------------------------------------------
# Not general NLU, just a narrow set of domain intents. Works offline and
# also serves as a grounded hint for the language model.

_ACTIONS = [
    ("load",     r"(load|open|read|parse|analyze|загруз|открой|прочит|разбер)\w*\s+([\w./\\-]+\.s)\b"),
    ("scenario", r"(run|show|switch|use|try|прогони|запусти|покажи|возьми)\w*\s+(\w+)"),
    ("doctor",   r"(diagnos|doctor|what.?s wrong|where.*lost|why.*slow|problem|loss|stall|диагност|что не так|где теря|почему медлен|проблем|доктор|потер)"),
    ("compare",  r"(compar|diff|baseline\s*(vs|versus|against|против)|oracle\s*(vs|versus|against)|сравн|разниц|оракул\w*\s+против)"),
    ("bounds",   r"(lower\s*bound|bound|limit|theoret|can.?t.*faster|предел|нижн\w*\s+границ|быстрее\s+нельзя|теоретическ)"),
    ("path",     r"(critical\s*path|критическ\w*\s+пут)"),
    ("asm",      r"(wide\s+instruct|\.s\b|assemb|asm|lcc|широк\w*\s+команд|ассемблер|как\s+в\s+lcc)"),
    ("model",    r"(machine\s+model|port\w*|capabilit|monopol|модель\s+машин|порт\w*|матриц\w*\s+возможн|монопол)"),
    ("explain",  r"(cycle\s+(\d+)|at\s+cycle\s+(\d+)|такт\w*\s+(\d+)|в\s+такте\s+(\d+))"),
]


# Pull scenario keys directly from the registry so new scenarios are recognized
# automatically without editing this file.
def _scenario_hint() -> re.Pattern:
    from ..core import SCENARIOS

    keys = sorted(SCENARIOS, key=len, reverse=True)
    return re.compile(r"\b(" + "|".join(map(re.escape, keys)) + r"|rand\d+)\b", re.I)


_SCENARIO_HINT = _scenario_hint()

#: Small-talk turns that should not trigger scheduling or append a "Next:" command.
_SMALLTALK = re.compile(
    r"^(hello|hi|hey|good\s+(morning|afternoon|evening)|"
    r"thanks|thank\s+you|thx|cheers|"
    r"bye|goodbye|see\s+you|"
    r"ok|okay|got\s+it|understood|sure|cool|nice|"
    r"how\s+are\s+you|what\s+can\s+you\s+do|who\s+are\s+you|"
    r"привет|прив|здравствуй(те)?|хай|"
    r"добр(ый|ого)\s+(день|вечер|утро)|йоу|"
    r"спасибо|спс|благодарю|"
    r"пока|до\s+свидания|бывай|"
    r"ок|окей|ясно|понял|понятно|угу|ага|"
    r"как\s+дела|что\s+умеешь|кто\s+ты)[\s!.?)]*$",
    re.I,
)


def _is_smalltalk(q: str) -> bool:
    return bool(_SMALLTALK.match(q.strip()))


#: Questions about provenance / certainty of the previous answer ("are you sure?").
_DOUBT = re.compile(
    r"^(are\s+you\s+)?(sure|certain|really|truly|proven|verify|double[- ]?check|"
    r"how\s+do\s+you\s+know|source|prove\s+it|"
    r"(а\s+)?(ты\s+)?(точно|уверен[аы]?|правда|серьёзно|не\s+врёшь|"
    r"не\s+ошиб(аешься|ся)|проверь|перепроверь|откуда|почему\s+так\s+решил))"
    r"[\s!?.]*$",
    re.I,
)


def _is_doubt(q: str) -> bool:
    """Doubt about the previous answer.

    Handled deterministically because the system prompt focuses on block FACTS,
    whereas "are you sure?" asks about provenance of the computed numbers —
    something the tool tracks directly and answers better than any LLM.
    """
    return bool(_DOUBT.match(q.strip()))


@dataclass
class Turn:
    question: str
    answer: str = ""
    actions: list[str] = field(default_factory=list)
    offline: bool = False
    error: str = ""


@dataclass
class Agent:
    """Conversational session layered over the current analysis state."""

    session: object
    history: list[Turn] = field(default_factory=list)
    last_error: str = ""

    # --- actions ----------------------------------------------------------

    def _detect(self, q: str) -> list[tuple[str, str]]:
        ql = q.lower()
        found: list[tuple[str, str]] = []
        m = re.search(_ACTIONS[0][1], ql)
        if m:
            found.append(("load", m.group(2)))
        sc = _SCENARIO_HINT.search(q)
        if sc:
            found.append(("scenario", sc.group(1).lower()))
        for name, pat in _ACTIONS[2:]:
            if re.search(pat, ql):
                found.append((name, ""))
        return found

    def _run_actions(self, q: str) -> list[str]:
        """Run deterministic actions implied by the question BEFORE calling the LLM."""
        from ..core import asm_parser, get_scenario

        done: list[str] = []
        for kind, arg in self._detect(q):
            try:
                if kind == "load" and arg:
                    parsed = asm_parser.parse_file(arg)
                    if parsed.ops:
                        dag = asm_parser.build_dag(parsed, key=f"asm:{arg}", title=arg)
                        self.session.set_dag(dag, f"asm:{arg.split('/')[-1]}")
                        done.append(f"parsed {arg}: {len(parsed.ops)} ops, "
                                    f"{parsed.bundles} wide instructions")
                elif kind == "scenario" and arg:
                    self.session.set_scenario(arg)
                    done.append(f"switched to scenario {arg}")
            except Exception as e:
                done.append(f"failed to run {kind} {arg}: {e}")
        # Small talk does not need scheduling — avoid running the oracle on "hi".
        if _is_smalltalk(q):
            return done
        # Any substantive question requires a computed schedule.
        if self.session.peek() is None:
            try:
                self.session.results()
                done.append("computed schedule (baseline and exact oracle)")
            except Exception as e:
                done.append(f"failed to compute schedule: {e}")
        return done

    # --- answering --------------------------------------------------------

    def _needs_layout(self, q: str) -> bool:
        """Always include the schedule layout once computed.

        Previously this used keyword matching, which caused hallucinated cycle
        and channel numbers whenever a question phrased layout queries without
        matching keywords. Including the compact layout costs only a dozen lines.
        """
        return self.session.peek() is not None

    def _history_pairs(self, limit: int = 6) -> list[tuple[str, str]]:
        pairs: list[tuple[str, str]] = []
        for t in self.history[-limit:]:
            if t.answer:
                pairs.append(("user", t.question))
                pairs.append(("model", t.answer))
        return pairs

    def ask_stream(self, question: str,
                   panel: tuple[str, list[str]] | None = None):
        """Stream response as ('action'|'text'|'error', value) tuples.

        `panel` is (title, facts) of a specific open pane when invoked from an
        inline pane prompt rather than the main AGENT chat. Actions still run
        identically; `panel` only narrows the answer via a prompt suffix
        (preserving llama.cpp prefix cache).
        """
        turn = Turn(question=question)
        self.history.append(turn)

        for note in self._run_actions(question):
            turn.actions.append(note)
            yield ("action", note)

        # Provenance question ("are you sure?") is answered directly from core data.
        if _is_doubt(question) and self.history[:-1]:
            answer = self._provenance()
            turn.answer = answer
            yield ("text", answer)
            return

        small = _is_smalltalk(question)
        system = context.system_prompt(self.session, self._needs_layout(question),
                                       panel=panel, smalltalk=small)
        chunks: list[str] = []
        try:
            for piece in llm.stream(system, question, self._history_pairs(),
                                    nudge=not small):
                chunks.append(piece)
                yield ("text", piece)
            turn.answer = "".join(chunks).strip()
            if not turn.answer:
                raise llm.LLMError("empty model response")
        except llm.LLMError as e:
            turn.offline = True
            turn.error = str(e)
            self.last_error = str(e)
            fallback = self.offline_answer(question)
            turn.answer = fallback
            yield ("error", str(e))
            yield ("text", fallback)

    def _provenance(self) -> str:
        """Honest provenance of the computed numbers, with explicit caveats."""
        got = self.session.peek()
        lines: list[str] = []
        if not got:
            return ("No schedule has been computed yet — nothing to verify. "
                    "Run one first: /run or F5.\n\nNext: /run")

        # peek() returns (baseline, oracle, metrics): only the oracle proves optimality.
        _base, orc, _met = got
        proven = getattr(orc, "optimal", None)
        stats = getattr(orc, "search_stats", {}) or {}
        makespan = orc.schedule.makespan

        if proven:
            lines.append(
                f"Yes, for the provable part. {makespan} cycles is a PROVEN "
                "optimum: exact search ruled out every shorter schedule.")
            if stats.get("nodes"):
                lines.append(f"Search nodes explored: {stats['nodes']}.")
        else:
            lb = stats.get("lower_bound")
            lines.append(
                f"Not completely. {makespan} cycles is the best FOUND, not "
                "proven optimal: exact search hit its budget."
                + (f" Only proven that nothing shorter than {lb} cycles exists."
                   if lb else ""))

        # Key project caveat: the machine model is simpler than real silicon.
        lines.append(
            "All of this holds relative to the MACHINE MODEL, which is simpler "
            "than real silicon: it excludes memory-carried dependencies, "
            "inter-cluster latencies, and int/fp transfer penalties.")

        try:
            from ..core.isa import collect
            rows = collect(self.session.model())
            guessed = [r.name for r in rows if not r.latency_measured]
            if guessed:
                lines.append(
                    f"Latency is measured for {len(rows) - len(guessed)} of "
                    f"{len(rows)} op classes; the rest use assumptions "
                    f"({', '.join(guessed[:5])}"
                    + ("…" if len(guessed) > 5 else "") + ").")
        except Exception:
            pass

        lines.append("Cross-check: /isa — provenance of every number, "
                     "/selfcheck — verify the oracle with an independent search.")
        return "\n".join(lines) + "\n\nNext: /isa"

    def ask(self, question: str) -> Turn:
        """One-shot full response (for CLI/script invocation)."""
        turn = Turn(question=question)
        self.history.append(turn)
        turn.actions = self._run_actions(question)
        system = context.system_prompt(self.session, self._needs_layout(question))
        try:
            turn.answer = llm.complete(system, question, self._history_pairs(),
                                       nudge=not _is_smalltalk(question))
        except llm.LLMError as e:
            turn.offline = True
            turn.error = str(e)
            turn.answer = self.offline_answer(question)
        return turn

    # --- offline fallback -------------------------------------------------

    def offline_answer(self, question: str) -> str:
        """Offline response using the same computed facts without LLM prose."""
        from ..core.doctor import diagnose

        if _is_smalltalk(question):
            return ("The model is currently unavailable. Type /ai to check "
                    "which key is active, then try again.")

        s = self.session
        cached = s.peek()
        lines = ["Model unavailable — answering from computed data."]
        if cached is None:
            lines.append("Schedule not computed yet: run /run.")
            return "\n".join(lines)

        base, orc, met = cached
        b, o = base.schedule.makespan, orc.schedule.makespan
        lines.append(f"Block {s.scenario}: baseline {b} cyc, exact oracle {o} cyc, "
                     f"lower bound {met.lower_bound} cyc.")
        try:
            from .context import tiny_facts

            lines.extend(tiny_facts(s))
        except Exception:
            pass
        try:
            d = diagnose(s.dag_obj, s.model(), base.schedule, met)
            losses = [f for f in d.findings if f.recoverable]
            if losses:
                f = losses[0]
                lines.append(f"Primary loss: −{f.cycles_lost} cyc — {f.title}.")
                lines.append(f"Why: {f.why}")
                lines.append(f"Fix: {f.fix}")
            else:
                lines.append("No ordering losses — limited by machine lower bound.")
        except Exception:
            pass
        lines.append("Next: /doctor — full diagnostics.")
        return "\n".join(lines)


def status() -> tuple[bool, str]:
    return llm.check()
