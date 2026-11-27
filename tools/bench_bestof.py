"""Benchmark best-of-N sampling on a strided subset of eval_wide.jsonl.

Usage:
    .venv/bin/python tools/bench_bestof.py [out.json]
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

STRIDE = 4
"""Every 4th graph out of 300 (75 representative examples)."""

N = 8
TEMPERATURES = (0.4, 0.7, 1.0)
SEED = 1


def make_subset(src: Path, out: Path, stride: int) -> int:
    """Write every stride-th example to a subset file; return row count."""
    lines = [l for l in src.read_text(encoding="utf-8").splitlines()
             if l.strip()]
    picked = lines[::stride]
    out.write_text("\n".join(picked) + "\n", encoding="utf-8")
    return len(picked)


def dump_bench(res, path: Path) -> None:
    """Serialize BenchResult (including all samples for k=1,2,4,8 slicing) to JSON."""
    data = {
        "seconds": res.seconds,
        "best_of": ({"n": res.best_of.n, "temperature": res.best_of.temperature,
                     "seed": res.best_of.seed} if res.best_of else None),
        "rows": [{
            "n": r.n, "kind": r.kind, "has_store": r.has_store,
            "gap": r.gap, "first_error": r.first_error,
            "samples": None if r.samples is None else [{
                "valid": s.valid, "errors": s.errors, "missing": s.missing,
                "makespan": s.makespan, "gap": s.gap,
            } for s in r.samples],
        } for r in res.rows],
    }
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1),
                    encoding="utf-8")


def load_rows(path: Path) -> list:
    """Reload completed rows from a partial JSON dump for resuming."""
    from vliw.learned.bench import BenchRow, SampleOutcome

    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        out = []
        for r in data["rows"]:
            samples = None if r.get("samples") is None else [
                SampleOutcome(valid=s["valid"], errors=s["errors"],
                              missing=s["missing"], makespan=s["makespan"],
                              gap=s["gap"]) for s in r["samples"]]
            out.append(BenchRow(n=r["n"], kind=r["kind"],
                                has_store=r["has_store"], gap=r["gap"],
                                first_error=r["first_error"], samples=samples))
        return out
    except (ValueError, KeyError, TypeError):
        return []


def _fmt_row(k: int, row) -> str:
    mark = "ok " if row.kind == "valid" else "…  "
    extra = f"samples {row.valid_samples}/{len(row.samples)}" if row.samples else ""
    return (f"  [{k:>3}] {mark} n={row.n:<3} {row.kind:<9} {extra} "
            + (row.first_error or "")[:60])


def summary(out_dir: Path) -> int:
    """Render best-of-k comparison table from saved JSON dumps."""
    tags = ["baseline"] + [f"t{t:g}" for t in TEMPERATURES]
    dumps = {}
    for tag in tags:
        p = out_dir / f"bestof_{tag}.json"
        if p.exists():
            dumps[tag] = json.loads(p.read_text(encoding="utf-8"))
    if not dumps:
        print(f"no dumps found in {out_dir} — run not started", file=sys.stderr)
        return 1

    rows_n = {len(d["rows"]) for d in dumps.values()}
    print(f"# best-of on eval_wide.jsonl subset (every {STRIDE}th)")
    if len(rows_n) > 1:
        print(f"WARNING: incomplete runs, row counts: {sorted(rows_n)}")
    n = min(rows_n)

    def valid_at(tag: str, k: int) -> int:
        return sum(1 for r in dumps[tag]["rows"][:n]
                   if any(s["valid"] for s in (r["samples"] or [])[:k]))

    def gap_mean(tag: str, k: int) -> float | None:
        """Mean gap to optimum among valid schedules within the first k samples."""
        gaps = []
        for r in dumps[tag]["rows"][:n]:
            ok = [s for s in (r["samples"] or [])[:k] if s["valid"]]
            if ok:
                gaps.append(min(s["gap"] for s in ok if s["gap"] is not None))
        return sum(gaps) / len(gaps) if gaps else None

    ks = sorted({1, 2, 4, N})
    print(f"\ngraphs compared: {n}\n")
    header = "| run | " + " | ".join(f"best-of-{k}" for k in ks) + " |"
    print(header)
    print("|---|" + "---|" * len(ks))
    for tag in tags:
        if tag not in dumps:
            continue
        if tag == "baseline":
            v = dumps[tag]["rows"][:n]
            ok = sum(1 for r in v if r["kind"] == "valid")
            print(f"| baseline (t=0, greedy) | {ok}/{n} " + "| " * (len(ks) - 1) + "|")
            continue
        cells = []
        for k in ks:
            ok = valid_at(tag, k)
            cells.append(f"{ok}/{n} ({100 * ok / n:.0f}%)")
        print(f"| t={dumps[tag]['best_of']['temperature']:g} | "
              + " | ".join(cells) + " |")

    print("\nmean gap to optimum among valid (cycles):")
    for tag in tags:
        if tag == "baseline" or tag not in dumps:
            continue
        cells = []
        for k in ks:
            g = gap_mean(tag, k)
            cells.append("—" if g is None else f"{g:.2f}")
        print(f"  t={dumps[tag]['best_of']['temperature']:g}: "
              + "  ".join(f"k={k}: {c}" for k, c in zip(ks, cells)))

    # Single-sample validity rate as baseline for best-of gain.
    #
    print("\nsingle-sample validity rate:")
    for tag in tags:
        if tag == "baseline" or tag not in dumps:
            continue
        total = ok = 0
        for r in dumps[tag]["rows"][:n]:
            for s in r["samples"] or ():
                total += 1
                ok += s["valid"]
        if total:
            print(f"  t={dumps[tag]['best_of']['temperature']:g}: "
                  f"{ok}/{total} ({100 * ok / total:.0f}%)")
    return 0


def main() -> int:
    from vliw.learned.bench import BestOf, BenchResult, run_bench
    from vliw.core import get_profile
    from vliw.learned import runtime
    from vliw.learned.scheduler import LearnedScheduler

    src = ROOT / "eval_wide.jsonl"
    if not src.exists():
        print(f"missing {src}", file=sys.stderr)
        return 1
    out_dir = ROOT / "build" / "bestof"
    out_dir.mkdir(parents=True, exist_ok=True)
    dataset = out_dir / f"eval_wide_s{STRIDE}.jsonl"
    total = make_subset(src, dataset, STRIDE)
    print(f"subset: every {STRIDE}th of {src.name} -> {total} examples",
          flush=True)

    machine = get_profile("e2k-v6-measured")
    adapter = runtime.resolve_adapter("lora-eos")
    if adapter is None:
        print("adapter lora-eos not found", file=sys.stderr)
        return 1

    # Reuse one scheduler/llama-server across runs.
    #
    # temperature/seed.
    sch = LearnedScheduler(adapter=adapter, repair=True)

    jobs = [("baseline", None)]
    jobs += [(f"t{t:g}", BestOf(n=N, temperature=t, seed=SEED))
             for t in TEMPERATURES]

    for tag, bo in jobs:
        print(f"\n=== {tag} ===", flush=True)
        dump = out_dir / f"bestof_{tag}.json"

        # Resume support: reload completed rows and slice remaining dataset.
        #
        #
        #
        #
        #
        done_rows = load_rows(dump)
        if len(done_rows) >= total:
            print(f"  already completed {len(done_rows)}/{total} — skipping",
                  flush=True)
            continue
        run_from = dataset
        if done_rows:
            print(f"  found {len(done_rows)}/{total} in dump — resuming",
                  flush=True)
            rest = out_dir / f"rest_{tag}.jsonl"
            lines = [l for l in dataset.read_text(encoding="utf-8").splitlines()
                     if l.strip()]
            rest.write_text("\n".join(lines[len(done_rows):]) + "\n",
                            encoding="utf-8")
            run_from = rest

        t0 = time.time()

        # Explicitly reset sampling attributes for baseline.
        #
        #
        if bo is None:
            sch.temperature, sch.seed = 0.0, None

        # Checkpoint JSON after every row to preserve multi-hour runs.
        #
        #
        partial = BenchResult(best_of=bo)
        partial.rows.extend(done_rows)

        def on_row(k, row):
            partial.rows.append(row)
            partial.seconds = time.time() - t0
            print(_fmt_row(len(partial.rows), row), flush=True)
            dump_bench(partial, dump)

        res = run_bench(run_from, total - len(done_rows), sch, machine,
                        on_row, best_of=bo)
        res.rows = done_rows + res.rows
        res.seconds = time.time() - t0
        dump_bench(res, dump)
        print(f"--- {tag}: {res.valid}/{len(res.rows)} valid, "
              f"{res.seconds / 60:.0f} min", flush=True)

    print("\nall runs finished:", flush=True)
    for tag, _ in jobs:
        print(f"  {out_dir / ('bestof_' + tag + '.json')}", flush=True)
    return 0


if __name__ == "__main__":
    out_dir = ROOT / "build" / "bestof"
    if len(sys.argv) > 1 and sys.argv[1] == "summary":
        raise SystemExit(summary(out_dir))
    raise SystemExit(main())
