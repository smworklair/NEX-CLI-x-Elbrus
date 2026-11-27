"""SEED: use the model response as a hint to exact search, not a replacement.

WHY
---
`vliw/core/oracle.py` anticipated this design before the model existed:
the portfolio fallback runs the greedy engine with hundreds of priority
vectors — conceptually what a learned model does instead of a single fixed
heuristic. Here the model plugs directly into that slot.

HOW THIS DIFFERS FROM CAB
-------------------------
CAB (`portfolio.py`) turns the model output into a VALID schedule and stops:
it cannot prove optimality. SEED hands the same material to exact search,
which does prove optimality:

* CAB  — final answer comes from the model (or heuristic if shorter);
* SEED — final answer comes from the oracle; the model only helps it faster.

Key property: **the model cannot make the answer worse.** The hint enters
search only as an upper bound (strictly shorter valid complete schedule)
and as priority vectors for the portfolio. No lower-bound proof depends on it.

WHAT IS NOT PROMISED
--------------------
Guaranteed speedup. Oracle iterative deepening runs BOTTOM-UP (`range(lb, ub)`),
so a tighter upper bound does not skip expensive infeasible lower targets.
Its three benefits (all to be measured, not assumed): instant proof when the
hint hits the lower bound, a narrower proven interval on timeout, and a
shorter loop when the optimum equals the upper bound.
"""

from __future__ import annotations

from ..core.dag import DAG
from ..core.model import MachineModel
from ..core.oracle import Hint
from .portfolio import choose, floor_from_model, order_from_model, variants


def hint_from_answer(dag: DAG, model: MachineModel,
                     placements: dict[int, tuple[int, int]],
                     *, source: str = "model") -> Hint:
    """Model response -> oracle Hint.

    The schedule comes from CAB (best VALID portfolio candidate, since an
    upper bound must be valid). Priority vectors match what CAB passes to
    `list_schedule`, giving the oracle portfolio the same model guidance.
    """
    from ..core.dag import compute_metrics

    metrics = compute_metrics(dag, model)
    best = choose(variants(dag, model, placements))
    greedy = next((v for v in variants(dag, model, placements)
                   if v.name == "greedy"), None)
    limit = greedy.makespan if greedy is not None else len(dag) * 4
    return Hint(
        schedule=best.schedule if best.legal else None,
        priority=tuple(order_from_model(placements, len(dag), metrics.height)),
        defer=floor_from_model(placements, limit),
        source=source,
    )
