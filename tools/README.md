# `tools/` — Helper Scripts

Everything here runs locally on CPU and requires nothing beyond `.venv` (the single exception is noted). Listed roughly in workflow order.

| script | what it does | when needed |
|---|---|---|
| `probe_matrix.py` | re-probes the port matrix against the real `e2k` assembler and compares with `vliw/core/model.py` | after any change to a machine profile |
| `vliw_gen.py` | generates "graph → schedule" examples via CP-SAT, provably optimal | when generating new data (requires `ortools`) |
| `validate_jsonl.py` | runs jsonl records through real `Schedule.validate()` and prints a summary | after generating or editing datasets |
| `build_split.py` | builds `train_merged.jsonl` and held-out `eval_wide.jsonl` (4..24 ops, stratified) | before training |
| `kaggle_prep.py` | assembles `build/kaggle/`: dataset + two kernel scripts | before uploading |
| `kaggle_push.sh` | uploads and runs; `pull` downloads dumps back, `status` checks without pushing | requires `~/.kaggle/kaggle.json` |
| `report_runs.py` | summarizes run dumps into a table with deltas and graph-size breakdown | after runs |
| `bench_bestof.py` | measures best-of-N locally over hours with resume-after-interrupt | testing hypotheses without Kaggle |
| `check_real_vs_synth.py` | compiles ordinary C programs with real `lcc` and compares the op vocabulary against training data | after parser or dataset changes |
| `collect_real_schedule.py` | standalone graph and schedule extractor from an external `.s` file | for external contributors without the repo |

`probe_matrix.py`, `validate_jsonl.py`, and `report_runs.py` are also available as `vliw` commands (`/verify`, `/validate`, `/report`) — same checks in-process without spawning a second Python. `kaggle_push.sh` is available as `/kaggle`. See [`../docs/CLI.md`](../docs/CLI.md#data).

## Standard Workflow

```bash
python tools/probe_matrix.py                              # hardware model hasn't drifted
python -m unittest discover -s tests -t .                 # code hasn't drifted
python tools/validate_jsonl.py train_merged.jsonl         # dataset is valid
tools/kaggle_push.sh                                      # step 0 on Kaggle
tools/kaggle_push.sh pull && python tools/report_runs.py  # aggregate results into table
```

Run order and what each step proves: [`../docs/archive/RUNBOOK_EOS.md`](../docs/archive/RUNBOOK_EOS.md).

## Intentional Quirks

`vliw_gen.py` imports constants from `vliw.core.model`, whereas `training/validate_kaggle.py` duplicates them inline. That is not an oversight: the validator must run on Kaggle where the `vliw` package is not installed, so it has to be self-contained. Any drift between the two is caught by `probe_matrix.py` and `tests/test_model.py`.
