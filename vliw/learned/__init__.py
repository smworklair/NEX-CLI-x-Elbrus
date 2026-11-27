"""Learned scheduling model: local execution over the same protocol.

`LearnedScheduler` implements the `Scheduler` protocol from `vliw.core.api` —
the same `schedule(dag, model) -> SchedulingResult` as baseline and oracle,
so CLI and visualization need no special handling for it.

One key difference: baseline and oracle produce a VALID schedule by
construction, whereas the learned model does not necessarily do so. Its
errors are never hidden; they are recorded in `notes`/`search_stats` and
printed. Details in
`scheduler.py`.

Heavy dependencies (torch/transformers/peft) are loaded lazily inside
`runtime.py`: `import vliw` does not require them, and without them the tool
works normally — simply without the `/learned` command.
"""

from .scheduler import LearnedScheduler

__all__ = ["LearnedScheduler"]
