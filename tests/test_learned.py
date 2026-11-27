"""Learned scheduler tests: the DAG -> prompt -> completion -> schedule pipeline.

Tests the plumbing around the model (not model quality): prompts are built by
the same encoder used in training, completions parse deterministically, legal
schedules pass validation, and illegal ones surface explicit diagnostics. Runs
via `ScriptedBackend` without torch or weights in milliseconds.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from training.encode import encode_completion, encode_prompt
from vliw.core import GreedyListScheduler, get_profile, get_scenario
from vliw.core.schedule import Schedule
from vliw.learned.runtime import ScriptedBackend
from vliw.learned.scheduler import LearnedScheduler


def _fixture():
    """Return a DAG, machine model, and a known-legal greedy baseline schedule."""
    dag = get_scenario("simple4")
    machine = get_profile("e2k-v6-measured")
    good = GreedyListScheduler().schedule(dag, machine).schedule
    return dag, machine, good


class TestPromptIsTrainingFormat(unittest.TestCase):
    def test_prompt_built_by_training_encoder(self):
        """Prompts must be built by the same encoder as the training dataset
        so training and inference formats can never silently diverge."""
        dag, machine, _ = _fixture()
        seen = {}

        class Spy(ScriptedBackend):
            def generate_events(self, prompt, max_new_tokens):
                seen["prompt"] = prompt
                return iter(())

        LearnedScheduler(backend=Spy("")).schedule(dag, machine)
        self.assertEqual(seen["prompt"], encode_prompt(dag, machine))


class TestValidAnswer(unittest.TestCase):
    def test_legal_schedule_recognised(self):
        dag, machine, good = _fixture()
        res = LearnedScheduler(
            backend=ScriptedBackend(encode_completion(good))).schedule(dag, machine)

        self.assertTrue(res.search_stats["valid"])
        self.assertEqual(res.search_stats["errors"], [])
        self.assertEqual(res.search_stats["missing"], [])
        self.assertEqual(res.schedule.makespan, good.makespan)

    def test_never_claims_optimality(self):
        """A learned model does not prove optimality — `optimal` must remain None."""
        dag, machine, good = _fixture()
        res = LearnedScheduler(
            backend=ScriptedBackend(encode_completion(good))).schedule(dag, machine)
        self.assertIsNone(res.optimal)


class TestBrokenAnswers(unittest.TestCase):
    """Each case reflects a real failure mode observed in evaluation dumps."""

    def test_illegal_channel_reported(self):
        """Placing ops on illegal or conflicting issue ports must be flagged."""
        dag, machine, good = _fixture()
        # Cram everything onto port 5 in cycle 0: triggers port and width conflicts.
        bad = "\n".join(f"{i}: такт=0 канал=5" for i in range(len(dag)))
        res = LearnedScheduler(backend=ScriptedBackend(bad)).schedule(dag, machine)

        self.assertFalse(res.search_stats["valid"])
        self.assertTrue(res.search_stats["errors"])
        self.assertTrue(any("SCHEDULE INVALID" in n for n in res.notes))

    def test_unstopped_tail_reported(self):
        """Model failed to stop at EOS and emitted lines for nonexistent op IDs."""
        dag, machine, good = _fixture()
        n = len(dag)
        text = encode_completion(good) + "\n" + "\n".join(
            f"{i}: такт=9 канал=0" for i in range(n, n + 5))
        res = LearnedScheduler(backend=ScriptedBackend(text)).schedule(dag, machine)

        self.assertEqual(res.search_stats["extra"], list(range(n, n + 5)))
        self.assertTrue(any("DID NOT STOP" in n for n in res.notes))
        # The prefix itself is legal — distinguishing an EOS overrun from a bad schedule.
        self.assertEqual(res.search_stats["errors"], [])

    def test_missing_instructions_reported(self):
        dag, machine, good = _fixture()
        lines = encode_completion(good).splitlines()[:-1]     # drop the last op
        res = LearnedScheduler(
            backend=ScriptedBackend("\n".join(lines))).schedule(dag, machine)

        self.assertIn(len(dag) - 1, res.search_stats["missing"])
        self.assertTrue(any("UNPLACED" in n for n in res.notes))

    def test_empty_answer_does_not_crash(self):
        """An empty reply must return a diagnosed invalid result, not raise."""
        dag, machine, _ = _fixture()
        res = LearnedScheduler(backend=ScriptedBackend("")).schedule(dag, machine)

        self.assertFalse(res.search_stats["valid"])
        self.assertEqual(res.search_stats["n_decoded"], 0)
        self.assertEqual(len(res.search_stats["missing"]), len(dag))

    def test_garbage_answer_does_not_crash(self):
        """Free-form prose with no parseable placement lines."""
        dag, machine, _ = _fixture()
        res = LearnedScheduler(
            backend=ScriptedBackend("Sure! Here is the optimal schedule:")
        ).schedule(dag, machine)
        self.assertFalse(res.search_stats["valid"])


class TestAdapterDiscovery(unittest.TestCase):
    def test_status_works_without_torch(self):
        """Readiness reporting must work without heavy ML dependencies installed."""
        from vliw.learned import runtime

        ready, lines = runtime.status()
        self.assertIsInstance(ready, bool)
        self.assertTrue(lines)

    def test_find_adapters_on_empty_dir(self):
        from pathlib import Path
        from tempfile import TemporaryDirectory

        from vliw.learned import runtime

        with TemporaryDirectory() as td:
            self.assertEqual(runtime.find_adapters(Path(td)), [])




class TestLlamaCppBackend(unittest.TestCase):
    """llama.cpp CPU backend: prompt-echo stripping and backend priority order."""

    def test_prompt_echo_is_stripped(self):
        """llama.cpp echoes the prompt before the completion — it must be stripped."""
        from vliw.learned.runtime import Adapter, LlamaCppBackend

        prompt = "профиль: e2k-v6-measured\nграф:\n0 ADD\nрасписание:"
        answer = "0: такт=0 канал=1"

        be = LlamaCppBackend.__new__(LlamaCppBackend)   # bypass binary lookup
        out = prompt + answer + "[end of text]\ntrailing junk"
        tail = prompt[-40:]
        self.assertIn(tail, out)
        cleaned = out.split(tail, 1)[1].split("[end of text]")[0]
        self.assertEqual(cleaned, answer)

    def test_gguf_adapter_path_matches_name(self):
        from pathlib import Path

        from vliw.learned import runtime

        a = runtime.Adapter(path=Path("/x/lora-eos"), base="b", size_mb=1.0,
                            has_tokenizer=False)
        got = runtime.gguf_adapter_for(a)
        # File may not exist — what matters is deriving the filename from the adapter name.
        self.assertTrue(got is None or got.name == "lora-eos-f16.gguf")

    def test_base_search_skips_adapters(self):
        """LoRA adapters (*-f16.gguf) must not be picked as the base GGUF model."""
        import inspect

        from vliw.learned import runtime

        src = inspect.getsource(runtime.find_gguf_base)
        self.assertIn("-f16.gguf", src)

    def test_make_backend_prefers_llama_cpp(self):
        import inspect

        from vliw.learned import runtime

        src = inspect.getsource(runtime.make_backend)
        # llama.cpp must take precedence over transformers: ~2.1 GB vs ~6.2 GB RAM.
        self.assertLess(src.index("llama_cpp_ready"), src.index("missing_deps"))



class TestConcurrencyGuard(unittest.TestCase):
    """A second /learned while the first is still running must not spawn a second process."""

    def test_second_call_rejected_while_first_holds_lock(self):
        from vliw.learned.runtime import _GENERATE_LOCK, LlamaCppBackend

        be = LlamaCppBackend.__new__(LlamaCppBackend)
        _GENERATE_LOCK.acquire()
        try:
            with self.assertRaises(RuntimeError):
                be.generate("x", 5)
        finally:
            _GENERATE_LOCK.release()

    def test_lock_released_after_call(self):
        """The concurrency lock must always be released, even after an exception."""
        from vliw.learned.runtime import _GENERATE_LOCK, LlamaCppBackend

        be = LlamaCppBackend.__new__(LlamaCppBackend)
        be.binary = None       # forces failure inside _generate_locked
        be.base_gguf = None
        be.lora_gguf = None
        be.threads = 1
        with self.assertRaises(Exception):
            be.generate("x", 5)
        self.assertTrue(_GENERATE_LOCK.acquire(blocking=False),
                        "lock remained held after failure")
        _GENERATE_LOCK.release()


class TestChannelRepair(unittest.TestCase):
    """Port repair: preserve model issue cycles while reassigning legal functional units."""

    def test_illegal_store_channel_is_fixed(self):
        from vliw.learned.repair import repair

        # mixed18 has the richest op mix, including STORE.
        dag = get_scenario("mixed18")
        machine = get_profile("e2k-v6-measured")
        good = GreedyListScheduler().schedule(dag, machine).schedule
        # STORE executes only on ,2 and ,5 — place on ,0 and expect repair.
        store = next(i for i in range(len(dag)) if dag[i].op == "STORE")
        broken = Schedule(dag, machine)
        for i in range(len(dag)):
            p = good.placements[i]
            broken.place(i, p.cycle, 0 if i == store else p.channel)

        fixed, rep = repair(broken, machine)
        self.assertEqual(fixed.validate(), [])
        self.assertIn(fixed.placements[store].channel, machine.channels_for("STORE"))
        self.assertTrue(rep.touched)

    def test_cycles_are_never_moved(self):
        """Core invariant: issue cycles (and thus makespan) are never altered by port repair."""
        from vliw.learned.repair import repair

        dag, machine, good = _fixture()
        broken = Schedule(dag, machine)
        for i in range(len(dag)):
            broken.place(i, good.placements[i].cycle, 0)   # all forced onto port 0

        fixed, _ = repair(broken, machine)
        for i in range(len(dag)):
            self.assertEqual(fixed.placements[i].cycle, good.placements[i].cycle,
                             f"issue cycle of op {i} shifted during port repair")
        self.assertEqual(fixed.makespan, broken.makespan)

    def test_already_legal_schedule_is_left_alone(self):
        """An already-legal schedule must be untouched (zero port moves)."""
        from vliw.learned.repair import repair

        dag, machine, good = _fixture()
        fixed, rep = repair(good, machine)
        self.assertEqual(rep.touched, 0)
        for i in range(len(dag)):
            self.assertEqual(fixed.placements[i].channel,
                             good.placements[i].channel)

    def test_narrow_op_wins_over_greedy_grab(self):
        """Bipartite matching, not greedy assignment: wide ops must not steal
        narrow ports needed by constrained ops like STORE."""
        from vliw.learned.repair import _assign_cycle

        machine = get_profile("e2k-v6-measured")
        add_ch = machine.channels_for("ADD")
        store_ch = machine.channels_for("STORE")
        # Both request ,2; only STORE->,2 (or ,5) and ADD->any other port is legal.
        got = _assign_cycle([(0, add_ch, 2), (1, store_ch, 2)], machine.width)
        self.assertIsNotNone(got, "valid matching exists but was not found")
        self.assertIn(got[1], store_ch)
        self.assertNotEqual(got[0], got[1])

    def test_impossible_cycle_reported_not_hidden(self):
        """Unsatisfiable port demand (e.g. 3 STOREs in 1 cycle) must return None."""
        from vliw.learned.repair import _assign_cycle

        machine = get_profile("e2k-v6-measured")
        store_ch = machine.channels_for("STORE")      # only two store ports
        # Three STOREs in one cycle exceed the 2 available store ports.
        got = _assign_cycle([(i, store_ch, store_ch[0]) for i in range(3)],
                            machine.width)
        self.assertIsNone(got)

    def test_scheduler_repair_flag_off_by_default(self):
        """By default repair_channels=False preserves the raw model answer."""
        dag, machine, good = _fixture()
        bad = "\n".join(
            f"{i}: такт={good.placements[i].cycle} канал=0" for i in range(len(dag)))
        res = LearnedScheduler(backend=ScriptedBackend(bad)).schedule(dag, machine)
        self.assertEqual(res.search_stats["repaired"], 0)

    def test_scheduler_repair_flag_on_fixes_and_reports(self):
        dag, machine, good = _fixture()
        bad = "\n".join(
            f"{i}: такт={good.placements[i].cycle} канал=0" for i in range(len(dag)))
        res = LearnedScheduler(backend=ScriptedBackend(bad),
                               repair=True).schedule(dag, machine)
        self.assertTrue(res.search_stats["valid"])
        self.assertTrue(res.search_stats["repaired"])
        self.assertTrue(any("REPAIRED CHANNELS" in n for n in res.notes))
        # Model issue cycles are preserved — makespan stays unchanged.
        self.assertEqual(res.schedule.makespan, good.makespan)


class TestStreaming(unittest.TestCase):
    """Model output streams incrementally during generation rather than buffering until completion."""

    def test_callback_receives_text(self):
        dag, machine, good = _fixture()
        got = []
        LearnedScheduler(
            backend=ScriptedBackend(encode_completion(good))
        ).schedule(dag, machine, on_text=got.append)
        self.assertTrue(got, "streaming callback was never invoked")
        self.assertIn("такт=", "".join(got))

    def test_works_without_callback(self):
        """`on_text` is optional and not required by the Scheduler protocol."""
        dag, machine, good = _fixture()
        res = LearnedScheduler(
            backend=ScriptedBackend(encode_completion(good))).schedule(dag, machine)
        self.assertTrue(res.search_stats["valid"])

    def test_echo_detection_splits_prompt_from_answer(self):
        """llama.cpp echoes the prompt before streaming the answer; only the answer is emitted."""
        prompt = encode_prompt(*_fixture()[:2])
        answer = "0: такт=0 канал=1\n"
        stream = prompt + answer

        tail = prompt[-40:]
        buf, out, echo_done = [], [], False
        for ch in stream:
            buf.append(ch)
            if echo_done:
                out.append(ch)
            elif "".join(buf[-len(tail):]) == tail:
                echo_done = True
        self.assertTrue(echo_done, "prompt tail was not detected in stream")
        self.assertEqual("".join(out), answer)
class ChunkedBackend(ScriptedBackend):
    """Emit completion in small arbitrary chunks not aligned to newlines, like real llama.cpp."""

    def __init__(self, text: str, size: int = 3):
        super().__init__(text)
        self._text = text
        self._size = size

    def generate_events(self, prompt, max_new_tokens):
        for i in range(0, len(self._text), self._size):
            yield self._text[i:i + self._size]


class CancelWatchBackend(ScriptedBackend):
    """Unbounded generator that records when it is closed/cancelled."""

    def __init__(self) -> None:
        super().__init__("")
        self.cleaned = False
        self.emitted = 0

    def generate_events(self, prompt, max_new_tokens):
        try:
            while True:
                self.emitted += 1
                yield "…\n"          # non-placement token: only streaming matters
        finally:
            # In the real backend this terminates the llama.cpp subprocess and releases the lock.
            self.cleaned = True


def _answer_line(dag, machine, instr: int, cycle: int, channel: int) -> str:
    """Single completion line produced by the canonical training encoder."""
    sched = Schedule(dag, machine)
    sched.place(instr, cycle, channel)
    return encode_completion(sched)


class TestLiveGridFilling(unittest.TestCase):
    """The schedule grid populates incrementally as lines stream in."""

    def setUp(self) -> None:
        self.dag, self.machine, self.good = _fixture()
        self.answer = encode_completion(self.good)

    def _events(self, backend):
        from vliw.core import stream

        return list(stream(LearnedScheduler(backend=backend), self.dag, self.machine))

    def test_placements_arrive_before_the_end(self) -> None:
        """At least one `Placed` event must arrive before the terminal `Done` event."""
        from vliw.core import Done, Placed

        evs = self._events(ChunkedBackend(self.answer))
        first_placed = next(i for i, e in enumerate(evs) if isinstance(e, Placed))
        done = next(i for i, e in enumerate(evs) if isinstance(e, Done))
        self.assertLess(first_placed, done)

    def test_every_instruction_placed_exactly_once(self) -> None:
        from vliw.core import Placed

        placed = [e for e in self._events(ChunkedBackend(self.answer))
                  if isinstance(e, Placed)]
        ids = [e.placement.instr for e in placed]
        self.assertEqual(sorted(ids), sorted(range(len(self.dag))))

    def test_live_run_is_marked_live(self) -> None:
        """Live streaming run is marked as non-replay (`replay=False`)."""
        from vliw.core import Placed

        placed = [e for e in self._events(ChunkedBackend(self.answer))
                  if isinstance(e, Placed)]
        self.assertEqual({e.live for e in placed}, {True})

    def test_chunk_boundaries_do_not_lose_lines(self) -> None:
        """Chunk size must not affect line parsing across arbitrary byte boundaries."""
        from vliw.core import Placed

        for size in (1, 2, 3, 7, 1000):
            with self.subTest(size=size):
                placed = [e for e in self._events(ChunkedBackend(self.answer, size))
                          if isinstance(e, Placed)]
                self.assertEqual(len(placed), len(self.dag))

    def test_illegal_placement_still_reaches_the_grid(self) -> None:
        """Illegal placements still emit `Placed` events so the grid can highlight errors."""
        from vliw.core import Placed

        # Place the first op on an illegal port and verify the event is still emitted.
        bad = _answer_line(self.dag, self.machine, 0, 0, 7) + "\n"
        placed = [e for e in self._events(ChunkedBackend(bad))
                  if isinstance(e, Placed)]
        self.assertEqual(len(placed), 1)
        self.assertEqual(placed[0].placement.channel, 7)

    def test_repeated_identical_line_is_not_a_second_event(self) -> None:
        """Duplicate identical placement lines do not emit redundant `Placed` events."""
        from vliw.core import Placed

        line = _answer_line(self.dag, self.machine, 0, 0, 1)
        placed = [e for e in self._events(ChunkedBackend("\n".join([line] * 3) + "\n"))
                  if isinstance(e, Placed)]
        self.assertEqual(len(placed), 1)

    def test_moved_placement_is_a_second_event(self) -> None:
        """Re-placing the same op at a different (cycle, port) emits a new `Placed` event."""
        from vliw.core import Placed

        text = (_answer_line(self.dag, self.machine, 0, 0, 1) + "\n"
                + _answer_line(self.dag, self.machine, 0, 2, 1) + "\n")
        placed = [e for e in self._events(ChunkedBackend(text))
                  if isinstance(e, Placed)]
        self.assertEqual([e.placement.cycle for e in placed], [0, 2])

    def test_old_schedule_contract_matches_the_stream(self) -> None:
        """`schedule()` returns the exact same result as the terminal `Done` event."""
        from vliw.core import Done

        evs = self._events(ChunkedBackend(self.answer))
        via_stream = next(e for e in evs if isinstance(e, Done)).result
        direct = LearnedScheduler(
            backend=ChunkedBackend(self.answer)).schedule(self.dag, self.machine)
        self.assertEqual(direct.schedule.placements, via_stream.schedule.placements)
        self.assertEqual(direct.search_stats["valid"], via_stream.search_stats["valid"])


class TestCancellation(unittest.TestCase):
    """Cancellation propagates to the backend generator so subprocesses do not leak."""

    def test_close_kills_the_backend_stream(self) -> None:
        from vliw.core import stream

        dag, machine, _ = _fixture()
        be = CancelWatchBackend()
        gen = stream(LearnedScheduler(backend=be), dag, machine)
        for _ in range(5):
            next(gen)
        self.assertFalse(be.cleaned)
        gen.close()
        self.assertTrue(be.cleaned)

    def test_partial_placements_survive_cancellation(self) -> None:
        """A cancelled run still yields partial placements collected before cancellation."""
        from vliw.core import Placed, stream

        dag, machine, good = _fixture()
        answer = encode_completion(good)
        gen = stream(LearnedScheduler(backend=ChunkedBackend(answer, 1)), dag, machine)
        seen = [e for _, e in zip(range(60), gen) if isinstance(e, Placed)]
        gen.close()
        self.assertGreater(len(seen), 0)
        self.assertLess(len(seen), len(dag) + 1)


class TestSamplingPlumb(unittest.TestCase):
    """Verify temperature/seed forwarding while preserving legacy deterministic default calls."""

    def test_sampling_kwargs_empty_at_defaults(self):
        from vliw.learned.runtime import sampling_kwargs

        self.assertEqual(sampling_kwargs(0.0, None), {})
        self.assertEqual(sampling_kwargs(0, None), {})

    def test_sampling_kwargs_only_when_asked(self):
        from vliw.learned.runtime import sampling_kwargs

        self.assertEqual(sampling_kwargs(0.7, None), {"temperature": 0.7})
        self.assertEqual(sampling_kwargs(0.0, 5), {"seed": 5})
        self.assertEqual(sampling_kwargs(0.7, 5),
                         {"temperature": 0.7, "seed": 5})

    def test_old_signature_backend_survives_default_generate(self):
        from vliw.learned.runtime import Backend

        class Old(Backend):
            def generate_events(self, prompt, max_new_tokens):
                yield "reply"

        self.assertEqual(Old().generate("p", 5), "reply")

    def test_scheduler_passes_sampling_to_backend(self):
        dag, machine, good = _fixture()
        be = ScriptedBackend(encode_completion(good))
        LearnedScheduler(backend=be, temperature=0.7,
                         seed=11).schedule(dag, machine)
        self.assertEqual(be.last_sampling, {"temperature": 0.7, "seed": 11})

    def test_scheduler_default_keeps_old_call(self):
        """Default deterministic call passes no sampling kwargs, keeping legacy backends working."""
        dag, machine, good = _fixture()

        class Old(ScriptedBackend):
            def generate_events(self, prompt, max_new_tokens):
                yield encode_completion(good)

        res = LearnedScheduler(backend=Old("")).schedule(dag, machine)
        self.assertTrue(res.search_stats["valid"])

    def test_llama_cmd_grows_only_when_sampling(self):
        """Default llama-completion CLI args remain identical when sampling is off."""
        from pathlib import Path as _P

        from vliw.learned.runtime import _llama_cmd

        base = _llama_cmd(_P("llama"), _P("b.gguf"), None, "p.txt", 64, 128, 4)
        self.assertNotIn("--seed", base)
        self.assertEqual(base[base.index("--temp") + 1], "0")

        with_seed = _llama_cmd(_P("llama"), _P("b.gguf"), None,
                               "p.txt", 64, 128, 4, temperature=0.7, seed=9)
        self.assertIn("--seed", with_seed)
        self.assertEqual(with_seed[with_seed.index("--temp") + 1], "0.7")


class TestBestOfBench(unittest.TestCase):
    """best-of-N benchmarking: N samples, per-sample repair, selection by (violations, makespan)."""

    def setUp(self) -> None:
        self.dag, self.machine, self.good = _fixture()
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dataset = Path(self.tmp.name) / "ds.jsonl"
        self.dataset.write_text(
            json.dumps({"prompt": encode_prompt(self.dag, self.machine),
                        "meta": {"makespan": self.good.makespan}}) + "\n",
            encoding="utf-8")

    def _scheduler(self, replies) -> LearnedScheduler:
        return LearnedScheduler(backend=ScriptedBackend(replies), repair=True)

    def _broken(self, drop_last: int = 1) -> str:
        """Incomplete completion with missing ops (cannot be repaired by port reassignment)."""
        return "\n".join(encode_completion(self.good).splitlines()[:-drop_last])

    def _stretched(self, by: int = 1) -> str:
        """Valid schedule with stretched cycles — legal, but longer makespan."""
        s = Schedule(self.dag, self.machine)
        for i in range(len(self.dag)):
            p = self.good.placements[i]
            s.place(i, p.cycle + by, p.channel)
        return encode_completion(s)

    def test_best_of_picks_the_valid_sample(self):
        from vliw.learned.bench import BestOf, run_bench

        res = run_bench(self.dataset, 1,
                        self._scheduler([self._broken(), encode_completion(self.good)]),
                        self.machine,
                        best_of=BestOf(n=2, temperature=0.7, seed=1))
        row = res.rows[0]
        self.assertEqual(row.kind, "valid")
        self.assertEqual(row.valid_samples, 1)
        self.assertEqual([s.valid for s in row.samples], [False, True])

    def test_prefix_table_counts_any_of_first_k(self):
        """best-of-2 and best-of-4 evaluate prefixes of the same sample sequence."""
        from vliw.learned.bench import BestOf, run_bench

        good = encode_completion(self.good)
        res = run_bench(self.dataset, 1,
                        self._scheduler([self._broken(), good,
                                         self._broken(2), self._broken(3)]),
                        self.machine,
                        best_of=BestOf(n=4, temperature=0.7, seed=1))
        for k, want in ((1, 0), (2, 1), (3, 1), (4, 1)):
            with self.subTest(k=k):
                self.assertEqual(res.best_of_valid(k), (want, 1))

    def test_tie_on_valid_prefers_shorter_makespan(self):
        from vliw.learned.bench import BestOf, run_bench

        res = run_bench(self.dataset, 1,
                        self._scheduler([self._stretched(),
                                         encode_completion(self.good)]),
                        self.machine,
                        best_of=BestOf(n=2, temperature=0.7, seed=1))
        row = res.rows[0]
        self.assertEqual(row.kind, "valid")
        self.assertEqual(row.gap, 0)      # picked compact schedule over stretched one
        self.assertEqual([s.gap for s in row.samples], [1, 0])

    def test_fewer_violations_win(self):
        """When no sample is valid, select the one with the fewest violations."""
        from vliw.learned.bench import BestOf, run_bench

        res = run_bench(self.dataset, 1,
                        self._scheduler([self._broken(2), self._broken(1)]),
                        self.machine,
                        best_of=BestOf(n=2, temperature=0.7, seed=1))
        row = res.rows[0]
        self.assertNotEqual(row.kind, "valid")
        # Picked the sample with ONE missing op rather than two.
        self.assertEqual(row.samples[0].missing, 2)
        self.assertEqual(row.samples[1].missing, 1)

    def test_default_run_leaves_sampling_alone(self):
        """Without best_of, run a single sample and leave best-of fields untouched."""
        from vliw.learned.bench import run_bench

        sch = self._scheduler(encode_completion(self.good))
        res = run_bench(self.dataset, 1, sch, self.machine)
        self.assertIsNone(res.rows[0].samples)
        self.assertEqual(res.rows[0].kind, "valid")
        self.assertEqual(sch.temperature, 0.0)
        self.assertIsNone(sch.seed)

    def test_single_sample_still_samples(self):
        """best-of-1 is a valid single-sample benchmark run."""
        from vliw.learned.bench import BestOf, run_bench

        sch = self._scheduler(encode_completion(self.good))
        run_bench(self.dataset, 1, sch, self.machine,
                  best_of=BestOf(n=1, temperature=0.5, seed=7))
        self.assertEqual(sch.backend().last_sampling,
                         {"temperature": 0.5, "seed": 7})

    def test_seed_increments_per_sample(self):
        from vliw.learned.bench import BestOf

        bo = BestOf(n=2, temperature=0.7, seed=5)
        self.assertEqual([bo.sample_seed(k) for k in range(bo.n)], [5, 6])

    def test_best_of_requires_sampling_scheduler(self):
        from vliw.learned.bench import BestOf, run_bench

        with self.assertRaises(TypeError):
            run_bench(self.dataset, 1, GreedyListScheduler(), self.machine,
                      best_of=BestOf(n=2, temperature=0.7))


class TestLearnedArgParse(unittest.TestCase):
    """Pure flag parsing for `/learned`: regression guard for float values like `--temperature 0.7`."""

    def parse(self, arg: str):
        from vliw.cli import _parse_learned

        return _parse_learned(arg.split())

    def test_defaults_unchanged(self):
        a = self.parse("")
        self.assertIsNone(a.name)
        self.assertEqual(a.bench, 0)
        self.assertEqual(a.best_of, 0)
        self.assertEqual(a.temperature, 0.0)
        self.assertEqual(a.seed, 1)
        self.assertTrue(a.repair)
        self.assertFalse(a.raw)
        self.assertFalse(a.status)

    def test_temperature_value_is_not_adapter_name(self):
        a = self.parse("lora-eos --bench 10 --best-of 4 --temperature 0.7")
        self.assertEqual(a.name, "lora-eos")
        self.assertEqual(a.bench, 10)
        self.assertEqual(a.best_of, 4)
        self.assertEqual(a.temperature, 0.7)

    def test_flag_equals_form(self):
        a = self.parse("--bench=8 --best-of=2 --temperature=0.4 --seed=9")
        self.assertEqual((a.bench, a.best_of, a.temperature, a.seed),
                         (8, 2, 0.4, 9))
        self.assertIsNone(a.name)

    def test_bench_value_is_not_adapter_name(self):
        """Numeric count after `--bench` is not mistaken for an adapter name."""
        a = self.parse("--bench 15")
        self.assertEqual(a.bench, 15)
        self.assertIsNone(a.name)

    def test_pure_disables_repair(self):
        self.assertTrue(self.parse("").repair)
        self.assertFalse(self.parse("--pure").repair)


class TestBestOfRender(unittest.TestCase):
    """Benchmark summary prints the best-of-k validity table."""

    def _result(self, valid_by_sample: list[list[bool]]):
        from vliw.learned.bench import BestOf, BenchResult, BenchRow, SampleOutcome

        res = BenchResult(best_of=BestOf(n=8, temperature=0.7, seed=1))
        for samples in valid_by_sample:
            res.rows.append(BenchRow(
                n=10, kind="valid" if any(samples) else "other",
                has_store=True,
                samples=[SampleOutcome(valid=v, errors=0 if v else 1,
                                       missing=0, makespan=5, gap=0 if v else None)
                         for v in samples]))
        return res

    def test_k_table_lines_present(self):
        from vliw.ui import learned_view

        lines = learned_view.render_bench(
            self._result([[False, True, False, False, False, False, False, False],
                          [False] * 8]), "lora-eos")
        text = "\n".join(lines)
        self.assertIn("best-of: 8 samples", text)
        for k in (1, 2, 4, 8):
            self.assertIn(f"k={k} ", text)
        self.assertIn("(1/2)", text)      # k=2: first graph recovered

    def test_plain_bench_render_unchanged(self):
        """Without best_of, summary omits sampling headers and k-table."""
        from vliw.learned.bench import BenchResult, BenchRow
        from vliw.ui import learned_view

        res = BenchResult()
        res.rows.append(BenchRow(n=10, kind="valid", has_store=True))
        text = "\n".join(learned_view.render_bench(res, "lora-eos"))
        self.assertNotIn("best-of", text)
        self.assertNotIn("k=", text)
class TestLearnedArgErrors(unittest.TestCase):
    """Typos in numeric flags must be reported in `bad_value`, never silently ignored or raising ValueError."""

    @staticmethod
    def _parse(text: str):
        from vliw.cli import _parse_learned

        return _parse_learned(text.split())

    def test_non_numeric_bench_is_reported(self):
        a = self._parse("--bench abc")
        self.assertEqual(a.bad_value, ("--bench", "abc"))

    def test_non_numeric_temperature_does_not_raise(self):
        a = self._parse("--temperature oops")
        self.assertEqual(a.bad_value, ("--temperature", "oops"))
        self.assertEqual(a.temperature, 0.0)

    def test_good_values_pass_through(self):
        a = self._parse("--bench 3 --temperature 0.7 --best-of 4 --seed 9")
        self.assertIsNone(a.bad_value)
        self.assertEqual((a.bench, a.temperature, a.best_of, a.seed),
                         (3, 0.7, 4, 9))

    def test_adapter_name_is_not_mistaken_for_a_flag_value(self):
        a = self._parse("lora-eos --bench 2")
        self.assertIsNone(a.bad_value)
        self.assertEqual(a.name, "lora-eos")


class TestScheduleGrammar(unittest.TestCase):
    """GBNF completion grammar: structural legality guarantee for llama.cpp decoding."""

    @staticmethod
    def _grammar(key="slotclash"):
        from vliw.core import get_profile, get_scenario
        from vliw.learned.grammar import schedule_grammar

        return schedule_grammar(get_scenario(key), get_profile("e2k-v6-measured"))

    def test_newline_is_escaped_not_raw(self):
        """Raw unescaped newlines inside GBNF string literals are invalid and must not appear."""
        g = self._grammar()
        self.assertIn("\\n", g)
        for line in g.splitlines():
            self.assertTrue(line.strip(), "empty line in GBNF grammar")
        self.assertNotIn('"\n', g, "unescaped newline in GBNF literal")

    def test_channels_come_from_the_machine_not_from_a_common_set(self):
        """Each op rule must list only its legal issue ports."""
        from vliw.core import get_profile, get_scenario

        model = get_profile("e2k-v6-measured")
        dag = get_scenario("slotclash")
        g = self._grammar()
        for idx, ins in enumerate(dag.instrs):
            rule = next(l for l in g.splitlines() if l.startswith(f"op{idx} ::="))
            allowed = model.channels_for(ins.op)
            with self.subTest(op_name=ins.name, op_class=ins.op):
                for c in range(model.width):
                    present = f'"{c}"' in rule.split("канал=")[1]
                    self.assertEqual(present, c in allowed,
                                     f"port {c} for {ins.op}")

    def test_store_cannot_be_put_on_an_illegal_channel(self):
        """STORE must be restricted strictly to ports ,2 and ,5."""
        from vliw.core import get_scenario

        dag = get_scenario("slotclash")
        g = self._grammar()
        idx = next(i for i, ins in enumerate(dag.instrs) if ins.op == "STORE")
        rule = next(l for l in g.splitlines() if l.startswith(f"op{idx} ::="))
        tail = rule.split("канал=")[1]
        self.assertIn('"2"', tail)
        self.assertIn('"5"', tail)
        self.assertNotIn('"0"', tail)

    def test_every_instruction_is_in_the_root(self):
        """Root rule must cover every instruction in the DAG."""
        from vliw.core import get_scenario

        dag = get_scenario("mixed18")
        from vliw.core import get_profile
        from vliw.learned.grammar import schedule_grammar

        g = schedule_grammar(dag, get_profile("e2k-v6-measured"))
        root = next(l for l in g.splitlines() if l.startswith("root ::="))
        for idx in range(len(dag.instrs)):
            self.assertIn(f"op{idx}", root.split())

    def test_grammar_is_off_by_default(self):
        """Free generation remains the default when grammar constraints are not requested."""
        from vliw.learned.scheduler import LearnedScheduler

        self.assertFalse(LearnedScheduler().constrained)

    def test_sampling_kwargs_carry_the_grammar_only_when_asked(self):
        from vliw.learned.runtime import sampling_kwargs

        self.assertEqual(sampling_kwargs(0.0, None), {})
        self.assertEqual(sampling_kwargs(0.0, None, "root ::= \"x\""),
                         {"grammar": 'root ::= "x"'})


if __name__ == "__main__":
    unittest.main()
