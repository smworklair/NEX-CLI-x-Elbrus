"""Визуализация расписания: пачки-рамки, каналы, такты, вердикт, разбор.

Всё здесь — чистые функции отрисовки: на входе готовые данные из `vliw.core`
(Schedule, DAG, MachineModel, DagMetrics, SchedulingResult), на выходе строки
для терминала. Одни и те же функции используются и в быстром вызове, и в
интерактивном цикле — оформление одинаковое.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..core import DAG, DagMetrics, MachineModel, Schedule, SchedulingResult
from . import render
from .render import (
    Style,
    ansi_box,
    cycles,
    op_legend,
    paint,
    paint_op,
    panel,
    plural,
    table,
    wrap,
)

# CRIT_CODE/DIVERGE_CODE берём через модуль (render.CRIT_CODE), а не прямым
# импортом: тема может смениться уже после импорта, и прямая привязка осталась
# бы со старым цветом.


def critical_set(dag: DAG, met: DagMetrics) -> set[int]:
    """Узлы критического пути: asap + height == длина критического пути."""
    return {
        i for i in range(len(dag))
        if met.asap[i] + met.height[i] == met.critical_path_bound
    }


# --------------------------------------------------------------------------
# Пачки (широкие команды) как рамки
# --------------------------------------------------------------------------


def _cell(dag: DAG, model: MachineModel, port: int, instr: int, hl: dict[int, str]) -> str:
    op = dag[instr].op
    nm = dag[instr].name
    label = Style.dim(model.port_label(port))
    body = paint(hl[instr], nm) if instr in hl else paint_op(op, nm)
    return f"{label} {paint_op(op, op)} {body}"


def _bundle_lines(dag, model, cycle, heads, held, hl) -> list[str]:
    cells = [_cell(dag, model, p, i, hl) for p, i in heads]
    body = "   ".join(cells)
    extra = [Style.dim(f"{model.port_label(p)} ↓{dag[i].op}") for p, i in held]
    if extra:
        body += "   " + " ".join(extra)
    title = f"такт {cycle} · {'1 оп' if len(heads) == 1 else str(len(heads)) + ' оп'}"
    full = len(heads) == model.width
    if full:
        title += " · полная пачка"
    return ansi_box([body], title=title, color="success" if full else "border")


def schedule_items(sched: Schedule, dag: DAG, model: MachineModel):
    """('bundle', t, heads, held) | ('wait', t0, t1, held)."""
    busy = sched.busy_map()
    heads_by: dict[int, list] = {}
    held_by: dict[int, list] = {}
    for (c, p), (i, is_head) in busy.items():
        (heads_by if is_head else held_by).setdefault(c, []).append((p, i))
    last = max([*heads_by, *held_by], default=0)
    items = []
    t = 0
    while t <= last:
        if t in heads_by:
            items.append(("bundle", t, sorted(heads_by[t]), sorted(held_by.get(t, []))))
            t += 1
            continue
        run = t
        while run + 1 <= last and (run + 1) not in heads_by:
            run += 1
        held = sorted({(p, i) for c in range(t, run + 1) for p, i in held_by.get(c, [])})
        items.append(("wait", t, run, held))
        t = run + 1
    return items


def _wait_line(dag, model, sched, t0, t1, held) -> str:
    span = t1 - t0 + 1
    label = f"т.{t0}..{t1}" if span > 1 else f"т.{t0}"
    if held:
        who = ", ".join(
            f"{paint_op(dag[i].op, dag[i].name)} держит {model.port_label(p)} до т."
            f"{sched.placements[i].cycle + model.occupancy(dag[i].op)}"
            for p, i in held
        )
        note = paint("error", f"⏳ {cycles(span)} без выдачи") + Style.dim(f" — {who}")
    else:
        note = paint("error", f"⏳ {cycles(span)} без выдачи") + Style.dim(" — ждём операндов")
    return Style.dim(f"  {label:>10}  ") + note


def render_item(dag, model, sched, item, hl) -> list[str]:
    """Одна пачка (рамкой) или строка ожидания — для пошагового воспроизведения."""
    if item[0] == "bundle":
        _, t, heads, held = item
        return ["  " + l for l in _bundle_lines(dag, model, t, heads, held, hl)]
    _, t0, t1, held = item
    return [_wait_line(dag, model, sched, t0, t1, held)]


# --------------------------------------------------------------------------
# Расписание как сетка «такты × порты» — основной вид
# --------------------------------------------------------------------------

CONT = "│"      # операция продолжает занимать порт
EMPTY = "·"     # слот пуст


def _cell_width(dag: DAG, avail: int, nports: int) -> int:
    longest = max((len(i.name) + len(i.op) + 1 for i in dag), default=8)
    return max(6, min(longest + 1, (avail - 7) // nports))


def render_grid(sched: Schedule, dag: DAG, model: MachineModel,
                hl: dict[int, str] | None = None, title: str = "") -> list[str]:
    """Расписание сеткой: строки — такты, столбцы — порты машины.

    Так устроена сама широкая команда, поэтому таблица читается прямо как
    состояние машины: видно, какой порт чем занят в каждом такте и где
    простаивает. Раньше на каждый такт рисовалась отдельная рамка — три
    строки экрана ради одной операции, и структура машины терялась.

    Длинные серии тактов без выдачи схлопываются в одну строку: иначе
    тринадцать одинаковых строк ожидания деления заслоняют всё остальное.
    """
    hl = hl or {}
    busy = sched.busy_map()
    ports = list(model.ports)
    cw = _cell_width(dag, render.W, len(ports))
    sole = model.sole_host_ops()

    out: list[str] = []
    if title:
        out.append(title)

    head = Style.dim(f"{'такт':>5}  ")
    for p in ports:
        label = model.port_label(p.index)
        if p.index in sole:
            label += "*"
        role = "accent2" if p.index in sole else "dim"
        head += paint(role, label.center(cw))
    out.append(head)
    out.append(Style.dim(f"{'':>5}  " + "─" * (cw * len(ports))))

    last = max((pl.cycle for pl in sched.placements.values()), default=0)

    def row_cells(t: int) -> tuple[str, int, int]:
        cells, heads, held = "", 0, 0
        for p in ports:
            hit = busy.get((t, p.index))
            if hit is None:
                cells += Style.dim(EMPTY.center(cw))
                continue
            instr, is_head = hit
            if is_head:
                heads += 1
                txt = f"{dag[instr].op} {dag[instr].name}"[: cw - 1]
                code = hl.get(instr)
                cells += (paint(code, txt.center(cw)) if code
                          else paint_op(dag[instr].op, txt.center(cw)))
            else:
                held += 1
                cells += Style.dim(CONT.center(cw))
        return cells, heads, held

    t = 0
    while t <= last:
        cells, heads, held = row_cells(t)
        if heads == 0:
            run = t
            while run + 1 <= last and row_cells(run + 1)[1] == 0:
                run += 1
            span = run - t + 1
            if span >= 2:
                label = f"{t}–{run}"
                row = Style.dim(f"{label:>5}  ") + cells
                # Подпись добавляем, только если строка ещё влезает в ширину:
                # иначе она уползала под боковую панель и обрубалась.
                note = f"  {span} т., " + ("порт занят" if held else "ждём операндов")
                if render.vlen(row) + len(note) <= render.W:
                    row += Style.dim(note)
                out.append(row)
                t = run + 1
                continue
        mark = ""
        if heads == len(ports):
            mark = paint("success", "  полная пачка")
        out.append(Style.dim(f"{t:>5}  ") + cells + mark)
        t += 1

    out.append(Style.dim(f"{'':>5}  * монопольный порт   {CONT} занят   {EMPTY} пусто"))
    return out


def render_schedule(sched, dag, model, hl, title) -> list[str]:
    """Совместимость: основной вид расписания — сетка."""
    return render_grid(sched, dag, model, hl, title)


# --------------------------------------------------------------------------
# Критический путь в графе
# --------------------------------------------------------------------------


def render_dag_path(dag: DAG, model: MachineModel, met: DagMetrics) -> list[str]:
    crit = critical_set(dag, met)
    rows = []
    for ins in dag:
        star = paint(render.CRIT_CODE, "★") if ins.id in crit else " "
        name = (paint(render.CRIT_CODE, ins.name) if ins.id in crit
                else paint_op(ins.op, ins.name))
        preds = ", ".join(dag[p].name for p in ins.preds) or Style.dim("—")
        rows.append([
            star, str(ins.id), name, paint_op(ins.op, ins.op),
            str(model.latency(ins.op)), preds,
            str(met.height[ins.id]), str(met.asap[ins.id]),
        ])
    out = list(table(
        ["", "#", "имя", "оп", "лат", "зависит от", "height", "asap"],
        rows, aligns=" ><<><>>",
    ))
    out.append("")
    out += wrap(Style.dim(
        "★ — узлы критического пути (asap + height = длина критического пути "
        f"{met.critical_path_bound}). Эту цепочку зависимостей не ускорит ни один "
        "планировщик; всё, что можно отыграть, — вокруг неё."), render.W - 2)
    return out


# --------------------------------------------------------------------------
# Нижние границы
# --------------------------------------------------------------------------


def render_bounds(dag: DAG, model: MachineModel, met: DagMetrics) -> list[str]:
    body = [
        f"по критическому пути      : {met.critical_path_bound} "
        f"{plural(met.critical_path_bound, 'такт', 'такта', 'тактов')}",
        "  (цепочку зависимостей не ускорить никаким планировщиком)",
        "",
        f"по пропускной способности : {met.resource_bound} "
        f"{plural(met.resource_bound, 'такт', 'такта', 'тактов')}",
        f"  ({len(dag)} операций делим на порты, которые их умеют исполнять)",
        "",
        f"итог: быстрее {met.lower_bound} "
        f"{plural(met.lower_bound, 'такт', 'такта', 'тактов')} не выполнить — "
        f"связывает {met.binding}",
    ]
    out = ["  " + l for l in panel(body, title="ДВЕ НИЖНИЕ ГРАНИЦЫ", color="border")]
    out.append("")
    out += wrap(Style.dim(
        "Разрыв между baseline и нижней границей — это бюджет, за который имеет "
        "смысл бороться. Смотри /compare."), render.W, "  ")
    return out


# --------------------------------------------------------------------------
# Вердикт
# --------------------------------------------------------------------------


def render_verdict(base: SchedulingResult, orc: SchedulingResult, met: DagMetrics) -> list[str]:
    """Вердикт акцентной полосой — тот же язык, что у поля ввода."""
    b, o = base.schedule.makespan, orc.schedule.makespan
    gap = b - o
    lb = met.lower_bound
    role = "success" if gap > 0 else "warning"
    bar = paint(role, "▌")

    if gap > 0:
        head = paint(role, f"выигрыш  −{gap} "
                           f"{plural(gap, 'такт', 'такта', 'тактов')}  "
                           f"из {b}  ({100 * gap / b:.0f}%)")
    else:
        head = paint(role, "разницы нет — эвристика уже оптимальна")

    if orc.optimal is True:
        note = paint("success", "оптимум доказан точным поиском")
    elif orc.optimal is False:
        note = paint("warning", "оптимальность не доказана (лучшее найденное)")
    else:
        note = Style.dim("оптимальность неизвестна")

    rows = [
        ("baseline", "эвристика", b),
        ("oracle", "точный поиск", o),
        ("предел", "быстрее невозможно", lb),
    ]
    out = [f"  {bar} {head}", f"  {bar}"]
    for name, why, val in rows:
        out.append("  " + bar + " "
                   + render.pad(paint("title", name), 12)
                   + render.pad(Style.dim(why), 24)
                   + render.pad(paint("title", str(val)), 4, ">")
                   + Style.dim(" т."))
    out.append(f"  {bar}")
    out.append(f"  {bar} {note}")
    return out




def render_stats_line(base: SchedulingResult, orc: SchedulingResult) -> str:
    bs, os_ = base.schedule, orc.schedule
    return Style.dim(
        f"  baseline {bs.makespan} т./{bs.bundle_count} пачек"
        f"   ·   oracle {os_.makespan} т./{os_.bundle_count} пачек"
    )


# --------------------------------------------------------------------------
# Расхождение baseline vs oracle
# --------------------------------------------------------------------------


@dataclass
class Divergence:
    cycle: int | None
    base_only: list[int]
    oracle_only: list[int]


def find_divergence(base: Schedule, orc: Schedule, dag: DAG) -> Divergence:
    last = max(
        max((p.cycle for p in base.placements.values()), default=0),
        max((p.cycle for p in orc.placements.values()), default=0),
    )
    for t in range(last + 1):
        b = {p.instr for p in base.placements.values() if p.cycle == t}
        o = {p.instr for p in orc.placements.values() if p.cycle == t}
        if b != o:
            return Divergence(t, sorted(b - o), sorted(o - b))
    return Divergence(None, [], [])


def render_divergence_line(base, orc, dag, met) -> list[str]:
    d = find_divergence(base.schedule, orc.schedule, dag)
    if d.cycle is None:
        return list(wrap(Style.dim(
            "Расписания совпали полностью — эвристика приняла те же решения, что и "
            "точный поиск."), render.W, "  "))
    base_only = ", ".join(
        f"{paint_op(dag[i].op, dag[i].name)}(h={met.height[i]})" for i in d.base_only)
    orc_only = ", ".join(
        f"{paint_op(dag[i].op, dag[i].name)}(h={met.height[i]})" for i in d.oracle_only
    ) or Style.dim("ничего — сознательно придержал порт")
    out = list(wrap(
        f"Первое расхождение — такт {paint('1', str(d.cycle))}.  "
        f"baseline выдал: {base_only}.  oracle выдал: {orc_only}.", render.W, "  "))
    out.append(Style.dim(f"  Разбор этого такта: /explain {d.cycle}"))
    return out


# --------------------------------------------------------------------------
# Разбор одного такта
# --------------------------------------------------------------------------


# --------------------------------------------------------------------------
# Расписание как псевдо-.s (широкие команды e2k в синтаксисе { … })
# --------------------------------------------------------------------------

# Наши операции → мнемоники в духе e2k (то, что реально видно в выводе lcc).
E2K_MNEMO = {
    "ADD": "adds", "SUB": "subs", "MUL": "muls", "DIV": "sdivs",
    "AND": "andd", "SHL": "shls", "LOAD": "ldw", "STORE": "stw",
}


def render_asm(sched: Schedule, dag: DAG, model: MachineModel) -> list[str]:
    """Показать расписание так, как оно выглядело бы в реальном .s-выводе lcc:
    широкие команды в фигурных скобках, каждая операция с каналом (`,0`…`,5`).

    Смысл: модель мы СНЯЛИ с настоящего .s (см. /probe), и полезно увидеть свой
    результат обратно в том же формате — это и есть та самая «широкая команда».
    """
    out: list[str] = []
    for item in schedule_items(sched, dag, model):
        if item[0] == "bundle":
            _, t, heads, held = item
            out.append(Style.dim("{") + Style.dim(f"                    ! такт {t}"))
            for p, i in heads:
                mn = E2K_MNEMO.get(dag[i].op, dag[i].op.lower())
                op = paint_op(dag[i].op, f"{mn}{model.port_label(p)}")
                out.append(f"  {op}  {Style.dim(dag[i].text)}")
            for p, i in held:  # монопольная операция всё ещё держит порт
                mn = E2K_MNEMO.get(dag[i].op, dag[i].op.lower())
                until = sched.placements[i].cycle + model.occupancy(dag[i].op)
                out.append(Style.dim(f"  ! {model.port_label(p)} занят: {mn} {dag[i].name} до т.{until}"))
            out.append(Style.dim("}"))
        else:
            _, t0, t1, held = item
            span = t1 - t0 + 1
            why = "порт занят монопольной операцией" if held else "ждём готовности операндов"
            out.append(Style.dim(f"  ! nop {span}   ({why})"))
    return out


def render_explain(t: int, base, orc, dag, model) -> list[str]:
    bt = {s.cycle: s for s in base.trace}
    ot = {s.cycle: s for s in orc.trace}
    out: list[str] = []
    for who, tr, code in (("BASELINE (эвристика)", bt, "33"), ("ORACLE (точный поиск)", ot, "32")):
        step = tr.get(t)
        out.append("  " + paint(code, who))
        if step is None:
            out.append(Style.dim("    — на этом такте планировщик уже закончил"))
            continue
        issued = step.issued
        if issued:
            txt = ", ".join(
                f"{paint_op(dag[i].op, dag[i].name)}→"
                f"{model.port_label(next(c.channel for c in step.candidates if c.instr == i))}"
                for i in issued
            )
            out += wrap("выдал: " + txt, render.W, "    ")
        else:
            out.append("    выдал: " + paint("error", "ничего"))
        for c in step.candidates:
            if c.chosen:
                out += wrap(paint("success", "✓ ") + f"{dag[c.instr].name}: {c.reason}", render.W, "    ")
        for c in step.candidates:
            if not c.chosen:
                out += wrap(Style.dim(f"✗ {dag[c.instr].name}: {c.reason}"), render.W, "    ")
        if step.comment:
            out += wrap(paint("warning", "! " + step.comment), render.W, "    ")
    out.append("")
    out += wrap(Style.dim(
        "Слева — по какому правилу решала эвристика, справа — что показал точный "
        "поиск для того же такта."), render.W, "  ")
    return out
