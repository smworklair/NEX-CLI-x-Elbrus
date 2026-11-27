# Quick Start

> Stage 1 of 13 · [Roadmap](docs/README.md) · [CLI →](docs/CLI.md)

Up and running in a couple of minutes. Only **Python 3.10+** is required; `lcc`, QEMU, and Elbrus hardware are not needed.

## 1. Get the Code

```bash
git clone https://github.com/smworklair/NEX-CLI-x-Elbrus
cd NEX-CLI-x-Elbrus
python3 --version        # on Windows: python --version or py --version
```

## 2. Install

The core VLIW scheduler and plain-text mode have zero third-party dependencies:

```bash
pip install -e .
```

For the fullscreen TUI workspace (recommended):

```bash
pip install -e ".[tui]"  # rich + textual
```

Once installed, the `vliw` command is available on `PATH`; without installing, `python -m vliw` runs directly from the repository root.

## 3. Run

```bash
python -m vliw                 # mode selector: CODE / LAB / AGENT / CORE
python -m vliw run slotclash   # run one scenario and exit
python -m vliw compare         # greedy list scheduler vs. exact branch-and-bound oracle
python -m vliw all             # summary across all 17 scenarios
python -m vliw --plain         # line-by-line mode without fullscreen panels
```

Inside the workspace, slash commands drive the session: `/run slotclash`, `/compare`, `/doctor`, `/tiny`.
Full command reference: `/help` or `python -m vliw --help`.

## 4. Your Own `.s` File

Open **CODE** mode (`1` on the mode selector, or `--mode code`), load an assembly file:

```text
/load examples/probe.s
```

and press `F5`. This parses real `lcc` assembly into basic blocks and displays the VLIW bundle schedule, diagnostics, and comparison against the exact solver.
Details: [`docs/CODE_MODE.md`](docs/CODE_MODE.md).

## 5. Verify

```bash
python -m unittest discover -s tests
```

Skipped tests when `torch` (learned LLM) or `textual` (fullscreen TUI) is absent are expected, not failures.
Full dependency set: `pip install -e ".[tui,learned]"`.

## Troubleshooting

| symptom | what to do |
|---|---|
| `No module named vliw` | run from the repository root or execute `pip install -e .` |
| `python3` not found | on Windows, use `python` or `py` |
| setup assistant opens instead of the TUI | `textual` is not installed; confirm the prompt to install it automatically |
| garbled non-ASCII characters | update the repository: UTF-8 output is enabled automatically |
| agent replies without a model | expected: without an API key it answers strictly from computed schedule metrics |

More details: [`docs/CLI.md`](docs/CLI.md) and [`docs/WINDOWS.md`](docs/WINDOWS.md).
