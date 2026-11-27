"""Assembly generator tests: generated e2k assembly must always be legal.

The generator's core invariant is that issue slots / functional unit ports come
from the machine model, never hardcoded assumptions, so an illegal encoding like
`muls,2` (where integer multiply has no FU) can never be emitted. Breaking this
would produce assembly rejected by the e2k assembler, wasting engineer time
instead of saving it.

Verification has two layers: here against the machine model (fast, runs
everywhere), and in `tools/probe_matrix.py` against the real e2k assembler
wherever the toolchain is installed.
"""

from __future__ import annotations

import unittest

from vliw.core import asmgen
from vliw.core import get_profile
from vliw.core.asm_parser import parse_asm


class TestOnlyLegalChannels(unittest.TestCase):
    def setUp(self):
        self.machine = get_profile("e2k-v6-measured")

    def _channels_used(self, text: str) -> dict[str, set[int]]:
        """Return the set of issue ports actually emitted for each operation class."""
        out: dict[str, set[int]] = {}
        for op in parse_asm(text).ops:
            if op.channel is not None:
                out.setdefault(op.op, set()).add(op.channel)
        return out

    def test_generated_channels_are_legal_for_every_class(self):
        """Primary guard: never emit an operation on an unsupported issue port."""
        for name in asmgen.known_names():
            for packed in (False, True):
                text = asmgen.independent(self.machine, name, 8, packed=packed)
                for op, channels in self._channels_used(text).items():
                    legal = set(self.machine.channels_for(op))
                    with self.subTest(op=name, packed=packed):
                        self.assertTrue(
                            channels <= legal,
                            f"{op} emitted on illegal ports {sorted(channels - legal)}, "
                            f"supported ports are {sorted(legal)}")

    def test_chain_channels_are_legal_too(self):
        for name in ("MUL", "DIV", "FMUL", "ADD"):
            text = asmgen.chain(self.machine, name, 5)
            for op, channels in self._channels_used(text).items():
                with self.subTest(op=name):
                    self.assertTrue(channels <= set(self.machine.channels_for(op)))

    def test_nothing_unknown_gets_generated(self):
        """Generated assembly must round-trip through our own parser without UNKNOWN ops.

        An UNKNOWN op would mean the generator emitted a mnemonic not covered by
        the opcode table, causing downstream scheduling analysis to degrade.
        """
        for text in (asmgen.independent(self.machine, "MUL", 6),
                     asmgen.chain(self.machine, "FMUL", 4),
                     asmgen.filler(self.machine, 6)):
            ops = parse_asm(text).ops
            self.assertTrue(ops)
            for op in ops:
                self.assertNotEqual(op.op, "UNKNOWN", op.mnemonic)


class TestRegisterFile(unittest.TestCase):
    """Registers must stay within the valid window: %r0..%r63.

    Verified empirically against the real e2k assembler — the limit is fixed
    regardless of `wsz`. An earlier version emitted %r70+ and triggered
    `Illegal register index`. This test prevents regressions that the abstract
    machine model alone does not catch.
    """

    def setUp(self):
        self.machine = get_profile("e2k-v6-measured")

    def test_all_register_indices_fit_the_window(self):
        import re

        for text in (asmgen.independent(self.machine, "MUL", 40),
                     asmgen.independent(self.machine, "ADD", 40, packed=True),
                     asmgen.chain(self.machine, "FMUL", 40),
                     asmgen.filler(self.machine, 40)):
            for num in re.findall(r"%d?r\[?(\d+)", text):
                self.assertLessEqual(int(num), asmgen.MAX_REG)


class TestHonestHeader(unittest.TestCase):
    def test_wraparound_is_announced(self):
        """When destination registers wrap around, ops are no longer independent.

        Silently labeling 40 ops as independent when only the first 32 have
        distinct destinations would hide WAW/RAW hazards.
        """
        machine = get_profile("e2k-v6-measured")
        few = asmgen.independent(machine, "ADD", 8)
        many = asmgen.independent(machine, "ADD", 40)
        self.assertNotIn("WARNING", few)
        self.assertIn("WARNING", many)

    def test_header_states_the_measured_facts(self):
        """Header comments must report issue ports and latency from the machine model."""
        machine = get_profile("e2k-v6-measured")
        text = asmgen.independent(machine, "DIV", 4)
        self.assertIn(",5", text)                     # exclusive divider port
        self.assertIn(str(machine.latency("DIV")), text)
        self.assertIn("port occupancy", text)         # 2-cycle divider occupancy


if __name__ == "__main__":
    unittest.main()
