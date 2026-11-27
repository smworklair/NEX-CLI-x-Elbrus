#!/usr/bin/env python3
"""Compare synthetic training op vocabulary against real lcc compiler output.

    python3 tools/check_real_vs_synth.py
"""

from __future__ import annotations

import collections
import itertools
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from vliw.core.asm_parser import (                          # noqa: E402
    MNEMONICS, build_dag, compiler_schedule, parse_asm)
from vliw.core.model import get_profile                     # noqa: E402

# Unknown channel-tagged ops map to UNKNOWN; unchanneled ones count as control.
#
#
#

# Representative C kernels: accumulation loop, FP, branch, memcpy, string hash.
#
PROGRAMS = {
    "loop":   "int f(int *a,int n){int s=0;for(int i=0;i<n;i++)s+=a[i]*3+1;return s;}",
    "math":   "double g(double x,double y){return (x*y + x/y)*(x - y);}",
    "branch": "int h(int a,int b,int c){if(a>b)return a*c;else if(b>c)return b+c;return a-b-c;}",
    "mem":    "void cp(char *d,const char *s,int n){for(int i=0;i<n;i++)d[i]=s[i];}",
    "str":    "unsigned hs(const char*s){unsigned h=5381;while(*s)h=h*33+(unsigned char)*s++;return h;}",
}
LEVELS = ("0", "2", "3")


def find_lcc() -> Path | None:
    """MCST cross-lcc compiler (same toolchain used for examples/probes/)."""
    for p in sorted(Path.home().glob("e2k-toolchain/opt/mcst/lcc-*/bin/lcc")):
        return p
    return None


def synthetic_mix(name: str, limit: int = 20000):
    """Operation classes present in a training JSONL file, or None if missing."""
    path = ROOT / name
    if not path.exists():
        return None
    ops: collections.Counter = collections.Counter()
    sizes = []
    with path.open(encoding="utf-8") as f:
        for line in itertools.islice(f, limit):
            row = json.loads(line)
            k = 0
            for raw in row["prompt"].split("\n")[2:]:
                raw = raw.strip()
                if raw in ("schedule:", "\u0440\u0430\u0441\u043f\u0438\u0441\u0430\u043d\u0438\u0435:"):
                    break
                if not raw:
                    continue
                k += 1
                ops[raw.split(" <- ")[0].split(" ", 1)[1]] += 1
            sizes.append(k)
    return ops, sizes


def main() -> int:
    lcc = find_lcc()
    if lcc is None:
        print("cross-lcc not found in ~/e2k-toolchain — cannot compile",
              file=sys.stderr)
        return 1
    ver = subprocess.run([str(lcc), "--version"], capture_output=True,
                         text=True).stdout.splitlines()[0]
    print(f"compiler: {ver}\n")

    machine = get_profile("e2k-v6-measured")
    tmp = Path(tempfile.mkdtemp(prefix="real_vs_synth_"))
    rows = []
    real_ops: collections.Counter = collections.Counter()
    unknown_mn: collections.Counter = collections.Counter()

    for name, src in PROGRAMS.items():
        c = tmp / f"{name}.c"
        c.write_text(src + "\n", encoding="utf-8")
        for lvl in LEVELS:
            s = tmp / f"{name}_O{lvl}.s"
            r = subprocess.run([str(lcc), "-S", f"-O{lvl}", str(c), "-o", str(s)],
                               capture_output=True, text=True)
            if r.returncode != 0 or not s.exists():
                print(f"  {name} -O{lvl}: compiler failed", file=sys.stderr)
                continue
            parsed = parse_asm(s.read_text(encoding="utf-8"))
            ops = parsed.ops
            counts = collections.Counter(o.op for o in ops)
            real_ops += counts
            for mn, k in parsed.unknown_mnemonics.items():
                unknown_mn[mn] += k
            n = len(ops) or 1
            unk = sum(1 for o in ops if o.op == "UNKNOWN")
            sched = compiler_schedule(parsed, build_dag(parsed, name), machine)
            rows.append((f"{name}_O{lvl}", len(ops), 100.0 * unk / n,
                         parsed.skipped_lines,
                         "yes" if sched is not None else "no"))

    print("REAL lcc OUTPUT")
    print(f"  {'file':<12}{'ops':>9}{'UNKNOWN':>10}"
          f"{'unparsed':>14}{'lcc schedule':>16}")
    for name, n, unk, skipped, sched in rows:
        print(f"  {name:<12}{n:>9}{unk:>9.0f}%{skipped:>14}{sched:>16}")

    total = sum(real_ops.values()) or 1
    unk_total = sum(unknown_mn.values())
    print("\n  compiler operation classes (as parsed):")
    for op, k in real_ops.most_common():
        print(f"    {op:<10}{k:>6}{100.0 * k / total:>7.1f}%")
    known = total - real_ops.get("UNKNOWN", 0)
    print(f"\n  recognized: {known} of {total} ops "
          f"({100.0 * known / total:.0f}%)")

    print(f"\n  mnemonics in project dictionary: {len(MNEMONICS)}"
          f"  ->  classes: {len(set(MNEMONICS.values()))}")
    if unknown_mn:
        print(f"  unknown mnemonics: {len(unknown_mn)} distinct, "
              f"{sum(unknown_mn.values())} occurrences")
        print("    " + ", ".join(sorted(unknown_mn)[:24]))

    print("\nSYNTHETIC TRAINING DATA")
    for name in ("dataset.jsonl", "train_merged.jsonl", "eval_wide.jsonl"):
        mix = synthetic_mix(name)
        if mix is None:
            print(f"  {name}: missing file")
            continue
        ops, sizes = mix
        tot = sum(ops.values()) or 1
        print(f"  {name}: graphs {min(sizes)}..{max(sizes)} ops, "
              f"{len(ops)} classes")
        print("    " + "  ".join(f"{op} {100.0 * k / tot:.0f}%"
                                 for op, k in ops.most_common()))

    unk_share = 100.0 * real_ops.get("UNKNOWN", 0) / total
    print(f"\nSUMMARY: {unk_share:.0f}% of DAG ops are UNKNOWN: unmapped by model, "
          f"\nscheduled with latency 1 and any channel "
          f"(placeholder, not measured).")
    print(f"temp files kept in {tmp}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
