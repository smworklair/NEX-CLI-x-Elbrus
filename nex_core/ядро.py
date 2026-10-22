# -*- coding: utf-8 -*-
"""Проводка ядра NEX: техкарта → матплата с блоками → процессор тактов → решатель.

Ядро NNL берётся из nnl_vliw/NNL как есть. Здесь только приложение: читает техкарту, подключает блоки
из неё, превращает граф участка в запрос и отдаёт итог (решения блоков, payload, шина) тому, кто спросил:
панели НЕЙРОСЕТИ и рассказчику (агенту). Любой сбой при сборке — `None`: инструмент работает и без ядра.
"""

from __future__ import annotations

import json
import threading
from pathlib import Path

КОРЕНЬ = Path(__file__).resolve().parent
ТЕХКАРТА = КОРЕНЬ / "техкарта.json"
_замок = threading.Lock()
_кэш: dict = {}


class Система:
    def __init__(self, техкарта: dict, плата, процессор, решатель, причины: list[str]):
        self.техкарта, self.плата, self.процессор, self.решатель = техкарта, плата, процессор, решатель
        self.причины = причины          # почему какой-то блок из техкарты не подключился


def собрать(путь=None) -> Система | None:
    """Собрать ядро по техкарте. Блоки, которые не подключились, записываются в `причины`; нет ни одного — None."""
    import sys

    корень = КОРЕНЬ.parent
    if str(корень) not in sys.path:
        sys.path.insert(0, str(корень))
    from nnl_vliw.NNL.матплата import Матплата
    from nnl_vliw.NNL.процессор import Процессор
    from nnl_vliw.NNL.решатель import Решатель
    from nnl_vliw.NNL.ядро import ЯдроПричинности
    from nex_core.язык import ЯзыкГрафа

    п = Path(путь) if путь else ТЕХКАРТА
    тк = json.loads(п.read_text(encoding="utf-8"))
    плата = Матплата(ЯзыкГрафа(), str(КОРЕНЬ / "архитектуры"))
    причины = []
    for b in тк["блоки"]:
        ok, рез = плата.подключить(str(п.parent / b["папка"]))
        if not ok:
            причины.append(f"{b['имя']}: {'; '.join(рез)}")
    if not плата.блоки:
        return None
    проц = Процессор(плата, ЯдроПричинности(), tau_conf=float(тк.get("порог_уверенности", 1.0)))
    return Система(тк, плата, проц, Решатель(float(тк.get("порог_воздержания", 1.0))), причины)


def система() -> Система | None:
    """Одна на процесс. Не собралась — запоминаем и не пробуем на каждый запрос."""
    if "s" not in _кэш:
        try:
            _кэш["s"] = собрать()
        except Exception:
            _кэш["s"] = None
    return _кэш["s"]


def выполнить(dag, model) -> dict | None:
    """Прогнать участок через ядро. {"решения", "payload", "шина", "конфликты", "блоки", "текст"} или None."""
    с = система()
    if с is None:
        return None
    from nex_core.язык import текст_из_dag

    текст = текст_из_dag(dag, model)
    try:
        with _замок:
            r = с.процессор.выполнить(текст)
            решения = с.решатель.решить(r["финал"])
            payload = {}
            for имя, d in решения.items():
                if имя.startswith("_"):
                    continue
                блок = с.плата.блоки[имя]
                if d["статус"] == "ответ" and hasattr(блок.arch, "экспорт"):
                    payload[имя] = блок.arch.экспорт(блок.obj, r["токены"], {}, d["ответ"])
    except Exception:
        return None
    return {"решения": решения, "payload": payload, "шина": r["шина"], "конфликты": r["конфликты"],
            "блоки": list(с.плата.блоки), "текст": текст}


def факты(dag, model, оракул: int | None = None) -> list[str]:
    """Строки для рассказчика (агента): по одной на блок, фразы берутся из техкарты, чисел своих не добавляют."""
    с = система()
    r = выполнить(dag, model) if с else None
    if r is None:
        return []
    фразы = с.техкарта.get("рассказчику", {})
    строки = []
    for имя, d in r["решения"].items():
        if имя.startswith("_") or имя not in фразы:
            continue
        if d["статус"] != "ответ":
            строки.append(фразы[имя]["не_знаю"])
            continue
        p = r["payload"].get(имя, {})
        орак = f" Оракул: {оракул} т." if оракул is not None else ""
        строки.append(фразы[имя][d["ответ"]].format(
            граница=p.get("граница", "?"), tiny=p.get("tiny", "?"), baseline=p.get("baseline", "?"),
            победитель=p.get("победитель", "?"), выигрыш=p.get("baseline", 0) - p.get("tiny", 0), оракул=орак))
    return строки
