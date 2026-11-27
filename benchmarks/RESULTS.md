# e2k Snippet Benchmark

Machine profile: `e2k-v6-measured` (6 ports). Exact search budget: 1.5 s per file.

| file | N | orig | baseline | TINY Flash | oracle | optimal | UNKNOWN | errors |
|---|---:|---:|---:|---:|---:|---|---:|---:|
| `01_mul_latency.s` | 15 | 12 | 8 | 8 | 8 | yes | 0 | 4 |
| `02_software_pipeline.s` | 19 | 7 | 9 | 9 | 9 | yes | 0 | 14 |
| `03_predication.s` | 9 | 3 | 8 | 8 | 8 | yes | 2 | 10 |
| `04_horner_load.s` | 12 | 6 | 15 | 15 | 15 | yes | 0 | 8 |

`orig` is the schedule length as written in the file. It may be shorter
than the valid minimum: the linter flags reads issued before producer
latency elapses. `baseline`, `TINY Flash`, and `oracle` reschedule from
scratch using the dependency DAG and machine model.

## Details

### `01_mul_latency.s`

- Lower bound: 8 (resources); critical path 7, resources 8.
- Time: baseline 0.382 ms, TINY Flash 1.588 ms, oracle 1.0 ms.
- Compiler schedule not reconstructed: channel layout conflicts with machine model
- Linter diagnostics:
  - line 5: muls on channel ,2 — unsupported channel for MUL
  - line 6: channel ,3 in cycle 0 is already busy: muls on line 5
  - line 11: muls on channel ,2 — unsupported channel for MUL
  - line 12: channel ,3 in cycle 1 is already busy: muls on line 11

### `02_software_pipeline.s`

- Lower bound: 9 (resources); critical path 8, resources 9.
- Time: baseline 0.36 ms, TINY Flash 0.479 ms, oracle 0.7 ms.
- Compiler schedule not reconstructed: channel layout conflicts with machine model
- Linter diagnostics:
  - line 6: muls on channel ,2 — unsupported channel for MUL
  - line 7: channel ,3 in cycle 0 is already busy: muls on line 6
  - line 13: muls on channel ,2 — unsupported channel for MUL
  - line 14: channel ,3 in cycle 1 is already busy: muls on line 13
  - line 20: %r20 read in cycle 2, but muls on line 4 produces it only in cycle 4
  - line 20: %r21 read in cycle 2, but muls on line 5 produces it only in cycle 4

### `03_predication.s`

- Lower bound: 8 (both); critical path 8, resources 8.
- Time: baseline 0.212 ms, TINY Flash 0.276 ms, oracle 0.4 ms.
- Compiler schedule not reconstructed: channel layout conflicts with machine model
- UNKNOWN: 2 ops (`cmples`, `cmpgts`) — latency 1 and any channel (placeholder, not measured).
- Linter diagnostics:
  - line 6: muls on channel ,2 — unsupported channel for MUL
  - line 7: channel ,3 in cycle 0 is already busy: muls on line 6
  - line 11: %r20 read in cycle 1, but muls on line 6 produces it only in cycle 4
  - line 11: %r21 read in cycle 1, but muls on line 7 produces it only in cycle 4
  - line 12: %r20 read in cycle 1, but muls on line 6 produces it only in cycle 4
  - line 12: %r21 read in cycle 1, but muls on line 7 produces it only in cycle 4

### `04_horner_load.s`

- Lower bound: 15 (both); critical path 15, resources 15.
- Time: baseline 0.298 ms, TINY Flash 0.358 ms, oracle 0.6 ms.
- Compiler schedule not reconstructed: 8 issues, first: r40 issued in cycle 1, but operand r20 is not ready until cycle 5. Common cause on -O3 code is a software-pipelined loop: values carry from the previous iteration while the parser reads the block linearly
- Linter diagnostics:
  - line 10: %r20 read in cycle 1, but ldw on line 3 produces it only in cycle 5
  - line 13: %r40 read in cycle 2, but muls on line 10 produces it only in cycle 5
  - line 13: %r21 read in cycle 2, but ldw on line 4 produces it only in cycle 5
  - line 17: %r31 read in cycle 3, but muls on line 14 produces it only in cycle 6
  - line 18: %r22 read in cycle 3, but ldw on line 8 produces it only in cycle 6
  - line 21: %r43 read in cycle 4, but muls on line 18 produces it only in cycle 7

