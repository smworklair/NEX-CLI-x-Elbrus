# Contributing

Small, focused pull requests are welcome.

## Setup

```bash
git clone <your-fork-url>
cd NEX-CLI-x-Elbrus
pip install -e ".[tui]"
python -m unittest discover -s tests
```

## Key Architecture Notes

- The scheduler core lives in `vliw/core/` (`baseline.py`, `oracle.py`, `schedule.py`, `model.py`). It has zero third-party dependencies — please do not add any.
- `vliw/tui/` is an optional fullscreen interface. Without `textual`, its tests are skipped.
- `vliw/learned/` and `training/` are the historical learned-LLM track. Without `torch`, those tests are skipped.
- `vliw/tiny/` is the active learned scheduler — lightweight and primary.
- Code comments are mostly in Russian; English PRs and comments are welcome.
- `real_candidates_100_400/asm/*.s` are small test fixtures. Everything else in that directory is multi-gigabyte local data excluded from git.

## Checks

```bash
python -m unittest discover -s tests
```

The test suite must stay green. Skips when `torch`/`textual` are absent are expected, not failures.
New behavior requires a regression test in `tests/`.

Do not commit secrets (`.env` is in `.gitignore` for a reason), model weights (`*.safetensors`), or local PDFs.

## Documentation

- User guides live in `docs/`.
- Historical notes live in `docs/archive/`; they do not need to be updated when code changes.
- Table of contents: [`docs/README.md`](docs/README.md).

## License

By submitting a PR, you agree that your contributions are licensed under the same terms as the project (see [LICENSE](LICENSE)): free for educational and personal use, with commercial use requiring a separate agreement with the copyright holder.
