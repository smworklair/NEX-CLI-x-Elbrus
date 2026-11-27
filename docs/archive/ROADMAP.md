# What Is Needed (and Not Needed) Before Run 2

Assessment compiled on 18.08.2026 from measurements rather than a paper plan. Every
conclusion below is locally reproducible without a GPU: the data and run dumps are
already in the repository.

## Headline: Run 1 failed on the wide eval not because of graph size

This changes the framing of Run 2, so it comes first.

`docs/RUNBOOK_EOS.md` explains the drop on `eval_wide` (32.7% vs. 97.7%) by saying
that it contains graphs of size 16..24, which the model had not seen. Inspecting the
`eos_eval_wide.jsonl` dump shows something else.

**In `dataset.jsonl` — the data Run 1 trained on — there are zero STORE operations.**
Not few, literally none out of 199,608. `eval.jsonl` has zero as well, so the narrow
eval cannot see this error class at all. Meanwhile, `eval_wide.jsonl` contains STORE
in 61% of its examples.

Breakdown of the same dump by "is STORE present in the graph":

| examples | resource | valid | shift | total |
|---|---|---|---|---|
| with STORE | 159 (87%) | 5 (3%) | 18 | 183 |
| without STORE | 17 (15%) | **93 (79%)** | 7 | 117 |

On graphs without STORE, Run 1 achieves 79% — roughly the same as on the narrow eval.
85% of all "resource" errors are STORE placed on a channel that does not execute it
(194 times on `,0`; only `,2` and `,5` are legal).

Graph size does still have an effect, though noticeably weaker, and it could not be
seen in isolation because the STORE share grows with size:

| bucket | share with STORE | valid (all) | valid (without STORE) |
|---|---|---|---|
| 4..7 | 28% | 73% | 100% |
| 8..11 | 55% | 40% | 77% |
| 12..15 | 57% | 36% | 79% |
| 16..19 | 77% | 11% | 46% |
| 20..24 | 84% | 7% | 45% |

Conclusion: the dominant cause is **operation vocabulary**, not length. The residual
size effect is real (46% vs. 79..100%), but secondary.

Good news: `train_merged.jsonl` closes this gap — 19,622 STOREs (4.41% of operations),
placed only on `,2` and `,5` in the ground truth. So Run 2 targets the real cause.
However, its hypothesis must be formulated differently than in the RUNBOOK.

## Blocking Run 2

1. **No kernel exists for Run 2.** `tools/kaggle_prep.py` only builds
   `vliw-step0-baseline` and `vliw-run1-eos` (`KERNELS`, line 236);
   the docstring explicitly notes that Run 2 is intentionally not prepared. Until
   the kernel is added, there is nothing to launch. This is the only true blocker —
   everything else below is optional.

## Worth doing beforehand (cheap, no GPU)

2. **Reformulate the Run 2 hypothesis in RUNBOOK** per the section above. Right now
   it says "larger graphs will be pulled up by new data"; more accurately, "the model
   sees STORE for the first time". The difference is not cosmetic: it defines what
   counts as success and which breakdown to inspect in the report.

3. **Teach `report_runs.py` to break down by STORE presence**, not just by graph
   size. Currently the script prints buckets 4..7, 8..11, etc. — the real cause is
   invisible there, smeared across all buckets. Two columns ("with STORE / without STORE")
   would make Run 2 immediately readable.

4. **Close the latent `max_len` trap.** `train_qlora.py` trains with `--max-len`
   defaulting to **1024**, while the `check_eos()` self-check tokenizes with
   `max_length=4096`. Today this does not fire: the longest example in
   `train_merged.jsonl` is 832 characters (roughly 280..420 tokens), a 2× margin.
   But this is the exact same pattern that caused the original EOS bug: the guard
   checks a different path than the one training takes. Having `check_eos()` use
   `args.max_len` is enough — then if `--base` or the data changes, EOS truncation
   will be caught rather than discovered after eight GPU hours.

5. **Be aware of the distribution skew.** In `train_merged.jsonl`, graphs of size
   16..24 make up 14.6% of examples; in `eval_wide.jsonl`, 42%. Training is lighter
   on large graphs than the evaluation. This is not a reason to rebuild the dataset
   (rebuilding changes the experiment and invalidates comparison with Run 1), but it
   explains why the residual size effect may not close completely.

## What NOT to do before Run 2

Listed not for completeness, but because each item looks reasonable and invalidates
the measurement if done now.

- **Adding combination bans (clusters) to the model.** Changing the profile changes
  the rules of the task, which invalidates both the adapter and both columns of the
  run table. RUNBOOK already fixes this; the measurement is done and guarded in
  `probe_matrix.py` — that is enough until Run 2 finishes.
- **Rebuilding `train_merged.jsonl`** (rebalancing by size, adding data). Run 2 is
  designed to answer a single question; changing the data underneath it turns it into
  "something improved, unclear why" — the exact mistake Run 1 was isolated to avoid.
- **Integrating the adapter into `vliw/learned/scheduler.py`.** There is nothing to
  integrate yet: the Run 1 model outputs illegal schedules on 61% of the wide eval.
  After Run 2 — meaningful.
- **Checking latencies on live Elbrus hardware, porting to Hexagon, cleaning up
  scenario style.** All useful and all orthogonal: zero impact on Run 2.

## How to verify that Run 2 succeeded

The prediction is phrased so it can be falsified.

- **The "resource" category on `eval_wide` must collapse** from 59% to single-digit
  percentages. This is the direct test: the model sees STORE for the first time and
  sees it only on `,2`/`,5`. If "resource" stays high, the issue is not operation
  vocabulary, and the entire analysis above is wrong.
- **`eval_wide` "valid" will rise, though unlikely to the narrow-eval level.**
  A reasonable target is 60..85%: the residual size effect (45% on 16..24 graphs
  even without STORE) is not going away, and training examples of that size are only
  14.6%. There is no basis to promise 97%.
- **`eval.jsonl` (narrow) will barely move** — it has no STORE, so this eval does
  not test the hypothesis at all. If it suddenly drops, training from scratch lost
  something the Run 1 adapter had.
- **Check the with-STORE / without-STORE breakdown**, not just size buckets (item 3).

## What this analysis does NOT prove

That STORE will be placed correctly after Run 2. All that has been shown is that
the model had never seen it, and that the new data contains it and labels it legally.
That makes the hypothesis plausible, not confirmed: the number comes from measurement.
