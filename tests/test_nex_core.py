"""Ядро NEX: одна нейросеть NNL с составным блоком «планировщик» (крошки + правило границы)."""

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
БЛОК = ROOT / "nex_core" / "блоки" / "планировщик"
АРХ = ROOT / "nex_core" / "архитектуры"


def _session(сценарий):
    s = cli.Session(args=cli._build_parser().parse_args([]))
    s.set_scenario(сценарий)
    return s


class TestLanguage(unittest.TestCase):
    def test_graph_survives_tokens_and_back(self):
        for sc in cli.SCENARIOS:
            s = _session(sc)
            dag, model = s.dag_obj, s.model()
            токены = ЯзыкГрафа().перевести(текст_из_dag(dag, model))["токены"]
            текст, профиль = текст_из_токенов(токены)
            again = build_dag(parse_graph_entries(текст))
            self.assertEqual(профиль, model.name)
            self.assertEqual([(i.op, tuple(i.preds)) for i in again], [(i.op, tuple(i.preds)) for i in dag], sc)


class TestBlock(unittest.TestCase):
    def test_nnl_linter_accepts_block(self):
        import importlib.util

        spec = importlib.util.spec_from_file_location("nnl_linter", ROOT / "nnl_vliw" / "NNL" / "линтер.py")
        lin = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(lin)
        r = lin.проверить_блок(str(БЛОК), str(АРХ))
        self.assertEqual(r["статус"], "УСПЕХ", r)
        self.assertEqual(r["ошибки"], [])

    def test_tampered_block_weights_are_rejected(self):
        from nnl_vliw.NNL.матплата import Матплата

        with tempfile.TemporaryDirectory() as t:
            копия = Path(t) / "планировщик"
            shutil.copytree(БЛОК, копия)
            (копия / "веса.npz").write_bytes((копия / "веса.npz").read_bytes() + b"\0")
            ok, ошибки = Матплата(ЯзыкГрафа(), str(АРХ)).подключить(str(копия))
            self.assertFalse(ok)
            self.assertTrue(any("sha256" in e for e in ошибки))

    def test_changed_crumb_weights_are_rejected(self):
        from nex_core.архитектуры import планировщик as П

        with tempfile.TemporaryDirectory() as t:
            подмена = Path(t) / "weights.json"
            подмена.write_text("{}", encoding="utf-8")
            было = П.файлы_крошек
            try:
                П.файлы_крошек = lambda: [подмена] + было()[1:]
                подмена2 = подмена.with_name("weights.json")
                self.assertTrue(подмена2.exists())
                with self.assertRaises(ValueError):
                    П.загрузить(str(БЛОК / "веса.npz"), {})
            finally:
                П.файлы_крошек = было

    def test_garbage_request_means_dont_know(self):
        from nex_core.архитектуры import планировщик as П
        obj = П.загрузить(str(БЛОК / "веса.npz"), {})
        счёты = П.проход2(obj, ["мусор", "у:0:НЕТТАКОЙ"], {})
        self.assertEqual(set(счёты.values()), {0.0})


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
            прямой = TinyScheduler().schedule(dag, model).schedule.makespan
            m = compute_metrics(dag, model)
            self.assertEqual(p["baseline"], base.schedule.makespan, sc)
            self.assertEqual(p["tiny"], прямой, sc)
            self.assertTrue(p["законно"], sc)
            self.assertEqual(d["ответ"] == "граница_достигнута",
                             base.schedule.makespan <= max(m.critical_path_bound, m.resource_bound), sc)

    def test_removing_and_returning_block_changes_nothing(self):
        s = _session("slotclash")
        s.results()
        до = ядро.выполнить(s.dag_obj, s.model())["решения"]["планировщик"]["ответ"]
        с = ядро.система()
        self.assertTrue(с.плата.снять("планировщик"))
        try:
            self.assertEqual(с.плата.блоки, {})
        finally:
            ok, _ = с.плата.подключить(str(БЛОК))
            self.assertTrue(ok)
        после = ядро.выполнить(s.dag_obj, s.model())["решения"]["планировщик"]["ответ"]
        self.assertEqual(до, после)

    def test_techcard_without_working_blocks_gives_none(self):
        with tempfile.TemporaryDirectory() as t:
            тк = json.loads((ROOT / "nex_core" / "техкарта.json").read_text(encoding="utf-8"))
            тк["блоки"] = [{"имя": "нет", "папка": "блоки/нет"}]
            путь = Path(t) / "техкарта.json"
            путь.write_text(json.dumps(тк, ensure_ascii=False), encoding="utf-8")
            self.assertIsNone(ядро.собрать(путь))

    def test_narrator_gets_phrase_from_techcard(self):
        s = _session("slotclash")
        base, orc, _ = s.results()
        строки = ядро.факты(s.dag_obj, s.model(), orc.schedule.makespan)
        self.assertEqual(len(строки), 1)
        self.assertIn("ядро NEX", строки[0])
        self.assertIn("23", строки[0])


if __name__ == "__main__":
    unittest.main()
