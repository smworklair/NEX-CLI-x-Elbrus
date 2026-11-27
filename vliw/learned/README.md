# `vliw/learned`: Learned LLM as a Scheduler

LoRA adapter on top of Qwen2.5-3B implementing the `Scheduler` protocol. This is a historical track superseded by TINY AI. User guide: [`docs/LEARNED.md`](../../docs/LEARNED.md).

## Why a Separate Package

```text
vliw/
  core/     machine model, graph, schedulers, metrics
  ui/       colors, borders, tables, logo
  learned/  learned model (here)
  cli.py    glue: command → core → ui → output
```

`core/`, `ui/`, and `cli.py` do not know where a schedule came from. They only depend on the `Scheduler` contract, so a model can be plugged in here without touching anything outside.

## Contract

```python
class LearnedScheduler:
    name = "AI Scheduler (learned model)"
    kind = "learned"      # baseline=heuristic, oracle=exact
    short = "learned"

    def schedule(self, dag, model) -> SchedulingResult:
        ...
```

Input: `DAG` and `MachineModel`. Output: the same `SchedulingResult` returned by greedy and exact search, with optional `trace` and `notes`.

## What Was Built

1. Trained and published three adapters on [Hugging Face](https://huggingface.co/Shmonika/nex-vliw-lora).
2. `schedule()` encodes the graph into a prompt, generates a completion, and constructs a `Schedule`. Invalid outputs fall back to greedy instead of masquerading as valid schedules.
3. Populates `trace`, so `/explain` and `/compare` display the model's decisions.

## Result

On in-distribution synthetic graphs, the model occasionally beats greedy.
On **real code** from `lcc`, it failed to beat random search on any of the 13 graphs (+0 cycles total). Methodology and raw data: [`real_candidates_100_400/model_eval/REPORT.md`](../../real_candidates_100_400/model_eval/REPORT.md).

Both numbers are real: they were simply measured under different conditions.

## Training Your Own Version

Full procedure — dataset generation, QLoRA fine-tuning of Qwen on free GPUs, and validation — is in [`training/README.md`](../../training/README.md). `training/` is a separate package and does not pull ML dependencies into core `vliw`.
