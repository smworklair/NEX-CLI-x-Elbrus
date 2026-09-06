# CONTRIBUTING

Small, focused PRs are welcome.

## Setup

```bash
git clone <your-fork-url> vliw-ai-scheduler
cd vliw-ai-scheduler
pip install -e ".[tui]"
python -m unittest discover -s tests
```

## What to know before editing

- Core scheduler lives in `vliw/core/` (`baseline.py`, `oracle.py`,
  `schedule.py`, `model.py`). It has no third-party dependencies —
  please keep it that way.
- `vliw/tui/` is optional (works without `textual`, tests skip then).
- `vliw/learned/` + `training/` is the model track, optional
  (works without `torch`, tests skip then).
- Many code comments are in Russian; English PRs and comments are fine.
- `real_candidates_100_400/asm/*.s` are small fixtures used by
  `tests/test_ux_walk.py`. The rest of `real_candidates_100_400/`
  is local-only data (gigabytes) and stays out of git.

## Checks

- `python -m unittest discover -s tests` must stay green.
  Skips without `torch`/`textual` are expected, not failures.
- New behavior needs a regression test under `tests/`.
- Do not commit secrets (`.env` is git-ignored for a reason),
  weights (`*.safetensors`), or local PDFs under `docs/`.

## License

By contributing you agree your changes are MIT-licensed like the rest.
