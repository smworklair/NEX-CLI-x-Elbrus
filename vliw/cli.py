"""Единая точка входа: команда → core → ui → печать.

  python -m vliw                 интерактив: выбор приложения, затем цикл
  python -m vliw run slotclash   одна команда и выход
  python -m vliw --plain         тот же цикл построчно, без curses

Три панели одного workstation:
  ядро   — интерпретатор (sum 8, своя запись)
  разбор — /run /compare /doctor
  агент  — вопрос обычным языком

Здесь только склейка. Логика планирования — в vliw.core.
"""

from __future__ import annotations

import argparse
import difflib
import random as _random
import re
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

# readline — из стандартной библиотеки Python, но недоступен на некоторых
# сборках Windows без сторонних пакетов. Даёт даром: историю ввода (стрелки
# вверх/вниз, персистентную между запусками) и Tab-дополнение команд. Это
# НАМЕРЕННО не собственный raw-terminal код (как была прежняя «живая
# палитра» по «/», которую убрали за баги с перерисовкой) — readline
# написан и обкатан десятилетиями, сам разбирается с терминалом и не
# ломается на вставке текста, коротких терминалах и т.п.
try:
    import readline

    HAS_READLINE = True
except Exception:  # pragma: no cover - платформозависимо
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
# Сессия: текущий сценарий/профиль/ширина + кэш результатов планирования
# --------------------------------------------------------------------------


@dataclass
class Session:
    args: object
    profile: str = DEFAULT_PROFILE
    scenario: str = "slotclash"
    dag_obj: DAG | None = None
    width: int | None = None
    delay: float | None = None  # пауза воспроизведения; None = по Enter
    mode: str = "explore"      # совместимость: explore ≈ lab, chat ≈ mind
    focus: str = "lab"         # work | lab | mind — какая панель в фокусе
    last_work: str = ""
    _workspace: object = None
    _agent: object = None
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
        self.dag_obj = dag
        self.scenario = label

    def workspace(self) -> Workspace:
        if self._workspace is None:
            self._workspace = Workspace()
        return self._workspace

    def agent(self):
        """Диалоговая сессия агента (создаётся при первом обращении)."""
        if self._agent is None:
            from .agent import Agent

            self._agent = Agent(session=self)
        return self._agent

    def peek(self):
        """Уже посчитанный результат или None — БЕЗ запуска вычислений.

        Нужен панели контекста: она рисуется постоянно и не должна сама
        запускать точный поиск (это подвесило бы интерфейс на секунды).
        """
        return self._cache.get((self.scenario, self.profile, self.width))

    def results(self):
        """(base, oracle, metrics) — вычисляет core, кэширует, валидирует."""
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
                        f"ВНУТРЕННЯЯ ОШИБКА: {who} выдал некорректное расписание:\n  "
                        + "\n  ".join(errs)
                    )
            self._cache[key] = (base, orc, compute_metrics(d, m))
        return self._cache[key]


def _header(session: Session) -> str:
    m = session.model()
    return (
        paint("1", session.scenario)
        + Style.dim(f"  ·  {len(session.dag_obj)} инстр.  ·  {m.name}"
                    f"  ·  {m.width} портов")
    )


def _out(lines) -> None:
    print("\n".join(lines) if isinstance(lines, list) else lines)


# --------------------------------------------------------------------------
# Команды
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
        _out(wrap(paint("lab", "◆ ") + Style.dim(dag.lesson), render.W, "  "))
        print()
    hl = {i: render.CRIT_CODE for i in schedule_view.critical_set(dag, met)}
    _out(schedule_view.render_schedule(
        orc.schedule, dag, model, hl,
        paint("success", "  расписание oracle (точный поиск), ★ — критический путь:")))
    print()
    print(schedule_view.render_stats_line(base, orc))
    print()
    _out(schedule_view.render_verdict(base, orc, met))
    print()
    print(Style.dim("  дальше:  compare   doctor   path   bounds"))


def cmd_compare(session: Session, arg: str) -> None:
    if arg.strip():
        session.set_scenario(arg.split()[0])
    base, orc, met = session.results()
    dag, model = session.dag_obj, session.model()
    diverged = {
        i for i in range(len(dag))
        if base.schedule.placements[i].cycle != orc.schedule.placements[i].cycle
    }
    print(rule("сравнение · " + dag.title))
    print("  " + _header(session))
    print("  " + op_legend())
    print("  " + paint(render.DIVERGE_CODE, "красным") + Style.dim(" — инструкции в разных тактах"))
    print()
    hl = {i: render.DIVERGE_CODE for i in diverged}
    _out(schedule_view.render_schedule(
        base.schedule, dag, model, hl,
        paint("warning", "  baseline — жадная эвристика:")))
    print()
    _out(schedule_view.render_schedule(
        orc.schedule, dag, model, hl,
        paint("success", "  oracle — точный поиск:")))
    print()
    _out(schedule_view.render_divergence_line(base, orc, dag, met))
    print()
    _out(schedule_view.render_verdict(base, orc, met))


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
    print(rule(f"по тактам · {who.lower()}"))
    print("  " + _header(session))
    print("  " + op_legend())
    if stepping:
        print(Style.dim("  Enter — следующий такт · q + Enter — прервать"))
    print()
    issued = 0
    for item in items:
        if item[0] == "bundle":
            issued += len(item[2])
        _out(schedule_view.render_item(dag, model, sched, item, hl))
        print(Style.dim(f"       выдано {issued}/{len(dag)} инстр., makespan {sched.makespan}"))
        if not _pause(session):
            print(Style.dim("  … прервано"))
            return
    print()
    _out(schedule_view.render_verdict(base, orc, met))


def cmd_explain(session: Session, arg: str) -> None:
    base, orc, met = session.results()
    dag, model = session.dag_obj, session.model()
    if not arg.strip():
        d = schedule_view.find_divergence(base.schedule, orc.schedule, dag)
        t = d.cycle if d.cycle is not None else 0
        print(Style.dim(f"  такт не указан — беру первое расхождение (такт {t})"))
    else:
        try:
            t = int(arg.split()[0])
        except ValueError:
            print(paint("error", "нужен номер такта: /explain <такт>"))
            return False
    print(rule(f"такт {t}"))
    _out(schedule_view.render_explain(t, base, orc, dag, model))


def cmd_path(session: Session, arg: str) -> None:
    base, orc, met = session.results()
    print(rule("критический путь · " + session.dag_obj.title))
    print("  " + _header(session))
    print()
    _out(["  " + l for l in schedule_view.render_dag_path(session.dag_obj, session.model(), met)])


def cmd_bounds(session: Session, arg: str) -> None:
    base, orc, met = session.results()
    print(rule("границы"))
    _out(schedule_view.render_bounds(session.dag_obj, session.model(), met))


def cmd_model(session: Session, arg: str) -> None:
    arg = arg.strip().lower()
    if arg:
        match = next((n for n in PROFILES if n.lower().startswith(arg) or arg in n.lower()), None)
        match = match or {"measured": "e2k-v6-measured", "naive": "naive_homogeneous",
                          "homogeneous": "naive_homogeneous", "m": "e2k-v6-measured"}.get(arg)
        if not match:
            print(paint("error", f"неизвестный профиль {arg!r}; доступны: {', '.join(PROFILES)}"))
            return False
        session.profile = match
        print(paint("success", f"профиль переключён на {match}"))
    model = session.model()
    print(rule("машина · " + model.name))
    _out(tables.render_model_view(model))
    print()
    others = [n for n in PROFILES if n != session.profile]
    print(Style.dim(f"  Переключить: /model {others[0] if others else '<профиль>'}"))


def cmd_scenarios(session: Session, arg: str) -> None:
    print(rule("сценарии"))
    _out(tables.render_scenarios(session.scenario))


def cmd_random(session: Session, arg: str) -> None:
    parts = arg.split()
    n = 16
    seed = _random.randint(1, 10**6)
    if parts:
        try:
            n = max(3, int(parts[0]))
        except ValueError:
            pass
    if len(parts) > 1:
        try:
            seed = int(parts[1])
        except ValueError:
            pass
    dag = random_dag(seed, n=n, key=f"rand{seed}",
                     title=f"Случайный граф (seed={seed}, {n} инстр.)")
    session.set_dag(dag, f"rand{seed}")
    print(paint("success", f"сгенерирован случайный граф: {n} инструкций, seed={seed}"))
    cmd_run(session, "")


def cmd_all(session: Session, arg: str) -> None:
    print(rule("сводка"))
    _out(wrap(
        "Каждый сценарий планируется дважды: жадная эвристика (baseline) и точный "
        "поиск (oracle). Столбец «выигрыш» — разрыв до теоретического потолка.",
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
        f"{seeds} случайных графов × размеры {sizes} × конфигурации машины. Для "
        f"каждой считаем, в скольких графах точный поиск обогнал эвристику "
        f"(только где оптимальность доказана).", render.W, "  "))
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
        on_failure=lambda tag, probs: print(Style.red(f"  ✗ {tag}")),
    )
    _out(tables.render_selfcheck(result))


def cmd_docs(session: Session, arg: str) -> None:
    print(rule("что это"))
    body = [
        "Три панели: ядро считает граф, разбор ищет такты, агент отвечает.",
        "",
        "baseline — жадная эвристика, как в компиляторе.",
        "oracle — точный поиск, потолок, не ИИ.",
        "разница — такты, которые можно отыграть порядком выдачи.",
        "",
        "деление только в ,5, запись в ,2 и ,5, умножение в четырёх каналах.",
        "",
        "сначала:  sum 8   потом  compare   потом  doctor",
        "панели: /mode work  ·  /mode lab  ·  /mode mind",
    ]
    for line in body:
        print("  " + (Style.dim(line) if line else ""))


def cmd_agent(session: Session, arg: str) -> None:
    base, orc, met = session.results()
    gap = base.schedule.makespan - orc.schedule.makespan
    body = [
        "Где здесь место обученной модели.",
        "",
        "Все планировщики реализуют один протокол Scheduler (vliw/core/api.py):",
        "  baseline  → kind=\"heuristic\"   (жадный list scheduler)",
        "  oracle    → kind=\"exact\"       (точный поиск, потолок)",
        "  learned   → kind=\"learned\"     (обученная модель — ПОКА ЗАГЛУШКА)",
        "",
        "Каркас будущей модели уже зарезервирован: vliw/learned/scheduler.py.",
        "Когда обучение на Hexagon даст рабочую модель, её кладут туда — она",
        "реализует тот же schedule(dag, model) → SchedulingResult, и ни CLI, ни",
        "визуализация не меняются.",
        "",
        f"На текущем сценарии ({session.scenario}) потолок оракула обыгрывает",
        f"эвристику на {gap} {render.plural(gap, 'такт', 'такта', 'тактов')} — вот "
        "столько и должна",
        "отыграть обученная модель, чтобы сравняться с точным поиском.",
    ]
    _out(panel(body, title="ТОЧКА ПОДСТАНОВКИ МОДЕЛИ", color="accent2"))


def cmd_help(session: Session, arg: str) -> None:
    print(rule("клиент"))
    _hint()
    print()
    print(rule("команды"))
    rows = []
    for c in COMMANDS:
        rows.append([paint("accent", "/" + c["name"]), c["arg"], c["help"]])
    for l in render.table(["команда", "аргументы", "что делает"], rows, aligns="<<<"):
        print("  " + l)
    print()
    print(Style.dim("  в цикле со «/», снаружи без: python -m vliw run slotclash"))
    print(Style.dim("  ядро: sum 8  ·  агент: вопрос  ·  выход: /exit"))


def cmd_doctor(session: Session, arg: str) -> None:
    """Диагностика: где именно теряются такты и что с этим делать.

    `/doctor` — сводка, `/doctor N` — подробности находки N,
    `/doctor oracle` — то же для расписания точного поиска.
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
        print(rule(f"НАХОДКА №{detail} — {label}"))
        _out(diagnostics.render_detail(d, detail))
        return
    print(rule(f"doctor · {label} · {session.scenario}"))
    print()
    _out(diagnostics.render_diagnosis(d, label))


def cmd_load(session: Session, arg: str) -> None:
    """Загрузить настоящий .s от lcc, разобрать и сравнить с точным поиском."""
    path = arg.strip()
    if not path:
        print(paint("error", "укажите файл: /load examples/probe.s"))
        return False
    try:
        parsed = asm_parser.parse_file(path)
    except OSError as e:
        print(paint("error", f"не открыть файл: {e}"))
        return False
    if not parsed.ops:
        print(paint("error", "в файле не нашлось ни одной операции — "
                             "это точно .s-вывод lcc?"))
        return False

    model = session.model()
    dag = asm_parser.build_dag(parsed, key=f"asm:{path}", title=f"{path}")
    session.set_dag(dag, f"asm:{Path(path).name}")

    cs = asm_parser.compiler_schedule(parsed, dag, model)
    comp_cycles = cs.makespan if cs else None
    if cs and cs.validate():
        comp_cycles = None      # раскладка не сходится с моделью — не врём
    base, orc, met = session.results()

    print(rule("загружен · " + path))
    _out(diagnostics.render_parsed(parsed, dag, comp_cycles,
                                   orc.schedule.makespan, met.lower_bound))
    session.compiler_sched = cs if comp_cycles is not None else None


def cmd_analyze(session: Session, arg: str) -> None:
    """Типизированный разбор участка: вердикт, причина, план. Без диалога."""
    from .agent import analyst

    print(rule("анализ · " + session.scenario))
    print(Style.dim("  структурный разбор, без разговора"))
    print()
    a = analyst.analyze(session)
    _out(analyst_view.render_analysis(a, session.scenario))


def cmd_mode(session: Session, arg: str) -> None:
    """Переключить фокус панели: ядро / разбор / агент."""
    from .ui import panes

    a = arg.strip().lower()
    if a:
        dest = panes.resolve_focus(a)
        if dest is None:
            print(paint("error", f"неизвестная панель {a!r}; доступны: work, lab, mind"))
            return False
        session.focus = dest
        session.mode = "chat" if dest == "mind" else "explore"
        print(paint("success", f"панель: {panes.META[dest]['title'].lower()}"))
    print(rule("панели"))
    current = getattr(session, "focus", "lab")
    for name in panes.PANES:
        meta = panes.META[name]
        mark = paint(meta["role"], "●") if current == name else " "
        print(f"  {mark} {paint(meta['role'], meta['title']):<10} "
              + Style.dim(meta["sub"]))
    print()
    print(Style.dim("  /mode work  ·  /mode lab  ·  /mode mind"))


def cmd_ask(session: Session, arg: str) -> None:
    """Задать вопрос агенту (в режиме agent то же самое — просто текст)."""
    q = arg.strip()
    if not q:
        _out(agent_view.render_intro())
        return
    agent_view.stream_turn(session.agent(), q)


def cmd_ai(session: Session, arg: str) -> None:
    """Состояние языковой модели и как её настроить."""
    from .agent import status

    print(rule("ЯЗЫКОВАЯ МОДЕЛЬ"))
    ok, detail = status()
    _out(agent_view.render_status(ok, detail))


def cmd_status(session: Session, arg: str) -> None:
    print(rule("КОНТЕКСТ СЕССИИ"))
    _out(context.render_status(session))
    print()
    print("  " + logo.status_line(
        getattr(session, "focus", "lab"), session.scenario, session.model().name))


def cmd_theme(session: Session, arg: str) -> None:
    name = arg.strip()
    available = theme.list_themes()
    if name:
        if name not in available:
            print(paint("error", f"неизвестная тема {name!r}; доступны: "
                                 f"{', '.join(available)}"))
            return False
        render.apply_theme(name)
        print(paint("success", f"тема переключена на {name}"))
    print(rule("темы"))
    for t in available:
        th = theme.load_theme(t)
        mark = paint("work", "●") if th.name == render.THEME.name else " "
        print(f"  {mark} {paint('title', t)}")
        _out(wrap(Style.dim(th.description), render.W, "      "))
    print()
    print(Style.dim(f"  Файлы тем: vliw/ui/themes/*.json  ·  переключить: /theme <имя>"))
    print("  " + op_legend())


def _hint() -> None:
    print(Style.dim("  ядро: sum 8   ·   разбор: /run /compare /doctor"))
    print(Style.dim("  агент: вопрос обычным языком   ·   /mode work|lab|mind"))


def cmd_work(session: Session, arg: str) -> None:
    """Справка интерпретатора: запись, ядра, слова."""
    from .ui import interp_view

    _out(interp_view.render_welcome())
    print()
    rows = []
    for name, default, hint in kernel_help():
        rows.append([paint("work", name), str(default), hint])
    for l in render.table(["ядро", "n", "что считает"], rows, aligns="><<"):
        print("  " + l)


def cmd_clear(session: Session, arg: str) -> None:
    """Очистить экран и вернуться к выбору режима."""
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
    print(rule(f"ШИРОКИЕ КОМАНДЫ ({which}) — как в .s-выводе lcc"))
    print("  " + _header(session))
    print("  " + op_legend())
    print()
    _out(schedule_view.render_asm(sched, dag, model))
    print()
    _out(wrap(Style.dim(
        "Каждая { … } — одна ШИРОКАЯ команда e2k: всё внутри выполняется "
        "одновременно, `,N` — номер канала (порта). `nop` — вынужденный простой. "
        "Модель мы сняли ровно с такого .s (см. /probe), здесь — наш результат "
        "обратно в том же виде."), render.W, "  "))


def cmd_probe(session: Session, arg: str) -> None:
    body = [
        "Откуда взялась модель машины — и почему первая версия была неверна.",
        "",
        "ПЕРВАЯ ПОПЫТКА (ошибочная). Скомпилировали .c с четырьмя делениями и",
        "четырьмя умножениями, прочли готовые { … } из lcc -O3 -S. Все четыре",
        "muls легли на канал ,0 подряд — и это прочли как «умножитель один,",
        "держит порт 8 тактов». Ошибка: четырёх операций мало, чтобы жадный",
        "планировщик lcc захотел разложить их по каналам. Листинг показывает,",
        "что компилятор ЗАХОТЕЛ сделать, а не что железо МОЖЕТ.",
        "",
        "КАК ПРОВЕРЯЕМ ТЕПЕРЬ — три независимых способа:",
        "  1. Матрицу портов спрашиваем у АССЕМБЛЕРА: собираем крошечный .s с",
        "     операцией в конкретном канале. Нельзя — получаем прямой отказ",
        "     «'muls' cannot be encoded in ALC2». Это факт про кодировку железа.",
        "  2. Латентность — ЦЕПОЧКОЙ зависимых операций: каждая ждёт предыдущую,",
        "     и компилятор вынужден развести их ровно на латентность.",
        "  3. Темп приёма — ПОТОКОМ из 8-16 независимых: шаг между выдачами.",
        "",
        "Что получилось:",
        "  • sdivs — только канал ,5 (остальные пять ассемблер отверг);",
        "    латентность 11, новое деление принимается раз в 2 такта;",
        "  • muls/muld — каналы ,0 ,1 ,3 ,4; ЧЕТЫРЕ штуки влезают в одну широкую",
        "    команду; латентность 4, поток идёт по одному в такт;",
        "  • ldw/ldd — каналы ,0 ,2 ,3 ,5, латентность 5 (а не 2);",
        "  • stw/std — всего два канала: ,2 и ,5;",
        "  • adds/subs/ands/shls — все шесть каналов.",
        "",
        "Вывод: матрица возможностей у e2k действительно неравноправна, но",
        "монополия ровно одна — делитель. Умножитель узким местом не является.",
    ]
    _out(panel(body, title="ИЗМЕРЕНИЕ МОДЕЛИ И РАБОТА НАД ОШИБКАМИ", color="border"))
    print()
    print(Style.dim("  Матрица целиком: /model.  Ошибочная версия для сравнения: "
                    "/model e2k-v6-firstprobe"))


# --------------------------------------------------------------------------
# Обслуживание проекта: тонкая склейка с tools/ — те же проверки, что и
# отдельными скриптами, но одним входом наравне с /run /doctor и т.д.
# --------------------------------------------------------------------------


def _run_tool(main_fn, toks: list[str]) -> bool:
    """Вызвать main(argv) скрипта из tools/ в процессе и вернуть успех.

    Скрипты tools/*.py самодостаточны и умеют запускаться отдельно
    (`python tools/probe_matrix.py`); здесь та же функция main(), просто без
    второго питона subprocess'ом — она уже принимает argv и возвращает код
    возврата вместо sys.exit().
    """
    return main_fn(toks) in (0, None)


def cmd_verify(session: Session, arg: str) -> None:
    """Живая переснятие матрицы портов у ассемблера e2k (tools/probe_matrix.py).

    В отличие от /probe (рассказывает историю измерения) — реально гоняет
    ассемблер прямо сейчас и сверяет с vliw/core/model.py. Без ассемблера в
    PATH/E2K_AS не проваливается, а сообщает, что проверить нечем.
    """
    from tools import probe_matrix

    print(rule("verify · матрица портов у ассемблера"))
    if not _run_tool(probe_matrix.main, arg.split()):
        return False


def cmd_validate(session: Session, arg: str) -> None:
    """Прогнать jsonl через настоящий Schedule.validate() (tools/validate_jsonl.py)."""
    from tools import validate_jsonl

    toks = arg.split()
    if not any(not t.startswith("--") for t in toks):
        print(paint("error", "укажите файл(ы): /validate dataset.jsonl"))
        return False
    print(rule("validate · " + " ".join(t for t in toks if not t.startswith("--"))))
    if not _run_tool(validate_jsonl.main, toks):
        return False


def cmd_report(session: Session, arg: str) -> None:
    """Свести дампы прогонов (validate_kaggle.py --dump) в таблицу (tools/report_runs.py)."""
    from tools import report_runs

    print(rule("report · сводка прогонов"))
    if not _run_tool(report_runs.main, arg.split()):
        return False


def cmd_learned(session: Session, arg: str) -> None:
    """Запустить обученный адаптер на текущем графе — локально, без Kaggle.

    Без аргументов и без готовых весов/зависимостей — печатает отчёт о том,
    чего не хватает, и не падает: это самый частый случай на чужой машине.
    """
    from .learned import runtime
    from .ui import learned_view

    toks = arg.split()
    want_raw = "--raw" in toks
    want_status = "--status" in toks
    name = next((t for t in toks if not t.startswith("--")), None)

    ready, lines = runtime.status(name)
    if want_status or not ready:
        print(rule("обученный планировщик"))
        _out(learned_view.render_status(ready, lines))
        return None if want_status else False

    from .learned import LearnedScheduler

    adapter = runtime.resolve_adapter(name)
    if adapter is None:
        print(paint("error", f"адаптер {name!r} не найден; доступны: "
                             + ", ".join(a.name for a in runtime.find_adapters())))
        return False

    dag, machine = session.dag_obj, session.model()
    print(rule(f"обученный планировщик · {adapter.name} · {session.scenario}"))
    print("  " + _header(session))
    print()
    print(Style.dim(f"  поднимаю {adapter.base} + LoRA {adapter.name} — "
                    "первый запуск долгий (веса грузятся с диска)"))
    sys.stdout.flush()

    sch = LearnedScheduler(adapter=adapter)
    try:
        res = sch.schedule(dag, machine)
    except (RuntimeError, OSError, ImportError) as e:
        print(paint("error", f"не удалось запустить модель: {e}"))
        return False
    print()
    # Сравниваем только с тем, что уже посчитано: гонять точный поиск ради
    # сравнения с заведомо незаконным расписанием — впустую.
    base = orc = None
    if res.search_stats.get("valid"):
        base, orc, _ = session.results()
    _out(learned_view.render_result(res, dag, orc, base))
    if want_raw:
        print()
        _out(learned_view.render_raw(res))


def cmd_kaggle(session: Session, arg: str) -> None:
    """Залить/забрать/проверить Kaggle — тонкая обёртка над tools/kaggle_push.sh.

    Логика (учётные данные, сборка build/kaggle/, вызовы kaggle CLI) целиком
    в самом скрипте — здесь только один вход и передача режима: step0 (по
    умолчанию) | run1 | all | pull | status.
    """
    mode = (arg.split() or ["step0"])[0]
    script = Path(__file__).resolve().parent.parent / "tools" / "kaggle_push.sh"
    print(rule(f"kaggle · {mode}"))
    # Без flush() написанное выше при непустом stdout-буфере (когда вывод не
    # в терминал, а в файл/pipe) печатается ПОСЛЕ вывода подпроцесса —
    # подпроцесс пишет в тот же fd напрямую, порог сброса у него свой.
    sys.stdout.flush()
    r = subprocess.run([str(script), mode])
    if r.returncode != 0:
        return False


# --------------------------------------------------------------------------
# Реестр команд
# --------------------------------------------------------------------------

COMMANDS = [
    {"name": "run", "arg": "<сценарий>", "help": "прогнать сценарий: расписание оракула + вердикт", "fn": cmd_run},
    {"name": "compare", "arg": "[сценарий]", "help": "baseline и oracle бок о бок", "fn": cmd_compare},
    {"name": "play", "arg": "[base|oracle]", "help": "воспроизвести расписание такт за тактом", "fn": cmd_play},
    {"name": "asm", "arg": "[base|oracle]", "help": "расписание как широкие команды e2k { … }", "fn": cmd_asm},
    {"name": "explain", "arg": "<такт>", "help": "почему в этом такте выбрали именно это", "fn": cmd_explain},
    {"name": "path", "arg": "", "help": "граф с подсветкой критического пути", "fn": cmd_path},
    {"name": "bounds", "arg": "", "help": "две нижние границы makespan", "fn": cmd_bounds},
    {"name": "model", "arg": "[профиль]", "help": "матрица возможностей портов; смена профиля", "fn": cmd_model},
    {"name": "probe", "arg": "", "help": "как probe.c измерил модель машины e2k", "fn": cmd_probe},
    {"name": "scenarios", "arg": "", "help": "список доступных сценариев", "fn": cmd_scenarios},
    {"name": "random", "arg": "[N] [seed]", "help": "случайный граф на N инструкций и прогон", "fn": cmd_random},
    {"name": "all", "arg": "", "help": "сводная таблица по всем сценариям", "fn": cmd_all},
    {"name": "sweep", "arg": "[--seeds N]", "help": "массовый прогон по случайным графам", "fn": cmd_sweep},
    {"name": "selfcheck", "arg": "[--seeds N]", "help": "сверить оракул независимым перебором", "fn": cmd_selfcheck},
    {"name": "analyze", "arg": "", "help": "типизированный разбор: вердикт, причина, план", "fn": cmd_analyze},
    {"name": "mode", "arg": "[work|lab|mind]", "help": "фокус панели: ядро / разбор / агент", "fn": cmd_mode},
    {"name": "ask", "arg": "<вопрос>", "help": "спросить агента", "fn": cmd_ask},
    {"name": "ai", "arg": "", "help": "состояние языковой модели", "fn": cmd_ai},
    {"name": "doctor", "arg": "[base|oracle]", "help": "диагностика: где теряются такты и почему", "fn": cmd_doctor},
    {"name": "load", "arg": "<файл.s>", "help": "загрузить настоящий .s от lcc и разобрать", "fn": cmd_load},
    {"name": "learned", "arg": "[адаптер] [--raw]", "help": "прогнать обученную модель на текущем графе (локально)", "fn": cmd_learned},
    {"name": "verify", "arg": "[--show]", "help": "переснять матрицу портов у ассемблера e2k прямо сейчас", "fn": cmd_verify},
    {"name": "validate", "arg": "<файл.jsonl…>", "help": "прогнать jsonl через настоящий Schedule.validate()", "fn": cmd_validate},
    {"name": "report", "arg": "[--dir …]", "help": "свести дампы прогонов в таблицу с дельтами", "fn": cmd_report},
    {"name": "kaggle", "arg": "[step0|run1|all|pull|status]", "help": "залить/забрать/проверить Kaggle", "fn": cmd_kaggle},
    {"name": "status", "arg": "", "help": "контекст сессии: сценарий, машина, результат", "fn": cmd_status},
    {"name": "theme", "arg": "[имя]", "help": "темы оформления; переключить тему", "fn": cmd_theme},
    {"name": "work", "arg": "", "help": "ядра интерпретатора и синтаксис записи", "fn": cmd_work},
    {"name": "docs", "arg": "", "help": "что это за прототип и зачем", "fn": cmd_docs},
    {"name": "agent", "arg": "", "help": "куда встраивается обученная модель", "fn": cmd_agent},
    {"name": "clear", "arg": "", "help": "очистить экран и вернуться к выбору режима", "fn": cmd_clear},
    {"name": "help", "arg": "", "help": "список команд", "fn": cmd_help},
]
_ALIASES = {"ls": "scenarios", "cmp": "compare", "r": "run", "cls": "clear"}
_BY_NAME = {c["name"]: c for c in COMMANDS}


def resolve(name: str):
    name = _ALIASES.get(name, name)
    if name in _BY_NAME:
        return _BY_NAME[name]
    pref = [c for c in COMMANDS if c["name"].startswith(name)]
    return pref[0] if len(pref) == 1 else None


def suggest(name: str) -> list[str]:
    """Похожие имена команд — для «может, вы имели в виду /x?» при опечатке."""
    names = [c["name"] for c in COMMANDS] + list(_ALIASES)
    return difflib.get_close_matches(name, names, n=3, cutoff=0.5)


# --------------------------------------------------------------------------
# readline: Tab-дополнение и персистентная история (см. импорт в шапке файла)
# --------------------------------------------------------------------------

HISTORY_FILE = Path.home() / ".vliw_history"
HISTORY_SIZE = 1000

# Что дополнять во втором слове — по имени команды в первом.
_ARG_COMPLETIONS = {
    "run": lambda: list(SCENARIOS),
    "compare": lambda: list(SCENARIOS),
    "random": lambda: list(SCENARIOS),  # необязательно, но не мешает
    "model": lambda: list(PROFILES) + ["measured", "naive"],
    "play": lambda: ["baseline", "oracle"],
    "asm": lambda: ["baseline", "oracle"],
    "doctor": lambda: ["baseline", "oracle"],
    "kaggle": lambda: ["step0", "run1", "all", "pull", "status"],
    "learned": lambda: [a.name for a in _learned_adapters()],
}


def _learned_adapters():
    """Имена найденных адаптеров — для Tab-дополнения. Молча пусто, если нет."""
    try:
        from .learned import runtime

        return runtime.find_adapters()
    except Exception:
        return []


def _completer(text: str, state: int):
    """Tab-дополнение: первое слово — имя команды, второе — по контексту.

    readline вызывает эту функцию с растущим `state` (0, 1, 2, …) и ждёт
    поочерёдно все подходящие варианты, затем `None` как сигнал «дальше нет».
    """
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
    """Включить Tab-дополнение и загрузить историю прошлых сессий."""
    if not HAS_READLINE:
        return
    readline.set_completer(_completer)
    # Только пробел разделяет «слова» — так весь токен «/compare» дополняется
    # целиком, а не рвётся на «/» и «compare» (у «/» иначе особый смысл).
    readline.set_completer_delims(" \t\n")
    try:
        readline.parse_and_bind("tab: complete")
    except Exception:  # pragma: no cover - экзотические сборки readline/libedit
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
        pass  # история — приятная мелочь, не повод падать


def _parse_opts(arg: str, defaults: dict) -> dict:
    """Разобрать «--key value» из строки аргумента, дополнив значениями по умолчанию."""
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


# В полноэкранном режиме клавиатурой владеет curses, поэтому пошаговая пауза
# через input() там невозможна: /play печатает расписание целиком, а листает
# его пользователь прокруткой (PgUp/PgDn).
IN_TUI = False

# Идёт ли построчный интерактивный цикл. Нужен командам, которые спрашивают
# что-то у пользователя (`/clear` показывает экран выбора приложения): в разовом
# запуске из скрипта спрашивать нельзя — там никто не отвечает.
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
# Диспетчер и интерактивный цикл
# --------------------------------------------------------------------------


def _run_dag(session: Session, dag) -> bool:
    session.set_dag(dag, dag.key)
    cmd_run(session, "")
    return True


def _apply_mode(session: Session, name: str | None) -> None:
    """Выставить focus/mode по алиасу панели."""
    from .ui import panes

    dest = panes.resolve_focus(name or "lab") or "lab"
    session.focus = dest
    session.mode = "chat" if dest == "mind" else "explore"


def classify_pane(session: Session, raw: str) -> str:
    """Куда класть вывод: интерпретатор, разбор или агент."""
    from .ui import panes

    s = raw.strip()
    head = s.lstrip("/").split()[0].lower() if s else ""
    cmd = resolve(head)
    name = cmd["name"] if cmd else None
    known = session.workspace().regs if session._workspace else None
    return panes.classify(s, name, looks_like_work(s, known),
                          getattr(session, "focus", "lab"))


def _exec_work(session: Session, s: str) -> bool:
    from .ui import interp_view

    session.last_work = s
    session.focus = "work"
    try:
        result = session.workspace().exec(s)
    except InterpError as e:
        print(paint("error", f"интерпретатор: {e}"))
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
    """Команда CLI, строка интерпретатора, сценарий или вопрос агенту."""
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
            print(paint("error", f"агент: {e}"))
            return False

    if " " not in s and len(name) <= 20:
        return dispatch(session, name, arg)
    print(Style.dim("  это не команда.  /help  ·  a=load  ·  вопрос обычным языком"))
    return False


def dispatch(session: Session, name: str, arg: str) -> bool:
    """Выполнить команду. Возвращает False на нераспознанном имени — этим

    пользуется одноразовый вызов из `main()`, чтобы вернуть код возврата 1
    (а не молча выйти с 0: скрипт, вызвавший опечатанную команду, должен это
    увидеть по `$?`, а не только по тексту в stdout).
    """
    name = name.lstrip("/").lower()
    if not name:  # голое «/» (или пусто) — то же самое, что /help
        cmd_help(session, "")
        return True
    cmd = resolve(name)
    if cmd is None:
        msg = paint("error", f"неизвестная команда /{name}.")
        hints = suggest(name)
        if hints:
            msg += Style.dim("  Может, вы имели в виду: ") + ", ".join(
                paint("accent", "/" + h) for h in hints) + Style.dim("?")
        else:
            msg += Style.dim(" Наберите /help — список команд.")
        print(msg)
        return False
    # Команда может сообщить о неудаче, вернув False — тогда разовый
    # вызов завершится кодом 1, и скрипт это увидит по $?.
    return cmd["fn"](session, arg) is not False


def _prompt(session: Session) -> str:
    _ = session
    return paint("prompt", "nex ") + Style.dim("▸ ")

# Маркеры «bracketed paste»: некоторые терминалы оборачивают вставленный текст
# в ESC[200~ … ESC[201~. input() вернёт их как обычные символы — вырезаем.
_PASTE_MARK = re.compile("\x1b\\[20[01]~")


def _tui_complete(buf: str) -> list[str]:
    if not buf.startswith("/"):
        buf = "/" + buf
    return slash.complete_plain(buf, COMMANDS)


def _fullscreen_ok() -> bool:
    """Есть ли хоть один полноэкранный интерфейс: новый или прежний."""
    from .ui import tui as curses_tui

    try:
        from . import tui as nextui

        if nextui.available():
            return True
    except Exception:
        pass
    return curses_tui.available()


def run_tui(session: Session, pick_app: bool | None = None) -> int:
    """Полноэкранный интерфейс. При любой проблеме — обычный цикл.

    Порядок отката: Textual (три полноценных экрана) → прежний curses-экран →
    построчный режим. Отдельный интерфейс на curses оставлен намеренно: Textual
    ставится отдельно, а инструмент должен запускаться и без него.
    """
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
        print(paint("warning", f"новый интерфейс не поднялся ({e}); "
                               "пробую прежний"))
    finally:
        IN_TUI = False

    IN_TUI = True
    try:
        from .ui import tui

        return tui.run(session, execute, COMMANDS, _tui_complete,
                       pick_app=pick_app, classify=classify_pane)
    except Exception as e:
        IN_TUI = False
        print(paint("warning", f"полноэкранный режим недоступен ({e}); "
                               "продолжаю в обычном режиме"))
        print_logo()
        return repl(session)
    finally:
        IN_TUI = False


def repl(session: Session) -> int:
    _setup_readline()
    print()
    hint = "ядро · разбор · агент.  /run slotclash  ·  sum 8  ·  вопрос. "
    if HAS_READLINE:
        hint += "Tab — дополнить, ↑/↓ — история. "
    hint += "/exit — выход."
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
        except EOFError:              # конец ввода (Ctrl+D / закрытый пайп)
            print()
            return 0
        except KeyboardInterrupt:     # Ctrl+C на приглашении — отменяем строку
            print("\n" + Style.dim("^C  (наберите /exit, чтобы выйти)"))
            continue

        line = _PASTE_MARK.sub("", line)
        s = line.strip()
        low = s.lower()

        if s == "" or low in ("/help", "help"):
            cmd_help(session, "")
            continue
        if low in ("/exit", "exit", "/quit", "quit"):
            print(Style.dim("пока!"))
            return 0
        try:
            handle_input(session, s)
        except KeyboardInterrupt:      # Ctrl+C во время команды — отменяем её
            print("\n" + Style.dim("^C  команда прервана"))
        except SystemExit as e:
            print(paint("error", str(e)))
        except Exception as e:         # одна кривая команда не роняет сессию
            print(paint("error", f"ошибка команды: {e}"))
    return 0


# --------------------------------------------------------------------------
# Разбор аргументов и точка входа
# --------------------------------------------------------------------------


def _commands_epilog() -> str:
    lines = ["команды (одинаковые что снаружи, что внутри цикла с «/»):", ""]
    width = max(len(c["name"]) + len(c["arg"]) for c in COMMANDS) + 3
    for c in COMMANDS:
        sig = (c["name"] + " " + c["arg"]).strip()
        lines.append(f"  {sig:<{width}} {c['help']}")
    lines += [
        "",
        "примеры:",
        "  python -m vliw run slotclash",
        "  python -m vliw compare --no-color",
        "  python -m vliw                      # без команды — интерактивный режим",
        "",
        "полная документация: docs/CLI.md",
    ]
    return "\n".join(lines)


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m vliw", add_help=True,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description="NEX CLI — планировщик VLIW на модели Elbrus e2k-v6. "
                    "Без аргументов — интерактивный режим; с командой — один запуск.",
        epilog=_commands_epilog(),
    )
    from . import VERSION_LABEL, __version__

    p.add_argument("--version", action="version",
                   version=f"NEX CLI {VERSION_LABEL}  ({__version__})",
                   help="показать версию и выйти")
    p.add_argument("--profile", choices=list(PROFILES), default=None, help="модель машины")
    p.add_argument("--width", type=int, default=None, help="переопределить число портов")
    p.add_argument("--budget", type=float, default=10.0, help="бюджет точного поиска, с")
    p.add_argument("--portfolio", type=float, default=3.0, help="бюджет запасного поиска, с")
    p.add_argument("--color", dest="color", action="store_true", default=None, help="включить цвет")
    p.add_argument("--no-color", dest="color", action="store_false", help="выключить цвет")
    p.add_argument("--theme", default=None, help="тема оформления (см. /theme)")
    p.add_argument("--mode",
                   choices=["work", "lab", "mind", "explore", "chat"],
                   default=None,
                   help="пропустить экран выбора: work / lab / mind")
    p.add_argument(
        "--plain", action="store_true",
        help="без полноэкранного режима: обычный построчный интерактив",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args, extras = parser.parse_known_args(argv)
    render.setup_output(args.color, args.theme)

    session = Session(args=args)
    _apply_mode(session, getattr(args, "mode", None) or "lab")
    if args.profile:
        session.profile = args.profile
    if args.width:
        session.width = args.width

    # Ctrl+C где угодно — аккуратный выход без трейсбека.
    try:
        if not extras:
            if not args.plain and args.color is not False and _fullscreen_ok():
                return run_tui(session)

            print_logo()
            chosen = launcher.prompt_plain()
            if not chosen:
                return 0
            _apply_mode(session, chosen)
            return repl(session)

        print_logo()

        # Один запуск команды и выход. Код возврата — по контракту для
        # скриптов/CI: 0 = успех, 1 = ошибка (неизвестная команда,
        # неизвестный сценарий/профиль, внутренняя проверка расписания и
        # т.п.), 130 = прервано Ctrl+C (ниже).
        # `python -m vliw lab` / `mind` — войти в workstation с фокусом панели.
        if extras[0].lower() in ("chat", "agent", "explore", "lab", "mind") \
                and len(extras) == 1:
            _apply_mode(session, extras[0])
            if not args.plain and args.color is not False and _fullscreen_ok():
                return run_tui(session, pick_app=False)
            print_logo()
            return repl(session)

        try:
            ok = handle_input(session, " ".join(extras))
        except SystemExit:
            raise
        except Exception as e:
            print(paint("error", f"ошибка команды: {e}"))
            return 1
        return 0 if ok else 1
    except KeyboardInterrupt:
        print("\n" + Style.dim("прервано (Ctrl+C)"))
        return 130
