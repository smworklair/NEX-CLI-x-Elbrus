"""e2k instruction-set timing reference: what was MEASURED vs assumed.

Generated directly from `model.py` and `asm_parser.py` (like Agner Fog / uops.info
tables for Elbrus) so documentation never drifts from the scheduler model.
Every row states its measurement provenance explicitly; unmeasured latencies
are listed separately as open gaps.
"""

from __future__ import annotations

from dataclasses import dataclass

from .model import ASSUMED, DEFAULT_PROFILE, MachineModel, get_profile

# Forbidden op-pair combinations in a single wide instruction, found by
# exhaustive assembler probing (2 of 119 pairs rejected). Recorded here as
# measured hardware facts rather than active scheduler constraints.
#
#
#
#
# Official MCST latency table ("Elbrus Efficient Programming Guide",
# rev 1.2, 2024-02-28, CC BY 4.0, Section 6.1, mcst.ru/elbrus_prog).
#
#
# NOTE: MCST table covers E4C/E8C whereas this toolchain targets e2k-v6,
# so these numbers are cross-checks only, not substituted into the model.
#
#
#
DOC_LATENCY: dict[str, tuple[str, str]] = {
    "ADD":   ("1", "Int, Bitwise"),
    "SUB":   ("1", "Int, Bitwise"),
    "AND":   ("1", "Int, Bitwise"),
    "SHL":   ("1", "Int, Bitwise"),
    "MUL":   ("4", "Fp (integer multiply grouped under Fp)"),
    "FADD":  ("4", "Fp"),
    "FMUL":  ("4", "Fp"),
    "FMA":   ("8", "Fp_combined"),
    "DIV":   ("11", "Fdivs — 32-bit"),
    "FDIV":  ("14", "Fdivd — 64-bit"),
    "LOAD":  ("3", "Ld L1 hit (L2: 11, L3: 40, RAM: ~100)"),
    "COMBO": ("2", "Int_combined"),
    "PRED":  ("0.5…3", "logic->logic 0.5, Cmp->logic 1, ->qual 2, ->ct 3"),
}
"""Op class -> (documented latency, MCST table label).

Pairwise effects (fp<->int domain crossing and cross-cluster bypass delays)
are not representable as a single per-op `OpClass.latency` scalar.
"""

COMBINATION_BANS = (
    ("STORE", 2, "LOAD", 3,
     "Error: the combination of STORE in ALC2 with LOAD in ALC3 is prohibited"),
    ("STORE", 5, "LOAD", 0,
     "Error: the combination of STORE in ALC5 with LOAD in ALC0 is prohibited"),
)

CLUSTERS = ((0, 1, 2), (3, 4, 5))
"""Channel clusters observed via pair-ban seams at (2,3) and (5,0).
Cross-cluster latency cannot be probed with the local toolchain alone."""


@dataclass(frozen=True)
class IsaClass:
    """Single operation class with its measured parameters and provenance."""

    name: str
    latency: int
    latency_source: str
    occupancy: int
    occupancy_source: str
    channels: tuple[int, ...]
    mnemonics: tuple[str, ...]

    @property
    def peak_per_cycle(self) -> float:
        """Peak issue throughput (ops/cycle = capable_channels / occupancy)."""
        return len(self.channels) / self.occupancy

    @property
    def latency_measured(self) -> bool:
        return self.latency_source != ASSUMED

    @property
    def occupancy_measured(self) -> bool:
        return self.occupancy_source != ASSUMED

    @property
    def monopoly(self) -> bool:
        """True if the class has only a single capable channel (exclusive port)."""
        return len(self.channels) == 1


def collect(model: MachineModel | None = None) -> list[IsaClass]:
    """Build full ISA table ordered from narrowest (most constrained) to widest."""
    from . import model as _m
    from .asm_parser import MNEMONICS

    model = model or get_profile(DEFAULT_PROFILE)

    by_class: dict[str, list[str]] = {}
    for mnemonic, cls in MNEMONICS.items():
        by_class.setdefault(cls, []).append(mnemonic)

    rows: list[IsaClass] = []
    for name, oc in _m._OPS.items():
        if name == "UNKNOWN":
            # Sentinel parser class, not a real hardware class — omit from ISA table.
            #
            continue
        rows.append(IsaClass(
            name=name,
            latency=oc.latency,
            latency_source=oc.latency_source,
            occupancy=oc.occupancy,
            occupancy_source=oc.occupancy_source,
            channels=tuple(_m._PORTS_FOR_OP[name]),
            mnemonics=tuple(sorted(by_class.get(name, ()))),
        ))
    rows.sort(key=lambda r: (len(r.channels), -r.latency, r.name))
    return rows


def gaps(rows: list[IsaClass]) -> list[IsaClass]:
    """Op classes whose latency is still an assumption rather than measured."""
    return [r for r in rows if not r.latency_measured]
