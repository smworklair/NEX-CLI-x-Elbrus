"""ISA cost reference tests: every published number must declare its provenance.

This reference is read by engineers with access to real hardware, so the core
invariant is simple: **no assumed latency or occupancy may be published as a
measured hardware value.**
"""

from __future__ import annotations

import unittest

from vliw.core import get_profile
from vliw.core.asm_parser import MNEMONICS
from vliw.core.isa import COMBINATION_BANS, collect, gaps
from vliw.core.model import ASM, ASSUMED, BURST, CHAIN
from vliw.ui import isa_view

KNOWN_SOURCES = {ASM, CHAIN, BURST, ASSUMED}


class TestCollect(unittest.TestCase):
    def setUp(self):
        self.machine = get_profile("e2k-v6-measured")
        self.rows = collect(self.machine)

    def test_unknown_is_not_published(self):
        """`UNKNOWN` is a parser fallback, not a hardware operation class."""
        self.assertNotIn("UNKNOWN", [r.name for r in self.rows])

    def test_every_mnemonic_reaches_a_class(self):
        """The mnemonic table and ISA reference must cover the exact same set."""
        published = {m for r in self.rows for m in r.mnemonics}
        expected = {m for m, cls in MNEMONICS.items() if cls != "UNKNOWN"}
        self.assertEqual(published, expected)

    def test_no_invented_sources(self):
        """Every provenance tag must be one of the four canonical source constants."""
        for r in self.rows:
            with self.subTest(cls=r.name):
                self.assertIn(r.latency_source, KNOWN_SOURCES)
                self.assertIn(r.occupancy_source, KNOWN_SOURCES)

    def test_peak_is_channels_over_occupancy(self):
        """Peak issue rate is derived from port count / occupancy, not a separate measurement."""
        for r in self.rows:
            with self.subTest(cls=r.name):
                self.assertAlmostEqual(r.peak_per_cycle,
                                       len(r.channels) / r.occupancy)

    def test_monopoly_classes_are_the_narrow_ones(self):
        mono = {r.name for r in self.rows if r.monopoly}
        self.assertIn("DIV", mono)
        self.assertIn("FDIV", mono)
        self.assertNotIn("ADD", mono)

    def test_gaps_are_exactly_the_assumed_latencies(self):
        holes = {r.name for r in gaps(self.rows)}
        assumed = {r.name for r in self.rows if r.latency_source == ASSUMED}
        self.assertEqual(holes, assumed)
        self.assertTrue(holes, "fixture: model must contain assumed entries")


class TestDocument(unittest.TestCase):
    def setUp(self):
        self.machine = get_profile("e2k-v6-measured")
        self.rows = collect(self.machine)
        self.md = isa_view.render_markdown(self.rows, self.machine, "test")

    def test_every_gap_is_listed_as_a_gap(self):
        """Every assumed class must appear in the Unmeasured Latencies section."""
        tail = self.md.split("## Unmeasured Latencies", 1)
        self.assertEqual(len(tail), 2, "Unmeasured Latencies section missing from document")
        for r in gaps(self.rows):
            with self.subTest(cls=r.name):
                self.assertIn(f"`{r.name}`", tail[1])

    def _summary_rows(self) -> dict[str, str]:
        """Extract rows of the Summary Table only."""
        body = self.md.split("## Summary Table", 1)[1]
        body = body.split("## Classes and Mnemonics", 1)[0]
        return {l.split("`")[1]: l for l in body.splitlines() if l.startswith("| `")}

    def test_assumed_numbers_are_marked_in_the_table(self):
        """Assumed values must be visibly marked in the summary table, not shown as measured."""
        rows = self._summary_rows()
        self.assertEqual(set(rows), {r.name for r in self.rows},
                         "summary table diverged from collected ISA rows")
        for r in self.rows:
            with self.subTest(cls=r.name):
                if r.latency_measured:
                    self.assertIn("measured", rows[r.name])
                else:
                    self.assertIn("**assumed**", rows[r.name])

    def test_document_refuses_to_be_an_isa_manual(self):
        """The document must explicitly state that it is a cost table, not an ISA manual."""
        self.assertIn("SDM", self.md)
        self.assertIn("That is not here", self.md)

    def test_bans_are_quoted_verbatim(self):
        """Forbidden bundle combinations must be quoted verbatim from assembler output."""
        for *_ignored, text in COMBINATION_BANS:
            self.assertIn(text, self.md)


class TestCrossCheckWithVendorDocs(unittest.TestCase):
    """Cross-check against MCST's official guide must remain a comparison, not an import.

    The official guide documents E4C/E8C, whereas our measured profile targets
    e2k-v6. Numbers are cross-checked side-by-side without overwriting local
    measurements.
    """

    def setUp(self):
        from vliw.core.isa import DOC_LATENCY
        self.doc = DOC_LATENCY
        self.rows = {r.name: r for r in collect(get_profile("e2k-v6-measured"))}

    def test_no_stale_entries(self):
        """Every class in DOC_LATENCY must exist in the machine model."""
        for cls in self.doc:
            self.assertIn(cls, self.rows, f"{cls} is in DOC_LATENCY but missing from model")

    def test_known_discrepancy_is_still_there(self):
        """LOAD intentionally differs: 5 cycles measured on e2k-v6 vs 3 in MCST E4C/E8C docs."""
        self.assertEqual(self.rows["LOAD"].latency, 5)
        self.assertEqual(self.doc["LOAD"][0], "3")

    def test_measured_classes_agree_with_docs(self):
        """All other measured classes must match MCST documentation."""
        for cls, row in self.rows.items():
            if cls in ("LOAD",) or cls not in self.doc:
                continue
            if not row.latency_measured:
                continue
            with self.subTest(cls=cls):
                self.assertEqual(str(row.latency), self.doc[cls][0],
                                 f"{cls}: measurement diverged from MCST documentation")


if __name__ == "__main__":
    unittest.main()
