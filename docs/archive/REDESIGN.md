# CODE Redesign: What Was Deferred to the Next Pass

This document tracks what was **deliberately not built**: ideas that have merit, but
have neither a finished shape nor an answer to "why does this belong in a VLIW bundle
scheduler". Everything added here must carry its cost and risk — otherwise the list
turns into a wish-list dumping ground.

What was built lives in the code and in `git log`; this file is about what was not.

## Marked ALPHA and already in the UI

### Right-hand explorer (^E)

Present: single folder listing, entering subdirectories, `..` up, recursive name search
(4 levels deep, up to 60 hits), deleting your own file via ✕ with confirmation. Closed
by default.

Why alpha: it is the first step toward "bring your own `.s` without knowing commands".
There is not yet any folder history, bookmarks, type filter, or opening with Enter from
the keyboard — mouse only. Search walks the tree on every keystroke; on a large
directory that is noticeable.

What must NOT appear in it: a full-featured file manager. The tool is about schedules,
not files; a permanent folder column steals horizontal space from what the screen is
actually opened for.

**Revised on 05.09.2026, see "New philosophy" below.** That restriction was written
before the "content determines the tool" idea and directly contradicts it: there, the
opened folder changes the entire set of available tools rather than merely listing
files. Kept here as a reminder that the old rule no longer applies on its own — the
decision was explicitly overturned, not forgotten.

## New philosophy: content determines the tool, not the other way around

"One tab, file search, you open a file, the system looks at what kind of file it is and
opens the corresponding tools... Open a folder with cycles — you get the analysis
toolkit. Open Python in a new one — you only see Python files without clutter. Want to —
add a window. Want to — dock two windows side by side for viewing. Want to — add a
compiler: compiler on the left, NEX CLI counting cycles on the right."

The starting point was Steam (Valve's earlier, broader concept, not fully understood,
but inspiring). Closer and more accurate in practice are two well-known precedents from
the UNIX world, both worth knowing before designing this from scratch:

* **Acme** (Rob Pike, Plan 9). The `plumber` daemon: a selected text span (file path,
  `file.go:42`, URL) routes itself to the right handler — the user does not pick a
  program, the system decides from the content. Granularity there is a line/selection;
  here we propose folder/content-type granularity on the same principle.
* **Jef Raskin**, *The Humane Interface*, the `Archy` project. Thesis: an application
  is a prison for content; the system should decide which capabilities apply to a file
  rather than forcing you to choose a program first. A direct answer to "why haven't
  editors and IDEs fully added this" — Raskin argued it is not lack of imagination, but
  that IDE architecture and business models (product = "Tool A") structurally resist it.

### What is actually proposed

* a content classifier: not by file extension, but by meaning ("a folder with
  cycles/schedules" differs from "just a `.txt`");
* a registry of pluggable tools per content type (currently there is one tool —
  schedule analysis; a Python file should get a bare editor without CODE tabs that do
  not apply to it);
* on-demand window layout: open, dock two views together, close — instead of the fixed
  panel set we have now.

### Honestly about the scope of work

This is not an explorer extension, but two new architectural layers: a pluggable handler
system (today one is hardcoded — schedule analysis) and a window layout manager (today
the layout is fixed). This has to be built once and properly, otherwise every new
content type gets stitched on by hand — the exact way the six modes sprawled out that
we now want to get rid of (see "Dropping separate screens" below).

### Where to start if we take it on

By analogy with "Dropping separate screens": start with one hardcoded rule, not a
general classifier. `.s` → analysis (already exists), `.py` → bare editor without
unrelated tabs — and only once those work without interfering with each other,
generalize into a registry. Building a full Acme-style plumber up front is a sure way
to finish none of the parts.

### The compiler panel is the one piece already ready today

"Compiler on the left, NEX counting cycles on the right" is not blocked on engineering —
the backend for the right panel is built and independently re-verified on 05.09.2026 on
25 real kernels (`real_candidates_100_400/`): real `e2k-linux-cc -O3 -S`, parsing via
`vliw/core/asm_parser.py`, cycle counting via `list_schedule`. Only window layout is
missing, not the counting logic — that is less work than the classifier and window
manager above, and the closest thing to try first.

## Done along the way and worth remembering

### Model Headquarters in AGENT (18.09.2026)

The right column of AGENT was reorganized into four blocks, each expandable to full
screen with a double-click:

* **HQ** — the primary block. Mini: summary (how many connections and missions, latest
  task) + task input, sendable without expanding. Expanded: connections (which one runs
  the task), focus area with explanation, prompt addendum script, mission list (retry /
  remove), "clear completed".
* **CONNECTION** — compact mini-block replacing the overloaded MODEL panel: current
  provider, five one-click API buttons, key field + "connect". Expanded — step by step:
  provider → key → catalog. Catalog search is labeled honestly: it is only a list
  filter, Enter picks the first row.
* **WHAT THE AGENT SEES** and **TRACE** — as before, as separate panels.

Why this way instead of everything in one window: HQ used to live inside the expanded
MODEL view — without a connected model you couldn't even find it, and the mini panel
could neither pick an API nor accept a key. Now HQ is always visible, connections are
fixed right in the mini view, and the catalog stays out of the way.

Cost: on short terminals, four blocks do not fit in 24 rows, so there is a responsive
step-down (`nex.tcss`, after width rules): short — HQ shrinks to content, WHAT IT SEES
and TRACE thin out; very short — WHAT IT SEES hides completely (the expanded HQ's TAB
serves the same facts) and API buttons hide (key is typed into the field below).
Verified by `TestNothingFallsBelowTheFold` across five sizes — tuned purely in styles,
not code.

Covered by: `TestHeadquartersPanel` (7 tests: own block, expanded view with missions,
hint without connections, `hqclear`, switching API and entering key from mini without
disk writes, filter explanation); `test_hq.py` migrated to the new block. Full suite at
the time of writing: 547 tests, all green.

### Open question: synergy between HQ and tiny schedulers

Tiny schedulers (`vliw/tiny/`, tiny-1/2/3) and HQ are currently connected in one
direction: `tiny_facts()` in `agent/context.py` puts the tiny cycle count into context,
where both the dialog and HQ missions see it. The direction is honest: tiny runs
deterministically in milliseconds without an LLM, and the agent receives the finished
number and explains it. The reverse (a model advising the scheduler) would be
hallucination instead of search — forbidden by the same honesty rule from CAB that
awards portfolio ties to baseline rather than the model.

What could be added, from cheap to expensive:

1. A "tiny" area in HQ (one line in `hq.AREAS` + default question): the agent explains
   where tiny beat baseline and why. Cost — near zero; risk — an extra item in the
   area grid.
2. A tiny line in the HQ mini view ("tiny: 41 c. = baseline"): computed locally in
   milliseconds, no network needed, adding a third number beside baseline/oracle. Cost —
   one summary line and panel height; risk — noise when weights are absent (silently
   skip in that case, as `tiny_facts` already does).
3. Weights status in CONNECTION ("tiny: weights present/absent"): tiny is not an API
   and needs no key, yet today nowhere in the UI can you tell whether it is trained or
   falling back to baseline. Cost — reading two weight files; risk — confusion over
   "why isn't tiny in the provider list" (answer: it is not a connection, it is local
   computation — must be labeled clearly).

### Block snippets via "/" (`CodeScreen.SNIPPETS`)

Seven assembly snippets inserted into the buffer: empty wide instruction, four parallel
multiplications, the same four serialized, a dependent chain, division on the monopoly
channel, load with consumer, store.

These are not static text pastes, but ASSEMBLED for the current buffer: registers are
allocated from free ones (`_free_regs` checks what is already used), pauses are computed
from model latencies (`_pause_for`), and channels come from `channels_for`. The first
version pasted static text with hardcoded `%r10, %r11, %r20`, so a second insert caused
a write conflict in code the user never wrote. An ordinary snippet editor cannot do
this: it has neither buffer parsing nor a machine model.

The channels in them are not invented. The `<mnemonic>,<channel> <args>, <result>`
format and `nop N` semantics come from the MCST manual (release 1.2, p. 19). Legal
channels agreed across THREE independent sources:

| class | assembler probe | QEMU `alop.decode` |
|---|---|---|
| multiply | `,0 ,1 ,3 ,4` | mask `-0-` → alc0/1/3/4 |
| divide | `,5` only | mask `110` → alc5 only |
| load | `,0 ,2 ,3 ,5` | mask `--0` → alc0/2/3/5 |
| store | `,2 ,5` | mask `-10` → alc2/5 |
| arithmetic | all six | mask `---` → any |

This is the first independent external confirmation of the machine model: previously it
rested on assembler probing and checking against the MCST manual. Worth documenting as
a separate section in `docs/ISA.md`.

What snippets do NOT do: they do not pretend to be compiler output. Real `lcc` memory
addressing is written differently (`ldw,3 0x0, [ _f64,_lts0 a ], %r3`); here the short
form is a scheduling sandbox, not assembly-ready code.

## Deferred entirely

### Scripts alongside a block (`.py`)

Was in the UI for one day and **removed**: the tool could create a `.py` file, but
could not run it. A button that creates a file and stops there is not a feature, it is
a promise.

The reason worth bringing it back for: a script **generates** a block. It runs
`lcc -O3 -S`, extracts the target function, writes a `.s` file next to it — and it
opens as a tab. Then F5 on a script means "build my block", not "run Python".

What must be decided before bringing it back:
* where the interpreter comes from and what to do if it is missing;
* where output goes and how to handle a process that never terminates;
* how to distinguish "script crashed" from "script succeeded but produced no block".

### Dropping separate LAB / CORE / AGENT screens

Idea: since the dock tabs show the same thing, separate screens are redundant, and `^O`
with a mode picker even more so.

Why not done now: the tabs lack features that live only in the screens — finding
navigation (`n`/`N`), stepping through operations (`[` `]`), dependency chain (`c`),
view toggles (`z x p w`), cycle-by-cycle replay, and the machine matrix. Deleting the
screens today means deleting those features, not shrinking code.

Order if we take it on: first port the above into the tabs, then remove screens one by
one, each with its own test run.

### File types and a "canvas" around a block

Owner: "ideally in the left panel you can create files of different types… maybe we can
even drop the CORE block then." Right now `.s` and `.md` notes can be created;
everything else goes together with the scripts above.

Here sits a question that still has no answer: how does such a setup differ from an
ordinary editor, and what remains of the scheduler in it.

### Dragging side columns with the mouse

The bottom dock is draggable by its `╍╍╍` border (height persists for the session). The
left column and explorer have fixed widths.

### "Split panel" for the schedule

Owner's request, recorded verbatim: "for the schedule, yes, it would be nice to split
the panel." What exactly to split has not been clarified; ask before building.

## What lies beyond the UI boundary

There is nothing left to polish in CODE — progress is bottlenecked on hardware and data:

* **model on real Elbrus hardware.** Latencies and port occupancies were measured via
  `lcc` and the assembler; channels were verified against QEMU and the MCST manual.
  Nobody has measured anything on live silicon.
* **real `.s` of large functions.** The entire sample is synthetic, and that has already
  bitten us twice: the first machine model was built from a single listing and turned
  out wrong, and the first dataset contained no real problem (greedy sat at the optimum
  on 298 out of 300 graphs).
* **verifying `F6` by execution.** Nobody has run the oracle-rewritten code: only
  independent operations are reordered and `validate()` checks it, but hardware
  equivalence is unproven.
* **live terminal.** The entire redesign was tested headless via `App.run_test()` —
  not a single run in a real terminal session with mouse and color.

Until this is done, any new numbers in the UI are about the model, not the machine. The
tool states this honestly (source tags on every number in `model.py`), and that must
not change until we reach real hardware.
