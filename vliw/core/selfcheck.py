"""Independent brute-force verification of the exact oracle.

Cross-checks oracle optimality claims and `compute_metrics` lower bounds
against an exhaustive enumerator on small random DAGs and narrow machines.

Usage: python -m vliw selfcheck
"""

from __future__ import annotations

import itertools
import time
from dataclasses import dataclass

from .baseline import GreedyListScheduler
from .dag import DAG, compute_metrics, random_dag
from .model import MachineModel, get_profile
from .oracle import OracleScheduler

INF = 10**9


def brute_force_makespan(dag: DAG, model: MachineModel, limit: int) -> int:
    """True optimum via exhaustive enumeration bounded above by `limit`."""
    n = len(dag)
    lat = [model.latency(i.op) for i in dag]
    occ = [model.occupancy(i.op) for i in dag]
    capable = [set(model.channels_for(i.op)) for i in dag]
    memo: dict = {}

    def rec(t: int, uns: frozenset[int], ready: tuple[int, ...], free: tuple[int, ...]) -> int:
        if not uns:
            return 0
        if t > limit:
            return INF

        avail = [i for i in uns if all(p not in uns for p in dag[i].preds)]
        ready_now = [i for i in avail if ready[i] <= t]
        if not ready_now:
            nxt = min(max(ready[i], min(free[c] for c in capable[i])) for i in avail)
            nxt = max(nxt, t + 1)
            return INF if nxt > limit else rec(nxt, uns, ready, free)

        key = (
            uns,
            tuple(max(0, ready[i] - t) for i in range(n)),
            tuple(max(0, f - t) for f in free),
            limit - t,
        )
        if key in memo:
            return memo[key]

        free_ch = [c for c in range(model.width) if free[c] <= t]
        best = INF
        for r in range(len(ready_now), -1, -1):
            for sub in itertools.combinations(ready_now, r):
                for perm in itertools.permutations(free_ch, r):
                    if any(perm[k] not in capable[sub[k]] for k in range(r)):
                        continue
                    nf, nr = list(free), list(ready)
                    for k in range(r):
                        nf[perm[k]] = t + occ[sub[k]]
                        a = t + lat[sub[k]]
                        for s in dag.succs[sub[k]]:
                            nr[s] = max(nr[s], a)
                    finish = max((t + lat[i] for i in sub), default=0)
                    rest = rec(t + 1, uns - frozenset(sub), tuple(nr), tuple(nf))
                    if rest < INF:
                        best = min(best, max(finish, rest))
        memo[key] = best
        return best

    return rec(0, frozenset(range(n)), tuple([0] * n), tuple([0] * model.width))


@dataclass
class SelfcheckResult:
    """Pure data result of oracle self-check (formatting lives in ui/cli)."""

    checked: int
    failed: int
    problems: list[tuple[str, list[str]]]  # (check_tag, list_of_mismatches)
    seconds: float
    stopped_early: bool
    seeds: int
    sizes: tuple[int, ...]
    models: int

    @property
    def ok(self) -> bool:
        return self.failed == 0


def run_selfcheck(
    seeds: int = 40,
    sizes: tuple[int, ...] = (5, 6, 7, 8),
    widths: tuple[int, ...] = (2, 3),
    time_limit: float = 60.0,
    on_failure=None,
) -> SelfcheckResult:
    """Verify oracle against brute-force search and return SelfcheckResult."""
    profiles = [
        get_profile(p).with_width(w)
        for p in ("e2k-v6-measured", "naive_homogeneous")
        for w in widths
    ]

    checked = failed = 0
    all_problems: list[tuple[str, list[str]]] = []
    t0 = time.monotonic()
    stopped_early = False
    for seed in range(1, seeds + 1):
        for n in sizes:
            dag = random_dag(seed, n=n)
            for model in profiles:
                metrics = compute_metrics(dag, model)
                base = GreedyListScheduler().schedule(dag, model)
                orc = OracleScheduler(budget_s=10.0, portfolio_s=1.0).schedule(dag, model)
                truth = brute_force_makespan(dag, model, base.schedule.makespan)
                checked += 1
                tag = f"seed={seed} n={n} {model.name}"

                problems: list[str] = []
                if truth >= INF:
                    problems.append("brute-force search found no valid schedule")
                else:
                    if orc.optimal and orc.schedule.makespan != truth:
                        problems.append(
                            f"oracle claimed optimum {orc.schedule.makespan}, "
                            f"brute-force found {truth}"
                        )
                    if orc.schedule.makespan < truth:
                        problems.append(
                            f"oracle ({orc.schedule.makespan}) beat true "
                            f"optimum ({truth}) — schedule is invalid"
                        )
                    if metrics.lower_bound > truth:
                        problems.append(
                            f"lower bound {metrics.lower_bound} exceeds optimum {truth}"
                        )
                problems += base.schedule.validate() + orc.schedule.validate()

                if problems:
                    failed += 1
                    all_problems.append((tag, problems))
                    if on_failure is not None:
                        on_failure(tag, problems)
        if time.monotonic() - t0 > time_limit:
            stopped_early = True
            break

    return SelfcheckResult(
        checked=checked,
        failed=failed,
        problems=all_problems,
        seconds=time.monotonic() - t0,
        stopped_early=stopped_early,
        seeds=seeds,
        sizes=sizes,
        models=len(profiles),
    )
