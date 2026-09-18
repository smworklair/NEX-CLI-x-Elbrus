"""Крошка-1: MLP приоритетов. Инференс — чистый stdlib, без numpy.

Архитектура по умолчанию 18 -> 128 -> 64 -> 1:
  18*128+128 = 2432, 128*64+64 = 8256, 64*1+1 = 65 -> ~10.7К параметров.
Опция --hidden 256 128 дает ~37К. Обе под лимитом 150К с запасом.

Веса — обычный JSON (списки): загрузка без numpy, прямой проход на графе
n=24 это ~10К умножений — микросекунды.
"""

from __future__ import annotations

import json
import math
import random

from .features import FEATURE_NAMES, N_FEATURES


def _relu(x: float) -> float:
    return x if x > 0.0 else 0.0


class TinyPriority:
    def __init__(self, w1, b1, w2, b2, w3, b3) -> None:
        self.w1 = w1  # [F][H1]
        self.b1 = b1  # [H1]
        self.w2 = w2  # [H1][H2]
        self.b2 = b2  # [H2]
        self.w3 = w3  # [H2]
        self.b3 = b3  # float

    @property
    def h1(self) -> int:
        return len(self.b1)

    @property
    def h2(self) -> int:
        return len(self.b2)

    def param_count(self) -> int:
        f = len(self.w1)
        return f * self.h1 + self.h1 + self.h1 * self.h2 + self.h2 + self.h2 + 1

    def scores(self, X: list[list[float]]) -> list[float]:
        """Прямой проход для всех узлов графа."""
        out: list[float] = []
        h1, h2 = self.h1, self.h2
        for row in X:
            a1 = [0.0] * h1
            for j in range(h1):
                s = self.b1[j]
                for i, v in enumerate(row):
                    if v:
                        s += v * self.w1[i][j]
                a1[j] = _relu(s)
            a2 = [0.0] * h2
            for j in range(h2):
                s = self.b2[j]
                for k in range(h1):
                    if a1[k]:
                        s += a1[k] * self.w2[k][j]
                a2[j] = _relu(s)
            s = self.b3
            for k in range(h2):
                if a2[k]:
                    s += a2[k] * self.w3[k]
            out.append(s)
        return out

    def to_dict(self) -> dict:
        return {
            "arch": "mlp",
            "features": list(FEATURE_NAMES),
            "n_features": N_FEATURES,
            "hidden": [self.h1, self.h2],
            "w1": self.w1, "b1": self.b1,
            "w2": self.w2, "b2": self.b2,
            "w3": self.w3, "b3": self.b3,
        }

    def save(self, path: str) -> None:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f)

    @staticmethod
    def load(path: str) -> "TinyPriority":
        with open(path, encoding="utf-8") as f:
            d = json.load(f)
        return TinyPriority(d["w1"], d["b1"], d["w2"], d["b2"], d["w3"], d["b3"])

    @staticmethod
    def init(n_features: int = N_FEATURES, hidden: tuple[int, int] = (128, 64),
             seed: int = 0) -> "TinyPriority":
        rnd = random.Random(seed)
        h1, h2 = hidden
        # He-инициализация под ReLU.
        s1 = math.sqrt(2.0 / n_features)
        w1 = [[rnd.gauss(0.0, s1) for _ in range(h1)] for _ in range(n_features)]
        b1 = [0.0] * h1
        s2 = math.sqrt(2.0 / h1)
        w2 = [[rnd.gauss(0.0, s2) for _ in range(h2)] for _ in range(h1)]
        b2 = [0.0] * h2
        s3 = math.sqrt(2.0 / h2)
        w3 = [rnd.gauss(0.0, s3) for _ in range(h2)]
        b3 = 0.0
        return TinyPriority(w1, b1, w2, b2, w3, b3)
