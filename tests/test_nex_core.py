"""NEX core: single NNL network with composite scheduler block (TINY + lower-bound rule)."""

from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from vliw import cli
from vliw.core.dag import compute_metrics
from vliw.tiny.features import build_dag, parse_graph_entries
from vliw.tiny.scheduler import TinyScheduler

from nex_core import ядро
from nex_core.язык import ЯзыкГрафа, текст_из_dag, текст_из_токенов

ROOT = Path(__file__).resolve().parent.parent
BLOCK = ROOT / "nex_core" / "блоки" / "планировщик"
ARCH = ROOT / "nex_core" / "архитектуры"


def _session(scenario):
    s = cli.Session(args=cli._build_parser().parse_args([]))
    s.set_scenario(scenario)
    return s


class TestLanguage(unittest.TestCase):
    def test_graph_survives_tokens_and_back(self):
        for sc in cli.SCENARIOS:
            s = _session(sc)
            dag, model = s.dag_obj, s.model()
            tokens = ЯзыкГрафа().перевести(текст_из_dag(dag, model))["токены"]
            text, profile = текст_из_токенов(tokens)
            again = build_dag(parse_graph_entries(text))
            self.assertEqual(profile, model.name)
            self.assertEqual([(i.op, tuple(i.preds)) for i in again], [(i.op, tuple(i.preds)) for i in dag], sc)


class TestBlock(unittest.TestCase):
    def test_nnl_linter_accepts_block(self):
        import importlib.util

        spec = importlib.util.spec_from_file_location("nnl_linter", ROOT / "nnl_vliw" / "NNL" / "линтер.py")
        lin = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(lin)
        r = lin.проверить_блок(str(BLOCK), str(ARCH))
        self.assertEqual(r["статус"], "УСПЕХ", r)
        self.assertEqual(r["ошибки"], [])

    def test_tampered_block_weights_are_rejected(self):
        from nnl_vliw.NNL.матплата import Матплата

        with tempfile.TemporaryDirectory() as t:
            copy_dir = Path(t) / "планировщик"
            shutil.copytree(BLOCK, copy_dir)
            (copy_dir / "веса.npz").write_bytes((copy_dir / "веса.npz").read_bytes() + b"\0")
            ok, errors = Матплата(ЯзыкГрафа(), str(ARCH)).подключить(str(copy_dir))
            self.assertFalse(ok)
            self.assertTrue(any("sha256" in e for e in errors))

    def test_changed_crumb_weights_are_rejected(self):
        from nex_core.архитектуры import планировщик as SCHED_ARCH

        with tempfile.TemporaryDirectory() as t:
            fake = Path(t) / "weights.json"
            fake.write_text("{}", encoding="utf-8")
            orig = SCHED_ARCH.файлы_крошек
            try:
                SCHED_ARCH.файлы_крошек = lambda: [fake] + orig()[1:]
                fake2 = fake.with_name("weights.json")
                self.assertTrue(fake2.exists())
                with self.assertRaises(ValueError):
                    SCHED_ARCH.загрузить(str(BLOCK / "веса.npz"), {})
            finally:
                SCHED_ARCH.файлы_крошек = orig

    def test_garbage_request_means_dont_know(self):
        from nex_core.архитектуры import планировщик as SCHED_ARCH
        obj = SCHED_ARCH.загрузить(str(BLOCK / "веса.npz"), {})
        scores = SCHED_ARCH.проход2(obj, ["junk", "u:0:NOSUCH"], {})
        self.assertEqual(set(scores.values()), {0.0})


class TestCore(unittest.TestCase):
    def test_core_matches_direct_crumbs_on_every_scenario(self):
        for sc in cli.SCENARIOS:
            s = _session(sc)
            base, _orc, _ = s.results()
            dag, model = s.dag_obj, s.model()
            r = ядро.выполнить(dag, model)
            self.assertIsNotNone(r, sc)
            d = r["решения"]["планировщик"]
            self.assertEqual(d["статус"], "ответ", sc)
            p = r["payload"]["планировщик"]
            direct = TinyScheduler().schedule(dag, model).schedule.makespan
            m = compute_metrics(dag, model)
            self.assertEqual(p["baseline"], base.schedule.makespan, sc)
            self.assertEqual(p["tiny"], direct, sc)
            self.assertTrue(p["законно"], sc)
            self.assertEqual(d["ответ"] == "граница_достигнута",
                             base.schedule.makespan <= max(m.critical_path_bound, m.resource_bound), sc)

    def test_removing_and_returning_block_changes_nothing(self):
        s = _session("slotclash")
        s.results()
        before = ядро.выполнить(s.dag_obj, s.model())["решения"]["планировщик"]["ответ"]
        sys_obj = ядро.система()
        self.assertTrue(sys_obj.плата.снять("планировщик"))
        try:
            self.assertEqual(sys_obj.плата.блоки, {})
        finally:
            ok, _ = sys_obj.плата.подключить(str(BLOCK))
            self.assertTrue(ok)
        after = ядро.выполнить(s.dag_obj, s.model())["решения"]["планировщик"]["ответ"]
        self.assertEqual(before, after)

    def test_techcard_without_working_blocks_gives_none(self):
        with tempfile.TemporaryDirectory() as t:
            cfg = json.loads((ROOT / "nex_core" / "техкарта.json").read_text(encoding="utf-8"))
            cfg["блоки"] = [{"имя": "missing", "папка": "блоки/missing"}]
            cfg_path = Path(t) / "техкарта.json"
            cfg_path.write_text(json.dumps(cfg, ensure_ascii=False), encoding="utf-8")
            self.assertIsNone(ядро.собрать(cfg_path))

    def test_narrator_gets_phrase_from_techcard(self):
        s = _session("slotclash")
        base, orc, _ = s.results()
        lines = ядро.факты(s.dag_obj, s.model(), orc.schedule.makespan)
        self.assertEqual(len(lines), 1)
        self.assertIn("ядро NEX", lines[0])
        self.assertIn("23", lines[0])


if __name__ == "__main__":
    unittest.main()
