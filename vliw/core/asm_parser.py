"""Parser for real lcc `.s` assembly output targeting Elbrus (e2k).

Parses `{ ... }` wide instructions, explicit channel suffixes (`adds,0`),
and `nop N` stall counts, building a register-level RAW dependency DAG and
reconstructing the compiler schedule for exact comparison and linting.
"""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass, field

from .dag import DAG, Instr
from .model import MachineModel
from .schedule import Schedule

# e2k mnemonic -> machine-model operation class.
# Unknown channel-tagged mnemonics map to UNKNOWN.
#
MNEMONICS: dict[str, str] = {
    "adds": "ADD", "addd": "ADD", "addw": "ADD", "incs": "ADD", "incd": "ADD",
    "subs": "SUB", "subd": "SUB", "subw": "SUB", "decs": "SUB",
    "muls": "MUL", "muld": "MUL", "mulw": "MUL", "umuls": "MUL", "umuld": "MUL",
    "sdivs": "DIV", "sdivd": "DIV", "udivs": "DIV", "udivd": "DIV",
    "divs": "DIV", "divd": "DIV",
    "ldw": "LOAD", "ldd": "LOAD", "ldb": "LOAD", "ldh": "LOAD",
    "ldgdw": "LOAD", "ldgdd": "LOAD",
    "stw": "STORE", "std": "STORE", "stb": "STORE", "sth": "STORE",
    "shls": "SHL", "shld": "SHL", "shrs": "SHL", "shrd": "SHL",
    "sars": "SHL", "sard": "SHL", "scls": "SHL", "scrs": "SHL",
    "ands": "AND", "andd": "AND", "ors": "AND", "ord": "AND",
    "xors": "AND", "xord": "AND", "andns": "AND",
    # `sxt` — sign extension seen in real lcc output.
    #
    #
    #
    "movts": "ADD", "movtd": "ADD", "sxt": "ADD",

    # --- Floating-point, predicates, packed ops (2026-08-30) ----------------
    # Channels and latencies probed against the real assembler/compiler.
    #
    #
    "fadds": "FADD", "faddd": "FADD", "fsubs": "FADD", "fsubd": "FADD",
    "fmuls": "FMUL", "fmuld": "FMUL",
    # Fused multiply-add (added 2026-09-02 from lcc -O3 kernels).
    #
    #
    "fmul_addd": "FMA", "fmul_adds": "FMA",
    "fmul_subd": "FMA", "fmul_subs": "FMA",
    "fmul_rsubd": "FMA", "fmul_rsubs": "FMA",
    # Array prefetch buffer (APB) reads: `,0,1,2,3`, except `movaq` on `,0,2`.
    #
    #
    #
    "movab": "MOVA", "movah": "MOVA", "movaw": "MOVA",
    "movad": "MOVA", "movaqp": "MOVA",
    "movaq": "MOVAQ",
    # `incr` advances AAU index; does not occupy an ALC slot (co-issues with `staad,2`).
    #
    #
    #
    #
    "incr": "INCR",
    # Format conversions; channels ,0 ,1 ,3 ,4 verified with assembler.
    "istofd": "CONV", "istofs": "CONV", "idtofd": "CONV", "idtofs": "CONV",
    "fdtoistr": "CONV", "fstoistr": "CONV", "fdtois": "CONV", "fstois": "CONV",
    "fdtoid": "CONV", "fstoid": "CONV", "fdtofs": "CONV", "fstofd": "CONV",
    "fdivs": "FDIV", "fdivd": "FDIV",

    # Comparisons writing predicate registers (shared channel/latency class).
    #
    #
    "cmpesb": "PRED", "cmpedb": "PRED", "cmplsb": "PRED", "cmpldb": "PRED",
    "cmplesb": "PRED", "cmpledb": "PRED", "cmpbsb": "PRED", "cmpbdb": "PRED",
    "cmpandesb": "PRED", "cmpandedb": "PRED",
    "cmpandsb": "PRED", "cmpanddb": "PRED",

    # Packed ops: `p*` (64-bit) and `qp*` (128-bit) share the same channels.
    #
    "paddw": "PACK", "paddb": "PACK", "paddh": "PACK", "paddd": "PACK",
    "psubw": "PACK", "psubb": "PACK", "psubh": "PACK", "psubd": "PACK",
    "pcmpgtw": "PACK", "pcmpeqw": "PACK", "pminsw": "PACK", "pmaxsw": "PACK",
    "qpaddw": "PACK", "qpaddb": "PACK", "qpaddh": "PACK", "qpaddd": "PACK",
    "qpsubw": "PACK", "qpsllw": "PACK", "qpsrlw": "PACK",
    "qpminsw": "PACK", "qpmaxsw": "PACK", "qpcmpgtw": "PACK",
    "qppackdl": "PACK", "qpswitchd": "PACK",

    # Packed logic and shifts: wider channel mask (,0 ,1 ,3 ,4 vs ,0 ,3).
    #
    "qpor": "PACKLOG", "qpand": "PACKLOG", "qpxor": "PACKLOG",
    "qpsllw": "PACKLOG", "qpsrlw": "PACKLOG", "qpsraw": "PACKLOG",
    "por": "PACKLOG", "pand": "PACKLOG", "pxor": "PACKLOG",
    "psllw": "PACKLOG", "psrlw": "PACKLOG",

    # Packed FP shares channels and timing with scalar FP.
    #
    "pfadds": "FADD", "pfaddd": "FADD", "pfsubs": "FADD",
    "pfmuls": "FMUL", "pfmuld": "FMUL",

    # Array Access Unit (AAU): register moves and stores on channels ,2 ,5.
    #
    "aaurw": "AAU", "aaurwd": "AAU", "aaurr": "AAU", "aaurrd": "AAU",
    "staaw": "AAU", "staad": "AAU", "staah": "AAU", "staab": "AAU",
    "staaq": "AAU", "mmurw": "AAU", "mmurr": "AAU",

    # Combined shift-and-add ops: channels ,1 and ,4 only.
    "shl_adds": "COMBO", "shl_addd": "COMBO",
    "shr_adds": "COMBO", "shr_addd": "COMBO",
    "getf_adds": "COMBO", "getf_addd": "COMBO",

    # Bitfield ops: insert is narrower; extract/merge are wider.
    "insfs": "INSF", "insfd": "INSF",
    "getfs": "MERGE", "getfd": "MERGE",
    "merges": "MERGE", "merged": "MERGE",

    # Wide load/store share the standard memory ports.
    "ldqp": "LOAD", "ldapq": "LOAD", "stqp": "STORE", "stapq": "STORE",

    # Writes to state registers (loop counter %lsr, etc.) — channel ,0.
    "rwd": "RW", "rws": "RW",
}

# `adds,0 %r1, %r2, %r3` — mnemonic, optional channel, operands.
CONTROL = {
    "nop", "return", "ct", "ibranch", "call", "disp", "rbranch",
    "setwd", "setbn", "setsft", "settr", "setmas", "setei",
    "getsp", "getpl", "bap", "eap", "flushr", "flushc", "wait",
    "ipd", "abn", "abp", "abg", "alc", "loop_mode", "pref", "landing",
    # Control/setup ops (`ldisp`, `fapb`, etc.) excluded from compute DAG.
    #
    #
    #
    #
    "ldisp", "fapb",
}
"""Control/setup mnemonics excluded from the compute DAG and counted in `ParsedAsm.control_ops`."""

_OP = re.compile(
    r"^\s*(?P<mn>[a-z][a-z0-9_]*)"      # mnemonic
    r"(?:,(?P<chan>\d+))?"              # channel: ,0 .. ,5
    r"(?P<flags>(?:,[a-z][a-z0-9]*)*)"  # post-channel modifiers: ,sm etc.
    r"(?:\s+(?P<args>.*?))?\s*$"
)
"""Instruction regex inside a wide instruction (captures post-channel modifiers like `,sm`)."""
_NOP = re.compile(r"^\s*nop\s+(?P<n>\d+)\s*$", re.I)
# NOTE: no trailing \b — rotating registers like `%db[16],` end with `]`
# followed by `,` (both non-word chars), so \b would miss them.
#
#
#
#
#
#
_REG = re.compile(r"%?\b([a-z]+\d+|[a-z]+\[\d+\])")
_COMMENT = re.compile(r"(//|!|;).*$")


@dataclass
class AsmOp:
    """Single parsed operation from `.s`."""

    index: int
    mnemonic: str
    op: str                 # machine-model op class: ADD/MUL/DIV/LOAD/...
    channel: int | None     # explicit channel from `,N`, if present
    dst: str | None
    srcs: tuple[str, ...]
    bundle: int             # index of enclosing wide instruction
    cycle: int              # issue cycle in compiler schedule
    text: str
    known: bool = True
    flags: tuple[str, ...] = ()
    """Post-channel modifiers, e.g. `("sm",)` for speculative execution."""
    line: int = 0
    """1-based source line number for editor gutter annotations and navigation."""


@dataclass
class AsmProblem:
    """Line-anchored parser or linter diagnostic."""

    line: int
    kind: str              # parse | mnemonic | channel | busy | free
    severity: str          # error | warn | info
    text: str
    hint: str = ""
    op: int = -1           # operation index, if diagnostic refers to an op


@dataclass
class ParsedAsm:
    """Parsed assembly result."""

    ops: list[AsmOp] = field(default_factory=list)
    bundles: int = 0
    nop_cycles: int = 0
    skipped_lines: int = 0
    control_ops: int = 0
    """Count of skipped control/setup operations (see CONTROL)."""
    unknown_mnemonics: dict[str, int] = field(default_factory=dict)
    source: str = ""
    problems: list[AsmProblem] = field(default_factory=list)
    """Line-anchored parse warnings and errors."""

    @property
    def compiler_cycles(self) -> int:
        """Total cycle span of the compiler's own schedule."""
        if not self.ops:
            return 0
        return max(o.cycle for o in self.ops) + 1

    def op_counts(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for o in self.ops:
            out[o.op] = out.get(o.op, 0) + 1
        return out


def parse_asm(text: str, source: str = "") -> ParsedAsm:
    """Parse `.s` assembly text into operations and compiler issue cycles."""
    res = ParsedAsm(source=source)
    bundle = -1
    cycle = 0
    in_bundle = False
    saw_bundle = False
    pending_nop = 0

    for lineno, raw in enumerate(text.splitlines(), 1):
        line = _COMMENT.sub("", raw).strip()
        if not line:
            continue

        if line.startswith("{"):
            in_bundle = True
            saw_bundle = True
            bundle += 1
            cycle += pending_nop
            pending_nop = 0
            line = line[1:].strip()
            if not line:
                continue
        if line.startswith("}"):
            in_bundle = False
            cycle += 1
            continue

        # Skip directives and labels.
        if line.startswith(".") or line.endswith(":"):
            continue

        m_nop = _NOP.match(line)
        if m_nop:
            # `nop N` — explicit stall cycles before the next wide instruction.
            pending_nop += int(m_nop.group("n"))
            res.nop_cycles += int(m_nop.group("n"))
            continue

        m = _OP.match(line)
        if not m:
            res.skipped_lines += 1
            res.problems.append(AsmProblem(
                line=lineno, kind="parse", severity="warn",
                text="could not parse line — omitted from DAG",
                hint="expected an operation like `adds,0 %r1, %r2, %r3`"))
            continue

        mn = m.group("mn").lower()
        if mn in CONTROL:
            res.control_ops += 1
            continue

        chan = m.group("chan")

        op_class = MNEMONICS.get(mn)
        known = op_class is not None
        if not known:
            # Unknown mnemonic WITHOUT channel is not an ALC op (e.g. predicate/control);
            # count under control_ops rather than inserting into compute DAG.
            #
            #
            #
            #
            #
            if chan is None:
                res.control_ops += 1
                res.unknown_mnemonics[mn] = res.unknown_mnemonics.get(mn, 0) + 1
                continue
            # Channel-tagged unknown op: keep in DAG as UNKNOWN (latency 1 placeholder).
            #
            #
            op_class = "UNKNOWN"
            res.unknown_mnemonics[mn] = res.unknown_mnemonics.get(mn, 0) + 1
            near = difflib.get_close_matches(mn, MNEMONICS, n=3, cutoff=0.72)
            res.problems.append(AsmProblem(
                line=lineno, kind="mnemonic", severity="warn", op=len(res.ops),
                text=f"unknown mnemonic `{mn}` — assigned class UNKNOWN "
                     f"(latency 1, any channel: placeholder, not measured)",
                hint=("did you mean: " + "  ".join(near)) if near else
                     "known mnemonics are listed in MNEMONICS (core/asm_parser.py)"))

        args = (m.group("args") or "").strip()
        regs = _REG.findall(args)
        dst = regs[-1] if regs else None
        srcs = tuple(regs[:-1]) if len(regs) > 1 else ()

        res.ops.append(AsmOp(
            index=len(res.ops), mnemonic=mn, op=op_class,
            channel=int(chan) if chan is not None else None,
            dst=dst, srcs=srcs,
            bundle=max(0, bundle), cycle=cycle,
            text=line, known=known, line=lineno,
            flags=tuple(f for f in (m.group("flags") or "").split(",") if f),
        ))

    res.bundles = bundle + 1
    if not saw_bundle and res.ops:
        # Brace-free file: treat each operation as its own cycle.
        #
        # Check `saw_bundle` rather than `not in_bundle` so a single-bundle file
        # does not get split across separate cycles.
        #
        #
        #
        #
        for i, o in enumerate(res.ops):
            o.cycle = i
            o.bundle = i
        res.bundles = len(res.ops)
    return res


def build_dag(parsed: ParsedAsm, key: str = "asm", title: str = "") -> DAG:
    """Build RAW register dependency DAG respecting wide-instruction semantics.

    All operations in the same cycle read operands from PREVIOUS cycles
    simultaneously before any writes in the current cycle take effect.
    """
    last_writer: dict[str, int] = {}
    instrs: list[Instr] = []

    def group_key(o: AsmOp) -> int:
        # Brace-free file: each op is its own cycle so sequential deps are preserved.
        #
        return o.cycle if o.cycle >= 0 else -(o.index + 1)

    i = 0
    ops = parsed.ops
    while i < len(ops):
        j = i
        while j < len(ops) and group_key(ops[j]) == group_key(ops[i]):
            j += 1

        # Process whole cycle: all reads see prior-cycle writers, then apply writes.
        #
        for o in ops[i:j]:
            preds = []
            for src in o.srcs:
                w = last_writer.get(src)
                if w is not None and w not in preds:
                    preds.append(w)
            instrs.append(Instr(
                id=o.index,
                name=(o.dst or f"i{o.index}"),
                op=o.op,
                preds=tuple(sorted(preds)),
                text=o.text,
            ))
        for o in ops[i:j]:
            if o.dst:
                last_writer[o.dst] = o.index
        i = j

    return DAG(
        key=key,
        title=title or f"Parsed .s: {parsed.source or 'unnamed'}",
        note=(f"{len(parsed.ops)} ops in {parsed.bundles} wide instructions. "
              f"DAG built from RAW register dependencies; "
              f"compiler schedule — {parsed.compiler_cycles} cycles."),
        instrs=instrs,
    )


def compiler_schedule(parsed: ParsedAsm, dag: DAG, model: MachineModel) -> Schedule | None:
    """Reconstruct the compiler's own schedule for direct comparison with exact search.

    Returns None if channel assignment conflicts with the machine model.
    """
    sched = Schedule(dag, model)
    used: dict[tuple[int, int], int] = {}
    for o in parsed.ops:
        ports = model.channels_for(o.op)
        if not ports:
            return None
        port = o.channel if o.channel in ports else None
        if port is None:
            port = next((p for p in ports if (o.cycle, p) not in used), None)
            if port is None:
                return None
        if (o.cycle, port) in used:
            return None
        occ = model.occupancy(o.op)
        for k in range(occ):
            used[(o.cycle + k, port)] = o.index
        sched.place(o.index, o.cycle, port)
    return sched


UNKNOWN_SHARE_LIMIT = 0.05
"""UNKNOWN op fraction above which compiler comparison becomes meaningless."""


def unknown_share(parsed: ParsedAsm) -> float:
    """Fraction of operations classified as UNKNOWN."""
    if not parsed.ops:
        return 0.0
    return sum(1 for o in parsed.ops if o.op == "UNKNOWN") / len(parsed.ops)


def compiler_schedule_checked(parsed: ParsedAsm, dag: DAG, model: MachineModel):
    """Return `(schedule|None, problem|None)` where `problem` is `(title, detail)`."""
    sched = compiler_schedule(parsed, dag, model)
    if sched is None:
        return None, ("compiler schedule could not be reconstructed",
                      "channel layout conflicts with machine model")
    errs = sched.validate()
    if errs:
        detail = (errs[0] if len(errs) == 1
                  else f"{len(errs)} issues, first: {errs[0]}")
        return None, (
            "compiler schedule failed validation",
            detail + ". Common cause on -O3 code is a software-pipelined "
                     "loop: values carry from the previous iteration while the parser "
                     "reads the block linearly")
    return sched, None


def lint(parsed: ParsedAsm, model: MachineModel) -> list[AsmProblem]:
    """Lint parsed assembly against the machine model (illegal channels, port conflicts, early reads)."""
    out: list[AsmProblem] = []
    if not parsed.ops:
        return out

    # 1. Channel vs port capability matrix.
    for o in parsed.ops:
        if o.channel is None:
            continue
        allowed = model.channels_for(o.op)
        if allowed and o.channel not in allowed:
            names = " ".join(model.port_label(p) for p in allowed)
            out.append(AsmProblem(
                line=o.line, kind="channel", severity="error", op=o.index,
                text=f"{o.mnemonic} on channel ,{o.channel} — unsupported channel for "
                     f"{o.op}",
                hint=f"{o.op} executes on: {names}"))

    # 2. Port occupancy conflicts (multi-cycle occupancy blocks subsequent cycles).
    #
    held: dict[tuple[int, int], AsmOp] = {}
    for o in parsed.ops:
        # Separate-syllable ops (movaX) do not occupy ALC slots (`OpClass.free_slot`).
        #
        #
        #
        #
        try:
            if model.op(o.op).free_slot:
                continue
        except KeyError:
            pass
        ports = model.channels_for(o.op)
        port = o.channel if (o.channel is not None and o.channel in ports) else None
        if port is None:
            port = next((p for p in ports if (o.cycle, p) not in held), None)
        if port is None:
            continue
        occ = model.occupancy(o.op)
        prev = held.get((o.cycle, port))
        if prev is not None:
            same = prev.cycle == o.cycle
            free_at = prev.cycle + model.occupancy(prev.op)
            out.append(AsmProblem(
                line=o.line, kind="busy", severity="error", op=o.index,
                text=(f"channel ,{port} in cycle {o.cycle} is already busy: "
                      + (f"{prev.mnemonic} on line {prev.line}" if same else
                         f"{prev.mnemonic} on line {prev.line} holds port for "
                         f"{model.occupancy(prev.op)} cyc")),
                hint=f"port frees in cycle {free_at}"))
        for k in range(occ):
            held.setdefault((o.cycle + k, port), o)

    # 3. Operand not ready: read before producer latency elapses.
    #
    # Whole-cycle semantics: all ops in a wide instruction read prior cycles first.
    #
    #
    #
    #
    #
    #
    last_writer: dict[str, AsmOp] = {}
    ops = parsed.ops
    i = 0
    while i < len(ops):
        j = i
        while j < len(ops) and ops[j].cycle == ops[i].cycle:
            j += 1
        for o in ops[i:j]:
            for src in o.srcs:
                w = last_writer.get(src)
                if w is None:
                    continue
                ready = w.cycle + model.latency(w.op)
                if o.cycle < ready:
                    out.append(AsmProblem(
                        line=o.line, kind="ready", severity="error", op=o.index,
                        text=f"%{src} read in cycle {o.cycle}, but "
                             f"{w.mnemonic} on line {w.line} produces it "
                             f"only in cycle {ready}",
                        hint=f"{w.op} latency is {model.latency(w.op)} cyc; "
                             f"requires a {ready - w.cycle}-cycle gap"))
        for o in ops[i:j]:
            if o.dst:
                last_writer[o.dst] = o
        i = j

    # 4. Missing explicit channels: warn that port layout is inferred.
    #
    #
    free = [o for o in parsed.ops if o.channel is None]
    if free:
        out.append(AsmProblem(
            line=free[0].line, kind="free", severity="info", op=free[0].index,
            text=f"{len(free)} of {len(parsed.ops)} ops lack explicit channel — "
                 f"port layout is inferred",
            hint="lcc output always includes explicit channels, e.g. `adds,0 ...`"))

    out.sort(key=lambda p: (p.line, p.kind))
    return out


def parse_file(path: str) -> ParsedAsm:
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        return parse_asm(fh.read(), source=path)
