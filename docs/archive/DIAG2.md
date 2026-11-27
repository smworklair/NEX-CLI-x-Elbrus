# Why Run 2 Collapsed — Dump Analysis

The `vliw-diag2` diagnostic **did run** (status COMPLETE); its dumps are stored in
`training/checkpoints/diag2_free.jsonl` and `diag2_constrained.jsonl`. An earlier
working note stated that it had not been run — that is outdated.

Measurement: Run 2 adapter, 20 examples from `eval.jsonl` (narrow eval, graphs of
6..14 operations) — the exact benchmark where Run 2 scored 17.7% vs. Run 1's 97.7%.
Each example was run twice: with free generation and with constrained generation.

## Result

| mode | valid | gap to optimum |
|---|---|---|
| free generation | 3/20 (15%) | — |
| constrained | **20/20 (100%)** | **0.00 cycles, all 20 strictly optimal** |

Failure breakdown in free mode: hallucination 9, garbage 7, tail 1.

## Cause: the leading `\n0: ` is dropped

In **all 20** free-mode responses, the label for the first instruction is missing.
The model treats the prompt's trailing colon as the label and continues it
as a schedule line:

```
prompt ends with:  ...5 ADD <- 3 4\nрасписание:
expected:          \n0: такт=0 канал=0\n1: такт=5 канал=1
actual:             такт=0 канал=0\n1: такт=5 канал=1
```

From there, things fall apart in different ways: sometimes only instruction 0 is lost
("hallucination" — a hole in the IDs), sometimes the model also drops colons on
the remaining lines ("garbage" — zero parsed lines), and sometimes it slips into
paraphrasing the graph from the prompt.

**The schedule itself is correct.** In 5 out of 20 examples, the free-mode response
matches the constrained one BYTE-FOR-BYTE once the missing `\n0: ` is restored.
The rest diverge later in the line only because constrained mode also prevents
picking an illegal channel.

## What is NOT the cause

**Not a token boundary issue.** Verified on the actual Qwen2.5-3B tokenizer:
`расписание:` tokenizes identically both in isolation and concatenated with the response
(`':'` and `'0'` are separate tokens, with no merging). The prompt-boundary shift
hypothesis was not confirmed.

**Not the data format.** `dataset.jsonl`, `train_merged.jsonl`, and
`vliw_train_extra_fixed.jsonl` all encode the response the same way: `0: такт=N
канал=M`, with the boundary `расписание:0: такт=` in all three.

What remains suspect is the `расписание:0:` boundary itself — the prompt ends with
a colon, the response starts with a colon-terminated label, and there is no separator
between them. The structure is ambiguous, and training from scratch on a larger dataset
settled into a different local optimum than Run 1, which fine-tuned on top of Run 0.
This is a hypothesis, not an established fact: it can be tested with a cheap run
on data formatted as `расписание:\n0: ...`.

## What this changes for Run 3

The Run 2 adapter is **not bad at scheduling**. On the narrow eval under
constrained generation, it achieves 100% validity and 100% exact optima —
that is, no worse than Run 1 (97.7%), and better in terms of optimality gap.
The 17.7% failure is a FORMAT EMISSION failure, not a scheduling failure.

Hence, the question "do we need another training run" stands differently than
previously thought. Before retraining, two cheap moves are worth testing:

1. **Constrained generation as the default mode** for the Run 2 adapter.
   Measuring it on the wide eval costs minutes of GPU time — only the narrow eval
   (20 examples) was measured here.
2. **A separator in the data** (`расписание:\n0: ...`) and a short run to test
   the boundary hypothesis.

Caveat: 20 examples, narrow eval. The same has not been measured on `eval_wide`,
and the STORE error class (see `docs/ROADMAP.md`) is not tested here at all —
`eval.jsonl` contains zero STORE operations.
