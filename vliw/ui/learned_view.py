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

    repaired = st.get("repaired", 0)
    if valid and repaired:
        # Подписываем честно: это уже не чистый ответ модели, а гибрид.
        out.append("  " + paint("success", "РАСПИСАНИЕ ЗАКОННО")
                   + Style.dim("  (модель + починка каналов)"))
    elif valid:
        out.append("  " + paint("success", "РАСПИСАНИЕ ЗАКОННО")
                   + Style.dim("  (чистый ответ модели)"))
    else:
        out.append("  " + paint("error", "РАСПИСАНИЕ НЕЗАКОННО"))
    out.append("")
    for n in res.notes:
        if n.startswith(("НЕ ", "РАСПИСАНИЕ")):
            out.append("  " + paint("warning", n))
        elif n.startswith("ПОЧИНЕНО"):
            out.append("  " + paint("lab", n))
        else:
            out.append("  " + Style.dim(n))

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
    out.append("  " + Style.dim("сырой ответ модели: /learned --raw"
                                "   ·   без починки: /learned --pure"))
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


def render_compare_line(learned_res, base_res, oracle_res) -> list[str]:
    """Итог сравнения трёх планировщиков в одну табличку.

    Порядок строк — от худшего к лучшему по смыслу, а не по числу: эвристика
    (что делает компилятор), модель (что предлагает ИИ), оракул (потолок).
    """
    st = learned_res.search_stats
    if not st.get("valid"):
        return ["  " + Style.dim("модель законного расписания не дала — "
                                 "сравнивать нечего")]

    ms = learned_res.schedule.makespan
    b = base_res.schedule.makespan
    o = oracle_res.schedule.makespan
    tag = "  (+ починка каналов)" if st.get("repaired") else ""

    rows = [
        ("жадная эвристика", b, "warning"),
        ("обученная модель" + tag, ms, "lab"),
        ("точный поиск", o, "success"),
    ]
    width = max(len(r[0]) for r in rows)
    out = ["  " + paint("title", "ТРИ ПЛАНИРОВЩИКА НА ОДНОМ ГРАФЕ"), ""]
    for label, v, colour in rows:
        out.append(f"  {paint(colour, label):<{width + 12}}  {v:>4} т.")

    out.append("")
    if ms < b:
        out.append("  " + paint("success",
                                f"модель обыграла эвристику на {b - ms} т."
                                + (" и попала в оптимум" if ms == o else
                                   f", до оптимума {ms - o} т.")))
    elif ms == b == o:
        out.append("  " + Style.dim("все три сошлись — на этом графе выбирать нечего"))
    elif ms == b:
        out.append("  " + Style.dim(
            f"модель повторила эвристику; до оптимума {ms - o} т."))
    else:
        out.append("  " + Style.dim(
            f"модель отстала от эвристики на {ms - b} т."))
    return out


class PlainRenderer:
    """Поток событий планировщика → строки для построчного вывода.

    Существует потому, что стриминг и «чистая» отрисовка списком строк плохо
    уживаются: отчёт можно собрать целиком и напечатать, а поток нельзя —
    его смысл в том, что он идёт. Компромисс: рендерер хранит одно состояние
    (недописанную строку ответа модели), а печатает по-прежнему `cli.py`.

    Токены копятся до перевода строки, а не красятся посимвольно: посимвольная
    раскраска даёт по паре ANSI-кодов на букву — мусор в выводе и лишние байты
    в терминал.

    События `Placed` здесь НЕ показываются отдельно: в построчном режиме их
    уже видно — модель пишет ровно эти строки. Заливка решётки по `Placed` —
    дело полноэкранного интерфейса, где текста ответа на экране нет.
    """

    def __init__(self) -> None:
        self._line: list[str] = []
        self._opened = False

    def feed(self, ev) -> list[str]:
        """Событие → что напечатать сейчас. Пустой список — печатать нечего."""
        from ..core import Done, Failed, Note, Started, Token

        if isinstance(ev, Started):
            return []
        if isinstance(ev, Note):
            return ["  " + (paint(ev.level, ev.text) if ev.level != "dim"
                            else Style.dim(ev.text))]
        if isinstance(ev, Token):
            out: list[str] = []
            if not self._opened:
                self._opened = True
                out.append("  " + Style.dim("── модель пишет ──"))
            out.extend(self._feed_text(ev.text))
            return out
        if isinstance(ev, (Done, Failed)):
            # Только дописываем хвост без перевода строки. Текст самого отказа
            # печатает `cli.py`: он же решает код возврата, и две половины
            # одного сообщения в двух местах разъезжаются.
            return self._feed_text("\n")
        return []

    def _feed_text(self, chunk: str) -> list[str]:
        out: list[str] = []
        for ch in chunk:
            if ch == "\n":
                text = "".join(self._line).replace("[end of text]", "").rstrip()
                self._line.clear()
                if text:
                    out.append("  " + Style.dim(text))
            else:
                self._line.append(ch)
        return out
