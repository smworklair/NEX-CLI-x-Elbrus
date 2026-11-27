"""VLIW instruction scheduler (Elbrus e2k-v6): exact scheduling as the
primary result; model training is an experimental track with a negative
outcome (see README "What is measured here").

Packages:
  vliw.core     — logic (machine model, DAG, schedulers, metrics, verification)
  vliw.ui       — visualization (colors, boxes, tables, logo)
  vliw.learned  — trained model: LoRA on top of Qwen2.5-3B, run via vliw/learned/runtime.py
  vliw.cli      — single entry point: command -> core -> ui -> print

Public project API comes from vliw.core (re-exported here for convenience).
"""

# Two representations of the same version by design. `__version__` is machine-readable
# per PEP 440 so packagers can parse and compare it as a version. `VERSION_LABEL` is
# human-readable for banners and labels: "0.8.0a1" in a header looks like a typo,
# whereas "0.8 alpha" immediately signals that the tool is still evolving.
#
# 0.7 — three full-screen modes on Textual.
# 0.8 — command layer redesign: commands grouped by task (help, "/" palette, and
#   --help show sections; "/help <command>" explains a single command); legacy curses
#   screen removed — full-screen is Textual-only; if unavailable, a setup screen is
#   printed (reason + pip command), while line-by-line mode is enabled explicitly via `--plain`.
# 0.9 — working with REAL code, not just synthetic scenarios:
#   · fourth full-screen tab CODE — open your own `.s` file, inspect parsed ops,
#     compiler schedule, and linter diagnostics directly on source lines;
#   · `lcc` output parser brought up to real files: speculative operations (`,sm`)
#     are no longer dropped, unknown mnemonics are not misclassified as addition,
#     and control ops do not occupy ALU channels (see docs/REAL_VS_SYNTH.md);
#   · trained model runs locally without GPU (`/learned`), with channel repair
#     and best-of-N sampling (`--best-of`).
# Alpha: layouts are still subject to change.
# 1.1 — ensemble instead of a solo model: HQ and connection in separate blocks,
#   15 providers via vliw/agent/backends/, TINY AI 284/300 (portfolio of 9 opinions),
#   changelog, and first tag.
# 1.1.1 — fast TINY AI (TinyFastScheduler), "per-block" mode for real `.s` files,
#   and eval_real suite; behavior of existing schedulers unchanged.
# 1.2 — NNL cores (nnl_vliw/): first test of NNL architecture on portfolio group selection.
# 1.3 — NNL cores (nnl_vliw/): first test of NNL architecture on portfolio group selection.
# 1.3.1 — NNL AI removed from CLI itself (TINY AI remains in the panel and agent context);
#   "exotic" glyphs replaced with safe ones, Windows console switched to UTF-8.
# 1.4 — license switched to source-available: free for learning and personal use,
#   commercial use by agreement; clarified NNL's role (nex_core is active,
#   nnl_vliw/nnl_isa are experiments); documentation organized into a reading path.
# 1.5 — full English localization of the TUI, CLI, core diagnostics, docs, and visuals.

__version__ = "1.5"
VERSION_LABEL = "1.5"

from .core import (
    DAG,
    DEFAULT_PROFILE,
    PROFILES,
    SCENARIOS,
    Candidate,
    DecisionStep,
    GreedyListScheduler,
    MachineModel,
    OracleScheduler,
    Schedule,
    Scheduler,
    SchedulingResult,
    compute_metrics,
    get_profile,
    get_scenario,
    list_schedule,
    random_dag,
)

__all__ = [
    "Candidate",
    "DecisionStep",
    "Scheduler",
    "SchedulingResult",
    "GreedyListScheduler",
    "list_schedule",
    "DAG",
    "SCENARIOS",
    "compute_metrics",
    "get_scenario",
    "random_dag",
    "DEFAULT_PROFILE",
    "PROFILES",
    "MachineModel",
    "get_profile",
    "OracleScheduler",
    "Schedule",
]
