# -*- coding: utf-8 -*-
"""Два языка одной и той же метки (класс мнемоники).

Язык названия не видит, в каком канале команда стояла. Язык употребления не видит
букв мнемоники — только как она встретилась в 25 файлах lcc. Класс в токены
не кладётся: иначе сеть учила бы ответ из входа.
"""

from __future__ import annotations

import re
from collections import Counter

ПРИСТАВКИ = ("qp", "q", "p", "f")   # длинные раньше коротких
ШИРИНЫ = set("sdbhwq")
_ЛИТ = re.compile(r"0x[0-9a-f]+|\b\d+\b", re.I)


def корзина(x: int) -> int:
    x = int(x)
    if x <= 8:
        return x
    if x <= 32:
        return 8 + (x - 8 + 3) // 4 * 4
    return 32 + (x - 32 + 7) // 8 * 8


def разобрать(мнемоника: str) -> tuple[list[str], list[str], list[str]]:
    """Приставки, основы частей, суффиксы ширины. Основа не короче одного знака."""
    прист, основы, суф = [], [], []
    for часть in мнемоника.split("_"):
        rest = часть
        while True:
            hit = next((p for p in ПРИСТАВКИ if rest.startswith(p) and len(rest) > len(p)), None)
            if not hit:
                break
            прист.append(hit)
            rest = rest[len(hit):]
        хвост: list[str] = []
        # Один суффикс ширины. У предикатов lcc хвост «sb»/«db»: ширина и форма b.
        # Дальше не глотаем: иначе addd превращается в основу «a».
        if len(rest) > 2 and rest[-2:] in ("sb", "db"):
            хвост = [rest[-2], rest[-1]]
            rest = rest[:-2]
        elif len(rest) > 1 and rest[-1] in ШИРИНЫ:
            хвост = [rest[-1]]
            rest = rest[:-1]
        суф.extend(хвост)
        основы.append(rest if rest else часть)
    return прист, основы, суф


def токены_имени(мнемоника: str) -> list[str]:
    прист, основы, суф = разобрать(мнемоника)
    части = мнемоника.split("_")
    tok = [f"частей:{len(части)}", f"длина:{min(len(мнемоника), 16)}"]
    for i, p in enumerate(части):
        tok.append(f"часть:{i}:{p}")
    tok.append("прист:" + ("+".join(прист) if прист else "нет"))
    for p in прист:
        tok.append(f"приставка:{p}")
    for s in основы:
        tok.append(f"основа:{s}")
    tok.append("суф:" + ("".join(суф) if суф else "нет"))
    for s in суф:
        tok.append(f"ширина:{s}")
    s = "^" + мнемоника + "$"
    for n in (2, 3):
        for i in range(len(s) - n + 1):
            tok.append(f"нг{n}:{s[i:i + n]}")
    return tok


def _вид_приёмника(dst: str | None) -> str:
    d = dst or ""
    if d.startswith("pred"):
        return "пред"
    if "[" in d:
        return "вр"
    if d.startswith("aa") or d.startswith("lsr") or d.startswith("ct"):
        return "служеб"
    if not d or d == "empty":
        return "нет"
    return "рег"


def _виды_текста(text: str) -> set[str]:
    k = set()
    if "[" in text:
        k.add("пам")
    if _ЛИТ.search(text):
        k.add("лит")
    if "pred" in text:
        k.add("пред")
    if "%b[" in text or "%db[" in text or "%g[" in text:
        k.add("вр")
    return k


def токены_употребления(встреча: list[dict], соседи: list[list[dict]]) -> list[str]:
    """встреча: список {channel, srcs, dst, flags, text} по всем вхождениям мнемоники.
    соседи: для каждого вхождения — другие операции того же бандла (мнемоника, channel).
    Пустой список — мнемоники в 25 файлах нет: токены это говорят прямо.
    """
    n = len(встреча)
    if n == 0:
        return ["встреч:0", "srcs:0", "dst:нет", "sm:0", "соседей:0"] + [f"кан{c}:0" for c in range(6)]
    tok = [f"встреч:{корзина(n)}"]
    ch = Counter(o["channel"] for o in встреча)
    for c in range(6):
        tok.append(f"кан{c}:{int(10 * ch.get(c, 0) / n)}")
    tok.append("кан_есть:" + "".join(str(c) for c in range(6) if ch.get(c, 0)))
    sc = Counter(len(o["srcs"]) for o in встреча)
    tok.append(f"srcs:{sc.most_common(1)[0][0]}")
    tok.append(f"srcs_ср:{int(round(10 * sum(len(o['srcs']) for o in встреча) / n))}")
    tok.append(f"sm:{int(10 * sum('sm' in o['flags'] for o in встреча) / n)}")
    виды = Counter()
    for o in встреча:
        for k in _виды_текста(o["text"]):
            виды[k] += 1
    for k in ("пам", "лит", "пред", "вр"):
        tok.append(f"вид:{k}:{int(10 * виды.get(k, 0) / n)}")
    dst = Counter(_вид_приёмника(o["dst"]) for o in встреча)
    tok.append("dst:" + dst.most_common(1)[0][0])
    nb = Counter()
    ширины = []
    for mates in соседи:
        ширины.append(len(mates))
        for m in mates:
            for основа in разобрать(m["mnemonic"])[1]:
                nb[основа] += 1
    tok.append(f"соседей:{min(8, int(sum(ширины) / max(1, len(ширины))))}")
    for основа, c in nb.most_common(6):
        tok.append(f"сосед:{основа}:{min(c, 8)}")
    return tok


class ЯзыкИмени:
    имя = "NNL-ISA-имя"
    версия = "0.1"

    def перевести(self, текст: str) -> dict:
        return {"токены": токены_имени(текст.strip())}

    def паспорт_языка(self) -> dict:
        return {"имя": self.имя, "версия": self.версия}


class ЯзыкУпотребления:
    """перевести(мнемоника) берёт заранее посчитанные токены файлов."""

    имя = "NNL-ISA-употребление"
    версия = "0.1"

    def __init__(self, таблица: dict[str, list[str]] | None = None) -> None:
        self.таблица = таблица or {}

    def перевести(self, текст: str) -> dict:
        mn = текст.strip()
        return {"токены": list(self.таблица.get(mn, ["встреч:0"]))}

    def паспорт_языка(self) -> dict:
        return {"имя": self.имя, "версия": self.версия, "мнемоник": len(self.таблица)}
