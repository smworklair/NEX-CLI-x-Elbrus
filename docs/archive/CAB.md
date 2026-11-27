# CAB: A Portfolio of Legal Schedules from a Single Model Response

Stage one of two. Stage two — `SEED`, grafting the model into the oracle — is described
at the end; it builds on what CAB does and does not start without it.

> **All numbers below are on SYNTHETIC graphs (the project generator, inside the
> model's training distribution), NOT on real `lcc` code.** On real code (graphs of
> 112–386 nodes from `lcc`, out of distribution) the benchmark is stricter and the
> result is different — negative: the model did not beat random search on a single one
> of 13 graphs. Both sets of numbers are real; this is not a contradiction, but a
> difference in conditions. Methodology and raw data for the real-code benchmark —
> [`real_candidates_100_400/model_eval/REPORT.md`](../../real_candidates_100_400/model_eval/REPORT.md).

## What changed substantively

Previously, the model had to act as an accountant: memorize the channel matrix, track
who occupied which channel in the current cycle, and compute operand readiness.
`docs/DIAG3.md` counted what that cost: 315 illegal channels, 208 conflicts, 26 unready
operands. Meanwhile, its scheduling was strong — out of 98 legal responses in Run 1,
ninety-seven were the EXACT CP-SAT optimum.

CAB takes the bookkeeping away from the model completely and leaves it with the one
thing it does well — **ordering**. Bookkeeping is handled by `list_schedule` from
`core/baseline.py`, which by construction never issues an instruction before its
predecessors and never puts two instructions on the same channel.

The consequence that justifies all of it: **the schedule is legal by mechanism, not by
luck.** There is no longer any need to prove legality.

## What exactly is taken from the model

| taken | how | what is discarded |
|---|---|---|
| order | sort by its own `(cycle, channel)` → `priority` vector | — |
| cycles | its cycles as `defer_until`, i.e., "no earlier than" | — |
| channels | **not taken at all** | its most frequent error |

Discarding channels is not a loss, it is the point: channels are what the model
confuses most often, and the scheduler picks them by cost anyway.

Anything the model failed to emit (truncated, lost format) goes to the tail of the
ordering and is sorted by `height`, i.e., the baseline rule. That gives graceful
degradation: the less the model managed to say, the closer the result falls back to the
heuristic rather than to randomness. An empty response yields exact baseline — locked
down by a test.

## Portfolio: nine candidates from two generations

Only one thing here is expensive — generation (~30 s per graph). Order and cycles are
already in that output, so every variant below is post-processing of ONE token stream,
without a single extra generation:

| candidate | whose work |
|---|---|
| `model` | raw response |
| `model+channels` | + channel repair (`repair.py`, bipartite matching) |
| `order` | model's order; cycles and channels from the scheduler |
| `order+cycles` | model's order, its cycles as "no earlier than", channels from the scheduler |
| `greedy` | baseline, model did not participate |

The same five from a second generation, grammar-constrained (`--constrained`). Plus
greedy runs in milliseconds. Selection uses `Schedule.validate()` and makespan: an
exact criterion with zero learned components.

Compare with best-of-N (`5b80506`): that spends N generations and throws away invalid
ones — for Run 2 under free generation, that is an 85% discard rate.

## Honesty rules without which the numbers would lie

1. **Makespan in "order" and "order+cycles" is a hybrid.** Cycles are assigned by the
   scheduler. Labeled in the UI as `CAB: <candidate>`, just as `repair.py` labels its
   hybrid.
2. **Legality rising to 100% says nothing about the model improving.** Legality here is
   definitional — a property of the mechanism. After CAB, compare not "how many are
   legal", but "how many cycles worse than the oracle".
3. **On tied cycles, the model's own response wins** — it comes first in the portfolio.
   Otherwise the algorithm would get credit for wins where it improved nothing.
4. **Off by default** (`/learned --cab`). All prior benchmarks were taken without the
   portfolio, and changing their meaning silently is forbidden — that is the exact
   mistake that left DIAG3's 84% living only in a report.

## Prediction recorded BEFORE measurement

Testing the mechanism on `slotclash` with a deliberately corrupted response (all
channels collapsed to `,0` — the exact DIAG3 failure) already produced a surprise:

| candidate | cycles |
|---|---|
| raw response | 22, but ILLEGAL (5 violations) |
| greedy | 23 |
| order | 23 |
| **order+cycles** | **22** — matches the proven oracle optimum |

**Order alone was not enough.** A greedy pass cannot HOLD an operation: sorting by
`(cycle, channel)` discards the "wait" decision that produced 22. `defer_until`
restores that information — and that is what separates 23 from 22.

Hence the prediction for live benchmarking: **`order+cycles` will systematically beat
`order`, and the gap will grow on graphs with monopoly ports** (division, `,5`),
because holding is the only way to save a cycle there. If the opposite happens, the
model's cycles are noisier than its ordering, which flips the entire CAB bet.

Caveat without which the table above is self-deception: the response in it was forged
from the oracle optimum with only the channels corrupted. That is a MECHANISM check,
not a benchmark. Real numbers come from `/learned --cab` and `/learned --bench N --cab`.

## Measurement on 30.08.2026 — and why it proves nothing

30 examples from `eval_wide.jsonl`, adapter `lora-merged` (Run 2), local llama.cpp.

| | legal | gap to optimum | exact optimum |
|---|---|---|---|
| grammar | 29/30 (97%) | 0.45 c. | 23/29 |
| grammar + CAB | **30/30 (100%)** | **0.00 c.** | **30/30** |

Looks like a total victory. It is not, and here is why.

**The greedy heuristic on the same data, in milliseconds:**

| dataset | greedy exact optimum | mean gap |
|---|---|---|
| `eval_wide.jsonl`, 300 | **298/300 (99.3%)** | 0.007 c. |
| `eval.jsonl`, 300 | **300/300 (100%)** | 0.000 c. |
| the same 30 as in the benchmark | **30/30** | 0.000 c. |

That means on both project datasets, **baseline already sits at the proven optimum
almost everywhere**. There is nothing left to win. CAB's zero is the zero of the
baseline sitting inside the portfolio; the model could add nothing because there was
nothing to add. 477 seconds of model runtime versus milliseconds of a heuristic for the
exact same answer.

Cross-checks required before accepting this conclusion:

* `meta.makespan` in the eval is the **proven CP-SAT optimum**, not a heuristic
  (`tools/vliw_gen.py`, file header and `schedule_optimal`);
* the machine profile matches: the project's oracle on the current `model.py` returned
  exact `meta.makespan` on 15 out of 15 examples. The recent latency update
  (LOAD 2→5, DIV 13→11) did not desynchronize the eval.

This is the exact situation `vliw/core/oracle.py` described in its header long before
the model existed:

> The gap between baseline and this ceiling is the budget worth fighting for with a
> trained model. **If there is no gap, the heuristic is already optimal, and there is
> nothing to learn on this graph.**

There is no budget. Across all of `eval_wide`, it exists on exactly **two graphs out of
300** (n=17 and n=19, one cycle each). The training set was generated by the same
`vliw_gen.py`, so it is almost certainly the same there: the model was trained to
reproduce schedules that the greedy heuristic already finds on its own.

### What this implies for CAB

The mechanism works and is verified: legality by construction, fallback to baseline,
zero cost. However, **CAB's potential cannot be measured on zero-gap data** — any
algorithm on top of the model will simply score baseline here.

The bottleneck is neither the algorithmic layer nor the model. It is the data.

### What is needed to make benchmarking meaningful

The generator must emit graphs with a real baseline↔optimum gap — like the handcrafted
`slotclash` (monopoly port occupied by a less urgent operation). The filter is ready
and costs milliseconds: generate a graph, run greedy and CP-SAT, keep only those where
`greedy > optimum`.

Separately — real `lcc` code: hundreds of operations, exact search is hopeless, and a
gap is guaranteed to exist. See `tools/collect_real_schedule.py`.

## Gap filter — built and measured (31.08.2026)

`vliw/core/hardness.py` + `/hard` command. Inside the app, not an external script.

    /hard                    gap on the current graph
    /hard --survey 200       share of hard graphs among random ones
    /hard --harvest 50       harvest hard graphs into JSONL

`measure()` returns `baseline`, `optimum`, `proven`, and the optimal schedule itself —
a ready-made ground truth for a training example. Caution is one-sided: a graph with an
UNPROVEN optimum is not counted as hard. Skipping a hard graph loses one example;
labeling an unproven one as hard poisons the dataset with a target that may itself be
worse than optimal.

### What makes a graph hard: not size, but contention for a narrow port

Share of graphs with a `greedy > optimum` gap, 300 graphs per mix:

| operation mix | hard |
|---|---|
| current (DIV 3%) | 1.0% |
| DIV 15% | 2.3% |
| DIV 15%, STORE 20% | 2.7% |
| **pressure on `,5`: DIV 20, STORE 26, LOAD 20** | **6.3%** |

The reason is direct: `DIV` executes ONLY on `,5`, `STORE` on `,2` and `,5`, `LOAD` on
`,0 ,2 ,3 ,5`. While DIV is 3% of operations, contention for the monopoly port simply
never happens, and the greedy heuristic is optimal. The mix is recorded in
`tools/vliw_gen.py:PRESSURE_WEIGHTS`, and weights became an argument to `gen_graph`
rather than a module-level constant.

### Size also helps — and hits the oracle wall

Under the pressure mix:

| n | optimum proven | with gap | share | sec/graph |
|---|---|---|---|---|
| 12 | 120/120 | 1 | 0.8% | 0.00 |
| 16 | 120/120 | 8 | 6.7% | 0.01 |
| 20 | 120/120 | 14 | **11.7%** | 0.13 |
| 24 | 115/120 | 12 | 10.4% | 0.61 |
| 28 | 47/50 | 4 | 8.5% | 0.72 |
| 32 | 43/50 | 8 | **18.6%** | 1.65 |

Hence the harvesting window **n = 16..24**: plenty of hard graphs, while the ground
truth is still provable and cheap. Above 24, the oracle starts missing budget (5 of 120
at n=24, 7 of 50 at n=32) and becomes nearly thirty times more expensive.

That is why both project datasets turned out empty: they were generated with 3% DIV on
n=4..24 graphs, concentrated in the small sizes.

### Verified on output

12 harvested examples: every target is legal, complete, equal to the recorded optimum,
and strictly shorter than the greedy schedule. Yield is 8.4% usable, ~5 CPU seconds per
saved example. For a 20,000-example dataset that is roughly one single-threaded CPU
day; graphs are independent, so the real answer is parallelism, not tweaking thresholds.

## Hard eval: `eval_hard.jsonl` (31.08.2026)

Harvested with `/hard --harvest 300 --jobs 11` in a minute and a half. Graphs are
independent, so processes give near-linear speedup: 20 examples single-threaded took
60 s, 11 processes took 7 s.

File verified in full: **300 examples, zero broken.** Every ground truth is legal,
complete, equal to the recorded optimum, and strictly shorter than greedy.

| | |
|---|---|
| sizes `n` | 16..24, mean 20.3 |
| shapes | chain 89, layer 71, mixed 84, wide 56 |
| gap greedy−optimum | 1 cycle on 291, 2 cycles on 9 |

**The baseline to beat now:**

> greedy heuristic — always legal, **exact optimum 0/300**, mean gap **1.030 cycles**.

Compare with `eval_wide.jsonl`, where the same heuristic hit optimum 298 times out of
300 with a 0.007 c. gap. For the first time in the project, the model has an opponent
instead of thin air.

A separate caveat that must not be lost: `PRESSURE_WEIGHTS` yields hard graphs at the
cost of distribution shift — DIV is ~20% of operations vs. single-digit percentages in
real `lcc` output. This set teaches the exact trap the project was built around, but
cannot be called realistic code. Keep it as a SEPARATE eval rather than replacing
`eval_wide`; the mixing ratio is a separate decision not yet made.

### Hard-eval measurement — the first where the model added something

30 examples of `eval_hard.jsonl`, adapter `lora-merged`, the exact same graphs in all
three rows:

| | legal | mean gap | exact optimum |
|---|---|---|---|
| greedy heuristic | 30/30 | 1.000 c. | **0/30** |
| model with grammar | 5/30 (17%) | 0.80 (among five) | 2/5 |
| **model + CAB** | **30/30** | **0.833 c.** | **5/30** |

Two takeaways, both important.

**First: CAB beat baseline.** 0.833 vs. 1.000 is exactly five cycles recovered across
thirty graphs. And not "on average": on five graphs the result matched the PROVEN
optimum, which the greedy heuristic never reaches on this eval by construction. That
means on those five, a model-generated candidate won rather than the greedy fallback.
This is the first measurement in the project where the model's contribution is isolated
from the heuristic's and turns out positive.

**Second: without CAB the model collapses on hard graphs.** 17% legal vs. 97% on
`eval_wide` — same adapter, same grammar. The graphs are larger (n=16..24) and denser
on the monopoly port, so the model can barely emit a hundred lines without a single
error. The legality guarantee stops being a convenience here: without it, 83% of
responses are simply unusable.

Arithmetic caveat: greedy sits inside the portfolio, so CAB **cannot** score worse than
1.000 in principle. "No worse than baseline" proves nothing on its own — the five hits
on the optimum are what prove it.

### Who actually won the portfolio

| candidate | wins | strictly better than greedy |
|---|---|---|
| greedy | 23 | — |
| model | 3 | 2 |
| order | 2 | **2** |
| model+channels | 1 | 0 |
| order+cycles | 1 | **1** |

Seven wins for model candidates — yet five improvements. The difference comes from the
tie-breaking rule: the model's raw response comes FIRST in the portfolio and claims
ties. That is intentional (never credit the algorithm for someone else's work), but it
means a "model" win can simply be a tie with the heuristic.

The breakdown follows unambiguously: "order" and "order+cycles" sit AFTER greedy, so
their wins can only be strict — that is 2 and 1. The remaining two improvements come
from the raw model response, while two "model" wins are ties.

After this measurement, the report learned to distinguish them:
`search_stats["cab_beat_greedy"]`, the "strictly better than greedy" column, and the
summary line "graphs beating heuristic: 5/30". Before the fix, the table labeled ties
as "model's work" — flattering in the exact way this entire document was written to
prevent.

**What this says about variants A and B.** "order" gave 2 improvements, "order+cycles"
gave 1. So A is not useless as `slotclash` made it look, nor is it the sole source:
two-thirds of improvements came from ordering, one-third from holding, and the raw model
response gave as many as ordering. Thirty graphs is too small to split those shares —
we need all 300.

### Full run: 300 hard graphs (31.08.2026, 117 minutes)

| | legal | mean gap | exact optimum |
|---|---|---|---|
| greedy heuristic | 300/300 | 1.030 c. | 0/300 |
| model + CAB | 300/300 | **0.82 c.** | **59/300** |

| candidate | wins | strictly better than greedy |
|---|---|---|
| greedy | 225 | — |
| model | 27 | 16 |
| **order** | 25 | **25** |
| **order+cycles** | 13 | **13** |
| model+channels | 10 | 7 |
| | | **total 61/300** |

**This refutes a conclusion drawn earlier in this very document.** From three graphs
and brute-forcing `slotclash`, the "order" variant had been declared structurally
limited and practically useless. On thirty graphs it looked no stronger than the raw
model response (2 improvements vs. 2). On three hundred, it is the LARGEST contributor:
25 improvements out of 61.

The limitation is still real: 200,000 random orderings on `slotclash` never reach the
optimum — only holding does. But monopoly-port trap graphs are a minority among hard
graphs, and on the rest ordering works best. The moral is the exact same as in
`docs/EOS_INCIDENT.md`: an error category is a hypothesis, not a fact, until counted
across a sample.

Overall score: **the model beats the heuristic on 20% of hard graphs**, adds nothing on
75%, and without CAB on the same data is legal 17% of the time.

## SEED built and measured — SEED-1 is dead (31.08.2026)

`vliw/core/oracle.py:Hint` + `vliw/learned/seed.py`. A hint enters exact search in two
ways: as an upper bound (only a legal complete schedule strictly shorter than baseline)
and as a priority vector for the portfolio engine. It cannot alter the oracle's answer —
locked down by four tests, including "illegal hint is ignored" and "incomplete hint is
ignored".

On `slotclash` it works transparently: the hint hit the lower bound, and optimality was
proven in **zero search nodes**.

### Yet the ceiling was measured, and it is 5%

Using the TRUE optimum as the hint — by definition no better hint exists. 60 graphs of
`eval_hard.jsonl`:

| | nodes | seconds | proven |
|---|---|---|---|
| without hint | 128,304 | 1.8 | 60/60 |
| with perfect upper bound | 121,804 | 1.6 | 60/60 |

**Savings: 5.1% of nodes and 7.6% of time — with a perfect hint.**

The cause is not hint quality, but search structure. Deepening goes BOTTOM-UP
(`for target in range(lb, ub)`), in this order:

* first, FAILED probes at low targets — they must be exhausted completely, and that is
  almost the entire cost;
* the very first successful probe ends the loop.

An upper bound only trims the tail of the loop, which is rarely reached anyway. Plus on
44 of 60 graphs (73%), the optimum EQUALS the lower bound — the first probe succeeds
immediately, so the oracle barely works even without a hint.

Hence a conclusion worth writing explicitly: **under bottom-up deepening, an upper-bound
hint is useless by construction.** For it to matter, search must go top-down or use UB
for pruning inside a probe — right now each probe prunes against its own `target`, not
against UB.

Practical outcome: paying 30 seconds of generation to save 5% of 30 milliseconds of
oracle time is pointless. SEED-1 is closed by measurement, not opinion. The mechanism
stays in the code — it costs nothing, breaks nothing, and is ready if search is ever
rewritten to go top-down.

### SEED-2 is untested and untestable on these data

The portfolio engine activates ONLY when exact search runs out of budget. On `eval_hard`
it never activated once: 60 of 60 were proven in 1.8 seconds total. Testing SEED-2
requires large graphs — real `lcc` output with hundreds of operations, where the oracle
is always hopeless. That is also the main catch: the model was trained on n=4..24 and
is out of distribution on such graphs.


## STORE is no longer an assumption (31.08.2026, response to external critique)

External critique (summarized via DeepSeek) pointed to a concrete gap rather than a
vague one: STORE latency and channel occupancy in `model.py` were set to `1` by
assumption, while STORE accounts for **25% of all dependency edges** in the hard eval
(908 of 3,633, measured). So that assumption was not a peripheral detail, but a direct
input to `ready_time` and thus to the makespan of half the metrics in this document.

The critique was right on the main point and wrong on the scale: out of 11 "assumed"
classes, only `AND`, `SHL`, `STORE` even appear in the synthetic generator
(`tools/vliw_gen.py`) — `MERGE`, `PACK`, `PRED`, `RW`, `AAU`, `COMBO`, `INSF`,
`PACKLOG` are not in it and affect zero numbers in this document. `AND`/`SHL` belong to
the same ALU group as the measured `ADD`/`SUB`, so risk there is low. The real
perimeter is a single parameter: STORE.

### Both quantities measured without hardware — using the method already in the project

**Channel occupancy — 1, confirmed twice.** A stream of independent stores to distinct
addresses (`examples/probes/store_burst.c`, same method as `mul_burst.c`/`div8.c`):
step between bundles is 1 cycle. Stronger still: using the same technique that extracted
the port matrix itself, we asked the assembler directly whether `stw,2` and `stw,5`
encode in ONE wide instruction. They do. The compiler is not even involved here;
hardware encoding answers directly.

**Latency — 2, was 1.** A store→load chain through ONE volatile cell
(`examples/probes/store_latency.c`): `volatile` forbids the compiler from reordering
store and load or eliminating the memory access, so the step in the listing reflects
forced store visibility, not scheduler whim. Same epistemic standard already used in
the project for `div_latency.c` and `load_latency.c`.

Honest caveat without which this would be self-deception in reverse: what was measured
is "store → load of the SAME address", while the synthetic graph generator builds
structural edges not tied to a real address. The number 2 is the best measured
order-of-magnitude estimate, not as tight as LOAD/MUL/DIV latency where the consumer is
literally the next op in a register chain.

### What moved — a number, not a fear

| | STORE=1 (before) | STORE=2 (measured) |
|---|---|---|
| exact proven optimum | 59/300 | **62/300** |
| beat heuristic | 59/300 | **63/300** |
| mean gap | 0.82 | 0.82 |

Closing the gap did not collapse the result — it slightly strengthened it. The winner
breakdown shifted sensibly: `order+cycles` rose from 13 to 31 wins because STORE
latency grew from 1 to 2 cycles — more graphs now require holding an operation near the
monopoly port, which is exactly what `order+cycles` can do and bare `order` cannot. A
more accurate machine model made the task slightly harder for greedy and slightly richer
for the algorithm responsible for holding.

`docs/ISA.md` regenerated: latency is now measured for **9 of 19 classes** (was 8).
`eval_hard.jsonl` rebuilt on the corrected model — the baseline barely changed (greedy
mean gap 1.027 cycles vs. previous 1.030), so the assumption did not distort the
qualitative conclusion, though it was a wrong number at the foundation of all CAB
calculations. The model's score on the new eval is running — once it finishes, the
number will be appended right here.

## Obsolete SEED plan (written BEFORE measurement, see section above)

`vliw/core/oracle.py` predicted this move in its own header long before the model
existed:

> PORTFOLIO (if exact search exceeds budget). We run the same greedy engine with
> hundreds of different priority vectors… Conceptually this is exactly what a trained
> model will do: sample good orderings instead of a single rigid rule.

And at `oracle.py:328` sits `rnd.uniform` on top of `height` plus random `defer` — the
exact same two arguments, `priority` and `defer_until`, that CAB produces. The model
drops into the place of `random.Random`, into a ready-made socket.

**SEED-1 — upper bound** (`oracle.py:357`): substitute the model's legalized schedule
in place of greedy. Line 382 has `if lb >= ub`, so if the model hits the lower bound,
optimality is proven **without a single search node**; `ctx.nodes` shows this. For
precision: deepening runs bottom-up, so a better UB does not skip expensive failed
probes at low targets. It gives three things — instant proof on hitting LB, a tighter
proven interval on timeout, and a shorter loop when the optimum equals UB.

**SEED-2 — portfolio vectors** (`oracle.py:313`): replace random jitter with the
model's ordering. This is the path that activates on LARGE graphs where exact search
exceeds budget — i.e., on real `lcc` output with hundreds of operations, it is the only
working path.

Why SEED is unambiguous: the comparison is sterile. Same engine, same budget, same
graphs; only the source of the priority vector differs — noise vs. model. Nothing else
can explain a difference in makespan.

## Code entry points

* `vliw/learned/portfolio.py` — `order_from_model`, `floor_from_model`, `variants`,
  `choose`. The docstring explains what is not here.
* `vliw/learned/scheduler.py` — `cab=` flag, portfolio assembly in `_assemble`, winner
  stored in `search_stats["cab"]` and `["cab_winner"]`.
* `vliw/ui/learned_view.py` — `CAB: <candidate>` label and candidate table.
* `tests/test_portfolio.py` — 11 tests; the main one verifies that a corrupted response
  still yields a legal schedule.
