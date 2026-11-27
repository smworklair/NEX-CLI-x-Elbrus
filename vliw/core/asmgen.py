"""e2k assembly generator: synthesize valid test scenarios in one command.

Pulls channels, latencies, and occupancies directly from `vliw/core/model.py`,
so it can never emit illegal channel assignments like `muls,2`. Registers are
assigned round-robin to produce assembleable code with the requested dependency
structure (for schedule analysis, not meaningful execution).
"""

from __future__ import annotations

from .model import MachineModel

#: Assembly text template per operation class (mnemonic and operand form),
#: taken from `tools/probe_matrix.py` where they were verified against
#: the real assembler.
FORMS: dict[str, tuple[str, str]] = {
    "ADD":   ("adds",  "%r{a}, %r{b}, %r{d}"),
    "SUB":   ("subs",  "%r{a}, %r{b}, %r{d}"),
    "AND":   ("ands",  "%r{a}, %r{b}, %r{d}"),
    "SHL":   ("shls",  "%r{a}, %r{b}, %r{d}"),
    "MUL":   ("muls",  "%r{a}, %r{b}, %r{d}"),
    "DIV":   ("sdivs", "%r{a}, %r{b}, %r{d}"),
    "FADD":  ("faddd", "%dr{a}, %dr{b}, %dr{d}"),
    "FMUL":  ("fmuld", "%dr{a}, %dr{b}, %dr{d}"),
    "FDIV":  ("fdivd", "%dr{a}, %dr{b}, %dr{d}"),
    "FMA":   ("fmul_addd", "%dr{a}, %dr{b}, %dr{c}, %dr{d}"),
    "LOAD":  ("ldw",   "0x0, [ _f64,_lts0 mem ], %r{d}"),
    "STORE": ("stw",   "%dr2, 0x0, %r{a}"),
}

#: Human-friendly aliases for CLI input and error messages.
ALIASES = {
    "muls": "MUL", "mul": "MUL", "multiply": "MUL",
    "adds": "ADD", "add": "ADD", "add": "ADD",
    "subs": "SUB", "sub": "SUB",
    "ands": "AND", "and": "AND",
    "shls": "SHL", "shl": "SHL",
    "sdivs": "DIV", "div": "DIV", "divide": "DIV",
    "faddd": "FADD", "fadd": "FADD",
    "fmuld": "FMUL", "fmul": "FMUL",
    "fdivd": "FDIV", "fdiv": "FDIV",
    "fmul_addd": "FMA", "fma": "FMA",
    "ldw": "LOAD", "load": "LOAD", "load": "LOAD",
    "stw": "STORE", "store": "STORE", "store": "STORE",
}


def resolve(name: str) -> str | None:
    """Map user-supplied op name to model op class, or None if unknown."""
    key = name.strip().lower()
    if key.upper() in FORMS:
        return key.upper()
    return ALIASES.get(key)


def known_names() -> list[str]:
    """Accepted op names for help text and error messages."""
    return sorted(FORMS)


#: Register window: assembler accepts %r0..%r63. Destinations use the upper
#: half and sources the lower half so the first 32 ops have distinct
#: destinations and stay truly independent; beyond 32, a warning is emitted.
#:
#:
#:
MAX_REG = 63
DST_BASE, DST_COUNT = 32, 32
SRC_BASE, SRC_COUNT = 1, 15


def _regs(k: int) -> tuple[int, int, int, int]:
    """Register indices for the k-th operation: sources and destination."""
    a = SRC_BASE + (k % SRC_COUNT)
    b = SRC_BASE + SRC_COUNT + (k % SRC_COUNT)
    c = SRC_BASE + ((k + 7) % SRC_COUNT)
    d = DST_BASE + (k % DST_COUNT)
    return a, b, c, d


def _op_text(op: str, channel: int, k: int) -> str:
    mnemonic, form = FORMS[op]
    a, b, c, d = _regs(k)
    return f"{mnemonic},{channel}\t" + form.format(a=a, b=b, c=c, d=d)


def independent(model: MachineModel, op: str, count: int,
                *, packed: bool = False) -> str:
    """Generate `count` independent operations of class `op`.

    `packed=False` issues one per wide instruction; `packed=True` packs across
    all capable channels to illustrate the hardware lower bound.
    """
    ports = model.channels_for(op)
    if not ports:
        raise ValueError(f"{op} has no capable channel in profile {model.name}")

    lines = [
        f"! {count} independent {FORMS[op][0]} operations — "
        + ("packed across all channels" if packed else "one per cycle"),
        f"! channels for {op}: "
        + " ".join(f",{p}" for p in ports)
        + f"  ·  latency {model.latency(op)} cyc"
        + (f"  ·  port occupancy {model.occupancy(op)} cyc"
           if model.occupancy(op) > 1 else ""),
        "!",
    ]
    if count > DST_COUNT:
        lines.append(f"! WARNING: only {DST_COUNT} destination registers in window, requested "
                     f"{count} — starting at op {DST_COUNT + 1}, destinations wrap and overwrite")
        lines.append("! used registers, introducing write dependencies.")
        lines.append("!")
    lines.append("! F5 — run, F6 — rewrite from oracle.")

    if packed:
        # One operation per available channel until exhausted.
        per_bundle = len(ports)
        for start in range(0, count, per_bundle):
            lines.append("{")
            for k in range(start, min(start + per_bundle, count)):
                lines.append("  " + _op_text(op, ports[(k - start) % per_bundle], k))
            lines.append("}")
    else:
        home = ports[0]
        for k in range(count):
            lines.append("{")
            lines.append("  " + _op_text(op, home, k))
            lines.append("}")
    return "\n".join(lines) + "\n"


def chain(model: MachineModel, op: str, count: int) -> str:
    """Generate a chain of `count` dependent operations (each waits on the previous).

    Demonstrates latency lower bound: N * latency cycles regardless of width.
    """
    ports = model.channels_for(op)
    if not ports:
        raise ValueError(f"{op} has no capable channel in profile {model.name}")
    lat = model.latency(op)
    lines = [
        f"! chain of {count} dependent {FORMS[op][0]}: each waits on the previous",
        f"! latency {lat} cyc -> cannot finish in under {count * lat} cyc,",
        "! regardless of free channels. Zero headroom here, and that is",
        "! the correct scheduler answer.",
        "!",
        "! F5 — run.",
    ]
    for k in range(count):
        lines.append("{")
        # Previous destination feeds next source, forming the dependency chain.
        prev = DST_BASE + ((k - 1) % DST_COUNT) if k else SRC_BASE
        cur = DST_BASE + (k % DST_COUNT)
        mnemonic, form = FORMS[op]
        lines.append(f"  {mnemonic},{ports[0]}\t"
                     + form.format(a=prev, b=SRC_BASE + 1, c=prev, d=cur))
        lines.append("}")
    return "\n".join(lines) + "\n"


def filler(model: MachineModel, cycles: int) -> str:
    """Generate `cycles` filler wide instructions (one independent ADD per cycle)."""
    ports = model.channels_for("ADD")
    lines = [
        f"! filler: {cycles} cycles of independent additions",
        "! dummy work to occupy cycles.",
    ]
    for k in range(cycles):
        lines.append("{")
        lines.append("  " + _op_text("ADD", ports[k % len(ports)], k))
        lines.append("}")
    return "\n".join(lines) + "\n"
