"""Build real-code eval JSONL with proven optima from lcc `.s` basic blocks and windows.

Usage:
    python3 tools/make_eval_real.py
    python3 tools/make_eval_real.py --oracle 10 --jobs 2
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from training.encode import (  # noqa: E402
    build_schedule, decode_completion, encode_completion, encode_prompt)
from vliw.core import dag as _dag_module  # noqa: E402
from vliw.core.baseline import GreedyListScheduler  # noqa: E402
from vliw.core.blocks import (  # noqa: E402
    block_graphs_of_file, window_graphs)
from vliw.core.dag import DAG, compute_metrics  # noqa: E402
from vliw.core.model import get_profile  # noqa: E402
from vliw.core.oracle import OracleScheduler  # noqa: E402
from vliw.tiny.fast import TinyFlashScheduler  # noqa: E402
from vliw.tiny.features import build_dag, parse_graph_entries  # noqa: E402

DEFAULT_DIR = ROOT / "real_candidates_100_400" / "asm"
DEFAULT_PROFILE = "e2k-v6-measured"

#: Ops that do not need a symbol in `_SYMBOL` (encoded separately).
_NO_SYMBOL_NEEDED = {"LOAD", "STORE"}


# --------------------------------------------------------------------------
# Graph collection
# --------------------------------------------------------------------------

@dataclass
class Item:
    file: str        # .s filename without directory
    kind: str        # block | block_loop | window | window_loop
    key: str         # graph key (stem#block[wNtM])
    loop: bool
    dag: DAG
    seen: int = 1    # occurrence count of this graph across the corpus


def signature(dag: DAG) -> tuple:
    """Canonical graph signature (ops and edges as seen by the scheduler)."""
    return tuple((i.op, i.preds) for i in dag)


def missing_symbols(dag: DAG) -> set[str]:
    """Ops missing from `_SYMBOL` (unencodable in prompt format)."""
    known = set(getattr(_dag_module, "_SYMBOL", {})) | _NO_SYMBOL_NEEDED
    return {i.op for i in dag} - known


def roundtrip(dag: DAG, model) -> tuple[DAG | None, str]:
    """Roundtrip encode -> decode check: returns `(dag, "")` or `(None, reason)`."""
    try:
        back = build_dag(parse_graph_entries(encode_prompt(dag, model)))
    except KeyError as exc:
        return None, f"missing symbol in dag._SYMBOL: {exc.args[0] if exc.args else exc}"
    except Exception as exc:  # noqa: BLE001 — any failure means unencodable
        return None, f"{type(exc).__name__}: {exc}"
    if signature(back) != signature(dag):
        return None, "graph structure changed after roundtrip"
    return back, ""


def collect(paths: list[Path], min_ops: int, windows: bool,
            win_min: int, win_max: int) -> tuple[list[Item], int]:
    """Collect blocks then windows, deduplicating identical graphs."""
    items: list[Item] = []
    index: dict[tuple, Item] = {}
    dups = 0

    def add(file: str, kind: str, key: str, loop: bool, dag: DAG) -> None:
        nonlocal dups
        sig = signature(dag)
        if sig in index:
            index[sig].seen += 1
            dups += 1
            return
        it = Item(file, kind, key, loop, dag)
        index[sig] = it
        items.append(it)

    # all blocks before windows so whole-block duplicates remain tagged as blocks
    for p in paths:
        for g in block_graphs_of_file(p, min_ops=min_ops):
            add(p.stem, "block_loop" if g.block.loop else "block", g.dag.key,
                g.block.loop, g.dag)
    if windows:
        for p in paths:
            text = p.read_text(encoding="utf-8")
            for w in window_graphs(text, source=p.name, min_ops=win_min, max_ops=win_max):
                add(p.stem, "window_loop" if w.loop else "window", w.dag.key, w.loop, w.dag)
    return items, dups


# --------------------------------------------------------------------------
# Search for proven optima (worker processes)
# --------------------------------------------------------------------------

_W: dict = {}


def _init(profile: str, oracle_budget: float) -> None:
    _W["model"] = get_profile(profile)
    _W["fast"] = TinyFlashScheduler(mode="exact", with_trace=False)
    _W["greedy"] = GreedyListScheduler()
    _W["budget"] = oracle_budget


def solve(dag: DAG, model, fast, greedy, oracle_budget: float) -> dict:
    """Return best schedule and proof source: `bound` | `oracle` | None."""
    t0 = time.perf_counter()
    base = greedy.schedule(dag, model).schedule.makespan
    lb = compute_metrics(dag, model).lower_bound
    res = fast.schedule(dag, model)
    best = res.schedule
    by = "bound" if best.makespan <= lb else None
    oracle_s = 0.0
    if by is None and oracle_budget > 0:
        t1 = time.perf_counter()
        orc = OracleScheduler(budget_s=oracle_budget, portfolio_s=0.0).schedule(dag, model)
        oracle_s = time.perf_counter() - t1
        o = orc.schedule
        legal = o.complete and not o.validate()
        if orc.optimal and legal:
            if o.makespan > best.makespan:     # proven optimum cannot be worse than an already-found valid schedule
                raise RuntimeError(
                    f"{dag.key}: oracle claimed {o.makespan}, but tiny found {best.makespan}")
            best, by = o, "oracle"
        elif legal and o.makespan < best.makespan:
            best = o                            # unproven but shorter — keep as best known
    return {"by": by, "lb": lb, "base": base, "ms": best.makespan,
            "completion": encode_completion(best), "oracle_s": oracle_s,
            "s": time.perf_counter() - t0}


def _solve_job(job: tuple) -> tuple[int, dict]:
    idx, dag = job
    return idx, solve(dag, _W["model"], _W["fast"], _W["greedy"], _W["budget"])


# --------------------------------------------------------------------------
# File serialization and roundtrip verification
# --------------------------------------------------------------------------

def shape_of(kind: str) -> str:
    return "real-" + kind.replace("_", "-")


def make_row(it: Item, r: dict, model) -> dict:
    meta = {
        "n": len(it.dag), "shape": shape_of(it.kind), "baseline": r["base"],
        "lb": r["lb"], "file": it.file, "key": it.key, "loop": it.loop, "seen": it.seen,
    }
    if r["by"]:
        meta = {"makespan": r["ms"], "gap": r["base"] - r["ms"], "proven_by": r["by"], **meta}
    else:
        meta = {"best_known": r["ms"], "proven": False, **meta}
    return {"prompt": encode_prompt(it.dag, model), "completion": r["completion"], "meta": meta}


def verify_file(path: Path, model, proven: bool) -> list[str]:
    """Read back written JSONL and verify every row (empty list = all OK)."""
    problems: list[str] = []
    with path.open(encoding="utf-8") as f:
        for lineno, line in enumerate(f, 1):
            if not line.strip():
                continue
            row = json.loads(line)
            meta = row["meta"]
            tag = f"{path.name}:{lineno}"
            try:
                dag = build_dag(parse_graph_entries(row["prompt"]))
            except Exception as exc:  # noqa: BLE001
                problems.append(f"{tag}: failed to parse DAG ({type(exc).__name__}: {exc})")
                continue
            if len(dag) != meta["n"]:
                problems.append(f"{tag}: incomplete DAG parse {len(dag)} of {meta['n']}")
                continue
            sched = build_schedule(dag, model, decode_completion(row["completion"]))
            errs = sched.validate()
            if errs or not sched.complete:
                problems.append(f"{tag}: invalid schedule: {(errs or ['incomplete'])[0][:80]}")
                continue
            want = meta["makespan"] if proven else meta["best_known"]
            if sched.makespan != want:
                problems.append(f"{tag}: makespan {sched.makespan}, meta has {want}")
            if proven and "makespan" not in meta:
                problems.append(f"{tag}: missing meta.makespan")
            if not proven and "makespan" in meta:
                problems.append(f"{tag}: unproven graph must not have meta.makespan")
            if sched.makespan < meta["lb"]:
                problems.append(f"{tag}: makespan {sched.makespan} below lower bound {meta['lb']}")
            if meta["baseline"] < sched.makespan:
                problems.append(f"{tag}: greedy {meta['baseline']} beats recorded {sched.makespan}")
    return problems


def write_jsonl(path: Path, rows: list[dict]) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8", newline="\n") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    os.replace(tmp, path)


# --------------------------------------------------------------------------
# Summary
# --------------------------------------------------------------------------

def summarize(items: list[Item], results: list[dict], skipped: Counter, dups: int,
              wall: float) -> None:
    proven = [(it, r) for it, r in zip(items, results) if r["by"]]
    opened = [(it, r) for it, r in zip(items, results) if not r["by"]]
    print(f"\nunique graphs after dedup: {len(items) + sum(skipped.values())} "
          f"(duplicates removed: {dups})")
    if skipped:
        tot = sum(skipped.values())
        why = ", ".join(f"{k} ×{v}" for k, v in skipped.most_common())
        print(f"unencodable graphs skipped: {tot} — {why}")
    print(f"written: proven {len(proven)}, open {len(opened)}")
    if proven:
        by = Counter(r["by"] for _, r in proven)
        print(f"  proven by: lower bound {by.get('bound', 0)}, oracle {by.get('oracle', 0)}")
        gaps = [r["base"] - r["ms"] for _, r in proven]
        zero = sum(1 for g in gaps if g == 0)
        print(f"  greedy already optimal: {zero}/{len(proven)} "
              f"({100.0 * zero / len(proven):.1f}%), total greedy excess cycles: {sum(gaps)}")
    kinds = Counter(it.kind for it, _ in proven)
    kinds_o = Counter(it.kind for it, _ in opened)
    if kinds or kinds_o:
        print("  by kind:", ", ".join(
            f"{k}: {kinds.get(k, 0)}+{kinds_o.get(k, 0)}"
            for k in ("block", "block_loop", "window", "window_loop")),
            "(proven + open)")
    if opened:
        slack = [r["ms"] - r["lb"] for _, r in opened]
        print(f"  open graphs: total best-known slack above lower bound {sum(slack)} cycles "
              f"(max {max(slack)} per graph)")
    print(f"elapsed {wall:.0f} s")


# --------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    # Avoid UnicodeEncodeError on narrow Windows console encodings
    for _stream in (sys.stdout, sys.stderr):
        try:
            _stream.reconfigure(errors="replace")
        except Exception:  # noqa: BLE001 — stream replaced (tests/redirect)
            pass
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("files", nargs="*", type=Path, help=".s files (default: entire corpus)")
    ap.add_argument("--dir", type=Path, default=DEFAULT_DIR)
    ap.add_argument("--profile", default=DEFAULT_PROFILE)
    ap.add_argument("--min-ops", type=int, default=10, help="minimum ops per block")
    ap.add_argument("--no-windows", action="store_true", help="whole blocks only (no windows)")
    ap.add_argument("--win-min", type=int, default=12)
    ap.add_argument("--win-max", type=int, default=56)
    ap.add_argument("--oracle", type=float, default=3.0,
                    help="oracle budget per graph in seconds when above lower bound (0 = disable)")
    ap.add_argument("--jobs", type=int, default=1, help="worker processes")
    ap.add_argument("--out", type=Path, default=ROOT / "eval_real.jsonl")
    ap.add_argument("--out-open", type=Path, default=ROOT / "eval_real_open.jsonl")
    ap.add_argument("--limit", type=int, default=0, help="cap at N graphs (for quick runs)")
    a = ap.parse_args(argv)

    model = get_profile(a.profile)
    paths = list(a.files) or sorted(a.dir.glob("*.s"))
    if not paths:
        print(f"no .s files in {a.dir}", file=sys.stderr)
        return 2
    t0 = time.perf_counter()
    items, dups = collect(paths, a.min_ops, not a.no_windows, a.win_min, a.win_max)

    # filter unencodable graphs before running search
    keep: list[Item] = []
    skipped: Counter = Counter()
    for it in items:
        back, why = roundtrip(it.dag, model)
        if back is None:
            miss = sorted(missing_symbols(it.dag))
            skipped[" ".join(miss) if miss else why] += 1
        else:
            keep.append(it)
    if a.limit:
        keep = keep[:a.limit]
    print(f"files {len(paths)}; graphs to solve {len(keep)}; profile {model.name}; "
          f"oracle {a.oracle:g} s/graph; workers {a.jobs}", flush=True)

    jobs = [(i, it.dag) for i, it in enumerate(keep)]
    results: list[dict | None] = [None] * len(keep)
    if a.jobs > 1 and len(jobs) > 1:
        with ProcessPoolExecutor(max_workers=a.jobs, initializer=_init,
                                 initargs=(a.profile, a.oracle)) as pool:
            for k, (i, r) in enumerate(pool.map(_solve_job, jobs, chunksize=4), 1):
                results[i] = r
                if k % 250 == 0:
                    print(f"  ... {k}/{len(jobs)}  {time.perf_counter() - t0:.0f} s", flush=True)
    else:
        _init(a.profile, a.oracle)
        for k, job in enumerate(jobs, 1):
            i, r = _solve_job(job)
            results[i] = r
            if k % 250 == 0:
                print(f"  ... {k}/{len(jobs)}  {time.perf_counter() - t0:.0f} s", flush=True)

    rows_ok, rows_open = [], []
    for it, r in zip(keep, results):
        (rows_ok if r["by"] else rows_open).append(make_row(it, r, model))
    write_jsonl(a.out, rows_ok)
    write_jsonl(a.out_open, rows_open)
    summarize(keep, results, skipped, dups, time.perf_counter() - t0)
    print(f"files: {a.out}, {a.out_open}")

    problems = verify_file(a.out, model, True) + verify_file(a.out_open, model, False)
    if problems:
        print(f"\nVERIFY WRITTEN: {len(problems)} issues; first:")
        for p in problems[:8]:
            print("  ", p)
        return 1
    print("written file verification (roundtrip, validity, makespan, lower bound): OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
