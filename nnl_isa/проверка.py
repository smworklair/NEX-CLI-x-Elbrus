# -*- coding: utf-8 -*-
"""Короткая проверка ядер ISA. Не больше восьми тестов.

    python3 -m unittest nnl_isa.проверка
"""

from __future__ import annotations

import unittest
from pathlib import Path

from nnl_vliw.NNL.линтер import проверить_блок
from nnl_vliw.NNL.матплата import Матплата
from vliw.core.model import E2K_V6_MEASURED

from nnl_isa import данные as Д
from nnl_isa import ядра as Я
from nnl_isa.латентность import вердикт
from nnl_isa.обучить import собрать_блоки
from nnl_isa.оценка import перекрёсток
from nnl_isa.язык import ЯзыкИмени, токены_имени, токены_употребления

КОРЕНЬ = Path(__file__).resolve().parents[1]
ARCH = КОРЕНЬ / "nnl_vliw" / "архитектуры"
БЛОКИ = Path(__file__).resolve().parent / "блоки"


class Проверка(unittest.TestCase):
    def test_класс_ровно_в_одном_блоке(self):
        все = set(E2K_V6_MEASURED.ops)
        а = Я.классы_блока("имя")
        б = Я.классы_блока("употребление")
        self.assertEqual(set(а), все)
        self.assertEqual(set(б), все)
        self.assertEqual(len(а), len(все))
        self.assertTrue(any(а[k] != б[k] for k in все))

    def test_токены_имени_не_содержат_класс(self):
        tok = токены_имени("faddd")
        self.assertTrue(any(t.startswith("приставка:f") for t in tok))
        self.assertTrue(any(t == "основа:add" for t in tok))
        self.assertTrue(any(t == "ширина:d" for t in tok))
        self.assertFalse(any("FADD" in t or t.startswith("класс:") for t in tok))
        пусто = токены_употребления([], [])
        self.assertIn("встреч:0", пусто)

    def test_одиночные_классы_только_в_обучении(self):
        данные = Д.собрать()
        блоки, одиночные, классы = Д.фолды(данные["известные"], k=5, зерно=1)
        в_тесте = {r["класс"] for b in блоки for r in b}
        self.assertTrue(классы)
        self.assertTrue(set(классы).isdisjoint(в_тесте))
        self.assertEqual({r["класс"] for r in одиночные}, set(классы))

    def test_чисел_не_больше_30_тысяч(self):
        for я in ("имя", "употребление"):
            блоки, _о, чисел = собрать_блоки(я, зерно=1)
            self.assertLessEqual(чисел, 30_000)
            self.assertGreater(чисел, 1000)
            self.assertEqual(len({b.соль for b in блоки}), len(блоки))
        а = Я.описание_блоков("имя")[0]["размер"]
        б = Я.описание_блоков("употребление")[0]["размер"]
        self.assertNotEqual(а, б)

    def test_вердикт_зазора(self):
        self.assertEqual(вердикт(1, 0, 5), "опровергнуто")
        self.assertEqual(вердикт(1, 1, 5), "согласуется")
        self.assertEqual(вердикт(1, 4, 5), "сомнительно")
        self.assertEqual(вердикт(1, 0, 2), "мало данных")
        self.assertEqual(вердикт(1, None, 0), "мало данных")

    def test_линтер_и_sha256(self):
        import json
        папка = БЛОКИ / "имя" / "имя_цел_пам"
        res = проверить_блок(str(папка), str(ARCH))
        self.assertEqual(res["статус"], "УСПЕХ", res.get("ошибки"))
        for я in ("имя", "употребление"):
            плата = Матплата(ЯзыкИмени(), str(ARCH))
            всего = 0
            for bd in sorted((БЛОКИ / я).iterdir()):
                if not (bd / "паспорт.json").exists():
                    continue
                ok, msg = плата.подключить(str(bd))
                self.assertTrue(ok, msg)
                ps = json.loads((bd / "паспорт.json").read_text(encoding="utf-8"))
                всего += ps["веса"]["чисел"]
            self.assertLessEqual(всего, 30_000)
            self.assertGreater(всего, 1000)

    def test_такт1_не_зависит_от_соседа(self):
        плата = Матплата(ЯзыкИмени(), str(ARCH))
        a = БЛОКИ / "имя" / "имя_цел_пам"
        b = БЛОКИ / "имя" / "имя_дроб"
        плата.подключить(str(a))
        блок = next(iter(плата.блоки.values()))
        токены = токены_имени("adds")
        один = блок.arch.проход2(блок.obj, токены, {})
        плата.подключить(str(b))
        два = блок.arch.проход2(блок.obj, токены, {})
        self.assertEqual(один, два)

    def test_перекрёсток(self):
        self.assertEqual(перекрёсток("ADD", "ADD"), "ADD")
        self.assertIsNone(перекрёсток("ADD", "MUL"))
        self.assertIsNone(перекрёсток(None, "ADD"))
        self.assertIsNone(перекрёсток(None, None))
        self.assertIsNone(перекрёсток("ADD", None))


if __name__ == "__main__":
    unittest.main()
