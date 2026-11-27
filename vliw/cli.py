"""Single CLI entry point: command -> core -> ui -> output.

  python -m vliw                 interactive: mode picker, then main loop
  python -m vliw run slotclash   one-shot command and exit
  python -m vliw --plain         line-by-line interactive loop (no full-screen TUI)

Three workstation panes:
  core   — interpreter (sum 8, custom expressions)
  lab    — /run /compare /doctor
  agent  — natural-language Q&A

Glue layer only. All scheduling logic lives in `vliw.core`.
"""

from __future__ import annotations

import argparse
import difflib
import itertools
import json
import os
import random as _random
import re
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

# readline is part of the Python stdlib (optional on some Windows builds).
# Provides persistent command history and Tab completion in plain mode.
try:
    import readline

    HAS_READLINE = True
except Exception:  # pragma: no cover - platform-dependent
    readline = None  # type: ignore[assignment]
    HAS_READLINE = False

from . import core
from .core import (
    DAG,
    DEFAULT_PROFILE,
    PROFILES,
    SCENARIOS,
    GreedyListScheduler,
    MachineModel,
    OracleScheduler,
    compute_metrics,
    get_profile,
    get_scenario,
    interpret,
    kernel_help,
    looks_like_work,
    InterpError,
    Workspace,
    random_dag,
    run_selfcheck,
)
from .core import asm_parser, doctor
from .ui import (
    agent_view, analyst_view, context, launcher, diagnostics, logo, render,
    schedule_view, slash, tables, theme,
)
from .ui.logo import print_logo
from .ui.render import Style, op_legend, paint, panel, rule, wrap


# --------------------------------------------------------------------------
# Session: active scenario/profile/width + schedule result cache
# --------------------------------------------------------------------------


@dataclass
class Session:
    args: object
    profile: str = DEFAULT_PROFILE
    scenario: str = "slotclash"
    event_sink: object = None
    """Optional callback receiving scheduler events instead of printing lines."""
    dag_obj: DAG | None = None
    width: int | None = None
    delay: float | None = None  # playback delay; None = step on Enter
    mode: str = "explore"       # compatibility: explore ~ lab, chat ~ mind
    focus: str = "lab"          # work | lab | mind | code — active pane
    last_work: str = ""
    code_text: str = ""
    """Source buffer (e2k assembly) shared across CODE mode and `/code`."""
    code_path: str = ""
    """Last file path loaded into or saved from the CODE buffer."""
    code_run_text: str = ""
    """Snapshot of `code_text` as of the last `/code run` (F5)."""
    journal_runs: list = field(default_factory=list)
    """Shared session run journal across CORE, LAB, AGENT, and CODE."""
    journal_events: list = field(default_factory=list)
    """Live event stream belonging to the current run."""
    dialog: list = field(default_factory=list)
    """Shared agent conversation history for the session."""

    pending_note: str = ""
    """Note queued for CORE (set by journal bridge)."""
    pending_question: str = ""
    """Question queued for AGENT (set by journal bridge)."""
    _workspace: object = None
    _agent: object = None
    compiler_sched: object = None
    _cache: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.dag_obj is None:
            self.dag_obj = get_scenario(self.scenario)

    def model(self) -> MachineModel:
        m = get_profile(self.profile)
        if self.width and self.width != m.width:
            m = m.with_width(self.width)
        return m

    def set_scenario(self, key: str) -> None:
        self.dag_obj = get_scenario(key)
        self.scenario = key

    def set_dag(self, dag: DAG, label: str) -> None:
        # Invalidate cached schedules for this label so re-running an edited
        # CODE buffer always recomputes fresh numbers.
        self._cache = {k: v for k, v in self._cache.items() if k[0] != label}
        self.dag_obj = dag
        self.scenario = label

    def workspace(self) -> Workspace:
        if self._workspace is None:
            self._workspace = Workspace()
        return self._workspace

    def agent(self):
        """Conversational agent session (created lazily on first use)."""
        if self._agent is None:
            from .agent import Agent

            self._agent = Agent(session=self)
        return self._agent

    def peek(self):
        """Return cached (base, oracle, metrics) or None without running search."""
        return self._cache.get((self.scenario, self.profile, self.width))

    def results(self):
        """Compute, validate, and cache (base, oracle, metrics) via core."""
        key = (self.scenario, self.profile, self.width)
        if key not in self._cache:
            d, m = self.dag_obj, self.model()
            base = GreedyListScheduler().schedule(d, m)
            orc = OracleScheduler(
                budget_s=getattr(self.args, "budget", 10.0) or 10.0,
                portfolio_s=getattr(self.args, "portfolio", 3.0) or 3.0,
            ).schedule(d, m)
            for res, who in ((base, "baseline"), (orc, "oracle")):
                errs = res.schedule.validate()
                if errs:
                    raise SystemExit(
                        f"INTERNAL ERROR: {who} produced an invalid schedule:\n  "
                        + "\n  ".join(errs)
                    )
            self._cache[key] = (base, orc, compute_metrics(d, m))
        return self._cache[key]


def _header(session: Session) -> str:
    m = session.model()
    return (
        paint("1", session.scenario)
        + Style.dim(f"  ·  {len(session.dag_obj)} instr.  ·  {m.name}"
                    f"  ·  {m.width} ports")
    )


def _out(lines) -> None:
    print("\n".join(lines) if isinstance(lines, list) else lines)


# --------------------------------------------------------------------------
# Commands
# --------------------------------------------------------------------------


def cmd_run(session: Session, arg: str) -> None:
    if arg.strip():
        session.set_scenario(arg.split()[0])
    base, orc, met = session.results()
    dag, model = session.dag_obj, session.model()
    print(rule(dag.title))
    print("  " + _header(session))
    print("  " + op_legend())
    print()
    if dag.note:
        _out(wrap(dag.note, render.W, "  "))
        print()
    if getattr(dag, "lesson", ""):
        _out(wrap(paint("lab", "* ") + Style.dim(dag.lesson), render.W, "  "))
        print()
    hl = {i: render.CRIT_CODE for i in schedule_view.critical_set(dag, met)}
    _out(schedule_view.render_schedule(
        orc.schedule, dag, model, hl,
        paint("success", "  oracle schedule (exact search), * — critical path:")))
    print()
    print(schedule_view.render_stats_line(base, orc))
    print()
    _out(schedule_view.render_verdict(base, orc, met))
    print()
    print(Style.dim("  next:  compare   doctor   path   bounds"))


def cmd_compare(session: Session, arg: str) -> None:
    """Compare baseline and oracle side by side; `--model` adds the learned model."""
    toks = arg.split()
    want_model = any(t in ("--model", "--learned") for t in toks)
    rest = [t for t in toks if not t.startswith("--")]
    if rest:
        session.set_scenario(rest[0])
    base, orc, met = session.results()
    dag, model = session.dag_obj, session.model()
    diverged = {
        i for i in range(len(dag))
        if base.schedule.placements[i].cycle != orc.schedule.placements[i].cycle
    }
    print(rule("compare · " + dag.title))
    print("  " + _header(session))
    print("  " + op_legend())
    print("  " + paint(render.DIVERGE_CODE, "highlighted") + Style.dim(" — instructions in different cycles"))
    print()
    hl = {i: render.DIVERGE_CODE for i in diverged}
    _out(schedule_view.render_schedule(
        base.schedule, dag, model, hl,
        paint("warning", "  baseline — greedy heuristic:")))
    print()
    _out(schedule_view.render_schedule(
        orc.schedule, dag, model, hl,
        paint("success", "  oracle — exact search:")))
    print()
    from .ui import learned_view

    learned_res = None
    if want_model:
        learned_res = _compare_learned(session, dag, model, hl)
    _out(schedule_view.render_divergence_line(base, orc, dag, met))
    print()
    _out(schedule_view.render_verdict(base, orc, met))
    if learned_res is not None:
        print()
        _out(learned_view.render_compare_line(learned_res, base, orc))
    elif not want_model:
        print()
        print(Style.dim("  include learned model as a third scheduler: /compare --model"))


def _compare_learned(session: Session, dag, model, hl):
    """Run the learned model and print its schedule third. Returns None on failure."""
    from .learned import runtime

    ready, lines = runtime.status()
    if not ready:
        print()
        print(paint("warning", "  learned model unavailable — showing comparison without it"))
        print(Style.dim("  details: /learned --status"))
        return None

    adapter = runtime.resolve_adapter()
    print()
    print(paint("lab", f"  learned model ({adapter.name}) running, ~30 s:"))
    _line: list[str] = []

    def _stream(chunk: str) -> None:
        for ch in chunk:
            if ch == "\n":
                text = "".join(_line).replace("[end of text]", "").rstrip()
                _line.clear()
                if text:
                    print("    " + Style.dim(text))
                    sys.stdout.flush()
            else:
                _line.append(ch)

    from .learned import LearnedScheduler

    try:
        res = LearnedScheduler(adapter=adapter, repair=True).schedule(
            dag, model, on_text=_stream)
        _stream("\n")
    except (RuntimeError, OSError, ImportError, TimeoutError) as e:
        print(paint("error", f"  model failed: {e}"))
        return None

    print()
    st = res.search_stats
    if st["valid"]:
        label = "  model — learned" + (
            " + channel repair:" if st.get("repaired") else ":")
        _out(schedule_view.render_schedule(res.schedule, dag, model, hl,
                                           paint("lab", label)))
    else:
        print(paint("error", "  model produced an invalid schedule — skipping grid:"))
        for e in st["errors"][:4]:
            print("    " + Style.dim(e))
    return res


def cmd_tiny(session: Session, arg: str) -> None:
    """Compare TINY AI against baseline and oracle on the current block.

    Weights live in `vliw/tiny/weights*.json`; if missing, TinyFlashScheduler
    falls back cleanly to baseline. Runs in milliseconds.
    """
    toks = arg.split()
    if toks:
        session.set_scenario(toks[0])
    base, orc, _met = session.results()
    dag, model = session.dag_obj, session.model()
    from .tiny.fast import TinyFlashScheduler
    import time as _time
    t0 = _time.perf_counter()
    tiny = TinyFlashScheduler()
    res = tiny.schedule(dag, model)
    dt = (_time.perf_counter() - t0) * 1000.0
    errs = res.schedule.validate()
    print(rule("TINY AI · " + dag.title))
    print("  " + _header(session))
    print()
    print(f"  baseline : {base.schedule.makespan} cyc")
    print(f"  oracle   : {orc.schedule.makespan} cyc"
          + (" (proven)" if orc.optimal else ""))
    print(f"  tiny     : {res.schedule.makespan} cyc "
          f"({res.search_stats.get('tiny_winner', '?')}, {dt:.1f} ms)")
    print(f"  valid    : {'yes' if not errs and res.schedule.complete else errs}")
    for note in res.notes:
        print("  " + Style.dim(note))
    if res.schedule.makespan < base.schedule.makespan:
        print("  " + paint("success", f"beat baseline: "
                                      f"{base.schedule.makespan} -> {res.schedule.makespan}"))
    elif res.schedule.makespan == base.schedule.makespan:
        print("  " + Style.dim("tied with baseline — no regression"))
    else:
        print("  " + paint("warning", "WORSE than baseline — please report this"))
    print()
    print(Style.dim("  next:  compare   doctor   bounds"))


def cmd_play(session: Session, arg: str) -> None:
    base, orc, met = session.results()
    dag, model = session.dag_obj, session.model()
    which = "oracle"
    for p in arg.split():
        if p in ("baseline", "base", "b"):
            which = "baseline"
        elif p in ("oracle", "orc", "o", "ai"):
            which = "oracle"
        elif p.startswith("--delay="):
            try:
                session.delay = float(p.split("=", 1)[1])
            except ValueError:
                pass
    sched = base.schedule if which == "baseline" else orc.schedule
    who = "BASELINE" if which == "baseline" else "ORACLE"
    hl = {i: render.CRIT_CODE for i in schedule_view.critical_set(dag, met)}
    items = schedule_view.schedule_items(sched, dag, model)
    stepping = session.delay is None and sys.stdin.isatty()
    print(rule(f"cycle by cycle · {who.lower()}"))
    print("  " + _header(session))
    print("  " + op_legend())
    if stepping:
        print(Style.dim("  Enter — next cycle · q + Enter — stop"))
    print()
    issued = 0
    for item in items:
        if item[0] == "bundle":
            issued += len(item[2])
        _out(schedule_view.render_item(dag, model, sched, item, hl))
        print(Style.dim(f"       issued {issued}/{len(dag)} instr., makespan {sched.makespan}"))
        if not _pause(session):
            print(Style.dim("  … stopped"))
            return
    print()
    _out(schedule_view.render_verdict(base, orc, met))


def cmd_explain(session: Session, arg: str) -> None:
    base, orc, met = session.results()
    dag, model = session.dag_obj, session.model()
    if not arg.strip():
        d = schedule_view.find_divergence(base.schedule, orc.schedule, dag)
        t = d.cycle if d.cycle is not None else 0
        print(Style.dim(f"  no cycle specified — using first divergence (cycle {t})"))
    else:
        try:
            t = int(arg.split()[0])
        except ValueError:
            print(paint("error", "cycle number required: /explain <cycle>"))
            return False
    print(rule(f"cycle {t}"))
    _out(schedule_view.render_explain(t, base, orc, dag, model))


def cmd_path(session: Session, arg: str) -> None:
    base, orc, met = session.results()
    print(rule("critical path · " + session.dag_obj.title))
    print("  " + _header(session))
    print()
    _out(["  " + l for l in schedule_view.render_dag_path(session.dag_obj, session.model(), met)])


def cmd_bounds(session: Session, arg: str) -> None:
    base, orc, met = session.results()
    print(rule("lower bounds"))
    _out(schedule_view.render_bounds(session.dag_obj, session.model(), met))


def cmd_model(session: Session, arg: str) -> None:
    arg = arg.strip().lower()
    if arg:
        match = next((n for n in PROFILES if n.lower().startswith(arg) or arg in n.lower()), None)
        match = match or {"measured": "e2k-v6-measured", "naive": "naive_homogeneous",
                          "homogeneous": "naive_homogeneous", "m": "e2k-v6-measured"}.get(arg)
        if not match:
            print(paint("error", f"unknown profile {arg!r}; available: {', '.join(PROFILES)}"))
            return False
        session.profile = match
        print(paint("success", f"switched profile to {match}"))
    model = session.model()
    print(rule("machine · " + model.name))
    _out(tables.render_model_view(model))
    print()
    others = [n for n in PROFILES if n != session.profile]
    print(Style.dim(f"  Switch: /model {others[0] if others else '<profile>'}"))


def cmd_scenarios(session: Session, arg: str) -> None:
    print(rule("scenarios"))
    _out(tables.render_scenarios(session.scenario))


# Upper cap for `random N` to prevent OOM on huge synthetic graphs.
MAX_RANDOM_N = 5000


def cmd_random(session: Session, arg: str) -> bool | None:
    parts = arg.split()
    n = 16
    seed = _random.randint(1, 10**6)
    if parts:
        try:
            n = int(parts[0])
        except ValueError:
            print(paint("error", f"instruction count must be an integer, not {parts[0]!r}"))
            return False
        if n < 3:
            print(paint("error", f"cannot build a graph with {n} instructions: need 3 or more"))
            return False
        if n > MAX_RANDOM_N:
            print(paint("error",
                        f"{n} instructions is too large for a single block "
                        f"(limit {MAX_RANDOM_N})"))
            _out(wrap("Scheduling memory grows superlinearly and hits OOM at "
                      "this size (--budget does not cap memory). Real lcc "
                      "blocks are hundreds of ops — see real_candidates_100_400/.",
                      render.W, "  "))
            return False
    if len(parts) > 1:
        try:
            seed = int(parts[1])
        except ValueError:
            pass
    dag = random_dag(seed, n=n, key=f"rand{seed}",
                     title=f"Random graph (seed={seed}, {n} instr.)")
    session.set_dag(dag, f"rand{seed}")
    print(paint("success", f"generated random graph: {n} instructions, seed={seed}"))
    cmd_run(session, "")


def cmd_all(session: Session, arg: str) -> None:
    print(rule("summary"))
    _out(wrap(
        "Each scenario is scheduled twice: greedy heuristic (baseline) and exact "
        "search (oracle). The 'gain' column shows the gap to the theoretical ceiling.",
        render.W, "  "))
    print()
    rows = []
    for key, dag in SCENARIOS.items():
        model = get_profile(session.args.profile or dag.profile or DEFAULT_PROFILE)
        if session.width:
            model = model.with_width(session.width)
        t0 = time.monotonic()
        base = GreedyListScheduler().schedule(dag, model)
        orc = OracleScheduler(
            budget_s=session.args.budget, portfolio_s=session.args.portfolio,
        ).schedule(dag, model)
        met = compute_metrics(dag, model)
        rows.append({
            "key": key, "n": len(dag), "model_name": model.name, "lb": met.lower_bound,
            "base_ms": base.schedule.makespan, "oracle_ms": orc.schedule.makespan,
            "gap": base.schedule.makespan - orc.schedule.makespan,
            "optimal": orc.optimal, "seconds": time.monotonic() - t0,
        })
    _out(tables.render_summary(rows))


def cmd_sweep(session: Session, arg: str) -> None:
    opts = _parse_opts(arg, {"seeds": 30, "sizes": "14,18,22", "widths": "6,4,3",
                             "time-limit": 180.0})
    seeds = int(opts["seeds"])
    sizes = [int(x) for x in str(opts["sizes"]).split(",")]
    widths = [int(x) for x in str(opts["widths"]).split(",")]
    time_limit = float(opts["time-limit"])

    print(rule("sweep"))
    _out(wrap(
        f"{seeds} random graphs x sizes {sizes} x machine profiles. Counts how "
        f"often exact search beats the greedy heuristic (proven optima only).",
        render.W, "  "))
    print()
    configs = [
        get_profile(p).with_width(w) if w != get_profile(p).width else get_profile(p)
        for p in PROFILES for w in widths
    ]
    per_config = time_limit / len(configs)
    budget = min(session.args.budget, 3.0)
    rows = []
    stopped = False
    for model in configs:
        n_proven = n_gap = 0
        gaps: list[float] = []
        worst = 0
        deadline = time.monotonic() + per_config
        for seed in range(1, seeds + 1):
            for n in sizes:
                dag = random_dag(seed, n=n)
                base = GreedyListScheduler().schedule(dag, model)
                orc = OracleScheduler(budget_s=budget, portfolio_s=0.5).schedule(dag, model)
                if not orc.optimal:
                    continue
                n_proven += 1
                gap = base.schedule.makespan - orc.schedule.makespan
                if gap > 0:
                    n_gap += 1
                    gaps.append(100.0 * gap / base.schedule.makespan)
                    worst = max(worst, gap)
            if time.monotonic() > deadline:
                stopped = True
                break
        rows.append({
            "model_name": model.name, "width": model.width,
            "uniform": model.uniform_channels(), "n_gap": n_gap, "n_proven": n_proven,
            "avg_gap": (sum(gaps) / len(gaps)) if gaps else None, "worst": worst,
        })
    _out(tables.render_sweep(rows, stopped))


def cmd_selfcheck(session: Session, arg: str) -> None:
    opts = _parse_opts(arg, {"seeds": 20, "time-limit": 60.0})
    print(rule("selfcheck"))
    result = run_selfcheck(
        seeds=int(opts["seeds"]), sizes=(5, 6, 7, 8),
        time_limit=float(opts["time-limit"]),
        on_failure=lambda tag, probs: print(Style.red(f"  - {tag}")),
    )
    _out(tables.render_selfcheck(result))


def cmd_docs(session: Session, arg: str) -> None:
    print(rule("overview"))
    body = [
        "Three panes: CORE evaluates graphs, LAB schedules cycles, AGENT explains.",
        "",
        "baseline — greedy heuristic, like a compiler list scheduler.",
        "oracle   — exact search, theoretical ceiling, not AI.",
        "gap      — cycles recoverable by changing issue order.",
        "",
        "division runs only on ,5; store on ,2 and ,5; multiply on four channels.",
        "",
        "try first:  sum 8   then  compare   then  doctor",
        "panes: /mode work  ·  /mode lab  ·  /mode mind",
    ]
    for line in body:
        print("  " + (Style.dim(line) if line else ""))


def cmd_agent(session: Session, arg: str) -> None:
    base, orc, met = session.results()
    gap = base.schedule.makespan - orc.schedule.makespan
    body = [
        "Where a learned scheduler plugs in.",
        "",
        "All schedulers implement the same Scheduler protocol (vliw/core/api.py):",
        '  baseline  → kind="heuristic"   (greedy list scheduler)',
        '  oracle    → kind="exact"       (exact search, ceiling)',
        '  learned   → kind="learned"     (trained model — experimental)',
        "",
        "The integration point is vliw/learned/scheduler.py: any model",
        "implementing schedule(dag, model) -> SchedulingResult works",
        "directly with the CLI and TUI with zero UI changes.",
        "",
        f"On the current scenario ({session.scenario}), the oracle beats the",
        f"greedy heuristic by {render.cycles(gap)} — that is the headroom",
        "available for a learned scheduler to recover.",
    ]
    _out(panel(body, title="MODEL PLUG-IN POINT", color="accent2"))


def cmd_hard(session: Session, arg: str) -> None:
    """Measure whether a graph has a gap over greedy — and harvest hard graphs."""
    import shlex

    from .core.hardness import harvest_one, measure

    toks = shlex.split(arg or "")
    n_survey = n_harvest = 0
    n_jobs = 0
    out_path = Path("hard.jsonl")
    for i, t in enumerate(toks):
        if t == "--survey":
            n_survey = int(toks[i + 1]) if i + 1 < len(toks) and toks[i + 1].isdigit() else 200
        elif t.startswith("--survey="):
            n_survey = int(t.split("=", 1)[1] or 200)
        elif t == "--harvest":
            n_harvest = int(toks[i + 1]) if i + 1 < len(toks) and toks[i + 1].isdigit() else 50
        elif t.startswith("--harvest="):
            n_harvest = int(t.split("=", 1)[1] or 50)
        elif t == "--out":
            out_path = Path(toks[i + 1]) if i + 1 < len(toks) else out_path
        elif t.startswith("--out="):
            out_path = Path(t.split("=", 1)[1])
        elif t == "--jobs":
            n_jobs = int(toks[i + 1]) if i + 1 < len(toks) and toks[i + 1].isdigit() else 0
        elif t.startswith("--jobs="):
            n_jobs = int(t.split("=", 1)[1] or 0)

    machine = session.model()

    if not n_survey and not n_harvest:
        h = measure(session.dag_obj, machine)
        print(rule(f"hardness · {session.scenario}"))
        print()
        print(f"  greedy heuristic   {h.baseline:>4} cyc")
        print(f"  optimum            {h.optimum:>4} cyc"
              + Style.dim("   (proven)" if h.proven else "   (NOT proven within budget)"))
        print()
        if not h.proven:
            print("  " + paint("warning",
                               "optimum unproven — cannot classify graph as hard or easy"))
        elif h.hard:
            print("  " + paint("success",
                               f"GAP {h.gap} cyc — real headroom for a smarter scheduler"))
        else:
            print("  " + paint("warning",
                               "NO GAP — greedy heuristic is already optimal on this graph"))
        print()
        print("  " + Style.dim("hard share among random graphs: /hard --survey 200"))
        print("  " + Style.dim("harvest hard graphs to file:    /hard --harvest 50"))
        return None

    from tools.vliw_gen import PRESSURE_WEIGHTS, SHAPES, gen_graph

    def _dag(instrs):
        from .core.dag import DAG as _DAG, Instr as _I
        return _DAG("hard", "", "",
                    [_I(x.id, f"n{x.id}", x.op, x.preds, f"n{x.id}") for x in instrs])

    if n_survey:
        print(rule(f"hardness survey · {n_survey} graphs per mix"))
        print()
        for label, weights in (("default weights", None),
                               ("channel ,5 pressure", PRESSURE_WEIGHTS)):
            rnd = _random.Random(20260831)
            hard = shown = 0
            for k in range(n_survey):
                dag = _dag(gen_graph(rnd, rnd.randint(16, 24),
                                     rnd.choice(SHAPES), weights))
                h = measure(dag, machine, budget_s=6.0)
                if not h.proven:
                    continue
                shown += 1
                hard += 1 if h.hard else 0
                if k % 25 == 0 and sys.stdout.isatty():
                    print(f"  {label:22} {k + 1:>4}/{n_survey}…", end="\r")
                    sys.stdout.flush()
            pct = 100 * hard / max(shown, 1)
            paint_fn = paint("success", f"{pct:5.1f}%") if pct >= 5 else Style.dim(f"{pct:5.1f}%")
            print(f"  {label:22} hard    {hard:>4}/{shown:<4} {paint_fn}      ")
        print()
        print("  " + Style.dim(
            "hardness comes from narrow-port contention, not graph size alone: "
            "DIV only runs on ,5"))
        return None

    print(rule(f"harvesting hard graphs · target {n_harvest}"))
    print()
    from training.encode import encode_completion, encode_prompt

    N_LO, N_HI = 16, 24
    profile = getattr(machine, "name", "e2k-v6-measured")
    kept, seen, t0 = [], 0, time.monotonic()
    limit = n_harvest * 400
    tasks = ((seed, N_LO, N_HI, profile) for seed in itertools.count(20260831))

    def _note(gap: int) -> None:
        if sys.stdout.isatty():
            print(f"  found {len(kept):>4}/{n_harvest}   scanned {seen}   "
                  f"gap {gap} cyc      ", end="\r")
            sys.stdout.flush()

    if n_jobs > 1:
        import multiprocessing as mp

        with mp.Pool(n_jobs) as pool:
            for row in pool.imap_unordered(harvest_one, tasks, chunksize=4):
                seen += 1
                if row is not None:
                    kept.append(row)
                    _note(row["meta"]["gap"])
                if len(kept) >= n_harvest or seen >= limit:
                    pool.terminate()
                    break
    else:
        for task in tasks:
            if len(kept) >= n_harvest or seen >= limit:
                break
            seen += 1
            row = harvest_one(task)
            if row is not None:
                kept.append(row)
                _note(row["meta"]["gap"])

    with out_path.open("w", encoding="utf-8") as f:
        for row in kept:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    dt = time.monotonic() - t0
    print(f"  found {len(kept)}/{n_harvest}, scanned {seen} "
          f"({100 * len(kept) / max(seen, 1):.1f}% kept) in {dt:.0f} s      ")
    print()
    print("  " + paint("success", f"saved to {out_path}"))
    if len(kept) < n_harvest:
        print("  " + paint("warning",
                           "target not reached: raise scan limit or relax gap threshold"))
    return None


def cmd_isa(session: Session, arg: str) -> None:
    """ISA reference: channels, latencies, peak issue rates, and provenance."""
    import shlex

    from .core.isa import collect
    from .ui import isa_view

    toks = shlex.split(arg or "")
    out_path = None
    for i, t in enumerate(toks):
        if t == "--out" and i + 1 < len(toks):
            out_path = Path(toks[i + 1])
        elif t.startswith("--out="):
            out_path = Path(t.split("=", 1)[1])

    machine = session.model()
    rows = collect(machine)

    if out_path is None:
        print(rule("ISA reference"))
        _out(isa_view.render_terminal(rows))
        return None

    from . import VERSION_LABEL

    text = isa_view.render_markdown(rows, machine, VERSION_LABEL)
    out_path.write_text(text, encoding="utf-8")
    print(rule("ISA reference"))
    print()
    print("  " + paint("success", f"written to {out_path}")
          + Style.dim(f"   {len(text.splitlines())} lines, "
                      f"{len(rows)} classes, "
                      f"{sum(len(r.mnemonics) for r in rows)} mnemonics"))
    return None


def _group_title(cmd: dict) -> str:
    gid = cmd.get("group", "session")
    return next((t for g, t in GROUPS if g == gid), gid)


def cmd_help(session: Session, arg: str) -> None:
    """Help: without an argument lists all commands by group; with one explains it."""
    q = arg.strip().lstrip("/").lower()
    if q and q != "help":
        return _help_one(q)
    print(rule("commands"))
    _hint()
    for gid, title in GROUPS:
        members = [c for c in COMMANDS if c.get("group") == gid]
        if not members:
            continue
        print()
        print(rule(title))
        rows = [[paint("accent", "/" + c["name"]), c["arg"], c["help"]]
                for c in members]
        for l in render.table(["command", "arguments", "description"], rows,
                              aligns="<<<"):
            print("  " + l)
        print(Style.dim(
            "  details: /help " + members[0]["name"]
            + (" … /help " + members[-1]["name"] if len(members) > 1 else "")))
    print()
    print(Style.dim("  inside REPL with '/', outside without: python -m vliw run slotclash"))
    print(Style.dim("  core: sum 8  ·  agent: plain question  ·  /exit"))


def _help_one(name: str) -> None:
    """Detailed help for a single command: signature, docstring, sibling commands."""
    import inspect

    cmd = resolve(name)
    if cmd is None:
        msg = paint("error", f"no such command /{name}.")
        hints = suggest(name)
        if hints:
            msg += Style.dim("  Did you mean: ") + ", ".join(
                paint("accent", "/" + h) for h in hints) + Style.dim("?")
        else:
            msg += Style.dim("  /help — list all commands.")
        print(msg)
        return False
    sig = ("/" + cmd["name"] + " " + cmd["arg"]).strip()
    print(rule(f"{sig}  ·  {_group_title(cmd)}"))
    doc = inspect.getdoc(cmd["fn"])
    if doc:
        print()
        for line in doc.splitlines():
            print("  " + line)
    else:
        print()
        print("  " + cmd["help"])
    peers = [c for c in COMMANDS
             if c.get("group") == cmd.get("group") and c is not cmd]
    if peers:
        print()
        print(Style.dim("  related: ") + Style.dim("   ".join(
            paint("accent", "/" + p["name"]) for p in peers)))
    return True


def cmd_doctor(session: Session, arg: str) -> None:
    """Diagnostics: where cycles are lost and what can be fixed.

    `/doctor` — summary, `/doctor N` — details for finding N,
    `/doctor oracle` — same diagnostics for the exact oracle schedule.
    """
    which = "baseline"
    detail = 0
    for tok in arg.split():
        t = tok.lower()
        if t in ("oracle", "orc", "o"):
            which = "oracle"
        elif t in ("baseline", "base", "b"):
            which = "baseline"
        elif t.isdigit():
            detail = int(t)

    base, orc, met = session.results()
    dag, model = session.dag_obj, session.model()
    res = base if which == "baseline" else orc
    d = doctor.diagnose(dag, model, res.schedule, met)
    label = "baseline" if which == "baseline" else "oracle"

    if detail:
        print(rule(f"FINDING #{detail} — {label}"))
        _out(diagnostics.render_detail(d, detail))
        return
    print(rule(f"doctor · {label} · {session.scenario}"))
    print()
    _out(diagnostics.render_diagnosis(d, label))


def _load_parsed(session: Session, parsed, label: str) -> bool:
    """Convert parsed `.s` into a DAG, check compiler schedule, and print report."""
    if not parsed.ops:
        print(paint("error", "no operations found — is this valid lcc .s output?"))
        return False

    model = session.model()
    dag = asm_parser.build_dag(parsed, key=f"asm:{label}", title=label)
    session.set_dag(dag, f"asm:{label}")
    if label == "buffer":
        session.code_run_text = session.code_text

    cs, comp_problem = asm_parser.compiler_schedule_checked(parsed, dag, model)
    comp_cycles = cs.makespan if cs else None
    base, orc, met = session.results()

    print(rule("loaded · " + label))
    problems = list(parsed.problems) + asm_parser.lint(parsed, model)
    _out(diagnostics.render_parsed(parsed, dag, comp_cycles,
                                   orc.schedule.makespan, met.lower_bound,
                                   comp_problem, problems))
    session.compiler_sched = cs if comp_cycles is not None else None
    return True


def cmd_load(session: Session, arg: str) -> None:
    """Load a real `.s` file from lcc, parse it, and compare against the oracle."""
    path = arg.strip()
    if not path:
        print(paint("error", "specify a file: /load examples/probe.s"))
        return False
    try:
        parsed = asm_parser.parse_file(path)
    except OSError as e:
        print(paint("error", f"cannot open file: {e}"))
        return False
    return _load_parsed(session, parsed, Path(path).name)


def cmd_code(session: Session, arg: str) -> None:
    """Source buffer: write e2k assembly directly in NEX CLI and run it.

    `/code` — buffer status, `/code run` — schedule the buffer as `.s`,
    `/code show` — print with line numbers, `/code clear` — clear buffer,
    `/code load <file.s>` — load file into buffer,
    `/code save <file.s>` — save buffer to file.
    """
    sub, _, rest = arg.strip().partition(" ")
    sub = sub.lower()
    rest = rest.strip()

    if sub in ("run", "go"):
        if not session.code_text.strip():
            print(paint("error", "CODE buffer is empty: open the editor (CODE mode) "
                                 "or run /code load <file.s>"))
            return False
        try:
            parsed = asm_parser.parse_asm(session.code_text, source="<buffer>")
        except Exception as e:
            print(paint("error", f"failed to parse: {e}"))
            return False
        return _load_parsed(session, parsed, "buffer")

    if sub == "show":
        if not session.code_text.strip():
            print(Style.dim("  CODE buffer is empty"))
            return True
        print(rule(f"buffer · {len(session.code_text.splitlines())} lines"))
        for i, line in enumerate(session.code_text.splitlines(), 1):
            print(f"  {i:>3}  {line}")
        return True

    if sub == "clear":
        session.code_text = ""
        print(paint("success", "CODE buffer cleared"))
        return True

    if sub == "load":
        if not rest:
            print(paint("error", "specify a file: /code load examples/probe.s"))
            return False
        try:
            session.code_text = Path(rest).read_text(encoding="utf-8",
                                                      errors="replace")
        except OSError as e:
            print(paint("error", f"cannot open file: {e}"))
            return False
        session.code_path = rest
        n = len(session.code_text.splitlines())
        print(paint("success", f"loaded into CODE buffer: {rest} · {n} lines"
                    + Style.dim("   run: /code run")))
        return True

    if sub == "save":
        if not session.code_text.strip():
            print(paint("error", "buffer is empty — nothing to save"))
            return False
        if not rest:
            print(paint("error", "specify a file: /code save my.s"))
            return False
        try:
            Path(rest).write_text(session.code_text, encoding="utf-8")
        except OSError as e:
            print(paint("error", f"cannot write file: {e}"))
            return False
        session.code_path = rest
        print(paint("success", f"CODE buffer → {rest}"
                    + Style.dim("   Ctrl+S will save to this path")))
        return True

    n = len(session.code_text.splitlines()) if session.code_text.strip() else 0
    print(rule("code"))
    if n:
        unit = "line" if n == 1 else "lines"
        print(f"  buffer: {n} {unit}"
              + Style.dim("   run: /code run   show: /code show"))
    else:
        print(Style.dim("  buffer is empty. In full-screen mode open CODE "
                        "(key 4) for the editor."))
        print(Style.dim("  Or: /code load <file.s> — load an existing .s "
                        "into the buffer."))
    return True


def plural_ru(n: int, one: str, few: str, many: str) -> str:
    if 11 <= n % 100 <= 14:
        return many
    return {1: one, 2: few, 3: few, 4: few}.get(n % 10, many)


def cmd_analyze(session: Session, arg: str) -> None:
    """Typed structured block analysis: verdict, root cause, plan (no chat)."""
    from .agent import analyst

    print(rule("analysis · " + session.scenario))
    print(Style.dim("  structured analysis, no dialogue"))
    print()
    a = analyst.analyze(session)
    _out(analyst_view.render_analysis(a, session.scenario))


def cmd_mode(session: Session, arg: str) -> None:
    """Switch active pane focus: CORE / LAB / AGENT."""
    from .ui import panes

    a = arg.strip().lower()
    if a:
        dest = panes.resolve_focus(a)
        if dest is None:
            print(paint("error", f"unknown pane {a!r}; available: work, lab, mind"))
            return False
        session.focus = dest
        session.mode = "chat" if dest == "mind" else "explore"
        print(paint("success", f"pane: {panes.META[dest]['title'].lower()}"))
    print(rule("panes"))
    current = getattr(session, "focus", "lab")
    for name in panes.PANES:
        meta = panes.META[name]
        mark = paint(meta["role"], "*") if current == name else " "
        print(f"  {mark} {paint(meta['role'], meta['title']):<10} "
              + Style.dim(meta["sub"]))
    print()
    print(Style.dim("  /mode work  ·  /mode lab  ·  /mode mind"))


def cmd_ask(session: Session, arg: str) -> None:
    """Ask the agent a question (in AGENT mode you can just type plain text)."""
    q = arg.strip()
    if not q:
        _out(agent_view.render_intro())
        return
    agent_view.stream_turn(session.agent(), q)


def _ai_save(updates: dict[str, str | None]) -> None:
    """Apply API settings for this session only (in-memory, nothing written to disk)."""
    for k, v in updates.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v


def _ai_status() -> None:
    """Display language model status (shared finale of `/ai` and `/key`)."""
    from .agent import status

    print(rule("LANGUAGE MODEL"))
    ok, detail = status()
    _out(agent_view.render_status(ok, detail))


def cmd_ai(session: Session, arg: str) -> None:
    """Show language model status, or configure a provider in one command.

    Forms (applied immediately for this session only, never written to disk):
      /ai                                        status
      /ai deepseek                               switch provider
      /ai deepseek key=sk-...                    switch + set key
      /ai deepseek key=sk-... model=deepseek-chat + pin model
      /ai grok|anthropic|glm|muse|openrouter key=... model=...
      /ai local-server url=http://localhost:11434/v1 model=...
      /ai custom url=... model=... key=...       legacy custom server
      /ai gigachat key=<id>:<secret>             Sber OAuth pair
      /ai yandex folder=... key=...              Yandex Cloud
    To set a key without switching providers, use `/key`.
    """
    from .agent import llm
    from .agent import envfile

    toks = arg.split()
    if not toks:
        _ai_status()
        return

    prov = llm.normalize_provider(toks[0])
    if prov is None or prov == "local":
        print(paint("error", f"unknown provider {toks[0]!r}; "
                             f"available: {', '.join(p for p in llm.PROVIDERS if p != 'local')}"))
        return False
    kv: dict[str, str] = {}
    for m in re.finditer(r"([A-Za-z_]+)\s*=\s*(\S+)", arg):
        kv[m.group(1).lower()] = m.group(2)

    try:
        updates = llm.provider_updates(prov, kv)
    except llm.LLMError as e:
        print(paint("error", str(e)))
        return False

    _ai_save(updates)
    _ai_status()


def _key_guide(prov: str) -> list[str]:
    """Short guide explaining what an API key is and where to get one."""
    from .agent import llm

    lines = ["An API key is a token from your provider granting access to the LLM.",
             "Without one, the agent still answers offline from computed numbers."]
    hint = llm.key_source_hint(prov)
    if hint:
        lines.append("  " + hint)
    if prov == "gigachat":
        lines.append("  set:        /key <client_id> <client_secret>")
        lines.append("  all-in-one: /ai gigachat key=<id>:<secret>")
    else:
        lines.append("  set:        /key <key>")
        lines.append(f"  all-in-one: /ai {prov} key=...")
    return lines


def cmd_key(session: Session, arg: str) -> None:
    """Set the API key for the current provider: /key <key> (session-only)."""
    from .agent import llm
    from .agent import envfile

    toks = arg.split()
    prov = llm.provider()
    if prov == "local":
        print(paint("error", "local mode is active (on-device weights) — no key needed. "
                             "Switch first with /ai <provider>."))
        return False
    try:
        updates = llm.key_updates(prov, toks)
    except llm.LLMError:
        _out([Style.dim(l) for l in _key_guide(prov)])
        return False
    if prov == "gigachat":
        shown = f"id {envfile.mask(toks[0])}"
    else:
        shown = f"{next(iter(updates))} {envfile.mask(toks[0])}"
    if prov == "yandex" and not llm.setting("YANDEX_FOLDER_ID", ""):
        print(paint("warning", "key saved, but folder ID is still required: "
                               "/ai yandex folder=..."))

    _ai_save(updates)
    print(paint("success", f"accepted for this session: {shown} (not saved to disk)"))
    _ai_status()


def cmd_status(session: Session, arg: str) -> None:
    print(rule("SESSION CONTEXT"))
    _out(context.render_status(session))
    print()
    print("  " + logo.status_line(
        getattr(session, "focus", "lab"), session.scenario, session.model().name))


def cmd_theme(session: Session, arg: str) -> None:
    name = arg.strip()
    available = theme.list_themes()
    if name:
        if name not in available:
            print(paint("error", f"unknown theme {name!r}; available: "
                                 f"{', '.join(available)}"))
            return False
        render.apply_theme(name)
        print(paint("success", f"theme switched to {name}"))
    print(rule("themes"))
    for t in available:
        th = theme.load_theme(t)
        mark = paint("work", "*") if th.name == render.THEME.name else " "
        print(f"  {mark} {paint('title', t)}")
        _out(wrap(Style.dim(th.description), render.W, "      "))
    print()
    print(Style.dim("  Theme files: vliw/ui/themes/*.json  ·  switch: /theme <name>"))
    print("  " + op_legend())


def _hint() -> None:
    print(Style.dim("  core: sum 8   ·   lab: /run /compare /doctor"))
    print(Style.dim("  agent: plain-English question   ·   /mode work|lab|mind"))


def cmd_work(session: Session, arg: str) -> None:
    """Interpreter reference: expressions, kernels, and commands."""
    from .ui import interp_view

    _out(interp_view.render_welcome())
    print()
    rows = []
    for name, default, hint in kernel_help():
        rows.append([paint("work", name), str(default), hint])
    for l in render.table(["kernel", "n", "what it computes"], rows, aligns="><<"):
        print("  " + l)


def cmd_clear(session: Session, arg: str) -> None:
    """Clear the screen and return to the mode picker."""
    if Style.enabled:
        sys.stdout.write("\033[3J\033[2J\033[H")
        sys.stdout.flush()
    print_logo()
    if not IN_REPL or not sys.stdin.isatty():
        for line in launcher.render_choice(selected=-1):
            print(line)
        return
    chosen = launcher.prompt_plain()
    if not chosen:
        return
    _apply_mode(session, chosen)


def cmd_asm(session: Session, arg: str) -> None:
    base, orc, met = session.results()
    dag, model = session.dag_obj, session.model()
    which = "baseline" if arg.split()[:1] == ["baseline"] or arg.strip() in ("base", "b") else "oracle"
    sched = base.schedule if which == "baseline" else orc.schedule
    print(rule(f"WIDE INSTRUCTIONS ({which}) — lcc .s format"))
    print("  " + _header(session))
    print("  " + op_legend())
    print()
    _out(schedule_view.render_asm(sched, dag, model))
    print()
    _out(wrap(Style.dim(
        "Each { … } is one e2k wide instruction: everything inside executes "
        "in parallel, `,N` is the channel (port), and `nop` is a stall. "
        "The machine model was measured from this exact `.s` format (see /probe)."),
        render.W, "  "))


def cmd_probe(session: Session, arg: str) -> None:
    body = [
        "How the machine model was measured — and why v1 was wrong.",
        "",
        "FIRST ATTEMPT (wrong). Compiled a .c file with four divisions and four",
        "multiplications, read { … } from lcc -O3 -S. All four muls landed on",
        "channel ,0 — misread as 'one multiplier, 8-cycle occupancy'. Four ops",
        "were simply too few for lcc to spread across channels. A listing shows",
        "what the compiler CHOSE, not what the hardware CAN do.",
        "",
        "HOW WE MEASURE NOW — three independent probes:",
        "  1. Port matrix via the ASSEMBLER: assemble a tiny .s placing each op",
        "     in each channel. Illegal slots fail with \"cannot be encoded in ALC2\".",
        "  2. Latency via DEPENDENT CHAINS: each op waits on the previous one,",
        "     forcing lcc to space bundles by the exact latency.",
        "  3. Issue rate via INDEPENDENT STREAMS of 8–16 ops.",
        "",
        "Measured results:",
        "  • sdivs — channel ,5 ONLY (all other five rejected by assembler);",
        "    latency 11, occupancy 2 cycles;",
        "  • muls/muld — channels ,0 ,1 ,3 ,4 (four fit in one wide instruction);",
        "    latency 4, fully pipelined (1/cycle);",
        "  • ldw/ldd — channels ,0 ,2 ,3 ,5, latency 5;",
        "  • stw/std — two channels only: ,2 and ,5;",
        "  • adds/subs/ands/shls — all six channels.",
        "",
        "Takeaway: e2k ports are genuinely asymmetric, but there is only ONE",
        "exclusive unit — the divider. Multiplication is not a bottleneck.",
    ]
    _out(panel(body, title="MODEL MEASUREMENT & CORRECTIONS", color="border"))
    print()
    print(Style.dim("  Full matrix: /model.  Disproven v1 profile for comparison: "
                    "/model e2k-v6-firstprobe"))


# --------------------------------------------------------------------------
# Project tooling wrappers (`tools/*.py`)
# --------------------------------------------------------------------------


def _run_tool(main_fn, toks: list[str]) -> bool:
    """Invoke a `tools/*.py` main(argv) in-process with clean error messages."""
    import json

    try:
        return main_fn(toks) in (0, None)
    except json.JSONDecodeError as exc:
        print(paint("error", f"file is not valid jsonl (line {exc.lineno}): "
                             f"expected one JSON object per line"))
        return False
    except FileNotFoundError as exc:
        print(paint("error", f"cannot open file: {exc.filename}"))
        return False
    except (KeyError, ValueError) as exc:
        print(paint("error", f"file parsed, but data schema did not match: {exc}"))
        return False


def cmd_verify(session: Session, arg: str) -> None:
    """Re-probe the e2k port matrix live with the assembler (`tools/probe_matrix.py`)."""
    from tools import probe_matrix

    print(rule("verify · live assembler port matrix"))
    if not _run_tool(probe_matrix.main, arg.split()):
        return False


def cmd_validate(session: Session, arg: str) -> None:
    """Run jsonl records through real `Schedule.validate()` (`tools/validate_jsonl.py`)."""
    from tools import validate_jsonl

    toks = arg.split()
    if not any(not t.startswith("--") for t in toks):
        print(paint("error", "specify file(s): /validate dataset.jsonl"))
        return False
    print(rule("validate · " + " ".join(t for t in toks if not t.startswith("--"))))
    if not _run_tool(validate_jsonl.main, toks):
        return False


def cmd_report(session: Session, arg: str) -> None:
    """Summarize benchmark dumps into a comparison table (`tools/report_runs.py`)."""
    from tools import report_runs

    print(rule("report · run summary"))
    if not _run_tool(report_runs.main, arg.split()):
        return False


def _as_float(text: str) -> float:
    """Parse float or return 0.0 without crashing; validated separately below."""
    try:
        return float(text)
    except (TypeError, ValueError):
        return 0.0


@dataclass
class _LearnedArgs:
    """Parsed arguments for `/learned` (pure helper for unit testing)."""

    name: str | None = None
    bench: int = 0
    best_of: int = 0
    temperature: float = 0.0
    seed: int = 1
    constrained: bool = False
    cab: bool = False
    data: str = "eval_wide.jsonl"
    bad_value: tuple[str, str] | None = None
    raw: bool = False
    status: bool = False
    repair: bool = True


def _parse_learned(toks: list[str]) -> _LearnedArgs:
    """Parse `--flag N` and `--flag=N` for `/learned`."""
    a = _LearnedArgs()
    a.raw = "--raw" in toks
    a.status = "--status" in toks
    a.repair = "--pure" not in toks
    flag_values: set[int] = set()
    for i, t in enumerate(toks):
        if t == "--bench":
            a.bench = int(toks[i + 1]) if i + 1 < len(toks) and toks[i + 1].isdigit() else 15
            flag_values.add(i + 1)
        elif t.startswith("--bench="):
            a.bench = int(t.split("=", 1)[1] or 15)
        elif t == "--best-of":
            a.best_of = int(toks[i + 1]) if i + 1 < len(toks) and toks[i + 1].isdigit() else 4
            flag_values.add(i + 1)
        elif t.startswith("--best-of="):
            a.best_of = int(t.split("=", 1)[1] or 4)
        elif t == "--temperature":
            a.temperature = _as_float(toks[i + 1]) if i + 1 < len(toks) else 0.0
            flag_values.add(i + 1)
        elif t.startswith("--temperature="):
            a.temperature = _as_float(t.split("=", 1)[1])
        elif t in ("--constrained", "--grammar"):
            a.constrained = True
        elif t == "--cab":
            a.cab = True
        elif t == "--data":
            if i + 1 < len(toks):
                a.data = toks[i + 1]
                flag_values.add(i + 1)
        elif t.startswith("--data="):
            a.data = t.split("=", 1)[1] or a.data
        elif t == "--seed":
            a.seed = int(toks[i + 1]) if i + 1 < len(toks) and toks[i + 1].isdigit() else 1
            flag_values.add(i + 1)
        elif t.startswith("--seed="):
            a.seed = int(t.split("=", 1)[1] or 1)
    a.name = next((t for i, t in enumerate(toks)
                   if not t.startswith("--") and not t.isdigit()
                   and i not in flag_values), None)

    for i, t in enumerate(toks):
        if t in ("--bench", "--best-of", "--seed") and i + 1 < len(toks):
            nxt = toks[i + 1]
            if not nxt.startswith("--") and not nxt.isdigit():
                a.bad_value = (t, nxt)
        if t == "--temperature" and i + 1 < len(toks):
            nxt = toks[i + 1]
            try:
                float(nxt)
            except ValueError:
                if not nxt.startswith("--"):
                    a.bad_value = (t, nxt)
    return a


def cmd_learned(session: Session, arg: str) -> None:
    """Run a trained LoRA adapter locally on the current graph (no Kaggle needed)."""
    from .learned import runtime
    from .ui import learned_view

    a = _parse_learned(arg.split())
    if a.bad_value:
        flag, value = a.bad_value
        print(paint("error", f"{flag} expects a number, got {value!r}"))
        return False
    want_raw, want_status, want_repair = a.raw, a.status, a.repair
    n_bench, best_of_n, temperature, seed = a.bench, a.best_of, a.temperature, a.seed
    name = a.name

    ready, lines = runtime.status(name)
    if want_status or not ready:
        print(rule("learned scheduler"))
        _out(learned_view.render_status(ready, lines))
        return None if want_status else False

    from .learned import LearnedScheduler

    adapter = runtime.resolve_adapter(name)
    if adapter is None:
        print(paint("error", f"adapter {name!r} not found; available: "
                             + ", ".join(a.name for a in runtime.find_adapters())))
        return False

    from .learned import LearnedScheduler as _LS

    machine = session.model()
    if n_bench:
        data = Path(a.data)
        if not data.exists():
            print(paint("error", f"eval file not found: {data}"))
            return False
        if best_of_n and temperature <= 0:
            print(paint("error",
                        "best-of only makes sense with --temperature > 0: "
                        "greedy decoding produces identical samples"))
            return False
        if temperature > 0 and not best_of_n:
            best_of_n = 1
        bo = None
        if best_of_n:
            from .learned.bench import BestOf

            bo = BestOf(n=best_of_n, temperature=temperature, seed=seed)
        gens = n_bench * max(1, best_of_n)
        print(rule(f"bench · {adapter.name} · {n_bench} samples"
                   + (f" · best-of {best_of_n} · t={temperature:g}" if bo else "")))
        print(Style.dim(f"  local run, no Kaggle. ~30 s per generation — "
                        f"est. {gens * 30 // 60} min."))
        print()
        sys.stdout.flush()
        from .learned import bench as _bench

        def _tick(k, row):
            mark = paint("success", "ok  ") if row.kind == "valid" else paint("error", "….  ")
            extra = (f"samples {row.valid_samples}/{len(row.samples)}  "
                     if row.samples else "")
            print(f"  [{k:>3}/{n_bench}] {mark} n={row.n:<3} {row.kind:<9} {extra}"
                  + Style.dim(row.first_error[:46]))
            sys.stdout.flush()

        try:
            res = _bench.run_bench(data, n_bench,
                                   _LS(adapter=adapter, repair=want_repair,
                                       constrained=a.constrained, cab=a.cab),
                                   machine, _tick, best_of=bo)
        except (RuntimeError, OSError, ImportError) as e:
            print(paint("error", f"benchmark aborted: {e}"))
            return False
        print()
        _out(learned_view.render_bench(res, adapter.name))
        return None

    dag = session.dag_obj
    print(rule(f"learned scheduler · {adapter.name} · {session.scenario}"))
    print("  " + _header(session))
    print()
    sys.stdout.flush()

    sch = LearnedScheduler(adapter=adapter, repair=want_repair,
                           constrained=a.constrained, cab=a.cab)
    if a.constrained:
        print("  " + Style.dim(
            "constrained decoding: format and channels enforced by grammar, "
            "cycles still chosen by the model"))
        print()
    if a.cab:
        print("  " + Style.dim(
            "CAB portfolio: builds multiple valid schedules from one response "
            "and selects the shortest"))
        print()
    renderer = learned_view.PlainRenderer()
    res = None
    failed = None

    sink = session.event_sink
    events = core.stream(sch, dag, machine)
    try:
        for ev in events:
            if sink is not None:
                sink(ev)
            else:
                for line in renderer.feed(ev):
                    print(line)
                    sys.stdout.flush()
            if isinstance(ev, core.Done):
                res = ev.result
            elif isinstance(ev, core.Failed):
                failed = ev.error
    except (RuntimeError, OSError, ImportError) as e:
        failed = str(e)
    finally:
        events.close()

    if res is None:
        print(paint("error",
                    f"failed to run model: {failed or 'no response'}"))
        return False
    print()
    base = orc = None
    if res.search_stats.get("valid"):
        base, orc, _ = session.results()
    _out(learned_view.render_result(res, dag, orc, base))
    if want_raw:
        print()
        _out(learned_view.render_raw(res))


def cmd_kaggle(session: Session, arg: str) -> None:
    """Push/pull/check Kaggle runs — thin wrapper over `tools/kaggle_push.sh`."""
    mode = (arg.split() or ["step0"])[0]
    script = Path(__file__).resolve().parent.parent / "tools" / "kaggle_push.sh"
    print(rule(f"kaggle · {mode}"))
    proc = subprocess.Popen([str(script), mode], stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, text=True, bufsize=1)
    for line in proc.stdout:
        print(line, end="")
    proc.wait()
    if proc.returncode != 0:
        return False


# --------------------------------------------------------------------------
# Command registry
# --------------------------------------------------------------------------

COMMANDS = [
    # --- schedule ---------------------------------------------------------
    {"group": "sched", "name": "run", "arg": "<scenario>", "help": "run scenario: oracle schedule + verdict", "fn": cmd_run},
    {"group": "sched", "name": "compare", "arg": "[scenario] [--model]", "help": "baseline vs oracle side by side", "fn": cmd_compare},
    {"group": "sched", "name": "tiny", "arg": "[scenario]", "help": "TINY AI (priority+defer+beam) vs baseline and oracle", "fn": cmd_tiny},
    {"group": "sched", "name": "play", "arg": "[base|oracle]", "help": "step through the schedule cycle by cycle", "fn": cmd_play},
    {"group": "sched", "name": "asm", "arg": "[base|oracle]", "help": "render schedule as e2k wide instructions { … }", "fn": cmd_asm},
    {"group": "sched", "name": "explain", "arg": "<cycle>", "help": "explain why these ops were issued in a given cycle", "fn": cmd_explain},
    # --- graph · diagnostics ----------------------------------------------
    {"group": "graph", "name": "path", "arg": "", "help": "dependency graph with critical path highlighted", "fn": cmd_path},
    {"group": "graph", "name": "bounds", "arg": "", "help": "two theoretical lower bounds on makespan", "fn": cmd_bounds},
    {"group": "graph", "name": "doctor", "arg": "[base|oracle]", "help": "diagnostics: where cycles are lost and why", "fn": cmd_doctor},
    {"group": "graph", "name": "analyze", "arg": "", "help": "typed structured analysis: verdict, root cause, plan", "fn": cmd_analyze},
    # --- machine model ----------------------------------------------------
    {"group": "machine", "name": "model", "arg": "[profile]", "help": "port capability matrix; switch machine profile", "fn": cmd_model},
    {"group": "machine", "name": "probe", "arg": "", "help": "how probe.c measured the e2k machine model", "fn": cmd_probe},
    {"group": "machine", "name": "isa", "arg": "[--out FILE]", "help": "ISA reference: channels, latencies, peak rate, provenance", "fn": cmd_isa},
    {"group": "machine", "name": "verify", "arg": "[--show]", "help": "re-probe the port matrix live with the e2k assembler", "fn": cmd_verify},
    # --- benchmarks -------------------------------------------------------
    {"group": "runs", "name": "scenarios", "arg": "", "help": "list built-in scenarios", "fn": cmd_scenarios},
    {"group": "runs", "name": "random", "arg": "[N] [seed]", "help": "generate a random N-instruction DAG and run it", "fn": cmd_random},
    {"group": "runs", "name": "all", "arg": "", "help": "summary table across all built-in scenarios", "fn": cmd_all},
    {"group": "runs", "name": "sweep", "arg": "[--seeds N]", "help": "batch sweep across random graphs and profiles", "fn": cmd_sweep},
    {"group": "runs", "name": "selfcheck", "arg": "[--seeds N]", "help": "verify oracle against independent exhaustive search", "fn": cmd_selfcheck},
    {"group": "runs", "name": "hard", "arg": "[--survey N] [--harvest N] [--jobs N]", "help": "check greedy-vs-oracle gap; harvest hard graphs", "fn": cmd_hard},
    # --- agent · learned --------------------------------------------------
    {"group": "agent", "name": "ask", "arg": "<question>", "help": "ask the LLM agent a question", "fn": cmd_ask},
    {"group": "agent", "name": "ai", "arg": "[provider] [key=…] [model=…]", "help": "LLM status; /ai <provider> key=… to configure in one step", "fn": cmd_ai},
    {"group": "agent", "name": "key", "arg": "<key>", "help": "set API key for this session (never stored on disk)", "fn": cmd_key},
    {"group": "agent", "name": "learned", "arg": "[--cab] [--constrained] [--bench N] [--data FILE] [--pure]", "help": "run trained LoRA model on the current graph (locally)", "fn": cmd_learned},
    {"group": "agent", "name": "agent", "arg": "", "help": "where a learned scheduler plugs in", "fn": cmd_agent},
    # --- data -------------------------------------------------------------
    {"group": "data", "name": "code", "arg": "[run|show|save|load|clear]", "help": "e2k assembly buffer: CODE editor (key 4), run, files", "fn": cmd_code},
    {"group": "data", "name": "load", "arg": "<file.s>", "help": "load a real .s file from lcc and analyze it", "fn": cmd_load},
    {"group": "data", "name": "validate", "arg": "<file.jsonl…>", "help": "validate jsonl schedules via Schedule.validate()", "fn": cmd_validate},
    {"group": "data", "name": "report", "arg": "[--dir …]", "help": "aggregate run dumps into a delta comparison table", "fn": cmd_report},
    {"group": "data", "name": "kaggle", "arg": "[step0|run1|all|pull|status]", "help": "push/pull/check Kaggle training runs", "fn": cmd_kaggle},
    # --- session ----------------------------------------------------------
    {"group": "session", "name": "status", "arg": "", "help": "session context: scenario, machine, results", "fn": cmd_status},
    {"group": "session", "name": "theme", "arg": "[name]", "help": "list or switch color themes", "fn": cmd_theme},
    {"group": "session", "name": "work", "arg": "", "help": "interpreter kernels and expression syntax", "fn": cmd_work},
    {"group": "session", "name": "docs", "arg": "", "help": "brief overview of NEX CLI", "fn": cmd_docs},
    {"group": "session", "name": "mode", "arg": "[work|lab|mind]", "help": "switch pane focus: CORE / LAB / AGENT", "fn": cmd_mode},
    {"group": "session", "name": "clear", "arg": "", "help": "clear screen and return to mode picker", "fn": cmd_clear},
    {"group": "session", "name": "help", "arg": "", "help": "list commands; 'help <command>' for details", "fn": cmd_help},
]

#: Unified group order shared by help and the slash palette.
GROUPS = slash.GROUPS

_ALIASES = {"ls": "scenarios", "cmp": "compare", "r": "run", "cls": "clear"}
_BY_NAME = {c["name"]: c for c in COMMANDS}


def resolve(name: str):
    name = _ALIASES.get(name, name)
    if name in _BY_NAME:
        return _BY_NAME[name]
    pref = [c for c in COMMANDS if c["name"].startswith(name)]
    return pref[0] if len(pref) == 1 else None


def suggest(name: str) -> list[str]:
    """Suggest close command names on typos."""
    names = [c["name"] for c in COMMANDS] + list(_ALIASES)
    return difflib.get_close_matches(name, names, n=3, cutoff=0.5)


# --------------------------------------------------------------------------
# readline: Tab completion and persistent history
# --------------------------------------------------------------------------

HISTORY_FILE = Path.home() / ".vliw_history"
HISTORY_SIZE = 1000

_ARG_COMPLETIONS = {
    "run": lambda: list(SCENARIOS),
    "compare": lambda: list(SCENARIOS),
    "tiny": lambda: list(SCENARIOS),
    "random": lambda: list(SCENARIOS),
    "model": lambda: list(PROFILES) + ["measured", "naive"],
    "play": lambda: ["baseline", "oracle"],
    "asm": lambda: ["baseline", "oracle"],
    "doctor": lambda: ["baseline", "oracle"],
    "kaggle": lambda: ["step0", "run1", "all", "pull", "status"],
    "learned": lambda: [a.name for a in _learned_adapters()],
}


def _learned_adapters():
    """Discovered adapter names for Tab completion (empty if unavailable)."""
    try:
        from .learned import runtime

        return runtime.find_adapters()
    except Exception:
        return []


def _completer(text: str, state: int):
    """Readline Tab completer: command names and context-aware arguments."""
    try:
        buf = readline.get_line_buffer()
        if " " not in buf:
            stub = buf if buf.startswith("/") else "/" + buf.lstrip("/")
            cands = slash.complete_plain(stub, COMMANDS)
        else:
            stub = buf if buf.startswith("/") else "/" + buf
            cands = slash.complete_plain(stub, COMMANDS)
    except Exception:
        cands = []
    return cands[state] if state < len(cands) else None


def _setup_readline() -> None:
    """Enable Tab completion and load command history."""
    if not HAS_READLINE:
        return
    readline.set_completer(_completer)
    readline.set_completer_delims(" \t\n")
    try:
        readline.parse_and_bind("tab: complete")
    except Exception:  # pragma: no cover - exotic readline/libedit builds
        pass
    readline.set_history_length(HISTORY_SIZE)
    readline.clear_history()
    try:
        readline.read_history_file(HISTORY_FILE)
    except (FileNotFoundError, OSError, PermissionError):
        pass


def _save_history() -> None:
    if not HAS_READLINE:
        return
    try:
        readline.write_history_file(HISTORY_FILE)
    except OSError:
        pass


def _parse_opts(arg: str, defaults: dict) -> dict:
    """Parse `--key value` and `--key=value` options with defaults."""
    out = dict(defaults)
    toks = arg.split()
    i = 0
    while i < len(toks):
        t = toks[i]
        if t.startswith("--"):
            key = t[2:]
            if "=" in key:
                key, val = key.split("=", 1)
                out[key] = val
            elif i + 1 < len(toks):
                out[key] = toks[i + 1]
                i += 1
        i += 1
    return out


# True while Textual owns the terminal (disables interactive input() pauses).
IN_TUI = False

# True inside the plain-mode REPL (enables interactive prompts like `/clear`).
IN_REPL = False


def _pause(session: Session) -> bool:
    if IN_TUI:
        return True
    if session.delay is not None:
        try:
            time.sleep(session.delay)
        except KeyboardInterrupt:
            return False
        return True
    if not sys.stdin.isatty():
        return True
    try:
        return input().strip().lower() not in ("q", "quit", "exit")
    except EOFError:
        return False


# --------------------------------------------------------------------------
# Dispatcher and interactive loop
# --------------------------------------------------------------------------


def _run_dag(session: Session, dag) -> bool:
    session.set_dag(dag, dag.key)
    cmd_run(session, "")
    return True


def _apply_mode(session: Session, name: str | None) -> None:
    """Set focus/mode from a pane alias."""
    from .ui import panes

    dest = panes.resolve_focus(name or "lab") or "lab"
    session.focus = dest
    session.mode = "chat" if dest == "mind" else "explore"


def _exec_work(session: Session, s: str) -> bool:
    from .ui import interp_view

    session.last_work = s
    session.focus = "work"
    try:
        result = session.workspace().exec(s)
    except InterpError as e:
        print(paint("error", f"interpreter: {e}"))
        return False
    if result.kind not in ("reset", "empty") and not session.workspace().empty():
        session.set_dag(session.workspace().snapshot(), "interp")
    _out(interp_view.render_result(session.workspace(), result))
    if result.kind == "go":
        if session.workspace().empty():
            return True
        session.focus = "lab"
        return _run_dag(session, session.workspace().snapshot())
    return True


def handle_input(session: Session, raw: str) -> bool:
    """Route a CLI command, interpreter expression, scenario name, or agent question."""
    s = raw.strip()
    if not s:
        return True
    head, _, tail = s.partition(" ")
    name = head.lstrip("/").lower()
    arg = tail.strip()

    if resolve(name):
        return dispatch(session, name, arg)

    if getattr(session, "focus", "") == "work":
        return _exec_work(session, s)

    known = session.workspace().regs if session._workspace else None
    if looks_like_work(s, known):
        return _exec_work(session, s)

    if name in SCENARIOS or name.startswith("rand"):
        return dispatch(session, "run", s.lstrip("/").strip())

    if " " in s or any(ch in s for ch in "?!") or len(name) > 20:
        try:
            session.focus = "mind"
            session.mode = "chat"
            agent_view.stream_turn(session.agent(), s)
            return True
        except Exception as e:
            print(paint("error", f"agent: {e}"))
            return False

    if " " not in s and len(name) <= 20:
        return dispatch(session, name, arg)
    print(Style.dim("  not a command.  /help  ·  a=load  ·  plain-English question"))
    return False


def dispatch(session: Session, name: str, arg: str) -> bool:
    """Execute a command. Returns False on unknown command or command failure."""
    name = name.lstrip("/").lower()
    if not name:  # bare '/' -> /help
        cmd_help(session, "")
        return True
    cmd = resolve(name)
    if cmd is None:
        msg = paint("error", f"unknown command /{name}.")
        hints = suggest(name)
        if hints:
            msg += Style.dim("  Did you mean: ") + ", ".join(
                paint("accent", "/" + h) for h in hints) + Style.dim("?")
        else:
            msg += Style.dim(" Type /help for a list of commands.")
        print(msg)
        return False
    return cmd["fn"](session, arg) is not False


def _prompt(session: Session) -> str:
    _ = session
    return paint("prompt", "nex ") + Style.dim("> ")


# Bracketed paste markers emitted by some terminals around pasted text.
_PASTE_MARK = re.compile("\x1b\\[20[01]~")


def _fullscreen_ok() -> bool:
    """Whether the full-screen Textual interface can start."""
    try:
        from . import tui as nextui

        return nextui.available()
    except Exception:
        return False


def run_tui(session: Session, pick_app: bool | None = None) -> int:
    """Launch the full-screen Textual UI, falling back to `setup_screen` on failure."""
    global IN_TUI

    def execute(line: str) -> None:
        handle_input(session, line)

    if pick_app is None:
        pick_app = getattr(session.args, "mode", None) is None
    start_mode = None if pick_app else getattr(session, "focus", "lab")

    IN_TUI = True
    try:
        from . import tui as nextui

        if nextui.available():
            return nextui.run(session, execute, COMMANDS, start_mode=start_mode)
    except Exception as e:
        print(paint("warning", f"full-screen mode unavailable ({e})"))
        from .ui import setup_screen

        return setup_screen.explain(extra=f"Textual startup failed: {e}")
    finally:
        IN_TUI = False

    from .ui import setup_screen

    return setup_screen.explain()


def repl(session: Session) -> int:
    _setup_readline()
    print()
    hint = "core · lab · agent.  /run slotclash  ·  sum 8  ·  ask a question. "
    if HAS_READLINE:
        hint += "Tab — complete, ↑/↓ — history. "
    hint += "/exit — quit."
    print(Style.dim(hint))
    global IN_REPL
    IN_REPL = True
    try:
        return _repl_loop(session)
    finally:
        IN_REPL = False
        _save_history()


def _repl_loop(session: Session) -> int:
    while True:
        try:
            line = input("\n" + _prompt(session))
        except EOFError:              # Ctrl+D / closed pipe
            print()
            return 0
        except KeyboardInterrupt:     # Ctrl+C at prompt cancels current line
            print("\n" + Style.dim("^C  (type /exit to quit)"))
            continue

        line = _PASTE_MARK.sub("", line)
        s = line.strip()
        low = s.lower()

        if s == "" or low in ("/help", "help"):
            cmd_help(session, "")
            continue
        if low in ("/exit", "exit", "/quit", "quit"):
            print(Style.dim("bye!"))
            return 0
        try:
            handle_input(session, s)
        except KeyboardInterrupt:      # Ctrl+C during command cancels it
            print("\n" + Style.dim("^C  command interrupted"))
        except SystemExit as e:
            print(paint("error", str(e)))
        except Exception as e:         # one bad command never crashes the session
            print(paint("error", f"command error: {e}"))
    return 0


# --------------------------------------------------------------------------
# Argument parsing and entry point
# --------------------------------------------------------------------------


def _commands_epilog() -> str:
    lines = ["commands (identical on the CLI and inside the REPL with '/'):"]
    width = max(len(c["name"]) + len(c["arg"]) for c in COMMANDS) + 3
    for gid, title in GROUPS:
        members = [c for c in COMMANDS if c.get("group") == gid]
        if not members:
            continue
        lines += ["", f"  {title}:"]
        for c in members:
            sig = (c["name"] + " " + c["arg"]).strip()
            lines.append(f"    {sig:<{width}} {c['help']}")
    lines += [
        "",
        "command details:  python -m vliw help <command>",
        "",
        "examples:",
        "  python -m vliw run slotclash",
        "  python -m vliw compare --no-color",
        "  python -m vliw                      # no command — interactive mode",
        "",
        "full documentation: docs/CLI.md",
    ]
    return "\n".join(lines)


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m vliw", add_help=True,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description="NEX CLI — VLIW instruction scheduler for the Elbrus e2k-v6 model. "
                    "Without arguments launches interactive mode; with a command runs once.",
        epilog=_commands_epilog(),
    )
    from . import VERSION_LABEL, __version__

    p.add_argument("--version", action="version",
                   version=f"NEX CLI {VERSION_LABEL}  ({__version__})",
                   help="show version and exit")
    p.add_argument("--profile", choices=list(PROFILES), default=None, help="machine profile")
    p.add_argument("--width", type=int, default=None, help="override port count")
    p.add_argument("--budget", type=float, default=10.0, help="exact oracle time budget (s)")
    p.add_argument("--portfolio", type=float, default=3.0, help="fallback search budget (s)")
    p.add_argument("--color", dest="color", action="store_true", default=None, help="enable color")
    p.add_argument("--no-color", dest="color", action="store_false", help="disable color")
    p.add_argument("--theme", default=None, help="color theme (see /theme)")
    p.add_argument("--mode",
                   choices=["work", "lab", "mind", "code", "explore", "chat"],
                   default=None,
                   help="skip mode picker: work / lab / mind / code")
    p.add_argument(
        "--plain", action="store_true",
        help="plain line-by-line interactive mode (no full-screen TUI)",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    # Enable UTF-8 before parsing args so `--help` renders cleanly on Windows.
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    render.utf8_console()

    parser = _build_parser()
    args, extras = parser.parse_known_args(argv)
    render.setup_output(args.color, args.theme)

    session = Session(args=args)
    _apply_mode(session, getattr(args, "mode", None) or "lab")
    if args.profile:
        session.profile = args.profile
    if args.width is not None and args.width < 1:
        print(paint("error", f"machine width cannot be {args.width}: "
                             f"must be an integer >= 1"))
        return 1
    if args.width:
        session.width = args.width

    try:
        if not extras:
            if not args.plain and args.color is not False:
                if _fullscreen_ok():
                    return run_tui(session)
                from .ui import setup_screen

                return setup_screen.explain()

            print_logo()
            if getattr(args, "mode", None) is None:
                chosen = launcher.prompt_plain()
                if not chosen:
                    return 0
                _apply_mode(session, chosen)
            return repl(session)

        if extras[0].lower() in ("chat", "explore", "lab", "mind",
                                 "code") \
                and len(extras) == 1:
            _apply_mode(session, extras[0])
            if not args.plain and args.color is not False:
                if _fullscreen_ok():
                    return run_tui(session, pick_app=False)
                from .ui import setup_screen

                return setup_screen.explain()
            print_logo()
            return repl(session)

        _SINGLE_GRAPH_CMDS = {"run", "load", "compare", "doctor", "bounds",
                              "path", "analyze"}
        cmd_name = extras[0].lower()
        if (cmd_name in _SINGLE_GRAPH_CMDS and not args.plain
                and args.color is not False and _fullscreen_ok()):
            try:
                if cmd_name == "load":
                    if len(extras) > 1 and not handle_input(session,
                                                            " ".join(extras)):
                        return 1
                else:
                    scen = next((t for t in extras[1:]
                                 if not t.startswith("-")), None)
                    if scen is not None:
                        session.set_scenario(scen)
            except SystemExit:
                raise
            except Exception as e:
                print(paint("error", f"command error: {e}"))
                return 1
            _apply_mode(session, "lab")
            return run_tui(session, pick_app=False)

        try:
            ok = handle_input(session, " ".join(extras))
        except SystemExit:
            raise
        except Exception as e:
            print(paint("error", f"command error: {e}"))
            return 1
        return 0 if ok else 1
    except KeyboardInterrupt:
        print("\n" + Style.dim("interrupted (Ctrl+C)"))
        return 130
