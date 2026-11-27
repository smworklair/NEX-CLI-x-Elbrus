# Elbrus e2k-v6: Operation Costs

> Stage 10 of 13 · [← TINY AI](TINY.md) · [Roadmap](README.md) · [Real vs. Synthetic →](REAL_VS_SYNTH.md)

Profile `e2k-v6-measured`: 24 operation classes, 160 annotated mnemonics.
Generated from `vliw/core/model.py`; verify and regenerate via `python -m vliw isa --out docs/ISA.md`.

## What This Is and What It Isn't

This is a machine-model cost table, not an ISA reference manual. There are no encodings, operand formats, or semantics here — only scheduling parameters: which issue slots (functional units / channels `ALC0`..`ALC5`, written `,0`..`,5` in `e2k` assembly) an operation can target, its RAW (read-after-write) latency, and how many cycles it occupies its functional unit.

The official "Elbrus Platform Efficient Programming Guide" (CC BY 4.0) covers E4C/E8C processors and reports latencies by class. The toolchain here targets `e2k-v6` — a later microarchitecture, so timings diverge. Moreover, latencies here are keyed by mnemonic, and every measured value is locally reproducible.

## How to Read the Table

| column | meaning |
|---|---|
| **channels** | VLIW bundle issue slots (`ALC0`..`ALC5`, assembly syntax `,0`..`,5`) where the operation can execute — the direct analogue of Intel execution ports or Hexagon issue slots |
| **latency** | cycles until the result is visible to a consumer: issuing a dependent operation earlier than `t + latency` creates a RAW (read-after-write) latency hazard |
| **occupancy** | cycles the operation exclusively reserves its functional unit (initiation interval). `1` means the unit is fully pipelined and accepts another operation on the next cycle |
| **peak/cyc** | issue slots ÷ occupancy: peak throughput per cycle (equivalent to reciprocal throughput in Agner Fog's tables) |
| **source** | provenance of the latency figure. Note that latency is empirically measured for 11 of 24 classes |

## Summary Table

Ordered from narrowest to widest resource classes: tightest functional-unit bottlenecks first, because that is where scheduling pressure and cycle loss originate.

| class | channels | latency | occupancy | peak/cyc | mnemonics | latency source |
|---|---|---:|---:|---:|---:|---|
| `FDIV` | `5` | 14 | 2 | 0.5 | 2 | measured (dependent chain, lcc -O3) |
| `DIV` | `5` | 11 | 2 | 0.5 | 6 | measured (dependent chain, lcc -O3) |
| `RW` | `0` | 1 | 1 | 1.0 | 2 | **assumption** |
| `STORE` | `2,5` | 2 | 1 | 2.0 | 6 | measured (dependent chain, lcc -O3) |
| `AAU` | `2,5` | 1 | 1 | 2.0 | 11 | **assumption** |
| `COMBO` | `1,4` | 1 | 1 | 2.0 | 6 | **assumption** |
| `MOVAQ` | `0,2` | 1 | 1 | 2.0 | 1 | **assumption** |
| `PACK` | `0,3` | 1 | 1 | 2.0 | 22 | **assumption** |
| `LOAD` | `0,2,3,5` | 5 | 1 | 4.0 | 8 | measured (dependent chain, lcc -O3) |
| `CONV` | `0,1,3,4` | 4 | 1 | 4.0 | 12 | measured (dependent chain, lcc -O3) |
| `MUL` | `0,1,3,4` | 4 | 1 | 4.0 | 5 | measured (dependent chain, lcc -O3) |
| `INSF` | `0,1,3,4` | 1 | 1 | 4.0 | 2 | **assumption** |
| `MOVA` | `0,1,2,3` | 1 | 1 | 4.0 | 5 | **assumption** |
| `PACKLOG` | `0,1,3,4` | 1 | 1 | 4.0 | 11 | **assumption** |
| `PRED` | `0,1,3,4` | 1 | 1 | 4.0 | 12 | **assumption** |
| `FMA` | `0,1,2,3,4,5` | 8 | 1 | 6.0 | 6 | measured (dependent chain, lcc -O3) |
| `FADD` | `0,1,2,3,4,5` | 4 | 1 | 6.0 | 7 | measured (dependent chain, lcc -O3) |
| `FMUL` | `0,1,2,3,4,5` | 4 | 1 | 6.0 | 4 | measured (dependent chain, lcc -O3) |
| `ADD` | `0,1,2,3,4,5` | 1 | 1 | 6.0 | 8 | measured (dependent chain, lcc -O3) |
| `AND` | `0,1,2,3,4,5` | 1 | 1 | 6.0 | 7 | **assumption** |
| `INCR` | `0,1,2,3,4,5` | 1 | 1 | 6.0 | 1 | **assumption** |
| `MERGE` | `0,1,2,3,4,5` | 1 | 1 | 6.0 | 4 | **assumption** |
| `SHL` | `0,1,2,3,4,5` | 1 | 1 | 6.0 | 8 | **assumption** |
| `SUB` | `0,1,2,3,4,5` | 1 | 1 | 6.0 | 4 | measured (dependent chain, lcc -O3) |

Sole-issue functional-unit classes (single-slot bottlenecks): `FDIV`, `DIV`, `RW`. This is where non-trivial scheduling difficulty originates — two operations in the same sole-issue class can never co-issue in the same VLIW bundle.

## Classes and Mnemonics

### `FDIV` — 5

Latency **14** (measured (dependent chain, lcc -O3)), channel occupancy **2** (measured (independent stream, lcc -O3)), peak **0.5** ops/cycle.

```
fdivd fdivs
```

### `DIV` — 5

Latency **11** (measured (dependent chain, lcc -O3)), channel occupancy **2** (measured (independent stream, lcc -O3)), peak **0.5** ops/cycle.

```
divd divs sdivd sdivs udivd udivs
```

### `RW` — 0

Latency **1** (assumption), channel occupancy **1** (assumption), peak **1.0** ops/cycle.

```
rwd rws
```

### `STORE` — 2,5

Latency **2** (measured (dependent chain, lcc -O3)), channel occupancy **1** (measured (independent stream, lcc -O3)), peak **2.0** ops/cycle.

```
stapq stb std sth stqp stw
```

### `AAU` — 2,5

Latency **1** (assumption), channel occupancy **1** (assumption), peak **2.0** ops/cycle.

```
aaurr aaurrd aaurw aaurwd mmurr mmurw staab staad
staah staaq staaw
```

### `COMBO` — 1,4

Latency **1** (assumption), channel occupancy **1** (assumption), peak **2.0** ops/cycle.

```
getf_addd getf_adds shl_addd shl_adds shr_addd shr_adds
```

### `MOVAQ` — 0,2

Latency **1** (assumption), channel occupancy **1** (assumption), peak **2.0** ops/cycle.

```
movaq
```

### `PACK` — 0,3

Latency **1** (assumption), channel occupancy **1** (assumption), peak **2.0** ops/cycle.

```
paddb paddd paddh paddw pcmpeqw pcmpgtw pmaxsw pminsw
psubb psubd psubh psubw qpaddb qpaddd qpaddh qpaddw
qpcmpgtw qpmaxsw qpminsw qppackdl qpsubw qpswitchd
```

### `LOAD` — 0,2,3,5

Latency **5** (measured (dependent chain, lcc -O3)), channel occupancy **1** (measured (independent stream, lcc -O3)), peak **4.0** ops/cycle.

```
ldapq ldb ldd ldgdd ldgdw ldh ldqp ldw
```

### `CONV` — 0,1,3,4

Latency **4** (measured (dependent chain, lcc -O3)), channel occupancy **1** (assumption), peak **4.0** ops/cycle.

```
fdtofs fdtoid fdtois fdtoistr fstofd fstoid fstois fstoistr
idtofd idtofs istofd istofs
```

### `MUL` — 0,1,3,4

Latency **4** (measured (dependent chain, lcc -O3)), channel occupancy **1** (measured (independent stream, lcc -O3)), peak **4.0** ops/cycle.

```
muld muls mulw umuld umuls
```

### `INSF` — 0,1,3,4

Latency **1** (assumption), channel occupancy **1** (assumption), peak **4.0** ops/cycle.

```
insfd insfs
```

### `MOVA` — 0,1,2,3

Latency **1** (assumption), channel occupancy **1** (assumption), peak **4.0** ops/cycle.

```
movab movad movah movaqp movaw
```

### `PACKLOG` — 0,1,3,4

Latency **1** (assumption), channel occupancy **1** (assumption), peak **4.0** ops/cycle.

```
pand por psllw psrlw pxor qpand qpor qpsllw
qpsraw qpsrlw qpxor
```

### `PRED` — 0,1,3,4

Latency **1** (assumption), channel occupancy **1** (assumption), peak **4.0** ops/cycle.

```
cmpanddb cmpandedb cmpandesb cmpandsb cmpbdb cmpbsb cmpedb cmpesb
cmpldb cmpledb cmplesb cmplsb
```

### `FMA` — 0,1,2,3,4,5

Latency **8** (measured (dependent chain, lcc -O3)), channel occupancy **1** (verified by assembler (ALC encoding)), peak **6.0** ops/cycle.

```
fmul_addd fmul_adds fmul_rsubd fmul_rsubs fmul_subd fmul_subs
```

### `FADD` — 0,1,2,3,4,5

Latency **4** (measured (dependent chain, lcc -O3)), channel occupancy **1** (measured (independent stream, lcc -O3)), peak **6.0** ops/cycle.

```
faddd fadds fsubd fsubs pfaddd pfadds pfsubs
```

### `FMUL` — 0,1,2,3,4,5

Latency **4** (measured (dependent chain, lcc -O3)), channel occupancy **1** (measured (independent stream, lcc -O3)), peak **6.0** ops/cycle.

```
fmuld fmuls pfmuld pfmuls
```

### `ADD` — 0,1,2,3,4,5

Latency **1** (measured (dependent chain, lcc -O3)), channel occupancy **1** (measured (independent stream, lcc -O3)), peak **6.0** ops/cycle.

```
addd adds addw incd incs movtd movts sxt
```

### `AND` — 0,1,2,3,4,5

Latency **1** (assumption), channel occupancy **1** (assumption), peak **6.0** ops/cycle.

```
andd andns ands ord ors xord xors
```

### `INCR` — 0,1,2,3,4,5

Latency **1** (assumption), channel occupancy **1** (assumption), peak **6.0** ops/cycle.

```
incr
```

### `MERGE` — 0,1,2,3,4,5

Latency **1** (assumption), channel occupancy **1** (assumption), peak **6.0** ops/cycle.

```
getfd getfs merged merges
```

### `SHL` — 0,1,2,3,4,5

Latency **1** (assumption), channel occupancy **1** (assumption), peak **6.0** ops/cycle.

```
sard sars scls scrs shld shls shrd shrs
```

### `SUB` — 0,1,2,3,4,5

Latency **1** (measured (dependent chain, lcc -O3)), channel occupancy **1** (measured (independent stream, lcc -O3)), peak **6.0** ops/cycle.

```
decs subd subs subw
```

## Prohibited VLIW Bundle Combinations

The issue-slot matrix answers legality for one operation in isolation. The same probing technique extends to pairs: assemble a VLIW bundle containing two individually legal operations and check whether the assembler accepts it. Exhaustive probing reveals exactly 2 structural prohibitions:

```
Error: the combination of STORE in ALC2 with LOAD in ALC3 is prohibited
Error: the combination of STORE in ALC5 with LOAD in ALC0 is prohibited
```

Every other pair is legal — including `STORE,2 + LOAD,0` and `STORE,5 + LOAD,3`. The restriction is not "store co-issued with load", but specifically these two issue-slot pairs: `(2,3)` and `(5,0)`.

Those are the boundaries between clusters `,0 ,1 ,2` and `,3 ,4 ,5`. **Machine clustering is real and observable — here it manifests as an intra-bundle structural hazard rather than an inter-cluster bypass latency.** Inter-cluster latency itself cannot be extracted from the local toolchain alone, and that limitation was verified rather than assumed.

## Cross-Check Against Official MCST Documentation

Source: "Guide to Efficient Programming on the Elbrus Platform", release 1.2 (2024-02-28), CC BY 4.0, Section 6.1 — [mcst.ru/elbrus_prog](http://www.mcst.ru/elbrus_prog). Numbers from that guide were NOT substituted into the model — this is an independent cross-check, not a data source: the guide describes E4C/E8C, whereas the model targets `e2k-v6`.

| class | measured here | MCST guide | name in guide | verdict |
|---|---:|---:|---|---|
| `FDIV` | 14 | 14 | Fdivd — 64-bit | **match** (measured and confirmed) |
| `DIV` | 11 | 11 | Fdivs — 32-bit | **match** (measured and confirmed) |
| `COMBO` | 1 | 2 | Int_combined | assumption here; guide gives different value |
| `LOAD` | 5 | 3 | Ld L1 hit (L2 — 11, L3 — 40, RAM — ~100) | **divergence** |
| `MUL` | 4 | 4 | Fp (integer multiply grouped under Fp) | **match** (measured and confirmed) |
| `PRED` | 1 | 0.5…3 | logic->logic 0.5, Cmp->logic 1, ->qual 2, ->ct 3 | assumption here; guide gives different value |
| `FMA` | 8 | 8 | Fp_combined | **match** (measured and confirmed) |
| `FADD` | 4 | 4 | Fp | **match** (measured and confirmed) |
| `FMUL` | 4 | 4 | Fp | **match** (measured and confirmed) |
| `ADD` | 1 | 1 | Int, Bitwise | **match** (measured and confirmed) |
| `AND` | 1 | 1 | Int, Bitwise | assumption confirmed by guide |
| `SHL` | 1 | 1 | Int, Bitwise | assumption confirmed by guide |
| `SUB` | 1 | 1 | Int, Bitwise | **match** (measured and confirmed) |

Matched on **10** classes, diverged on **3**.

**`LOAD`: 5 vs. 3 is a generational difference, not a measurement bug.** The guide lists 3 cycles for an L1 hit on E4C/E8C. Measuring real `lcc -O3` output for `e2k-v6` yields 5: across 36 dependent pairs the minimum bundle spacing is 5, with twelve pairs at exactly 5. Confirmed via both address chains (`load_latency.c`) and data-consumption chains (`load_data_latency.c`) — both yield 5. The model reflects the microarchitecture the toolchain actually compiles for.

**What the guide documents that the model omits.** Both effects depend on a producer–consumer PAIR rather than a single operation, so they cannot be encoded as a scalar in `OpClass.latency`:

* cross-domain transfer penalty between integer and floating-point pipes: `fp→int` +2 cycles. The guide cites an explicit example: "latency from `muls` to `add` is 6 cycles: 4 of its own latency plus 2 for the transfer";
* inter-cluster bypass delays (Chapter 12): 1 cycle via same-cluster bypass, 2 cycles across clusters, 3–4 cycles through the register file. Clusters `,0 ,1 ,2` and `,3 ,4 ,5` are called out explicitly in the guide.

This is a deliberate simplification of the machine model, not an oversight: see `OpClass.occupancy`, where the same scalar abstraction is documented for functional-unit reservation cycles.

## Methodology

Every parameter was derived externally, without an official ISA manual, using three techniques of differing evidential strength.

**Issue slots (channels) — queried from the assembler.** Assemble a minimal `.s` stub placing an operation in a specific channel (`,0`..`,5`); if illegal, the assembler rejects it with `cannot be encoded in ALCn`. Sweeping all six slots yields one row of the capability matrix. This is the strongest of the three methods: hardware encoding rules answer directly through the assembler rather than indirectly through compiler heuristics.

**Latency — dependent-operation chain.** `x = x * b` in a loop: the compiler must space consecutive multiplies by at least their RAW latency, and the bundle-to-bundle delta in the listing exposes it.

**Issue rate (occupancy) — independent-operation stream.** Sixteen independent multiplies in a row: the spacing between issues reveals how many cycles elapse before the functional unit accepts the next operation.

**What cannot be inferred from compiler listings.** A compiler listing shows what the compiler *chose* to schedule, not what the hardware *can* issue. The first version of this model was built from a listing where four multiplies landed sequentially on a single channel — misread as "only one multiplier." In reality, four operations were simply not enough to push the greedy list scheduler onto a second functional unit. Hence the rule: issue-slot matrices must come exclusively from the assembler.

## What Has Not Been Measured

Latency is measured for **11** of **24** classes. The remaining 13 use 1 cycle as a placeholder assumption, not an empirical measurement:

| class | channels | mnemonics | what needs measuring |
|---|---|---:|---|
| `RW` | `0` | 2 | latency via dependent chain |
| `AAU` | `2,5` | 11 | latency via dependent chain |
| `COMBO` | `1,4` | 6 | latency via dependent chain |
| `MOVAQ` | `0,2` | 1 | latency via dependent chain |
| `PACK` | `0,3` | 22 | latency via dependent chain |
| `INSF` | `0,1,3,4` | 2 | latency via dependent chain |
| `MOVA` | `0,1,2,3` | 5 | latency via dependent chain |
| `PACKLOG` | `0,1,3,4` | 11 | latency via dependent chain |
| `PRED` | `0,1,3,4` | 12 | latency via dependent chain |
| `AND` | `0,1,2,3,4,5` | 7 | latency via dependent chain |
| `INCR` | `0,1,2,3,4,5` | 1 | latency via dependent chain |
| `MERGE` | `0,1,2,3,4,5` | 4 | latency via dependent chain |
| `SHL` | `0,1,2,3,4,5` | 8 | latency via dependent chain |

The methodology is established and documented above — only physical silicon is missing. If you have access to an Elbrus machine, running a dependent chain for each class and inspecting bundle spacing closes this gap completely.

Issue-slot legality, by contrast, is measured for every class without exception: the assembler validates encodings locally, with no hardware required.
