"""CODE mode buffer parsing: line numbers, linter diagnostics, and cache invalidation.

The CODE editor overlays schedule annotations onto assembly source (issue cycle
and port in the gutter, `▲` markers on errors, jump-to-line). All of this rests
on two core invariants: accurate source line numbers per operation and a linter
that catches hazards the e2k assembler silently accepts.
"""

from __future__ import annotations

import unittest
from pathlib import Path

from vliw.core import asm_parser
from vliw.core.model import DEFAULT_PROFILE, get_profile

try:
    import textual  # noqa: F401

    HAS_TEXTUAL = True
except Exception:  # pragma: no cover - environment-dependent
    HAS_TEXTUAL = False


def _lint(text: str):
    parsed = asm_parser.parse_asm(text, source="<test>")
    model = get_profile(DEFAULT_PROFILE)
    return parsed, asm_parser.lint(parsed, model)


class TestLineNumbers(unittest.TestCase):
    def test_op_knows_its_source_line(self) -> None:
        parsed, _ = _lint("! header\n{\n  adds,0 %r1, %r2, %r3\n}\n")
        self.assertEqual([o.line for o in parsed.ops], [3])

    def test_skipped_lines_do_not_shift_the_rest(self) -> None:
        """Line numbering tracks the SOURCE FILE, not the parsed-op index."""
        parsed, _ = _lint("{\n  ???\n  adds,0 %r1, %r2, %r3\n}\n")
        self.assertEqual([o.line for o in parsed.ops], [3])

    def test_unparsed_line_is_reported_with_its_number(self) -> None:
        parsed, _ = _lint("{\n  ???\n}\n")
        self.assertEqual([(p.line, p.kind) for p in parsed.problems],
                         [(2, "parse")])

    def test_unknown_mnemonic_suggests_a_close_one(self) -> None:
        parsed, _ = _lint("{\n  addd,0 %r1, %r2, %r3\n  adfs,0 %r4, %r5, %r6\n}\n")
        problems = [p for p in parsed.problems if p.kind == "mnemonic"]
        self.assertEqual([p.line for p in problems], [3])
        self.assertIn("adds", problems[0].hint)


class TestLint(unittest.TestCase):
    def test_clean_fragment_has_nothing_to_say(self) -> None:
        """Legal assembly produces zero errors."""
        text = ("{\n  muls,0 %r10, %r11, %r20\n  muls,1 %r12, %r13, %r21\n}\n"
                "nop 3\n{\n  adds,0 %r20, %r21, %r22\n}\n")
        _, problems = _lint(text)
        self.assertEqual([p for p in problems if p.severity == "error"], [])

    def test_channel_outside_the_port_matrix(self) -> None:
        """`muls,2` is rejected by the assembler: MUL executes only on ,0 ,1 ,3 ,4."""
        _, problems = _lint("{\n  muls,2 %r1, %r2, %r3\n}\n")
        chan = [p for p in problems if p.kind == "channel"]
        self.assertEqual([(p.line, p.severity) for p in chan], [(2, "error")])
        self.assertIn(",0", chan[0].hint)

    def test_second_division_while_the_port_is_still_held(self) -> None:
        """DIV holds port ,5 for 2 cycles — the next cycle cannot issue another DIV."""
        _, problems = _lint("{\n  sdivs,5 %r0, %r1, %r2\n}\n"
                            "{\n  sdivs,5 %r3, %r4, %r5\n}\n")
        busy = [p for p in problems if p.kind == "busy"]
        self.assertEqual([p.line for p in busy], [5])
        self.assertIn("line 2", busy[0].text)

    def test_reading_a_result_before_it_is_ready(self) -> None:
        """DIV latency is 11 cycles: reading earlier creates a RAW hazard."""
        _, problems = _lint("{\n  sdivs,5 %r0, %r1, %r2\n}\n"
                            "nop 2\n{\n  adds,0 %r2, %r3, %r4\n}\n")
        ready = [p for p in problems if p.kind == "ready"]
        self.assertEqual([p.line for p in ready], [6])
        self.assertIn("11", ready[0].text)

    def test_lint_agrees_with_the_core_validator(self) -> None:
        """What the linter flags as an error must also fail `Schedule.validate()`."""
        text = ("{\n  muls,0 %r1, %r2, %r3\n}\n{\n  adds,0 %r3, %r4, %r5\n}\n")
        parsed, problems = _lint(text)
        model = get_profile(DEFAULT_PROFILE)
        dag = asm_parser.build_dag(parsed, key="asm:test", title="test")
        sched = asm_parser.compiler_schedule(parsed, dag, model)
        self.assertTrue([p for p in problems if p.kind == "ready"],
                        "linter must flag RAW hazard before latency elapses")
        self.assertTrue(sched.validate(),
                        "core validator must report the same violation")

    def test_missing_channels_are_flagged_as_a_guess(self) -> None:
        """Ops without explicit issue ports are flagged as free/unassigned."""
        _, problems = _lint("{\n  adds %r1, %r2, %r3\n}\n")
        self.assertEqual([p.kind for p in problems if p.kind == "free"],
                         ["free"])


@unittest.skipUnless(HAS_TEXTUAL, "textual not installed — example catalog lives in TUI module")
class TestExampleCatalogue(unittest.TestCase):
    """Examples in `examples/code/*.s` must match their declared `! nex:` headers.

    Each file carries `! nex: src=… orc=… err=…`. Recomputing these values with
    the current machine model and oracle prevents stale demo expectations.
    """

    import re as _re

    HEADER = _re.compile(r"!\s*nex:\s*src=(\S+)\s+orc=(\d+)\s+err=(\d+)")

    def _files(self):
        from vliw.tui.screens.code_screen import EXAMPLES, examples_dir

        return [(name, examples_dir() / f"{name}.s") for name, _, _ in EXAMPLES]

    def test_every_catalogue_entry_has_a_file(self) -> None:
        for name, path in self._files():
            self.assertTrue(path.exists(), f"{name}: missing file {path}")

    def test_headers_match_what_the_tool_computes(self) -> None:
        from vliw.core.oracle import OracleScheduler

        model = get_profile(DEFAULT_PROFILE)
        for name, path in self._files():
            with self.subTest(example=name):
                text = path.read_text(encoding="utf-8")
                m = self.HEADER.search(text)
                self.assertIsNotNone(m, f"{name}: missing `! nex: …` header")
                want_src, want_orc, want_err = m.groups()

                parsed = asm_parser.parse_asm(text, source=name)
                dag = asm_parser.build_dag(parsed, key=f"asm:{name}")
                sched = asm_parser.compiler_schedule(parsed, dag, model)
                # Same rule as the core: an invalid layout does not count as a legal schedule.
                src = sched.makespan if sched and not sched.validate() else None
                orc = OracleScheduler(budget_s=6.0,
                                      portfolio_s=2.0).schedule(dag, model)
                problems = list(parsed.problems) + asm_parser.lint(parsed, model)
                errs = [p for p in problems if p.severity == "error"]

                self.assertEqual(str(src if src is not None else "none"),
                                 want_src, f"{name}: src makespan drifted")
                self.assertEqual(orc.schedule.makespan, int(want_orc),
                                 f"{name}: oracle makespan drifted")
                self.assertEqual(len(errs), int(want_err),
                                 f"{name}: error count drifted")


class TestResultsFreshness(unittest.TestCase):
    """Editing the buffer must invalidate cached schedules instead of returning stale runs."""

    def test_set_dag_drops_the_cached_results(self) -> None:
        from vliw import cli

        args = cli._build_parser().parse_args([])
        session = cli.Session(args=args)

        short = asm_parser.parse_asm("{\n  adds,0 %r1, %r2, %r3\n}\n")
        session.set_dag(asm_parser.build_dag(short, key="asm:buffer"),
                        "asm:buffer")
        first = session.results()[1].schedule.makespan

        long = asm_parser.parse_asm(
            "{\n  sdivs,5 %r0, %r1, %r2\n}\n"
            "nop 11\n{\n  adds,0 %r2, %r3, %r4\n}\n")
        session.set_dag(asm_parser.build_dag(long, key="asm:buffer"),
                        "asm:buffer")
        second = session.results()[1].schedule.makespan

        self.assertNotEqual(first, second,
                            "second run returned first run's makespan — cache not invalidated")


class TestRealCompilerOutput(unittest.TestCase):
    """Parsing REAL `lcc -O3` output, not just synthetic calibration probes."""

    def test_speculative_modifier_does_not_eat_the_line(self):
        """Speculative `,sm` suffix after a channel must not drop the instruction."""
        from vliw.core.asm_parser import parse_asm

        src = "{\n  merges,2,sm\t0x1, %g17, %r9, %pred3\n  adds,0\t%r1, %r2, %r3\n}\n"
        parsed = parse_asm(src)
        self.assertEqual(len(parsed.ops), 2, "speculative op was dropped")
        spec = parsed.ops[0]
        self.assertEqual(spec.channel, 2, "channel before modifier was not parsed")
        self.assertEqual(spec.flags, ("sm",), "modifier flag was not preserved")
        self.assertEqual(parsed.ops[1].flags, (), "plain op received spurious flags")

    def test_unknown_mnemonic_is_not_passed_off_as_addition(self):
        """An unrecognized channelized op must be classified as UNKNOWN, never silently ADD."""
        from vliw.core.asm_parser import parse_asm

        # Intentionally fictional mnemonic so future opcode additions never break this test.
        parsed = parse_asm("{\n  zzqwrt,1\t%r1, %r2, %r3\n}\n")
        self.assertEqual(len(parsed.ops), 1)
        self.assertEqual(parsed.ops[0].op, "UNKNOWN")
        self.assertFalse(parsed.ops[0].known)
        self.assertEqual(parsed.unknown_mnemonics, {"zzqwrt": 1})

    def test_unknown_without_channel_is_not_an_alc_operation(self):
        """Unrecognized ops without `,N` are control/predicate ops, not ALC arithmetic ops."""
        from vliw.core.asm_parser import parse_asm

        parsed = parse_asm("{\n  landp\t~%pred0, ~%pred1, %pred2\n"
                           "  adds,0\t%r1, %r2, %r3\n}\n")
        self.assertEqual([o.mnemonic for o in parsed.ops], ["adds"])
        self.assertEqual(parsed.control_ops, 1)
        self.assertIn("landp", parsed.unknown_mnemonics)

    def test_setwd_and_friends_are_control_not_arithmetic(self):
        """`setwd` configures the register window — it is a control op, not arithmetic."""
        from vliw.core.asm_parser import parse_asm

        parsed = parse_asm("{\n  setwd\twsz = 0xc, nfx = 0x1\n"
                           "  adds,0\t%r1, %r2, %r3\n}\n")
        self.assertEqual([o.mnemonic for o in parsed.ops], ["adds"])
        self.assertEqual(parsed.control_ops, 1)
        self.assertEqual(parsed.unknown_mnemonics, {},
                         "control op must not be reported as unknown")

    def test_model_answers_for_unknown_class(self):
        """Every machine profile must define UNKNOWN with placeholder latency 1 and valid ports."""
        from vliw.core.model import PROFILES, get_profile

        for name in PROFILES:
            with self.subTest(profile=name):
                model = get_profile(name)
                self.assertEqual(model.latency("UNKNOWN"), 1)
                self.assertTrue(model.channels_for("UNKNOWN"),
                                "UNKNOWN must have at least one valid port")

    def test_calibration_probes_still_parse(self):
        """Calibration probes used to measure the machine model must parse with zero unknowns."""
        from vliw.core.asm_parser import parse_asm

        root = Path(__file__).resolve().parent.parent / "examples" / "probes"
        found = sorted(root.glob("*.s"))
        self.assertTrue(found, "no calibration probes found")
        for path in found:
            with self.subTest(probe=path.name):
                parsed = parse_asm(path.read_text(encoding="utf-8"))
                self.assertEqual(parsed.unknown_mnemonics, {})
                self.assertTrue(parsed.ops)


class TestStandaloneCollectorMatchesCore(unittest.TestCase):
    """`tools/collect_real_schedule.py` must stay in sync with `vliw.core.asm_parser`."""

    @staticmethod
    def _script():
        import importlib.util
        import sys

        path = Path(__file__).resolve().parent.parent / "tools" / "collect_real_schedule.py"
        spec = importlib.util.spec_from_file_location("_collector", path)
        mod = importlib.util.module_from_spec(spec)
        sys.modules["_collector"] = mod
        spec.loader.exec_module(mod)
        return mod

    def test_mnemonic_tables_agree(self):
        scr = self._script()
        self.assertEqual(scr.MNEMONICS, asm_parser.MNEMONICS,
                         "MNEMONICS table diverged from standalone collector")

    def test_control_lists_agree(self):
        scr = self._script()
        self.assertEqual(set(scr.CONTROL), set(asm_parser.CONTROL),
                         "CONTROL op list diverged from standalone collector")

    def test_same_classes_on_the_same_source(self):
        """Identical assembly input must produce identical op-class counts."""
        import collections

        scr = self._script()
        src = ("{\n  setwd\twsz = 0xc\n  merges,2,sm\t0x1, %g17, %r9, %pred3\n"
               "  landp\t~%pred0, ~%pred1, %pred2\n  adds,0\t%r1, %r2, %r3\n"
               "  ldw,3\t0x0, [ %dr1 ], %r4\n}\n")
        mine = asm_parser.parse_asm(src)
        theirs = scr.parse_asm(src)
        self.assertEqual(
            collections.Counter(o.op for o in mine.ops),
            collections.Counter(o.op for o in theirs.ops))
        self.assertEqual([o.mnemonic for o in mine.ops],
                         [o.mnemonic for o in theirs.ops])
        self.assertEqual(mine.control_ops, theirs.control_ops)


class TestWideInstructionSemantics(unittest.TestCase):
    """Within a VLIW bundle, all operands are read BEFORE any write commits."""

    def test_same_bundle_read_sees_the_old_value(self):
        """A load and a consumer of the same register in one VLIW bundle do NOT form a RAW edge."""
        src = ("{\n  ldw,0\t0x0, [ %dr1 ], %r5\n"
               "  sdivs,5\t%r5, %r6, %r4\n}\n")
        parsed = asm_parser.parse_asm(src)
        dag = asm_parser.build_dag(parsed)
        self.assertEqual(len(dag.instrs), 2)
        self.assertEqual(dag.instrs[1].preds, (),
                         "same-bundle neighbor cannot be a RAW producer")

    def test_next_bundle_does_depend(self):
        """Across consecutive bundles, the RAW dependency edge must be created."""
        src = ("{\n  ldw,0\t0x0, [ %dr1 ], %r5\n}\n"
               "{\n  adds,1\t%r5, %r6, %r7\n}\n")
        parsed = asm_parser.parse_asm(src)
        dag = asm_parser.build_dag(parsed)
        self.assertEqual(dag.instrs[1].preds, (0,),
                         "inter-bundle RAW dependency was lost")

    def test_compiler_schedule_of_real_probes_validates(self):
        """Reconstructed `lcc` schedules for calibration probes must pass `Schedule.validate()`."""
        from vliw.core.model import get_profile

        model = get_profile(DEFAULT_PROFILE)
        root = Path(__file__).resolve().parent.parent / "examples" / "probes"
        checked = 0
        for path in sorted(root.glob("*.s")):
            parsed = asm_parser.parse_asm(path.read_text(encoding="utf-8"))
            dag = asm_parser.build_dag(parsed)
            sched = asm_parser.compiler_schedule(parsed, dag, model)
            if sched is None:
                continue
            checked += 1
            with self.subTest(probe=path.name):
                self.assertEqual(sched.validate(), [],
                                 "compiler schedule falsely rejected as illegal")
        self.assertTrue(checked, "no probes were validated")


class TestHonestCompilerComparison(unittest.TestCase):
    """Do not claim speedup headroom over `lcc` when many ops are UNKNOWN placeholders."""

    @staticmethod
    def _render(ops_unknown: int, ops_known: int, comp: int, orc: int):
        from types import SimpleNamespace

        from vliw.ui import diagnostics

        ops = ([SimpleNamespace(op="UNKNOWN")] * ops_unknown
               + [SimpleNamespace(op="ADD")] * ops_known)
        parsed = SimpleNamespace(ops=ops, bundles=1, nop_cycles=0,
                                 skipped_lines=0, unknown_mnemonics={},
                                 problems=[], source="t",
                                 op_counts=lambda: {"ADD": ops_known})
        return "\n".join(diagnostics.render_parsed(
            parsed, None, comp, orc, None))

    def test_large_unknown_share_blocks_the_claim(self):
        text = self._render(63, 69, comp=77, orc=22)
        self.assertIn("invalid", text)
        self.assertNotIn("headroom 55", text)

    def test_clean_graph_still_reports_the_reserve(self):
        text = self._render(0, 36, comp=35, orc=26)
        self.assertIn("headroom 9", text)
        self.assertNotIn("invalid", text)


class TestSingleBundleFile(unittest.TestCase):
    """A single-bundle `{ ... }` file must stay one cycle, not split into per-op cycles."""

    ONE = "{\n  ldw,0\t0x0, [ %dr1 ], %r5\n  adds,1\t%r6, %r7, %r8\n}\n"

    def test_one_bundle_stays_one(self):
        parsed = asm_parser.parse_asm(self.ONE)
        self.assertEqual(parsed.bundles, 1)
        self.assertEqual([o.cycle for o in parsed.ops], [0, 0])

    def test_file_without_braces_still_splits(self):
        """Brace-free flat assembly still assigns one operation per cycle."""
        src = "  ldw,0\t0x0, [ %dr1 ], %r5\n  adds,1\t%r6, %r7, %r8\n"
        parsed = asm_parser.parse_asm(src)
        self.assertEqual([o.cycle for o in parsed.ops], [0, 1])
        self.assertEqual(parsed.bundles, 2)


class TestLinterDoesNotBlameTheCompiler(unittest.TestCase):
    """The linter must respect VLIW simultaneous-read bundle semantics on real `lcc` output."""

    def test_real_probes_have_no_dependency_errors(self):
        from vliw.core.model import get_profile

        model = get_profile(DEFAULT_PROFILE)
        root = Path(__file__).resolve().parent.parent / "examples" / "probes"
        for path in sorted(root.glob("*.s")):
            parsed = asm_parser.parse_asm(path.read_text(encoding="utf-8"))
            errs = [p for p in asm_parser.lint(parsed, model)
                    if p.severity == "error" and p.kind == "ready"]
            with self.subTest(probe=path.name):
                self.assertEqual(
                    errs, [], "lcc output falsely flagged as illegal: "
                    + "; ".join(e.text for e in errs[:2]))

    def test_real_violation_across_bundles_is_still_caught(self):
        """A genuine inter-bundle RAW hazard must still be caught by the linter."""
        from vliw.core.model import get_profile

        # LOAD has 5-cycle latency; reading it 1 cycle later is a RAW hazard.
        src = ("{\n  ldw,0\t0x0, [ %dr1 ], %r5\n}\n"
               "{\n  adds,1\t%r5, %r6, %r7\n}\n")
        parsed = asm_parser.parse_asm(src)
        errs = [p for p in asm_parser.lint(parsed, get_profile(DEFAULT_PROFILE))
                if p.kind == "ready"]
        self.assertEqual(len(errs), 1, "inter-bundle RAW hazard was missed")
        self.assertIn("%r5", errs[0].text)


class TestModeFlagSkipsThePicker(unittest.TestCase):
    """`--mode` must bypass the interactive mode picker in BOTH TUI and `--plain` mode."""

    @staticmethod
    def _run(argv, feed):
        import io
        import contextlib
        from unittest import mock

        from vliw.cli import main

        out = io.StringIO()
        with mock.patch("sys.stdin", io.StringIO(feed)), \
                contextlib.redirect_stdout(out):
            try:
                main(argv)
            except SystemExit:
                pass
        return out.getvalue()

    def test_plain_with_mode_does_not_ask(self):
        text = self._run(["--plain", "--no-color", "--mode", "lab"], "/quit\n")
        self.assertNotIn("1 / 2 / 3", text)

    def test_plain_without_mode_still_asks(self):
        text = self._run(["--plain", "--no-color"], "q\n")
        self.assertIn("1 / 2 / 3", text)


if __name__ == "__main__":
    unittest.main()
