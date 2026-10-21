"""Режим «по блокам»: разрез .s на базовые блоки (vliw/core/blocks.py)."""

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from vliw.core import asm_parser
from vliw.core.blocks import (
    BUCKETS, WINDOW_TARGETS, Block, WindowGraph, bucket_of, block_graphs,
    block_graphs_of_file, split_blocks, window_graphs)
from vliw.core.model import get_profile

ROOT = Path(__file__).resolve().parent.parent
ASM_DIR = ROOT / "real_candidates_100_400" / "asm"

# Четыре блока: с переходом; цикл loop_mode; провал вниз по метке; return.
SAMPLE = """\
\t.text
\t.global\tf
f:
\t{
\t  setwd\twsz = 0x4, nfx = 0x1
\t  adds,0\t%r0, %r1, %r2
\t  muls,1\t%r0, %r1, %r3
\t}
\t{
\t  adds,0\t%r2, %r3, %r4
\t  ct\t%ctpr1
\t}
.L1:
\t{
\t  loop_mode
\t  disp\t%ctpr1, .L1
\t  adds,0\t%r4, %r4, %r5
\t}
\t{
\t  loop_mode
\t  adds,0\t%r5, %r4, %r6
\t  ct\t%ctpr1
\t}
.L2:
\t{
\t  adds,0\t%r6, %r6, %r7
\t}
\t{
\t  adds,0\t%r7, %r6, %r8
\t}
.L3:
\t{
\t  adds,0\t%r8, %r8, %r9
\t  return\t%ctpr3
\t}
"""


class TestSplit(unittest.TestCase):
    def test_four_blocks(self):
        bl = split_blocks(SAMPLE)
        self.assertEqual([b.label for b in bl], ["f", ".L1", ".L2", ".L3"])
        self.assertEqual([b.bundles for b in bl], [2, 2, 2, 1])
        self.assertEqual([b.loop for b in bl], [False, True, False, False])
        self.assertEqual([b.index for b in bl], [0, 1, 2, 3])
        self.assertIsInstance(bl[0], Block)

    def test_transfer_closes_block_and_label_closes_fallthrough(self):
        bl = split_blocks(SAMPLE)
        # блок f закончился на `ct`, следующая метка начала новый блок
        self.assertIn("ct", bl[0].text)
        self.assertNotIn(".L1:", bl[0].text)
        # .L2 не заканчивается переходом, его закрыла метка .L3
        self.assertNotIn("return", bl[2].text)
        self.assertIn("return", bl[3].text)

    def test_graphs(self):
        gs = block_graphs(SAMPLE, source="f.s")
        self.assertEqual([g.n for g in gs], [3, 2, 2, 1])
        self.assertEqual(gs[0].dag.key, "f#0")
        # третья операция блока 0 читает результаты обеих предыдущих
        self.assertEqual(gs[0].dag[2].preds, (0, 1))
        # значения снаружи блока зависимостей не создают
        self.assertEqual(gs[1].dag[0].preds, ())

    def test_min_ops_filter(self):
        gs = block_graphs(SAMPLE, min_ops=3)
        self.assertEqual([g.block.label for g in gs], ["f"])
        self.assertEqual(len(block_graphs(SAMPLE, min_ops=0)), 4)  # 0 → как 1

    def test_ops_are_partitioned(self):
        """Блоки разбивают все операции без потерь и повторов."""
        whole = asm_parser.parse_asm(SAMPLE)
        self.assertEqual(sum(g.n for g in block_graphs(SAMPLE)), len(whole.ops))

    def test_empty_and_labels_only(self):
        self.assertEqual(split_blocks(""), [])
        self.assertEqual(split_blocks("\t.text\nf:\n.L1:\n"), [])
        self.assertEqual(block_graphs("\t.text\nf:\n.L1:\n"), [])

    def test_text_without_label_is_one_block(self):
        text = "{\n  adds,0 %r0, %r1, %r2\n}\n{\n  adds,0 %r2, %r2, %r3\n  ct %ctpr1\n}\n"
        bl = split_blocks(text)
        self.assertEqual(len(bl), 1)
        self.assertEqual(bl[0].label, "")
        self.assertEqual(bl[0].bundles, 2)

    def test_buckets(self):
        self.assertEqual([b for b, _ in BUCKETS], ["<10", "10-49", "50-99", "100-199", "200+"])
        for n, want in ((0, "<10"), (9, "<10"), (10, "10-49"), (49, "10-49"), (50, "50-99"),
                        (99, "50-99"), (100, "100-199"), (199, "100-199"), (200, "200+"),
                        (5000, "200+")):
            self.assertEqual(bucket_of(n), want, n)

    def test_lcc_schedule_contract(self):
        gs = block_graphs(SAMPLE, source="f.s")
        sched, why = gs[0].lcc_schedule(get_profile("e2k-v6-measured"))
        self.assertTrue((sched is None) != (why is None))


def chain_asm(n_bundles: int, loop: bool = False, label: str = "f") -> str:
    """Один блок из `n_bundles` широких команд по одной операции: цепочка, где каждая
    читает два предыдущих результата. Последняя команда с `ct` закрывает блок."""
    lines = ["\t.text", f"{label}:"]
    for i in range(n_bundles):
        a = 10 + i
        lines.append("\t{")
        if loop and i == 0:
            lines.append("\t  loop_mode")
        lines.append(f"\t  adds,0\t%r{a - 1}, %r{a - 2}, %r{a}")
        if i == n_bundles - 1:
            lines.append("\t  ct\t%ctpr1")
        lines.append("\t}")
    return "\n".join(lines) + "\n"


class TestWindows(unittest.TestCase):
    def test_sample_blocks_are_too_short_for_windows(self):
        """Во всех блоках SAMPLE меньше 12 операций: окон нет."""
        self.assertEqual(window_graphs(SAMPLE, source="f.s"), [])

    def test_targets_and_sizes(self):
        ws = window_graphs(chain_asm(40), source="w.s")
        self.assertEqual({w.target for w in ws}, set(WINDOW_TARGETS))
        for w in ws:
            self.assertIsInstance(w, WindowGraph)
            self.assertTrue(12 <= w.n <= 56, w.n)
            self.assertLessEqual(w.n, 40)                  # больше блока окно быть не может
            self.assertEqual(w.block_index, 0)
            self.assertFalse(w.loop)
        # сдвиг — примерно полокна: для цели 16 окна начинаются с 0, 8, 16, 24
        self.assertEqual([w.start_bundle for w in ws if w.target == 16], [0, 8, 16, 24])
        self.assertEqual([w.n for w in ws if w.target == 16], [16, 16, 16, 16])

    def test_keys_are_unique_and_name_the_window(self):
        ws = window_graphs(chain_asm(40), source="dir/w.s")
        keys = [w.dag.key for w in ws]
        self.assertEqual(len(keys), len(set(keys)))
        self.assertIn("w#0w8t16", keys)

    def test_min_and_max_ops_filter(self):
        t = chain_asm(40)
        self.assertEqual({w.n for w in window_graphs(t, min_ops=30)}, {32, 40})
        small = window_graphs(t, max_ops=20)
        self.assertTrue(small)
        self.assertTrue(all(12 <= w.n <= 20 for w in small))

    def test_loop_flag_comes_from_the_block(self):
        """Флаг цикла — признак блока: окно без `loop_mode` внутри блока-цикла тоже цикл."""
        ws = window_graphs(chain_asm(40, loop=True), source="w.s")
        self.assertTrue(ws)
        self.assertTrue(all(w.loop for w in ws))
        # `loop_mode` стоит только в первой команде блока, а окна с start_bundle > 0 его не содержат
        self.assertTrue(any(w.start_bundle > 0 for w in ws))

    def test_short_block_gives_one_window_per_target(self):
        """Блок ровно из 12 операций: окно любой цели — весь блок целиком."""
        t = chain_asm(12)
        ws = window_graphs(t, source="b.s")
        self.assertEqual([(w.target, w.start_bundle, w.n) for w in ws],
                         [(16, 0, 12), (24, 0, 12), (32, 0, 12), (48, 0, 12)])
        [blk] = block_graphs(t, source="b.s", min_ops=10)
        sig = [(i.op, i.preds) for i in blk.dag]
        for w in ws:
            self.assertEqual([(i.op, i.preds) for i in w.dag], sig)

    def test_windows_do_not_cross_blocks(self):
        t = chain_asm(14, label="a") + chain_asm(14, label="b")
        ws = window_graphs(t, source="two.s")
        self.assertEqual({w.block_index for w in ws}, {0, 1})
        self.assertTrue(all(w.n <= 14 for w in ws))

    def test_window_dependencies_are_inside_the_window(self):
        for w in window_graphs(chain_asm(40), source="w.s"):
            for i in w.dag:
                self.assertTrue(all(0 <= p < i.id for p in i.preds))


@unittest.skipUnless(ASM_DIR.exists(), "нет real_candidates_100_400/asm")
class TestRealCorpus(unittest.TestCase):
    def test_every_file_is_partitioned(self):
        for p in sorted(ASM_DIR.glob("*.s")):
            with self.subTest(file=p.name):
                text = p.read_text(encoding="utf-8")
                whole = asm_parser.parse_asm(text)
                gs = block_graphs(text, source=p.name)
                self.assertEqual(sum(g.n for g in gs), len(whole.ops))
                for g in gs:
                    self.assertGreater(g.n, 0)
                    self.assertEqual(g.block.loop, "loop_mode" in g.block.text)

    def test_counts_on_the_25_file_corpus(self):
        """Цифры из заметки «GRASP и NEX CLI»: 238 блоков, 6047 операций, 93 блока
        от 10 операций, 42 цикла. Привязаны к корпусу из 25 файлов."""
        files = sorted(ASM_DIR.glob("*.s"))
        if len(files) != 25:
            self.skipTest(f"корпус изменился: {len(files)} файлов вместо 25")
        gs = [g for p in files for g in block_graphs_of_file(p)]
        self.assertEqual(len(gs), 238)
        self.assertEqual(sum(g.n for g in gs), 6047)
        self.assertEqual(sum(1 for g in gs if g.n >= 10), 93)
        self.assertEqual(sum(1 for g in gs if g.block.loop), 42)
        self.assertEqual(sum(1 for g in gs if g.block.loop and g.n >= 10), 14)

    def test_window_count_on_the_25_file_corpus(self):
        """1421 окно на 25 файлах (цели 16/24/32/48, 12..56 операций) — число из замеров."""
        files = sorted(ASM_DIR.glob("*.s"))
        if len(files) != 25:
            self.skipTest(f"корпус изменился: {len(files)} файлов вместо 25")
        ws = [w for p in files
              for w in window_graphs(p.read_text(encoding="utf-8"), source=p.name)]
        self.assertEqual(len(ws), 1421)
        self.assertTrue(all(12 <= w.n <= 56 for w in ws))


class TestBlockReportTool(unittest.TestCase):
    def test_smoke(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "sample.s"
            p.write_text(SAMPLE, encoding="utf-8")
            out = subprocess.run(
                [sys.executable, str(ROOT / "tools" / "block_report.py"), str(p),
                 "--oracle", "0", "--min-ops", "2", "--json", str(Path(d) / "rows.json")],
                capture_output=True, text=True, timeout=120, cwd=d)
            self.assertEqual(out.returncode, 0, out.stderr)
            self.assertIn("[1] блоков 4, операций 8", out.stdout)
            self.assertIn("ИТОГО n >= 2", out.stdout)
            self.assertIn("[4]", out.stdout)
            import json
            rows = json.loads((Path(d) / "rows.json").read_text(encoding="utf-8"))
            self.assertEqual([r["n"] for r in rows], [3, 2, 2, 1])
            self.assertTrue(all(r["base"] is not None for r in rows))
            # блок из одной операции короче --min-ops: крошки не запускались
            self.assertIsNone(rows[3]["tiny"])


if __name__ == "__main__":
    unittest.main()
