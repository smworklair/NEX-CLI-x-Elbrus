"""Справочник системы команд e2k: то, что удалось ИЗМЕРИТЬ, и то, что нет.

ЗАЧЕМ
-----
МЦСТ описание системы команд не публикует. У Intel такой документ есть в двух
видах, и путать их нельзя:

* SDM том 2 — семантика и кодировка: что инструкция делает, какие операнды,
  какие флаги. Этого здесь НЕТ и быть не может: придумать кодировки значит
  выдать догадку за факт.
* Приложение к оптимизационному руководству — сколько инструкция СТОИТ: на
  какие порты уходит, латентность, темп приёма. Народный эквивалент —
  таблицы Агнера Фога и uops.info. Вот это здесь есть, потому что это
  измеряется снаружи, без документации.

Для Эльбруса второго не существует публично вообще. Поэтому справочник
собирается ровно из `model.py` и `asm_parser.py` — генератором, а не руками,
чтобы он не разъезжался с тем, по чему инструмент реально считает.

ЧЕСТНОСТЬ ЗДЕСЬ — ГЛАВНОЕ
------------------------
Из девятнадцати классов латентность измерена у восьми. У остальных стоит
единица, и это ДОПУЩЕНИЕ, а не результат. Справочник, который об этом умолчит,
бесполезен и заслуженно будет назван выдумкой.

Поэтому источник печатается в самой строке таблицы, а не в сноске внизу, и
дыры сведены отдельным списком — как приглашение их закрыть, а не как стыд.
"""

from __future__ import annotations

from dataclasses import dataclass

from .model import ASSUMED, DEFAULT_PROFILE, MachineModel, get_profile

# Запреты на СОЧЕТАНИЯ операций в одной широкой команде. Сняты полным
# перебором пар у ассемблера: собрать команду из двух по отдельности законных
# операций и посмотреть, примет ли он её. Из 119 пар запрещены ровно две.
#
# В профиль планировщика они НЕ заведены намеренно (см. HANDOFF.md): смена
# модели мира обесценила бы все снятые замеры разом. Здесь они как измеренный
# факт о машине, а не как параметр расчёта.
COMBINATION_BANS = (
    ("STORE", 2, "LOAD", 3,
     "Error: the combination of STORE in ALC2 with LOAD in ALC3 is prohibited"),
    ("STORE", 5, "LOAD", 0,
     "Error: the combination of STORE in ALC5 with LOAD in ALC0 is prohibited"),
)

CLUSTERS = ((0, 1, 2), (3, 4, 5))
"""Кластеры каналов. Наблюдаемы через запреты выше — швы проходят по парам
(2,3) и (5,0), то есть между кластерами. Как МЕЖКЛАСТЕРНАЯ ЗАДЕРЖКА это снять
локальным тулчейном нельзя, и в модели её нет (examples/probes/README.md)."""


@dataclass(frozen=True)
class IsaClass:
    """Один класс операций со всем, что о нём известно и чем это получено."""

    name: str
    latency: int
    latency_source: str
    occupancy: int
    occupancy_source: str
    channels: tuple[int, ...]
    mnemonics: tuple[str, ...]

    @property
    def peak_per_cycle(self) -> float:
        """Сколько таких операций машина принимает за такт в пределе.

        Каналов делить на такты удержания порта: шесть каналов при занятии 1
        дают 6 операций в такт, единственный делитель при занятии 2 — 0.5.
        Это тот же смысл, что «throughput» в таблицах Агнера Фога.
        """
        return len(self.channels) / self.occupancy

    @property
    def latency_measured(self) -> bool:
        return self.latency_source != ASSUMED

    @property
    def occupancy_measured(self) -> bool:
        return self.occupancy_source != ASSUMED

    @property
    def monopoly(self) -> bool:
        """Класс, у которого канал ровно один. Отсюда берётся вся трудность
        планирования: две такие операции в одном такте не разойдутся."""
        return len(self.channels) == 1


def collect(model: MachineModel | None = None) -> list[IsaClass]:
    """Справочник целиком, из модели машины и разметки мнемоник.

    Порядок — от самых узких классов к самым широким: сначала то, где
    планировщику тесно, потому что именно там теряются такты.
    """
    from . import model as _m
    from .asm_parser import MNEMONICS

    model = model or get_profile(DEFAULT_PROFILE)

    by_class: dict[str, list[str]] = {}
    for mnemonic, cls in MNEMONICS.items():
        by_class.setdefault(cls, []).append(mnemonic)

    rows: list[IsaClass] = []
    for name, oc in _m._OPS.items():
        if name == "UNKNOWN":
            # Не класс машины, а честное «не знаю» разбора: его числа —
            # заглушка по построению, печатать их справочником нельзя.
            continue
        rows.append(IsaClass(
            name=name,
            latency=oc.latency,
            latency_source=oc.latency_source,
            occupancy=oc.occupancy,
            occupancy_source=oc.occupancy_source,
            channels=tuple(_m._PORTS_FOR_OP[name]),
            mnemonics=tuple(sorted(by_class.get(name, ()))),
        ))
    rows.sort(key=lambda r: (len(r.channels), -r.latency, r.name))
    return rows


def gaps(rows: list[IsaClass]) -> list[IsaClass]:
    """Классы, у которых латентность — допущение, а не измерение.

    Это и есть список того, что стоит попросить измерить у людей с настоящей
    машиной: приём известен (цепочка зависимых операций), не хватает только
    железа.
    """
    return [r for r in rows if not r.latency_measured]
