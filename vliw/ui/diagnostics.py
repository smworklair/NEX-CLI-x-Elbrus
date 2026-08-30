"""Отрисовка диагностики: плотно, с иерархией, без стены текста.

Принцип: за три секунды человек должен увидеть ГЛАВНОЕ число и одну строку
с самой дорогой проблемой. Подробности — по запросу (`/doctor N`), а не
вываливаются все сразу.

Поэтому здесь:
  * однотипные находки схлопываются в одну строку («простои: 3 участка, 16 т.»)
    — раньше три одинаковых блока подряд повторяли один и тот же текст;
  * список находок — компактная таблица, по строке на находку;
  * развёрнутое объяснение печатается только для самой дорогой проблемы;
  * яркий акцент достаётся ровно одному элементу — тому, что можно отыграть.
"""

from __future__ import annotations

from ..core.doctor import Diagnosis, Finding
from . import render
from .render import Style, paint, table, wrap


def _cost(f: Finding) -> str:
    return f"−{f.cycles_lost} т." if f.cycles_lost > 0 else "—"


def _bar(load: float, width: int = 12) -> str:
    filled = int(width * load)
    role = "error" if load > 0.8 else ("accent2" if load > 0.55 else "accent_soft")
    return paint(role, "▄" * filled) + Style.dim("▁" * (width - filled))


# --------------------------------------------------------------------------
# Схлопывание однотипных находок
# --------------------------------------------------------------------------


# Задержки разных операций перекрываются во времени, поэтому их цены НЕЛЬЗЯ
# складывать: сумма выйдет больше самого расписания и станет бессмыслицей
# (было «−126 т.» при расписании в 59 т.). Складываем только заведомо
# непересекающиеся находки — участки простоя.
_ADDITIVE = {"idle-stall"}


def _group(findings: list[Finding]) -> list[tuple[Finding, int, int]]:
    """[(представитель, количество, цена группы)] — по коду правила."""
    order: list[str] = []
    buckets: dict[str, list[Finding]] = {}
    for f in findings:
        if f.code not in buckets:
            buckets[f.code] = []
            order.append(f.code)
        buckets[f.code].append(f)
    out = []
    for code in order:
        group = buckets[code]
        costs = [g.cycles_lost for g in group]
        total = sum(costs) if code in _ADDITIVE else max(costs, default=0)
        out.append((group[0], len(group), total))
    out.sort(key=lambda t: -t[2])
    return out


def _group_title(f: Finding, count: int) -> str:
    if count == 1:
        return f.title
    if f.code == "idle-stall":
        return f"простои: {count} участка(-ов)"
    if f.code == "monopoly-queue":
        return f"очередь на монопольный порт: {count} операции(-й)"
    if f.code == "monopoly-block":
        return f"монопольный порт занят не тем: {count} случая(-ев)"
    return f"{f.title} (×{count})"


# --------------------------------------------------------------------------
# Компактный отчёт
# --------------------------------------------------------------------------


def render_diagnosis(d: Diagnosis, label: str = "") -> list[str]:
    out: list[str] = []
    losses = [f for f in d.findings if f.recoverable]
    limits = [f for f in d.findings if not f.recoverable]

    # --- одна строка с главным числом ---------------------------------
    if d.total_lost > 0:
        head = paint("error", f"■ {d.total_lost} т.") + paint("title", " можно сократить")
    else:
        head = paint("success", "■ упирается в предел машины")
    tail = Style.dim(f"{d.makespan} т.  →  предел {d.lower_bound} т.")
    out.append(f"  {head}    {tail}")

    busiest = max(d.ports, key=lambda p: p.load(d.span), default=None)
    if busiest is not None:
        out.append("  " + Style.dim(
            f"простоев {d.idle_cycles} т.  ·  слоты {d.slot_utilization:.0%}  ·  "
            f"самый занятый порт {busiest.label} {busiest.load(d.span):.0%}"))
    out.append("")

    # --- порты одной компактной строкой каждый -------------------------
    rows = []
    for p in d.ports:
        load = p.load(d.span)
        if not load and not p.sole_ops:
            continue
        sole = paint("accent2", "только " + "/".join(p.sole_ops)) if p.sole_ops else ""
        rows.append([p.label, _bar(load), f"{load:>4.0%}", f"{p.issued} оп.", sole])
    if rows:
        # Без шапки: колонки и так очевидны, а пустые заголовки выглядели
        # как сломанная таблица.
        for r in rows:
            out.append("   " + "  ".join([
                render.pad(r[0], 5), r[1], render.pad(r[2], 5, ">"),
                render.pad(r[3], 7, ">"), r[4]]))
        out.append("")

    # --- что можно отыграть -------------------------------------------
    if losses:
        out.append("  " + paint("error", "МОЖНО ОТЫГРАТЬ"))
        for n, (f, cnt, total) in enumerate(_group(losses), 1):
            mark = paint("error", "●") if n == 1 else Style.dim("○")
            out.append(f"   {mark} {n}  {paint('warning', f'−{total} т.'):>12}  "
                       f"{_group_title(f, cnt)}")
        out.append("")
        # Подробно — только про самую дорогую: остальное по /doctor N.
        top = _group(losses)[0][0]
        out += _detail(top, prefix="   ", with_title=False)
        out.append("")
    else:
        out.append("  " + paint("success", "МОЖНО ОТЫГРАТЬ: ничего"))
        out += wrap(Style.dim("порядок выдачи не теряет тактов — всё, что можно "
                              "было выдать раньше, выдано раньше"), render.W, "   ")
        out.append("")

    # --- пределы машины: только одной строкой каждый --------------------
    if limits:
        out.append("  " + Style.dim("ПРЕДЕЛЫ МАШИНЫ") + Style.dim(" — не ошибки планировщика"))
        for f, cnt, total in _group(limits):
            cost = f"−{total} т." if total > 0 else "—"
            out.append(f"   {Style.dim('·')}    {Style.dim(cost):>12}  "
                       f"{Style.dim(_group_title(f, cnt))}")
        out.append("")

    hint = "/doctor 2 — подробности другой находки" if len(_group(losses)) > 1 else \
           "/doctor oracle — то же для точного поиска"
    out.append("  " + Style.dim(hint))
    return out


def _detail(f: Finding, prefix: str = "  ", with_title: bool = True) -> list[str]:
    """Развёрнутое объяснение одной находки."""
    w = render.W - len(prefix)
    out = [prefix + paint("title", f.title)] if with_title else []
    out += wrap(Style.dim("где    ") + f.where, w, prefix + "  ")
    out += wrap(Style.dim("почему ") + f.why, w, prefix + "  ")
    out += wrap(paint("accent_soft", "решение ") + f.fix, w, prefix + "  ")
    return out


def render_detail(d: Diagnosis, n: int) -> list[str]:
    """Подробности находки номер N из списка «можно отыграть»."""
    losses = [f for f in d.findings if f.recoverable]
    groups = _group(losses)
    if not groups:
        return ["  " + Style.dim("отыгрываемых находок нет")]
    if n < 1 or n > len(groups):
        return ["  " + paint("error", f"нет находки №{n}; всего {len(groups)}")]
    f, cnt, total = groups[n - 1]
    out = [f"  {paint('error', f'−{total} т.')}  {_group_title(f, cnt)}", ""]
    out += _detail(f, prefix="  ")
    return out


def sidebar_rows(d: Diagnosis, width: int) -> list[str]:
    """Две-три строки для боковой панели — только суть."""
    losses = [f for f in d.findings if f.recoverable]
    limits = [f for f in d.findings if not f.recoverable]
    out: list[str] = []
    if d.total_lost > 0:
        out.append(paint("error", f"  ■ {d.total_lost} т. сверх предела"))
    else:
        out.append(paint("success", "  ■ упирается в предел"))
    groups = _group(losses)
    if groups:
        f, cnt, total = groups[0]
        out.append(Style.dim(f"  {len(groups)} потери · {len(limits)} предела"))
        title = _group_title(f, cnt)
        out.append(paint("warning", f"  −{total} т."))
        for line in wrap(Style.dim(title), width, "    ")[:2]:
            out.append(line)
    else:
        out.append(Style.dim(f"  потерь нет · {len(limits)} предела"))
    return out


# --------------------------------------------------------------------------
# Разбор .s
# --------------------------------------------------------------------------


def render_parsed(parsed, dag, compiler_cycles: int | None,
                  oracle_cycles: int | None, lower_bound: int | None,
                  compiler_problem: tuple[str, str] | None = None,
                  problems=None) -> list[str]:
    """Разбор загруженного `.s`.

    `compiler_problem` — пара (заголовок, подробность): почему расписания
    компилятора нет. Раньше причина была одна на все случаи («раскладка по
    каналам не сходится»), и на настоящем `-O3` она врала: каналы сходились,
    а разъезжалась одна зависимость из-за программной конвейеризации,
    которой линейный разбор файла не видит. Сказать «не сошлись каналы»
    там, где не сошлась зависимость, — отправить человека искать не в том
    месте.
    """
    out: list[str] = []

    # СКОЛЬКО ОПЕРАЦИЙ МАШИНЕ НЕИЗВЕСТНО. От этого зависит, можно ли вообще
    # называть разницу с компилятором «резервом». У класса UNKNOWN латентность
    # 1 и любой канал — это заглушка, а не измерение (см. model.py). Оракул
    # планирует такие операции как однотактовые и обыгрывает компилятор просто
    # потому, что не знает их настоящей цены: на выводе `lcc -O3` обычного
    # цикла так получался «резерв 71%», хотя половина операций там — упакованный
    # SIMD и плавающая точка, которых модель не описывает вовсе. Показать такое
    # число как достижение — соврать, поэтому при заметной доле UNKNOWN
    # сравнение подписывается как несостоятельное, а не как выигрыш.
    unknown_ops = sum(1 for o in parsed.ops if o.op == "UNKNOWN")
    unknown_share = unknown_ops / len(parsed.ops) if parsed.ops else 0.0

    if compiler_cycles is not None and oracle_cycles is not None:
        gap = compiler_cycles - oracle_cycles
        if unknown_share >= 0.05:
            out.append("  " + paint("warning", "■ сравнение с компилятором несостоятельно"))
            out += wrap(Style.dim(
                f"{unknown_ops} из {len(parsed.ops)} операций "
                f"({unknown_share:.0%}) машине неизвестны — их латентность "
                f"взята за 1 такт как заглушка. Точный поиск обыгрывает "
                f"компилятор здесь потому, что не знает настоящей цены этих "
                f"операций, а не потому, что нашёл лучший план"), render.W, "  ")
            out.append("  " + Style.dim(
                f"lcc {compiler_cycles} т.  →  поиск {oracle_cycles} т. "
                f"(число справочное, сравнивать нельзя)"))
        else:
            if gap > 0:
                pct = 100.0 * gap / compiler_cycles
                head = paint("success", f"■ резерв {gap} т. ({pct:.0f}%)")
            elif gap == 0:
                head = paint("dim", "■ резерва нет")
            else:
                head = paint("warning", f"■ компилятор быстрее на {-gap} т.")
            out.append(f"  {head}")
            out.append("  " + Style.dim(
                f"lcc {compiler_cycles} т.  →  поиск {oracle_cycles} т."
                + (f"  →  предел {lower_bound} т." if lower_bound else "")))
            if unknown_ops:
                out += wrap(Style.dim(
                    f"(с оговоркой: {unknown_ops} операц. машине неизвестны, "
                    f"их латентность взята за 1 такт)"), render.W, "  ")
    else:
        head, detail = compiler_problem or (
            "расписание компилятора не восстановлено",
            "раскладка по каналам не сходится с моделью")
        out.append("  " + paint("warning", "■ " + head))
        out += wrap(Style.dim(detail), render.W, "  ")
    out.append("")

    out += wrap(Style.dim(
        f"{len(parsed.ops)} операций · {parsed.bundles} широких команд · "
        f"{parsed.nop_cycles} т. в nop"), render.W, "  ")
    ops = "  ".join(f"{k}×{v}" for k, v in sorted(parsed.op_counts().items()))
    out += wrap(Style.dim(ops), render.W, "  ")

    if parsed.unknown_mnemonics:
        unk = ", ".join(f"{k}×{v}" for k, v in
                        sorted(parsed.unknown_mnemonics.items(),
                               key=lambda kv: -kv[1])[:6])
        # НЕ «считано как арифметика»: с версии 0.9 незнакомая мнемоника
        # получает класс UNKNOWN (латентность 1, любой канал) и видна как
        # UNKNOWN в разбивке выше, а не прячется в ADD. Формулировка про
        # арифметику осталась от прежнего поведения и уже неверна.
        out += wrap(paint("warning",
                          f"нераспознано (класс UNKNOWN, латентность 1): {unk}"),
                    render.W, "  ")
    if parsed.skipped_lines:
        out.append("  " + Style.dim(f"пропущено строк: {parsed.skipped_lines}"))

    # Замечания линтера. Раньше их видел только полноэкранный режим КОД, а
    # `/load` о них молчал — один и тот же файл получал два разных вердикта,
    # и в построчном режиме незаконный ассемблер (`adds,9` на шестиканальной
    # машине) проходил без единого слова.
    errors = [pr for pr in problems or () if pr.severity == "error"]
    warns = [pr for pr in problems or () if pr.severity == "warn"]
    if errors or warns:
        out.append("")
        if errors:
            out.append("  " + paint("error",
                                    f"■ ошибок: {len(errors)}"))
            for pr in errors[:5]:
                out += wrap(paint("error", f"строка {pr.line}: {pr.text}"),
                            render.W, "    ")
            if len(errors) > 5:
                out.append("    " + Style.dim(f"…и ещё {len(errors) - 5}"))
        if warns:
            out.append("  " + Style.dim(f"замечаний: {len(warns)}"))
            for pr in warns[:3]:
                out += wrap(Style.dim(f"строка {pr.line}: {pr.text}"),
                            render.W, "    ")
            if len(warns) > 3:
                out.append("    " + Style.dim(f"…и ещё {len(warns) - 3}"))

    out.append("")
    out.append("  " + Style.dim("Дальше: /doctor — где теряются такты · /compare · /asm"))
    return out
