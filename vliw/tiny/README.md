# TINY AI: Architecture and Training

A small MLP (~21K parameters) that provides a priority vector and defer hints to a conventional scheduler. The model generates no text, so hallucinations cannot occur as a class. Deterministic code builds the schedule, guaranteeing validity by construction.

User-facing numbers and boundaries: [`docs/TINY.md`](../../docs/TINY.md).

## Files

| file | role |
|---|---|
| `features.py` | 18 node features: op class, height/asap, latency, occupancy, channels, degrees |
| `model.py` | MLP 18→128→64→1, inference on Python stdlib |
| `train.py` | behavioral cloning of CP-SAT oracle ordering |
| `es.py` | Evolution Strategies optimizing makespan reward |
| `scheduler.py` | `TinyScheduler`: candidate portfolio and best-makespan selection |
| `fast.py` | `TinyFlashScheduler`: identical result, much faster |
| `eval.py`, `verify.py` | benchmarks and validity verification |
| `weights.json`, `weights_defer.json`, `weights_hold.json` | trained heads |

## Portfolio

```text
greedy → prio → prio_defer → prio_hold → rule_hold → rule_hold_far
       → beam_t* → beam_h* → beam_d*
```

The shortest makespan wins; ties go to greedy. Thus **it is never worse than greedy**.
Without `weights.json`, an honest fallback remains: beam around height plus greedy.

- **prio** — priority order from MLP.
- **defer** — "not earlier than" constraint clipped to greedy makespan.
- **hold** — deliberate delay past ASAP, separate head.
- **rule_hold** — handcrafted monopoly-port holds without ML.
- **beam** — deterministic priority jitter, K=16 around two normalized centers.

## Commands

```bash
python -m vliw.tiny.train --train train_merged.jsonl \
    --out vliw/tiny/weights.json --max-graphs 8000 --epochs 25 --seed 0
python -m vliw.tiny.train --train train_merged.jsonl \
    --out vliw/tiny/weights_defer.json --target cycle
python -m vliw.tiny.es --train train_hard.jsonl \
    --init vliw/tiny/weights.json --out vliw/tiny/weights.json --iters 20 --pop 16
python -m vliw.tiny.eval --eval eval_hard.jsonl --weights vliw/tiny/weights.json
python -m vliw.tiny.verify --weights vliw/tiny/weights.json --train-sample 500 --fuzz 200
python -m unittest tests.test_tiny tests.test_tiny_fast tests.test_tiny_verify
```

`numpy` is only required for training. Inference runs on the bare standard library.

## Datasets

| dataset | role | rule |
|---|---|---|
| `train_merged.jsonl` | training | may be used in full |
| `eval_hard_dev.jsonl` | config selection | base decisions only on this |
| `eval_hard.jsonl` | final test | evaluate once |
| `eval_wide.jsonl` | regression on easy graphs | tie with greedy |
| random graphs | never-worse check | 0 regressions |

## Results

- `eval_hard`: 284/300 optimal, gap 0.053, 100% schedule validity.
- Real code: 927/947 optimal blocks vs. 890 for greedy.
- Zero regressions across 1,547 tested graphs.
- `TinyFlashScheduler`: identical makespan, 0 discrepancies across 3,061 graphs; 0.95 ms/graph on `eval_real`.

## Inspirations

- `google/ml-compiler-opt` — behavioral cloning warmstart plus ES on makespan.
- `llvm/llvm-project` — runtime-free AOT model inference.
- `google-research-datasets/tpu_graphs` — "graph + config + timing" evaluation discipline.
