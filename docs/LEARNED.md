# Learned LLM as a Scheduler

> Stage 12 of 13 · [← Real vs. Synthetic](REAL_VS_SYNTH.md) · [Roadmap](README.md) · [For Developers →](ENTHUSIAST.md)

Historical track: a LoRA adapter on top of `Qwen/Qwen2.5-3B-Instruct`. It works, but has been superseded by TINY AI — which is orders of magnitude faster and no worse on real code.

## Status

- Adapters: three checkpoints (`r=16`, ~120 MB) on [Hugging Face](https://huggingface.co/Shmonika/nex-vliw-lora), in `safetensors` and GGUF formats.
- The base model is not stored in this repository: `tools/setup_local_llm.sh` downloads it.
- The agent's conversational base model is Phi-4-mini GGUF; the scheduler is a separate LoRA track.
- Main result is negative: on real `lcc` output, the model did not beat random search on any of the 13 graphs. Methodology: [`../real_candidates_100_400/model_eval/REPORT.md`](../real_candidates_100_400/model_eval/REPORT.md).

## Running

```bash
pip install -e ".[learned]"      # torch, transformers, peft
python -m vliw learned           # on the current graph
python -m vliw learned --bench 5 # across several graphs
```

Without weights or dependencies, the command does not crash — it prints what is missing.
One graph on a CPU-only laptop takes around 30 seconds.

## Two Backends

**1. transformers.** Reference path — the same code that ran on Kaggle.

| format | model size | practical where |
|---|---:|---|
| float32 | 12.4 GB | almost nowhere |
| bfloat16 / float16 | 6.2 GB | CPU with 16+ GB RAM / GPU |
| 4-bit GGUF | ~2.0 GB | CPU with 8+ GB RAM |

Override device with `NEX_LEARNED_DEVICE=cpu`.

**2. GGUF via llama.cpp.** Primary CPU path:

```bash
tools/setup_local_llm.sh          # engine + base model + adapter conversion
tools/setup_local_llm.sh check    # check what is already present
```

The script fetches a prebuilt `llama-completion`, downloads `qwen2.5-3b-instruct-q4_k_m.gguf`, and converts the adapters. All heavy files live in `vendor/` and are excluded from git.

You cannot swap the base model: LoRA is a delta applied to a specific checkpoint's weights. Another model with matching matrix shapes will load without error and silently emit nonsense.

## Architecture

| file | role |
|---|---|
| `vliw/learned/runtime.py` | weight discovery, dependencies, loading, generation |
| `vliw/learned/scheduler.py` | `Scheduler` protocol: graph → schedule |
| `vliw/learned/portfolio.py` | candidate portfolio |
| `training/` | dataset generation and training |

The model receives the graph as a prompt and returns a schedule. If the output is invalid, the scheduler honestly falls back to greedy rather than passing off a broken schedule as valid.

## Why It Didn't Stick

- 2–6 GB of weights and tens of seconds per graph versus milliseconds for TINY AI.
- On in-distribution synthetic graphs, the model occasionally beats greedy.
- On out-of-distribution real code, it fails to beat random search.
- Both numbers are real — they were simply measured under different conditions.

Training your own version: [`../training/README.md`](../training/README.md).
