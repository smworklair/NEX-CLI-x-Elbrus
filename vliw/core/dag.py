"""Instruction dependency DAG and built-in test scenarios.

One DAG = one basic block of straight-line code scheduled into wide
instructions. Nodes are instructions; edges are RAW dependencies.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from functools import cached_property

from .model import MachineModel

_SYMBOL = {
    "ADD": "+",
    "SUB": "-",
    "MUL": "*",
    "DIV": "/",
    "AND": "&",
    "SHL": "<<",
    # Op classes measured 2026-08-30; FP uses dotted symbols (`+.`, `*.`).
    #
    #
    #
    #
    "FADD": "+.",
    "FMUL": "*.",
    "FDIV": "/.",
    "PACK": "+|",
    "PACKLOG": "&|",
    "PRED": "?",
    "MERGE": "><",
    "INSF": ">>|",
    "COMBO": "<<+",
    "AAU": "@",
    "RW": "=>",
    "UNKNOWN": "??",
}


@dataclass(frozen=True)
class Instr:
    id: int
    name: str
    op: str
    preds: tuple[int, ...]
    text: str

    def __str__(self) -> str:
        return f"{self.name}: {self.text}"


@dataclass
class DAG:
    key: str
    title: str
    note: str
    instrs: list[Instr]
    profile: str | None = None
    """Target machine profile for this scenario (None = any)."""

    family: str = ""
    """Scenario group for /scenarios listing."""

    lesson: str = ""
    """One-line takeaway describing what this block demonstrates."""

    def __post_init__(self) -> None:
        for i, ins in enumerate(self.instrs):
            assert ins.id == i, "instructions must be numbered consecutively"
            for p in ins.preds:
                assert p < i, "predecessor must precede consumer (graph must be acyclic)"

    def __len__(self) -> int:
        return len(self.instrs)

    def __iter__(self):
        return iter(self.instrs)

    def __getitem__(self, i: int) -> Instr:
        return self.instrs[i]

    @cached_property
    def succs(self) -> list[tuple[int, ...]]:
        out: list[list[int]] = [[] for _ in self.instrs]
        for ins in self.instrs:
            for p in ins.preds:
                out[p].append(ins.id)
        return [tuple(s) for s in out]

    def op_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for ins in self.instrs:
            counts[ins.op] = counts.get(ins.op, 0) + 1
        return counts


# --------------------------------------------------------------------------
# DAG metrics relative to a specific machine model
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class DagMetrics:
    """Pre-scheduling DAG metrics: ASAP, height, and critical-path vs resource lower bounds."""

    asap: tuple[int, ...]
    """Earliest issue cycle ignoring resources (dependencies only)."""

    height: tuple[int, ...]
    """Remaining critical-path length from this instruction to completion (including its latency)."""

    critical_path_bound: int
    """Makespan lower bound from dependency chain length."""

    resource_bound: int
    """Makespan lower bound from channel throughput (energetic interval bound via `_interval_bound`)."""

    @property
    def lower_bound(self) -> int:
        return max(self.critical_path_bound, self.resource_bound)

    @property
    def binding(self) -> str:
        if self.resource_bound > self.critical_path_bound:
            return "resources"
        if self.critical_path_bound > self.resource_bound:
            return "critical path"
        return "both"


def _interval_bound(dag: DAG, model: MachineModel,
                    asap: list[int], height: list[int]) -> int:
    """Energetic interval resource lower bound: makespan >= r + q + ceil(sum(occ) / |C|)."""
    n = len(dag)
    if not n:
        return 0
    occ = [model.occupancy(i.op) for i in dag]
    chans = [frozenset(model.channels_for(i.op)) for i in dag]
    tail = [height[i] - occ[i] for i in range(n)]

    best = 0
    for group in set(chans):
        width = len(group)
        if not width:
            continue
        # Only ops whose capable channels are a subset of group C.
        idx = [i for i in range(n) if chans[i] <= group]
        if not idx:
            continue
        by_tail = sorted(idx, key=lambda i: -tail[i])
        for r in sorted({asap[i] for i in idx}):
            work = 0
            for i in by_tail:
                if asap[i] < r:
                    continue
                work += occ[i]
                cand = r + tail[i] + -(-work // width)
                if cand > best:
                    best = cand
    return best


def compute_metrics(dag: DAG, model: MachineModel) -> DagMetrics:
    n = len(dag)
    lat = [model.latency(ins.op) for ins in dag]

    asap = [0] * n
    for ins in dag:  # instructions are topologically sorted by construction
        for p in ins.preds:
            asap[ins.id] = max(asap[ins.id], asap[p] + lat[p])

    height = [0] * n
    for ins in reversed(dag.instrs):
        h = 0
        for s in dag.succs[ins.id]:
            h = max(h, height[s])
        height[ins.id] = lat[ins.id] + h

    cp_bound = max((asap[i] + height[i] for i in range(n)), default=0)

    # Resource lower bound via energetic interval bound (`_interval_bound`).
    res_bound = _interval_bound(dag, model, asap, height)

    return DagMetrics(
        asap=tuple(asap),
        height=tuple(height),
        critical_path_bound=cp_bound,
        resource_bound=max(0, res_bound),
    )


# --------------------------------------------------------------------------
# DAG builder
# --------------------------------------------------------------------------


class DagBuilder:
    def __init__(self, key: str, title: str, note: str = "", profile: str | None = None,
                 family: str = "", lesson: str = ""):
        self.key = key
        self.title = title
        self.note = note
        self.profile = profile
        self.family = family
        self.lesson = lesson
        self._instrs: list[Instr] = []

    def op(self, op: str, name: str, *preds: int, args: str | None = None) -> int:
        i = len(self._instrs)
        if args is not None:
            text = f"{name} = {args}"
        elif op in ("LOAD",):
            src = f"[{self._nm(preds[0])}]" if preds else f"[p{i}]"
            text = f"{name} = ld {src}"
        elif op == "STORE":
            text = f"st {self._nm(preds[0])}" if preds else f"st {name}"
        elif len(preds) == 2:
            text = f"{name} = {self._nm(preds[0])} {_SYMBOL[op]} {self._nm(preds[1])}"
        elif len(preds) == 1:
            text = f"{name} = {self._nm(preds[0])} {_SYMBOL[op]} c{i}"
        else:
            text = f"{name} = x{i} {_SYMBOL[op]} y{i}"
        self._instrs.append(Instr(i, name, op, tuple(preds), text))
        return i

    def _nm(self, i: int) -> str:
        return self._instrs[i].name

    def build(self) -> DAG:
        return DAG(self.key, self.title, self.note, self._instrs, self.profile,
                   self.family, self.lesson)


# --------------------------------------------------------------------------
# Built-in scenarios
# --------------------------------------------------------------------------


def _simple4() -> DAG:
    b = DagBuilder(
        "simple4",
        "Four independent ops and reduction",
        "Four independent ops of varied latency followed by pairwise reduction.\n"
        ""
        "ADD, SUB, MUL, and DIV issue in a single wide instruction; the block "
        "then waits for the longest latency to complete.",
        family="basics",
        lesson="Starting point: independent operations fan out across ports immediately.",
    )
    a = b.op("ADD", "t0")
    m = b.op("MUL", "t1")
    s = b.op("SUB", "t2")
    d = b.op("DIV", "t3")
    s0 = b.op("ADD", "s0", a, m)
    s1 = b.op("ADD", "s1", s, d)
    b.op("ADD", "r", s0, s1)
    return b.build()


def _loadchain() -> DAG:
    b = DagBuilder(
        "loadchain",
        "Eight loads: hiding 5 cycles of memory latency",
        "Eight loads and dependent arithmetic. On e2k loads run on `,0 ,2 ,3 ,5` "
        "with 5-cycle latency.\n"
        "The scheduler must separate loads from consumers and fill the gap with "
        "useful work to avoid stalls.",
        family="memory",
        lesson="Fill the 5-cycle load-to-use window with independent work.",
    )
    loads = [b.op("LOAD", f"v{i}") for i in range(8)]
    m0 = b.op("MUL", "p0", loads[0], loads[1])
    m1 = b.op("MUL", "p1", loads[2], loads[3])
    a0 = b.op("ADD", "q0", loads[4], loads[5])
    a1 = b.op("ADD", "q1", loads[6], loads[7])
    s0 = b.op("ADD", "s0", m0, m1)
    s1 = b.op("ADD", "s1", a0, a1)
    r = b.op("ADD", "r", s0, s1)
    b.op("STORE", "out", r)
    return b.build()


def _mixed18() -> DAG:
    b = DagBuilder(
        "mixed18",
        "18 instructions: mixed latencies and irregular dependencies",
        "Two divisions, four multiplications, loads, and scalar arithmetic with "
        "irregular dependencies.\n"
        "Dependency chains stretch the block while the divider queues on `,5`. "
        "Both limits appear in a single DAG.",
        family="basics",
        lesson="Mixed block: dependency chains and exclusive port contention together.",
    )
    l0 = b.op("LOAD", "v0")
    l1 = b.op("LOAD", "v1")
    l2 = b.op("LOAD", "v2")
    l3 = b.op("LOAD", "v3")
    d0 = b.op("DIV", "d0", l0, l1)
    m0 = b.op("MUL", "m0", l2, l3)
    a0 = b.op("ADD", "a0", l0, l2)
    a1 = b.op("SUB", "a1", l1, l3)
    m1 = b.op("MUL", "m1", a0, a1)
    a2 = b.op("ADD", "a2", a0, l3)
    d1 = b.op("DIV", "d1", m0, a2)
    a3 = b.op("SHL", "a3", a1)
    m2 = b.op("MUL", "m2", a2, a3)
    a4 = b.op("AND", "a4", a3, l0)
    m3 = b.op("MUL", "m3", m1, a4)
    s0 = b.op("ADD", "s0", d0, m2)
    s1 = b.op("ADD", "s1", d1, m3)
    r = b.op("ADD", "r", s0, s1)
    b.op("STORE", "out", r)
    return b.build()


def _divpressure() -> DAG:
    b = DagBuilder(
        "divpressure",
        "Four divisions on the exclusive divider",
        "Four divisions on exclusive port `,5`: one issue every 2 cycles, "
        "11-cycle latency each.\n"
        "No scheduling choice exists; baseline and oracle match at the hardware "
        "lower bound.",
        family="op cost",
        lesson="Nothing to schedule — eliminate divisions instead: see divstrength.",
    )
    divs = [b.op("DIV", f"d{i}") for i in range(4)]
    adds = [b.op("ADD", f"a{i}") for i in range(8)]
    s0 = b.op("ADD", "s0", divs[0], divs[1])
    s1 = b.op("ADD", "s1", divs[2], divs[3])
    s2 = b.op("ADD", "s2", adds[0], adds[1])
    s3 = b.op("ADD", "s3", adds[2], adds[3])
    t0 = b.op("ADD", "t0", s0, s1)
    t1 = b.op("ADD", "t1", s2, s3)
    b.op("ADD", "r", t0, t1)
    return b.build()


def _reduce_tree(b: DagBuilder, ids: list[int], prefix: str) -> int:
    """Pairwise tree reduction (like an unrolled loop epilogue)."""
    level = list(ids)
    k = 0
    while len(level) > 1:
        nxt = []
        for i in range(0, len(level) - 1, 2):
            nxt.append(b.op("ADD", f"{prefix}{k}", level[i], level[i + 1]))
            k += 1
        if len(level) % 2:
            nxt.append(level[-1])
        level = nxt
    return level[0]


def _slotclash() -> DAG:
    b = DagBuilder(
        "slotclash",
        "Divider monopoly: dead-end division vs critical division",
        "Two divisions on exclusive port `,5`: `z0` is ready at cycle 0 with no "
        "critical consumers, while `dc` is on the critical path and ready at "
        "cycle 1.\n"
        "Greedy issues `z0` immediately and blocks `,5`; oracle holds `,5` for "
        "`dc`, saving 1 cycle.",
        profile="e2k-v6-measured",
        family="exclusive port",
        lesson="Never occupy an exclusive port with non-critical work ahead of a critical op.",
    )
    a0 = b.op("ADD", "a0")            # operand of critical division, ready at cyc 1
    dz = b.op("DIV", "z0")           # dead-end division, ready at cyc 0 — trap
    dc = b.op("DIV", "dc", a0)       # critical division, ready at cyc 1
    m0 = b.op("MUL", "m0", dc)       # critical path continues with multiply
    e0 = b.op("ADD", "e0", m0)
    e1 = b.op("ADD", "e1", e0)
    e2 = b.op("ADD", "e2", e1)
    z = b.op("ADD", "z", dz)         # consumer of dead-end division (low priority)
    g0 = b.op("ADD", "g0")           # independent scalar ops to fill free ports
    g1 = b.op("ADD", "g1", g0)
    r = b.op("ADD", "r", e2, z)
    r2 = b.op("ADD", "r2", r, g1)
    b.op("STORE", "out", r2)
    return b.build()


def _mulclash() -> DAG:
    b = DagBuilder(
        "mulclash",
        "Four-channel multiply: slotclash mirror has no gap",
        "Built as a mirror of slotclash under the old 1-multiplier assumption. "
        "Assembler probing refuted this: `muls` executes on `,0 ,1 ,3 ,4` "
        "(4 per wide instruction).\n"
        ""
        "No monopoly and zero gap on e2k-v6. Kept for comparison against "
        "`e2k-v6-firstprobe`, where a false gap appears from the flawed model."
        "",
        profile="e2k-v6-measured",
        family="model check",
        lesson="Four-channel multiplier. Compare with profile e2k-v6-firstprobe.",
    )
    a0 = b.op("ADD", "a0")
    mz = b.op("MUL", "z0")           # dead-end multiply, ready at cyc 0
    mc = b.op("MUL", "mc", a0)       # critical multiply, ready at cyc 1
    d0 = b.op("DIV", "d0", mc)       # critical path feeds the divider
    e0 = b.op("ADD", "e0", d0)
    e1 = b.op("ADD", "e1", e0)
    z = b.op("ADD", "z", mz)
    g0 = b.op("ADD", "g0")
    g1 = b.op("ADD", "g1", g0)
    r = b.op("ADD", "r", e1, z)
    r2 = b.op("ADD", "r2", r, g1)
    b.op("STORE", "out", r2)
    return b.build()


# --------------------------------------------------------------------------
# Optimization-technique scenarios
#
# Scenarios below compare code transformations ("before" -> "after")
# where the algorithm itself must change rather than the schedule.
#
#
#
#
#
#
#
#
# --------------------------------------------------------------------------


def _seqreduce() -> DAG:
    b = DagBuilder(
        "seqreduce",
        "Single-accumulator reduction: no parallelism",
        "Typical loop `for (i...) acc += v[i];`: 8 independent loads followed by "
        "a serial addition chain.\n"
        "Baseline and oracle tie. Compare with `treereduce` (same op count, "
        "shorter critical path).",
        profile="e2k-v6-measured",
        family="graph shape",
        lesson="Serial `acc += x` cannot parallelize. Reassociate into a tree: treereduce.",
    )
    loads = [b.op("LOAD", f"v{i}") for i in range(8)]
    acc = b.op("ADD", "acc0", loads[0], loads[1])
    for i in range(2, 8):
        acc = b.op("ADD", f"acc{i - 1}", acc, loads[i])
    b.op("STORE", "out", acc)
    return b.build()


def _treereduce() -> DAG:
    b = DagBuilder(
        "treereduce",
        "Tree reduction: reassociation",
        "Same work and op count as seqreduce, reassociated into a binary tree: "
        "3 addition levels instead of 7.\n"
        ""
        "Compilers cannot auto-reassociate FP due to rounding; rewrite or enable "
        "fast-math. Compare: /run seqreduce, then /run treereduce."
        "",
        profile="e2k-v6-measured",
        family="graph shape",
        lesson="Same instruction count, shorter makespan from graph shape alone.",
    )
    loads = [b.op("LOAD", f"v{i}") for i in range(8)]
    r = _reduce_tree(b, loads, "s")
    b.op("STORE", "out", r)
    return b.build()


def _divstrength() -> DAG:
    b = DagBuilder(
        "divstrength",
        "Strength reduction: four divisions replaced by shifts",
        "Same DAG as divpressure with power-of-two divisor replaced by SHL: "
        "all 6 ports, latency 1, occupancy 1 vs exclusive port `,5` (lat 11, occ 2).\n"
        ""
        ""
        "All four issue in one wide instruction. For loop-invariant divisors, "
        "hoist reciprocal computation outside the loop."
        "",
        profile="e2k-v6-measured",
        family="op cost",
        lesson="Eliminating division beats scheduling it. Compare with /run divpressure.",
    )
    fast = [b.op("SHL", f"q{i}") for i in range(4)]
    adds = [b.op("ADD", f"a{i}") for i in range(8)]
    s0 = b.op("ADD", "s0", fast[0], fast[1])
    s1 = b.op("ADD", "s1", fast[2], fast[3])
    s2 = b.op("ADD", "s2", adds[0], adds[1])
    s3 = b.op("ADD", "s3", adds[2], adds[3])
    t0 = b.op("ADD", "t0", s0, s1)
    t1 = b.op("ADD", "t1", s2, s3)
    b.op("ADD", "r", t0, t1)
    return b.build()


def _ptrchase() -> DAG:
    b = DagBuilder(
        "ptrchase",
        "Pointer chasing: dependent load chain",
        "`p = p->next` six times: each address depends on the previous load "
        "(5-cycle latency -> ~30-cycle critical path).\n"
        ""
        "Independent arithmetic must be packed into the load-latency shadow. "
        "/doctor will show memory latency as the lower bound.",
        profile="e2k-v6-measured",
        family="memory",
        lesson="Dependent loads cannot reorder; hide latency with independent work.",
    )
    p = b.op("LOAD", "p0")
    for i in range(1, 6):
        p = b.op("LOAD", f"p{i}", p)
    work = [b.op("ADD", f"w{i}") for i in range(8)]
    w = _reduce_tree(b, work, "u")
    r = b.op("ADD", "r", p, w)
    b.op("STORE", "out", r)
    return b.build()


def _memstream() -> DAG:
    b = DagBuilder(
        "memstream",
        "Load-compute-store stream: store-port bottleneck",
        "Eight independent `x = a[i]; x += c; b[i] = x;` streams. Stores only "
        "encode on `,2` and `,5` (loads on 4 ports), capping throughput at 2/cycle.\n"
        ""
        "Exact search beats greedy on store-port ordering. Reduce traffic via "
        "wider types, vectorization, or loop fusion."
        "",
        profile="e2k-v6-measured",
        family="memory",
        lesson="Stores execute on only two channels (`,2` and `,5`).",
    )
    for i in range(8):
        v = b.op("LOAD", f"v{i}")
        t = b.op("ADD", f"t{i}", v)
        b.op("STORE", f"st{i}", t)
    return b.build()


def _unroll4() -> DAG:
    b = DagBuilder(
        "unroll4",
        "4x unrolled multiply-accumulate: load-latency bound",
        "Four unrolled iterations of `s += v[i] * k` with tree reduction. "
        "Four multiplies issue in parallel across 4 channels (lat 4).\n"
        ""
        "Makespan is bounded by 5-cycle load latency; hoist loads or prefetch."
        ""
        "",
        profile="e2k-v6-measured",
        family="loops",
        lesson="Unrolling works; load latency is the remaining bottleneck.",
    )
    muls = []
    for i in range(4):
        v = b.op("LOAD", f"v{i}")
        muls.append(b.op("MUL", f"m{i}", v))
    s0 = b.op("ADD", "s0", muls[0], muls[1])
    s1 = b.op("ADD", "s1", muls[2], muls[3])
    r = b.op("ADD", "r", s0, s1)
    b.op("STORE", "out", r)
    return b.build()


def _ifconv() -> DAG:
    b = DagBuilder(
        "ifconv",
        "Speculative execution of both branches",
        "Branches are costly on e2k while ports are plentiful. Long branch (6 ops) "
        "and short branch (3 ops) execute concurrently, merged conditionally.\n"
        ""
        "Twice the ops, nearly zero extra cycles — unless a branch contains DIV "
        "and hogs exclusive port `,5`."
        "",
        profile="e2k-v6-measured",
        family="branching",
        lesson="Executing both branches pays off when ops use flexible ports.",
    )
    c = b.op("SUB", "cond")
    long_br = b.op("ADD", "L0")
    for i in range(1, 6):
        long_br = b.op("ADD", f"L{i}", long_br)
    short_br = b.op("ADD", "S0")
    for i in range(1, 3):
        short_br = b.op("ADD", f"S{i}", short_br)
    sel = b.op("ADD", "sel", long_br, short_br)
    r = b.op("AND", "r", sel, c)
    b.op("STORE", "out", r)
    return b.build()


def random_dag(
    seed: int,
    n: int = 24,
    key: str | None = None,
    title: str | None = None,
    note: str = "",
    profile: str | None = None,
    weights: dict[str, float] | None = None,
    max_preds: int = 2,
    reach: int = 6,
) -> DAG:
    """Reproducible random DAG for stress-testing and benchmarking."""
    rnd = random.Random(seed)
    w = weights or {"ADD": 4, "SUB": 2, "MUL": 3, "DIV": 1, "SHL": 1, "AND": 1, "LOAD": 2}
    ops = list(w)
    probs = [w[o] for o in ops]

    b = DagBuilder(
        key or f"rand{seed}",
        title or f"Random DAG (seed={seed}, {n} instructions)",
        note,
        profile,
    )
    for i in range(n):
        op = rnd.choices(ops, probs)[0]
        cands = list(range(max(0, i - reach), i))
        k = 0 if not cands else rnd.randint(0, min(max_preds, len(cands)))
        if op in ("MUL", "DIV", "ADD", "SUB") and cands and k == 0 and rnd.random() < 0.6:
            k = 1
        preds = tuple(sorted(rnd.sample(cands, k))) if k else ()
        b.op(op, f"n{i}", *preds)
    return b.build()


def _wide_ilp() -> DAG:
    """Large high-ILP block bound by port resources rather than critical path."""
    b = DagBuilder(
        "wide_ilp",
        "Unrolled loop: throughput bound",
        "14 independent multiplies across `,0 ,1 ,3 ,4` plus heavy scalar work.\n"
        ""
        "Resource lower bound exceeds critical path; large graph triggers the "
        "oracle's portfolio fallback."
        "",
        profile="e2k-v6-measured",
        family="loops",
        lesson="Resource-bound rather than latency-bound.",
    )
    muls = [b.op("MUL", f"m{i}") for i in range(14)]
    adds = [b.op("ADD", f"a{i}") for i in range(18)]
    mid = []
    for i in range(0, 14, 2):
        mid.append(b.op("ADD", f"p{i//2}", muls[i], muls[i + 1]))
    for i in range(0, 18, 2):
        mid.append(b.op("ADD", f"q{i//2}", adds[i], adds[i + 1]))
    lvl = mid
    idx = 0
    while len(lvl) > 1:
        nxt = []
        for i in range(0, len(lvl) - 1, 2):
            nxt.append(b.op("ADD", f"r{idx}", lvl[i], lvl[i + 1]))
            idx += 1
        if len(lvl) % 2:
            nxt.append(lvl[-1])
        lvl = nxt
    return b.build()


def _twodividers() -> DAG:
    """Two distinct divider classes (INT and FP) contending on exclusive port ,5."""
    b = DagBuilder(
        "twodividers",
        "One port, two dividers: integer vs floating-point",
        "Probing showed FP division shares exclusive port `,5` with integer DIV.\n"
        ""
        ""
        ""
        "Structured like `slotclash`, but FDIV latency (14 vs 11) equalizes both "
        "heights (21 vs 21), hiding the 1-cycle port stall inside the FDIV tail."
        ""
        ""
        ""
        ""
        ""
        "",
        profile="e2k-v6-measured",
        family="exclusive port",
        lesson="Same port conflict as slotclash, but long FDIV latency hides the stall."
               ""
               ""
               "",
    )
    # Same trap structure as slotclash, with FDIV contending on exclusive port ,5.
    #
    a0 = b.op("ADD", "a0")            # operand of critical division, ready at cyc 1
    fz = b.op("FDIV", "fz")           # dead-end FDIV, ready at cyc 0
    dc = b.op("DIV", "dc", a0)        # critical DIV, operand ready at cyc 1
    m0 = b.op("MUL", "m0", dc)        # long dependent tail
    e0 = b.op("ADD", "e0", m0)
    e1 = b.op("ADD", "e1", e0)
    e2 = b.op("ADD", "e2", e1)
    zm = b.op("FMUL", "zm", fz)       # dead-end tail: FP multiply...
    z = b.op("FADD", "z", zm)         # ...and FP add (both on all 6 channels)
    g0 = b.op("ADD", "g0")
    g1 = b.op("AND", "g1", g0)
    r = b.op("ADD", "r", e2, z)
    r2 = b.op("ADD", "r2", r, g1)
    b.op("STORE", "out", r2)
    return b.build()


def _packnarrow() -> DAG:
    """Packed SIMD arithmetic: only two lanes across a 6-wide machine."""
    b = DagBuilder(
        "packnarrow",
        "SIMD on two channels: 6-wide machine cannot help",
        "Packed arithmetic (`PACK`) encodes only on `,0` and `,3` (max 2/cycle).\n"
        ""
        ""
        "Eight independent PACK ops serialize 2-per-cycle; only scalar work can "
        "fill the other four channels."
        ""
        "",
        profile="e2k-v6-measured",
        family="narrow class",
        lesson="Effective width is per-op-class ports, not total machine width."
               ""
               "",
    )
    src = b.op("LOAD", "v")
    packs = [b.op("PACK", f"p{i}", src) for i in range(8)]
    fill = [b.op("ADD", f"s{i}", src) for i in range(4)]
    acc = b.op("PACKLOG", "acc", *packs[:4])
    acc2 = b.op("PACKLOG", "acc2", acc, *packs[4:])
    tail = b.op("ADD", "t", acc2, *fill)
    b.op("STORE", "out", tail)
    return b.build()


def _predchain() -> DAG:
    """Predicates: if-conversion limited to four of six channels."""
    b = DagBuilder(
        "predchain",
        "Predicates: cost of if-converting branches",
        "Predicate comparisons (`PRED`) run on `,0 ,1 ,3 ,4` (not `,2` or `,5`).\n"
        ""
        ""
        ""
        "Six comparisons prepare masks while loads naturally take `,2` and `,5`, "
        "packing complementary channel halves cleanly."
        ""
        ""
        "",
        profile="e2k-v6-measured",
        family="narrow class",
        lesson="Complementary channel sets pack cleanly; greedy hits optimum."
               ""
               "",
    )
    a = b.op("LOAD", "a")
    c = b.op("LOAD", "c")
    preds = [b.op("PRED", f"pd{i}", a, c) for i in range(6)]
    m1 = b.op("MERGE", "m1", *preds[:3])
    m2 = b.op("MERGE", "m2", *preds[3:])
    ins = b.op("INSF", "ins", m1, m2)
    cb = b.op("COMBO", "cb", ins)
    b.op("STORE", "out", cb)
    return b.build()


SCENARIOS: dict[str, DAG] = {}


def _register(dag: DAG) -> None:
    SCENARIOS[dag.key] = dag


for _d in (
    # scheduler showcase: same DAG, two schedules
    _simple4(),
    _loadchain(),
    _mixed18(),
    _slotclash(),
    _mulclash(),
    _divpressure(),
    _wide_ilp(),
    # op classes probed 2026-08-30 (FP, predicates, SIMD)
    #
    _twodividers(),
    _packnarrow(),
    _predchain(),
    # optimization techniques: before/after pairs
    _seqreduce(),
    _treereduce(),
    _divstrength(),
    _unroll4(),
    _ptrchase(),
    _memstream(),
    _ifconv(),
):
    _register(_d)


def get_scenario(key: str) -> DAG:
    if key in SCENARIOS:
        return SCENARIOS[key]
    if key.startswith("rand"):
        try:
            return random_dag(int(key[4:]))
        except ValueError:
            pass
    raise SystemExit(
        f"unknown scenario {key!r}; available: {', '.join(SCENARIOS)} "
        f"(or randN where N is a seed)"
    )
