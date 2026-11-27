# Changelog

Format: user-facing changes and the numbers backing them up.
Internal decision history lives in `docs/archive/JOURNAL.md` and `docs/TINY.md`.

## 1.5 (2026-11-27)

Full English localization of NEX CLI:

- **TUI, CLI, and core engine.** All Textual screens (`CODE`, `LAB`, `AGENT`, `CORE`, mode picker), CLI output, diagnostics (`doctor`), built-in help, and agent prompts translated into English.
- **Documentation and visuals.** All documentation (including archive), SVG diagrams, infographics, and README screenshots updated to English with live v1.5 TUI captures.

## 1.4 (2026-11-11)

License change and clarification of NNL's role. Schedulers are unchanged.

- **No longer MIT-licensed.** The project moved to a source-available license: free for educational and personal use; commercial and corporate use requires a separate paid agreement with the copyright holder. Full text: [LICENSE](LICENSE).
- **NNL's role documented honestly.** The active core is `nex_core/`: TINY AI is packaged into the scheduler NNL block, which serves the NEURAL NETS panel and the agent; the help assistant NNL block serves the setup assistant screen. `nnl_vliw/` and `nnl_isa/` are experiments (portfolio group selection and mnemonic classification) and are not wired into the CLI.
- **TINY Fast renamed to TINY Flash.** Class name is now `TinyFlashScheduler`; the old `TinyFastScheduler` name remains as a compatibility alias. The NEURAL NETS panel and `nex_core` now compute through it.
- **Documentation organized as a 13-stage roadmap** with three levels: understand, run, dive deeper. Added [`docs/METHOD.md`](docs/METHOD.md) — methodology and model boundaries on a single screen.

## 1.3 · Setup Assistant Screen and NNL Help Block

The screen shown when `textual` is missing is no longer a static reference page. It is now an interactive assistant: plain-language query or arrow-key selection → short plan with exact commands → confirmation → execution.

- Action menu: "Install and launch", "Check environment", "What is NEX CLI", "Ask a question", "Exit". Typing any letter immediately starts a question — no need to select "Ask a question" first.
- Built-in plans for launching, repairing, checking, updating, `venv` setup, and removal. Nothing executes before confirmation; removal is never executed automatically — only the commands are shown. During installation, the assistant installs `textual`/`rich`, falls back to `ensurepip` if `pip` is missing, and then launches `python -m vliw`.
- Answers are concise: full text is tucked behind "Details". A trained NNL help-assistant block (548 questions, 13 topic categories + chat + "off-topic", dev accuracy 0.655) handles installation and startup questions. Inference also runs in pure Python using the weight copy in `vliw/help_weights.json`.
- `--plain` / `--no-color` remain explicit line-by-line modes. When piped, the screen prints statically with the reason, commands, and exit code 1.

## 1.3 · NEX Core (merged into main)

Version number stayed 1.3. Direct calls to TINY AI in the UI and agent context were replaced by routing through the NNL core.

- `nex_core/` — a single NNL neural network (motherboard, cycle processor, solver from `nnl_vliw/NNL`, unmodified) with one composite scheduler block: TINY AI (`vliw/tiny/`, unmodified) + exact lower-bound rule. Externally it is a standard NNL block: passport, `веса.npz`, closed answer list; SHA-256 of TINY AI weights detects tampering.
- Core language: lossless conversion between instruction graph and tokens. The routing manifest (`nex_core/техкарта.json`) defines blocks, thresholds, and narrator phrases; adding a new block means adding a folder and a line in the manifest.
- The NEURAL NETS panel and agent obtain TINY AI schedules from the core; if the core fails to assemble, they fall back to the previous direct path.
- Verified: the NNL linter accepts the block; core output matches direct TINY AI calls across all scenarios; tampered weights are rejected; removing and restoring the block changes nothing; garbage input yields "don't know". Tests: `tests/test_nex_core.py` (9), 259 total with the rest of the suite.
- Currently the core has one block, so the bus is largely idle (no inter-block reads yet).

## 1.3.1 (2026-11-10)

UI cleanup; schedulers unchanged.

- **Documentation rewritten.** README, QUICKSTART, CLI, and mode guides were trimmed and checked against the code; historical notes moved to `docs/archive/`; stale numbers, links, and package version fixed.
- **NNL AI removed from the CLI itself.** The NEURAL NETS panel in LAB and the agent context now show only **TINY AI** (what TINY AI achieved on the scenario and across file blocks). The `nnl_vliw/` library and the assistant's NNL block remain — only the on-screen "estimator" that added no value in the CLI was removed.
- **Question marks replacing glyphs fixed.** "Exotic" Unicode glyphs (`▏ ▶ ▸ ❯ ✓ ✕ ⇄ ★ ● ⏳`, etc.) were replaced with safe characters (`│ > < + - x <> *`); panel borders use `solid` instead of `vkey`. Textual's own glyph sources were also fixed: `Input` drew `tall` borders with thin blocks (`▊ ▔ ▎ ▁`) and scrollbars used `▁▂▃…`; they now use single lines and the full block `█`. Rendering no longer breaks in older console fonts.
- **Unicode in a fresh `cmd`.** Windows console switches to UTF-8 and VT mode before the first output — no more mojibake or raw ANSI codes printed as text.
- Setup assistant screen: LEGO-style NNL header and compact top bar so the first screen fits in 30 lines.
- **Assistant distinguishes questions from commands.** "Why are extra installs needed" previously matched the "install" stem and triggered an install plan. Interrogative phrasing ("why", "what is", "how does", "do I need", "is it required"...) now routes to an explanation: the scheduler runs in pure Python, and `textual`/`rich` are only needed for fullscreen panels. Added a "how NNL understands questions" topic: small trained blocks plus keyword parsing, with no conversation memory — the full agent is separate and requires an API key.
- Tests: `tests/test_nnl_ai.py` rewritten for TINY AI; expected glyphs updated in `test_tui_smoke`, `test_ux_walk`, `test_encode`, `test_agent_backends`; `test_setup_screen` — 47 tests (including question recognition).

## 1.3 (2026-10-22)

Schedulers unchanged. Added a second network alongside TINY AI and a panel showing both.

### Two Neural Networks Running Automatically Without Commands

- **TINY AI** builds the block schedule; **NNL AI** (`nnl_vliw/выигрыш.py` cores) estimates whether the block has room for improvement. Computed on every new block and every agent question: `vliw/ai_hints.py`, NNL AI line in agent context (`vliw/agent/context.py`).
- **NEURAL NETS** panel in LAB: shows TINY AI results, NNL AI's estimate, and — if a `.s` file is loaded — a per-block breakdown (NNL estimate next to actual TINY AI cycles). On terminals shorter than 50 lines, the panel shrinks and scrolls so nothing overflows.
- New blocks: two cores of two blocks each (`nnl_vliw/блоки_выигрыш/`), trained on labels "portfolio shorter than greedy".

### What the Numbers Showed (Honestly)

- **Exact rule, not a neural network:** if baseline hits the lower bound, no gain is possible. On `eval_real` it filters out 883 of 947 graphs with zero errors; also correct on 15 of 17 built-in scenarios.
- **NNL cores** where the rule is silent: rank well on synthetic data (AUC 0.75), near random on real code (AUC 0.52 on 64 graphs, 43 of which have a gain). The panel labels the exact rule and core estimate separately.
- Tests: `tests/test_nnl_ai.py`; suite run (`test_nnl_ai`, `test_nnl_vliw`, `test_agent_grounding`, `test_tui_smoke`) — 213 tests.

## 1.2.0b1 (2026-10-22)

Additions only: existing scheduler code untouched.

### NNL in the Compiler Project (`nnl_vliw/`)

- Snapshot of the NNL core (motherboard, processor, core, solver, linter, bag-bus architecture, training code) at commit `6b0c9e0` of `smworklair/NNL`, plus a token language for VLIW graphs.
- Two cores of two blocks each (~100K and ~200K parameters), trained to select a TINY AI portfolio group; blocks pass the NNL linter; training takes seconds on CPU. Details and full numbers: `nnl_vliw/README.md`.
- Honest outcome: on par with standard classifiers on the same features, weak group selection, cross-core validation no better than random abstention; virtually no effect on real code (43 hard graphs out of 947).
- Tools: `tools/portfolio_labels.py` (best makespan per group), `tools/gen_graphs.py` (raw graphs from the project generator). Tests: `tests/test_nnl_vliw.py` (26).

## 1.1.1b1 (2026-10-21)

Additions only: existing scheduler code untouched.

### Fast TINY AI

- `TinyFastScheduler` (`vliw/tiny/fast.py`) produces the same makespan as `TinyScheduler`: 0 discrepancies across 3,061 graphs, all schedules valid, zero regressions vs. greedy. The `asm` mode (without hold/defer) is faster, though chosen empirically rather than guaranteed.
- Time per graph, ms (before → after): `eval_hard` 63.4 → 2.6, `eval_real` 70.4 → 0.95, `eval_wide` 39 → 0.49.
- Where the speed comes from: early stop at the lower bound, `ListPlan` list engine (`vliw/core/fastlist.py`), `FastNet` with row caching, lazy trace generation. ES reward does not affect runtime speed.

### Block Mode and `eval_real`

- `vliw/core/blocks.py`: parses real `lcc` `.s` output into basic blocks and windows. Tools: `tools/block_report.py`, `tools/tiny_fast_check.py`, `tools/make_eval_real.py`.
- `eval_real.jsonl`: 947 graphs with a proven optimum; `eval_real_open.jsonl`: 11 graphs where the bound was not reached.
- Optimal count on `eval_real`: greedy 890, TINY AI 927, without networks 919.
- Headroom on real code in the model is small: greedy loses 0.51% of cycles. These are model cycles, not hardware; `loop_mode` is not modeled.

### Tests and Documentation

- 76 new tests (`test_fastlist`, `test_tiny_fast`, `test_blocks`, `test_make_eval_real`); details and optional tweaks in `docs/archive/TINY_FAST.md`.

## 1.1.0b1 (2026-09-18)

### TINY AI: 219 → 284/300 Optimal

- Expanded portfolio: `prio_hold` (hold-head holds), `rule_hold` / `rule_hold_far` (handcrafted monopoly-port holds), `beam_d*` (beam over holds), default beam width 8 → 16.
- `eval_hard`: gap 0.270 → 0.053, wins over baseline 203 → 267.
- Real graphs (`tools/tiny_real_eval.py`): 5/13 → 7/13, 0 losses.
- Same order of magnitude in speed: ~75 ms on synthetic graphs, ~2.5 s on a 386-node graph.
- Weight pipeline: supervised → ES fine-tuning (`es.py --mode prio|hold`).
- Zero losses throughout: fuzz 1,437/1,437, unit tests green.
- Rejected with numbers: 20 features (overfit), hard-set mixing, 140K weights, gap-gate, ES fine-tuning of hold — details in `docs/TINY.md`.

### Agent: HQ and Connections Instead of a Single Window

- HQ — dedicated main block: summary and task in compact view; connections / scenario / script / missions in expanded view.
- CONNECTION — compact block: API buttons + key; catalog with honest filtering in expanded view. 15 providers via `vliw/agent/backends/`.
- Keys live in session memory only; catalog is mocked in tests.
- New doc: `docs/ORCHESTRA.md` (dialogue / HQ / connection / TINY AI, file map).

### Cleanup

- Removed `.presentation/` (marketing material, unreferenced anywhere in the repo).
- Normalized line endings to LF; added junk (`Zone.Identifier`, generator output) to `.gitignore`.

## 1.0.0b1

First public beta: core (baseline vs. oracle), CLI, TUI (CODE / LAB / CORE / AGENT), `e2k-v6` machine model measured from `lcc`, docs, and showcase of real `.s` files.
