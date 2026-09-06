# QUICKSTART (English)

Get the calculator running in ~2 minutes.

## 1. Clone + Python

Requires Python 3.10+. No compiler toolchain needed (`lcc`, QEMU, LLVM
are NOT used anywhere).

```bash
git clone <your-fork-url> vliw-ai-scheduler
cd vliw-ai-scheduler
python3 --version  # must be 3.10+
```

## 2. Install

Core (scheduler + plain CLI) needs no dependencies:

```bash
pip install -e .
```

With the fullscreen TUI (recommended):

```bash
pip install -e ".[tui]"
```

For the learned-model track (heavy: torch/transformers):

```bash
pip install -e ".[learned]"
```

This installs the `vliw` command. Without install, `python -m vliw`
from the repo root works too.

## 3. Run

```bash
vliw run slotclash     # one command and exit
vliw compare           # baseline vs oracle side by side
vliw all               # summary over all scenarios
python -m vliw         # interactive loop (/help, /compare, /play, /exit)
```

Real `.s` through the TUI code editor: open the CODE mode, then
`/code load real_candidates_100_400/asm/poly_gemm.s`, then `F5`.
Expect a legal schedule in ~13 s (portfolio fallback) with an empty
`validate()`.

## 4. Test

```bash
python -m unittest discover -s tests
```

Skips without `torch` are normal (learned track not installed).
Skips without `textual` are normal too (fullscreen TUI not installed) —
install `.[tui]` to run those.
