"""Единая точка входа: команда → core → ui → печать.

  python -m vliw                 интерактив: выбор приложения, затем цикл
  python -m vliw run slotclash   одна команда и выход
  python -m vliw --plain         тот же цикл построчно, без полноэкранного

Три панели одного workstation:
  ядро   — интерпретатор (sum 8, своя запись)
  разбор — /run /compare /doctor
  агент  — вопрос обычным языком

Здесь только склейка. Логика планирования — в vliw.core.
"""

from __future__ import annotations

import argparse
import difflib
import itertools
import json
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
    event_sink: object = None
    """Куда отдавать события планировщика вместо печати.

    Ставит интерфейс на время команды. Пусто — печатаем построчно, как и
    раньше; занято — показывать поток берётся тот, кто его поставил (у него
    есть решётка, а у печати её нет).
    """
    dag_obj: DAG | None = None
    width: int | None = None
    delay: float | None = None  # пауза воспроизведения; None = по Enter
    mode: str = "explore"      # совместимость: explore ≈ lab, chat ≈ mind
    focus: str = "lab"         # work | lab | mind | code — какая панель в фокусе
    last_work: str = ""
    code_text: str = ""
    """Буфер исходника (ассемблер e2k) режима КОД.

    Живёт в сессии, а не в виджете: редактор его показывает, `/code run`
    прогоняет, умная вставка из любого режима кладёт сюда многострочный
    текст. Перезапуск инструмента буфер не переживает — как и черновик
    в любом редакторе без сохранения.
    """
    code_path: str = ""
    """Последний файл, куда буфер сохраняли / откуда загрузили: Ctrl+S в
    редакторе пишет туда без повторного вопроса."""
    code_run_text: str = ""
    """Текст буфера КОДА на момент последнего разбора (`/code run`, F5).

    Ставит `_load_parsed`, когда разобран именно буфер. Нужен индикатору
    спящих режимов в РАЗБОРЕ: «буфер изменён, не разобран» видно без захода
    в КОД. У экрана КОДА есть своя метка свежести (run_text), но она живёт
    только пока открыт экран — а эта переживает смену режимов.
    """
    journal_runs: list = field(default_factory=list)
    """Общий журнал прогонов сессии («гит сессии»).

    Один список на все экраны: ЯДРО, РАЗБОР, АГЕНТ и КОД пишут сюда каждый
    запуск, и из любого места к нему можно вернуться. У записи после
    выполнения появляются мостик-поля: сценарий, граф, профиль — по ним
    журнал отдаёт прогон в РАЗБОР, АГЕНТУ или ЯДРУ одной кнопкой. Ничего
    не уезжает само: что сделать общим, решает человек.
    """
    journal_events: list = field(default_factory=list)
    """Живой поток сессии отдельно от отчётов команд.

    Строки модели и пометки планировщика во время команды. Тоже один на
    все экраны: поток не принадлежит ни одному режиму, он принадлежит
    прогону, а прогон виден из журнала везде.
    """
    dialog: list = field(default_factory=list)
    """Переписка с агентом — ОДНА на сессию, как и журнал прогонов.

    Спрашивают агента из трёх мест: колонка справа в КОДЕ (быстрый вопрос
    про строку под курсором), вкладка АГЕНТ его нижнего дока и
    полноэкранный АГЕНТ. Пока история жила в виджетах, это были три РАЗНЫХ
    переписки: спросил в колонке, ушёл на весь экран — а там пусто, и
    ответа, ради которого уходил, уже нет. Продолжать разговор было нельзя
    нигде, кроме места, где он начат.

    Запись: `{"role": "you" | "nex", "text": str, "facts": list[str]}`.
    """

    pending_note: str = ""
    """Пометка для ЯДРА, ждущая показа (кладёт мостик из журнала)."""
    pending_question: str = ""
    """Вопрос, ждущий отправки в АГЕНТ (кладёт мостик из журнала)."""
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
        # Кэш результатов ключуется именем участка, а буфер КОДА всегда
        # зовётся `asm:буфер`: без сброса ВТОРОЙ F5 после правки отдавал
        # числа ПЕРВОГО прогона — правь сколько хочешь, «оракул 8 тактов»
        # не двигался. Новый граф под тем же именем — старому кэшу не родня.
        self._cache = {k: v for k, v in self._cache.items() if k[0] != label}
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
    """baseline и oracle бок о бок; `--model` добавляет третьим обученную.

    Модель НЕ подмешивается по умолчанию: она считается полминуты, а
    `/compare` должен оставаться мгновенным.
    """
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
        print(Style.dim("  добавить обученную модель третьей: /compare --model"))


def _compare_learned(session: Session, dag, model, hl):
    """Прогнать модель и напечатать её расписание третьим. None — не вышло."""
    from .learned import runtime

    ready, lines = runtime.status()
    if not ready:
        print()
        print(paint("warning", "  модель недоступна — показываю без неё"))
        print(Style.dim("  подробности: /learned --status"))
        return None

    adapter = runtime.resolve_adapter()
    print()
    print(paint("lab", f"  модель ({adapter.name}) считает, ~30 с:"))
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
        print(paint("error", f"  модель не отработала: {e}"))
        return None

    print()
    st = res.search_stats
    if st["valid"]:
        label = "  модель — обученная" + (
            " + починка каналов:" if st.get("repaired") else ":")
        _out(schedule_view.render_schedule(res.schedule, dag, model, hl,
                                           paint("lab", label)))
    else:
        print(paint("error", "  модель выдала незаконное расписание — "
                             "решётку не рисую:"))
        for e in st["errors"][:4]:
            print("    " + Style.dim(e))
    return res


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


# Потолок для `random N`. Замерено: 6000 узлов — 24 с и 644 МБ, 8000 не
# укладывается и в 30 с, а на 20 000 процесс убивает OOM-killer. Настоящие
# участки после lcc — сотни операций (real_candidates_100_400/), так что
# запас здесь на порядок больше любого реального случая.
MAX_RANDOM_N = 5000


def cmd_random(session: Session, arg: str) -> bool | None:
    parts = arg.split()
    n = 16
    seed = _random.randint(1, 10**6)
    if parts:
        try:
            n = int(parts[0])
        except ValueError:
            print(paint("error", f"число инструкций должно быть целым, "
                                 f"а не {parts[0]!r}"))
            return False
        # Раньше здесь стояло `max(3, ...)`: -5 молча превращалось в 3, и
        # инструмент считал не ту задачу, о которой его просили, ничего не
        # сказав. Отказ честнее подмены.
        if n < 3:
            print(paint("error", f"граф из {n} инструкций не бывает: "
                                 f"нужно 3 и больше"))
            return False
        # Верхняя граница — защита от OOM, а не вкусовщина. За генерацией
        # сразу идёт cmd_run, и планирование растёт заметно быстрее линейного:
        # 2000 узлов — 100 МБ, 4000 — 307 МБ, 6000 — 644 МБ, дальше процесс
        # съедал ~4 ГБ и его убивал OOM-killer с кодом 137. Бюджет точного
        # поиска (--budget) этот путь не ограничивает.
        if n > MAX_RANDOM_N:
            print(paint("error",
                        f"{n} инструкций — слишком крупный граф для одного "
                        f"участка (предел {MAX_RANDOM_N})"))
            _out(wrap("Планирование растёт быстрее линейного и на таких "
                      "размерах упирается в память, а не во время: --budget "
                      "здесь не спасает. Настоящие участки после lcc — сотни "
                      "операций, см. real_candidates_100_400/.",
                      render.W, "  "))
            return False
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


def cmd_hard(session: Session, arg: str) -> None:
    """Есть ли на графе что выигрывать у эвристики — и где такие графы брать.

    Появилась после замера `docs/CAB.md`: на обеих выборках проекта жадный
    планировщик стоит в доказанном оптимуме почти везде (298/300 и 300/300),
    то есть все прежние сравнения обученной модели шли на данных, где
    выигрывать нечего. Эта команда меряет тот самый бюджет, о котором
    говорит шапка `vliw/core/oracle.py`.
    """
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
        print(rule(f"трудность · {session.scenario}"))
        print()
        print(f"  жадная эвристика   {h.baseline:>4} т.")
        print(f"  оптимум            {h.optimum:>4} т."
              + Style.dim("   (доказан)" if h.proven else "   (НЕ доказан за бюджет)"))
        print()
        if not h.proven:
            print("  " + paint("warning",
                               "оптимум не доказан — граф нельзя назвать ни трудным, "
                               "ни лёгким"))
        elif h.hard:
            print("  " + paint("success",
                               f"ЗАЗОР {h.gap} т. — есть что выигрывать, модели есть "
                               "чем себя показать"))
        else:
            print("  " + paint("warning",
                               "ЗАЗОРА НЕТ — эвристика уже оптимальна, учить на этом "
                               "графе нечему"))
        print()
        print("  " + Style.dim("доля трудных среди случайных: /hard --survey 200"))
        print("  " + Style.dim("набрать трудных в файл:       /hard --harvest 50"))
        return None

    from tools.vliw_gen import PRESSURE_WEIGHTS, SHAPES, gen_graph

    def _dag(instrs):
        from .core.dag import DAG as _DAG, Instr as _I
        return _DAG("hard", "", "",
                    [_I(x.id, f"n{x.id}", x.op, x.preds, f"n{x.id}") for x in instrs])

    if n_survey:
        print(rule(f"опрос трудности · {n_survey} графов на смесь"))
        print()
        for label, weights in (("обычные веса", None),
                               ("давление на канал ,5", PRESSURE_WEIGHTS)):
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
            print(f"  {label:22} трудных {hard:>4}/{shown:<4} {paint_fn}      ")
        print()
        print("  " + Style.dim(
            "трудность делает не размер графа, а конкуренция за узкий порт: "
            "DIV живёт только на ,5"))
        return None

    print(rule(f"набор трудных графов · цель {n_harvest}"))
    print()
    from training.encode import encode_completion, encode_prompt

    # Замер 31.08.2026: доля графов с зазором растёт с размером — 0.8% при
    # n=12, 11.7% при n=20, 18.6% при n=32. Верхняя граница не в трудности, а
    # в оракуле: он перестаёт доказывать оптимум (5 из 120 при n=24) и
    # дорожает до 1.65 с на граф к n=32. 16..24 — окно, где трудных уже
    # много, а эталон ещё доказуем и дёшев.
    N_LO, N_HI = 16, 24
    profile = getattr(machine, "name", "e2k-v6-measured")
    kept, seen, t0 = [], 0, time.monotonic()
    limit = n_harvest * 400
    tasks = ((seed, N_LO, N_HI, profile) for seed in itertools.count(20260831))

    def _note(gap: int) -> None:
        if sys.stdout.isatty():
            print(f"  найдено {len(kept):>4}/{n_harvest}   просмотрено {seen}   "
                  f"зазор {gap} т.      ", end="\r")
            sys.stdout.flush()

    if n_jobs > 1:
        # Счёт независим по графам, поэтому масштабируется процессами почти
        # линейно. chunksize>1 — потому что задача секундная, а не миллисекундная:
        # раздавать по одной значит платить за передачу больше, чем считать.
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
    print(f"  найдено {len(kept)}/{n_harvest}, просмотрено {seen} "
          f"({100 * len(kept) / max(seen, 1):.1f}% годных) за {dt:.0f} с      ")
    print()
    print("  " + paint("success", f"записано в {out_path}"))
    if len(kept) < n_harvest:
        print("  " + paint("warning",
                           "цель не набрана: подними лимит просмотра или ослабь "
                           "требование к зазору"))
    return None


def cmd_isa(session: Session, arg: str) -> None:
    """Справочник системы команд: во что обходятся операции.

    МЦСТ систему команд не публикует, поэтому таблиц латентностей и портов
    для e2k публично не существует. Здесь они собираются генератором из
    `vliw/core/model.py` — из того самого, по чему инструмент считает, — и у
    каждого числа напечатан источник. См. `vliw/core/isa.py`.
    """
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
        print(rule("система команд"))
        _out(isa_view.render_terminal(rows))
        return None

    from . import VERSION_LABEL

    text = isa_view.render_markdown(rows, machine, VERSION_LABEL)
    out_path.write_text(text, encoding="utf-8")
    print(rule("система команд"))
    print()
    print("  " + paint("success", f"записано в {out_path}")
          + Style.dim(f"   {len(text.splitlines())} строк, "
                      f"{len(rows)} классов, "
                      f"{sum(len(r.mnemonics) for r in rows)} мнемоник"))
    return None


def _group_title(cmd: dict) -> str:
    gid = cmd.get("group", "session")
    return next((t for g, t in GROUPS if g == gid), gid)


def cmd_help(session: Session, arg: str) -> None:
    """Справка: без аргумента — все команды по группам, с аргументом — одна."""
    q = arg.strip().lstrip("/").lower()
    if q and q != "help":
        return _help_one(q)
    print(rule("клиент"))
    _hint()
    for gid, title in GROUPS:
        members = [c for c in COMMANDS if c.get("group") == gid]
        if not members:
            continue
        print()
        print(rule(title))
        rows = [[paint("accent", "/" + c["name"]), c["arg"], c["help"]]
                for c in members]
        for l in render.table(["команда", "аргументы", "что делает"], rows,
                              aligns="<<<"):
            print("  " + l)
        print(Style.dim(
            "  подробно: /help " + members[0]["name"]
            + (" … /help " + members[-1]["name"] if len(members) > 1 else "")))
    print()
    print(Style.dim("  в цикле со «/», снаружи без: python -m vliw run slotclash"))
    print(Style.dim("  ядро: sum 8  ·  агент: вопрос  ·  /exit"))


def _help_one(name: str) -> None:
    """Подробно об одной команде: сигнатура, докстринт, соседи по группе."""
    import inspect

    cmd = resolve(name)
    if cmd is None:
        msg = paint("error", f"нет команды /{name}.")
        hints = suggest(name)
        if hints:
            msg += Style.dim("  Похоже на: ") + ", ".join(
                paint("accent", "/" + h) for h in hints) + Style.dim("?")
        else:
            msg += Style.dim("  /help — список всех.")
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
        print(Style.dim("  рядом:  ") + Style.dim("   ".join(
            paint("accent", "/" + p["name"]) for p in peers)))
    return True


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


def _load_parsed(session: Session, parsed, label: str) -> bool:
    """Разобранный исходник → граф, расписание компилятора, отчёт.

    Общий путь `/load` (файл) и `/code run` (буфер редактора): разница
    только в том, откуда взялся текст.
    """
    if not parsed.ops:
        print(paint("error", "операций не нашлось — это точно .s-вывод lcc?"))
        return False

    model = session.model()
    dag = asm_parser.build_dag(parsed, key=f"asm:{label}", title=label)
    session.set_dag(dag, f"asm:{label}")
    # Метка «разобран ли буфер»: успешный прогон именно БУФЕРА запоминает
    # его текст. Правка после прогона снова сделает факт «изменён, не
    # разобран» видимым в РАЗБОРЕ; `/code load` метку не трогает нарочно —
    # загруженный файл разобран ещё не был.
    if label == "буфер":
        session.code_run_text = session.code_text

    cs, comp_problem = asm_parser.compiler_schedule_checked(parsed, dag, model)
    comp_cycles = cs.makespan if cs else None
    base, orc, met = session.results()

    print(rule("загружен · " + label))
    # Линтер зовём и здесь: до 0.9 его видел только полноэкранный КОД, и
    # `/load` на том же файле молчал про незаконные каналы.
    problems = list(parsed.problems) + asm_parser.lint(parsed, model)
    _out(diagnostics.render_parsed(parsed, dag, comp_cycles,
                                   orc.schedule.makespan, met.lower_bound,
                                   comp_problem, problems))
    session.compiler_sched = cs if comp_cycles is not None else None
    return True


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
    return _load_parsed(session, parsed, Path(path).name)


def cmd_code(session: Session, arg: str) -> None:
    """Буфер исходника: писать код прямо в инструменте и сразу его прогонять.

    `/code` — состояние буфера (в полноэкранном режиме ещё и подсказка, что
    редактор открывается выбором КОД или командой /code из строки),
    `/code run` — прогнать буфер как .s,
    `/code show` — буфер с номерами строк, `/code clear` — стереть,
    `/code load <файл.s>` — прочитать файл в буфер,
    `/code save <файл.s>` — записать буфер в файл.
    """
    sub, _, rest = arg.strip().partition(" ")
    sub = sub.lower()
    rest = rest.strip()

    if sub in ("run", "go"):
        if not session.code_text.strip():
            print(paint("error", "буфер КОДА пуст: открой редактор (режим КОД) "
                                 "или /code load <файл.s>"))
            return False
        try:
            parsed = asm_parser.parse_asm(session.code_text, source="<буфер>")
        except Exception as e:
            print(paint("error", f"не разобрать: {e}"))
            return False
        return _load_parsed(session, parsed, "буфер")

    if sub == "show":
        if not session.code_text.strip():
            print(Style.dim("  буфер КОДА пуст"))
            return True
        print(rule(f"буфер · {len(session.code_text.splitlines())} строк"))
        for i, line in enumerate(session.code_text.splitlines(), 1):
            print(f"  {i:>3}  {line}")
        return True

    if sub == "clear":
        session.code_text = ""
        print(paint("success", "буфер КОДА очищен"))
        return True

    if sub == "load":
        if not rest:
            print(paint("error", "укажите файл: /code load examples/probe.s"))
            return False
        try:
            session.code_text = Path(rest).read_text(encoding="utf-8",
                                                      errors="replace")
        except OSError as e:
            print(paint("error", f"не открыть файл: {e}"))
            return False
        session.code_path = rest
        n = len(session.code_text.splitlines())
        print(paint("success", f"в буфер КОДА: {rest} · {n} строк"
                    + Style.dim("   прогнать: /code run")))
        return True

    if sub == "save":
        if not session.code_text.strip():
            print(paint("error", "буфер пуст — сохранять нечего"))
            return False
        if not rest:
            print(paint("error", "укажите файл: /code save my.s"))
            return False
        try:
            Path(rest).write_text(session.code_text, encoding="utf-8")
        except OSError as e:
            print(paint("error", f"не записать файл: {e}"))
            return False
        session.code_path = rest
        print(paint("success", f"буфер КОДА → {rest}"
                    + Style.dim("   Ctrl+S сохранит туда же")))
        return True

    # голое /code и неизвестный подкомандный глагол — состояние буфера
    n = len(session.code_text.splitlines()) if session.code_text.strip() else 0
    print(rule("код"))
    if n:
        print(f"  буфер: {n} "
              + plural_ru(n, "строка", "строки", "строк")
              + Style.dim("   прогнать: /code run   показать: /code show"))
    else:
        print(Style.dim("  буфер пуст.  В полноэкранном режиме открой режим "
                        "КОД (клавиша 4) — там редактор."))
        print(Style.dim("  Или: /code load <файл.s> — прочитать готовый .s "
                        "в буфер."))
    return True


def plural_ru(n: int, one: str, few: str, many: str) -> str:
    if 11 <= n % 100 <= 14:
        return many
    return {1: one, 2: few, 3: few, 4: few}.get(n % 10, many)


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

    Ошибки СВОИХ данных ловим и пересказываем. Скрипт, запущенный отдельно,
    имеет право упасть трассировкой — это нормально для инструмента
    разработчика. Но здесь он вызван из интерактивной команды, и «Expecting
    value: line 1 column 1 (char 0)» вместо «файл не в формате jsonl» —
    это утечка внутренностей наружу: человек видит ошибку парсера JSON и не
    понимает, что подсунул не тот файл.
    """
    import json

    try:
        return main_fn(toks) in (0, None)
    except json.JSONDecodeError as exc:
        print(paint("error", f"файл не в формате jsonl (строка {exc.lineno}): "
                             f"здесь ждут по одному JSON-объекту на строку"))
        return False
    except FileNotFoundError as exc:
        print(paint("error", f"не открыть файл: {exc.filename}"))
        return False
    except (KeyError, ValueError) as exc:
        print(paint("error", f"файл разобран, но данные не те: {exc}"))
        return False


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


def _as_float(text: str) -> float:
    """Число или 0.0 — без падения. Негодное значение ловит проверка ниже."""
    try:
        return float(text)
    except (TypeError, ValueError):
        return 0.0


@dataclass
class _LearnedArgs:
    """Разобранные аргументы /learned. Чистая функция — ради тестов.

    Раньше парсинг жил внутри `cmd_learned`, и проверить его можно было
    только подняв модель. А ломается он тихо: «--temperature 0.7» —
    «0.7» не isdigit(), и его принимали за имя адаптера.
    """

    name: str | None = None
    bench: int = 0
    best_of: int = 0
    temperature: float = 0.0
    seed: int = 1
    constrained: bool = False
    cab: bool = False
    data: str = "eval_wide.jsonl"
    """Файл эвала для --bench. Появился, когда выяснилось, что на
    `eval_wide.jsonl` жадная эвристика оптимальна на 298 графах из 300 — то
    есть замер шёл на данных без задачи (docs/CAB.md)."""
    bad_value: tuple[str, str] | None = None
    """Числовой флаг с нечисловым значением: (флаг, что написали)."""
    raw: bool = False
    status: bool = False
    repair: bool = True


def _parse_learned(toks: list[str]) -> _LearnedArgs:
    """`--flag N` и `--flag=N` для всех флагов со значением."""
    a = _LearnedArgs()
    a.raw = "--raw" in toks
    a.status = "--status" in toks
    # Починка каналов включена по умолчанию: модель ошибается почти
    # исключительно в канале, а такты ставит верно. --pure выключает и
    # показывает сырой ответ модели как есть.
    a.repair = "--pure" not in toks
    # Токены-значения флагов (`--temperature 0.7`) не должны попасть в имя
    # адаптера: «0.7» не isdigit(), и прежняя проверка принимала его за имя.
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
            # float() здесь звался напрямую и на «--temperature ой» ронял
            # команду трассировкой ValueError. Значение проверяется ниже и
            # сообщается по-человечески.
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

    # Нечисловое значение у числового флага НЕ проглатываем молча. Прежде
    # «--bench 5o» тихо превращалось в «--bench 15», и человек ждал восемь
    # минут вместо двух, не понимая, почему примеров больше, чем он просил.
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
    """Запустить обученный адаптер на текущем графе — локально, без Kaggle.

    Без аргументов и без готовых весов/зависимостей — печатает отчёт о том,
    чего не хватает, и не падает: это самый частый случай на чужой машине.
    """
    from .learned import runtime
    from .ui import learned_view

    a = _parse_learned(arg.split())
    if a.bad_value:
        flag, value = a.bad_value
        print(paint("error", f"{flag} ждёт число, а получил {value!r}"))
        return False
    want_raw, want_status, want_repair = a.raw, a.status, a.repair
    n_bench, best_of_n, temperature, seed = a.bench, a.best_of, a.temperature, a.seed
    name = a.name

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

    from .learned import LearnedScheduler as _LS

    machine = session.model()
    if n_bench:
        data = Path(a.data)
        if not data.exists():
            print(paint("error", f"нет файла эвала {data} — замер не на чем гонять"))
            return False
        if best_of_n and temperature <= 0:
            print(paint("error",
                        "best-of имеет смысл только при --temperature > 0: "
                        "при жадной генерации все N ответов одинаковы"))
            return False
        # Температура без --best-of — тоже законный замер: один сэмплированный
        # ответ. Классифицируется как best-of-1.
        if temperature > 0 and not best_of_n:
            best_of_n = 1
        bo = None
        if best_of_n:
            from .learned.bench import BestOf

            bo = BestOf(n=best_of_n, temperature=temperature, seed=seed)
        gens = n_bench * max(1, best_of_n)
        print(rule(f"замер · {adapter.name} · {n_bench} примеров"
                   + (f" · best-of {best_of_n} · t={temperature:g}" if bo else "")))
        print(Style.dim(f"  локально, без Kaggle. Порядка 30 с на генерацию — "
                        f"ожидаемо {gens * 30 // 60} мин."))
        print()
        sys.stdout.flush()
        from .learned import bench as _bench

        def _tick(k, row):
            mark = paint("success", "ok  ") if row.kind == "валидно" else paint("error", "….  ")
            extra = (f"сэмплы {row.valid_samples}/{len(row.samples)}  "
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
            print(paint("error", f"замер прерван: {e}"))
            return False
        print()
        _out(learned_view.render_bench(res, adapter.name))
        return None

    dag = session.dag_obj
    print(rule(f"обученный планировщик · {adapter.name} · {session.scenario}"))
    print("  " + _header(session))
    print()
    sys.stdout.flush()

    sch = LearnedScheduler(adapter=adapter, repair=want_repair,
                           constrained=a.constrained, cab=a.cab)
    if a.constrained:
        print("  " + Style.dim(
            "ограниченная генерация: формат и канал заданы грамматикой, "
            "такты по-прежнему выбирает модель"))
        print()
    if a.cab:
        print("  " + Style.dim(
            "портфель CAB: из одного ответа строится несколько законных "
            "расписаний, лучшее выбирает точный критерий"))
        print()
    renderer = learned_view.PlainRenderer()
    res = None
    failed = None

    # Поток событий, а не один блокирующий вызов. Здесь разницы почти не
    # видно — печать та же, — но поток один и тот же для всех интерфейсов:
    # полноэкранный заливает по нему решётку, пока модель пишет. Заодно
    # прерывание теперь доходит до модели: закрытие генератора убивает
    # подпроцесс llama.cpp, а не оставляет его считать в одиночестве.
    sink = session.event_sink
    events = core.stream(sch, dag, machine)
    try:
        for ev in events:
            if sink is not None:
                # Показывает тот, кто поставил сток: у него решётка, и он
                # умеет то, чего печать не умеет. Дублировать поток ещё и в
                # stdout нельзя — мост покажет его вторым экземпляром в конце.
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
                    f"не удалось запустить модель: {failed or 'нет ответа'}"))
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
    # Вывод подпроцесса ПЕРЕПЕЧАТЫВАЕТСЯ через print(), а не наследует stdout.
    # В betaNEX панель показывает то, что bridge.run_command перехватил через
    # contextlib.redirect_stdout — это подмена на уровне Python. Подпроцесс с
    # наследованным дескриптором пишет мимо неё, прямо в терминал ПОД
    # интерфейсом: вывод пропадает из панели и портит отрисовку. Построчное
    # чтение заодно сохраняет живой поток — заливка идёт минутами, и ждать
    # её молчащим окном нельзя.
    proc = subprocess.Popen([str(script), mode], stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, text=True, bufsize=1)
    for line in proc.stdout:
        print(line, end="")
    proc.wait()
    if proc.returncode != 0:
        return False


# --------------------------------------------------------------------------
# Реестр команд
#
# Команды сгруппированы по занятию («расписание», «машина», …): так читается
# и /help, и палитра «/». Порядок в списке = порядок внутри группы, порядок
# GROUPS = порядок групп в справке.
# --------------------------------------------------------------------------

COMMANDS = [
    # --- расписание -------------------------------------------------------
    {"group": "sched", "name": "run", "arg": "<сценарий>", "help": "прогнать сценарий: расписание оракула + вердикт", "fn": cmd_run},
    {"group": "sched", "name": "compare", "arg": "[сценарий] [--model]", "help": "baseline и oracle бок о бок", "fn": cmd_compare},
    {"group": "sched", "name": "play", "arg": "[base|oracle]", "help": "воспроизвести расписание такт за тактом", "fn": cmd_play},
    {"group": "sched", "name": "asm", "arg": "[base|oracle]", "help": "расписание как широкие команды e2k { … }", "fn": cmd_asm},
    {"group": "sched", "name": "explain", "arg": "<такт>", "help": "почему в этом такте выбрали именно это", "fn": cmd_explain},
    # --- граф · диагноз -----------------------------------------------------
    {"group": "graph", "name": "path", "arg": "", "help": "граф с подсветкой критического пути", "fn": cmd_path},
    {"group": "graph", "name": "bounds", "arg": "", "help": "две нижние границы makespan", "fn": cmd_bounds},
    {"group": "graph", "name": "doctor", "arg": "[base|oracle]", "help": "диагностика: где теряются такты и почему", "fn": cmd_doctor},
    {"group": "graph", "name": "analyze", "arg": "", "help": "типизированный разбор: вердикт, причина, план", "fn": cmd_analyze},
    # --- модель машины ------------------------------------------------------
    {"group": "machine", "name": "model", "arg": "[профиль]", "help": "матрица возможностей портов; смена профиля", "fn": cmd_model},
    {"group": "machine", "name": "probe", "arg": "", "help": "как probe.c измерил модель машины e2k", "fn": cmd_probe},
    {"group": "machine", "name": "isa", "arg": "[--out ФАЙЛ]", "help": "справочник системы команд: каналы, латентности, темп приёма и чем измерено", "fn": cmd_isa},
    {"group": "machine", "name": "verify", "arg": "[--show]", "help": "переснять матрицу портов у ассемблера e2k прямо сейчас", "fn": cmd_verify},
    # --- прогоны ------------------------------------------------------------
    {"group": "runs", "name": "scenarios", "arg": "", "help": "список доступных сценариев", "fn": cmd_scenarios},
    {"group": "runs", "name": "random", "arg": "[N] [seed]", "help": "случайный граф на N инструкций и прогон", "fn": cmd_random},
    {"group": "runs", "name": "all", "arg": "", "help": "сводная таблица по всем сценариям", "fn": cmd_all},
    {"group": "runs", "name": "sweep", "arg": "[--seeds N]", "help": "массовый прогон по случайным графам", "fn": cmd_sweep},
    {"group": "runs", "name": "selfcheck", "arg": "[--seeds N]", "help": "сверить оракул независимым перебором", "fn": cmd_selfcheck},
    {"group": "runs", "name": "hard", "arg": "[--survey N] [--harvest N] [--jobs N]", "help": "есть ли на графе что выигрывать у эвристики; где брать трудные графы", "fn": cmd_hard},
    # --- агент · обучение ---------------------------------------------------
    {"group": "agent", "name": "ask", "arg": "<вопрос>", "help": "спросить агента", "fn": cmd_ask},
    {"group": "agent", "name": "ai", "arg": "", "help": "состояние языковой модели", "fn": cmd_ai},
    {"group": "agent", "name": "learned", "arg": "[--cab] [--constrained] [--bench N] [--data ФАЙЛ] [--pure]", "help": "прогнать обученную модель на текущем графе (локально)", "fn": cmd_learned},
    {"group": "agent", "name": "agent", "arg": "", "help": "куда встраивается обученная модель", "fn": cmd_agent},
    # --- данные ---------------------------------------------------------------
    {"group": "data", "name": "code", "arg": "[run|show|save|load|clear]", "help": "буфер исходника e2k: редактор КОД (клавиша 4), прогон, файлы", "fn": cmd_code},
    {"group": "data", "name": "load", "arg": "<файл.s>", "help": "загрузить настоящий .s от lcc и разобрать", "fn": cmd_load},
    {"group": "data", "name": "validate", "arg": "<файл.jsonl…>", "help": "прогнать jsonl через настоящий Schedule.validate()", "fn": cmd_validate},
    {"group": "data", "name": "report", "arg": "[--dir …]", "help": "свести дампы прогонов в таблицу с дельтами", "fn": cmd_report},
    {"group": "data", "name": "kaggle", "arg": "[step0|run1|all|pull|status]", "help": "залить/забрать/проверить Kaggle", "fn": cmd_kaggle},
    # --- сессия ----------------------------------------------------------------
    {"group": "session", "name": "status", "arg": "", "help": "контекст сессии: сценарий, машина, результат", "fn": cmd_status},
    {"group": "session", "name": "theme", "arg": "[имя]", "help": "темы оформления; переключить тему", "fn": cmd_theme},
    {"group": "session", "name": "work", "arg": "", "help": "ядра интерпретатора и синтаксис записи", "fn": cmd_work},
    {"group": "session", "name": "docs", "arg": "", "help": "что это за прототип и зачем", "fn": cmd_docs},
    {"group": "session", "name": "mode", "arg": "[work|lab|mind]", "help": "фокус панели: ядро / разбор / агент", "fn": cmd_mode},
    {"group": "session", "name": "clear", "arg": "", "help": "очистить экран и вернуться к выбору режима", "fn": cmd_clear},
    {"group": "session", "name": "help", "arg": "", "help": "список команд; «help <команда>» — подробнее", "fn": cmd_help},
]

#: Порядок групп в справке и палитре — единый, из ui.slash (см. комментарий там).
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


# В полноэкранном режиме экраном владеет Textual, поэтому пошаговая пауза
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


def _fullscreen_ok() -> bool:
    """Поднимается ли полноэкранный интерфейс (Textual)."""
    try:
        from . import tui as nextui

        return nextui.available()
    except Exception:
        return False


def run_tui(session: Session, pick_app: bool | None = None) -> int:
    """Полноэкранный интерфейс. При любой проблеме — обычный цикл.

    Порядок отката: Textual (три полноценных экрана) → построчный режим.
    Прежний однооконный экран на curses удалён: Textual покрывает всё, что он
    умел, а держать третий интерфейс означало трижды править каждую правку.
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
        print(paint("warning", f"полноэкранный режим недоступен ({e}); "
                               "продолжаю в обычном режиме"))
    finally:
        IN_TUI = False

    print_logo()
    return repl(session)


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
    lines = ["команды (одинаковые что снаружи, что внутри цикла с «/»):"]
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
        "подробнее о команде:  python -m vliw help <команда>",
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
                   choices=["work", "lab", "mind", "code", "explore", "chat"],
                   default=None,
                   help="пропустить экран выбора: work / lab / mind / code")
    p.add_argument(
        "--plain", action="store_true",
        help="без полноэкранного режима: обычный построчный интерактив",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    # UTF-8 включаем ДО разбора аргументов. `--help` обрабатывается внутри
    # parse_known_args() и завершает процесс там же, поэтому перекодировка из
    # setup_output() до справки не доходила никогда: на Windows с кодовой
    # страницей cp1251/cp866 вся русская справка выводилась как «▯▯▯», хотя
    # обычные команды печатались нормально.
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    parser = _build_parser()
    args, extras = parser.parse_known_args(argv)
    render.setup_output(args.color, args.theme)

    session = Session(args=args)
    _apply_mode(session, getattr(args, "mode", None) or "lab")
    if args.profile:
        session.profile = args.profile
    # Ширину проверяем здесь, до первого использования. Без проверки одно и то
    # же «невозможное» значение давало три разных исхода: 0 молча игнорировался
    # (falsy — откат на профиль), -1 порождал машину с именем `.../w-1` и
    # рапортовал «1 портов», а -3 и ниже роняли наружу `IndexError` из
    # with_width() — там цикл добора портов не выполняется ни разу и `kept`
    # остаётся пустым списком.
    if args.width is not None and args.width < 1:
        print(paint("error", f"ширина машины не может быть {args.width}: "
                             f"нужно целое от 1 и выше"))
        return 1
    if args.width:
        session.width = args.width

    # Ctrl+C где угодно — аккуратный выход без трейсбека.
    try:
        if not extras:
            if not args.plain and args.color is not False and _fullscreen_ok():
                return run_tui(session)

            print_logo()
            # `--mode` пропускает экран выбора и здесь. Полноэкранный режим так
            # и делал (`pick_app = args.mode is None`), а построчный применял
            # режим и тут же затирал его вопросом «наберите 1, 2 или 3» — флаг,
            # обещающий в справке «пропустить экран выбора», в `--plain` не
            # работал вовсе.
            if getattr(args, "mode", None) is None:
                chosen = launcher.prompt_plain()
                if not chosen:
                    return 0
                _apply_mode(session, chosen)
            return repl(session)

        # Логотипа здесь нет намеренно. Это путь одного запуска — для
        # скриптов, пайпов и CI (контракт кода возврата описан ниже).
        # Баннер в такой вывод не лезет: он попадал в перенаправленный файл,
        # в `| grep`, в отчёты испытателей — везде, где нужен только результат.
        # В интерактивных путях (REPL, возврат из полноэкранного режима,
        # экран выбора) логотип остаётся — там он к месту.

        # Один запуск команды и выход. Код возврата — по контракту для
        # скриптов/CI: 0 = успех, 1 = ошибка (неизвестная команда,
        # неизвестный сценарий/профиль, внутренняя проверка расписания и
        # т.п.), 130 = прервано Ctrl+C (ниже).
        # `python -m vliw lab` / `mind` / `code` — войти в workstation с фокусом панели.
        # «agent» из этого списка убран намеренно. Слово занято командой
        # `agent` («куда встраивается обученная модель», см. COMMANDS) — она
        # документирована в --help, а позиционный режим `agent` не описан
        # нигде. Пока он стоял здесь, он перехватывал команду: `python -m vliw
        # agent` вместо справки уходил в интерактивный цикл и висел на
        # приглашении до таймаута. Диалоговый режим по-прежнему доступен как
        # `chat`, `mind` и `--mode mind`.
        if extras[0].lower() in ("chat", "explore", "lab", "mind",
                                 "code") \
                and len(extras) == 1:
            _apply_mode(session, extras[0])
            if not args.plain and args.color is not False and _fullscreen_ok():
                return run_tui(session, pick_app=False)
            print_logo()
            return repl(session)

        # `run <сценарий>`, `load <файл>` и разборы того же участка (compare,
        # doctor, bounds, path, analyze) смотрят на ОДИН граф — для них есть
        # готовый экран, и печатать вместо него отчёт незачем: в живом
        # терминале со стоящим textual инструмент открывается сразу на этом
        # участке, а не пересказывает его текстом. Так задумано с самого
        # начала — это не поведение по умолчанию для тех, кому текст удобнее,
        # это единственное поведение.
        # `sweep`, `selfcheck`, `all`, `scenarios` сюда не входят намеренно:
        # это прогоны по сотням графов разом, а не разбор одного участка, и
        # single-screen представления для них попросту нет — печатать таблицу
        # по 200 графам как «графический экран» бессмысленно, а не неудобно.
        _SINGLE_GRAPH_CMDS = {"run", "load", "compare", "doctor", "bounds",
                              "path", "analyze"}
        cmd_name = extras[0].lower()
        if (cmd_name in _SINGLE_GRAPH_CMDS and not args.plain
                and args.color is not False and _fullscreen_ok()):
            try:
                if cmd_name == "run" and len(extras) > 1:
                    session.set_scenario(extras[1])
                elif cmd_name == "load" and len(extras) > 1:
                    handle_input(session, " ".join(extras))
            except SystemExit:
                raise
            except Exception as e:
                print(paint("error", f"ошибка команды: {e}"))
                return 1
            _apply_mode(session, "lab")
            return run_tui(session, pick_app=False)

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
