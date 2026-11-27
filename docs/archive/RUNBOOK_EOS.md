# Kaggle Run: Isolate EOS First, Then Add Data

Order matters more than commands here. Two things are changing at once — the model sees
EOS for the first time and receives twice as much data for the first time. If both are
launched in a single run, there will be a gain, but no explanation.

## What is already established locally

| fact | how verified |
|---|---|
| Generator profile == `vliw/core/model.py` | character-by-character comparison of all tables, 0 discrepancies |
| 40,000 examples are legal, optimality gap 0 | `Schedule.validate()` from `vliw.core`, both files |
| No eval leakage into training | prompt intersection = 0 across all file pairs |
| Adapter was trained WITHOUT EOS | archived `training/checkpoints/train_qlora.py`: `text = prompt + "\n" + completion` |
| 75% of errors are pure failure to stop | recount of `eval_kinds.jsonl` with current `classify()`: 24 "tail" out of 32 errors |

## What to upload to Kaggle

As a Dataset (Input):

```
train_merged.jsonl              39,700 examples, 24 MB  — Run 2 training
dataset.jsonl                   20,000 — Run 1 training (same data as before)
eval.jsonl                         300 — old eval, graphs 6..14, for before/after
eval_wide.jsonl                    300 — held-out 4..24, covers large graphs
```

Via `%%writefile` into cells: `train_qlora.py`, `validate_kaggle.py`.

The old `qwen-vliw-lora` adapter is needed as Input — it is both the baseline and the
starting point for Run 1. **Do not overwrite:** every run has its own `--out`.

---

## Step 0. Baseline with the same classifier

Without this step there is nothing to compare against. The "36% valid" figure came from
a dump on 15.08 at 22:40, while `validate_kaggle.py` was rewritten at 22:51 — the old
classifier did not separate "tail" from "hallucination" and wrote off 24 legal prefixes
as hopeless. We need a measurement with the current code, otherwise part of the gain
will be purely on paper.

No training here, inference only — cheap.

```bash
!python validate_kaggle.py --model /kaggle/input/vliw-lora/qwen-vliw-lora \
    --dump /kaggle/working/base_eval.jsonl \
    /kaggle/input/vliw-data/eval.jsonl
```

```bash
!python validate_kaggle.py --model /kaggle/input/vliw-lora/qwen-vliw-lora \
    --dump /kaggle/working/base_eval_wide.jsonl \
    /kaggle/input/vliw-data/eval_wide.jsonl
```

Expectation: on `eval.jsonl`, roughly "valid 36%, tail ~48%, shift ~10%, resource ~6%".
On `eval_wide.jsonl`, noticeably worse — it contains graphs of up to 24 instructions
that the model has never seen. Both numbers form the reference baseline.

## Step 1. Isolated EOS: one variable

The EXACT SAME data as the previous training (`dataset.jsonl`), continuing from the
existing adapter, one epoch. Exactly one difference from before — EOS.

```bash
!python train_qlora.py \
    --base Qwen/Qwen2.5-3B-Instruct \
    --adapter /kaggle/input/vliw-lora/qwen-vliw-lora \
    --data /kaggle/input/vliw-data/dataset.jsonl \
    --out /kaggle/working/lora-eos \
    --epochs 1
```

The first lines of the log must show the self-check:

```
EOS at the end of each example: '<|im_end|>'
  last token of example: 151645 '<|im_end|>' (eos_token_id=151645, pad_token_id=151643)
  EOS enters loss (labels != -100) — OK
```

If `!! WARNING` is printed instead — abort the run; there is no point continuing.
Those three lines are the entire reason for this setup.

Evaluation:

```bash
!python validate_kaggle.py --model /kaggle/working/lora-eos \
    --dump /kaggle/working/eos_eval.jsonl \
    /kaggle/input/vliw-data/eval.jsonl
```

```bash
!python validate_kaggle.py --model /kaggle/working/lora-eos \
    --dump /kaggle/working/eos_eval_wide.jsonl \
    /kaggle/input/vliw-data/eval_wide.jsonl
```

The second evaluation is inference on 300 examples, no training, costs next to nothing.
It is needed so there is no hole in the table: without it, you cannot separate
"EOS helped on large graphs too" from "the new data pulled up large graphs".

**What this will prove.** If "tail" collapses toward zero and "valid" moves toward 80%,
the diagnosis is completely confirmed, and that is the result of a single line of code,
not 20,000 new examples. If tails remain, then either one epoch is not enough or EOS is
not the only issue, and Run 2 must be planned differently.

The ceiling here is 84% (the current share of legal prefixes), and that is a hypothesis,
not a promise: continued training may also nudge "shift" and "resource" in either
direction.

## Step 2. Full run on merged data

From scratch off the base model, not on top of the old adapter: the habit of not
stopping is baked into the old adapter, and unlearning it is more expensive than
learning from a clean slate.

```bash
!python train_qlora.py \
    --base Qwen/Qwen2.5-3B-Instruct \
    --data /kaggle/input/vliw-data/train_merged.jsonl \
    --out /kaggle/working/lora-merged \
    --epochs 2 --batch-size 2 --accum 8
```

Batch size 2, not 4: the first launch (23.08) hit CUDA OOM at step 303 of 4964 —
the merged data is longer than the old data (graphs up to 24 operations), increasing
peak activation memory. `accum 8` preserves the effective batch size of 16 and the step
count; `expandable_segments` is set in the run kernel to prevent fragmentation.

≈ 4960 steps at effective batch size 16. Checkpoints every 100 steps — a Kaggle session
has already timed out at 93% of an epoch, hence `save_strategy="steps"`.

Evaluation on both eval sets:

```bash
!python validate_kaggle.py --model /kaggle/working/lora-merged \
    --dump /kaggle/working/merged_eval.jsonl \
    /kaggle/input/vliw-data/eval.jsonl
```

```bash
!python validate_kaggle.py --model /kaggle/working/lora-merged \
    --dump /kaggle/working/merged_eval_wide.jsonl \
    /kaggle/input/vliw-data/eval_wide.jsonl
```

## Summary table

Pull the six dumps from Kaggle and place them in `training/checkpoints/` under the
exact filenames used in the commands above. Then locally, without a GPU:

```bash
python tools/report_runs.py
```

The script finds the files by name, prints the error breakdown for each dump, the
summary table, and the wide-eval breakdown by graph size:

| run | eval.jsonl (6..14) | eval_wide.jsonl (4..24) |
|---|---|---|
| 0. current adapter (no EOS) | 26.7% (81%) | 9.7% (31%) |
| 1. + EOS, old data | 97.7% (98%) | 32.7% (33%) |
| 2. + EOS, merged data, from scratch | | |

Row 0 → 1 answers "how much did the EOS bug cost".
Row 1 → 2 answers "how much did the new data add".
The `eval_wide` column answers "what happens on graphs that were not seen before".

**Row 0 was run on 17.08.2026 (`base_eval.jsonl`, `base_eval_wide.jsonl` in
`training/checkpoints/`).** `eval_wide` breakdown by graph size:
`4-7 → 0%`, `8-11 → 2%`, `12-15 → 27%`, `16-19 → 11%`, `20-24 → 10%`.

The forecast for row 1 needs adjustment. On `eval.jsonl`, "tail" dominates (54.3% of
all examples) — EOS should pull that column up sharply, as expected. On `eval_wide`,
however, **not tail, but `resource`** dominates (58.0%: the model places operations on
channels that physically cannot execute them — e.g., `STORE` not on `,2`/`,5`) — that is
not about stopping, but about the channel matrix not being learned on unfamiliar graph
sizes. EOS will barely affect that: Run 1 trains only on `dataset.jsonl` (range 6..14)
and does not close the size gap. Expect movement on `eval_wide` from row 1 → 2, not
from 0 → 1.

The optimality gap among legal prefixes is small on both evals (0.48 and 0.39 cycles on
average): when the model does not confuse channels and remembers to stop, it schedules
sensibly. The weak spot is not schedule quality, but the capability matrix and the stop
signal.

**Row 1 was run on 18.08.2026 (`eos_eval.jsonl`, `eos_eval_wide.jsonl`).**
The forecast was confirmed, in places more strongly than expected:

  * `eval.jsonl`: 26.7% → 97.7% (+71.0 pp). The "tail" category vanished almost
    completely (was 54.3%, now 0%). The optimality gap among legal prefixes dropped
    from 0.48 to **0.02** cycles — the model almost always hits the exact optimum,
    not merely a "legal" schedule.
  * `eval_wide.jsonl`: 9.7% → 32.7% (+23.0 pp) — a noticeable jump, even though EOS
    was not the primary cause there. The breakdown by graph size explains where the
    gain came from: `4-7 → 0%→73%`, `8-11 → 2%→40%` (a short tail on small graphs
    produced disproportionate garbage, and EOS removed it), `12-15 → 27%→36%`, while
    **`16-19` and `20-24` did not budge at all** (`11%→11%`, `10%→7%`) — `resource`
    (58%) dominates there just as before. Confirmed: the problem on large graphs is not
    about stopping; Run 2 fixes it, not this one.

The new adapter sits in `training/checkpoints/lora-eos/` (locally, not in git — like
the original `qwen-vliw-lora/`, these are weights).

**Important:** `report_runs.py` recomputes labels from scratch using the current
`classify()`, rather than taking `kind` from the dump. The 15.08 dump was written by
a version that confused "tail" with "hallucination"; merging it into one table with
raw labels would discard 24 legal prefixes and inflate the difference. The script prints
how many records it reclassified and into what.

## What is NOT in this run

Channel clusters (item 6, file `08_sverka_s_oficialnoy_tablicey_MCST.md`) — intentionally
excluded. Changing the profile invalidates both the adapter and both columns of the
table above. Measure first, change the world model second.
