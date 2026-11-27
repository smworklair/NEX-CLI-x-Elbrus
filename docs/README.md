# Documentation Roadmap

You don't need to read everything front to back. The roadmap has three levels — pick the one you need right now. Within each level, documents follow a sequence with back and next links.

If you are an Elbrus specialist who wants to verify the numbers immediately, jump straight to [`METHOD.md`](METHOD.md) (stage 3).

## Level 1. Understand the Project

**3–5 minutes. One document.**

| document | purpose |
|---|---|
| [`../README.md`](../README.md) | what NEX CLI does, its results, and its boundaries |

This is enough to grasp the core idea: Elbrus executes up to six operations per cycle, and NEX CLI compares ways to pack compiled `.s` code into wide instructions while honestly showing where gains exist and where they don't.

## Level 2. Run It

**10–15 minutes. Two documents, stages 1–2.**

| stage | document | purpose |
|---|---|---|
| 1 | [`../QUICKSTART.md`](../QUICKSTART.md) | clone, install, first launch, and first run |
| 2 | [`CLI.md`](CLI.md) | all commands, flags, exit codes, common issues |

After this, `python -m vliw` works on your machine and you know how to run scenarios. You don't have to read further — the tool is already usable.

## Level 3. Dive Deeper

**As needed. Stages 3–13; order only matters if reading straight through.**

| stage | document | when to open |
|---|---|---|
| 3 | [`METHOD.md`](METHOD.md) | check where the numbers come from and model boundaries |
| 4 | [`CODE_MODE.md`](CODE_MODE.md) | bring a real `.s` file from `lcc` and run it |
| 5 | [`LAB_MODE.md`](LAB_MODE.md) | inspect the cycles × channels grid and "why here" |
| 6 | [`CORE_MODE.md`](CORE_MODE.md) | see how a dependency graph is built |
| 7 | [`AGENT_PROMPTS.md`](AGENT_PROMPTS.md) | ask the agent and verify its answers |
| 8 | [`ORCHESTRA.md`](ORCHESTRA.md) | keys, providers, HQ, TINY AI |
| 9 | [`TINY.md`](TINY.md) | what TINY AI computes and how to retrain it |
| 10 | [`ISA.md`](ISA.md) | inspect the machine model: channels, latencies, sources |
| 11 | [`REAL_VS_SYNTH.md`](REAL_VS_SYNTH.md) | understand the gap between `lcc` output and synthetic data |
| 12 | [`LEARNED.md`](LEARNED.md) | read the history of the LLM track and its negative outcome |
| 13 | [`ENTHUSIAST.md`](ENTHUSIAST.md) | modify code, train your own model, dig further |

Landmarks: questioning the numbers — stages 3 and 10; training — stages 9 and 12; interface — stages 4–6 and 13.

## Side Branches

Not part of the linear path, but standalone references:

- [`WINDOWS.md`](WINDOWS.md) — Windows-specific differences (after stage 2).
- [`../CONTRIBUTING.md`](../CONTRIBUTING.md) — PR rules and checks (after stage 12).
- [`archive/`](archive/) — historical notes and negative results. Not user guides.
- Subproject maps: [`../vliw/tui/README.md`](../vliw/tui/README.md), [`../vliw/tiny/README.md`](../vliw/tiny/README.md), [`../tools/README.md`](../tools/README.md).
- NNL: active core — `nex_core/` (see [`TINY.md`](TINY.md)); experiments not wired into the CLI — [`../nnl_vliw/README.md`](../nnl_vliw/README.md), [`../nnl_isa/README.md`](../nnl_isa/README.md).

The main negative result is not hidden: on real code, the fine-tuned LLM fails to beat random search on any of the 13 graphs. Methodology and raw data: [`real_candidates_100_400/model_eval/REPORT.md`](../real_candidates_100_400/model_eval/REPORT.md).
