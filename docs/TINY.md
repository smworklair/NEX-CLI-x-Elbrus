# TINY AI: Learned Scheduler Without an LLM

> Stage 9 of 13 · [← Orchestra](ORCHESTRA.md) · [Roadmap](README.md) · [Machine Model →](ISA.md)

TINY AI is not a language model — it is a suite of compact MLPs (~21K parameters) that advise a deterministic list scheduler on operation priorities, defers, and holds. Conventional scheduling code emits the final VLIW bundles, guaranteeing legal schedules by construction: invalid schedules and hallucinations are structurally impossible.

In the CLI, TINY AI runs through the `nex_core/` NNL wrapper in its fast variant **TINY Flash**: the exact same scheduler packaged as an NNL block (passport, weights, SHA-256), not a separate network. The `nnl_vliw/` experiments are independent.

## What It Computes

A candidate portfolio evaluated from cheapest to most expensive:

```text
greedy → prio → prio+defer → prio+hold → rule_hold → rule_hold_far
       → beam_t* → beam_h* → beam_d*
```

- **prio** — priority ordering driven by MLP scores.
- **defer** — earliest-issue constraint ("do not issue before cycle `t`").
- **hold** — deliberate delay past ASAP, predicted by a dedicated head.
- **rule_hold** — deterministic heuristics for sole-issue functional-unit holds without ML.
- **beam** — candidate fan-out around two anchors, selecting the shortest makespan.

The shortest makespan wins. Ties break in favor of the greedy list scheduler baseline, so **TINY AI never regresses against the baseline**.

## Numbers

| | greedy baseline | TINY AI | exact optimum |
|---|---|---|---|
| real code, optimal basic blocks out of 947 | 890 | **927** | 947 |
| hard graphs, out of 300 | 18 | **284** | 300 |
| time per basic block | 0.4 ms | 0.6 ms | up to 20 s |

- On real code, the greedy baseline leaves 0.51% in recoverable cycles; TINY AI recovers roughly 70% of that scheduling headroom.
- Zero regressions across 1,547 tested graphs.
- `eval_hard`: 284/300 optimal, gap 0.053; schedule validity 100%.
- `eval_wide`: tied with the baseline, zero wins and zero losses.

## TINY Flash

`TinyFlashScheduler` (`vliw/tiny/fast.py`) produces the exact same makespan as standard TINY, much faster:

| dataset | before | after |
|---|---:|---:|
| `eval_hard` | 63.4 ms | 2.6 ms |
| `eval_real` | 70.4 ms | 0.95 ms |
| `eval_wide` | 39 ms | 0.49 ms |

Up to 26× speedup. Across 3,061 graphs: 0 makespan discrepancies, all schedules valid.
The speedup comes from early termination upon hitting the theoretical lower bound, the `ListPlan` engine, and lazy trace generation.

## Commands

```bash
python -m vliw tiny                     # run on the current basic block
python -m vliw.tiny.train --train train_merged.jsonl \
    --out vliw/tiny/weights.json --max-graphs 8000 --epochs 25 --seed 0
python -m vliw.tiny.es --train train_hard.jsonl \
    --init vliw/tiny/weights.json --out vliw/tiny/weights.json --iters 20 --pop 16
python -m vliw.tiny.eval --eval eval_hard.jsonl --weights vliw/tiny/weights.json
python -m vliw.tiny.verify --weights vliw/tiny/weights.json --train-sample 500 --fuzz 200
python -m unittest tests.test_tiny tests.test_tiny_fast
```

Training takes minutes on CPU; `numpy` is required only for training, while inference runs purely on the Python standard library.
If `weights.json` is missing, the scheduler falls back cleanly to the greedy list scheduler baseline.

## Datasets

| dataset | role |
|---|---|
| `train_merged.jsonl` | training |
| `eval_hard_dev.jsonl` | configuration selection |
| `eval_hard.jsonl` | final test set, evaluate once |
| `eval_wide.jsonl` | regression check on easy graphs |
| random graphs | "no worse than baseline" verification |

## Boundaries

- Cycle counts are model-based, not hardware measurements; `loop_mode` (software-pipelined loops) is not modeled.
- Gains on real code are modest because the greedy list scheduler is already optimal on 94% of basic blocks.
- TINY AI selects the best schedule from its candidate portfolio; it does not prove optimality.
- Experimental NNL cores (`nnl_vliw/`) for selecting portfolio groups are not wired into the CLI: on real code they perform barely better than random abstention — [`../nnl_vliw/README.md`](../nnl_vliw/README.md).

Internals and developer commands: [`../vliw/tiny/README.md`](../vliw/tiny/README.md).
