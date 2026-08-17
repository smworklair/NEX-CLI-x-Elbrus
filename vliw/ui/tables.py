"""Таблицы: сценарии, сводка результатов, матрица возможностей, sweep, selfcheck.

Функции берут ГОТОВЫЕ данные (числа/флаги, посчитанные в `vliw.core`/`vliw.cli`)
и возвращают строки для терминала. Никаких вычислений планирования здесь нет.
"""

from __future__ import annotations

from ..core import (
    SCENARIOS,
    MachineModel,
    SelfcheckResult,
    capability_matrix,
    describe_model,
)
from . import render
from .render import (
    Style,
    pad,
    paint,
    paint_op,
    table,
    wrap,
)


# --------------------------------------------------------------------------
# Список сценариев
# --------------------------------------------------------------------------


# Порядок и пояснение групп. Сценарии перечисляются не сплошным списком, а по
# ГРУППАМ: первые показывают работу планировщика (один граф — две раскладки),
# остальные — приёмы оптимизации самого кода, где планировщик уже бессилен.
_FAMILY_ORDER = [
    ("основа", "как вообще выглядит расписание — с этого начинать"),
    ("монопольный порт", "здесь жадная эвристика теряет такты: есть разрыв с оптимумом"),
    ("проверка модели", "что бывает, когда модель машины описана неверно"),
    ("форма графа", "планировщик бессилен — переписывать надо исходник"),
    ("цена операции", "дешевле не планировать лучше, а убрать дорогую операцию"),
    ("циклы", "развёртка, рост ILP и его предел"),
    ("память", "загрузки, обход по указателям, поток данных"),
    ("ветвления", "обе ветви посчитаны заранее, без перехода"),
]

# Пары «как написано» → «как надо»: их полезно прогнать подряд и сравнить.
_PAIRS = [("seqreduce", "treereduce"), ("divpressure", "divstrength")]


def render_scenarios(current: str | None = None) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    groups = list(_FAMILY_ORDER)
    # Сценарии без группы (например, добавленные позже) не должны пропасть.
    groups += [(f, "") for f in {d.family for d in SCENARIOS.values()}
               if f not in {g for g, _ in _FAMILY_ORDER}]

    for family, hint in groups:
        keys = [k for k, d in SCENARIOS.items() if d.family == family]
        if not keys:
            continue
        if out:
            out.append("")
        out.append("  " + paint("lab", "● ") + paint("title", family)
                   + ("   " + Style.dim(hint) if hint else ""))
        for key in keys:
            dag = SCENARIOS[key]
            seen.add(key)
            mark = paint("work", "●") if key == current else " "
            head = (f"  {mark} " + paint("accent", pad(key, 13))
                    + Style.dim(pad(str(len(dag)), 4, ">") + "  ") + dag.title)
            out.append(head)
            if dag.lesson:
                out += wrap(Style.dim(dag.lesson), render.W, "       ")

    rest = [k for k in SCENARIOS if k not in seen]
    if rest:
        out.append("")
        for key in rest:
            dag = SCENARIOS[key]
            mark = paint("work", "●") if key == current else " "
            out.append(f"  {mark} " + paint("accent", pad(key, 13))
                       + Style.dim(pad(str(len(dag)), 4, ">") + "  ") + dag.title)

    out.append("")
    pairs = "  ·  ".join(f"/run {a} → /run {b}" for a, b in _PAIRS
                         if a in SCENARIOS and b in SCENARIOS)
    if pairs:
        out += wrap(Style.dim("пары подряд: " + pairs.replace("/run ", "")),
                    render.W, "  ")
    out.append(Style.dim("  все разом: all    ·    случайный: random 16"))
    return out


# --------------------------------------------------------------------------
# Матрица возможностей портов + латентности
# --------------------------------------------------------------------------


def render_matrix(model: MachineModel) -> list[str]:
    op_names, grid = capability_matrix(model)
    sole = model.sole_host_ops()
    cw = max(len(o) for o in op_names) + 1
    header = Style.dim("порт ") + " ".join(pad(paint_op(o, o), cw, "^") for o in op_names)
    out = [header, Style.dim("─" * (5 + len(op_names) * (cw + 1)))]
    for port in model.ports:
        cells = []
        for j, o in enumerate(op_names):
            mark = paint_op(o, "●") if grid[port.index][j] else Style.dim("·")
            cells.append(pad(mark, cw, "^"))
        tag = ""
        if port.index in sole:
            names = "/".join(sole[port.index])
            tag = "  " + paint_op(sole[port.index][0], f"◄ только {names}")
        out.append(Style.dim(f"{model.port_label(port.index):>4} ") + " ".join(cells) + tag)
    return out


def render_model_view(model: MachineModel) -> list[str]:
    out = []
    out += wrap(model.description, render.W, "  ")
    out.append("")
    out.append("  " + Style.bold("матрица возможностей: порт → какие операции исполнимы"))
    out += ["  " + l for l in render_matrix(model)]
    out.append("")
    out.append("  " + Style.bold("латентности и монопольное занятие:"))
    rows = [[p, v, Style.dim(src)] for p, v, src in describe_model(model)]
    out += ["  " + l for l in table(["параметр", "значение", "источник"], rows)]
    return out


# --------------------------------------------------------------------------
# Сводка по всем сценариям (команда all)
# --------------------------------------------------------------------------


def render_summary(rows: list[dict]) -> list[str]:
    """rows: dict(key, n, model_name, lb, base_ms, oracle_ms, gap, optimal, seconds)."""
    disp = []
    n_gap = n_proven_equal = n_unproven = 0
    for r in rows:
        gap = r["gap"]
        if gap:
            n_gap += 1
        elif r["optimal"]:
            n_proven_equal += 1
        else:
            n_unproven += 1
        pct = 100.0 * gap / r["base_ms"] if r["base_ms"] else 0
        disp.append([
            r["key"], str(r["n"]), r["model_name"], str(r["lb"]),
            str(r["base_ms"]), str(r["oracle_ms"]),
            Style.green(f"-{gap} ({pct:.0f}%)") if gap else Style.dim("—"),
            Style.green("доказан") if r["optimal"] else Style.yellow("не доказан"),
            f"{r['seconds']:.1f}с",
        ])
    out = ["  " + l for l in table(
        ["сценарий", "N", "модель", "нижн.гр.", "baseline", "oracle",
         "выигрыш", "оптимум", "время"],
        disp, aligns="<><>>><<>",
    )]
    out.append("")
    parts = [f"Итого из {len(rows)} сценариев:"]
    if n_gap:
        parts.append(
            f"в {n_gap} есть доказанный разрыв между эвристикой и потолком оракула — "
            f"именно там обученной модели есть что отыгрывать;"
        )
    if n_proven_equal:
        parts.append(
            f"в {n_proven_equal} эвристика доказанно оптимальна — учить нечему, "
            f"и это честный результат, а не неудача поиска;"
        )
    if n_unproven:
        parts.append(
            f"в {n_unproven} точный поиск не уложился в бюджет: разрыва не нашли, "
            f"но и отсутствие разрыва не доказали."
        )
    out += wrap(" ".join(parts), render.W, "  ")
    return out


# --------------------------------------------------------------------------
# Массовый прогон по случайным графам (команда sweep)
# --------------------------------------------------------------------------


def render_sweep(rows: list[dict], stopped: bool) -> list[str]:
    """rows: dict(model_name, width, uniform, n_gap, n_proven, avg_gap, worst)."""
    disp = []
    for r in rows:
        share = f"{r['n_gap']}/{r['n_proven']}" if r["n_proven"] else "—"
        disp.append([
            r["model_name"], str(r["width"]),
            Style.dim("равноправны") if r["uniform"] else Style.yellow("неравноправны"),
            share,
            f"{100.0 * r['n_gap'] / r['n_proven']:.0f}%" if r["n_proven"] else "—",
            f"{r['avg_gap']:.0f}%" if r["avg_gap"] is not None else Style.dim("—"),
            f"{r['worst']}" if r["worst"] else Style.dim("—"),
        ])
    out = ["  " + l for l in table(
        ["модель", "кан.", "слоты", "с разрывом", "доля", "средний разрыв", "макс, тактов"],
        disp, aligns="<><>>>>",
    )]
    out.append("")
    if stopped:
        out += wrap(Style.dim(
            "Часть конфигураций обработана не полностью — сработал лимит времени "
            "(--time-limit)."), render.W, "  ")
    out += wrap(
        "Читать так: чем неравноправнее порты, тем чаще жадная эвристика "
        "промахивается. На модели «все порты равноправны» разрыв практически "
        "отсутствует; на измеренной он появляется там, где дефицитный канал "
        "(делитель `,5`, запись `,2`/`,5`) достаётся менее срочной операции.",
        render.W, "  ")
    out.append("")
    out += wrap(Style.dim(
        "Для сравнения в наборе есть профиль e2k-v6-firstprobe — опровергнутая "
        "первая версия модели, где умножителю ошибочно приписана монополия. На "
        "нём разрывы заметно крупнее, и хорошо видно, насколько выводы зависят "
        "от качества описания машины."), render.W, "  ")
    return out


# --------------------------------------------------------------------------
# Результат сверки оракула перебором (команда selfcheck)
# --------------------------------------------------------------------------


def render_selfcheck(res: SelfcheckResult) -> list[str]:
    out = [
        Style.dim(
            f"Сверяем оракул (точный поиск) с независимым полным перебором: "
            f"{res.seeds} графов × {len(res.sizes)} размеров × {res.models} моделей."
        ),
        Style.dim("Полный перебор считается только на маленьких графах — это нормально."),
        "",
    ]
    for tag, problems in res.problems:
        out.append(Style.red(f"  ✗ {tag}"))
        out += [f"      {p}" for p in problems]
    if res.failed:
        out.append(Style.red(
            f"ПРОВАЛ: {res.failed} расхождений из {res.checked} проверок "
            f"({res.seconds:.0f} с)"))
    else:
        note = " (частично, по лимиту времени)" if res.stopped_early else ""
        out.append(Style.green(
            f"OK: {res.checked} проверок, расхождений нет{note} ({res.seconds:.0f} с)."))
        out += wrap(
            "Оптимальность, которую заявляет оракул, подтверждена независимым "
            "перебором.", render.W, "  ")
    return out
