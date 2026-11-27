#!/usr/bin/env python3
"""Standalone stdlib extractor for dependency DAGs and compiler schedules from lcc `.s`.

    python3 collect_real_schedule.py path/to/file.s          # parse
    python3 collect_real_schedule.py report collected.jsonl  # aggregate report
    python3 collect_real_schedule.py to-dataset in.jsonl -o train.jsonl
    python3 collect_real_schedule.py selftest                # self-check
"""

from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import math
import re
import sys
from collections import defaultdict
from pathlib import Path

SCHEMA = 2
TOOL_VERSION = "2.0"

# --------------------------------------------------------------------------
# Standalone mirror of vliw/core/asm_parser.py and vliw/core/model.py
# (zero external dependencies so it can be shared standalone).
#
#
# --------------------------------------------------------------------------

MNEMONICS: dict[str, str] = {
    'adds': 'ADD',
    'addd': 'ADD',
    'addw': 'ADD',
    'incs': 'ADD',
    'incd': 'ADD',
    'subs': 'SUB',
    'subd': 'SUB',
    'subw': 'SUB',
    'decs': 'SUB',
    'muls': 'MUL',
    'muld': 'MUL',
    'mulw': 'MUL',
    'umuls': 'MUL',
    'umuld': 'MUL',
    'sdivs': 'DIV',
    'sdivd': 'DIV',
    'udivs': 'DIV',
    'udivd': 'DIV',
    'divs': 'DIV',
    'divd': 'DIV',
    'ldw': 'LOAD',
    'ldd': 'LOAD',
    'ldb': 'LOAD',
    'ldh': 'LOAD',
    'ldgdw': 'LOAD',
    'ldgdd': 'LOAD',
    'stw': 'STORE',
    'std': 'STORE',
    'stb': 'STORE',
    'sth': 'STORE',
    'shls': 'SHL',
    'shld': 'SHL',
    'shrs': 'SHL',
    'shrd': 'SHL',
    'sars': 'SHL',
    'sard': 'SHL',
    'scls': 'SHL',
    'scrs': 'SHL',
    'ands': 'AND',
    'andd': 'AND',
    'ors': 'AND',
    'ord': 'AND',
    'xors': 'AND',
    'xord': 'AND',
    'andns': 'AND',
    'movts': 'ADD',
    'movtd': 'ADD',
    'sxt': 'ADD',
    'fadds': 'FADD',
    'faddd': 'FADD',
    'fsubs': 'FADD',
    'fsubd': 'FADD',
    'fmuls': 'FMUL',
    'fmuld': 'FMUL',
    # Fused multiply-add — see FMA class in vliw/core/model.py.
    'fmul_addd': 'FMA',
    'fmul_adds': 'FMA',
    'fmul_subd': 'FMA',
    'fmul_subs': 'FMA',
    'fmul_rsubd': 'FMA',
    'fmul_rsubs': 'FMA',
    # APB reads: `,0-,3` (`movaq` `,0 ,2`), free_slot=True (no ALC slot).
    #
    'movab': 'MOVA', 'movah': 'MOVA', 'movaw': 'MOVA',
    'movad': 'MOVA', 'movaqp': 'MOVA',
    'movaq': 'MOVAQ',
    'incr': 'INCR',
    # Format conversions: channels ,0 ,1 ,3 ,4 verified with assembler.
    'istofd': 'CONV', 'istofs': 'CONV', 'idtofd': 'CONV', 'idtofs': 'CONV',
    'fdtoistr': 'CONV', 'fstoistr': 'CONV', 'fdtois': 'CONV', 'fstois': 'CONV',
    'fdtoid': 'CONV', 'fstoid': 'CONV', 'fdtofs': 'CONV', 'fstofd': 'CONV',
    'fdivs': 'FDIV',
    'fdivd': 'FDIV',
    'cmpesb': 'PRED',
    'cmpedb': 'PRED',
    'cmplsb': 'PRED',
    'cmpldb': 'PRED',
    'cmplesb': 'PRED',
    'cmpledb': 'PRED',
    'cmpbsb': 'PRED',
    'cmpbdb': 'PRED',
    'cmpandesb': 'PRED',
    'cmpandedb': 'PRED',
    'cmpandsb': 'PRED',
    'cmpanddb': 'PRED',
    'paddw': 'PACK',
    'paddb': 'PACK',
    'paddh': 'PACK',
    'paddd': 'PACK',
    'psubw': 'PACK',
    'psubb': 'PACK',
    'psubh': 'PACK',
    'psubd': 'PACK',
    'pcmpgtw': 'PACK',
    'pcmpeqw': 'PACK',
    'pminsw': 'PACK',
    'pmaxsw': 'PACK',
    'qpaddw': 'PACK',
    'qpaddb': 'PACK',
    'qpaddh': 'PACK',
    'qpaddd': 'PACK',
    'qpsubw': 'PACK',
    'qpsllw': 'PACKLOG',
    'qpsrlw': 'PACKLOG',
    'qpminsw': 'PACK',
    'qpmaxsw': 'PACK',
    'qpcmpgtw': 'PACK',
    'qppackdl': 'PACK',
    'qpswitchd': 'PACK',
    'qpor': 'PACKLOG',
    'qpand': 'PACKLOG',
    'qpxor': 'PACKLOG',
    'qpsraw': 'PACKLOG',
    'por': 'PACKLOG',
    'pand': 'PACKLOG',
    'pxor': 'PACKLOG',
    'psllw': 'PACKLOG',
    'psrlw': 'PACKLOG',
    'pfadds': 'FADD',
    'pfaddd': 'FADD',
    'pfsubs': 'FADD',
    'pfmuls': 'FMUL',
    'pfmuld': 'FMUL',
    'aaurw': 'AAU',
    'aaurwd': 'AAU',
    'aaurr': 'AAU',
    'aaurrd': 'AAU',
    'staaw': 'AAU',
    'staad': 'AAU',
    'staah': 'AAU',
    'staab': 'AAU',
    'staaq': 'AAU',
    'mmurw': 'AAU',
    'mmurr': 'AAU',
    'shl_adds': 'COMBO',
    'shl_addd': 'COMBO',
    'shr_adds': 'COMBO',
    'shr_addd': 'COMBO',
    'getf_adds': 'COMBO',
    'getf_addd': 'COMBO',
    'insfs': 'INSF',
    'insfd': 'INSF',
    'getfs': 'MERGE',
    'getfd': 'MERGE',
    'merges': 'MERGE',
    'merged': 'MERGE',
    'ldqp': 'LOAD',
    'ldapq': 'LOAD',
    'stqp': 'STORE',
    'stapq': 'STORE',
    'rwd': 'RW',
    'rws': 'RW',
}

# Control/setup ops excluded from compute DAG and counted in `control_ops`.
#
#
#
#
#
CONTROL = {
    "nop", "return", "ct", "ibranch", "call", "disp", "rbranch",
    "setwd", "setbn", "setsft", "settr", "setmas", "setei",
    "getsp", "getpl", "bap", "eap", "flushr", "flushc", "wait",
    "ipd", "abn", "abp", "abg", "alc", "loop_mode", "pref", "landing",
    "ldisp", "fapb",
}

# Stores have no destination register: all register operands are sources.
#
#
#
NO_DST = {"STORE"}

# Latencies and port occupancies from vliw/core/model.py.
#
#
_LATENCY = {"ADD": 1, "SUB": 1, "AND": 1, "SHL": 1,
            "MUL": 4, "DIV": 11, "LOAD": 5, "STORE": 2,
            "FMA": 8, "MOVA": 1, "MOVAQ": 1, "INCR": 1,
            "CONV": 4}
_OCCUPANCY = {"DIV": 2}                       # others default to 1
_LAT_SOURCE = {"ADD": "measured", "SUB": "measured",
               "AND": "assumed", "SHL": "assumed",
               "MUL": "measured", "DIV": "measured",
               "LOAD": "measured", "STORE": "measured",
               "FMA": "measured", "MOVA": "assumed",
               "MOVAQ": "assumed", "INCR": "assumed",
               "CONV": "measured"}
_CHANNELS = {
    "ADD": (0, 1, 2, 3, 4, 5), "SUB": (0, 1, 2, 3, 4, 5),
    "AND": (0, 1, 2, 3, 4, 5), "SHL": (0, 1, 2, 3, 4, 5),
    "MUL": (0, 1, 3, 4), "DIV": (5,),
    "LOAD": (0, 2, 3, 5), "STORE": (2, 5),
    "FMA": (0, 1, 2, 3, 4, 5),
    "MOVA": (0, 1, 2, 3), "MOVAQ": (0, 2),
    "INCR": (0, 1, 2, 3, 4, 5), "CONV": (0, 1, 3, 4),
}
WIDTH = 6

_OP = re.compile(
    r"^\s*(?P<mn>[a-z][a-z0-9_]*)"
    r"(?:,(?P<chan>\d+))?"
    r"(?P<flags>(?:,[a-z][a-z0-9]*)*)"  # post-channel modifiers: ,sm etc.
    r"(?:\s+(?P<args>.*?))?\s*$"
)
"""Single wide-instruction op regex (includes post-channel modifiers like `,sm`)."""
_NOP = re.compile(r"^\s*nop\s+(?P<n>\d+)\s*$", re.I)
_REG = re.compile(r"%?\b([a-z]+\d+|[a-z]+\[\d+\])\b")
_COMMENT = re.compile(r"(//|!|;).*$")
# lcc annotates each bundle with `! <NNNN>` cycle number; cross-check against nop count.
#
#
#
#
_BUNDLE_MARK = re.compile(r"!\s*<(\d+)>")


class Op:
    __slots__ = ("index", "mnemonic", "op", "channel", "dst", "srcs",
                 "cycle", "bundle", "known", "line")

    def __init__(self, index, mnemonic, op, channel, dst, srcs,
                 cycle, bundle, known, line):
        self.index = index
        self.mnemonic = mnemonic
        self.op = op
        self.channel = channel
        self.dst = dst
        self.srcs = srcs
        self.cycle = cycle
        self.bundle = bundle
        self.known = known
        self.line = line


class Parsed:
    __slots__ = ("ops", "bundles", "nop_cycles", "control_ops", "unknown",
                 "skipped", "marker_cycles", "marker_seen", "marker_mismatch")

    def __init__(self):
        self.ops: list[Op] = []
        self.bundles = 0
        self.nop_cycles = 0
        self.marker_cycles = 0      # last lcc-annotated cycle + 1
        self.marker_seen = 0        # count of lcc-annotated bundles
        self.marker_mismatch = 0    # count of mismatches between our counter and lcc markers
        self.control_ops = 0
        self.unknown: dict[str, int] = {}
        self.skipped = 0

    @property
    def compiler_cycles(self) -> int:
        return (max(o.cycle for o in self.ops) + 1) if self.ops else 0


def parse_asm(text: str) -> Parsed:
    """Parse `.s` text into operations with original compiler cycles."""
    res = Parsed()
    bundle = -1
    cycle = 0
    pending_nop = 0
    pending_mark: int | None = None

    def take(body: str, lineno: int) -> None:
        nonlocal pending_nop
        if body.startswith(".") or body.endswith(":"):
            return                                  # directive or label

        m_nop = _NOP.match(body)
        if m_nop:
            # `nop N` inside a wide instruction adds stall cycles before the next bundle.
            #
            pending_nop += int(m_nop.group("n"))
            res.nop_cycles += int(m_nop.group("n"))
            return

        m = _OP.match(body)
        if not m:
            res.skipped += 1
            return

        mn = m.group("mn").lower()
        if mn in CONTROL:
            res.control_ops += 1
            return

        op_class = MNEMONICS.get(mn)
        known = op_class is not None
        if not known:
            # Channel-tagged unknown mnemonics map to UNKNOWN; unchanneled ones are control ops.
            #
            #
            res.unknown[mn] = res.unknown.get(mn, 0) + 1
            #
            #
            #
            #
            #
            #
            if m.group("chan") is None:
                res.control_ops += 1
                return
            op_class = "UNKNOWN"

        args = (m.group("args") or "").strip()
        regs = _REG.findall(args)
        if op_class in NO_DST:
            dst, srcs = None, tuple(regs)
        else:
            dst = regs[-1] if regs else None
            srcs = tuple(regs[:-1]) if len(regs) > 1 else ()

        chan = m.group("chan")
        res.ops.append(Op(
            index=len(res.ops), mnemonic=mn, op=op_class,
            channel=int(chan) if chan is not None else None,
            dst=dst, srcs=srcs, cycle=cycle, bundle=max(0, bundle),
            known=known, line=lineno,
        ))

    for lineno, raw in enumerate(text.splitlines(), 1):
        mk = _BUNDLE_MARK.search(raw)
        if mk:
            pending_mark = int(mk.group(1))
            res.marker_cycles = max(res.marker_cycles, pending_mark + 1)

        line = _COMMENT.sub("", raw).strip()
        # Handle single-line bundles like `{ nop 1 }` without losing a cycle.
        #
        #
        while line:
            if line.startswith("{"):
                bundle += 1
                cycle += pending_nop
                pending_nop = 0
                if pending_mark is not None:
                    # Prefer compiler-annotated cycle; record any counter mismatch.
                    #
                    #
                    #
                    res.marker_seen += 1
                    if pending_mark != cycle:
                        res.marker_mismatch += 1
                    cycle = pending_mark
                    pending_mark = None
                line = line[1:].strip()
                continue
            if line.startswith("}"):
                cycle += 1
                line = line[1:].strip()
                continue
            close = line.find("}")
            if close >= 0:
                body, line = line[:close].strip(), line[close:]
            else:
                body, line = line, ""
            if body:
                take(body, lineno)

    res.bundles = bundle + 1
    if res.ops and all(o.cycle == 0 for o in res.ops):
        # Brace-free listing: cycle is unknown (None).
        #
        #
        for o in res.ops:
            o.cycle = -1
    return res


# --------------------------------------------------------------------------
# Dependency DAG
# --------------------------------------------------------------------------

def build_graph(ops: list[Op]) -> list[dict]:
    """Build RAW/WAR/WAW dependency DAG using simultaneous wide-instruction semantics."""
    reg_id: dict[str, int] = {}

    def rid(name: str) -> int:
        return reg_id.setdefault(name, len(reg_id))

    last_writer: dict[str, int] = {}
    readers: dict[str, list[int]] = defaultdict(list)
    graph: list[dict] = [None] * len(ops)          # type: ignore[list-item]

    def group_key(o: Op) -> int:
        # Brace-free listing: each op forms its own cycle.
        #
        #
        return o.cycle if o.cycle >= 0 else -(o.index + 1)

    i = 0
    while i < len(ops):
        j = i
        while j < len(ops) and group_key(ops[j]) == group_key(ops[i]):
            j += 1
        group = ops[i:j]

        # 1. All reads observe prior-cycle writers.
        for o in group:
            graph[o.index] = {
                "id": o.index,
                "op": o.op,
                "preds": sorted({last_writer[s] for s in o.srcs
                                 if s in last_writer}),
                "war": [],
                "waw": [],
                "dst": rid(o.dst) if o.dst else None,
                "srcs": [rid(s) for s in o.srcs],
            }
        # 2. Record readers (including same-cycle readers for WAR edges).
        #
        for o in group:
            for s in o.srcs:
                readers[s].append(o.index)
        # 3. Apply writes (WAW/WAR).
        for o in group:
            if not o.dst:
                continue
            w = last_writer.get(o.dst)
            if w is not None:
                graph[o.index]["waw"] = [w]
            graph[o.index]["war"] = sorted(set(readers.get(o.dst, ()))
                                           - {o.index})
            last_writer[o.dst] = o.index
            readers[o.dst] = []
        i = j
    return graph


def _lat(op: str) -> int:
    return _LATENCY.get(op, 1)


def _occ(op: str) -> int:
    return _OCCUPANCY.get(op, 1)


def _ports(op: str) -> tuple[int, ...]:
    return _CHANNELS.get(op, tuple(range(WIDTH)))    # UNKNOWN — any channel


# --------------------------------------------------------------------------
# Lower bounds for comparing against the compiler schedule
# --------------------------------------------------------------------------

def critical_path(graph: list[dict]) -> int:
    """Critical-path lower bound in cycles along RAW edges."""
    est = [0] * len(graph)
    end = 0
    for n in graph:
        i = n["id"]
        for p in n["preds"]:
            est[i] = max(est[i], est[p] + _lat(graph[p]["op"]))
        end = max(end, est[i] + _lat(n["op"]))
    return end


def resource_bound(counts: dict[str, int]) -> int:
    """Port-capacity lower bound in cycles (per-class throughput + exclusive ports)."""
    best = 0
    sole: dict[int, int] = defaultdict(int)
    for op, n in counts.items():
        ports = _ports(op)
        if not ports:
            continue
        best = max(best, math.ceil(n * _occ(op) / len(ports)))
        if len(ports) == 1:
            sole[ports[0]] += n * _occ(op)
    if sole:
        best = max(best, max(sole.values()))
    return max(best, math.ceil(sum(counts.values()) / WIDTH) if counts else 0)


def observed_gaps(graph: list[dict], ops: list[Op]) -> dict[str, int]:
    """Minimum observed producer->consumer cycle gap per op class (upper bound on latency)."""
    gaps: dict[str, int] = {}
    for n in graph:
        c = ops[n["id"]]
        if c.cycle < 0:
            continue
        for p in n["preds"]:
            pr = ops[p]
            if pr.cycle < 0:
                continue
            g = c.cycle - pr.cycle
            if g <= 0:
                # Same-cycle RAW is impossible by construction — flag parser bug if seen.
                #
                raise AssertionError(
                    f"RAW edge {p}->{n['id']} with gap {g}: parser bug")
            if pr.op not in gaps or g < gaps[pr.op]:
                gaps[pr.op] = g
    return gaps


def latency_violations(gaps: dict[str, int]) -> list[dict]:
    """Report classes where observed compiler gap is smaller than our assumed latency."""
    out = []
    for op, g in sorted(gaps.items()):
        if g < _lat(op):
            out.append({"op": op, "assumed": _lat(op), "observed": g,
                        "source": _LAT_SOURCE.get(op, "assumed")})
    return out


def reg_pressure(ops: list[Op]) -> int:
    """Peak number of simultaneously live values (register pressure estimate)."""
    last_use: dict[str, int] = {}
    for o in ops:
        for s in o.srcs:
            last_use[s] = o.index
    live: set[str] = set()
    peak = 0
    for o in ops:
        if o.dst:
            live.add(o.dst)
        peak = max(peak, len(live))
        for s in o.srcs:
            if last_use.get(s) == o.index:
                live.discard(s)
    return peak


def compiler_schedule(ops: list[Op]) -> list[dict] | None:
    """Reconstruct the compiler's schedule, or return None on port/cycle conflicts."""
    if not ops or any(o.cycle < 0 for o in ops):
        return None
    used: dict[tuple[int, int], int] = {}
    out: list[dict] = []
    for o in ops:
        ports = _ports(o.op)
        if not ports:
            return None
        port = o.channel if o.channel in ports else None
        if port is None:
            port = next((p for p in ports if (o.cycle, p) not in used), None)
            if port is None:
                return None
        if (o.cycle, port) in used:
            return None
        for k in range(_occ(o.op)):
            used[(o.cycle + k, port)] = o.index
        out.append({"id": o.index, "cycle": o.cycle, "channel": port})
    return out


def fingerprint(graph: list[dict]) -> str:
    """Structural DAG fingerprint for deduplicating identical graphs across reports."""
    canon = json.dumps([[n["id"], n["op"], n["preds"]] for n in graph],
                       separators=(",", ":"))
    return hashlib.sha256(canon.encode()).hexdigest()[:16]


# --------------------------------------------------------------------------
# Record assembly
# --------------------------------------------------------------------------

def process(path: Path) -> dict:
    text = path.read_text(encoding="utf-8", errors="replace")
    res = parse_asm(text)
    graph = build_graph(res.ops)

    counts: dict[str, int] = {}
    for n in graph:
        counts[n["op"]] = counts.get(n["op"], 0) + 1

    sched = compiler_schedule(res.ops)
    cycles = res.compiler_cycles if sched else 0
    cp = critical_path(graph)
    rb = resource_bound(counts)
    lower = max(cp, rb)
    gaps = observed_gaps(graph, res.ops)

    widths: dict[str, int] = defaultdict(int)
    ports: dict[str, int] = defaultdict(int)
    if sched:
        per_cycle: dict[int, int] = defaultdict(int)
        for s in sched:
            per_cycle[s["cycle"]] += 1
            ports[str(s["channel"])] += 1
        for w in per_cycle.values():
            widths[str(w)] += 1

    return {
        "schema": SCHEMA,
        "tool": TOOL_VERSION,
        "source": path.name,            # filename only, strip directory path
        "fingerprint": fingerprint(graph),
        "n_ops": len(graph),
        "op_counts": counts,
        "graph": graph,
        "compiler_schedule": sched,
        "compiler_cycles": cycles or None,
        "bundles": res.bundles,
        "lcc_cycles": res.marker_cycles or None,
        "marker_checked": res.marker_seen,
        "marker_mismatch": res.marker_mismatch,
        "nop_cycles": res.nop_cycles,
        "bundle_widths": dict(widths) or None,
        "port_usage": dict(ports) or None,
        "critical_path": cp,
        "resource_bound": rb,
        "lower_bound": lower,
        "slack": (cycles - lower) if cycles else None,
        "ipc": round(len(graph) / cycles, 2) if cycles else None,
        "reg_pressure": reg_pressure(res.ops),
        "observed_min_gap": gaps,
        "latency_violations": latency_violations(gaps),
        "control_ops": res.control_ops,
        "unknown_mnemonics": res.unknown,
        "skipped_lines": res.skipped,
        "model": {
            "width": WIDTH,
            "latency": _LATENCY,
            "occupancy": _OCCUPANCY,
            "channels": {k: list(v) for k, v in _CHANNELS.items()},
            "note": "latencies measured on lcc-1.29.16 / e2k-v6; adjust for "
                    "other targets and bounds will recompute",
        },
    }


# --------------------------------------------------------------------------
# Output formatting
# --------------------------------------------------------------------------

def render_preview(rec: dict) -> str:
    graph = rec["graph"]
    lines = ["dependency DAG (exported payload):"]
    for n in graph:
        bits = ""
        if n["preds"]:
            bits += f" <- {' '.join(map(str, n['preds']))}"
        false_dep = n["war"] + n["waw"]
        if false_dep:
            bits += f"   (false deps: {' '.join(map(str, sorted(set(false_dep))))})"
        lines.append(f"  {n['id']} {n['op']}{bits}")

    sched = rec["compiler_schedule"]
    if sched:
        lines.append("compiler schedule (cycle=channel):")
        for s in sched:
            lines.append(f"  {s['id']}: cycle={s['cycle']} channel={s['channel']}")
    else:
        lines.append("(no explicit channels in file — compiler schedule "
                     "not reconstructed, DAG only)")
    return "\n".join(lines)


def render_summary(rec: dict) -> str:
    out = [f"ops: {rec['n_ops']}   by class: {rec['op_counts']}"]
    if rec["control_ops"]:
        out.append(f"control ops skipped: {rec['control_ops']} "
                   f"(setwd/disp/ct etc. — non-compute)")
    if rec["skipped_lines"]:
        out.append(f"unparsed lines: {rec['skipped_lines']}")
    if rec["unknown_mnemonics"]:
        for mn, k in sorted(rec["unknown_mnemonics"].items()):
            near = difflib.get_close_matches(mn, MNEMONICS, n=3, cutoff=0.72)
            hint = ("similar to: " + ", ".join(near)) if near else "class UNKNOWN"
            out.append(f"unknown mnemonic `{mn}` x{k} — {hint}")

    if rec["compiler_cycles"]:
        out.append(
            f"compiler cycles: {rec['compiler_cycles']}   "
            f"lower bound: {rec['lower_bound']} "
            f"(critical path {rec['critical_path']}, "
            f"ports {rec['resource_bound']})")
        slack = rec["slack"]
        if slack == 0:
            out.append("  slack 0 — schedule hits the lower bound: "
                       "proven optimal")
        else:
            out.append(f"  slack to lower bound: {slack} cyc — NOT a proven "
                       f"loss (bound may not be achievable), "
                       f"just a signal that this file is worth inspecting")
        out.append(f"  IPC {rec['ipc']}   peak live values: "
                   f"{rec['reg_pressure']}   bundle width: "
                   f"{rec['bundle_widths']}")
    if rec.get("marker_checked"):
        if rec["marker_mismatch"]:
            out.append(f"  CHECK: of {rec['marker_checked']} lcc-annotated wide instructions, "
                       f"our cycle counter differed on "
                       f"{rec['marker_mismatch']} — using lcc markers, "
                       f"but format parsing may be imprecise")
        else:
            out.append(f"  check: all {rec['marker_checked']} wide instructions "
                       f"matched lcc markers — cycles are exact "
                       f"compiler output")
        tail = (rec.get("lcc_cycles") or 0) - (rec.get("compiler_cycles") or 0)
        if rec.get("compiler_cycles") and tail > 0:
            out.append(f"  (total lcc {rec['lcc_cycles']} cyc; trailing "
                       f"{tail} cyc are return/branch with no DAG ops, "
                       f"excluded from comparison)")
    for v in rec["latency_violations"]:
        out.append(f"  FINDING: {v['op']} — model assumed latency "
                   f"{v['assumed']} ({v['source']}), but file gap is "
                   f"{v['observed']}; update machine model")
    return "\n".join(out)


# --------------------------------------------------------------------------
# CLI modes
# --------------------------------------------------------------------------

def read_records(paths: list[Path]) -> list[dict]:
    recs: list[dict] = []
    for p in paths:
        if not p.exists():
            print(f"!! file not found: {p}", file=sys.stderr)
            continue
        for ln, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError as e:
                print(f"!! {p.name}:{ln} invalid JSON — skipped ({e})",
                      file=sys.stderr)
                continue
            if "graph" not in rec:
                print(f"!! {p.name}:{ln} missing graph field — skipped",
                      file=sys.stderr)
                continue
            recs.append(rec)
    return recs


def cmd_collect(args) -> int:
    out_fh = args.out.open("a", encoding="utf-8") if args.out else None
    try:
        for path in args.files:
            if not path.exists():
                print(f"!! file not found: {path}", file=sys.stderr)
                continue
            rec = process(path)
            if not args.quiet:
                print(f"\n=== {path.name} ===")
                if rec["n_ops"] == 0:
                    print("zero operations parsed — wrong file "
                          "or unexpected format")
                else:
                    print(render_summary(rec))
                    print(render_preview(rec))
                print("--- JSON line below: full shareable record ---")
            line = json.dumps(rec, ensure_ascii=False)
            print(line)
            if out_fh:
                out_fh.write(line + "\n")
    finally:
        if out_fh:
            out_fh.close()

    if not args.quiet:
        many = len(args.files) > 1
        print(f"\nNothing was transmitted — the file{'s' if many else ''} "
              f"above {'were' if many else 'was'} only printed to stdout"
              + (f" and appended to {args.out}"
                 if args.out else "")
              + ". Sharing is completely up to you.")
    return 0


def cmd_report(args) -> int:
    """Aggregate collected JSONL records: slack summary and observed latencies."""
    recs = read_records(args.files)
    if not recs:
        print("nothing to aggregate: zero records read", file=sys.stderr)
        return 1

    seen: dict[str, dict] = {}
    dups = 0
    for r in recs:
        fp = r.get("fingerprint") or fingerprint(r["graph"])
        if fp in seen:
            dups += 1
            continue
        seen[fp] = r
    uniq = list(seen.values())

    old = [r for r in uniq if r.get("schema", 1) < SCHEMA]
    print(f"records read: {len(recs)}   unique graphs: {len(uniq)}"
          + (f"   duplicates collapsed: {dups}" if dups else ""))
    if old:
        print(f"WARNING: {len(old)} records from an older schema "
              f"(schema<{SCHEMA}) — missing lower bounds and false deps; "
              f"regenerate with the current script")

    print("\nfile                     ops  cycles   bound  slack   IPC")
    print("-" * 62)
    with_sched = 0
    total_ops = 0
    total_slack = 0
    for r in sorted(uniq, key=lambda x: -(x.get("slack") or 0)):
        total_ops += r.get("n_ops", 0)
        cyc = r.get("compiler_cycles")
        lb = r.get("lower_bound")
        sl = r.get("slack")
        if cyc:
            with_sched += 1
            total_slack += sl or 0
        name = (r.get("source") or "?")[:22]
        print(f"{name:<22} {r.get('n_ops', 0):>5} "
              f"{(cyc if cyc else '—'):>6} {(lb if lb is not None else '—'):>8} "
              f"{(sl if sl is not None else '—'):>6} "
              f"{(r.get('ipc') if r.get('ipc') else '—'):>6}")
    print("-" * 62)
    print(f"total: {total_ops} ops, {with_sched} of {len(uniq)} files "
          f"reconstructed schedules, total slack {total_slack} cyc")
    print("slack is distance to the LOWER BOUND, not necessarily achievable "
          "optimum: 0 proves optimality; large values highlight files "
          "worth inspecting first.")

    # Observed latencies across collected files.
    agg: dict[str, int] = {}
    for r in uniq:
        for op, g in (r.get("observed_min_gap") or {}).items():
            if op not in agg or g < agg[op]:
                agg[op] = g
    if agg:
        print("\nlatencies observed across collected code:")
        print("  class   our model          min observed gap    verdict")
        for op in sorted(agg):
            g, mine = agg[op], _lat(op)
            if g < mine:
                verdict = f"MODEL OVERESTIMATES: <= {g}"
            elif g == mine:
                verdict = "matches"
            else:
                verdict = f"consistent (upper bound <= {g})"
            print(f"  {op:<7} {mine:>3} ({_LAT_SOURCE.get(op, 'assumed')})"
                  f"{'':<4}{g:>6}{'':<14}{verdict}")
        print("  note: gap is an UPPER bound on latency "
              "(compiler could not issue closer), tightening as "
              "more files are collected.")

    ops_total: dict[str, int] = defaultdict(int)
    for r in uniq:
        for op, n in (r.get("op_counts") or {}).items():
            ops_total[op] += n
    if ops_total:
        print(f"\nop counts across all files: {dict(sorted(ops_total.items()))}")

    unknown: dict[str, int] = defaultdict(int)
    for r in uniq:
        for mn, n in (r.get("unknown_mnemonics") or {}).items():
            unknown[mn] += n
    if unknown:
        print("\nunknown mnemonics "
              "(consider adding to MNEMONICS — currently UNKNOWN):")
        for mn, n in sorted(unknown.items(), key=lambda kv: -kv[1]):
            near = difflib.get_close_matches(mn, MNEMONICS, n=3, cutoff=0.72)
            print(f"  {mn:<16} ×{n}"
                  + (f"   similar to: {', '.join(near)}" if near else ""))
    return 0


def cmd_to_dataset(args) -> int:
    """Convert collected JSONL records into prompt/completion dataset format."""
    recs = read_records(args.files)
    seen: set[str] = set()
    written = 0
    skipped = 0
    fh = args.out.open("w", encoding="utf-8") if args.out else sys.stdout
    try:
        for r in recs:
            sched = r.get("compiler_schedule")
            if not sched:
                skipped += 1
                continue        # no schedule -> nothing to train on
            ids = {n["id"] for n in r["graph"]}
            if {s["id"] for s in sched} != ids:
                # Schedule op IDs do not match graph -> skip.
                #
                print(f"!! {r.get('source')}: schedule does not match graph "
                      f"op IDs — skipped", file=sys.stderr)
                skipped += 1
                continue
            fp = r.get("fingerprint") or fingerprint(r["graph"])
            if fp in seen:
                skipped += 1
                continue
            seen.add(fp)

            graph_lines = []
            for n in r["graph"]:
                pred = (" <- " + " ".join(map(str, n["preds"]))) if n["preds"] else ""
                graph_lines.append(f"{n['id']} {n['op']}{pred}")
            prompt = ("profile: e2k-v6-measured\ngraph:\n"
                      + "\n".join(graph_lines) + "\nschedule:")
            completion = "\n".join(
                f"{s['id']}: cycle={s['cycle']} channel={s['channel']}"
                for s in sched)
            fh.write(json.dumps({
                "prompt": prompt,
                "completion": completion,
                "meta": {
                    "source": "real",          # distinguish from synthetic dataset
                    "file": r.get("source"),
                    "fingerprint": fp,
                    "n": r.get("n_ops"),
                    "width": WIDTH,
                    "makespan": r.get("compiler_cycles"),
                    "lower_bound": r.get("lower_bound"),
                    "slack": r.get("slack"),
                },
            }, ensure_ascii=False) + "\n")
            written += 1
    finally:
        if fh is not sys.stdout:
            fh.close()
    print(f"training examples written: {written}"
          + (f", skipped (no schedule or duplicate): {skipped}" if skipped else "")
          + (f" → {args.out}" if args.out else ""), file=sys.stderr)
    if written:
        print("meta.source=\"real\" distinguishes these from synthetic data; "
              "track the real-data ratio when mixing into training.",
              file=sys.stderr)
    return 0


_SAMPLE = """\
	.text
main:
	! <0000>
	{
	  setwd	wsz = 0xc, nfx = 0x1
	  ldw,3	0x0, [ _f64,_lts0 a ], %r3
	}
	! <0001>
	{
	  ldw,2	0x0, [ _f64,_lts0 b ], %r4
	}
	! <0002>
	{ nop 1 }
	! <0004>
	{
	  ldw,0	0x0, [ _f64,_lts0 c ], %r3
	  muls,1	%r3, %r4, %r5
	  nop 4
	}
	! <0009>
	{
	  adds,1	%r5, %r3, %r6
	  std,2	%r3, 0x0, %r4
	}
"""


def cmd_selftest(args) -> int:
    """Self-test parser, DAG builder, and schedule reconstruction on built-in sample."""
    res = parse_asm(_SAMPLE)
    graph = build_graph(res.ops)
    checks: list[tuple[str, bool, str]] = []

    ops_by_class = [n["op"] for n in graph]
    checks.append(("control ops excluded from DAG",
                   "UNKNOWN" not in ops_by_class and len(graph) == 6,
                   f"classes: {ops_by_class}"))
    checks.append(("single-line `{ nop 1 }` preserved cycle",
                   res.bundles == 5,
                   f"bundles counted: {res.bundles}, expected 5"))
    checks.append(("cycles matched lcc markers (nops accounted for)",
                   res.marker_seen == 5 and res.marker_mismatch == 0
                   and [o.cycle for o in res.ops] == [0, 1, 4, 4, 9, 9],
                   f"checked {res.marker_seen}, mismatches "
                   f"{res.marker_mismatch}, cycles "
                   f"{[o.cycle for o in res.ops]}"))
    store = graph[-1]
    checks.append(("store has no destination register, both operands are sources",
                   store["op"] == "STORE" and store["dst"] is None
                   and len(store["srcs"]) == 2,
                   f"STORE: dst={store['dst']} srcs={store['srcs']}"))
    mul = graph[3]
    checks.append(("same-cycle reads happen before writes: MUL read "
                   "%r3 from cycle 0, not same-cycle load",
                   mul["op"] == "MUL" and mul["preds"] == [0, 1],
                   f"MUL preds={mul['preds']}, expected [0, 1]"))
    checks.append(("same-cycle load received WAR edge from MUL",
                   graph[2]["war"] == [3] and graph[2]["waw"] == [0],
                   f"LOAD war={graph[2]['war']} waw={graph[2]['waw']}"))
    cp = critical_path(graph)
    checks.append(("critical path sums latencies",
                   cp == 5 + 4 + 1,
                   f"critical path {cp}, expected 10 (LOAD 5 + MUL 4 + ADD 1)"))
    sched = compiler_schedule(res.ops)
    checks.append(("compiler schedule reconstructed completely",
                   sched is not None and len(sched) == len(graph),
                   f"schedule: {sched}"))
    fp1 = fingerprint(graph)
    fp2 = fingerprint(build_graph(parse_asm(_SAMPLE).ops))
    checks.append(("fingerprint is stable", fp1 == fp2, f"{fp1} / {fp2}"))

    ok = True
    for name, passed, detail in checks:
        print(f"  [{'OK' if passed else 'FAIL'}] {name}")
        if not passed:
            ok = False
            print(f"         {detail}")
    print("\nselftest passed — parser behaves as expected."
          if ok else
          "\nSELFTEST FAILED: parser did not behave as expected. "
          "Do not submit results from this build.")
    return 0 if ok else 1


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    modes = {"collect", "report", "to-dataset", "selftest"}
    # Backwards compatibility: `script file.s` without explicit subcommand.
    if not argv or (argv[0] not in modes and not argv[0].startswith("-")):
        argv.insert(0, "collect")
    elif argv and argv[0].startswith("-") and argv[0] not in ("-h", "--help"):
        argv.insert(0, "collect")

    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="mode", required=True)

    p = sub.add_parser("collect", help="parse .s files and print JSON records")
    p.add_argument("files", nargs="+", type=Path, help="one or more .s files")
    p.add_argument("--out", type=Path, default=None,
                   help="append JSON records to file in addition to stdout "
                        "(default: stdout only, writes nothing "
                        "unless specified)")
    p.add_argument("--quiet", action="store_true",
                   help="omit human-readable summary, print JSON only")
    p.set_defaults(fn=cmd_collect)

    p = sub.add_parser("report", help="aggregate collected JSONL records into a summary")
    p.add_argument("files", nargs="+", type=Path)
    p.set_defaults(fn=cmd_report)

    p = sub.add_parser("to-dataset",
                       help="convert collected JSONL into prompt/completion dataset")
    p.add_argument("files", nargs="+", type=Path)
    p.add_argument("--out", type=Path, default=None)
    p.set_defaults(fn=cmd_to_dataset)

    p = sub.add_parser("selftest", help="run built-in parser selftest")
    p.set_defaults(fn=cmd_selftest)

    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
