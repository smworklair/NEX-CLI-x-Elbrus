# Probes Used to Measure the Machine Model

This directory contains the C sources and **real** `lcc` output used to populate the port matrix and latencies in [`vliw/core/model.py`](../../vliw/core/model.py). Nothing has been hand-edited: every `.s` file is verbatim compiler output.

Compiler: cross-`lcc` from MCST's publicly distributed toolchain (`cross-sp-public-osl-1.29.16.e2k-v6`), running on an x86 host:

```bash
LCC=~/e2k-toolchain/opt/mcst/lcc-1.29.16.e2k-v6.linux-6.1/bin.toolchain/e2k-linux-lcc
$LCC -fverbose-asm -S -O3 probe.c -o probe.s
```

## What Each Probe Measures

| file | what it measures | how to read |
|---|---|---|
| `probe.c/.s` | initial probe: 4 divisions + 4 multiplies | **historical**: this is the one that was misread; see below |
| `mul8.c/.s` | 8 independent multiplies | bundle `<0013>` has `muls,0` and `muls,1` — more than one multiplier |
| `mul_burst.c/.s` | 16 independent multiplies | issued back-to-back every cycle → port is free immediately, occupancy = 1 |
| `mul_latency.c/.s` | chain `x = x * b` | spacing between bundles = **4** → `MUL` latency |
| `div_latency.c/.s` | chain `x = x / b` | spacing = **11** → `DIV` latency |
| `div8.c/.s` | 8 independent divisions | spacing = **2** → divider accepts a new division every 2 cycles |
| `load_latency.c/.s` | chain `p = *p` | spacing = **5** → `LOAD` latency (not 2) |
| `store_burst.c/.s` | 16 independent stores to distinct addresses | spacing = **1** → `STORE` channel occupancy = 1 |
| `store_latency.c/.s` | chain `mem = x; x = mem + 1;` through ONE volatile cell | store→load spacing = **2** → store visibility latency (not 1) |

General technique: **latency** is measured with a chain of DEPENDENT operations (the compiler must space them by at least the latency), while **issue rate** is measured with a stream of INDEPENDENT operations (spacing between consecutive issues). `volatile` prevents constant folding.

## Port Matrix: Ask the Assembler, Not the Scheduler

The main lesson from these probes: a compiler listing shows what the compiler **chose** to do, not what the hardware **can** do. The first version of the model was built from `probe.c`, where all four `muls` landed sequentially on `,0` — which was misread as "one multiplier holding its port for 8 cycles". In reality, four operations simply weren't enough to push `lcc`'s greedy scheduler onto a second channel.

The reliable method is to assemble a tiny `.s` placing an operation in a specific channel and see if the **assembler** accepts it:

```bash
$LCC -c one_muls_2.s -o /dev/null
# Error: `muls' cannot be encoded in ALC2
```

That produced the matrix below (all 6 channels probed for each operation):

| operation | channels | latency | rate |
|---|---|---|---|
| `adds` / `subs` / `ands` / `shls` | `,0 ,1 ,2 ,3 ,4 ,5` | 1 | 1/cyc |
| `muls` / `muld` | `,0 ,1 ,3 ,4` | 4 | 1/cyc |
| `sdivs` | `,5` — exclusive | 11 | 1 per 2 cyc |
| `ldw` / `ldd` | `,0 ,2 ,3 ,5` | 5 | 1/cyc |
| `stw` / `std` | `,2 ,5` | 2 | 1/cyc |

Store previously had a dash for latency — "nobody consumes the result" sounded conclusive, but that only applies to register consumers. `store_latency.c` probes the machine differently: through ONE `volatile` cell written and immediately read eight times in a row. `volatile` forbids reordering the store and load or eliminating the memory access, so the store→load spacing in the listing reflects forced store visibility rather than scheduler choice. It came out to **2 cycles**, not the assumed 1.

`STORE` channel occupancy was confirmed twice, the second time more strongly than any compiler listing: using the same technique as the port matrix, `tools/probe_matrix.py` asked the assembler directly whether `stw,2` and `stw,5` encode in the SAME wide instruction. They do. Thus the store port is not shared across both channels and does not block itself even within a single cycle — no compiler behavior involved, just hardware encoding rules.

An essential caveat: **2 cycles is the latency of "store followed by load from the SAME address"**, not "latency of STORE in general". In the synthetic graph generator (`tools/vliw_gen.py`), an edge from `STORE` to another op is structural and not tied to a real address: it does not verify that a random child of `STORE` actually reads the same cell. 2 is the best measured order-of-magnitude estimate — better than the earlier assumption of 1 — though not as airtight as `LOAD`/`MUL`/`DIV` latency where the consumer is literally the next op in the chain.

Four `muls` in a single wide instruction (channels `,0 ,1 ,3 ,4`) assemble cleanly — so there is no encoding-level restriction of "at most two multiplies at once".

The machine's only true monopoly is the **divider**. That is what remains in the model as the source of the gap between greedy heuristics and the optimum.

## Re-Check (2026-08-24): `volatile` in Probes and What It Distorted

All probes here were written with `volatile` to stop constant folding. It turned out `volatile` also alters what we observe: `volatile` accesses cannot be reordered or combined, so `lcc` paces them one per cycle and everything fed by them inherits that cadence.

Re-tested by compiling the same kernels WITHOUT `volatile` (values passed by pointer into an `__attribute__((noinline))` function — prevents folding while allowing reordering) using the same `lcc-1.29.16 -O3`:

| observation | with `volatile` | without `volatile` |
|---|---|---|
| loads in one wide instruction | 1 | **4** |
| load channels | `,0 ,2` | **`,0 ,2 ,3 ,5`** |
| multiplies in one wide instruction | 1 | **2** |
| multiply channels | 15 of 16 on `,0` | `,0 ,1 ,4` |

So the `volatile` probes misrepresented **packing**: the compiler can pack wide instructions densely; `volatile` just prevented it from doing so.

### What Was NOT Affected — Issue Rate (`occupancy`)

The key question was whether `occupancy` measured from those streams was overstated. Spacing between consecutive issues of the SAME operation type on the SAME channel:

| operation | with `volatile` | without `volatile` | in model |
|---|---|---|---|
| `sdivs` on `,5` | 2 cyc | **2 cyc** | `occupancy=2` ✔ |
| `muls` on its channel | 1 cyc | **1 cyc** | `occupancy=1` ✔ |
| `ldw` on its channel | 1 cyc | **1 cyc** | `occupancy=1` ✔ |

Without `volatile`, divisions landed in cycles 5, 7, 9, 11, 13, 15, 17, 19 — the exact same stride of 2 as in the volatile probe (12, 14, …, 26). **All rate parameters are confirmed**: the rule "divider holds `,5` for two cycles" holds, and nothing in `model.py` needs to change.

The sole difference: `stw` in volatile `div8.s` had stride 2, whereas without `volatile` it has stride 1. `STORE` already had `occupancy=1` in the model, so no numbers changed.

### Takeaway

`volatile` prevents constant folding but distorts scheduling. For latencies and issue rates it is harmless (those depend on spacing between dependent ops or same-type ops on one port), but for observing **packing** it is invalid. This is a second instance of the same pitfall: first the model erred because four ops weren't enough for the greedy scheduler, then because `volatile` blocked packing. Compiler output shows what the compiler wanted and was allowed to do, not what the hardware can do.

Re-check sources: `mul8_novolatile.c`, `div8_nv.c`, `mulburst_nv.c` (not yet committed to the repo — see TODO below).

## Combinations: A Second Class of Constraints Missing from the Model

The port matrix answers "can this op execute in this channel?" one operation at a time. That isn't everything the assembler enforces. Using the same technique, we can probe **pairs**: assemble a wide instruction with two individually valid operations and check if the assembler accepts it.

Exhaustive pair probing (`tools/probe_matrix.py`, also `python -m vliw verify`) finds exactly **two** prohibitions:

```
Error: the combination of STORE in ALC2 with LOAD in ALC3 is prohibited
Error: the combination of STORE in ALC5 with LOAD in ALC0 is prohibited
```

All other 117 combinations are valid — including `STORE,2 + LOAD,0`, `STORE,2 + LOAD,5`, `STORE,5 + LOAD,2`, and `STORE,5 + LOAD,3`. So the ban is not "store plus load in general", but specifically these two channel pairs.

`e2k` channels split into two clusters: `,0 ,1 ,2` and `,3 ,4 ,5`. The forbidden pairs — `(2,3)` and `(5,0)` — are the exact "seams": the last channel of one cluster paired with the first channel of the other (the second seam wraps around). **Machine clustering exists and is observable — here it shows up as a structural prohibition inside a wide instruction rather than an inter-cluster latency.**

### Why Inter-Cluster LATENCY Cannot Be Measured This Way

It is tempting to measure clusters the same way as latencies — with a dependent chain. That does not work, and here is why (verified, not assumed):

1. **The assembler does not check latencies at all.** It has a `-no_strict_delay` flag ("don't enforce implicit delay between instructions"), and `lcc` even emits `.ignore strict_delay`. Yet a dependent pair in adjacent cycles — `muls,0 … %g18` followed immediately by `adds,1 %g18, …` — assembles without complaint. Removing `.ignore strict_delay` from real `lcc` output changes nothing either. The assembler does not track register dependencies, so querying it for latency is pointless.
2. **You cannot force the compiler to pick a cluster.** From `.c`, channels cannot be assigned — `lcc`'s scheduler picks them. To see a difference between an intra-cluster dependent pair and a cross-cluster one, you would need to PIN both operations to specific channels, and C provides no such lever. In the probed chains, the compiler placed all dependent `muls` inside one cluster (channels `,0` and `,1`), so cross-cluster pairs never appear in the data.

Conclusion: inter-cluster latency **cannot be measured** with the local toolchain — neither via the assembler (doesn't check) nor via the compiler (uncontrollable). Putting it into the model "from documentation" would repeat the exact mistake that forced the creation of `e2k-v6-firstprobe`.

### Status: Measured, Not Wired Into the Model

`vliw/core/model.py` currently represents machine resources as a "port → operations" matrix. Pair prohibitions are **not** in it, and no scheduler enforces them. This divergence is intentional and tracked: `probe_matrix.py` prints it on every run, and `EXPECTED_COMBO_BANS` in that file guards against silent changes in the prohibition set.

Wiring it into the model is separate, non-trivial work: exact search in `vliw/core/oracle.py` relies on "a bipartite matching exists ⟺ the bundle is issuable in this cycle", and pair prohibitions break that property. It is constructively fixable (there are at most two stores per cycle — matching the two store ports — so you can enumerate store placements and mask out forbidden load channels before running standard matching), but it requires modifying the optimality proof core and re-verifying via `/selfcheck` on the new profile.
