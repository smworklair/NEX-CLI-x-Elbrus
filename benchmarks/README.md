# `e2k` Snippet Benchmark

Four handwritten `e2k` assembly snippets: `muls` latency, software pipelining, predicated execution, and Horner's scheme with loads. Each file is parsed with the same parser used for real `lcc` output and run through NEX CLI's three schedulers.

```bash
python tools/bench_snippets.py                 # all files, ~2 s
python tools/bench_snippets.py --budget 5      # more time for exact search
python tools/bench_snippets.py benchmarks/snippets/04_horner_load.s
```

Results are written to [`results.json`](results.json) and [`RESULTS.md`](RESULTS.md).

## What Is Measured

| column | meaning |
|---|---|
| `author` | schedule length as written in the file |
| `baseline` | greedy list scheduler |
| `TINY Flash` | project's fast learned scheduler, `exact` mode |
| `oracle` | exact search with a time budget (default 1.5 s per file) |
| `UNKNOWN` | operations whose class is unknown to the model (placeholder, not measured) |
| `errors` | linter findings: disallowed channel, occupied port, result read before ready |

`author` can be shorter than the valid minimum: the linter flags places where `nop 1` was written even though operation latency is higher. The schedulers rebuild the schedule from scratch using the dependency graph and machine model, so their makespan is always valid.

## Current Results

| file | N | author | baseline | TINY Flash | oracle | UNKNOWN |
|---|---:|---:|---:|---:|---:|---:|
| `01_mul_latency.s` | 15 | 12 | 8 | 8 | 8 | 0 |
| `02_software_pipeline.s` | 19 | 7 | 9 | 9 | 9 | 0 |
| `03_predication.s` | 9 | 3 | 8 | 8 | 8 | 2 |
| `04_horner_load.s` | 12 | 6 | 15 | 15 | 15 | 0 |

Observations:

- On these small snippets, the greedy scheduler already hits the lower bound, so TINY Flash does not shorten makespan — its value shows up on larger, irregular graphs. At 9–19 operations, TINY Flash is slightly slower than greedy (tenths of a millisecond).
- Handwritten schedules 02–04 are 1.3–2.5× shorter than the valid minimum because results are read before they are ready. For example, in `04` a load has latency 5 cycles, yet its result is consumed in cycle 1.
- `muls,2` in 01–03 is an invalid channel: multiply executes on `,0 ,1 ,3 ,4` (verified against the assembler, see `docs/ISA.md`).
- `cmples` and `cmpgts` in 03 are unknown mnemonics and fall into `UNKNOWN` (latency 1, any channel). That is a placeholder, not a measurement.

Model numbers: `MUL` — latency 4, channels `,0 ,1 ,3 ,4`; `LOAD` — latency 5; `ADD`/`SUB` — 1. Profile `e2k-v6-measured`, 6 ports.
