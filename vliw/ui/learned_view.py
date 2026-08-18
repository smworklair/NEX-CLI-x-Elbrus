"""Отчёт обученного планировщика.

Главное отличие от `schedule_view`: здесь расписание МОЖЕТ быть незаконным, и
это не сбой инструмента, а результат замера. Поэтому вывод устроен так, чтобы
провал было видно так же отчётливо, как успех: сначала вердикт «законно / нет»,
потом чем именно нарушено, и только потом сравнение с оракулом — если сравнивать
вообще есть что.
"""

from __future__ import annotations

from . import render
from .render import Style, paint, wrap


def render_status(ready: bool, lines: list[str]) -> list[str]:
    """Готовность к локальному запуску: веса, зависимости, память."""
    out = [paint("lab", "◆ ") + paint("title", "обученный планировщик")]
    out.append("  " + (paint("success", "готов к запуску") if ready
                       else paint("warning", "запустить пока нельзя")))
    out.append("")
    for l in lines:
        out.append("  " + (Style.dim(l) if l else ""))
    out.append("")
    # Построчно, а не через wrap(): wrap склеивает абзац и съедает перевод,
    # а здесь это две отдельные формы запуска, их видно только столбиком.
    out.append("  " + Style.dim("запуск:  /learned            — на текущем сценарии"))
    out.append("  " + Style.dim("         /learned <адаптер>  — конкретными весами"))
    out.append("  " + Style.dim("         /learned --status   — только эта справка"))
    return out


def render_result(res, dag, oracle_res=None, baseline_res=None) -> list[str]:
    """Что выдала модель: вердикт, нарушения, сравнение с точным поиском."""
    st = res.search_stats
    valid = st.get("valid", False)
    out: list[str] = []

    out.append("  " + (paint("success", "РАСПИСАНИЕ ЗАКОННО") if valid
                       else paint("error", "РАСПИСАНИЕ НЕЗАКОННО")))
    out.append("")
    for n in res.notes:
        out.append("  " + (Style.dim(n) if not n.startswith(("НЕ ", "РАСПИСАНИЕ"))
                           else paint("warning", n)))

    if valid and oracle_res is not None:
        out.append("")
        ms = res.schedule.makespan
        orc = oracle_res.schedule.makespan
        base = baseline_res.schedule.makespan if baseline_res is not None else None
        rows = [("модель", ms), ("точный поиск (oracle)", orc)]
        if base is not None:
            rows.insert(1, ("жадная эвристика (baseline)", base))
        width = max(len(r[0]) for r in rows)
        for label, v in rows:
            out.append(f"  {label:<{width}}  {v:>4} т.")
        gap = ms - orc
        out.append("")
        if gap == 0:
            out.append("  " + paint("success",
                                    "модель попала В ОПТИМУМ — столько же, сколько точный поиск"))
        elif base is not None and ms <= base:
            out.append("  " + paint("success", f"модель обыграла эвристику, "
                                               f"до оптимума {gap} т."))
        else:
            out.append("  " + Style.dim(f"до оптимума {gap} т."))

    out.append("")
    out.append("  " + Style.dim("сырой ответ модели: /learned --raw"))
    return out


def render_raw(res) -> list[str]:
    """Сырой текст ответа — то, что модель написала буквально."""
    raw = str(res.search_stats.get("raw", ""))
    out = [paint("title", "  сырой ответ модели"), ""]
    if not raw.strip():
        out.append("  " + Style.dim("(пусто — модель не выдала ни строки)"))
        return out
    for line in raw.splitlines()[:60]:
        out.append("  " + Style.dim(line))
    extra = len(raw.splitlines()) - 60
    if extra > 0:
        out.append("  " + Style.dim(f"… ещё {extra} строк"))
    return out


def render_bench(res, adapter_name: str) -> list[str]:
    """Сводка замера: состав ошибок и разрез по наличию STORE.

    Разрез именно по STORE, а не только по размеру графа, — потому что в
    обучающих данных прогона 1 не было ни одной такой операции, и по корзинам
    размера эта причина размазывается (docs/ROADMAP.md).
    """
    n = len(res.rows)
    out = [paint("title", f"  замер · {adapter_name} · {n} примеров "
                          f"· {res.seconds:.0f} с"), ""]
    if not n:
        out.append("  " + Style.dim("нечего мерить"))
        return out

    order = ("валидно", "хвост", "ресурс", "прочее")
    counts = res.by_kind()
    for k in order:
        v = counts.get(k, 0)
        if not v:
            continue
        colour = "success" if k == "валидно" else "error" if k == "ресурс" else "warning"
        bar = "█" * max(1, round(20 * v / n))
        out.append(f"  {paint(colour, k):<20} {v:>3}  ({res.pct(v):>4.0f}%)  "
                   + Style.dim(bar))

    gaps = [r.gap for r in res.rows if r.gap is not None]
    if gaps:
        exact = sum(1 for g in gaps if g == 0)
        out.append("")
        out.append("  " + Style.dim(
            f"разрыв до оптимума среди законных: {sum(gaps) / len(gaps):.2f} т., "
            f"точно в оптимум {exact}/{len(gaps)}"))

    split = res.split_store()
    out.append("")
    out.append("  " + paint("title", "разрез по наличию STORE в графе"))
    for has, label in ((True, "со STORE"), (False, "без STORE")):
        ok, total = split[has]
        if not total:
            continue
        pct = 100.0 * ok / total
        colour = "error" if has and pct < 50 else "success" if pct >= 50 else "warning"
        out.append(f"    {label:<11} валидно {paint(colour, f'{pct:>3.0f}%')}"
                   + Style.dim(f"  ({ok}/{total})"))
    ok_s, tot_s = split[True]
    ok_n, tot_n = split[False]
    if tot_s and tot_n and (ok_n / tot_n) - (ok_s / tot_s) > 0.2:
        out.append("")
        out += wrap(Style.dim(
            "Разрыв между строками — тот самый диагноз: STORE в обучающих "
            "данных прогона 1 не встречался ни разу, и модель не знает, что "
            "его исполняют только каналы ,2 и ,5."), render.W, "    ")
    return out
