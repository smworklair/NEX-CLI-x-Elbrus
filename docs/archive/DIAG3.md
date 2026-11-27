# Constrained Generation on the Wide Eval: 2×2 Matrix

Measured on 30.08.2026 with the `vliw-diag3-wide` kernel. All of `eval_wide.jsonl` (300
examples, graphs of 4..24), two adapters, two generation modes — in a single kernel on
the same examples, so that differences between rows mean exactly what the row labels say.

## Result

| adapter | free generation | constrained |
|---|---|---|
| Run 1 (`lora-eos`) | 98/300 (33%) | 202/300 (67%) |
| Run 2 | 44/300 (15%) | **253/300 (84%)** |

The free-generation numbers reproduced the previously known ones (32.7% and 14.7%) —
the benchmark measures the same thing as before and can be trusted.

**The best cell in the matrix is Run 2 under constraints.** The very run that was
considered a failure.

## What this means for Run 3

Run 2 **did not fail training**. It trained BETTER than Run 1 — under constrained
generation, 84% vs. 67% on the exact same examples — and lost only because it failed
to emit the format (see `docs/DIAG2.md`: the leading `\n0: ` is dropped).

In other words, "do we need a third training run" was a question built on a false
premise. Training was not the problem. Decoding was the problem, and it can be fixed
without a single minute of GPU time.

## The prediction: half confirmed, and the second half is more useful

Before launching, we wrote down: constrained generation picks a channel only from
executable ones, so "operation on a channel that does not execute it" errors must
DROP TO ZERO.

| | illegal channel | channel conflict | operand not ready |
|---|---|---|---|
| Run 1, free | 315 | 144 | 26 |
| Run 1, constrained | **0** | 208 | 26 |
| Run 2, free | 2 | 1 | 3 |
| Run 2, constrained | **0** | 58 | 2 |

Illegal channels dropped to zero exactly as predicted — 315 → 0. Yet in the error-type
summary, the "resource" share did not fall, which at first looked like a refutation.
The reason is that the classifier lumps TWO distinct failures into "resource":

* **illegal channel** — the operation does not execute there at all. Constrained
  decoding eliminates this by construction;
* **channel conflict** — two operations picked the EXACT SAME legal channel in
  the same cycle. Constrained decoding does not eliminate this, and in places makes
  it worse (208 vs. 144 for Run 1): the mask narrows the choice to executable
  channels, increasing the probability that two operations pick the same one.

The mistake was in the wording of the prediction, not the mechanism: I equated
"85% resource errors" with "illegal channel", even though that was only two-thirds
of them.

## The direct next step

Constrained generation masks by `CHANNELS[op]` — where the operation is LEGAL.
It is missing the second condition: where the channel is still FREE in that cycle.
That is the exact difference why `repair.py` solves via bipartite matching rather
than greedily (see its docstring: ADD can execute on all six and may occupy `,2`,
leaving STORE with nowhere to go).

Combine them — and only one error class remains, "operand not ready" (26 and 2),
which neither approach handles: it is about cycles, and neither technique touches
cycles.

This closes the old "`--constrained` vs. `repair.py`" debate: they are neither
competitors nor duplicates. One provides a structural guarantee of channel legality;
the other provides a conflict-free assignment algorithm. Both are needed, in one place.
