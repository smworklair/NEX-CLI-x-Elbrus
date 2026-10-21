# -*- coding: utf-8 -*-
"""Обучение двух ядер (nnl_vliw/ядра.py) на метках портфеля.

    python3 -m nnl_vliw.обучить --метки <папка с train_*.labels.jsonl> [--выход nnl_vliw/блоки] [--зерно 1]

Использует обучающий код NNL как есть (обучение/сеть.py, копия с коммита 6b0c9e0): numpy, градиенты
вручную, те же формулы, что у ядра. Пишет блоки в <выход>/<ядро>/<блок>/{паспорт.json, веса.npz}.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from datetime import datetime
from pathlib import Path

from . import данные as Д
from . import ядра as Я
from .обучение import сеть as С
from .язык import ВСЕ_ПОНЯТИЯ, ЯзыкГрафов

НАСТРОЙКИ_ОБУЧЕНИЯ = {"эпох": 20, "терпение": 4, "пакет": 64, "lr": 0.01, "λ": 1.0}
ГРАНИЦА, СВЁРТКА, МАСШТАБ = 8.0, "корень", 8.0


def sha256_файла(путь) -> str:
    h = hashlib.sha256()
    with open(путь, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def обучить_ядро(ядро: str, tr_база, dv_база, зерно: int, выход: Path, сведения: dict) -> dict:
    опис = Я.описание_блоков(ядро)
    блоки = [С.БлокУч(о["имя"], о["ответы"], о["пишет"], о["читает"], корзины=о["корзины"], размер=о["размер"],
                      граница=ГРАНИЦА, соль=о["соль"], seed=зерно * 100 + i, область=о["область"],
                      роль=f"выбор группы портфеля для графов «{о['область']}»", свёртка=СВЁРТКА,
                      масштаб_чтения=МАСШТАБ)
             for i, о in enumerate(опис)]
    tr = С.Набор(Д.строки_ядра(ядро, tr_база), блоки, ВСЕ_ПОНЯТИЯ)
    dv = С.Набор(Д.строки_ядра(ядро, dv_база), блоки, ВСЕ_ПОНЯТИЯ)
    сеть = С.Сеть(блоки, проходов=2, смешивание="среднее", градиент_через_шину=False, шум_шины=0.0)
    папка = выход / ядро
    папка.mkdir(parents=True, exist_ok=True)
    cfg = НАСТРОЙКИ_ОБУЧЕНИЯ
    итог = С.обучить(сеть, tr, dv, эпох=cfg["эпох"], терпение=cfg["терпение"], пакет=cfg["пакет"], lr=cfg["lr"],
                     λ=cfg["λ"], p_выходной=0.0, seed=зерно, журнал=str(папка / "обучение.jsonl"), имя=f"ядро {ядро}")
    язык = ЯзыкГрафов().паспорт_языка()
    for b, о in zip(блоки, опис):
        bd = папка / b.имя
        bd.mkdir(parents=True, exist_ok=True)
        w = bd / "веса.npz"
        b.сохранить(str(w))
        паспорт = {
            "имя": b.имя, "версия": 1, "роль": b.роль, "область": о["область"], "архитектура": "мешок_шина",
            "настройки": {"корзины": b.B, "размер": b.d, "граница": b.L, "соль": b.соль, "свёртка": b.свёртка,
                          "масштаб_чтения": b.масштаб},
            "веса": {"файл": "веса.npz", "sha256": sha256_файла(w), "чисел": b.чисел()},
            "язык": язык, "пишет": b.пишет, "читает": b.читает, "ответы": b.ответы,
            "проекции": {a: {о["область"]: 16.0} for a in b.ответы},
            "обучение": {"скрипт": "nnl_vliw/обучить.py", "ядро": ядро, "зерно": зерно,
                         "когда": datetime.now().isoformat(timespec="seconds"), "данные": сведения,
                         "эпох": итог["эпох"], "лучший_dev": итог["лучший_dev"], "настройки": cfg,
                         "вместе_с": [x.имя for x in блоки if x is not b]},
        }
        (bd / "паспорт.json").write_text(json.dumps(паспорт, ensure_ascii=False, indent=1), encoding="utf-8")
    (папка / "ход_обучения.json").write_text(json.dumps(итог, ensure_ascii=False, indent=1), encoding="utf-8")
    return итог


def main() -> int:
    for _s in (sys.stdout, sys.stderr):
        try:
            _s.reconfigure(errors="replace", encoding="utf-8")
        except Exception:  # noqa: BLE001
            pass
    ap = argparse.ArgumentParser(description="Обучение двух ядер NNL для выбора группы портфеля")
    ap.add_argument("--метки", required=True, help="папка с train_*.labels.jsonl")
    ap.add_argument("--выход", default=str(Path(__file__).parent / "блоки"))
    ap.add_argument("--зерно", type=int, default=1)
    ap.add_argument("--доля-жадных", type=float, default=1.0)
    ap.add_argument("--ядра", default="А,Б")
    a = ap.parse_args()
    t0 = time.time()
    метки = []
    for p in sorted(Path(a.метки).glob("train_*.labels.jsonl")):
        метки += Д.прочитать_метки(p)
    база = Д.с_токенами(метки)
    tr, dv = Д.разбить(база, доля_жадных=a.доля_жадных, зерно=a.зерно)
    из_них_трудных = sum(1 for r in база if r["дешёвая"] != "greedy")
    сведения = {"графов_в_метках": len(база), "трудных": из_них_трудных, "обучение": len(tr), "dev": len(dv),
                "доля_жадных": a.доля_жадных, "зерно": a.зерно}
    print("данные:", json.dumps(сведения, ensure_ascii=False), "%.0f с" % (time.time() - t0), flush=True)
    for i, я in enumerate(a.ядра.split(",")):
        обучить_ядро(я.strip(), tr, dv, a.зерно * 10 + i + 1, Path(a.выход), сведения)
    print("готово за %.0f с" % (time.time() - t0))
    return 0


if __name__ == "__main__":
    sys.exit(main())
