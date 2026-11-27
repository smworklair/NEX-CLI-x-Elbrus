"""VLIW machine model for Elbrus (e2k-v6).

Parameters are empirically probed from `lcc-1.29.16` (e2k-v6 cross-toolchain)
via three independent methods: assembler port-encoding matrix, dependent-chain
latencies, and independent-burst occupancies. Each parameter carries its source.

Intentionally omits cross-cluster pair bans (`,2` store + `,3` load, `,5` store
+ `,0` load), documented in `examples/probes/README.md`.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Mapping

# Parameter provenance labels shown in /model reports.
#
#
ASM = "verified by assembler (ALC encoding)"
CHAIN = "measured (dependent chain, lcc -O3)"
BURST = "measured (independent burst, lcc -O3)"
ASSUMED = "assumed"

# Retained for backwards compatibility with older reports.
MEASURED = CHAIN
PROBED = BURST


@dataclass(frozen=True)
class OpClass:
    """Operation class: result latency, port occupancy, and provenance."""

    name: str

    latency: int
    """Cycles until result is ready (consumer may issue at t + latency)."""

    occupancy: int = 1
    """Cycles the operation holds its port exclusively (1 = fully pipelined).

    Known conservative simplification: for DIV/FDIV this blocks both the divider
    unit and ALC slot `,5` for 2 cycles, whereas real e2k frees slot `,5` in 1.
    """

    latency_source: str = ASSUMED
    occupancy_source: str = ASSUMED

    free_slot: bool = False
    """True if encoded in a separate syllable that does not consume an ALC slot (e.g. `movaX`)."""

    def blocks_channel(self) -> bool:
        return self.occupancy > 1


@dataclass(frozen=True)
class Port:
    """Single wide-instruction port/slot (`label`, e.g. `,5`) and supported `ops`."""

    index: int
    label: str
    ops: frozenset[str]

    def can(self, op_name: str) -> bool:
        return op_name in self.ops


@dataclass(frozen=True)
class MachineModel:
    """Wide-instruction machine configuration: operation classes and port capability matrix."""

    name: str
    description: str
    ops: Mapping[str, OpClass]
    ports: tuple[Port, ...]
    matrix_source: str = ASSUMED

    # --- dimensions -------------------------------------------------------

    @property
    def width(self) -> int:
        return len(self.ports)

    # --- model queries ----------------------------------------------------

    def op(self, op_name: str) -> OpClass:
        try:
            return self.ops[op_name]
        except KeyError:
            raise KeyError(
                f"operation {op_name!r} is not defined in model {self.name!r}; "
                f"known: {', '.join(sorted(self.ops))}"
            ) from None

    def latency(self, op_name: str) -> int:
        return self.op(op_name).latency

    def occupancy(self, op_name: str) -> int:
        return self.op(op_name).occupancy

    def channels_for(self, op_name: str) -> tuple[int, ...]:
        """Port indices capable of executing `op_name`."""
        return tuple(p.index for p in self.ports if op_name in p.ops)

    def port_label(self, index: int) -> str:
        for p in self.ports:
            if p.index == index:
                return p.label
        return f",{index}"

    def sole_host_ops(self) -> dict[int, list[str]]:
        """Map port index -> ops for which it is the EXCLUSIVE port."""
        out: dict[int, list[str]] = {}
        for op_name in self.ops:
            hosts = [p.index for p in self.ports if op_name in p.ops]
            if len(hosts) == 1:
                out.setdefault(hosts[0], []).append(op_name)
        return out

    def uniform_channels(self) -> bool:
        """True if every operation can execute on every port."""
        return all(len(self.channels_for(o)) == self.width for o in self.ops)

    def has_blocking_ops(self) -> bool:
        return any(o.blocks_channel() for o in self.ops.values())

    def with_width(self, width: int) -> "MachineModel":
        """Return a copy scaled to `width` ports while preserving exclusive-port coverage."""
        if width == self.width:
            return self

        sole = set(self.sole_host_ops())
        specialized = [p for p in self.ports if p.index in sole]
        generic = [p for p in self.ports if p.index not in sole]
        # Ops for synthesized generic ports when widening beyond original width.
        #
        generic_ops = frozenset(
            op for op in self.ops
            if sum(op in p.ops for p in self.ports) != 1
        )

        kept: list[Port] = list(specialized[:width])
        i = 0
        while len(kept) < width:
            if i < len(generic):
                kept.append(generic[i])
                i += 1
            else:
                kept.append(Port(0, "", generic_ops))

        # Safety check: ensure every op class retains at least one capable port.
        #
        #
        #
        #
        homeless = [op for op in self.ops if not any(op in p.ops for p in kept)]
        if homeless:
            kept[-1] = Port(kept[-1].index, kept[-1].label,
                            kept[-1].ops | frozenset(homeless))

        ports = tuple(
            Port(idx, f",{idx}", p.ops) for idx, p in enumerate(kept)
        )
        return replace(self, ports=ports, name=f"{self.name}/w{width}")


# --------------------------------------------------------------------------
# Operation classes (latencies and port occupancy)
# --------------------------------------------------------------------------

_OPS: dict[str, OpClass] = {
    # Placeholder class for unknown mnemonics (latency 1, any channel).
    #
    #
    #
    #
    #
    #
    #
    #
    #
    #
    "UNKNOWN": OpClass("UNKNOWN", latency=1, latency_source=ASSUMED),

    # --- Op classes probed 2026-08-30 on real lcc -O3 code -------------------
    #
    #
    #
    #
    #
    #
    #
    # Existing 8 core classes remain bit-identical for training/eval parity.
    #
    #

    # FP add and multiply: latency 4, occupancy 1 (pipelined).
    #
    #
    #
    "FADD": OpClass("FADD", latency=4, occupancy=1,
                    latency_source=CHAIN, occupancy_source=BURST),
    "FMUL": OpClass("FMUL", latency=4, occupancy=1,
                    latency_source=CHAIN, occupancy_source=BURST),

    # FMA (fmul_addd etc.): latency 8, occupancy 1, all 6 channels.
    #
    #
    #
    #
    #
    #
    #
    #
    #
    #
    #
    #
    #
    "FMA": OpClass("FMA", latency=8, occupancy=1,
                   latency_source=CHAIN, occupancy_source=ASM),

    # FP division: fdivs=11, fdivd=14 (using worst-case 14), occupancy 2.
    #
    #
    #
    #
    #
    "FDIV": OpClass("FDIV", latency=14, occupancy=2,
                    latency_source=CHAIN, occupancy_source=BURST),

    # Predicate comparisons (if-conversion): latency 1 assumed.
    #
    #
    "PRED": OpClass("PRED", latency=1, latency_source=ASSUMED),

    # Packed SIMD arithmetic: 2 channels (,0 ,3); latency assumed.
    #
    #
    "PACK": OpClass("PACK", latency=1, latency_source=ASSUMED),

    # Packed SIMD logic/shifts: 4 channels (,0 ,1 ,3 ,4).
    #
    #
    #
    "PACKLOG": OpClass("PACKLOG", latency=1, latency_source=ASSUMED),

    # Array Access Unit (AAU): `aaurw`/`aaurr`/`staa*` on channels ,2 ,5.
    #
    #
    #
    "AAU": OpClass("AAU", latency=1, latency_source=ASSUMED),

    # APB reads (`movaX`): separate syllable (free_slot=True); latency assumed.
    #
    #
    #
    #
    "MOVA": OpClass("MOVA", latency=1, latency_source=ASSUMED, free_slot=True),
    "MOVAQ": OpClass("MOVAQ", latency=1, latency_source=ASSUMED, free_slot=True),
    "INCR": OpClass("INCR", latency=1, latency_source=ASSUMED, free_slot=True),

    # Format conversions (istofd, fdtoistr, fdtofs): channels ,0 ,1 ,3 ,4, lat 4.
    #
    #
    #
    #
    #
    #
    #
    #
    #
    #
    #
    "CONV": OpClass("CONV", latency=4, occupancy=1,
                    latency_source=CHAIN, occupancy_source=ASSUMED),

    # Combined shift+add (`shl_adds`, `getf_adds`): channels ,1 ,4 only.
    #
    "COMBO": OpClass("COMBO", latency=1, latency_source=ASSUMED),

    # Bitfield ops: `insf*` (4 channels), `getf*`/`merge*` (all 6).
    #
    #
    "INSF": OpClass("INSF", latency=1, latency_source=ASSUMED),
    "MERGE": OpClass("MERGE", latency=1, latency_source=ASSUMED),

    # State register writes (`rwd`/`rws`, e.g. %lsr): exclusive channel ,0.
    #
    "RW": OpClass("RW", latency=1, latency_source=ASSUMED),
    "ADD": OpClass("ADD", latency=1, latency_source=CHAIN, occupancy_source=BURST),
    "SUB": OpClass("SUB", latency=1, latency_source=CHAIN, occupancy_source=BURST),
    "AND": OpClass("AND", latency=1, latency_source=ASSUMED),
    "SHL": OpClass("SHL", latency=1, latency_source=ASSUMED),
    # Multiply: latency 4, occupancy 1 (pipelined across 4 channels).
    #
    #
    #
    #
    #
    "MUL": OpClass(
        "MUL", latency=4, occupancy=1,
        latency_source=CHAIN, occupancy_source=BURST,
    ),
    # Division: latency 11, occupancy 2, exclusive port ,5.
    #
    #
    #
    "DIV": OpClass(
        "DIV", latency=11, occupancy=2,
        latency_source=CHAIN, occupancy_source=BURST,
    ),
    # Load: latency 5 (pointer-chase probe), occupancy 1.
    #
    #
    "LOAD": OpClass("LOAD", latency=5, latency_source=CHAIN, occupancy_source=BURST),
    # Store: occupancy 1 (burst + assembler pair probe), latency 2 (store->load same-addr probe).
    #
    #
    #
    #
    #
    #
    #
    #
    #
    #
    #
    #
    #
    #
    #
    #
    #
    #
    #
    #
    #
    #
    #
    #
    #
    #
    #
    #
    #
    "STORE": OpClass("STORE", latency=2, occupancy=1,
                     latency_source=CHAIN, occupancy_source=BURST),
}

# --------------------------------------------------------------------------
# Port capability matrix verified via assembler.
#
#     op                    channels        assembler error on others
#     adds/subs/ands/shls   0 1 2 3 4 5     —
#     muls / muld           0 1   3 4       "cannot be encoded in ALC2/ALC5"
#     sdivs                         5       "cannot be encoded in ALC0..ALC4"
#     ldw / ldd             0   2 3   5     "cannot be encoded in ALC1/ALC4"
#     stw / std               2       5     "cannot be encoded in ALC0/1/3/4"
# --------------------------------------------------------------------------

_ALU_PORTS = (0, 1, 2, 3, 4, 5)     # basic ALU/logic — all 6 ports
MUL_PORTS = (0, 1, 3, 4)            # multiplier is NOT exclusive: 4 channels
DIV_PORTS = (5,)                    # divider is truly exclusive (,5)
LOAD_PORTS = (0, 2, 3, 5)
STORE_PORTS = (2, 5)

# Additional op-class channels verified with assembler.
#
#
FADD_PORTS = (0, 1, 2, 3, 4, 5)     # FP add/mul — all 6 channels
FDIV_PORTS = (5,)                   # FP divider — same exclusive port ,5 as INT DIV
                                    #
PRED_PORTS = (0, 1, 3, 4)           # predicates: not on ,2 or ,5
PACK_PORTS = (0, 3)                 # packed arithmetic: 2 channels
PACKLOG_PORTS = (0, 1, 3, 4)        # packed logic/shifts: 4 channels
AAU_PORTS = (2, 5)                  # AAU: same channels as STORE
COMBO_PORTS = (1, 4)                # combined shl_adds / getf_adds
INSF_PORTS = (0, 1, 3, 4)           # bitfield insert
MERGE_PORTS = (0, 1, 2, 3, 4, 5)    # predicate merge / bitfield extract
RW_PORTS = (0,)                     # state register write

_PORTS_FOR_OP: dict[str, tuple[int, ...]] = {
    "UNKNOWN": _ALU_PORTS,          # placeholder: any channel
    "FADD": FADD_PORTS,
    "FMUL": FADD_PORTS,
    "FMA": FADD_PORTS,          # FMA — all 6 channels
    "FDIV": FDIV_PORTS,
    "PRED": PRED_PORTS,
    "PACK": PACK_PORTS,
    "PACKLOG": PACKLOG_PORTS,
    "AAU": AAU_PORTS,
    "MOVA": (0, 1, 2, 3),       # movab/h/w/d/qp — verified with assembler
    "MOVAQ": (0, 2),            # quad narrower: assembler rejects ,1 and ,3
    "INCR": (0, 1, 2, 3, 4, 5), # does not occupy ALC slot (free_slot)
    "CONV": (0, 1, 3, 4),       # format conversions — verified with assembler
    "COMBO": COMBO_PORTS,
    "INSF": INSF_PORTS,
    "MERGE": MERGE_PORTS,
    "RW": RW_PORTS,
    "ADD": _ALU_PORTS,
    "SUB": _ALU_PORTS,
    "AND": _ALU_PORTS,
    "SHL": _ALU_PORTS,
    "MUL": MUL_PORTS,
    "DIV": DIV_PORTS,
    "LOAD": LOAD_PORTS,
    "STORE": STORE_PORTS,
}

# Kept for legacy references: the exclusive divider port.
DIV_PORT = DIV_PORTS[0]


# --------------------------------------------------------------------------
# Machine profiles
# --------------------------------------------------------------------------


def _measured_ports() -> tuple[Port, ...]:
    """Assembler-verified capability matrix for e2k-v6 (6 ports, exclusive divider on `,5`)."""
    ports = []
    for idx in range(6):
        ops = {op for op, chans in _PORTS_FOR_OP.items() if idx in chans}
        ports.append(Port(idx, f",{idx}", frozenset(ops)))
    return tuple(ports)


E2K_V6_MEASURED = MachineModel(
    name="e2k-v6-measured",
    description=(
        "Assembler-verified lcc capability matrix: 6 ports (`,0`..`,5`). "
        "Basic ALU/logic on all 6; MUL on 4 (`,0 ,1 ,3 ,4`); LOAD on 4 "
        "(`,0 ,2 ,3 ,5`); STORE on 2 (`,2 ,5`); DIV and FDIV on exclusive "
        "port `,5`; state writes (`rwd`) on exclusive port `,0`; AAU shares "
        "`,2 ,5` with STORE."
        ""
        ""
        ""
        ""
        ""
    ),
    ops=_OPS,
    ports=_measured_ports(),
    matrix_source=ASM,
)


# Naive uniform profile (6 symmetric ports), kept as a contrast baseline.
#
#
#
def _homogeneous_ports() -> tuple[Port, ...]:
    allops = frozenset(_OPS)
    return tuple(Port(idx, f",{idx}", allops) for idx in range(6))


NAIVE_HOMOGENEOUS = MachineModel(
    name="naive_homogeneous",
    description=(
        "LEGACY contrast profile: 6 fully symmetric channels (every op on "
        "every port). Refuted by assembler probing, kept as a degenerate baseline."
        ""
        ""
        ""
    ),
    ops=_OPS,
    ports=_homogeneous_ports(),
    matrix_source=ASSUMED,
)


# --------------------------------------------------------------------------
# REFUTED v1 profile (kept intentionally to show how model errors skew results).
#
#
# --------------------------------------------------------------------------

_FIRSTPROBE_OPS: dict[str, OpClass] = dict(_OPS) | {
    "MUL": OpClass("MUL", latency=8, occupancy=8,
                   latency_source=ASSUMED, occupancy_source=ASSUMED),
    "DIV": OpClass("DIV", latency=13, occupancy=13,
                   latency_source=ASSUMED, occupancy_source=ASSUMED),
    "LOAD": OpClass("LOAD", latency=2, latency_source=ASSUMED,
                    occupancy_source=ASSUMED),
}


def _firstprobe_ports() -> tuple[Port, ...]:
    universal = {"UNKNOWN", "ADD", "SUB", "AND", "SHL", "LOAD", "STORE",
                 "FADD", "FMUL", "FDIV", "PRED", "PACK", "PACKLOG", "AAU",
                 "COMBO", "INSF", "MERGE", "RW"}
    ports = []
    for idx in range(6):
        ops = set(universal)
        if idx == 0:
            ops.add("MUL")      # assumed exclusive multiplier
        if idx == 5:
            ops.add("DIV")
        ports.append(Port(idx, f",{idx}", frozenset(ops)))
    return tuple(ports)


E2K_V6_FIRSTPROBE = MachineModel(
    name="e2k-v6-firstprobe",
    description=(
        "REFUTED v1 model (kept for comparison): misread probe.c as a single "
        "8-cycle multiplier on `,0`, overestimated DIV (13 vs 11), and "
        "underestimated LOAD (2 vs 5)."
        ""
        ""
        ""
        ""
        ""
    ),
    ops=_FIRSTPROBE_OPS,
    ports=_firstprobe_ports(),
    matrix_source=ASSUMED,
)


PROFILES: dict[str, MachineModel] = {
    E2K_V6_MEASURED.name: E2K_V6_MEASURED,
    E2K_V6_FIRSTPROBE.name: E2K_V6_FIRSTPROBE,
    NAIVE_HOMOGENEOUS.name: NAIVE_HOMOGENEOUS,
}

DEFAULT_PROFILE = E2K_V6_MEASURED.name


def get_profile(name: str) -> MachineModel:
    try:
        return PROFILES[name]
    except KeyError:
        raise SystemExit(
            f"unknown profile {name!r}; available: {', '.join(PROFILES)}"
        ) from None


def describe_model(model: MachineModel) -> list[tuple[str, str, str]]:
    """Model parameter table: (parameter, value, source)."""
    rows: list[tuple[str, str, str]] = [
        ("ports per wide instruction", str(model.width), model.matrix_source),
    ]
    for name in sorted(model.ops, key=lambda n: (model.ops[n].latency, n)):
        op = model.ops[name]
        val = f"{op.latency} cyc"
        if op.blocks_channel():
            val += f", occupancy {op.occupancy}"
        rows.append((f"latency {name}", val, op.latency_source))
    return rows


def capability_matrix(model: MachineModel) -> tuple[list[str], list[list[bool]]]:
    """Return `(op_order, port_rows)` capability matrix sorted narrowest-first."""
    op_names = sorted(model.ops,
                      key=lambda n: (len(model.channels_for(n)),
                                     -model.ops[n].latency, n))
    grid = [[op in p.ops for op in op_names] for p in model.ports]
    return op_names, grid
