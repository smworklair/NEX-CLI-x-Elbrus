"""Скелет ограниченной генерации: что подставлено, что выбирает модель.

Проверяется чистая часть (`plan_segments`) — без torch и без GPU. Сам цикл
инференса (`constrained_generate`) требует модели и проверяется на Kaggle;
здесь закреплено то, ради чего ограничение и вводилось: структура ответа
задана скелетом, а канал выбирается только из портов, на которых операция
физически исполнима.
"""

from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

from vliw.core.model import E2K_V6_MEASURED as MODEL

_ROOT = Path(__file__).resolve().parent.parent


def _load_validate_kaggle():
    """validate_kaggle.py самодостаточен и не импортируется как пакет.

    Грузим по пути: тяжёлые torch/peft там внутри main(), на уровне модуля
    только stdlib — импорт дёшев и на машине без GPU.
    """
    spec = importlib.util.spec_from_file_location(
        "validate_kaggle", _ROOT / "training" / "validate_kaggle.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


VK = _load_validate_kaggle()


def instrs(*specs):
    return [VK.Instr(i, op, preds) for i, (op, preds) in enumerate(specs)]


class TestPlanSegments(unittest.TestCase):
    def test_skeleton_shape(self):
        segs = VK.plan_segments(instrs(("ADD", ()), ("MUL", (0,))))
        # на инструкцию: «\nN: такт=» → цифры такта → « канал=» → цифра канала
        self.assertEqual([s[0] for s in segs],
                         ["force", "digits", "force", "choice"] * 2)

    def test_forced_text_matches_training_format(self):
        """prompt + '\\n' + completion, строки через '\\n', хвоста нет."""
        segs = VK.plan_segments(instrs(("ADD", ()), ("ADD", ())))
        forced = [s[1] for s in segs if s[0] == "force"]
        self.assertEqual(forced[0], "\n0: такт=")
        self.assertEqual(forced[2], "\n1: такт=")
        self.assertTrue(all(f == " канал=" for f in forced[1::2]))

    def test_channels_limited_to_executable_ports(self):
        """Канал выбирается лишь там, где операция исполнима — по model.py."""
        for op in ("ADD", "MUL", "DIV", "LOAD", "STORE"):
            with self.subTest(op=op):
                segs = VK.plan_segments(instrs((op, ())))
                choice = next(s for s in segs if s[0] == "choice")
                self.assertEqual(choice[1], MODEL.channels_for(op))

    def test_divider_choice_is_single_port(self):
        """У деления выбора нет вовсе: единственный порт ,5."""
        segs = VK.plan_segments(instrs(("DIV", ())))
        self.assertEqual(next(s for s in segs if s[0] == "choice")[1], (5,))

    def test_one_line_per_instruction(self):
        segs = VK.plan_segments(instrs(*[("ADD", ())] * 7))
        self.assertEqual(sum(1 for s in segs if s[0] == "digits"), 7)

    def test_ids_are_consecutive_and_ordered(self):
        segs = VK.plan_segments(instrs(*[("ADD", ())] * 5))
        ids = [s[1].split(":")[0].strip() for s in segs
               if s[0] == "force" and ":" in s[1]]
        self.assertEqual(ids, ["0", "1", "2", "3", "4"])


class TestRenderedSkeleton(unittest.TestCase):
    """Собранный из скелета ответ обязан разбираться штатным парсером."""

    def test_roundtrip_through_decoder(self):
        d = instrs(("ADD", ()), ("DIV", ()), ("MUL", (0,)))
        segs = VK.plan_segments(d)
        # подставляем вместо модели: такт=0 и первый допустимый канал
        parts = []
        for s in segs:
            if s[0] == "force":
                parts.append(s[1])
            elif s[0] == "digits":
                parts.append("0")
            else:
                parts.append(str(s[1][0]))
        text = "".join(parts)

        decoded = VK.decode_completion(text)
        self.assertEqual(sorted(decoded), [0, 1, 2])
        self.assertEqual(decoded[1][1], 5, "деление обязано попасть на ,5")
        keep, extra = VK.clip_placements(decoded, len(d))
        self.assertEqual(extra, [], "лишних id скелет породить не может")
        self.assertEqual(len(keep), len(d), "дыр в id скелет породить не может")


class TestDigitTokens(unittest.TestCase):
    def test_rejects_multi_token_digits(self):
        """Токенизатор, склеивающий цифры, обязан быть отвергнут явно."""
        class FakeTok:
            def __call__(self, s, add_special_tokens=True):
                return {"input_ids": [1, 2] if s == "7" else [1]}

        with self.assertRaises(SystemExit) as cm:
            VK.digit_token_ids(FakeTok())
        self.assertIn("7", str(cm.exception))

    def test_accepts_single_token_digits(self):
        class FakeTok:
            def __call__(self, s, add_special_tokens=True):
                return {"input_ids": [100 + int(s)]}

        got = VK.digit_token_ids(FakeTok())
        self.assertEqual(got["0"], 100)
        self.assertEqual(got["9"], 109)


if __name__ == "__main__":
    unittest.main()
