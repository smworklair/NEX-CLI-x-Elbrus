"""Graph hardness: how many cycles can be saved over the greedy heuristic.

Only graphs where the oracle proves optimality (`Hardness.proven == True`)
count as genuinely hard, preventing unproven references from poisoning datasets.
"""

from __future__ import annotations

from dataclasses import dataclass

from .baseline import GreedyListScheduler
from .dag import DAG
from .model import MachineModel
from .oracle import OracleScheduler
from .schedule import Schedule


@dataclass(frozen=True)
class Hardness:
    """Cycles recoverable over the greedy heuristic on this DAG."""

    baseline: int
    """Greedy schedule makespan."""
    optimum: int
    """Optimal makespan if proven, otherwise best found."""
    proven: bool
    """Whether optimality was proven (otherwise `gap` is only a lower bound)."""
    schedule: Schedule
    """Optimal schedule ready to use as a training reference."""

    @property
    def gap(self) -> int:
        return self.baseline - self.optimum

    @property
    def hard(self) -> bool:
        """True iff optimality is proven and baseline has headroom to beat."""
        return self.proven and self.gap > 0


def measure(dag: DAG, model: MachineModel, *, budget_s: float = 10.0) -> Hardness:
    """Compare greedy vs exact search on a single DAG."""
    base = GreedyListScheduler().schedule(dag, model)
    orc = OracleScheduler(budget_s=budget_s, portfolio_s=0.5).schedule(dag, model)
    return Hardness(
        baseline=base.schedule.makespan,
        optimum=orc.schedule.makespan,
        proven=bool(orc.optimal),
        schedule=orc.schedule,
    )


def harvest_one(task: tuple[int, int, int, str]) -> dict | None:
    """Generate one candidate DAG, measure hardness, return encoded example or None.

    Top-level pickle-friendly worker taking primitive args and lazy imports.
    """
    import random

    from training.encode import encode_completion, encode_prompt

    from .dag import Instr
    from .model import get_profile

    seed, n_lo, n_hi, profile = task
    from tools.vliw_gen import PRESSURE_WEIGHTS, SHAPES, gen_graph

    model = get_profile(profile)
    rnd = random.Random(seed)
    n = rnd.randint(n_lo, n_hi)
    shape = rnd.choice(SHAPES)
    raw = gen_graph(rnd, n, shape, PRESSURE_WEIGHTS)
    dag = DAG("hard", "", "",
              [Instr(x.id, f"n{x.id}", x.op, x.preds, f"n{x.id}") for x in raw])

    h = measure(dag, model, budget_s=6.0)
    if not h.hard:
        return None
    return {
        "prompt": encode_prompt(dag, model),
        "completion": encode_completion(h.schedule),
        "meta": {"makespan": h.optimum, "n": n, "shape": shape,
                 "gap": h.gap, "baseline": h.baseline, "seed": seed},
    }
