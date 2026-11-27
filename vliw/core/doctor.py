"""Deterministic schedule diagnostics: where cycles are lost and why.

Runs rule-based detectors over a schedule to pinpoint cycle losses vs hardware
lower bounds. Pure data (`Diagnosis`); rendering lives in `vliw.ui`.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .dag import DAG, DagMetrics, compute_metrics
from .model import MachineModel
from .schedule import Schedule

# Severity threshold as a fraction of makespan.
HIGH_SHARE = 0.15
MED_SHARE = 0.05


@dataclass
class Finding:
    """Single diagnostic finding: either a recoverable scheduler loss or a hardware limit."""

    code: str            # rule code: monopoly-block, idle-stall, ...
    title: str
    cycles_lost: int     # observed cost in cycles
    where: str
    why: str
    fix: str
    kind: str = "loss"   # loss = recoverable; limit = hardware lower bound
    severity: str = "low"
    instrs: tuple[int, ...] = ()

    @property
    def recoverable(self) -> bool:
        return self.kind == "loss"

    def mark(self) -> str:
        if self.kind == "limit":
            return "="
        return {"high": "!!", "medium": "!", "low": "·"}.get(self.severity, "·")


@dataclass
class PortStat:
    index: int
    label: str
    busy: int            # busy cycles
    issued: int          # operations issued
    sole_ops: tuple[str, ...] = ()   # ops for which this port is exclusive

    def load(self, span: int) -> float:
        return (self.busy / span) if span else 0.0


@dataclass
class Diagnosis:
    """Structured schedule diagnosis for UI rendering."""

    findings: list[Finding] = field(default_factory=list)
    makespan: int = 0
    lower_bound: int = 0
    span: int = 0
    idle_cycles: int = 0
    ports: list[PortStat] = field(default_factory=list)
    slot_utilization: float = 0.0

    @property
    def total_lost(self) -> int:
        """Gap above theoretical lower bound (maximum recoverable cycles)."""
        return max(0, self.makespan - self.lower_bound)

    @property
    def top(self) -> list[Finding]:
        return self.findings[:5]

    @property
    def clean(self) -> bool:
        return not self.findings


def _severity(cost: int, makespan: int) -> str:
    if not makespan:
        return "low"
    share = cost / makespan
    if share >= HIGH_SHARE:
        return "high"
    if share >= MED_SHARE:
        return "medium"
    return "low"


def _ready_times(dag: DAG, sched: Schedule) -> list[int]:
    """Earliest cycle each instruction's operands are ready under this schedule."""
    rt = [0] * len(dag)
    for ins in dag:
        for p in ins.preds:
            rt[ins.id] = max(rt[ins.id], sched.ready_at(p))
    return rt


def diagnose(dag: DAG, model: MachineModel, sched: Schedule,
             metrics: DagMetrics | None = None) -> Diagnosis:
    """Analyze a schedule and return sorted diagnostic findings."""
    met = metrics or compute_metrics(dag, model)
    d = Diagnosis(
        makespan=sched.makespan,
        lower_bound=met.lower_bound,
        span=sched.span_cycles,
        slot_utilization=sched.slot_utilization,
    )
    d.ports = _port_stats(dag, model, sched)
    d.idle_cycles = _idle_cycles(dag, sched)

    findings: list[Finding] = []
    findings += _rule_delayed_instructions(dag, model, sched, met)
    findings += _rule_idle_stretches(dag, model, sched)
    findings += _rule_port_bottleneck(dag, model, sched, d)
    findings += _rule_gap_to_bound(dag, model, sched, met)

    for f in findings:
        f.severity = _severity(f.cycles_lost, d.makespan) if f.recoverable else "low"
    # Actionable losses first, then hardware-limit facts.
    findings.sort(key=lambda f: (f.kind != "loss", -f.cycles_lost))
    d.findings = findings
    return d


# --------------------------------------------------------------------------
# Per-port utilization stats
# --------------------------------------------------------------------------


def _port_stats(dag: DAG, model: MachineModel, sched: Schedule) -> list[PortStat]:
    busy = sched.busy_map()
    sole = model.sole_host_ops()
    stats = []
    for p in model.ports:
        cells = [c for (c, port) in busy if port == p.index]
        issued = sum(
            1 for (c, port), (_, head) in busy.items() if port == p.index and head
        )
        stats.append(PortStat(
            index=p.index, label=model.port_label(p.index),
            busy=len(cells), issued=issued,
            sole_ops=tuple(sole.get(p.index, ())),
        ))
    return stats


def _idle_cycles(dag: DAG, sched: Schedule) -> int:
    """Cycles inside the block with zero operations issued."""
    issued = {p.cycle for p in sched.placements.values()}
    last = max(issued, default=0)
    return sum(1 for t in range(last + 1) if t not in issued)


# --------------------------------------------------------------------------
# Rule 1: instruction ready earlier than issued — identify blocker
# --------------------------------------------------------------------------


def _rule_delayed_instructions(dag: DAG, model: MachineModel, sched: Schedule,
                               met: DagMetrics) -> list[Finding]:
    """Detect queued ready operations and distinguish priority inversions from hardware limits."""
    rt = _ready_times(dag, sched)
    busy = sched.busy_map()
    height = met.height
    out: list[Finding] = []

    for ins in dag:
        i = ins.id
        ac = sched.cycle_of(i)
        delay = ac - rt[i]
        if delay <= 0:
            continue

        ports = model.channels_for(ins.op)
        monopoly = len(ports) == 1

        blockers: dict[int, int] = {}
        for t in range(rt[i], ac):
            for port in ports:
                hit = busy.get((t, port))
                if hit and hit[0] != i:
                    blockers[hit[0]] = blockers.get(hit[0], 0) + 1
        if not blockers:
            continue

        worst = max(blockers, key=lambda k: blockers[k])
        held = blockers[worst]
        wname, wop = dag[worst].name, dag[worst].op
        pname = (model.port_label(ports[0]) if monopoly
                 else ",".join(model.port_label(p) for p in ports))

        # Blocker is less urgent than the delayed op -> scheduling mistake.
        wasted = height[worst] < height[i]

        if monopoly and wasted:
            out.append(Finding(
                code="monopoly-block",
                title=f"exclusive port {pname} occupied by less-urgent {wname}",
                cycles_lost=delay,
                where=f"{ins.name} ready at cyc {rt[i]}, issued at cyc {ac}",
                why=(f"port {pname} is the sole unit for {ins.op}; "
                     f"{wname} ({wop}, remaining height "
                     f"{height[worst]}) held it for {held} cyc while {ins.name} (height "
                     f"{height[i]}) waited"),
                fix=(f"issue {ins.name} before {wname}: nothing depends on {wname}, "
                     f"so it can execute later in the shadow of the long op"),
                kind="loss",
                instrs=(i, worst),
            ))
        elif monopoly:
            out.append(Finding(
                code="monopoly-queue",
                title=f"queue on exclusive port {pname}",
                cycles_lost=delay,
                where=f"{ins.name} waits from cyc {rt[i]} to cyc {ac}",
                why=(f"{wname} ({wop}) on the same exclusive port {pname} was "
                     f"at least as urgent (height {height[worst]} vs "
                     f"{height[i]}) — waiting is optimal here"),
                fix=("hardware lower bound: two operations cannot share "
                     "the same port simultaneously"),
                kind="limit",
                instrs=(i, worst),
            ))
        elif wasted:
            out.append(Finding(
                code="port-contention",
                title=f"{ins.name} ({ins.op}) waited on busy ports",
                cycles_lost=delay,
                where=f"ready at cyc {rt[i]}, issued at cyc {ac}",
                why=(f"ports {pname} were busy, longest by less-urgent {wname}"
                     f""),
                fix="spread operations across ports or cycles",
                kind="loss",
                instrs=(i, worst),
            ))
    return out


# --------------------------------------------------------------------------
# Rule 2: contiguous idle stalls
# --------------------------------------------------------------------------


def _rule_idle_stretches(dag: DAG, model: MachineModel,
                         sched: Schedule) -> list[Finding]:
    """Find zero-issue cycle spans and classify whether work could have issued."""
    issued_at: dict[int, list[int]] = {}
    for p in sched.placements.values():
        issued_at.setdefault(p.cycle, []).append(p.instr)
    last = max(issued_at, default=0)
    busy = sched.busy_map()
    rt = _ready_times(dag, sched)

    def could_issue(t: int) -> bool:
        """Check if any ready op had a free capable port in cycle t."""
        for ins in dag:
            if rt[ins.id] > t or sched.cycle_of(ins.id) <= t:
                continue
            for port in model.channels_for(ins.op):
                if (t, port) not in busy:
                    return True
        return False

    out: list[Finding] = []
    t = 0
    while t <= last:
        if t in issued_at:
            t += 1
            continue
        start = t
        while t <= last and t not in issued_at:
            t += 1
        span = t - start
        if span < 3:
            continue

        holders = {
            busy[(c, p.index)][0]
            for c in range(start, t) for p in model.ports
            if (c, p.index) in busy
        }
        # Could anything have been issued during these cycles?
        wasted = any(could_issue(c) for c in range(start, t))

        if wasted:
            why = "ready operations and free ports existed, but nothing was issued"
            fix = "fill the stall with independent work — cycles are wasted"
        elif holders:
            names = ", ".join(sorted(dag[i].name for i in holders)[:3])
            why = (f"all capable ports busy with long ops ({names}), "
                   f"and no ready work for the remaining free ports")
            fix = ("block limit: no independent work available while long ops "
                   "are in flight")
        else:
            why = "no operation is ready: waiting on producer latencies"
            fix = ("dependency chain length — stall is unavoidable under any "
                   "issue order")
        out.append(Finding(
            code="idle-stall",
            title=f"idle stall of {span} cyc (cyc {start}-{t - 1})",
            cycles_lost=span,
            where=f"cycles {start}-{t - 1}",
            why=why,
            fix=fix,
            kind="loss" if wasted else "limit",
        ))
    return out


# --------------------------------------------------------------------------
# Rule 3: port bottleneck
# --------------------------------------------------------------------------


def _rule_port_bottleneck(dag: DAG, model: MachineModel, sched: Schedule,
                          d: Diagnosis) -> list[Finding]:
    out: list[Finding] = []
    span = sched.span_cycles
    if not span:
        return out
    for st in d.ports:
        load = st.load(span)
        if load < 0.6 or not st.sole_ops:
            continue
        ops = "/".join(st.sole_ops)
        out.append(Finding(
            code="port-saturated",
            title=f"port {st.label} at {load:.0%} utilization — bottleneck",
            cycles_lost=0,   # hardware limit fact, not a scheduling loss
            where=f"port {st.label} ({ops})",
            why=(f"{st.issued} {ops} operations must pass through exclusive "
                 f"port {st.label}, busy {st.busy} of {span} cycles"),
            fix=("hardware lower bound, not a scheduler bug: speed up only "
                 "by reducing the count of these operations in the block"),
            kind="limit",
        ))
    return out


# --------------------------------------------------------------------------
# Rule 4: gap to theoretical lower bound
# --------------------------------------------------------------------------


def _rule_gap_to_bound(dag: DAG, model: MachineModel, sched: Schedule,
                       met: DagMetrics) -> list[Finding]:
    gap = sched.makespan - met.lower_bound
    if gap <= 0:
        return []
    return [Finding(
        code="above-lower-bound",
        title=f"schedule is {gap} cyc longer than theoretical lower bound",
        cycles_lost=gap,
        where=f"{sched.makespan} cyc vs lower bound {met.lower_bound} cyc",
        why=(f"bound set by {met.binding} — critical path "
             f"{met.critical_path_bound} cyc, resources {met.resource_bound} cyc"),
        fix=("part of the gap may be recoverable via issue ordering — compare with "
             "exact search using /compare"),
    )]
