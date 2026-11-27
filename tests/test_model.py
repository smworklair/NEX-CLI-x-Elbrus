"""Machine model invariants for `e2k-v6-measured`.

Locks down the hardware port matrix, exclusive divider port `,5`, and the fact
that integer multiply is NOT exclusive (it executes on 4 ports: ,0 ,1 ,3 ,4).
Hardware verification lives in `tools/probe_matrix.py`; this suite guards code
invariants.
"""

from __future__ import annotations

import unittest

from vliw.core.model import (
    DEFAULT_PROFILE,
    E2K_V6_FIRSTPROBE,
    E2K_V6_MEASURED,
    PROFILES,
    capability_matrix,
    describe_model,
    get_profile,
)

M = E2K_V6_MEASURED


class TestMeasuredProfile(unittest.TestCase):
    def test_width_six(self):
        self.assertEqual(M.width, 6)

    def test_default_profile_is_measured(self):
        self.assertEqual(DEFAULT_PROFILE, M.name)
        self.assertIs(get_profile(DEFAULT_PROFILE), M)

    def test_port_matrix(self):
        self.assertEqual(M.channels_for("ADD"), (0, 1, 2, 3, 4, 5))
        self.assertEqual(M.channels_for("SUB"), (0, 1, 2, 3, 4, 5))
        self.assertEqual(M.channels_for("AND"), (0, 1, 2, 3, 4, 5))
        self.assertEqual(M.channels_for("SHL"), (0, 1, 2, 3, 4, 5))
        self.assertEqual(M.channels_for("MUL"), (0, 1, 3, 4))
        self.assertEqual(M.channels_for("DIV"), (5,))
        self.assertEqual(M.channels_for("LOAD"), (0, 2, 3, 5))
        self.assertEqual(M.channels_for("STORE"), (2, 5))

    def test_latency_and_occupancy(self):
        self.assertEqual(M.latency("MUL"), 4)
        self.assertEqual(M.latency("DIV"), 11)
        self.assertEqual(M.latency("LOAD"), 5)
        for op in ("ADD", "SUB", "AND", "SHL"):
            self.assertEqual(M.latency(op), 1, op)
        # STORE latency (2c) was measured via a volatile store->load chain.
        self.assertEqual(M.latency("STORE"), 2)
        # Integer DIV and floating-point FDIV are the only ops with 2-cycle port occupancy on ,5.
        self.assertEqual(M.occupancy("DIV"), 2)
        self.assertEqual(M.occupancy("FDIV"), 2)
        for op in M.ops:
            if op not in ("DIV", "FDIV"):
                self.assertEqual(M.occupancy(op), 1, op)

    def test_monopolies_are_where_the_assembler_says(self):
        """Exactly two exclusive ports exist: ,0 (RW) and ,5 (DIV/FDIV)."""
        sole = M.sole_host_ops()
        self.assertEqual(set(sole), {0, 5})
        self.assertEqual(set(sole[5]), {"DIV", "FDIV"})
        self.assertEqual(set(sole[0]), {"RW"})

    def test_multiplier_is_not_a_monopoly(self):
        """Refuted assumption (exclusive MUL) must never regress into the measured profile."""
        self.assertGreater(len(M.channels_for("MUL")), 1)
        self.assertEqual(M.occupancy("MUL"), 1)
        self.assertNotIn("MUL", M.sole_host_ops().get(0, []))

    def test_every_op_has_a_host(self):
        for op in M.ops:
            self.assertTrue(M.channels_for(op), f"{op} has no capable execution port")

    def test_not_uniform(self):
        """Issue ports are asymmetric: port ,5 has fewer ops than wide ALU ports."""
        self.assertFalse(M.uniform_channels())
        self.assertTrue(M.has_blocking_ops())

    def test_unknown_op_raises_with_hint(self):
        # Intentionally fictional op class name to avoid colliding with real opcodes.
        with self.assertRaises(KeyError) as cm:
            M.op("NO_SUCH_OP")
        self.assertIn("NO_SUCH_OP", str(cm.exception))


class TestWithWidth(unittest.TestCase):
    """Narrowing issue width (1..6) must always preserve at least one port per op class."""

    def test_every_op_keeps_a_host_at_any_width(self):
        for w in range(1, 9):
            m = M.with_width(w)
            self.assertEqual(m.width, w)
            for op in m.ops:
                self.assertTrue(m.channels_for(op),
                                f"width {w}: {op} has no capable port")

    def test_channels_are_renumbered_contiguously(self):
        for w in (1, 3, 6, 8):
            m = M.with_width(w)
            self.assertEqual([p.index for p in m.ports], list(range(w)))

    def test_same_width_returns_same_object(self):
        self.assertIs(M.with_width(M.width), M)


class TestProfiles(unittest.TestCase):
    def test_firstprobe_kept_as_counterexample(self):
        """The legacy refuted profile is retained solely for educational contrast."""
        self.assertIn(E2K_V6_FIRSTPROBE.name, PROFILES)
        self.assertEqual(E2K_V6_FIRSTPROBE.channels_for("MUL"), (0,))
        self.assertEqual(E2K_V6_FIRSTPROBE.occupancy("MUL"), 8)
        # And it must never replace the measured default.
        self.assertNotEqual(E2K_V6_FIRSTPROBE.name, DEFAULT_PROFILE)

    def test_unknown_profile_exits_with_list(self):
        with self.assertRaises(SystemExit) as cm:
            get_profile("e2k-v7-imaginary")
        self.assertIn(M.name, str(cm.exception))

    def test_describe_and_matrix_shapes(self):
        rows = describe_model(M)
        self.assertTrue(all(len(r) == 3 for r in rows))
        ops, grid = capability_matrix(M)
        self.assertEqual(len(grid), M.width)
        self.assertTrue(all(len(row) == len(ops) for row in grid))
        # Port matrix and channels_for() must agree exactly.
        for pi, row in enumerate(grid):
            for oi, can in enumerate(row):
                self.assertEqual(can, pi in M.channels_for(ops[oi]))


if __name__ == "__main__":
    unittest.main()
