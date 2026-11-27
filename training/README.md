# Training Qwen as a Scheduler

Step-by-step guide to reproducing the LoRA track: custom base model, different dataset, or extra epochs.
The model trains on "dependency graph → optimal schedule" pairs, with ground truth produced by exact search.

> This is a historical track. In the project it has been replaced by TINY AI, which is orders of magnitude faster and no worse on real code. These instructions are kept for reproducibility.

## Step 1. Dataset (CPU)

```bash
cd NEX-CLI-x-Elbrus
python3 training/generate_dataset.py \
    --count 20000 \
    --sizes 6,8,10,12,14 \
    --budget 1.5 \
    --out dataset.jsonl
```

- `--count` — number of examples. 500–1000 is enough for an initial smoke test.
- `--budget` — seconds per graph for exact search. Larger graphs need a larger budget.
- JSONL format: `{"prompt": "...", "completion": "...", "meta": {...}}`.

Verify before training:

```bash
python3 training/validate.py dataset.jsonl
```

Expected output: `N/N valid, round-trip verified`.

## Step 2. Kaggle with GPU

1. Sign up on kaggle.com (no credit card needed for free GPU).
2. New Notebook → Settings → **Accelerator: GPU T4×2**.
3. Add Data → upload `dataset.jsonl`.
4. Install dependencies:

```bash
!pip install -q -U -r requirements-kaggle.txt
```

5. Upload `training/train_qlora.py` and `training/validate_kaggle.py` into the notebook.

## Step 3. 4-Bit QLoRA

An EOS token is appended to every example: without it, the model never learns to stop and keeps generating trailing garbage.

**Continue an existing adapter:**

```bash
!python train_qlora.py \
    --base Qwen/Qwen2.5-3B-Instruct \
    --adapter /kaggle/input/.../qwen-vliw-lora \
    --data /kaggle/input/<dataset>/dataset.jsonl \
    --out /kaggle/working/qwen-vliw-lora \
    --epochs 2
```

**Different base model from scratch** — run the same command without `--adapter`.

For 7B on T4: `--batch-size 2`. Do not use `Qwen3-4B-Thinking-*`: chain-of-thought reasoning lengthens outputs and breaks the parser.

The log should show `trainable params ... < 2%` and confirm EOS at the end of every example.

## Step 4. Evaluation

```bash
!python validate_kaggle.py \
    --model /kaggle/working/qwen-vliw-lora \
    --limit 50 \
    --dump /kaggle/working/eval_kinds.jsonl \
    /kaggle/input/<dataset>/eval.jsonl
```

Two metrics:

- **as-is** — the model stopped on its own and the schedule is valid;
- **prefix 0..n-1** — valid after trimming non-existent IDs.

A trailing tail after a valid prefix is a stopping issue, not a scheduling comprehension failure.
Missing real IDs or empty responses mean it's time to change the base model.

## Step 5. Wire In the Adapter

Download the adapter folder from Kaggle. `vliw/learned/scheduler.py` already handles the rest: it encodes `(dag, model)`, generates the completion, parses the response, builds a `Schedule`, and calls `.validate()`. If the output is invalid, it falls back to greedy.

No code changes are needed for a new adapter.

## Free Resources Are Enough

Kaggle's 30 free GPU hours/week plus 4-bit QLoRA on a 3B model with a few thousand short examples is comfortably doable for free. Paid GPUs are only needed if you hit a hard ceiling.
