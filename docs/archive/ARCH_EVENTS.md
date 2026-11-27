# Step 1: Scheduler Event Contract

Compiled on 20.08.2026 from the code, not from memory. Every claim below is verifiable
in the repository — file and line references are included.

## What we are fixing and why it is not "hook up /learned to Textual"

From the outside, the complaint sounds like: the trained model is wired into the wrong
interface, and in the main one it neither works nor renders. The root cause runs deeper.

The contract between the core and every interface (Textual `vliw/tui/`, line-by-line
REPL) is currently just one thing: **a command prints pre-formatted ANSI strings to
stdout**. For baseline, oracle, and doctor this works — they run in milliseconds.

The local model is the first thing that takes 30..60 seconds and emits its answer piece
by piece. And the contract cannot hold it:

- `vliw/tui/bridge.py:41` `run_command` wraps execution in `redirect_stdout` and returns
  the buffer **only after the command finishes**.
- Meanwhile, `vliw/cli.py:925-940` faithfully streams tokens via `print` +
  `sys.stdout.flush()` — commit 98d8f05 was made specifically for this ("show the model
  writing the schedule instead of 30 seconds of silence").

So streaming in the main interface is **invisible by construction**. The screen freezes,
then dumps a wall of text. With `/learned --bench 15`, it is the same thing, except for
eight minutes.

Collateral symptoms from the same root:

- `grep learned vliw/tui/` returns **zero matches**. The cloud agent (Mistral/Gemini)
  has a full screen with streaming, a trace, and a grounding panel; the local model has
  no screen, and it is missing from the hints in `lab_screen.py:111`.
- The model's schedule is rendered as plain text (`ui/learned_view.render_result`), not
  in the grid where baseline and oracle live. You cannot compare them visually in one
  grid, even though that is the entire point of the tool.
- Root cause: `LearnedScheduler.schedule(dag, machine, on_text=...)` — an extra kwarg
  that does not exist in the `Scheduler` protocol (`vliw/core/api.py`). The protocol has
  no progress, no streaming, and no cancellation. The model did not fit the contract, so
  it was bolted onto the side.

**Conclusion: fix the contract, not the wiring.**

## The finding that simplified the design

The model backend is already a subprocess. `vliw/learned/runtime.py:436-458` launches
`llama-completion` via `Popen` and reads stdout one character at a time in a
`while True` loop.

Three consequences follow:

1. Turning it into a generator means replacing `on_text(chunk)` with `yield Token(chunk)`.
   The loop already has the right shape; no threads or queues are needed.
2. Cancellation is **already written**: `finally` calls `proc.kill()`. On a generator,
   `gen.close()` raises `GeneratorExit` at the `yield` point, and the same `finally`
   runs. Cancellation comes for free and cleanly.
3. `on_text` was not architecture — it was a side effect of printing to stdout.

## Contract

Addition to `vliw/core/api.py`. Changes nothing existing.

```python
@dataclass(frozen=True)
class Started:   who: str; note: str = ""
@dataclass(frozen=True)
class Note:      text: str; level: str = "dim"      # what is currently Style.dim(...)
@dataclass(frozen=True)
class Token:     text: str                          # raw model stream
@dataclass(frozen=True)
class Step:      step: DecisionStep; live: bool     # scheduler decision
@dataclass(frozen=True)
class Placed:    placement: Placement; live: bool   # grid fill
@dataclass(frozen=True)
class Repaired:  instr: int; frm: int; to: int      # channel repair
@dataclass(frozen=True)
class Progress:  done: int; total: int; note: str   # bench, later qemu
@dataclass(frozen=True)
class Done:      result: SchedulingResult
@dataclass(frozen=True)
class Failed:    error: str


def stream(scheduler, dag, model) -> Iterator[SchedulerEvent]:
    """Single entry point. A scheduler without schedule_events() is wrapped by an adapter."""
    fn = getattr(scheduler, "schedule_events", None)
    if fn is not None:
        yield from fn(dag, model)
        return
    yield Started(scheduler.short)
    res = scheduler.schedule(dag, model)      # old contract — unchanged
    for st in res.trace:
        yield Step(st, live=False)
    for p in res.schedule.placements.values():
        yield Placed(p, live=False)
    yield Done(res)
```

Four properties this design is built to guarantee:

1. **The `Scheduler` protocol does not change.** The `core/api.py` docstring and
   README:43 promise: wrap your scheduler in a class with `schedule()` and everything
   works. The adapter in `stream()` preserves that promise. Baseline and oracle are
   untouched.
2. **`Placed` is separate from `Step`.** The model has no cycle-by-cycle reasoning and
   does not produce `DecisionStep`; it produces placements. The grid widget needs only
   `Placed`, and that single event works for all three schedulers.
3. **`live: bool` inside the event.** For baseline/oracle, animation is a replay of a
   finished `trace`, not "watching it think". The flag travels inside the event itself
   so the UI physically cannot lie about it.
4. **`Repaired` is a separate event.** Otherwise a repaired channel silently looks like
   the model's own work — the exact result-laundering that the `learned/scheduler.py`
   docstring warns against.

Line-by-line mode after this is `for ev in stream(...): print(render_event(ev))`,
bit-for-bit identical to current behavior. In Textual, a worker iterates the same
generator and calls `call_from_thread` per event; this pattern is already used in
`lab_screen.py:219`. `bridge.py` stays, but only for report commands (`/doctor`,
`/compare`, `/asm`): reports are text, schedulers are events.

## Persistent model process: llama-server — DONE

Implemented in `vliw/learned/server.py`, wired into `runtime.make_backend()` as first
priority. Below are measurements, not expectations. Machine: 12 logical cores, 7.5 GB
RAM, WSL2. Block `slotclash`, adapter `lora-eos`.

| | process per command | persistent server |
|---|---|---|
| full run | 32 s | **12.3 s** |
| first token | ~20 s | **0.09 s** (warm cache) |
| first run in session | 32 s | 19.5 s (7 s startup) |
| cancellation | process killed, next run 32 s again | server stays alive, next run 12.5 s |
| RSS | 3.5 GB during run | 3.5 GB resident |

Output matches line for line: same llama.cpp build, same weights, `temperature=0`.

Confirmed in practice:

- `--host <path>.sock` — UNIX socket works, no network ports at all.
- `--lora-init-without-apply` + `POST /lora-adapters` — hot adapter switching confirmed
  (`{"success":true}`, scales update). All inactive adapters are explicitly zeroed: two
  enabled adapters would add together, yielding a model nobody ever trained.
- The server returns **only the continuation**. The prompt-echo stripping heuristic
  (`tail = prompt[-40:]`) is not needed at all on this path.
- Dropping the connection cancels the task on the server while the server itself stays
  alive. Verified: cancel on the fifth placement, followed by a normal run.
- `atexit` cleans up the process: zero orphaned servers after exit.

### Side finding: use half as many threads as cores

The previous code used `os.cpu_count()` in full. Measurement (warm prompt cache):

| threads | time |
|---|---|
| 4 | 14.2 s |
| 6 | **12.5 s** |
| 8 | 12.8 s |
| 12 (before) | 20.0 s |

All logical cores was the worst option tested, by a wide margin: hyperthreading does
not add extra ALUs, and threads fight over cache and memory. Now `default_threads()` =
half of logical cores, capped at eight. Fixed for both llama.cpp paths, not just the
server.

## UI decisions made

Made on 20.08.2026.

- **The model lives both as a column and as its own screen.** A column in LAB alongside
  baseline and oracle is the basis for comparison; the MODEL screen provides deep
  analysis, bench, and adapter status.
- **Illegal schedules are shown raw, with red cells.** Repair is an explicit keypress
  action; afterward the status line changes to "hybrid".
- **Baseline/oracle animation is on demand, labeled "replay of completed analysis".**
  By default, the grid appears immediately.

### Consequence that must be accepted consciously

Today in the CLI the default is inverted: `repair` is on by default, and the model's raw
output hides behind `--pure` (`cli.py:857-860`). The "show raw" decision flips this.
To avoid having two truths in two modes, the default must be flipped **everywhere**:
raw output by default, `--repair` as an explicit flag.

This changes the observable behavior of an existing command. Recorded here so the change
is a deliberate decision rather than a side effect.

## Order of work

1. **Event contract + llama-server.** `core/api.py` (+events, +`stream()`),
   `learned/runtime.py` (generator instead of callback, server instead of process per
   command), `cli.py::cmd_learned` on top of `stream()`, new path for scheduler commands
   in `tui/screens/base.py`. Tests: generator, cancellation via `close()`, server
   liveness.
2. **Model as a first-class citizen:** third column in LAB + MODEL screen. Falls out
   of step 1 almost entirely.
3. **L1 — closed loop:** write side in `asm_parser` (currently read-only), emitting
   valid `.s` with our own schedule, running under `qemu-e2k-static`, measuring real
   cycles. Separate document.

About C: the only place where the language is noticeable at all is exact search in
`core/oracle.py`. That is a surgical replacement of one function guided by profiling,
not a project rewrite, and comes after item 3, not before.

## What this plan does NOT solve

- Does not improve model quality. The share of legal schedules (33..79% on the wide
  eval, see ROADMAP.md) is completely unaffected by changing the contract.
- Does not turn the project into a compiler. After step 3 it becomes an optimizing pass
  over `lcc` output — that is the honest name, and it is not the same thing.
- Does not answer whether a persistent server pays for its memory on a weak machine.
  Measure afterward rather than promising beforehand.
