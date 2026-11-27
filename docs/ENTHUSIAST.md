# Guide for Contributors and Tinkerers

> Stage 13 of 13 · [← Learned LLM](LEARNED.md) · [Roadmap](README.md) · [Archive →](archive/README.md)

The project is shared as-is, negative results included: the fine-tuned LLM does not beat random search on real code. A weak result is no reason to hide the code, though a map helps.

## What Do You Want to Do?

### Change the Interface

→ [`../vliw/tui/README.md`](../vliw/tui/README.md) — screen map, what is safe to modify, what can be ripped out wholesale, and where the boundary with the scheduling algorithm lies.

Screen behavior is documented separately: [`CODE_MODE.md`](CODE_MODE.md), [`LAB_MODE.md`](LAB_MODE.md).

### Train Your Own Model

Two paths, from cheap to expensive:

1. **TINY AI** → [`TINY.md`](TINY.md): an MLP with ~21K parameters, trains in minutes on CPU, runs inference on the Python standard library. This is the production scheduler, not an experiment.
2. **LoRA on an LLM** → [`LEARNED.md`](LEARNED.md): heavy historical track with gigabytes of weights and GPU requirements. Negative result on real code.

### Write Your Own Script

→ [`../tools/README.md`](../tools/README.md) — existing scripts and their contract: accept `argv`, return an exit code, stay self-contained.

### Understand How Schedules Are Computed

→ [`ISA.md`](ISA.md) — machine model; [`TINY.md`](TINY.md) — how the learned scheduler works.

## Where Not to Touch

`vliw/core/` — the greedy scheduler and exact search — is not meant for casual rewrites. Not out of possessiveness: the project's negative result was measured against this exact implementation. Changing it without care silently invalidates the measurements referenced throughout the documentation.

If you want your own scheduler, implement the `Scheduler` contract in [`../vliw/core/api.py`](../vliw/core/api.py). That is enough to build your own variant and benchmark it against the built-ins without touching the core.

## Checks

```bash
pip install -e ".[tui]"
python -m unittest discover -s tests
```

Skips when `torch` or `textual` are absent are normal. New behavior should ship with a regression test.

## Support

The project is free for personal and educational use and remains so. If it helped you: [pay.cloudtips.ru/p/7809ff65](https://pay.cloudtips.ru/p/7809ff65). Donations do not buy support or priority fixes.
