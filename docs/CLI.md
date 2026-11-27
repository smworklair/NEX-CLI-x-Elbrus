# CLI: Installation and Commands

> Stage 2 of 13 · [← Quick Start](../QUICKSTART.md) · [Roadmap](README.md) · [Methodology →](METHOD.md)

Quick reference for `vliw`. Mode-specific workflows live in dedicated guides:
[CODE](CODE_MODE.md), [LAB](LAB_MODE.md), [CORE](CORE_MODE.md), [AGENT](AGENT_PROMPTS.md).

## Requirements

- Python 3.10 or newer.
- Zero mandatory dependencies: the core scheduler and plain-text mode run on the standard library.
- `rich` and `textual` are required for the fullscreen workspace.
- `lcc`, QEMU, and Elbrus hardware are not required.

```bash
python3 --version          # Windows: python --version or py --version
```

## Installation

```bash
pip install -e .           # core + vliw command
pip install -e ".[tui]"    # + fullscreen interface (recommended)
pip install -e ".[learned]" # + learned LLM (torch/transformers, heavy)
```

Without installation, everything runs from the repository root via `python -m vliw ...`.
If `textual` is not installed, `python -m vliw` opens the setup assistant and offers to install it.

## Two Ways to Run

**One-shot** — runs a command and exits:

```bash
python -m vliw run slotclash
python -m vliw compare --no-color
python -m vliw all
```

**Interactive** — opens the workspace:

```bash
python -m vliw                 # mode selector
python -m vliw --mode code     # straight into CODE
python -m vliw lab             # straight into LAB
python -m vliw --plain         # line-by-line mode without fullscreen panels
```

Inside the workspace, commands take a leading slash: `/run slotclash`, `/compare`, `/help`.

## Global Flags

| flag | meaning |
|---|---|
| `--version` | print version and exit |
| `--profile {e2k-v6-measured,e2k-v6-firstprobe,naive_homogeneous}` | machine model profile |
| `--width N` | override issue-slot / functional-unit width |
| `--budget S` | exact solver time budget, seconds |
| `--portfolio S` | fallback portfolio search time budget, seconds |
| `--color` / `--no-color` | enable / disable color |
| `--theme NAME` | theme: `nex-dark`, `atlas`, `classic`, `kilo`, `nnl-purple` |
| `--mode {work,lab,mind,code,explore,chat}` | skip the mode selector |
| `--plain` | line-by-line mode without fullscreen TUI |

`explore` is an alias for LAB; `chat` is an alias for AGENT.

## Commands

### Scheduling

| command | what it does |
|---|---|
| `run <scenario>` | run a scenario: exact solver schedule and verdict |
| `compare [scenario] [--model]` | greedy list scheduler and exact solver side by side; `--model` adds the learned LLM |
| `tiny [scenario]` | TINY AI vs. greedy baseline and exact solver |
| `play [base\|oracle]` | step through the schedule cycle by cycle |
| `asm [base\|oracle]` | emit the schedule as `e2k { … }` VLIW bundles |
| `explain <cycle>` | explain why those operations were bundled into that cycle |

```bash
python -m vliw run slotclash
python -m vliw compare --no-color
python -m vliw tiny
```

### Graph and Diagnostics

| command | what it does |
|---|---|
| `path` | data-dependency graph (DAG) with critical path highlighted |
| `bounds` | theoretical makespan lower bounds (critical-path length vs. resource bound) |
| `doctor [base\|oracle]` | pinpoint where cycles are lost and why; `doctor N` for finding details |
| `analyze` | structured analysis: verdict, root cause, remediation plan |

### Machine Model

| command | what it does |
|---|---|
| `model [profile]` | functional-unit capability matrix; switch profile |
| `probe` | how `probe.c` calibrated the `e2k` machine model |
| `isa [--out FILE]` | reference: issue slots (channels), latencies, occupancy, sources |
| `verify [--show]` | re-probe the issue-slot matrix directly against the assembler |

### Runs and Benchmarks

| command | what it does |
|---|---|
| `scenarios` | list built-in scenarios |
| `random [N] [seed]` | generate and schedule a random DAG of N instructions |
| `all` | summary table across all 17 scenarios |
| `sweep [--seeds N]` | batch sweep across random graphs |
| `selfcheck [--seeds N]` | cross-check the exact branch-and-bound oracle against an independent brute-force solver |
| `hard [--survey N] [--harvest N] [--jobs N]` | check whether a graph has scheduling headroom (recoverable cycles) and harvest hard graphs |

### Agent and Training

| command | what it does |
|---|---|
| `ask <question>` | ask the agent a question |
| `ai [provider] [key=…] [model=…]` | view status and configure model for the current session |
| `key <key>` | set API key for the current session without writing to disk |
| `learned [--cab] [--constrained] [--bench N] [--data FILE] [--pure]` | run the learned LLM on the current graph |
| `agent` | show where a learned model plugs into the scheduling pipeline |

Keys and providers: [`AGENT_PROMPTS.md`](AGENT_PROMPTS.md) and [`ORCHESTRA.md`](ORCHESTRA.md).

### Data

| command | what it does |
|---|---|
| `code [run\|show\|save\|load\|clear]` | `e2k` source buffer |
| `load <file.s>` | load and parse a real `.s` file from `lcc` |
| `validate <file.jsonl…>` | verify jsonl records with `Schedule.validate()` |
| `report [--dir …]` | aggregate run dumps into a summary table |
| `kaggle [step0\|run1\|all\|pull\|status]` | upload / pull / check Kaggle jobs |

### Session

| command | what it does |
|---|---|
| `status` | session context: scenario, machine model, result |
| `theme [name]` | list and switch UI themes |
| `work` | interpreter reference |
| `docs` | what this prototype is and why it exists |
| `mode [work\|lab\|mind\|code]` | switch panel focus |
| `clear` | clear screen and return to mode selector |
| `help [command]` | list commands or show detailed help |

Aliases: `ls` → `scenarios`, `cmp` → `compare`, `r` → `run`, `cls` → `clear`.

## Interactive Input

- Leading `/` runs a command; without a slash, input goes to the active mode.
- `Tab` — autocomplete commands and arguments.
- `↑` / `↓` — command history (except on Windows without `readline`).
- `help <command>` — detailed help.
- `Ctrl+C` — interrupt; exit code 130.

## Exit Codes

| code | meaning |
|---|---|
| `0` | success |
| `1` | error: unknown command, scenario, or file, or unhandled exception |
| `130` | interrupted via `Ctrl+C` |

Handy for scripts and CI:

```bash
python -m vliw validate eval_real.jsonl && echo "all valid"
```

## Environment Variables

For the agent and scripts (keys are never written to disk):

| variable | meaning |
|---|---|
| `NEX_PROVIDER` | provider name, defaults to `mistral` |
| `NEX_API_KEY` | generic API key |
| `NEX_MODEL` | model name |
| `NEX_BASE_URL` | OpenAI-compatible server base URL |
| `NEX_LOCAL_URL`, `NEX_LOCAL_MODEL` | local server (Ollama / LM Studio / llama.cpp) |

Full list: [`.env.example`](../.env.example).

## Common Issues

| issue | fix |
|---|---|
| `No module named vliw` | run from the repository root or install with `pip install -e .` |
| `python3` not found | on Windows, use `python` or `py` |
| no colored output | check `--color`; color disables automatically when piped |
| setup assistant opens instead of TUI | install `.[tui]` or launch with `--plain` |
| no command history | Windows lacks `readline`; affects `--plain` only |
| assembler not found in `verify` | set `E2K_AS` or add `lcc` to `PATH` |

Windows specifics: [`WINDOWS.md`](WINDOWS.md).
