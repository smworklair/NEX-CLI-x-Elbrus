# -*- coding: utf-8 -*-
"""Архитектура блока «мешок-шина» (код без весов; веса — в папке блока).

Блок читает токены языка (мешок слов языка) и шину. Внутри:
  h = сумма векторов токенов / √n (или / n — настройка «свёртка»); свой словарь блока: номер = crc32(соль + токен) mod корзины;
  проход 1 — вклад на шину: для каждого понятия, которое блок пишет, c = L·tanh((h·A + a)/L) — оценка в логарифме шансов;
  проход 2 — счёты своих ответов: s = h·U + x·V + b, где x — числа шины (делённые на «масштаб_чтения») по понятиям, которые блок читает, и признаки
  присутствия этих понятий (1 — понятие на шине есть, 0 — его никто не написал).
Счёт линеен по шине, поэтому ядро может точно разложить его на вклады блоков (разложить()).
Обучение — обучение/сеть.py (те же формулы, пакетами)."""
import zlib

import numpy as np


def индекс(соль, токен, корзины):
    return zlib.crc32((соль + "\x1f" + токен).encode("utf-8")) % корзины


def индексы(соль, токены, корзины):
    return np.fromiter((индекс(соль, t, корзины) for t in токены), dtype=np.int64, count=len(токены))


def загрузить(путь, паспорт):
    with np.load(путь, allow_pickle=False) as z:
        P = {k: z[k] for k in z.files}
    cfg = паспорт["настройки"]
    obj = {k: P[k] for k in ("E", "A", "a", "U", "V", "b")}
    obj["пишет"] = [str(x) for x in P["пишет"]]
    obj["читает"] = [str(x) for x in P["читает"]]
    obj["ответы"] = [str(x) for x in P["ответы"]]
    obj["соль"], obj["корзины"], obj["L"] = cfg["соль"], int(cfg["корзины"]), float(cfg["граница"])
    obj["свёртка"] = cfg.get("свёртка", "среднее")
    obj["масштаб"] = float(cfg.get("масштаб_чтения", 1.0))
    obj["_номер"] = {a: j for j, a in enumerate(obj["ответы"])}
    obj["_кэш"] = (None, None)
    B, d = obj["E"].shape
    W, R2, Y = len(obj["пишет"]), 2 * len(obj["читает"]), len(obj["ответы"])
    assert B == obj["корзины"], "размер таблицы не равен числу корзин"
    assert obj["A"].shape == (d, W) and obj["a"].shape == (W,), "форма A/a"
    assert obj["U"].shape == (d, Y) and obj["b"].shape == (Y,) and obj["V"].shape == (R2, Y), "форма U/V/b"
    return obj


def ответы(obj):
    return obj["ответы"]


def пишет(obj):
    return obj["пишет"]


def читает(obj):
    return obj["читает"]


def чисел(obj):
    return int(sum(obj[k].size for k in ("E", "A", "a", "U", "V", "b")))


def параметры(obj):
    return {k: obj[k] for k in ("E", "A", "a", "U", "V", "b")}


def _h(obj, токены):
    key, h = obj["_кэш"]
    if key is токены:
        return h
    idx = индексы(obj["соль"], токены, obj["корзины"])
    if len(idx) == 0:
        h = np.zeros(obj["E"].shape[1], dtype=np.float64)
    else:
        s = obj["E"][idx].astype(np.float64).sum(0)
        h = s / (np.sqrt(len(idx)) if obj["свёртка"] == "корень" else len(idx))
    obj["_кэш"] = (токены, h)
    return h


def проход1(obj, токены):
    if not obj["пишет"]:
        return {}
    h = _h(obj, токены)
    L = obj["L"]
    c = L * np.tanh((h @ obj["A"].astype(np.float64) + obj["a"]) / L)
    return {k: float(v) for k, v in zip(obj["пишет"], c)}


def _x(obj, шина):
    R = len(obj["читает"])
    x = np.zeros(2 * R, dtype=np.float64)
    for i, k in enumerate(obj["читает"]):
        if k in шина:
            x[i] = шина[k] / obj["масштаб"]
            x[R + i] = 1.0
    return x


def проход2(obj, токены, шина):
    h = _h(obj, токены)
    s = h @ obj["U"].astype(np.float64) + obj["b"]
    if obj["читает"]:
        s = s + _x(obj, шина) @ obj["V"].astype(np.float64)
    return {a: float(v) for a, v in zip(obj["ответы"], s)}


def разложить(obj, токены, шина, ответ):
    """Счёт ответа = прямой (блок сам читает вопрос) + Σ вес_чтения(понятие) · число_шины(понятие) + присутствие."""
    j = obj["_номер"][ответ]
    h = _h(obj, токены)
    прямой = float(h @ obj["U"][:, j].astype(np.float64) + obj["b"][j])
    R = len(obj["читает"])
    чтение, присутствие = {}, 0.0
    for i, k in enumerate(obj["читает"]):
        if k in шина:
            чтение[k] = float(obj["V"][i, j]) / obj["масштаб"]
            присутствие += float(obj["V"][R + i, j])
    return {"прямой": прямой, "чтение": чтение, "присутствие": присутствие}
