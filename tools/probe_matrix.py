"""Re-probe the e2k port capability matrix and pair bans against the assembler.

    python tools/probe_matrix.py            # probe and compare with model.py
    python tools/probe_matrix.py --show     # also print full matrix
"""

from __future__ import annotations

import argparse
import itertools
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from vliw.core.model import E2K_V6_MEASURED as MODEL  # noqa: E402

# Model op class -> lcc mnemonic template ({c}=channel, {d}=dest register).
#
#
#
# Separate dest registers prevent false write-port conflicts in pair probes.
#
#
#
OPS = {
    "ADD":   "adds,{c}\t%r3, %r4, %r{d}",
    "SUB":   "subs,{c}\t%r3, %r4, %r{d}",
    "AND":   "ands,{c}\t%r3, %r4, %r{d}",
    "SHL":   "shls,{c}\t%r3, %r4, %r{d}",
    "MUL":   "muls,{c}\t%r3, %r4, %r{d}",
    "DIV":   "sdivs,{c}\t%r3, %r4, %r{d}",
    "LOAD":  "ldw,{c}\t0x0, [ _f64,_lts0 a ], %r{d}",
    # STORE requires a register for SRC3; syntax errors are separated from channel bans.
    #
    #
    #
    #
    "STORE": "stw,{c}\t%dr2, 0x0, %r{d}",
}

# Representative ops per class for pairwise bundle probing.
#
#
PAIR_REPS = ("ADD", "MUL", "DIV", "LOAD", "STORE")

# EXPECTED pair bans in a single wide instruction (cross-cluster seams).
#
#
#
#
#
#
#     the combination of STORE in ALC2 with LOAD in ALC3 is prohibited
#     the combination of STORE in ALC5 with LOAD in ALC0 is prohibited
#
# Both lie on seams between channel clusters ALC0-2 and ALC3-5.
#
#
#
#
# NOTE: vliw/core/model.py intentionally omits pair bans (see examples/probes/README.md).
#
#
EXPECTED_COMBO_BANS: set[tuple[tuple[str, int], tuple[str, int]]] = {
    (("STORE", 2), ("LOAD", 3)),
    (("STORE", 5), ("LOAD", 0)),
}

# Minimal valid assembly wrapper: prologue, one wide instruction, epilogue.
#
#
SKELETON = """\
\t.text
\t.global\tmain
\t.type\tmain, #function
\t.align\t8
main:
\t{{
\t  setwd\twsz = 0xc, nfx = 0x1, dbl = 0x0
\t}}
\t{{
{body}
\t}}
\t{{
\t  return\t%ctpr3
\t}}
\t{{
\t  ct\t%ctpr3
\t}}
\t.data
\t.global\ta
\t.type\ta, #object
\t.align\t16
a:
\t.uadword\t0x0
"""

CANDIDATES = [
    "~/e2k-toolchain/opt/mcst/lcc-1.29.16.e2k-v6.linux-6.1/bin.toolchain/e2k-linux-as",
    "~/e2k-toolchain/opt/mcst/*/bin.toolchain/e2k-linux-as",
]


def find_as() -> str | None:
    env = os.environ.get("E2K_AS")
    if env and Path(env).exists():
        return env
    for pat in CANDIDATES:
        for p in sorted(Path(os.path.expanduser("/")).glob(pat.lstrip("~/").lstrip("/"))
                        if "*" in pat else []):
            if p.exists():
                return str(p)
        p = Path(os.path.expanduser(pat))
        if "*" not in pat and p.exists():
            return str(p)
    return shutil.which("e2k-linux-as")


def _assemble(as_bin: str, body: str, tmp: Path, tag: str) -> tuple[bool, str]:
    """Assemble one wide instruction; return `(accepted, error_text)`."""
    src = tmp / f"{tag}.s"
    src.write_text(SKELETON.format(body=body), encoding="utf-8")
    r = subprocess.run([as_bin, "-mcpu=elbrus-v6", str(src), "-o", str(src.with_suffix(".o"))],
                       capture_output=True, text=True)
    if r.returncode == 0:
        return True, ""
    msg = " ".join(line.strip() for line in r.stderr.splitlines()
                   if "Error" in line)[:160]
    return False, msg


def probe(as_bin: str, op: str, channel: int, tmp: Path) -> tuple[bool, str]:
    """Check if channel accepts this op; return `(accepted, error_text)`."""
    body = "\t  " + OPS[op].format(c=channel, d=5)
    ok, msg = _assemble(as_bin, body, tmp, f"{op}_{channel}")
    if ok:
        return True, ""
    # Ensure rejection is a channel-encoding error, not a syntax error.
    #
    if "cannot be encoded in ALC" not in msg:
        return False, f"NOT A CHANNEL ERROR: {msg}"
    return False, msg


def probe_pair(as_bin: str, a: tuple[str, int], b: tuple[str, int],
               tmp: Path) -> tuple[bool, str]:
    """Check if two individually valid ops assemble together in one wide instruction."""
    (opA, cA), (opB, cB) = a, b
    body = ("\t  " + OPS[opA].format(c=cA, d=5) + "\n"
            "\t  " + OPS[opB].format(c=cB, d=6))
    return _assemble(as_bin, body, tmp, f"pair_{opA}{cA}_{opB}{cB}")


def probe_combinations(as_bin: str, measured: dict[str, tuple[int, ...]],
                       tmp: Path) -> tuple[set, list[str]]:
    """Exhaustive pairwise probe; returns `(banned_pairs, non_combo_errors)`."""
    cells = [(op, c) for op in PAIR_REPS for c in measured.get(op, ())]
    bans: set[tuple[tuple[str, int], tuple[str, int]]] = set()
    odd: list[str] = []
    for a, b in itertools.combinations(cells, 2):
        if a[1] == b[1]:
            continue        # two ops on the same channel is trivially impossible
        ok, msg = probe_pair(as_bin, a, b, tmp)
        if ok:
            continue
        if "prohibited" in msg or "combination" in msg:
            # Normalize pair order since bans are symmetric.
            #
            bans.add(tuple(sorted((a, b))))
        else:
            odd.append(f"{a[0]},{a[1]} + {b[0]},{b[1]}: {msg}")
    return bans, odd


def run(show: bool = False) -> bool:
    """Probe and verify capability matrix against model.py (True if match or no assembler)."""
    as_bin = find_as()
    if not as_bin:
        print("e2k assembler not found (checked E2K_AS, ~/e2k-toolchain, PATH) — "
              "cannot probe capability matrix")
        print("not an error: without the toolchain, vliw/core/model.py remains "
              "the source of truth")
        return True
    print(f"assembler: {as_bin}\nprofile:   {MODEL.name}, {MODEL.width} ports\n")

    width = MODEL.width
    measured: dict[str, tuple[int, ...]] = {}
    broken: list[str] = []

    with tempfile.TemporaryDirectory(prefix="e2kprobe-") as td:
        tmp = Path(td)
        for op in OPS:
            ok: list[int] = []
            for ch in range(width):
                accepted, msg = probe(as_bin, op, ch, tmp)
                if accepted:
                    ok.append(ch)
                elif msg.startswith("NOT A CHANNEL ERROR"):
                    broken.append(f"{op},{ch}: {msg}")
            measured[op] = tuple(ok)

    if broken:
        print("!! assembler rejected for non-channel reason — probe "
              "inconclusive for these pairs:")
        for b in broken[:8]:
            print("   ", b)
        print()

    if show:
        print("    " + " " * 7 + "".join(f"{f',{c}':>4}" for c in range(width)))
        for op in OPS:
            row = "".join(f"{'•' if c in measured[op] else '·':>4}"
                          for c in range(width))
            print(f"    {op:<7}{row}")
        print()

    diffs = []
    for op in OPS:
        model_ch = MODEL.channels_for(op)
        if measured[op] != model_ch:
            diffs.append(f"{op}: assembler {measured[op]}, model.py {model_ch}")

    if diffs:
        print("MISMATCHES (assembler is ground truth, update model.py):")
        for d in diffs:
            print("   ", d)
        return False

    print(f"port matrix matches vliw/core/model.py across all "
          f"{len(OPS)}x{width} pairs")
    print("(latencies and occupancy are not probed here; they are measured via "
          "dependent chains and independent bursts, see "
          "examples/probes/README.md)")

    return _report_combinations(as_bin, measured)


def _report_combinations(as_bin: str, measured: dict[str, tuple[int, ...]]) -> bool:
    """Probe and report wide-instruction pair bans."""
    with tempfile.TemporaryDirectory(prefix="e2kpairs-") as td:
        bans, odd = probe_combinations(as_bin, measured, Path(td))

    want = {tuple(sorted(p)) for p in EXPECTED_COMBO_BANS}
    print(f"\nwide-instruction pair bans found: {len(bans)}")
    for a, b in sorted(bans):
        print(f"    {a[0]},{a[1]} + {b[0]},{b[1]} — cannot co-encode")

    if odd:
        print("!! non-combo error — probe inconclusive for these pairs:")
        for o in odd[:8]:
            print("   ", o)

    if bans != want:
        print("\nMISMATCH with expected ban set "
              "(EXPECTED_COMBO_BANS in this file):")
        for p in sorted(want - bans):
            print(f"    expected ban, but assembler allows: {p}")
        for p in sorted(bans - want):
            print(f"    NEW previously unknown ban: {p}")
        return False

    print("    matches expected ban set")
    print("    NOTE: vliw/core/model.py omits pair bans (models port->ops only)."
          "")
    print("    Known gap documented in examples/probes/README.md."
          "")
    return True


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--show", action="store_true", help="print full capability matrix")
    args = ap.parse_args(argv)
    return 0 if run(show=args.show) else 1


if __name__ == "__main__":
    sys.exit(main())
