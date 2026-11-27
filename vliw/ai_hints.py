"""Lightweight local neural helper: TINY AI (TINY Flash).

TINY Flash runs automatically on every new block: it builds a schedule for the block
(vliw/tiny) that is guaranteed to be "no worse than baseline". This module only computes
and returns data; what to display is decided by the screen (AI panel in LAB) and the
agent context. Any failure (missing weights, no numpy) quietly returns None:
the tool works fine without the neural network.
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
    через_ядро: bool = False   # True: computed by the NEX core "scheduler" block (nex_core), not a direct call


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
    # Primary path: NEX core "scheduler" block (TINY AI inside the NNL core). Fallback: direct TINY AI call.
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
    """Blocks from `.s` sorted descending by actual TINY Flash gain over baseline.

    Returns (first `limit` rows, total number of blocks).
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
    # blocks where TINY AI actually won first; tie-break by larger block size
    rows.sort(key=lambda r: (-r.tiny_gain, -r.n))
    return rows[:limit], len(rows)


def collect(session, base=None, orc=None, with_blocks: bool = True) -> Hints:
    """Everything for the panel: TINY AI on the current block and (if `.s` is loaded) per-block breakdown."""
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
    """Narrator lines from the NEX core (facts from the technical spec). Empty if core is absent (agent uses fallback path)."""
    cached = session.peek()
    if cached is None:
        return []
    try:
        from nex_core import ядро as _ядро

        return _ядро.факты(session.dag_obj, session.model(), cached[1].schedule.makespan)
    except Exception:
        return []
