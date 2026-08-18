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
