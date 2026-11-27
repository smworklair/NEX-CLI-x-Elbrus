# Research Journal

Chronology by date: what was tested, what turned out to be wrong, and why each decision
was made. Entries were written as work progressed rather than in hindsight, so they are
blunt in places — this is a working journal, not a polished report. Reports sit next to
it: [`CAB.md`](CAB.md), [`REAL_VS_SYNTH.md`](../REAL_VS_SYNTH.md),
[`DIAG2.md`](DIAG2.md), [`DIAG3.md`](DIAG3.md).

## August 30–31, 2026: the eval turned out to be empty, CAB, SEED closed by measurement

**Headline. Neither project benchmark contained an actual problem.** The greedy
heuristic sits at the PROVEN optimum on 298 out of 300 graphs in `eval_wide.jsonl` and
on all 300 in `eval.jsonl`. That means every previous comparison of the trained model —
DIAG2, DIAG3, the debate over Run 3 — was running against thin air: baseline is always
legal and almost always optimal there, in milliseconds versus hundreds of seconds for
the model. Cross-checked: `meta.makespan` is the proven CP-SAT optimum, and the machine
profile matches (the project's oracle matched `meta.makespan` 15 times out of 15).

Full analysis — [`CAB.md`](CAB.md), 380 lines. Do not rediscover this from scratch.

**What was built.**

* `vliw/learned/portfolio.py` — CAB: multiple LEGAL schedules from a single model
  response, selected by an exact criterion. `/learned --cab`.
* `vliw/core/hardness.py` + `/hard` — filter by the "greedy > optimum" gap, parallel
  harvesting (`--jobs`). Hardness comes not from graph size, but from contention on the
  monopoly port `,5`.
* `eval_hard.jsonl` — 300 hard examples, verified in full.
* `vliw/core/oracle.py:Hint` + `vliw/learned/seed.py` — SEED, hinting exact search.
* `/learned --bench N --data FILE` — benchmark decoupled from `eval_wide.jsonl`.

**Numbers on the hard eval (300 graphs, SYNTHETIC — project generator, in-distribution
for training):** greedy is 1.030 cycles from optimum, model+CAB is 0.82, exact optimum
on 59/300. The model beats the heuristic on 20% of graphs and adds nothing on 75%.
Without CAB it is legal 17% of the time (vs. 97% on the easy eval — that was a property
of the data, not the model). On real `lcc` code, out of distribution, the outcome is
different and negative — 0 out of 13, see
[`model_eval/REPORT.md`](../../real_candidates_100_400/model_eval/REPORT.md); this does
not contradict these numbers, it reflects different conditions.

**SEED-1 closed by measurement.** The ceiling is 5% of nodes even with a PERFECT hint,
because iterative deepening goes bottom-up and an upper bound only trims the cheap tail.
The mechanism stays in the code and will only start working if search is rewritten to
go top-down. SEED-2 (portfolio vectors) is untestable on this dataset: exact search
always finishes within budget.

**Two bugs caught along the way:** `--constrained` was being dropped when passed into
the benchmark (all previous "grammar-constrained" bench numbers were wrong); `valid`
was counted on the raw response rather than on the final schedule.

**What to decide next.**

1. A hard TRAINING dataset. The tooling is ready (`/hard --harvest --jobs`), ~1 CPU-day
   for 20,000 examples, no GPU needed. Right now the model has never seen a single hard
   graph in training — it was trained to imitate a heuristic and then evaluated on
   whether it beats that heuristic.
2. Mixing ratio. `PRESSURE_WEIGHTS` gives ~20% DIV operations versus single-digit
   percentages in real `lcc` output. Keep the hard set as a SEPARATE eval rather than
   replacing `eval_wide` with it.
3. SEED-2 on real `lcc` code — there the oracle is always hopeless and the portfolio
   engine actually runs. The catch: the model was trained on n=4..24 and is out of
   distribution on graphs of hundreds of operations.


## August 17–18, 2026: repository, EOS, two runs, CLI consolidation

**Repository rebuilt from scratch.** History was rewritten: `vliw/agent/llm.py` held
two API keys as literal strings in code (`EMBEDDED_KEYS`), which leaked into git. Now
no live secret ever enters code; the format is in `.env.example`. First commit of the
history — initial repository setup.

**Found and fixed the main training defect — the model did not know how to end its
response.** Three-quarters of the adapter's errors turned out not to be scheduling
errors, but a single missing token in the training data. Full post-mortem —
[`EOS_INCIDENT.md`](EOS_INCIDENT.md), run order — [`RUNBOOK_EOS.md`](RUNBOOK_EOS.md).
The moral is there too: an error category in a report is a classifier's hypothesis, not
a fact.

**Runs 0 and 1 completed on Kaggle.** Run 2 (from scratch on merged data) has not run
yet — it is expensive in quota and requires a separate decision.

| run | eval.jsonl (6..14) | eval_wide.jsonl (4..24) |
|---|---|---|
| 0. current adapter (no EOS) | 26.7% | 9.7% |
| 1. + EOS, old data | **97.7%** | 32.7% |
| 2. + EOS, merged data, from scratch | — | — |

Diagnosis confirmed: "tail" vanished almost entirely (was 54.3%), and the optimality
gap among legal prefixes fell from 0.48 to **0.02** cycles. On large graphs (16..24)
there is no movement — `resource` dominates there (the model confuses the channel
matrix), not stopping, and Run 2 is what fixes that.

**Everything useful from `tools/` wired into CLI commands** (18.08). The slash-command
dispatcher in `vliw/cli.py` is the single entry point, identical outside and inside the
REPL loop. Added `/verify`, `/validate`, `/report`, `/kaggle`; the logic stayed in
`tools/`, and the CLI only invokes it. Details —
[`CLI.md`](../CLI.md#обслуживание-проекта).

**Measured what is missing from the model: bans on OPERATION COMBINATIONS in a wide
instruction.** The assembler knows exactly two — a store on `,2` cannot pair with a
load on `,3`, and a store on `,5` cannot pair with a load on `,0`. These are the
"seams" between channel clusters, meaning machine clustering exists and is observable,
but as a structural ban rather than an inter-cluster latency. Inter-cluster latency
cannot be extracted with a local toolchain — why is verified and documented in
[`examples/probes/README.md`](../../examples/probes/README.md). The bans were
intentionally NOT added to the model: changing the profile would invalidate the adapter
and both columns of the table above (see RUNBOOK, "What is NOT in this run"). Measure
first, change the world model second.

**Fullscreen UI covered by tests.** `tests/test_tui_smoke.py` drives the app headless
(`App.run_test()`) — screens mount, keystrokes reach the input line, commands execute
in the core. Previously this had zero test coverage: `vliw.tui.available()` requires a
tty, so in scripts the TUI silently fell back to line mode. Total tests: 81.

## UI Overhaul (August 16, 2026) — version 0.7 alpha

Version bumped from 0.6 to `0.7.0a1` (`vliw/__init__.py`). Next to it sits
`VERSION_LABEL = "0.7 alpha"` — the human-readable string for banners and labels; the
machine version exists so versions can be compared programmatically. Displayed on the
mode picker screen, in the line-mode banner, and via `--version`. Alpha because the UI
has only been tested on one terminal and layouts will still change.

The interface was rewritten in [Textual](https://github.com/Textualize/textual) —
new package `vliw/tui/`. The old single-window curses screen (`vliw/ui/tui.py`) was
kept as a fallback when Textual is not installed.

Substantive changes:

1. **The three modes became three screens with their own layouts**, rather than three
   tabs of one window. No on-the-fly switching: exit a mode with `/clear` (or `^O`) to
   return to the picker. Side benefit — digits `1 2 3` stopped being hotkeys inside a
   mode and can be typed again (`2+2` in the interpreter used to switch tabs first).
2. **CORE** — workbench: evaluation tape on the left; live NAMES, MEMORY, and PROGRAM
   (block DAG) on the right. Expression values preview before Enter — evaluation runs
   on a copy of the workspace.
3. **LAB** — "cycles × channels" grid with a cursor; the WHY HERE panel explains the
   cell under the cursor, including empty cells (what we are waiting on, who holds the
   channel). On the right: NUMBERS, DIAGNOSIS, MACHINE; command reports in a separate
   panel.
4. **AGENT** — dialog with streaming output; on the right, WHAT THE AGENT SEES (the
   exact same numbers as in LAB) and a TRACE of actions it ran before answering.
5. Long computations (oracle, model requests) moved to background threads — the UI no
   longer freezes.

**Fixed a core bug along the way** (`vliw/core/interp.py`) exposed by the PROGRAM
panel: the block DAG was built in a second pass over the string with a regex, so
`x=load 0` added LOAD twice and `t=x*a+b` did not enter the graph at all (the regex
only knew one binary op). Now evaluation and DAG construction are a single recursion:
`_expr/_term/_factor` return both value and node. Values did not change; `selfcheck`
passes.

Separately on color: WSL sets `TERM=xterm-256color` without `COLORTERM`, so the UI
dropped to 256 colors and all surfaces merged into solid black.
`vliw/tui/__init__.py:prefer_truecolor()` injects `COLORTERM=truecolor` when the
terminal looks capable and leaves the variable untouched on `TERM=linux`/`dumb`. In
addition, surfaces are spaced so they remain distinct even in 256 colors (mapping to
grays 233/234/236/239).

The Elbrus emblem in the logo was redrawn to match the brand mark: two wings plus a
peak between them (`vliw/ui/logo.py:_MARK`), muted wings, accented peak. The sidebar
and hint bar toggle from the keyboard (`^B`, `^T`), and the input line sits in its own
bordered box.

Launch: `python3 -m venv .venv && .venv/bin/pip install textual`, then
`.venv/bin/python -m vliw`. Without Textual — the old screen; with `--plain` —
line-by-line mode.


## What this is

`vliw-ai-scheduler-demo` is a CLI tool demonstrating the gap between a greedy VLIW
instruction-scheduling heuristic and exact optimal search (oracle, branch-and-bound),
calibrated to the real Elbrus `e2k-v6` processor. Plus — in progress — a trained
(LoRA) scheduler model on top of Qwen.

Path: `~/vliw-ai-scheduler-demo` (WSL Ubuntu).

## What was done on August 16 (in order)

1. **Fixed `/clear`** in TUI — previously did not return to the app picker; now it
   does (`vliw/ui/tui.py`, `vliw/cli.py`).
2. **Added 7 new optimization-technique scenarios** (`vliw/core/dag.py`) — "as written"
   → "as it should be" pairs (`seqreduce`/`treereduce`, `divpressure`/`divstrength`,
   etc.).
3. **Found and fixed an error in the machine model.** The first version treated the
   multiplier as a monopoly (port `,0`, held for 8 cycles) — that turned out to be
   wrong. Probed the `lcc` assembler directly (not by reading compiler output, but by
   asking the assembler which channels physically accept an instruction): multiply
   executes on 4 channels, latency 4, pipelined. The only true monopoly is the divider
   (port `,5`), with latency 11 (not 13) and issue rate once every 2 cycles (not 13).
   Load has latency 5 (not 2), 4 channels. Store has only 2 channels.
   - Updated: `vliw/core/model.py`, README, `docs/CLI.md`, scenarios.
   - Refuted version kept as profile `e2k-v6-firstprobe` for contrast.
   - Actual probes and `lcc` output live in `examples/probes/` (the README there
     explains the methodology).
4. **MCST engineers (real chat) reviewed and corrected** — that is where the multiplier
   error was caught (Alex Bolt's query), which triggered item 3.
5. **Launched scheduler training** (`training/`):
   - `generate_dataset.py` — generates DAG → optimal schedule pairs using the project's
     own oracle (CPU-only, no ML dependencies).
   - `train_qlora.py` — QLoRA fine-tuning of Qwen2.5-3B-Instruct. Rewritten WITHOUT
     `trl` (after a cascade of transformers/trl/numpy incompatibilities) — plain
     `transformers.Trainer`.
   - Trained on Kaggle (free T4×2 GPU); adapter downloaded to
     `training/checkpoints/qwen-vliw-lora/`.
   - `validate_kaggle.py` — self-contained evaluation (without importing `vliw.core`,
     since Kaggle does not have the package). Patched for two environment bugs:
     incompatible `torchao` (disabled surgically) and `IndexError` on hallucinated
     instruction IDs (now simply marked invalid).
   - At the time, evaluation ran in the background and looked like a failure ("36%
     valid"). A day later it turned out three-quarters of the "failure" was the EOS
     bug, not scheduling quality. See the August 17–18 section above.

## What is NOT done / open loose ends

- **Run 2** (from scratch on `train_merged.jsonl`) has not been launched — expensive in
  quota, separate decision. It is what should close the gap on large graphs (16..24),
  where `resource` dominates rather than stopping.
- **Wide-instruction combination bans are measured, not yet in the model.** Not a
  cosmetic change: exact search in `vliw/core/oracle.py` relies on "a matching exists
  ⟺ the bundle is issuable", and pair bans break that property. Constructively fixable
  (at most two stores per cycle — enumerate their placements and strip the banned load
  channel before standard matching), verifiable via `/selfcheck` on the new profile.
  Order matters: Run 2 first, world-model change second — otherwise both the adapter
  and the run table become invalid.
- `docs/RUNBOOK_EOS.md` references `08_sverka_s_oficialnoy_tablicey_MCST.md` (audit
  against the official MCST table) — **that file is not in the repository**, dangling
  reference.
- `vliw/learned/scheduler.py` is still `NotImplementedError`. Integration of the
  trained adapter into the CLI itself has not started; waiting on evaluation results.
- `vliw/agent/llm.py` reads the key from `NEX_API_KEY` or `~/.config/nex/key`, and the
  provider from `NEX_PROVIDER` (`mistral` | `lechat` | `gemini`), format in
  `.env.example`. No more embedded keys in code: the old `EMBEDDED_KEYS` leaked into
  git, history rewritten 17.08.
- CLI prose style — some commands/descriptions sound "AI-written" (external feedback:
  English calques, ALL CAPS, "not X, but Y" phrasing). Fixed `wrap()` (paragraph
  wrapping) and rewrote 2 scenarios as examples; the other ~12 were left untouched —
  deliberately deferred.
- SSH access to a real Elbrus machine (granted by MCST for 6 months, port 8206) never
  worked; the private key went missing / was not found. Model latencies were extracted
  from COMPILER BEHAVIOR (`lcc`), not confirmed on live silicon.
- Next base-model candidates if Qwen2.5-3B struggles: `Qwen/Qwen3-4B` (same size class,
  stronger on STEM/coding benchmarks) or `Qwen2.5-Coder` — both plug in as a drop-in
  `--base` to the same `train_qlora.py`.

## Separate, unrelated project — also tracked

`betaNEX` (`C:\betaNEX`, Go platform, "modular monolith", OpenAI Hackathon submission) —
the README/DEVPOST states "Built with Codex & GPT-5.6", which by the author's own
admission is untrue, added retroactively for the submission. Agreed to fix it "later" —
not yet fixed.
