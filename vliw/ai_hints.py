"""Маленькая нейросеть рядом: крошки (TINY Flash).

TINY Flash работает сама, на каждом новом участке: строит расписание участка
(vliw/tiny), честно «не хуже baseline». Модуль только считает и возвращает
данные: что показать, решает экран (панель НЕЙРОСЕТИ в РАЗБОРе) и контекст
агента. Любой сбой (нет весов, нет numpy) даёт None — тихо, без шума:
инструмент работает и без нейросети.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field


@dataclass
class TinyAI:
    baseline: int
    oracle: int | None
    tiny: int
    winner: str
    ms: float
    legal: bool
    через_ядро: bool = False   # True: посчитал блок «планировщик» ядра NEX (nex_core), а не прямой вызов


@dataclass
class BlockRow:
    index: int
    label: str
    n: int
    baseline: int
    tiny: int

    @property
    def tiny_gain(self) -> int:
        return self.baseline - self.tiny


@dataclass
class Hints:
    tiny: TinyAI | None = None
    blocks: list[BlockRow] = field(default_factory=list)
    blocks_total: int = 0


def tiny_ai(dag, model, baseline: int, oracle: int | None = None) -> TinyAI | None:
    # Основной путь: блок «планировщик» ядра NEX (крошки внутри ядра NNL). Нет ядра — прямой вызов крошек.
    try:
        from nex_core import ядро as _ядро

        r = _ядро.выполнить(dag, model)
        p = (r or {}).get("payload", {}).get("планировщик")
        if p and "tiny" in p:
            return TinyAI(p["baseline"], oracle, p["tiny"], p["победитель"], p["мс"], p["законно"], True)
    except Exception:
        pass
    try:
        from .tiny.fast import TinyFlashScheduler

        t0 = time.perf_counter()
        res = TinyFlashScheduler().schedule(dag, model)
        ms = (time.perf_counter() - t0) * 1000.0
    except Exception:
        return None
    ok = not res.schedule.validate() and res.schedule.complete
    return TinyAI(baseline, oracle, res.schedule.makespan, str(res.search_stats.get("tiny_winner", "?")), ms, ok)


def block_rows(text: str, model, min_ops: int = 10, limit: int = 8) -> tuple[list[BlockRow], int]:
    """Блоки `.s` по убыванию того, что реально дал TINY Flash против baseline.

    Возвращает (первые `limit` строк, сколько блоков всего).
    """
    try:
        from .core.baseline import GreedyListScheduler
        from .core.blocks import block_graphs
        from .tiny.fast import TinyFlashScheduler

        graphs = block_graphs(text, min_ops=min_ops)
        fast = TinyFlashScheduler()
        greedy = GreedyListScheduler()
    except Exception:
        return [], 0
    rows: list[BlockRow] = []
    for g in graphs:
        try:
            base = greedy.schedule(g.dag, model).schedule.makespan
            tiny = fast.schedule(g.dag, model).schedule.makespan
        except Exception:
            continue
        rows.append(BlockRow(g.block.index, g.block.label, g.n, base, min(base, tiny)))
    # сначала блоки, где крошки реально выиграли, при равном выигрыше — большие блоки
    rows.sort(key=lambda r: (-r.tiny_gain, -r.n))
    return rows[:limit], len(rows)


def collect(session, base=None, orc=None, with_blocks: bool = True) -> Hints:
    """Всё для панели: крошки на текущем участке и (если загружен `.s`) разбор по блокам."""
    h = Hints()
    dag, model = session.dag_obj, session.model()
    if dag is None:
        return h
    if base is not None:
        h.tiny = tiny_ai(dag, model, base.schedule.makespan, orc.schedule.makespan if orc else None)
    text = (getattr(session, "code_text", "") or "").strip()
    if with_blocks and text:
        h.blocks, h.blocks_total = block_rows(text, model)
    return h


def core_facts(session) -> list[str]:
    """Строки рассказчику от ядра NEX (фразы из техкарты). Пусто — ядра нет, агент берёт прежний путь."""
    cached = session.peek()
    if cached is None:
        return []
    try:
        from nex_core import ядро as _ядро

        return _ядро.факты(session.dag_obj, session.model(), cached[1].schedule.makespan)
    except Exception:
        return []
