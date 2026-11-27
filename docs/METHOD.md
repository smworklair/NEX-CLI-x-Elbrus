# Methodology and Boundaries

> Stage 3 of 13 · [← CLI](CLI.md) · [Roadmap](README.md) · [CODE Mode →](CODE_MODE.md)

One page on where the numbers come from and where they should not be trusted. If you have worked with `lcc` and Elbrus VLIW bundles, this is enough to decide whether the model fits your needs.

## What Is Computed

Cycle counts in the `e2k-v6-measured` machine model, not physical hardware measurements. The model defines 24 operation classes, 160 annotated mnemonics, and six issue slots (`ALC0…ALC5`, assembly syntax `,0`..`,5`).

Three scheduling parameters are defined per operation:

- **issue slots (channels)** — which functional units (`ALC0…ALC5`) can encode and execute it;
- **latency** — cycles until the result is ready for a consumer without a RAW (read-after-write) latency hazard;
- **occupancy** — cycles the functional unit remains reserved (initiation interval).

## Where the Numbers Come From

| property | how obtained | reliability |
|---|---|---|
| issue slots (channels) | queried from the `lcc` assembler: illegal slot assignments are rejected | measured for all classes |
| latency | VLIW bundle spacing in dependent chains, `lcc -O3` | 11 of 24 classes |
| occupancy | issue spacing in independent streams | some classes; remainder assumed |
| pair prohibitions | exhaustive probe of 119 pairs against the assembler | 2 prohibitions: `(2,3)` and `(5,0)` |

For the remaining 13 classes, latency defaults to 1 cycle as an explicit assumption — each is flagged in [`ISA.md`](ISA.md).

One key distinction: a compiler listing shows what the compiler **chose** to schedule, not what the hardware **can** issue. That is why the issue-slot matrix was probed directly from the assembler rather than inferred from compiler output.

## Cross-Check Against the MCST Guide

Source: "Guide to Efficient Programming on the Elbrus Platform", release 1.2 (2024-02-28), Section 6.1 — [mcst.ru/elbrus_prog](http://www.mcst.ru/elbrus_prog). The guide covers E4C/E8C while the model targets `e2k-v6`, so its numbers are not substituted into the model: this is an independent cross-check, not a data source.

- Matched on **10 of 13** comparable classes.
- Divergences: `LOAD` — 5 vs. 3 (generational difference, confirmed by two independent probes), `COMBO` — 1 vs. 2, `PRED` — 1 vs. 0.5…3.

## What Is Not Modeled

- **Physical hardware.** Latencies were inferred from `lcc` scheduling behavior, not hardware performance counters.
- **`loop_mode`.** Software-pipelined loops are not modeled.
- **Inter-cluster delays** (1 / 2 / 3–4 cycles) and the `fp→int +2` cross-domain penalty: these depend on producer–consumer pairs, whereas the model stores a single scalar latency per operation.
- **Pair prohibitions `(2,3)` and `(5,0)`.** They are measured (see `vliw/core/isa.py`), but intentionally not enforced in the scheduler: turning them on would alter the machine model and invalidate prior benchmark comparisons.

## What This Means for the Numbers

On real `lcc` output, **37% of operations** land in `UNKNOWN`: the mnemonic is absent from the dictionary, so it defaults to 1-cycle latency on any issue slot. For those basic blocks, DAG topology is intact, but cycle counts are not. As noted in [`REAL_VS_SYNTH.md`](REAL_VS_SYNTH.md): "graph structure — roughly right; timings — no".

Comparisons evaluate the greedy list scheduler, TINY AI, and the exact branch-and-bound oracle **within the same machine model**. The schedule emitted by `lcc` itself is not benchmarked as a separate baseline.

## Verify Locally

```bash
python -m vliw isa --out docs/ISA.md     # regenerate the ISA table
python -m vliw run slotclash             # run a single scenario
python -m vliw all                       # run all 17 scenarios
python3 tools/check_real_vs_synth.py     # real code vs. synthetic
```

Probes and their descriptions live in `examples/probes/`.

This project is not affiliated with MCST. `lcc` was not modified and only the public toolchain is used; the codebase is source-available: free for educational and personal use, with commercial use requiring a separate agreement (see [`../LICENSE`](../LICENSE)).
