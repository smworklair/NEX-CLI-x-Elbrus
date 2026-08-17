"""Контракт текстового формата граф ⇄ расписание.

Формат — это интерфейс между генератором датасета, обучением и валидатором.
Расходится он молча: модель обучится на чуть другом тексте и просто станет
хуже, никакой ошибки при этом не возникнет.

Отдельно закреплено ОТСУТСТВИЕ завершающего перевода строки. Это уже стоило
одной поломки: внешний генератор ставил '\\n' в конце промпта и ответа, из-за
чего склейка `prompt + "\\n" + completion` давала двойной перевод строки
ровно на стыке, где стоит EOS. См. docs/EOS_INCIDENT.md.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from training.encode import (
    build_schedule,
    clip_placements,
    decode_completion,
    encode_completion,
    encode_prompt,
)
from vliw.core.dag import DAG, Instr
from vliw.core.model import E2K_V6_MEASURED as M
from vliw.core.schedule import Schedule

ROOT = Path(__file__).resolve().parent.parent


def dag(*specs: tuple[str, tuple[int, ...]]) -> DAG:
    return DAG("t", "t", "", [
        Instr(i, f"n{i}", op, preds, f"n{i}")
        for i, (op, preds) in enumerate(specs)
    ])


class TestPromptFormat(unittest.TestCase):
    def setUp(self):
        self.d = dag(("ADD", ()), ("MUL", (0,)), ("STORE", (0, 1)))
        self.p = encode_prompt(self.d, M)

    def test_two_line_header(self):
        lines = self.p.split("\n")
        self.assertEqual(lines[0], f"профиль: {M.name}")
        self.assertEqual(lines[1], "граф:")

    def test_ends_with_schedule_marker_and_no_trailing_newline(self):
        self.assertTrue(self.p.endswith("расписание:"))
        self.assertFalse(self.p.endswith("\n"))

    def test_graph_lines(self):
        lines = self.p.split("\n")[2:-1]
        self.assertEqual(lines, ["0 ADD", "1 MUL <- 0", "2 STORE <- 0 1"])

    def test_profile_name_is_in_prompt(self):
        """Смена профиля обязана быть видна в тексте, а не только в коде."""
        self.assertIn(M.name, self.p)


class TestCompletionFormat(unittest.TestCase):
    def setUp(self):
        self.d = dag(("ADD", ()), ("MUL", (0,)))
        self.s = Schedule(self.d, M)
        self.s.place(1, 1, 3)
        self.s.place(0, 0, 0)          # кладём вразнобой намеренно
        self.c = encode_completion(self.s)

    def test_sorted_by_id_regardless_of_insertion_order(self):
        self.assertEqual(self.c, "0: такт=0 канал=0\n1: такт=1 канал=3")

    def test_no_trailing_newline(self):
        self.assertFalse(self.c.endswith("\n"))

    def test_roundtrip(self):
        self.assertEqual(decode_completion(self.c), {0: (0, 0), 1: (1, 3)})


class TestDecoder(unittest.TestCase):
    def test_tolerates_junk_lines(self):
        text = ("Вот расписание:\n0: такт=0 канал=1\nпояснение от модели\n"
                "1: такт=2 канал=4\n")
        self.assertEqual(decode_completion(text), {0: (0, 1), 1: (2, 4)})

    def test_tolerates_spacing_variants(self):
        self.assertEqual(decode_completion("7:  такт=3   канал=5"), {7: (3, 5)})

    def test_empty_text_gives_nothing(self):
        self.assertEqual(decode_completion("извини, не знаю"), {})

    def test_last_line_wins_on_duplicate_id(self):
        self.assertEqual(decode_completion("0: такт=1 канал=0\n0: такт=9 канал=2"),
                         {0: (9, 2)})


class TestClipAndBuild(unittest.TestCase):
    def test_clip_splits_stray_ids(self):
        keep, extra = clip_placements({0: (0, 0), 1: (1, 1), 5: (2, 2)}, 2)
        self.assertEqual(keep, {0: (0, 0), 1: (1, 1)})
        self.assertEqual(extra, [5])

    def test_negative_ids_are_stray_too(self):
        keep, extra = clip_placements({-1: (0, 0), 0: (0, 1)}, 1)
        self.assertEqual(keep, {0: (0, 1)})
        self.assertEqual(extra, [-1])

    def test_build_schedule_ignores_stray(self):
        d = dag(("ADD", ()))
        s = build_schedule(d, M, {0: (0, 0), 9: (0, 1)})
        self.assertEqual(set(s.placements), {0})
        self.assertEqual(s.validate(), [])


class TestDatasetsMatchEncoder(unittest.TestCase):
    """Файлы на диске должны быть в том же формате, что выдаёт encode.py.

    Проверяется на первой строке каждого датасета: полный прогон делает
    tools/validate_jsonl.py, здесь — быстрая защита от расхождения формата.
    """

    FILES = ("dataset.jsonl", "train_merged.jsonl", "eval_wide.jsonl",
             "training/checkpoints/eval.jsonl")

    def test_first_row_format(self):
        checked = 0
        for name in self.FILES:
            path = ROOT / name
            if not path.exists():
                continue
            checked += 1
            with path.open(encoding="utf-8") as f:
                row = json.loads(f.readline())
            p, c = row["prompt"], row["completion"]
            with self.subTest(file=name):
                self.assertEqual(p.split("\n")[0], f"профиль: {M.name}")
                self.assertEqual(p.split("\n")[1], "граф:")
                self.assertTrue(p.endswith("расписание:"))
                self.assertFalse(p.endswith("\n"), "лишний перевод строки в промпте")
                self.assertFalse(c.endswith("\n"), "лишний перевод строки в ответе")
                ids = [int(line.split(":")[0]) for line in c.split("\n")]
                self.assertEqual(ids, sorted(ids), "строки ответа не по возрастанию id")
        self.assertTrue(checked, "не найдено ни одного датасета для проверки")


if __name__ == "__main__":
    unittest.main()
