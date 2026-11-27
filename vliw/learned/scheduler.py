"""Learned scheduler: same Scheduler protocol as baseline and oracle.

Previously this was a `NotImplementedError` stub and weights only ran on
Kaggle via standalone `training/validate_kaggle.py`.

Now runnable via `/learned` in CLI. Loading and generation live in `runtime.py`;
this module glues graph -> prompt -> response -> schedule -> validation.

HOW THIS SCHEDULER DIFFERS FROM BASELINE AND ORACLE
---------------------------------------------------
Baseline and oracle produce a VALID schedule by construction; any violation
is an internal bug. A learned model can place an op on an unsupported channel,
omit an instruction, or fail to stop (run 1 hit 33% valid on eval_wide).

Therefore `SchedulingResult` from here MAY contain an invalid schedule — not
a tool crash, but a measured outcome. Errors are never swallowed: they go into
`notes` and `search_stats` and are displayed by the CLI. Do not mix these into
the general `Session.results()` cache.

Prompt encoding comes from `training/encode.py` (the exact module used to build
the training dataset) to avoid silent train/inference drift (see
docs/archive/EOS_INCIDENT.md).
"""

from __future__ import annotations

import time

from ..core import (
    DAG,
    Done,
    Failed,
    MachineModel,
    Note,
    Placed,
    Repaired,
    SchedulingResult,
    Started,
    Token,
)
from ..core.schedule import Placement, Schedule

# Max tokens to wait for from the model. Longest reference in data is a
# 24-instruction graph (~400 tokens); add margin but cap it, because a
# model without EOS (qwen-vliw-lora adapter) will never stop on its own.
DEFAULT_MAX_NEW_TOKENS = 768


class LearnedScheduler:
    """Learned model as a scheduler. Implements the Scheduler protocol."""

    name = "AI scheduler (learned model)"
    kind = "learned"
    short = "learned"

    def __init__(self, adapter=None, backend=None,
                 max_new_tokens: int = DEFAULT_MAX_NEW_TOKENS,
                 device: str | None = None, repair: bool = False,
                 temperature: float = 0.0, seed: int | None = None,
                 constrained: bool = False, cab: bool = False):
        """`backend` may be injected directly (test hook).

        `repair=True` enables channel repair (see repair.py): model cycles
        stay intact while invalid channels are reassigned. The result is a
        HYBRID and labeled as such.

        `temperature`/`seed` control sampling for best-of-N (see bench.py).
        Stored as attributes rather than `schedule()` args because the
        Scheduler protocol is fixed. Default is deterministic greedy decoding.
        """
        self.cab = cab
        """CAB portfolio (see portfolio.py): builds several valid schedules from
        one model response and selects the shortest. OFF by default since it
        changes `result.schedule` from raw model output to portfolio winner."""
        self._adapter = adapter
        self._backend = backend
        self._device = device
        self.max_new_tokens = max_new_tokens
        self.repair = repair
        self.temperature = temperature
        self.seed = seed
        self.constrained = constrained
        """Constrain output with GBNF grammar (format + valid channels).

        Benchmark docs/archive/DIAG3.md: 84% valid vs 15% on the same adapter,
        74% at exact CP-SAT optimum. Grammar does not schedule; it only removes
        syntax and illegal-channel failures. OFF by default to preserve parity
        with unconstrained benchmarks.
        """

    # --- lazy loading ------------------------------------------------------

    def backend(self):
        if self._backend is None:
            from . import runtime

            adapter = self._adapter
            if adapter is None:
                adapter = runtime.resolve_adapter()
            if adapter is None:
                raise RuntimeError(
                    f"no trained weights found in {runtime.CHECKPOINTS}. "
                    "An adapter is a directory containing adapter_config.json and "
                    "adapter_model.safetensors.")
            self._adapter = adapter
            self._backend = runtime.make_backend(adapter, device=self._device)
        return self._backend

    @property
    def adapter(self):
        return self._adapter

    # --- scheduling --------------------------------------------------------

    def schedule_events(self, dag: DAG, model: MachineModel):
        """Stream model execution as events: tokens and LIVE grid updates.

        The grid fills incrementally during generation because the response
        format is line-based (one line per placement) and `decode_completion`
        parses line-by-line.

        Invalid placements are emitted alongside valid ones so the grid shows
        EXACTLY where the model erred before `validate()` renders the verdict.
        """
        from training.encode import decode_completion, encode_prompt

        from . import runtime

        yield Started(self.short, self.name)

        try:
            be = self.backend()
        except (RuntimeError, OSError, ImportError) as e:
            yield Failed(str(e))
            return

        yield Note(f"{getattr(be, 'name', '?')}"
                   + (f" · adapter {self._adapter.name}" if self._adapter else "")
                   + (" — first run is slow while weights load from disk"
                      if getattr(be, "slow_start", False) else ""))

        prompt = encode_prompt(dag, model)
        n = len(dag)
        t0 = time.monotonic()
        parts: list[str] = []
        line: list[str] = []
        seen: dict[int, tuple[int, int]] = {}

        def _flush_line() -> list[Placed]:
            """Completed line -> new or updated placements.

            Repeating the same placement is ignored to avoid flicker; a
            CHANGED placement for the same instruction emits an update.
            """
            text = "".join(line)
            line.clear()
            out: list[Placed] = []
            for i, (cycle, channel) in sorted(decode_completion(text).items()):
                if not (0 <= i < n) or seen.get(i) == (cycle, channel):
                    continue
                seen[i] = (cycle, channel)
                out.append(Placed(Placement(i, cycle, channel), live=True))
            return out

        gram = None
        if self.constrained:
            from .grammar import schedule_grammar
            gram = schedule_grammar(dag, model)
        gen = be.generate_events(
            prompt, self.max_new_tokens,
            **runtime.sampling_kwargs(self.temperature, self.seed, gram))
        try:
            for chunk in gen:
                parts.append(chunk)
                yield Token(chunk)
                for ch in chunk:
                    if ch == "\n":
                        yield from _flush_line()
                    else:
                        line.append(ch)
        except (RuntimeError, OSError, ImportError, TimeoutError) as e:
            yield Failed(f"failed to run model: {e}")
            return
        finally:
            # Close explicitly rather than relying on GC: kills the
            # llama.cpp subprocess and releases _GENERATE_LOCK. On cancel
            # (`close()` externally), GeneratorExit lands here, and
            # closing the nested generator is the only way not to leak
            # a multi-GB weight process.
            #
            # getattr instead of direct call: `generate_events()` contract is
            # an ITERABLE of chunks, not necessarily a generator. A backend
            # may return any iterable (as in tests), which might lack
            # `close()`.
            closer = getattr(gen, "close", None)
            if closer is not None:
                closer()

        yield from _flush_line()          # trailing line without newline

        raw = "".join(parts).split(runtime.END_MARKER)[0]
        res = self._assemble(dag, model, raw, time.monotonic() - t0)
        for i, was, now in res.search_stats.get("repair_moves", ()):
            yield Repaired(i, was, now)
        yield Done(res)

    def schedule(self, dag: DAG, model: MachineModel,
                 on_text=None) -> SchedulingResult:
        """Full response — legacy contract built on top of `schedule_events()`.

        `on_text(chunk)` is kept for line-mode and tests. New callers should
        use `schedule_events()` for live grid updates and cancellation.
        """
        res = None
        for ev in self.schedule_events(dag, model):
            if isinstance(ev, Token):
                if on_text:
                    on_text(ev.text)
            elif isinstance(ev, Done):
                res = ev.result
            elif isinstance(ev, Failed):
                # Legacy `schedule()` raised on failure and `cmd_learned`
                # catches it. Preserve this behavior verbatim.
                raise RuntimeError(ev.error)
        assert res is not None, "stream must terminate with Done or Failed"
        return res

    def _assemble(self, dag: DAG, model: MachineModel, raw: str,
                  elapsed: float) -> SchedulingResult:
        """Raw model response -> schedule, diagnostics, metrics."""
        from training.encode import clip_placements, decode_completion

        decoded = decode_completion(raw)
        keep, extra = clip_placements(decoded, len(dag))

        # Assemble schedule manually instead of build_schedule(): we need
        # to know exact out-of-range IDs emitted by the model and
        # which instructions were omitted, otherwise diagnostics just say "invalid".
        sched = Schedule(dag, model)
        for i, (cycle, channel) in sorted(keep.items()):
            sched.place(i, cycle, channel)

        missing = sorted(set(range(len(dag))) - set(keep))
        raw_errs = sched.validate()

        # Channel repair: only on complete answers — if an op was omitted,
        # a missing op cannot be fixed by reassigning channels.
        report = None
        errs = raw_errs
        if self.repair and not missing:
            from .repair import repair as _repair

            fixed, report = _repair(sched, model)
            fixed_errs = fixed.validate()
            # Keep repaired schedule only if it did not worsen errors: strict
            # verification, not blind trust — the repaired schedule must
            # pass the exact same validate() check.
            if len(fixed_errs) <= len(raw_errs):
                sched, errs = fixed, fixed_errs
            else:
                report = None

        # CAB: portfolio of candidates on the SAME response with zero
        # extra generation, since order and cycles are already produced.
        # See portfolio.py for details and honesty caveats.
        cab_rows: list = []
        cab_best = None
        if self.cab:
            from .portfolio import Variant, choose, variants

            mine = Variant(
                "model+channels" if (report is not None and report.touched)
                else "model",
                "channel repair on top of model output"
                if (report is not None and report.touched)
                else "raw model output",
                sched, tuple(errs))
            cab_rows = variants(dag, model, keep, extra=(mine,))
            cab_best = choose(cab_rows)
            # Winner becomes the result. The model's own response is first
            # in the portfolio and wins ties, so replacement happens
            # only when strictly shorter.
            sched = cab_best.schedule
            errs = list(cab_best.errors)

        notes = [
            f"model: {getattr(self.backend(), 'name', '?')}"
            + (f" · adapter {self._adapter.name}" if self._adapter else ""),
            f"generated in {elapsed:.1f} s, parsed lines: {len(decoded)}",
        ]
        if extra:
            notes.append(
                f"DID NOT STOP: {len(extra)} lines for nonexistent "
                f"instructions (id {extra[:6]}{'…' if len(extra) > 6 else ''}). "
                "The prefix may still be valid — see docs/archive/EOS_INCIDENT.md.")
        if missing:
            notes.append(f"UNPLACED instructions: {missing}")
        if report is not None and report.touched:
            notes.append(
                f"REPAIRED CHANNELS: {report.touched} "
                f"(model cycles untouched, makespan unchanged)")
            for i, was, now in report.moved[:6]:
                notes.append(f"  {dag[i].op} #{i}: channel {was} -> {now}")
            if len(report.moved) > 6:
                notes.append(f"  ... {len(report.moved) - 6} more")
        if cab_rows:
            notes.append(f"CAB PORTFOLIO, {len(cab_rows)} candidates:")
            for c in cab_rows:
                mark = "<-" if c is cab_best else "  "
                span = str(c.makespan) if c.schedule.complete else "-"
                notes.append(
                    f"  {mark} {c.name:14} {'valid' if c.legal else 'INVALID':9} "
                    f"cycles {span:>3}   {c.how}")
        if errs:
            notes.append(f"SCHEDULE INVALID, {len(errs)} violations:")
            notes.extend("  " + e for e in errs[:8])
            if len(errs) > 8:
                notes.append(f"  ... {len(errs) - 8} more")
        elif sched.complete:
            notes.append(f"schedule valid, makespan {sched.makespan}")

        return SchedulingResult(
            schedule=sched,
            notes=notes,
            optimal=None,          # model proves nothing
            search_stats={
                "raw": raw,
                "seconds": elapsed,
                "n_decoded": len(decoded),
                "extra": extra,
                "missing": missing,
                "errors": errs,
                # Use FINAL schedule rather than raw response: with portfolio
                # enabled, instructions omitted by the model are still placed,
                # so marking them invalid would undercount. Without portfolio,
                # `sched.complete` equals `not missing`, keeping prior numbers
                # unchanged.
                "valid": not errs and sched.complete,
                "complete": sched.complete,
                "repaired": report.touched if report is not None else 0,
                "repair_moves": report.moved if report is not None else [],
                "errors_before_repair": raw_errs,
                "cab": [
                    {"name": c.name, "legal": c.legal, "how": c.how,
                     "makespan": c.makespan if c.schedule.complete else None,
                     "won": c is cab_best}
                    for c in cab_rows
                ],
                "cab_winner": cab_best.name if cab_best is not None else None,
                # A tied win is not an improvement. "Model" is first in the
                # portfolio and takes ties (by design: never credit the
                # algorithm for ties), so reports must distinguish ties
                # from genuine wins over the heuristic.
                "cab_beat_greedy": bool(
                    cab_best is not None
                    and any(c.name == "greedy" and c.legal
                            and cab_best.makespan < c.makespan
                            for c in cab_rows)),
            },
        )
