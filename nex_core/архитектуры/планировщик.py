# -*- coding: utf-8 -*-
"""Архитектура составного блока «планировщик» (код без весов; веса — в папке блока).

Снаружи — обычный блок NNL: паспорт, веса.npz, закрытый список ответов, проход2(). Внутри — крошки
(vliw/tiny/) и точное правило границы. Крошки остаются там, где лежат; в веса.npz записаны имена и sha256 их
файлов: подмена весов крошек отвергается при подключении, как и подмена обычных весов.

Ответы (ровно один получает счёт 8, остальные 0):
  граница_достигнута      baseline уже на нижней границе — выигрыша нет, это доказательство, не оценка;
  крошки_лучше_baseline   законное расписание крошек короче baseline;
  крошки_вровень          крошки не хуже baseline, но и не лучше.
Расписание небезопасное или разбор упал — все счёты 0: решатель честно скажет «не знаю».
Блок детерминирован и от соседей не зависит (читает = []), контракт изоляции NNL выполнен.
"""
import hashlib
import json
import sys
import time
from pathlib import Path

import numpy as np

ОТВЕТЫ = ["граница_достигнута", "крошки_лучше_baseline", "крошки_вровень"]
КОРЕНЬ = Path(__file__).resolve().parents[2]


def _sha256(путь) -> str:
    h = hashlib.sha256()
    with open(путь, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _числа_в_json(x) -> int:
    if isinstance(x, (int, float)) and not isinstance(x, bool):
        return 1
    if isinstance(x, list):
        return sum(_числа_в_json(v) for v in x)
    if isinstance(x, dict):
        return sum(_числа_в_json(v) for v in x.values())
    return 0


def файлы_крошек() -> list[Path]:
    папка = КОРЕНЬ / "vliw" / "tiny"
    return [папка / n for n in ("weights.json", "weights_defer.json", "weights_hold.json")]


def загрузить(путь, паспорт):
    if str(КОРЕНЬ) not in sys.path:
        sys.path.insert(0, str(КОРЕНЬ))
    with np.load(путь, allow_pickle=False) as z:
        имена = [str(x) for x in z["файлы"]]
        суммы = [str(x) for x in z["sha256"]]
    по_имени = {p.name: p for p in файлы_крошек()}
    for имя, сумма in zip(имена, суммы):
        if имя not in по_имени or not по_имени[имя].is_file():
            raise ValueError(f"нет файла весов крошек {имя!r}")
        if _sha256(по_имени[имя]) != сумма:
            raise ValueError(f"веса крошек {имя!r} не совпадают с блоком (sha256): подмена или переобучение")
    from vliw.tiny.scheduler import TinyScheduler

    return {"tiny": TinyScheduler(), "кэш": (None, None), "ответы": list(ОТВЕТЫ),
            "чисел": int(sum(_числа_в_json(json.loads(по_имени[n].read_text(encoding="utf-8"))) for n in имена))}


def ответы(obj):
    return obj["ответы"]


def пишет(obj):
    return ["планировщик:граница", "планировщик:выигрыш_крошек"]


def читает(obj):
    return []


def чисел(obj):
    return obj["чисел"]


def _посчитать(obj, токены):
    """Один прогон на запрос; для проход2 и экспорт общий (кэш по содержимому запроса)."""
    ключ = tuple(токены)
    if obj["кэш"][0] == ключ:
        return obj["кэш"][1]
    рез = None
    try:
        from nex_core.язык import текст_из_токенов
        from vliw.core.baseline import GreedyListScheduler
        from vliw.core.dag import compute_metrics
        from vliw.core.model import get_profile
        from vliw.tiny.features import build_dag, parse_graph_entries

        текст, профиль = текст_из_токенов(list(токены))
        model = get_profile(профиль)
        dag = build_dag(parse_graph_entries(текст))
        if len(dag) == 0:
            raise ValueError("пустой граф")
        база = GreedyListScheduler().schedule(dag, model)
        m = compute_metrics(dag, model)
        lb = max(m.critical_path_bound, m.resource_bound)
        t0 = time.perf_counter()
        крош = obj["tiny"].schedule(dag, model)
        мс = (time.perf_counter() - t0) * 1000.0
        законно = (not крош.schedule.validate()) and крош.schedule.complete
        рез = {"baseline": база.schedule.makespan, "граница": lb, "tiny": крош.schedule.makespan,
               "победитель": str(крош.search_stats.get("tiny_winner", "?")), "мс": мс, "законно": bool(законно),
               "профиль": профиль, "n": len(dag)}
    except Exception as e:  # любой сбой — не угадываем, а воздерживаемся
        рез = {"ошибка": f"{type(e).__name__}: {e}"}
    obj["кэш"] = (ключ, рез)
    return рез


def проход2(obj, токены, шина):
    р = _посчитать(obj, токены)
    счёты = {a: 0.0 for a in obj["ответы"]}
    if "ошибка" in р or not р["законно"]:
        return счёты
    if р["baseline"] <= р["граница"]:
        счёты["граница_достигнута"] = 8.0
    elif р["tiny"] < р["baseline"]:
        счёты["крошки_лучше_baseline"] = 8.0
    else:
        счёты["крошки_вровень"] = 8.0
    return счёты


def экспорт(obj, токены, шина, top_ответ):
    """Структурированный ответ блока: числа и пояснение причины, без текста от модели."""
    р = dict(_посчитать(obj, токены))
    р["ответ"] = top_ответ
    return р
