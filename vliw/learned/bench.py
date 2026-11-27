"""Evaluate the learned model on an eval file — locally, without Kaggle.

Why built into the tool rather than a standalone script: previously the only
way to measure the model was `training/validate_kaggle.py`, which targets Kaggle
(loads torch, waits for GPU, prints its own summary). While evaluation lived
only there, every hypothesis check hit the 30h/week GPU quota.

This runs the same benchmark on the local engine. The classifier intentionally
matches `validate_kaggle.classify()`: "valid" / "tail" (valid prefix, but the
model did not stop) / "resource" (operation placed on an unsupported channel) /
"other". Separating tail from invalid is not pedantry — it caught the EOS bug,
see docs/archive/EOS_INCIDENT.md.

Breakdown is stratified by STORE presence in the graph, not just size. See
docs/archive/ROADMAP.md: run-1 training data had zero STORE ops, which gets
blurred in size buckets but stands out immediately by STORE.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class SampleOutcome:
    """Outcome of a single sample within best-of: exactly what selection uses.

    `gap` is set only for a valid sample: comparing makespan of broken
    outputs against the optimum is meaningless.
    """

    valid: bool
    errors: int
    missing: int
    makespan: int
    gap: int | None = None


@dataclass(frozen=True)
class BestOf:
    """N samples per graph at temperature>0, selecting best by validate().

    Why: repair() fixes ONLY channels (see its docstring) — it deliberately
    leaves dependency and port-occupancy violations untouched. Another sample
    may avoid them altogether: with temperature>0 the model writes slightly
    different schedules, so a valid one appears more often across N tries.

    `seed` is the base: sample k gets seed+k. Pinned for reproducibility:
    without it reruns would drift, and using the same seed for all k would
    produce N identical answers and degenerate best-of.
    """

    n: int = 1
    temperature: float = 0.0
    seed: int = 1

    def sample_seed(self, k: int) -> int:
        return self.seed + k


@dataclass
class BenchRow:
    n: int
    kind: str
    has_store: bool
    gap: int | None = None
    first_error: str = ""
    samples: list[SampleOutcome] | None = None
    """Best-of samples in order k=0..N-1. None for standard deterministic run.

    Storing all of them (not just the winner) powers the table: best-of-2 and
    best-of-4 are just prefixes of the same samples. One run with N=8 answers
    all k <= 8 without separate passes.
    """

    cab_improved: bool = False
    """Portfolio winner is strictly shorter than the greedy candidate, not a tie."""

    cab_winner: str | None = None
    """Winner of the CAB portfolio on this graph. None if portfolio is off.

    Without this, the benchmark tells "how many cycles" but not "whose work":
    on the hard eval set, the greedy candidate sits in the portfolio and
    prevents regressions below baseline, so the mean alone cannot show whether
    the model helped or merely stayed out of the way.
    """

    @property
    def valid_samples(self) -> int:
        return sum(1 for s in self.samples or () if s.valid)


@dataclass
class BenchResult:
    rows: list[BenchRow] = field(default_factory=list)
    seconds: float = 0.0
    best_of: BestOf | None = None

    @property
    def valid(self) -> int:
        return sum(1 for r in self.rows if r.kind == "valid")

    def pct(self, n: int) -> float:
        return 100.0 * n / len(self.rows) if self.rows else 0.0

    def by_kind(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for r in self.rows:
            out[r.kind] = out.get(r.kind, 0) + 1
        return out

    def cab_winners(self) -> dict[str, tuple[int, int]]:
        """{candidate: (wins, strictly_better_than_greedy)}.

        The second number is the true contribution: a tied win means the
        candidate matched the heuristic rather than beating it.
        """
        out: dict[str, list[int]] = {}
        for r in self.rows:
            if r.cab_winner:
                slot = out.setdefault(r.cab_winner, [0, 0])
                slot[0] += 1
                slot[1] += 1 if r.cab_improved else 0
        return {k: (v[0], v[1]) for k, v in out.items()}

    def split_store(self) -> dict[bool, tuple[int, int]]:
        """{has_store: (valid_count, total)} — primary diagnostic split."""
        out: dict[bool, list[int]] = {True: [0, 0], False: [0, 0]}
        for r in self.rows:
            out[r.has_store][1] += 1
            if r.kind == "valid":
                out[r.has_store][0] += 1
        return {k: (v[0], v[1]) for k, v in out.items()}

    def best_of_valid(self, k: int) -> tuple[int, int]:
        """(valid among first k samples, rows with samples).

        "Valid at best-of-k" means AT LEAST ONE of the first k samples is
        valid — selection minimizes violations, so any valid sample beats
        every invalid one.
        """
        rows = [r for r in self.rows if r.samples]
        return (sum(1 for r in rows if any(s.valid for s in r.samples[:k])),
                len(rows))


def _parse_graph(prompt: str):
    from ..core.dag import Instr

    instrs = []
    for line in prompt.split("\n")[2:]:
        line = line.strip()
        if line in ("schedule:", "\u0440\u0430\u0441\u043f\u0438\u0441\u0430\u043d\u0438\u0435:") or not line:
            continue
        head, _, preds_s = line.partition(" <- ")
        idx_s, _, op = head.partition(" ")
        preds = tuple(int(p) for p in preds_s.split()) if preds_s else ()
        i = int(idx_s)
        instrs.append(Instr(i, f"n{i}", op, preds, f"n{i}"))
    return instrs


def _candidate_key(res):
    """Best-of candidate ordering: fewer violations -> smaller makespan.

    validate() errors and unplaced instructions count EQUALLY: both are a
    schedule failure, not partial credit. Makespan is only a tie-breaker:
    comparing makespan of broken outputs is meaningless, while between two
    valid schedules it measures plan quality.
    """
    st = res.search_stats
    unplaced = 0 if res.schedule.complete else len(st["missing"])
    return (len(st["errors"]) + unplaced, res.schedule.makespan)


def _sample_outcome(res, meta_makespan: int) -> SampleOutcome:
    st = res.search_stats
    return SampleOutcome(
        valid=st["valid"],
        errors=len(st["errors"]),
        missing=0 if res.schedule.complete else len(st["missing"]),
        makespan=res.schedule.makespan,
        gap=res.schedule.makespan - meta_makespan if st["valid"] else None,
    )


def _candidates(scheduler, dag, model, best_of: BestOf | None):
    """All model responses for one graph. Without best_of, a single standard call."""
    if best_of is None:
        return [scheduler.schedule(dag, model)]

    # Attributes rather than schedule() arguments: the Scheduler protocol is
    # fixed, and bench varies sampling across attempts. Missing attributes mean
    # this is not a learned scheduler, so best-of does not apply.
    if not hasattr(scheduler, "temperature"):
        raise TypeError(
            "best-of requires a learned scheduler with sampling "
            "(vliw.learned.LearnedScheduler)")

    out = []
    for k in range(max(1, best_of.n)):
        scheduler.temperature = best_of.temperature
        scheduler.seed = best_of.sample_seed(k)
        out.append(scheduler.schedule(dag, model))
    return out


def run_bench(dataset: Path, limit: int, scheduler, model,
              on_row=None, best_of: BestOf | None = None) -> BenchResult:
    """Run `limit` examples. `on_row` is called after each for progress reporting.

    `best_of` enables picking from N samples at temperature>0: each sample
    passes through the same pipeline (including scheduler repair()), winning
    by fewest violations, then smallest makespan. None uses the standard
    single deterministic response.
    """
    from ..core.dag import DAG

    res = BenchResult(best_of=best_of)
    t0 = time.monotonic()
    with dataset.open(encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            if len(res.rows) >= limit:
                break
            row = json.loads(line)
            instrs = _parse_graph(row["prompt"])
            dag = DAG("bench", "bench", "", instrs)
            has_store = any(i.op == "STORE" for i in instrs)
            meta_makespan = row.get("meta", {}).get("makespan", 0)

            cands = _candidates(scheduler, dag, model, best_of)
            r = min(cands, key=_candidate_key) if len(cands) > 1 else cands[0]

            st = r.search_stats
            if st["valid"]:
                kind = "valid"
                gap = r.schedule.makespan - meta_makespan
            elif not st["errors"] and not st["missing"]:
                kind, gap = "tail", None
            elif any("does not execute" in e or "cannot execute" in e or "\u043d\u0435 \u0438\u0441\u043f\u043e\u043b\u043d\u044f\u0435\u0442" in e for e in st["errors"]):
                kind, gap = "resource", None
            else:
                kind, gap = "other", None

            br = BenchRow(n=len(instrs), kind=kind, has_store=has_store, gap=gap,
                          cab_winner=st.get("cab_winner"),
                          cab_improved=bool(st.get("cab_beat_greedy")),
                          first_error=(st["errors"][0] if st["errors"] else ""),
                          samples=([_sample_outcome(c, meta_makespan)
                                    for c in cands] if best_of is not None else None))
            res.rows.append(br)
            if on_row:
                on_row(len(res.rows), br)
    res.seconds = time.monotonic() - t0
    return res
