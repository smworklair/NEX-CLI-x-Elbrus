# Fast Tiny Schedulers, Block Mode, and the Real-Code Benchmark Set

Everything described here consists of **new files**. Existing code is untouched; the
behavior of `/tiny`, the agent, and the tests is unchanged. Two optional edits to
existing files (enabling the fast scheduler in the product; adding five symbols to
`_SYMBOL`) are described in §7 and **not applied**.

In brief:

- `TinyFastScheduler` produces the **exact same cycles** as `TinyScheduler`, 24–80×
  faster (3,061 graphs, 0 discrepancies). A ~25-op graph from real code takes ~1 ms —
  roughly one greedy pass; a 50–100-op block takes 4–14 ms.
- The speed came not from training, but from search mechanics (§2). Reward and weights
  have no effect on runtime.
- `tools/block_report.py` and `vliw/core/blocks.py` — block mode: `.s` is split into
  basic blocks, each with its own DAG.
- `eval_real.jsonl` — 947 graphs of real `lcc` code with a **proven** optimum, in the
  same format as `eval_hard.jsonl`; built by `tools/make_eval_real.py`.
- On real code, greedy is already optimal on 94% of graphs, and an ideal scheduler beats
  it by 0.51% of model cycles (§6). That is the main takeaway of the measurements.

## 1. File map

| File | Purpose |
|---|---|
| `vliw/core/fastlist.py` | `ListPlan` — list scheduler bit-identical to `baseline.list_schedule`, without redundant work |
| `vliw/tiny/fast.py` | `TinyFastScheduler`, `FastNet` (network inference with identical numbers) |
| `vliw/core/blocks.py` | splitting `.s` into basic blocks and windows inside blocks |
| `tools/tiny_fast_check.py` | verification against `TinyScheduler` + timings; exit code 1 on any mismatch |
| `tools/block_report.py` | block-level report: greedy → tiny → exact search → `lcc` |
| `tools/make_eval_real.py` | builds `eval_real.jsonl` / `eval_real_open.jsonl` from `.s` |
| `eval_real.jsonl`, `eval_real_open.jsonl` | datasets (§5) |
| `tests/test_fastlist.py`, `test_tiny_fast.py`, `test_blocks.py`, `test_make_eval_real.py` | tests |

## 2. Where the speed comes from

`TinyScheduler` runs a portfolio of groups (`bh`, `rule`, `bt`, `prio`, `hold`,
`defer`), evaluates each to completion, and picks the best makespan. The fast variant
does the exact same thing without unnecessary work:

1. **Lower bound.** A graph has a makespan lower bound (`DagMetrics.lower_bound`).
   Once a schedule hits it, nothing can beat it and the remaining groups are skipped.
   Greedy alone sits at the lower bound in 78% of blocks (73 of 93) and in 92% of
   unique graphs in the set (883 of 958).
2. **Group order:** `bh`, `rule`, `bt`, `prio`, `hold`, `defer` — cheap and effective
   ones first. On a full pass the order does not affect the outcome, only how early we
   hit the lower bound.
3. **Engine.** `ListPlan` computes the same thing as `list_schedule`, but with
   readiness counters instead of scanning, a per-model channel table, and jumping over
   empty cycles. Verified for full schedule equality (cycle and channel of every
   instruction, issue order).
4. **Network inference.** `FastNet` accumulates numbers in the same order as
   `TinyPriority`, so outputs match bit-for-bit; identical feature rows are evaluated
   once (on real code, only 12% of rows are unique across all blocks).
5. **Acceptance.** Makespan is compared first, and `Schedule` is built and validated
   only for a candidate that beats the current best. The decision trace is built once,
   for the winner, and only when `with_trace=True` (default: yes).

What each step saves (ms per graph, single process, no warmup):

| | eval_hard | eval_real |
|---|---:|---:|
| `TinyScheduler` as-is | 63.4 | 70.4 |
| items 2–5, without bound stop and without trace | 6.8 | 3.5 |
| + bound stop (item 1), without trace | 1.9 | 0.38 |
| + winner trace (default) | 2.6 | 0.95 |
| for scale: project's `GreedyListScheduler` | 0.75 | 0.66 |

Answer to "does the reward affect speed": no. The reward (mean makespan in `es.py`)
acted during training and determined **which** weights were learned. Speed is governed
by the lower bound and the engine, which are identical for any weights.

## 3. Guarantees and their limits

`TinyFastScheduler(mode="exact")`:

- makespan equals `TinyScheduler`'s makespan on any graph where the lower bound is
  valid. The bound was never above a found optimum across ~3,800 graphs; the project
  has a dedicated test for this (`TestIntervalLowerBound` in `tests/test_dag.py`);
- the schedule is legal (`validate()` is empty, `complete`) and no worse than greedy;
- `optimal=True` is set only when makespan == lower bound, i.e. when optimality is
  proven.

What is **not** guaranteed: on tied makespans, the exact schedule and winner tag
(`tiny_winner`) may differ from `TinyScheduler` — groups run in a different order, and
the first to reach the best score wins. Traces match whenever the tags match.

`mode="asm"` drops the `hold` and `defer` groups. This is **a measurement, not a
guarantee**: on real code, 0 losses (1,514 block/window graphs + 947 `eval_real`
graphs); on `eval_hard`, 6 of 300 graphs are worse by 1 cycle. The caller chooses the
mode.

How it was verified:

| What | How | Result |
|---|---|---|
| Same cycles | `tools/tiny_fast_check.py`, 3,061 graphs (final run) + 2,000 training graphs earlier | 0 mismatches, all legal, none worse than greedy |
| `ListPlan` | fuzz against `list_schedule`: scenarios and random graphs, machine profiles of varying widths, perturbed latencies and occupancies, tied priorities, holds | 452,699 combinations in long run, 0 mismatches; short rerun on final code — 49,519, 0 |
| `FastNet` | `==` comparison against all three networks | 688,968 values, 0 differences |
| Tests catch breakages | 14 mutants of `fast.py` (including dropping a portfolio group, shifting beam seed) | all 14 caught |
| Dataset generator | 12 mutants of `make_eval_real.py` | all 12 caught |

## 4. Block mode

`asm_parser.build_dag` builds one DAG for the entire `.s` file. Labels mean nothing
there, so the DAG stretches across block boundaries while the scheduler does not
reorder branches. The consequence was measured on 25 `lcc` files: the compiler's own
schedule reconstructs and passes validation on the whole-file DAG in **4 out of 25
files**, versus **71 out of 93 blocks** (n ≥ 10) in block mode. Honest comparison with
`lcc` and optimality proofs are only possible per block. GRASP (ICS '26) works the same
way: the unit of work is a basic block.

`vliw/core/blocks.py`: a block starts at a label and ends at a wide instruction with
`ct` / `ibranch` / `call` / `return` / `rbranch`; a new label closes the previous
block. Windows are sliding slices of consecutive wide instructions inside a block
(targets 16, 24, 32, 48 operations; 12–56 per window). Values entering from outside the
block are assumed ready at cycle 0.

```bash
python3 tools/block_report.py --dir real_candidates_100_400/asm --oracle 3
python3 tools/tiny_fast_check.py --set real            # blocks and windows, fast vs. reference
```

What the report showed on 25 files (238 blocks, 6,047 operations; 93 blocks with ≥ 10 ops):

| 93 blocks n ≥ 10 | sum of model cycles | time per block, ms |
|---|---:|---:|
| greedy | 2,498 | 2.3 |
| tiny, exact mode | 2,479 | 4.0 |
| exact search, 3 s per block | 2,471 (−1.1%) | 619 |

Optimality is proven in 80 of 93 blocks, with 16 blocks improved over greedy. The lower
bound is hit by greedy in 73 blocks (78%) and in 5 more after search; in 15 blocks it
is never reached, and 12 of those have ≥ 64 operations. That is where room for search
actually lives.

What block mode does not do: it ignores neighbors (which registers are live-out, what
waits after a branch); it does not model `loop_mode` loops (hardware pipelining: cycles
per iteration is a different quantity from straight-line length; loop blocks are
flagged). Any gap below `lcc` in model cycles is **model** headroom (it does not know
about registers, aliasing, or bank conflicts), not a promised hardware speedup.

## 5. The real-code dataset

`eval_hard` and `eval_wide` are synthetic. `eval_real.jsonl` comes from the same 25
`lcc` files, cut into blocks (n ≥ 10) and windows with duplicates merged (`meta.seen` =
how many times the graph appeared). Line format matches `eval_hard.jsonl`; additionally
`meta.proven_by` (`bound` — tiny hit the lower bound; `oracle` — exact search within
30 s), `meta.lb`, `meta.file`, `meta.key`, `meta.loop`.

| | graphs |
|---|---:|
| unique graphs after deduplication (from 1,514 blocks and windows) | 1,180 |
| project format cannot serialize (see limitations below) | 222 |
| optimum proven → `eval_real.jsonl` | 947 |
| not proven within 30 s → `eval_real_open.jsonl` | 11 |

With edit B from §7 (verified on a copy), the set is complete: 1,163 proven and 17
unproven graphs — all 1,180. The conclusion is the same: greedy is optimal on 94.1%
(1,094 of 1,163) and loses 85 cycles out of 16,646 (0.51%); tiny is optimal on 1,139
of 1,163. Graphs with FMA/MOVA/CONV/INCR (216) are no harder for the scheduler than the
rest: greedy is optimal on 204 of them.

`eval_real_open.jsonl` has **no** `meta.makespan`: it stores the best known
(`meta.best_known`) and `proven: false`. It cannot be mistaken for an optimum, and
`vliw/tiny/eval.py` will honestly fail on such a file rather than lie.

```bash
python3 vliw/tiny/eval.py --eval eval_real.jsonl                  # tiny as-is
python3 vliw/tiny/eval.py --eval eval_real.jsonl --ignore-weights # without trained weights
python3 tools/validate_jsonl.py eval_real.jsonl                   # project validator
python3 tools/make_eval_real.py --oracle 30 --jobs 2              # rebuild (≈4 min)
```

Limitations to keep in mind:

- **Optimum is in `e2k-v6-measured` model cycles**, not hardware cycles. Loop blocks
  (`meta.loop = true`) are scored by straight-line length.
- **222 graphs were not written.** `vliw.core.dag._SYMBOL` does not know the `FMA`,
  `MOVA`, `CONV`, `INCR` classes (or `MOVAQ`, which did not appear in these files), so
  `build_dag(parse_graph_entries(...))` crashes on them with `KeyError`. These are
  floating-point and address-arithmetic graphs — the interesting part of the code. The
  generator does not modify project code and skips those graphs while counting them.
  The fix is five lines in `_SYMBOL` (backward-compatible: those classes previously
  raised an error), see §7; afterward `make_eval_real.py` rebuilds the set including
  them.
- **Training leakage.** Windows of the same block overlap, and similar code repeats
  across files. Train/eval splits must be grouped by `meta.file`, not by line.

## 6. What the measurements showed

On the 947 graphs of `eval_real.jsonl`, using the project's own `vliw/tiny/eval.py`:

| | optimal | total extra cycles | ms per graph |
|---|---:|---:|---:|
| greedy | 890 / 947 | 67 | 0.7 |
| tiny without trained networks (`--ignore-weights`; same with all three disabled) | 919 / 947 | 32 | 10 |
| tiny with weights (as in project) | 927 / 947 | 20 | 70 |
| `TinyFastScheduler`, exact mode | 927 / 947 | 20 | 0.95 |

- Total optimal cycles: 13,131; greedy loses 67 (**0.51%**), tiny loses 20 (0.15%).
  That is the total headroom available from **intra-block reordering on a fixed DAG**
  on this corpus under this model.
- Of those 67 cycles, ~35 are closed by search without trained networks (height-based
  beam), another 12 by the networks, and 20 remain. On synthetic data the networks'
  contribution is noticeably larger; on real code it is small because greedy already
  solves almost every graph.
- In the GRASP paper, graph transformations (IDG) yield 1.08× on their own, RL
  operation ordering yields 1.02× on its own, and together 1.22×. Intra-block ordering
  is not where the main headroom lives; here it measures at 0.5%.

## 7. Optional edits to existing files (not applied)

**A. Enable the fast scheduler in the product.** Two call sites where the product
instantiates `TinyScheduler()`, plus a test that cross-checks agent facts against a
direct run:

```diff
--- a/vliw/cli.py                      # cmd_tiny
-    from .tiny.scheduler import TinyScheduler
+    from .tiny.fast import TinyFastScheduler
-    tiny = TinyScheduler()
+    tiny = TinyFastScheduler()

--- a/vliw/agent/context.py            # tiny_facts
-        from ..tiny.scheduler import TinyScheduler
+        from ..tiny.fast import TinyFastScheduler
-        res = TinyScheduler().schedule(session.dag_obj, session.model())
+        res = TinyFastScheduler().schedule(session.dag_obj, session.model())

--- a/tests/test_agent_grounding.py    # test_facts_match_direct_tiny_run
-        from vliw.tiny.scheduler import TinyScheduler
+        from vliw.tiny.fast import TinyFastScheduler
-        res = TinyScheduler().schedule(s.dag_obj, s.model())
+        res = TinyFastScheduler().schedule(s.dag_obj, s.model())
```

The test changes because it checks the winner tag (`tiny_winner`) in facts, and on tied
cycles the fast scheduler's tag may differ (§3). The interface is identical:
`schedule(dag, model)` → `SchedulingResult`; `search_stats` keys (`tiny_winner`,
`baseline_makespan`, …) are preserved, with `lower_bound`, `proved_by_bound`,
`bound_hit_at`, `groups_run`, `groups_skipped` added. Rollback is reverting those lines.
Setting `VLIW_NO_NUMPY=1` disables numpy (same result in pure Python, nearly the same
speed on real code).

**B. Five symbols in `vliw/core/dag.py::_SYMBOL`** (`FMA`, `MOVA`, `MOVAQ`, `INCR`,
`CONV`) and test `tests/test_symbols.py`: every model operation class round-trips
through text serialization. On a clean repo this test fails (15 class×profile pairs
without a symbol); with the edit it passes. The symbol is only used for graph text and
does not affect scheduling. With it, `make_eval_real.py` also serializes graphs with
FMA/MOVA/CONV/INCR.

Suggested entry for `CHANGELOG.md` (not committed):

```
### Scheduling speed
- `TinyFastScheduler` (vliw/tiny/fast.py): same makespan as `TinyScheduler`,
  24–80× faster; stops at the lower bound. Verified: 3,061 graphs, 0 mismatches.
- Block mode (vliw/core/blocks.py, tools/block_report.py).
- Dataset eval_real.jsonl: 947 graphs of real lcc code with proven optima.
```

## 8. Boundaries

- All cycles are machine-model cycles. They do not equal Elbrus hardware cycles.
- Block mode does not see neighboring block context and does not model `loop_mode`.
- `asm` mode is a measurement, not a guarantee (§3).
- The dataset covers 81% of unique graphs (958 of 1,180) until `_SYMBOL` knows the five
  missing classes (§5).
- For any new tiny scheduler, check not only `eval_hard`, but also `eval_real.jsonl`:
  it only has anything left to prove on 57 of 947 graphs (where greedy is not optimal)
  and on the 11 graphs in `eval_real_open.jsonl`.
