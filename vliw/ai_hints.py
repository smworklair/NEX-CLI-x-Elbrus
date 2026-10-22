"""Две маленькие нейросети рядом: крошки (TINY AI) и ядра NNL (NNL AI).

Обе работают сами, на каждом новом участке и на каждом вопросе агенту, команд не нужно.
Они отвечают на РАЗНЫЕ вопросы и друг другу не подсказывают:

  TINY AI — планирует: строит расписание участка (vliw/tiny), честно «не хуже baseline».
  NNL AI  — оценивает: «есть ли на этом участке что улучшать» (nnl_vliw/выигрыш.py).
            Не строит расписание, не меняет чужие числа; при сомнении говорит «не знаю»,
            и тогда поиск идёт как обычно.

Модуль только считает и возвращает данные: что показать, решает экран (панель НЕЙРОСЕТИ в
РАЗБОРе) и контекст агента. Любой сбой (нет весов, нет numpy) даёт None — тихо, без шума:
инструмент работает и без нейросетей.
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


@dataclass
class NnlAI:
    verdict: str | None      # "есть" | "нет" | None («не знаю»)
    a: tuple                 # (исход|None, p, p_есть) — ядро А
    b: tuple                 # то же — ядро Б
    p_есть: float            # среднее двух ядер: чем выше, тем вероятнее выигрыш
    ms: float
    rule: bool = False       # True: baseline на нижней границе — доказательство, ядра не спрашивались
    gap: int = 0             # на сколько тактов baseline длиннее нижней границы


@dataclass
class BlockRow:
    index: int
    label: str
    n: int
    baseline: int
    tiny: int
    nnl: NnlAI | None

    @property
    def tiny_gain(self) -> int:
        return self.baseline - self.tiny


@dataclass
class Hints:
    tiny: TinyAI | None = None
    nnl: NnlAI | None = None
    blocks: list[BlockRow] = field(default_factory=list)
    blocks_total: int = 0


def tiny_ai(dag, model, baseline: int, oracle: int | None = None) -> TinyAI | None:
    try:
        from .tiny.scheduler import TinyScheduler

        t0 = time.perf_counter()
        res = TinyScheduler().schedule(dag, model)
        ms = (time.perf_counter() - t0) * 1000.0
    except Exception:
        return None
    ok = not res.schedule.validate() and res.schedule.complete
    return TinyAI(baseline, oracle, res.schedule.makespan, str(res.search_stats.get("tiny_winner", "?")), ms, ok)


def nnl_ai(dag, model, baseline: int | None = None) -> NnlAI | None:
    try:
        from nnl_vliw import выигрыш as W

        if not W.доступно():
            return None
        t0 = time.perf_counter()
        r = W.оценить(dag, model, baseline)
        ms = (time.perf_counter() - t0) * 1000.0
    except Exception:
        return None
    return NnlAI(r["итог"], r["А"], r["Б"], r["p_есть"], ms, r["правило"], r["зазор"])


def block_rows(text: str, model, min_ops: int = 10, limit: int = 8) -> tuple[list[BlockRow], int]:
    """Блоки `.s` по убыванию «есть что улучшать» по мнению NNL AI.

    Рядом с каждым — что реально дал TINY AI на этом блоке (быстрые крошки) против baseline.
    Возвращает (первые `limit` строк, сколько блоков всего).
    """
    try:
        from .core.baseline import GreedyListScheduler
        from .core.blocks import block_graphs
        from .tiny.fast import TinyFastScheduler

        graphs = block_graphs(text, min_ops=min_ops)
        fast = TinyFastScheduler()
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
        rows.append(BlockRow(g.block.index, g.block.label, g.n, base, min(base, tiny), nnl_ai(g.dag, model, base)))
    # сначала блоки, где правило молчит (там поиск что-то может найти), по оценке ядер;
    # блоки на нижней границе — в конец: выигрыша там нет, доказано
    rows.sort(key=lambda r: (bool(r.nnl and r.nnl.rule), -(r.nnl.p_есть if r.nnl else -1.0), -r.n))
    return rows[:limit], len(rows)


def collect(session, base=None, orc=None, with_blocks: bool = True) -> Hints:
    """Всё для панели: оба ИИ на текущем участке и (если загружен `.s`) разбор по блокам."""
    h = Hints()
    dag, model = session.dag_obj, session.model()
    if dag is None:
        return h
    if base is not None:
        h.tiny = tiny_ai(dag, model, base.schedule.makespan, orc.schedule.makespan if orc else None)
    h.nnl = nnl_ai(dag, model, base.schedule.makespan if base is not None else None)
    text = (getattr(session, "code_text", "") or "").strip()
    if with_blocks and text:
        h.blocks, h.blocks_total = block_rows(text, model)
    return h


def nnl_facts(session) -> list[str]:
    """Строка для агента: что сказал NNL AI. Модель объясняет число, а не выдумывает своё."""
    cached = session.peek()
    if cached is None:
        return []
    nn = nnl_ai(session.dag_obj, session.model(), cached[0].schedule.makespan)
    if nn is None:
        return []
    if nn.rule:
        return ["NNL AI: baseline уже на нижней границе — искать нечего, это доказано "
                "(правило, не оценка нейросети)."]
    base = (f"NNL AI: baseline длиннее нижней границы на {nn.gap} т.; оценка ядер (на настоящем коде она слабая, "
            f"проверяется поиском): ")
    if nn.verdict == "есть":
        return [base + f"оба ядра за, p(выигрыш)≈{nn.p_есть:.2f} — поиск стоит запустить."]
    if nn.verdict == "нет":
        return [base + f"оба ядра против, p(выигрыш)≈{nn.p_есть:.2f}."]
    return [base + f"ядра не согласны — «не знаю», поиск идёт как обычно (p≈{nn.p_есть:.2f})."]
