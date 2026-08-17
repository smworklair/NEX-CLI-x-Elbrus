"""Расписание: размещение инструкций по (такт, канал) + проверка и метрики."""

from __future__ import annotations

from dataclasses import dataclass, field

from .dag import DAG
from .model import MachineModel


@dataclass(frozen=True)
class Placement:
    instr: int
    cycle: int
    channel: int


@dataclass
class Schedule:
    dag: DAG
    model: MachineModel
    placements: dict[int, Placement] = field(default_factory=dict)

    # --- построение -------------------------------------------------------

    def place(self, instr: int, cycle: int, channel: int) -> None:
        self.placements[instr] = Placement(instr, cycle, channel)

    def cycle_of(self, instr: int) -> int:
        return self.placements[instr].cycle

    def ready_at(self, instr: int) -> int:
        """Такт, начиная с которого результат инструкции доступен потребителю."""
        p = self.placements[instr]
        return p.cycle + self.model.latency(self.dag[instr].op)

    # --- метрики ----------------------------------------------------------

    @property
    def complete(self) -> bool:
        return len(self.placements) == len(self.dag)

    @property
    def makespan(self) -> int:
        """Тактов до готовности ВСЕХ результатов участка.

        Считаем по готовности, а не по такту выдачи: иначе длинное деление
        в последней широкой команде выглядело бы бесплатным.
        """
        if not self.placements:
            return 0
        return max(self.ready_at(i) for i in self.placements)

    @property
    def bundle_count(self) -> int:
        """Сколько широких команд реально выдано (непустых тактов)."""
        return len({p.cycle for p in self.placements.values()})

    @property
    def span_cycles(self) -> int:
        """От первого до последнего такта выдачи включительно."""
        if not self.placements:
            return 0
        return max(p.cycle for p in self.placements.values()) + 1

    @property
    def slot_utilization(self) -> float:
        """Доля занятых слотов широкой команды за время выдачи."""
        total = self.span_cycles * self.model.width
        return len(self.placements) / total if total else 0.0

    def busy_map(self) -> dict[tuple[int, int], tuple[int, bool]]:
        """(такт, канал) -> (инструкция, это такт выдачи?).

        Операции с occupancy > 1 (деление) занимают клетки и в последующих
        тактах — они помечаются как «продолжение».
        """
        out: dict[tuple[int, int], tuple[int, bool]] = {}
        for p in self.placements.values():
            occ = self.model.occupancy(self.dag[p.instr].op)
            for k in range(occ):
                out[(p.cycle + k, p.channel)] = (p.instr, k == 0)
        return out

    # --- проверка ---------------------------------------------------------

    def validate(self) -> list[str]:
        """Полная проверка корректности. Пустой список = расписание законно."""
        errs: list[str] = []
        if not self.complete:
            missing = sorted(set(range(len(self.dag))) - set(self.placements))
            errs.append(f"не размещены инструкции: {missing}")
            return errs

        # 1. Зависимости.
        for ins in self.dag:
            for p in ins.preds:
                need = self.ready_at(p)
                got = self.cycle_of(ins.id)
                if got < need:
                    errs.append(
                        f"{ins.name} выдана в такте {got}, но операнд "
                        f"{self.dag[p].name} готов только к такту {need}"
                    )

        # 2. Возможности каналов.
        for p in self.placements.values():
            op = self.dag[p.instr].op
            if p.channel not in self.model.channels_for(op):
                errs.append(
                    f"{self.dag[p.instr].name} ({op}) поставлена на канал "
                    f"{p.channel}, который её не исполняет"
                )

        # 3. Конфликты за канал (с учётом монопольного занятия).
        seen: dict[tuple[int, int], int] = {}
        for p in sorted(self.placements.values(), key=lambda x: (x.cycle, x.channel)):
            occ = self.model.occupancy(self.dag[p.instr].op)
            for k in range(occ):
                cell = (p.cycle + k, p.channel)
                if cell in seen:
                    errs.append(
                        f"конфликт на канале {p.channel} в такте {p.cycle + k}: "
                        f"{self.dag[seen[cell]].name} и {self.dag[p.instr].name}"
                    )
                seen[cell] = p.instr

        # 4. Ширина широкой команды.
        per_cycle: dict[int, int] = {}
        for p in self.placements.values():
            per_cycle[p.cycle] = per_cycle.get(p.cycle, 0) + 1
        for c, k in sorted(per_cycle.items()):
            if k > self.model.width:
                errs.append(f"такт {c}: {k} операций при ширине {self.model.width}")

        return errs


# --------------------------------------------------------------------------
# Состояние машины во время планирования (общее для всех планировщиков)
# --------------------------------------------------------------------------


class ChannelState:
    """До какого такта каждый канал занят."""

    def __init__(self, width: int):
        self.free_at = [0] * width

    def copy(self) -> "ChannelState":
        c = ChannelState(len(self.free_at))
        c.free_at = list(self.free_at)
        return c

    def free_channels(self, cycle: int, capable: tuple[int, ...]) -> list[int]:
        return [c for c in capable if self.free_at[c] <= cycle]

    def occupy(self, channel: int, cycle: int, occupancy: int) -> None:
        self.free_at[channel] = cycle + occupancy
