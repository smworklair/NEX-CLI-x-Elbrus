"""Генератор ассемблера e2k: ситуация одной командой вместо ручного набора.

ЗАЧЕМ
-----
Назначение инструмента — экономить время инженера. Самая дорогая мелочь в
работе с e2k — набрать руками десяток широких команд, чтобы проверить одну
мысль («а упакуются ли эти восемь умножений?»). Пишется это долго, а ошибка
в канале обнаруживается только на ассемблере, и не всегда внятно.

Поэтому генератор берёт каналы, латентности и занятость ПРЯМО ИЗ МОДЕЛИ
МАШИНЫ (`vliw/core/model.py`, где у каждого числа проставлен источник). Он
физически не может выдать `muls,2`: у класса MUL каналы `,0 ,1 ,3 ,4`, это
снято у ассемблера, и генератор просто не знает про другие.

Это же отличает его от каталога `/example`: там пять готовых текстов, тут
любая ситуация нужного размера, и всегда законная.

ЧЕГО ЗДЕСЬ НЕТ
--------------
Осмысленной программы. Регистры раздаются по кругу, значения никого не
интересуют: получается код, который АССЕМБЛИРУЕТСЯ и имеет заданную
структуру зависимостей, а не считает что-то полезное. Для замера расписания
этого достаточно, для запуска на машине — нет.
"""

from __future__ import annotations

from .model import MachineModel

#: Как выглядит операция класса в тексте: мнемоника и форма операндов.
#: Формы взяты из `tools/probe_matrix.py` — те же, которыми матрица портов
#: проверялась у настоящего ассемблера, значит заведомо принимаются им.
FORMS: dict[str, tuple[str, str]] = {
    "ADD":   ("adds",  "%r{a}, %r{b}, %r{d}"),
    "SUB":   ("subs",  "%r{a}, %r{b}, %r{d}"),
    "AND":   ("ands",  "%r{a}, %r{b}, %r{d}"),
    "SHL":   ("shls",  "%r{a}, %r{b}, %r{d}"),
    "MUL":   ("muls",  "%r{a}, %r{b}, %r{d}"),
    "DIV":   ("sdivs", "%r{a}, %r{b}, %r{d}"),
    "FADD":  ("faddd", "%dr{a}, %dr{b}, %dr{d}"),
    "FMUL":  ("fmuld", "%dr{a}, %dr{b}, %dr{d}"),
    "FDIV":  ("fdivd", "%dr{a}, %dr{b}, %dr{d}"),
    "FMA":   ("fmul_addd", "%dr{a}, %dr{b}, %dr{c}, %dr{d}"),
    "LOAD":  ("ldw",   "0x0, [ _f64,_lts0 mem ], %r{d}"),
    "STORE": ("stw",   "%dr2, 0x0, %r{a}"),
}

#: Человеческие имена для сообщений об ошибке.
ALIASES = {
    "muls": "MUL", "mul": "MUL", "умножение": "MUL",
    "adds": "ADD", "add": "ADD", "сложение": "ADD",
    "subs": "SUB", "sub": "SUB",
    "ands": "AND", "and": "AND",
    "shls": "SHL", "shl": "SHL",
    "sdivs": "DIV", "div": "DIV", "деление": "DIV",
    "faddd": "FADD", "fadd": "FADD",
    "fmuld": "FMUL", "fmul": "FMUL",
    "fdivd": "FDIV", "fdiv": "FDIV",
    "fmul_addd": "FMA", "fma": "FMA",
    "ldw": "LOAD", "load": "LOAD", "чтение": "LOAD",
    "stw": "STORE", "store": "STORE", "запись": "STORE",
}


def resolve(name: str) -> str | None:
    """Имя от человека → класс операции модели. None — не знаем такого."""
    key = name.strip().lower()
    if key.upper() in FORMS:
        return key.upper()
    return ALIASES.get(key)


def known_names() -> list[str]:
    """Что можно назвать в команде — для подсказки и сообщения об ошибке."""
    return sorted(FORMS)


#: Регистровый файл окна: ассемблер принимает %r0…%r63 и не больше — проверено
#: перебором, предел один при любом `wsz`. Приёмники берём из верхней половины,
#: источники из нижней: так у первых 32 операций приёмники РАЗНЫЕ, и они
#: остаются по-настоящему независимыми. Дальше приёмники пойдут по кругу, и
#: появятся зависимости по перезаписи — генератор об этом честно предупреждает
#: в шапке, а не делает вид, что операции всё ещё независимы.
MAX_REG = 63
DST_BASE, DST_COUNT = 32, 32
SRC_BASE, SRC_COUNT = 1, 15


def _regs(k: int) -> tuple[int, int, int, int]:
    """Номера регистров для k-й операции: два-три источника и приёмник."""
    a = SRC_BASE + (k % SRC_COUNT)
    b = SRC_BASE + SRC_COUNT + (k % SRC_COUNT)
    c = SRC_BASE + ((k + 7) % SRC_COUNT)
    d = DST_BASE + (k % DST_COUNT)
    return a, b, c, d


def _op_text(op: str, channel: int, k: int) -> str:
    mnemonic, form = FORMS[op]
    a, b, c, d = _regs(k)
    return f"{mnemonic},{channel}\t" + form.format(a=a, b=b, c=c, d=d)


def independent(model: MachineModel, op: str, count: int,
                *, packed: bool = False) -> str:
    """`count` независимых операций класса `op`.

    `packed=False` (по умолчанию) — по одной в широкой команде. Так пишет
    человек и так же выдаёт нейросеть: законно, считает верно и оставляет
    машину почти пустой. Дальше F5 показывает разрыв, F6 укладывает плотно —
    это и есть основной цикл инструмента, и генератор готовит для него вход.

    `packed=True` — сразу плотно, по всем каналам, где операция исполнима.
    Полезно как «вот предел» рядом с предыдущим.
    """
    ports = model.channels_for(op)
    if not ports:
        raise ValueError(f"{op} негде исполнить в профиле {model.name}")

    lines = [
        f"! {count} независимых операций {FORMS[op][0]} — "
        + ("плотно, по всем каналам" if packed else "по одной в такт"),
        f"! каналы класса {op}: "
        + " ".join(f",{p}" for p in ports)
        + f"  ·  латентность {model.latency(op)} т."
        + (f"  ·  держит порт {model.occupancy(op)} т."
           if model.occupancy(op) > 1 else ""),
        "!",
    ]
    if count > DST_COUNT:
        lines.append(f"! ВНИМАНИЕ: приёмников в окне {DST_COUNT}, а операций "
                     f"{count} — начиная с {DST_COUNT + 1}-й они пишут в уже")
        lines.append("! занятые регистры, то есть перестают быть независимыми.")
        lines.append("!")
    lines.append("! F5 — прогнать, F6 — переписать по оракулу.")

    if packed:
        # По одной операции на каждый доступный канал, пока они не кончатся.
        per_bundle = len(ports)
        for start in range(0, count, per_bundle):
            lines.append("{")
            for k in range(start, min(start + per_bundle, count)):
                lines.append("  " + _op_text(op, ports[(k - start) % per_bundle], k))
            lines.append("}")
    else:
        home = ports[0]
        for k in range(count):
            lines.append("{")
            lines.append("  " + _op_text(op, home, k))
            lines.append("}")
    return "\n".join(lines) + "\n"


def chain(model: MachineModel, op: str, count: int) -> str:
    """Цепочка из `count` зависимых операций: каждая ждёт предыдущую.

    Показывает не ширину машины, а её латентность: сколько бы каналов ни
    было, цепочка длиной N займёт не меньше N × латентность тактов. Это
    честный предел, на котором планировщику нечего улучшать, — и увидеть его
    так же важно, как увидеть простой.
    """
    ports = model.channels_for(op)
    if not ports:
        raise ValueError(f"{op} негде исполнить в профиле {model.name}")
    lat = model.latency(op)
    lines = [
        f"! цепочка из {count} зависимых {FORMS[op][0]}: каждая ждёт предыдущую",
        f"! латентность {lat} т. → короче {count * lat} т. это не уложится,",
        "! сколько бы каналов ни было свободно. Резерва здесь нет, и это",
        "! правильный ответ планировщика, а не его молчание.",
        "!",
        "! F5 — прогнать.",
    ]
    for k in range(count):
        lines.append("{")
        # Приёмник предыдущей — источник следующей: это и есть цепочка.
        prev = DST_BASE + ((k - 1) % DST_COUNT) if k else SRC_BASE
        cur = DST_BASE + (k % DST_COUNT)
        mnemonic, form = FORMS[op]
        lines.append(f"  {mnemonic},{ports[0]}\t"
                     + form.format(a=prev, b=SRC_BASE + 1, c=prev, d=cur))
        lines.append("}")
    return "\n".join(lines) + "\n"


def filler(model: MachineModel, cycles: int) -> str:
    """`cycles` тактов заполнителя — независимые сложения по одному в такт.

    Нужен, когда важна не сама работа, а её объём: растянуть участок, отодвинуть
    операцию, посмотреть, что будет на длинном коде. Сложение выбрано потому,
    что оно исполнимо во всех шести каналах и не создаёт дефицита.
    """
    ports = model.channels_for("ADD")
    lines = [
        f"! заполнитель: {cycles} тактов независимых сложений",
        "! ничего не считает, нужен чтобы занять место.",
    ]
    for k in range(cycles):
        lines.append("{")
        lines.append("  " + _op_text("ADD", ports[k % len(ports)], k))
        lines.append("}")
    return "\n".join(lines) + "\n"
