"""Факты о текущем состоянии — то, чем «заземляется» языковая модель.

Смысл модуля: языковая модель не должна ВЫДУМЫВАТЬ числа. Все величины
(такты, загрузка портов, найденные потери) считает детерминированное ядро
`vliw.core`, а сюда попадает готовая сводка, которая уходит в системную
подсказку. Модель работает только объяснением и рассуждением поверх этих
фактов — поэтому её ответы можно проверить командой `/doctor` или `/compare`.

Это же и есть практический ответ на «дообучить под процессор»: дообучения нет,
но модель получает измеренную модель машины и результаты анализа прямо в
контекст, и рассуждает уже про конкретный e2k, а не про VLIW вообще.
"""

from __future__ import annotations

from ..core import compute_metrics
from ..core.doctor import diagnose

SYSTEM = """\
Ты — NEX, инженерный ассистент по планированию инструкций для VLIW-процессора
Эльбрус (e2k). Ты встроен в исследовательский CLI и помогаешь разбираться,
почему участок кода выполняется за столько тактов и где теряется время.

ЖЁСТКИЕ ПРАВИЛА:
1. Все числа бери ТОЛЬКО из блока ФАКТЫ ниже. Не придумывай такты, проценты и
   имена операций. Если нужного числа в фактах нет — так и скажи и предложи
   команду, которая его посчитает.
2. Отвечай по-русски, коротко и по делу: инженеру, а не студенту. Без
   маркетинга и без общих слов про «оптимизацию».
3. Опирайся на измеренную модель машины. Единственный по-настоящему монопольный
   исполнитель на e2k — ДЕЛИТЕЛЬ (только порт `,5`). Умножение исполнимо на
   четырёх портах, запись — на двух, загрузка — на четырёх. Не приписывай
   умножителю монополию: это опровергнуто проверкой ассемблером.
4. Различай две вещи и называй их прямо: «потеря» (планировщик выдал операции в
   неудачном порядке, такты можно отыграть) и «предел машины» (ждать было
   правильно, быстрее нельзя).
5. Если уместно, заканчивай одной строкой «Дальше:» с конкретной командой
   (/doctor, /compare, /asm, /explain N, /load файл.s).
6. Не используй Markdown-заголовки и таблицы — вывод идёт в терминал.
   Допустимы короткие списки через «—».
"""


def machine_facts(model) -> list[str]:
    out = [f"Профиль машины: {model.name}, портов: {model.width}."]
    sole = model.sole_host_ops()
    for port, ops in sorted(sole.items()):
        out.append(f"Порт {model.port_label(port)} — ЕДИНСТВЕННЫЙ исполнитель "
                   f"{'/'.join(ops)} (монопольный).")
    lat = []
    for name in sorted(model.ops):
        op = model.ops[name]
        s = f"{name}={op.latency}т."
        if op.blocks_channel():
            s += f" (держит порт {op.occupancy}т.)"
        lat.append(s)
    out.append("Латентности: " + ", ".join(lat))
    for op_name in sorted(model.ops):
        chans = model.channels_for(op_name)
        if 1 < len(chans) < model.width:
            out.append(f"{op_name} исполнима на портах "
                       f"{', '.join(model.port_label(c) for c in chans)} "
                       f"({len(chans)} из {model.width}).")
    out.append("Модель снята с компилятора lcc-1.29.16: матрица портов "
               "проверена ассемблером (отказы вида 'cannot be encoded in ALC'), "
               "латентности — цепочками зависимых операций, темп приёма — "
               "потоками независимых.")
    return out


def schedule_facts(session) -> list[str]:
    """Числа по текущему участку — только если он уже посчитан."""
    cached = session.peek()
    dag = session.dag_obj
    out = [f"Текущий участок: {session.scenario}, инструкций: {len(dag)}."]
    counts = ", ".join(f"{k}×{v}" for k, v in sorted(dag.op_counts().items()))
    out.append(f"Состав операций: {counts}.")
    if dag.note:
        out.append(f"Описание участка: {dag.note[:400]}")
    if cached is None:
        out.append("Расписание ещё НЕ посчитано (нужна команда /run).")
        return out

    base, orc, met = cached
    b, o = base.schedule.makespan, orc.schedule.makespan
    out.append(f"baseline (жадная эвристика): {b} тактов.")
    out.append(f"oracle (точный поиск, теоретический потолок): {o} тактов.")
    out.append(f"Нижняя граница: {met.lower_bound} тактов "
               f"(критический путь {met.critical_path_bound}, "
               f"ресурсы {met.resource_bound}; связывает {met.binding}).")
    out.append(f"Разрыв baseline→oracle: {b - o} тактов.")
    out.append("Оптимальность oracle доказана." if orc.optimal
               else "Оптимальность oracle НЕ доказана (лучшее найденное).")
    return out


def doctor_facts(session, limit: int = 6) -> list[str]:
    cached = session.peek()
    if cached is None:
        return []
    base, orc, met = cached
    try:
        d = diagnose(session.dag_obj, session.model(), base.schedule, met)
    except Exception:
        return []
    out = [f"ДИАГНОСТИКА baseline: makespan {d.makespan}т., "
           f"предел {d.lower_bound}т., простоев {d.idle_cycles}т., "
           f"заполнение слотов {d.slot_utilization:.0%}."]
    for p in d.ports:
        load = p.load(d.span)
        if load or p.sole_ops:
            sole = f" (только {'/'.join(p.sole_ops)})" if p.sole_ops else ""
            out.append(f"  порт {p.label}: загрузка {load:.0%}, "
                       f"{p.issued} операций{sole}")
    losses = [f for f in d.findings if f.recoverable][:limit]
    limits = [f for f in d.findings if not f.recoverable][:limit]
    if losses:
        out.append("МОЖНО ОТЫГРАТЬ:")
        for f in losses:
            out.append(f"  −{f.cycles_lost}т. [{f.code}] {f.title}. "
                       f"Где: {f.where}. Почему: {f.why}")
    else:
        out.append("Потерь из-за порядка выдачи нет.")
    if limits:
        out.append("ПРЕДЕЛЫ МАШИНЫ (не ошибки):")
        for f in limits:
            out.append(f"  {f.title} — {f.why}")
    return out


def schedule_layout(session, which: str = "baseline", max_rows: int = 40) -> list[str]:
    """Компактная раскладка «такт: порт=операция» — чтобы модель видела расписание."""
    cached = session.peek()
    if cached is None:
        return []
    base, orc, met = cached
    sched = base.schedule if which == "baseline" else orc.schedule
    model = session.model()
    dag = session.dag_obj
    by_cycle: dict[int, list[str]] = {}
    for p in sched.placements.values():
        by_cycle.setdefault(p.cycle, []).append(
            f"{model.port_label(p.channel)}={dag[p.instr].op} {dag[p.instr].name}")
    out = [f"РАСПИСАНИЕ {which} (такт: что выдано):"]
    cycles = sorted(by_cycle)
    for c in cycles[:max_rows]:
        out.append(f"  т.{c}: " + ", ".join(sorted(by_cycle[c])))
    # Обрезка обязана быть видна модели. Молча укороченная раскладка выглядит
    # как полная — и на вопрос про инструкцию из хвоста модель ответит числом,
    # которого не видела.
    if len(cycles) > max_rows:
        hidden = len(cycles) - max_rows
        out.append(f"  ... ещё {hidden} тактов не показано: раскладка обрезана "
                   f"на {max_rows} строках. Про такты после т.{cycles[max_rows - 1]} "
                   f"данных здесь НЕТ — не называй их, предложи /run или /explain N.")
    # Такты baseline и oracle различаются; без явной пометки их легко смешать
    # в одном ответе, взяв makespan от одного, а номер такта от другого.
    other = orc if which == "baseline" else base
    if other.schedule.makespan != sched.makespan:
        out.append(f"  (это такты {which}; у "
                   f"{'oracle' if which == 'baseline' else 'baseline'} "
                   f"расстановка другая — {other.schedule.makespan} тактов)")
    return out


def build(session, include_layout: bool = False) -> str:
    """Собрать блок ФАКТЫ для системной подсказки."""
    parts: list[str] = ["ФАКТЫ (единственный источник чисел):", ""]
    parts += machine_facts(session.model())
    parts.append("")
    parts += schedule_facts(session)
    doc = doctor_facts(session)
    if doc:
        parts.append("")
        parts += doc
    if include_layout:
        lay = schedule_layout(session)
        if lay:
            parts.append("")
            parts += lay
    parts.append("")
    parts.append("Доступные сценарии: см. команду /scenarios. "
                 "Команды: /run /compare /doctor /asm /explain /path /bounds "
                 "/model /load /probe.")
    return "\n".join(parts)


PANEL_SYSTEM = """\
Ты — NEX, инженерный ассистент по планированию инструкций для VLIW-процессора
Эльбрус (e2k). Человек смотрит на ОДНУ панель инструмента и спрашивает про то,
что в ней.

ЖЁСТКИЕ ПРАВИЛА:
1. Отвечай ТОЛЬКО по строкам блока ПАНЕЛЬ ниже. Там всё, что нужно.
2. Ничего не выводи и не обобщай сверх этих строк. Если в них нет ответа —
   так и скажи и предложи команду (/doctor, /compare, /run, /bounds).
3. Не переворачивай утверждения. «Исполняется только на ,2 и ,5» значит, что
   на остальных портах она НЕ исполняется, — и ничего больше.
4. Отвечай по-русски, два-четыре предложения, инженеру. Без Markdown-таблиц и
   заголовков: вывод идёт в терминал.
"""


def panel_prompt(title: str, facts: list[str]) -> str:
    """Подсказка для чата по одной панели — узкая нарочно.

    Сюда НЕ идёт общий блок ФАКТЫ, хотя первая версия его слала. Две причины,
    обе измерены на живой модели.

    Скорость: общий блок — 1451 токен, и на CPU его прогрев стоит десятки
    секунд на каждый новый хвост. Панельный промпт — порядка полутора сотен
    токенов, и ответ приходит за секунды.

    Точность: чем больше материала, тем больше у модели на 3B поводов
    связать не то с не тем. На вопрос «какие операции ограничены одним
    портом?» с полным блоком она ответила «LOAD, MUL, STORE ограничены портом
    ,5» — то есть перевернула ровно те строки, которые ей дали (монопольный
    только DIV; LOAD и MUL идут на четырёх портах, STORE на двух). Узкий
    контекст — это не экономия, это и есть защита от выдумки.
    """
    out = [PANEL_SYSTEM, "", f"ПАНЕЛЬ «{title}» — единственный источник:", ""]
    out += ["  " + f for f in facts]
    return "\n".join(out)


def system_prompt(session, include_layout: bool = False,
                  panel: tuple[str, list[str]] | None = None) -> str:
    """Системная подсказка. `panel` — (заголовок, факты) открытой панели.

    ПОРЯДОК ЗДЕСЬ — НЕ КОСМЕТИКА. Панельная часть идёт СУФФИКСОМ, после общих
    фактов, и это единственное, что делает панельный чат пригодным на
    локальной модели.

    llama.cpp кэширует посчитанный ПРЕФИКС промпта (`cache_prompt`). Общая
    часть — правила, матрица машины, числа участка — примерно 1450 токенов, и
    на CPU она считается порядка сорока секунд. Если панельный контекст
    подмешивать в середину или в начало, префикс меняется при каждом переходе
    между панелями, кэш промахивается, и каждый вопрос снова стоит сорок
    секунд. С суффиксом общая часть остаётся байт в байт той же, кэш попадает,
    и платим только за хвост в несколько десятков токенов.
    """
    out = SYSTEM + "\n\n" + build(session, include_layout)
    if panel is not None:
        title, facts = panel
        out += ("\n\nСЕЙЧАС ЧЕЛОВЕК СМОТРИТ НА ПАНЕЛЬ «" + title + "». "
                "Отвечай про то, что в ней, и не пересказывай остальное.\n")
        out += "\n".join("  " + f for f in facts)
    return out
