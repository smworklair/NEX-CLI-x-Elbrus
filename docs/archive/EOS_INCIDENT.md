# The Model Did Not Know How to End Its Response

Post-mortem of a single bug: three-quarters of the trained model's errors turned out
not to be scheduling errors, but a single missing token in the training data.

## Symptom

The evaluation of the `qwen-vliw-lora` adapter on 50 examples (`eval_kinds.jsonl`, 15.08 22:40)
looked like this:

```
valid          18  (36%)
hallucination  30  (60%)
shift           2  ( 4%)
```

This read as "the model outputs nonsense 60% of the time" — i.e., a quality problem
to be fixed with more data and epochs. Under that hypothesis, an additional 20,000
examples were generated.

## What actually happened

The "hallucination" label means holes in real IDs: the model failed to place
instructions that exist in the graph. Yet recounting all 30 records revealed that
there were **zero** records with a "not placed" error. For 24 of the 30, the sole
complaint was lines with IDs that do not exist in the graph:

```
n_graph=8, n_decoded=14
errs=['non-existent instruction IDs in model response: [8, 9, 10, 11, 12, 13]']
```

The 8-instruction graph was scheduled correctly and completely. The model simply
did not stop and kept writing lines for non-existent instructions 8–13.
That is not hallucination in any substantive sense — it is **failure to stop**.

Recount of all 50 records with the current classifier:

| category | in the dump | actual |
|---|---|---|
| valid | 18 | 18 |
| **tail** (legal prefix, failed to stop) | 0 | **24** |
| shift | 2 | 5 |
| resource | 0 | 3 |
| hallucination | 30 | 0 |

**42 out of 50 (84%) have legal prefixes.** Out of 32 errors, 24 are pure failure to stop —
that is 75%.

## Why the dump lied

The `validate_kaggle.py` classifier was rewritten on 15.08 at **22:51**. The dump was
captured at **22:40** — eleven minutes earlier. The previous version counted errors across
the entire response and did not separate "tail" from "hallucination": any extra IDs
threw the example into the scrap heap along with its legal prefix.

That is a trap in its own right, and it nearly ruined all subsequent benchmarking:
comparing a new run against the old "36%" number would have produced a gain half
composed of relabeling. That is why step 0 in `docs/RUNBOOK_EOS.md` is re-evaluating
the existing adapter with the current code, without training.

## Root cause

Next to the weights sits an archived copy of the training script —
`training/checkpoints/train_qlora.py` (14.08 18:57), the exact one used to train the
adapter (there is no `train_meta.json` beside it; only the new version writes one). In it:

```python
rows.append({"text": row["prompt"] + "\n" + row["completion"]})
```

There is no end-of-sequence token at all. The model saw 20,000 examples that never
ended with anything, and learned exactly that: after the last instruction, keep going.
On short graphs it kept writing lines up to the "habitual" length of 12–14 — hence
`n_graph=8, n_decoded=14`.

No error was raised during training. Training ran, loss dropped, metrics were computed.
The defect was in the data, not the code, and only surfaced at inference time.

## Three places where EOS is silently lost

The investigation uncovered not one failure, but a class of failures. All three are
fixed, and all three are now checked.

**1. Not appended to the text.** The original bug itself. The current version of
`training/train_qlora.py` appends EOS — but that version had never participated in
an actual training run; it was written on 15.08 at 22:52, after the adapter had already
been trained. In other words, the fix existed on disk and had never been applied:
the 36% figure measures a model that never received the fix.

**2. Appended, but masked out in labels.** `DataCollatorForLanguageModeling(mlm=False)`
sets `-100` everywhere `pad_token_id` appears. In Qwen2.5, `pad` =
`<|endoftext|>` (151643) and `eos` = `<|im_end|>` (151645) — they differ, so EOS currently
enters the loss. However, one line above sits:

```python
if tok.pad_token is None:
    tok.pad_token = tok.eos_token
```

On a base model where `pad` is unset, `pad` becomes equal to `eos` — and the collator
masks out the end of every example. `--base` is switched with a single flag, with four
candidates in the docstring. EOS is visible to the naked eye in the text, yet there is
zero gradient for stopping.

Replaced with `CausalCollator`: the mask is taken from `attention_mask`, not by ID
equality. Which token is chosen as padding no longer matters.

**3. Eaten by an extra newline.** The training text is concatenated as
`prompt + "\n" + completion + eos`. The external generator used to build the extra
20,000 examples placed a trailing `\n` at the end of both the prompt and the completion —
at the boundary that would have produced `расписание:\n\n0: такт=...`, and EOS would have
landed after a blank line. Caught during format verification before merging the datasets;
never entered training.

## What now prevents this from recurring

| guard | where | what it catches |
|---|---|---|
| `check_eos()` prints the last token and its label in `labels` | `training/train_qlora.py`, first log lines | all three cases at once, before training starts |
| the run kernel aborts training if the self-check fails | `tools/kaggle_prep.py` | wasted GPU quota |
| tests for no trailing `\n` — in the encoder and in the dataset files themselves | `tests/test_encode.py` | case 3 |
| `report_runs.py` recomputes labels instead of trusting the dump | `tools/report_runs.py` | comparing classifiers instead of models |
| step 0 in the run is a baseline with the same code | `docs/RUNBOOK_EOS.md` | the same risk from the other side |

Expected lines in the training log:

```
EOS at the end of each example: '<|im_end|>'
  last token of example: 151645 '<|im_end|>' (eos_token_id=151645, pad_token_id=151643)
  EOS enters loss (labels != -100) — OK
```

## What this analysis does NOT prove

That after the fix it will reach 84%. The 84% ceiling is the share of legal prefixes
right now; there is no basis to assume all 24 tails will heal completely and without
side effects. Further training can move "shift" and "resource" as well, in either
direction. The number comes from measurement, not from this document.

## Moral

An error category in a report is a classifier's hypothesis, not a fact. Before treating
"the model outputs nonsense" with more data and epochs, open the errors themselves and
read what they actually say: here, there was zero difference in the report between
"we need 20,000 more examples" and "one token wasn't appended".
