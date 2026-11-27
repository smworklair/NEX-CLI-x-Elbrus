"""Real-code evaluation dataset generator tests (tools/make_eval_real.py).

Verifies the dataset's core guarantees: generated JSONL rows round-trip through
the project's own readers (`vliw/tiny/eval.py`, `tools/validate_jsonl.py`),
proven optima match independent CP-SAT proofs, duplicate graphs are merged, and
operations unsupported by the serialization format are explicitly reported
rather than silently corrupted.
"""

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

try:
    from tests.test_blocks import SAMPLE, chain_asm
except ImportError:                      # running directly from tests/
    from test_blocks import SAMPLE, chain_asm
from vliw.core.baseline import GreedyListScheduler
from vliw.core.dag import DagBuilder
from vliw.core.model import get_profile
from vliw.tiny.fast import TinyFlashScheduler
from vliw.tiny.features import build_dag, parse_graph_entries

ROOT = Path(__file__).resolve().parent.parent
TOOL = ROOT / "tools" / "make_eval_real.py"
ASM_DIR = ROOT / "real_candidates_100_400" / "asm"
MODEL = get_profile("e2k-v6-measured")


def _load_tool():
    spec = importlib.util.spec_from_file_location("make_eval_real", TOOL)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["make_eval_real"] = mod
    spec.loader.exec_module(mod)
    return mod


mer = _load_tool()


def _run(*args, cwd=None, timeout=240):
    return subprocess.run([sys.executable, *map(str, args)], capture_output=True, text=True,
                          timeout=timeout, cwd=cwd or ROOT)


class TestRoundtrip(unittest.TestCase):
    def test_plain_graph_survives_writing_and_reading(self):
        b = DagBuilder("g", "g")
        a = b.op("LOAD", "a")
        c = b.op("ADD", "c", a, a)          # operand read twice
        b.op("STORE", "s", c)
        dag = b.build()
        back, why = mer.roundtrip(dag, MODEL)
        self.assertIsNotNone(back, why)
        self.assertEqual(mer.signature(back), mer.signature(dag))
        self.assertEqual(mer.missing_symbols(dag), set())

    def test_format_limit_is_reported_not_hidden(self):
        """Ops missing from `_SYMBOL` cannot be serialized and must be reported explicitly."""
        from vliw.core import dag as dag_module
        absent = [op for op in ("FMA", "MOVA", "CONV", "INCR")
                  if op not in dag_module._SYMBOL]
        b = DagBuilder("fp", "fp")
        a = b.op("LOAD", "a")
        for op in ("FMA", "MOVA", "CONV", "INCR"):
            b.op(op, f"x_{op}", a, args=f"x_{op} = {op.lower()} a")
        dag = b.build()
        self.assertEqual(sorted(mer.missing_symbols(dag)), sorted(absent))
        back, why = mer.roundtrip(dag, MODEL)
        self.assertEqual(back is None, bool(absent), why)
        if absent:
            self.assertIn("_SYMBOL", why)

    def test_unreadable_prompt_is_a_refusal_not_a_crash(self):
        class Boom:
            def __iter__(self):
                raise ValueError("broken")

        back, why = mer.roundtrip(Boom(), MODEL)
        self.assertIsNone(back)
        self.assertIn("ValueError", why)


class TestCollect(unittest.TestCase):
    def _file(self, d, name, text):
        p = Path(d) / name
        p.write_text(text, encoding="utf-8")
        return p

    def test_identical_blocks_merge_and_are_counted(self):
        with tempfile.TemporaryDirectory() as d:
            p = self._file(d, "sample.s", SAMPLE)
            items, dups = mer.collect([p], min_ops=2, windows=False, win_min=12, win_max=56)
        # Blocks .L1 (loop) and .L2 are structurally identical: two dependent ADDs
        self.assertEqual([it.dag.key for it in items], ["sample#0", "sample#1"])
        self.assertEqual(dups, 1)
        self.assertEqual(items[1].seen, 2)
        self.assertEqual(items[0].seen, 1)

    def test_same_operations_different_edges_do_not_merge(self):
        """Deduplication keys on both ops AND DAG edges: different dependencies stay distinct."""
        dep = "\t.text\na:\n\t{\n\t  adds,0\t%r0, %r1, %r2\n\t}\n\t{\n\t  adds,0\t%r2, %r2, %r3\n\t  ct\t%ctpr1\n\t}\n"
        ind = "\t.text\nb:\n\t{\n\t  adds,0\t%r0, %r1, %r2\n\t}\n\t{\n\t  adds,0\t%r0, %r1, %r3\n\t  ct\t%ctpr1\n\t}\n"
        with tempfile.TemporaryDirectory() as d:
            pa = self._file(d, "a.s", dep)
            pb = self._file(d, "b.s", ind)
            items, dups = mer.collect([pa, pb], min_ops=2, windows=False, win_min=12, win_max=56)
        self.assertEqual(len(items), 2)
        self.assertEqual(dups, 0)
        self.assertNotEqual(mer.signature(items[0].dag), mer.signature(items[1].dag))

    def test_window_equal_to_a_block_stays_a_block(self):
        with tempfile.TemporaryDirectory() as d:
            p = self._file(d, "b.s", chain_asm(12))
            items, dups = mer.collect([p], min_ops=10, windows=True, win_min=12, win_max=56)
        self.assertEqual([it.kind for it in items], ["block"])
        self.assertEqual(dups, 4)                     # target 16/24/32/48 windows match the block
        self.assertEqual(items[0].seen, 5)

    def test_kinds(self):
        with tempfile.TemporaryDirectory() as d:
            p = self._file(d, "w.s", chain_asm(40) + chain_asm(41, loop=True, label="g"))
            items, _ = mer.collect([p], min_ops=10, windows=True, win_min=12, win_max=56)
        self.assertEqual({it.kind for it in items}, {"block", "block_loop", "window", "window_loop"})
        for it in items:
            self.assertEqual(it.loop, it.kind.endswith("_loop"))
            self.assertEqual(it.file, "w")


class TestSolve(unittest.TestCase):
    """Verify `solve` against `eval_hard.jsonl` where optima are independently proven (CP-SAT)."""

    @classmethod
    def setUpClass(cls):
        cls.fast = TinyFlashScheduler(mode="exact", with_trace=False)
        cls.greedy = GreedyListScheduler()
        rows = []
        with open(ROOT / "eval_hard.jsonl", encoding="utf-8") as f:
            for line in f:
                ex = json.loads(line)
                if ex["meta"]["gap"] >= 2:            # greedy is clearly suboptimal
                    rows.append(ex)
                if len(rows) == 6:
                    break
        cls.rows = rows

    def test_the_sample_is_not_empty(self):
        """Guard against silently skipping all assertions below."""
        self.assertEqual(len(self.rows), 6)

    def test_proven_optimum_equals_the_independent_one(self):
        for ex in self.rows:
            dag = build_dag(parse_graph_entries(ex["prompt"]))
            with self.subTest(n=ex["meta"]["n"], opt=ex["meta"]["makespan"]):
                r = mer.solve(dag, MODEL, self.fast, self.greedy, oracle_budget=20)
                self.assertIsNotNone(r["by"], "optimum should be proven within budget")
                self.assertEqual(r["ms"], ex["meta"]["makespan"])
                self.assertEqual(r["base"], ex["meta"]["baseline"])
                self.assertLessEqual(r["lb"], r["ms"])

    def test_row_fields_match_the_independent_eval(self):
        """Row metadata (makespan, baseline, gap, n) must match the independent eval."""
        for ex in self.rows:
            dag = build_dag(parse_graph_entries(ex["prompt"]))
            it = mer.Item("eval_hard", "window", "k", False, dag)
            r = mer.solve(dag, MODEL, self.fast, self.greedy, oracle_budget=20)
            row = mer.make_row(it, r, MODEL)
            with self.subTest(n=ex["meta"]["n"]):
                for k in ("makespan", "baseline", "gap", "n"):
                    self.assertEqual(row["meta"][k], ex["meta"][k], k)
                self.assertGreater(row["meta"]["gap"], 0)
                self.assertEqual(row["prompt"], ex["prompt"])

    def test_a_search_that_ran_out_of_time_proves_nothing(self):
        """With a negligible budget, any proven result must still match the true optimum."""
        for ex in self.rows:
            dag = build_dag(parse_graph_entries(ex["prompt"]))
            r = mer.solve(dag, MODEL, self.fast, self.greedy, oracle_budget=1e-9)
            with self.subTest(n=ex["meta"]["n"]):
                if r["by"] is not None:
                    self.assertEqual(r["ms"], ex["meta"]["makespan"])
                self.assertLessEqual(r["ms"], r["base"])

    def test_without_the_exact_search_nothing_false_is_claimed(self):
        """With budget=0, only lower-bound proofs are allowed; unproven rows leave `by=None`."""
        for ex in self.rows:
            dag = build_dag(parse_graph_entries(ex["prompt"]))
            r = mer.solve(dag, MODEL, self.fast, self.greedy, oracle_budget=0)
            if r["by"] == "bound":
                self.assertEqual(r["ms"], r["lb"])
                self.assertEqual(r["ms"], ex["meta"]["makespan"])    # bound is sound
            else:
                self.assertIsNone(r["by"])
                self.assertGreater(r["ms"], r["lb"])
            self.assertLessEqual(r["ms"], r["base"])


class TestRowsAndVerification(unittest.TestCase):
    def setUp(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "sample.s"
            p.write_text(SAMPLE, encoding="utf-8")
            items, _ = mer.collect([p], 2, False, 12, 56)
        self.it = items[0]                      # ADD, MUL, ADD <- 0 1
        fast = TinyFlashScheduler(mode="exact", with_trace=False)
        self.r = mer.solve(self.it.dag, MODEL, fast, GreedyListScheduler(), 0)

    def test_proven_row_has_the_eval_format(self):
        row = mer.make_row(self.it, self.r, MODEL)
        self.assertEqual(set(row), {"prompt", "completion", "meta"})
        m = row["meta"]
        for k in ("makespan", "n", "shape", "gap", "baseline", "lb", "proven_by", "file", "key", "loop", "seen"):
            self.assertIn(k, m)
        self.assertEqual(m["shape"], "real-block")
        self.assertEqual(m["gap"], m["baseline"] - m["makespan"])
        self.assertEqual(m["proven_by"], "bound")

    def test_unproven_row_cannot_be_mistaken_for_an_optimum(self):
        r = dict(self.r, by=None, ms=self.r["ms"] + 1)          # simulate unproven result
        row = mer.make_row(self.it, r, MODEL)
        self.assertNotIn("makespan", row["meta"])
        self.assertFalse(row["meta"]["proven"])
        self.assertEqual(row["meta"]["best_known"], r["ms"])

    def _write(self, d, rows, name="x.jsonl"):
        p = Path(d) / name
        mer.write_jsonl(p, rows)
        return p

    def test_verifier_accepts_the_good_file(self):
        with tempfile.TemporaryDirectory() as d:
            p = self._write(d, [mer.make_row(self.it, self.r, MODEL)])
            self.assertEqual(mer.verify_file(p, MODEL, True), [])

    def test_verifier_is_not_vacuous(self):
        """Corrupted rows must be caught; otherwise the verifier is vacuous."""
        good = mer.make_row(self.it, self.r, MODEL)
        cases = {
            "wrong makespan": lambda r: r["meta"].__setitem__("makespan", r["meta"]["makespan"] + 1),
            "broken schedule": lambda r: r.__setitem__("completion", "0: такт=0 канал=2\n1: такт=0 канал=2\n2: такт=0 канал=2"),
            "port double-booked, same makespan": lambda r: r.__setitem__(
                "completion", "0: такт=0 канал=2\n1: такт=0 канал=2\n2: такт=4 канал=2"),
            "incomplete schedule": lambda r: r.__setitem__("completion", "0: такт=0 канал=2"),
            "truncated graph": lambda r: r.__setitem__("prompt", r["prompt"].replace("2 ADD <- 0 1\n", "")),
            "lower bound too high": lambda r: r["meta"].__setitem__("lb", r["meta"]["makespan"] + 3),
            "greedy beats optimum": lambda r: r["meta"].__setitem__("baseline", r["meta"]["makespan"] - 1),
        }
        with tempfile.TemporaryDirectory() as d:
            for name, spoil in cases.items():
                row = json.loads(json.dumps(good))
                spoil(row)
                p = self._write(d, [row], f"{abs(hash(name))}.jsonl")
                with self.subTest(name):
                    self.assertTrue(mer.verify_file(p, MODEL, True), "corruption went undetected")


class TestCli(unittest.TestCase):
    def test_end_to_end_and_project_tools_accept_the_output(self):
        with tempfile.TemporaryDirectory() as d:
            src = Path(d) / "sample.s"
            src.write_text(SAMPLE, encoding="utf-8")
            out, out_open = Path(d) / "ok.jsonl", Path(d) / "open.jsonl"
            r = _run(TOOL, src, "--min-ops", "2", "--no-windows", "--oracle", "0",
                     "--out", out, "--out-open", out_open)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertIn("written file verification", r.stdout)
            rows = [json.loads(x) for x in out.read_text(encoding="utf-8").splitlines()]
            self.assertEqual([x["meta"]["n"] for x in rows], [3, 2])
            self.assertEqual(out_open.read_text(encoding="utf-8"), "")
            # Project JSONL validator
            v = _run(ROOT / "tools" / "validate_jsonl.py", out)
            self.assertEqual(v.returncode, 0, v.stdout + v.stderr)
            self.assertIn("RESULT: OK", v.stdout)
            # TINY Flash evaluation runner
            e = _run(ROOT / "vliw" / "tiny" / "eval.py", "--eval", out)
            self.assertEqual(e.returncode, 0, e.stdout + e.stderr)
            self.assertIn("n=2 valid=2/2", e.stdout)
            self.assertIn("optimal tiny=2/2", e.stdout)

    def test_no_files_is_an_error(self):
        with tempfile.TemporaryDirectory() as d:
            r = _run(TOOL, "--dir", d, "--out", Path(d) / "a.jsonl", "--out-open", Path(d) / "b.jsonl")
            self.assertEqual(r.returncode, 2)

    def test_two_processes_give_the_same_file_as_one(self):
        with tempfile.TemporaryDirectory() as d:
            src = Path(d) / "w.s"
            src.write_text(chain_asm(30) + chain_asm(33, loop=True, label="g"), encoding="utf-8")
            outs = []
            for jobs in (1, 2):
                o = Path(d) / f"o{jobs}.jsonl"
                r = _run(TOOL, src, "--oracle", "0", "--jobs", jobs,
                         "--out", o, "--out-open", Path(d) / f"p{jobs}.jsonl")
                self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
                outs.append(o.read_text(encoding="utf-8"))
            self.assertTrue(outs[0])
            self.assertEqual(outs[0], outs[1])


@unittest.skipUnless((ROOT / "eval_real.jsonl").exists(), "eval_real.jsonl not present")
class TestShippedFiles(unittest.TestCase):
    """Shipped repository datasets must pass the same verification as newly generated files."""

    def test_eval_real_is_consistent(self):
        self.assertEqual(mer.verify_file(ROOT / "eval_real.jsonl", MODEL, True), [])

    def test_eval_real_open_is_consistent(self):
        p = ROOT / "eval_real_open.jsonl"
        if not p.exists():
            self.skipTest("eval_real_open.jsonl not present")
        self.assertEqual(mer.verify_file(p, MODEL, False), [])

    def test_validate_jsonl_accepts_eval_real(self):
        v = _run(ROOT / "tools" / "validate_jsonl.py", ROOT / "eval_real.jsonl")
        self.assertEqual(v.returncode, 0, v.stdout + v.stderr)

    def test_no_graph_is_both_proven_and_open(self):
        keys = set()
        for name in ("eval_real.jsonl", "eval_real_open.jsonl"):
            p = ROOT / name
            if not p.exists():
                continue
            for line in p.read_text(encoding="utf-8").splitlines():
                k = json.loads(line)["prompt"]
                self.assertNotIn(k, keys)
                keys.add(k)


if __name__ == "__main__":
    unittest.main()
