# -*- coding: utf-8 -*-
"""Обучение NNL-блока «Помощь_ассистент» (установка NEX CLI).

Блок — обычный NNL-блок архитектуры `мешок_шина`: вопрос переводится в мешок
токенов (`vliw/help_nnl.py`), вектор — среднее строк E по корзинам crc32,
счёты тем — `h·U + b`. Обучение — softmax-регрессия по тем же формулам, что
исполняет блок, поэтому расхождения «обучение ≠ инференс» нет. Отдельный
класс «не_тема» учит блок честно отказываться от посторонних вопросов.

Пишет две копии одних чисел:
  nnl_vliw/блоки_помощь/Помощь_ассистент/{паспорт.json, веса.npz}
  vliw/help_weights.json   (чистый Python: экран установки работает без numpy)

Запуск:
  python tools/train_help_block.py
"""

from __future__ import annotations

import hashlib
import json
import sys
import time
from pathlib import Path

import numpy as np

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

КОРЕНЬ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(КОРЕНЬ))

from vliw.help_nnl import НЕ_ТЕМА, _индекс, токены  # noqa: E402

ДАННЫЕ = КОРЕНЬ / "nnl_vliw" / "блоки_помощь" / "обучение.jsonl"
БЛОК = КОРЕНЬ / "nnl_vliw" / "блоки_помощь" / "Помощь_ассистент"
ЛЁГКИЕ = КОРЕНЬ / "vliw" / "help_weights.json"

КОРЗИНЫ = 4096
РАЗМЕР = 32
СОЛЬ = "П-А1"
ЭПОХ = 300
СКОРОСТЬ = 0.05
ЗЕРНО = 1
ДОЛЯ_DEV = 0.2


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def загрузить() -> tuple[list[list[str]], list[int], list[str]]:
    строки = [json.loads(s) for s in ДАННЫЕ.read_text(encoding="utf-8").splitlines()
              if s.strip()]
    темы: list[str] = []
    for r in строки:
        if r["тема"] not in темы:
            темы.append(r["тема"])
    # «не_тема» держим последней: индексы остальных тем не зависят от неё.
    темы = [t for t in темы if t != НЕ_ТЕМА] + [НЕ_ТЕМА]
    ток = [токены(r["вопрос"]) for r in строки]
    метки = [темы.index(r["тема"]) for r in строки]
    return ток, метки, темы


def разбить(метки: list[int], темы: list[str]) -> tuple[list[int], list[int]]:
    """Стратифицированно: пятая часть каждой темы — dev."""
    rng = np.random.RandomState(ЗЕРНО)
    по_темам: dict[int, list[int]] = {}
    for i, y in enumerate(метки):
        по_темам.setdefault(y, []).append(i)
    train: list[int] = []
    dev: list[int] = []
    for y in range(len(темы)):
        idx = list(по_темам.get(y, []))
        rng.shuffle(idx)
        k = max(1, int(round(len(idx) * ДОЛЯ_DEV))) if len(idx) >= 5 else 0
        dev += idx[:k]
        train += idx[k:]
    return sorted(train), sorted(dev)


def упаковать(ток: list[list[str]]) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Токены → прямоугольная матрица индексов корзин + маска + длины."""
    длины = np.array([len(t) for t in ток], dtype=np.int64)
    ширина = int(длины.max())
    idx = np.zeros((len(ток), ширина), dtype=np.int64)
    маска = np.zeros((len(ток), ширина), dtype=np.float64)
    for i, слова in enumerate(ток):
        idx[i, :len(слова)] = [_индекс(СОЛЬ, t, КОРЗИНЫ) for t in слова]
        маска[i, :len(слова)] = 1.0
    return idx, маска, длины


def вектор(E: np.ndarray, idx: np.ndarray, маска: np.ndarray,
           длины: np.ndarray) -> np.ndarray:
    """h = среднее строк E по токенам вопроса (та же формула, что в блоке)."""
    return (E[idx] * маска[:, :, None]).sum(1) / длины[:, None]


def softmax(s: np.ndarray) -> np.ndarray:
    z = s - s.max(1, keepdims=True)
    e = np.exp(z)
    return e / e.sum(1, keepdims=True)


def точность(E, U, b, idx, маска, длины, метки, rows) -> float:
    h = вектор(E, idx[rows], маска[rows], длины[rows])
    s = h @ U + b
    return float((np.argmax(s, 1) == np.asarray(метки)[rows]).mean()) if rows else 0.0


def обучить(ток, метки, темы):
    rng = np.random.RandomState(ЗЕРНО)
    Y = len(темы)
    train, dev = разбить(метки, темы)
    idx, маска, длины = упаковать(ток)
    y = np.asarray(метки, dtype=np.int64)

    E = rng.normal(0.0, 0.6, (КОРЗИНЫ, РАЗМЕР))
    U = np.zeros((РАЗМЕР, Y))
    b = np.zeros(Y)
    mE, vE = np.zeros_like(E), np.zeros_like(E)
    mU, vU = np.zeros_like(U), np.zeros_like(U)
    mb, vb = np.zeros_like(b), np.zeros_like(b)
    лучший = (-1.0, E.copy(), U.copy(), b.copy())
    t = 0
    t0 = time.time()
    tr = np.asarray(train, dtype=np.int64)

    for эпоха in range(1, ЭПОХ + 1):
        H = вектор(E, idx[tr], маска[tr], длины[tr])
        S = H @ U + b
        P = softmax(S)
        P[np.arange(len(tr)), y[tr]] -= 1.0
        P /= len(tr)
        потеря = float(-np.log(np.maximum(
            1e-12, softmax(S)[np.arange(len(tr)), y[tr]])).mean())

        gU = H.T @ P
        gb = P.sum(0)
        gH = P @ U.T
        w = gH / длины[tr][:, None]
        W = np.broadcast_to(w[:, None, :], (len(tr), idx.shape[1], РАЗМЕР)).reshape(-1, РАЗМЕР)
        плоские = idx[tr].reshape(-1)
        годные = маска[tr].reshape(-1) > 0
        gE = np.zeros_like(E)
        np.add.at(gE, плоские[годные], W[годные])

        t += 1
        mE = 0.9 * mE + 0.1 * gE
        vE = 0.999 * vE + 0.001 * (gE * gE)
        E -= СКОРОСТЬ * (mE / (1 - 0.9 ** t)) / (np.sqrt(vE / (1 - 0.999 ** t)) + 1e-8)
        mU = 0.9 * mU + 0.1 * gU
        vU = 0.999 * vU + 0.001 * (gU * gU)
        U -= СКОРОСТЬ * (mU / (1 - 0.9 ** t)) / (np.sqrt(vU / (1 - 0.999 ** t)) + 1e-8)
        mb = 0.9 * mb + 0.1 * gb
        vb = 0.999 * vb + 0.001 * (gb * gb)
        b -= СКОРОСТЬ * (mb / (1 - 0.9 ** t)) / (np.sqrt(vb / (1 - 0.999 ** t)) + 1e-8)

        if эпоха % 10 == 0 or эпоха == ЭПОХ:
            д = точность(E, U, b, idx, маска, длины, метки, dev)
            if д > лучший[0]:
                лучший = (д, E.copy(), U.copy(), b.copy())
            if эпоха % 50 == 0 or эпоха == ЭПОХ:
                print(f"  эпоха {эпоха:3d}  потеря {потеря:.3f}  dev {д:.3f}")

    print(f"  обучение {time.time() - t0:.1f} с, строк {len(train)} + {len(dev)} dev")
    return лучший[1], лучший[2], лучший[3], train, dev, лучший[0]


def сохранить(E, U, b, темы, train, dev, dev_точность, точность_вне):
    БЛОК.mkdir(parents=True, exist_ok=True)
    npz = БЛОК / "веса.npz"
    np.savez_compressed(
        npz,
        E=E.astype(np.float32),
        A=np.zeros((РАЗМЕР, 0), np.float32),
        a=np.zeros(0, np.float32),
        U=U.astype(np.float32),
        V=np.zeros((0, len(темы)), np.float32),
        b=b.astype(np.float32),
        пишет=np.array([], dtype=str),
        читает=np.array([], dtype=str),
        ответы=np.array(темы, dtype=str),
    )
    чисел = int(E.size + U.size + b.size)
    паспорт = {
        "имя": "Помощь_ассистент",
        "версия": 1,
        "роль": "объясняет, зачем нужен NEX CLI, и помогает его установить",
        "архитектура": "мешок_шина",
        "настройки": {
            "корзины": КОРЗИНЫ,
            "размер": РАЗМЕР,
            "граница": 8.0,
            "соль": СОЛЬ,
            "свёртка": "среднее",
        },
        "веса": {
            "файл": "веса.npz",
            "sha256": _sha256(npz),
            "чисел": чисел,
        },
        "пишет": [],
        "читает": [],
        "ответы": темы,
        "проекции": {},
        "облегчённая_копия": "vliw/help_weights.json",
        "обучение": {
            "скрипт": "tools/train_help_block.py",
            "данные": "nnl_vliw/блоки_помощь/обучение.jsonl",
            "строк": len(train) + len(dev),
            "обучение": len(train),
            "dev": len(dev),
            "dev_точность": round(dev_точность, 4),
            "вне_темы_отказ": round(точность_вне, 4),
            "эпох": ЭПОХ,
            "зерно": ЗЕРНО,
            "когда": time.strftime("%Y-%m-%dT%H:%M:%S"),
        },
    }
    (БЛОК / "паспорт.json").write_text(
        json.dumps(паспорт, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")

    лёгкие = {
        "соль": СОЛЬ,
        "корзины": КОРЗИНЫ,
        "размер": РАЗМЕР,
        "свёртка": "среднее",
        "ответы": темы,
        "E": np.round(E, 5).tolist(),
        "U": np.round(U, 5).tolist(),
        "b": np.round(b, 5).tolist(),
        "источник": "nnl_vliw/блоки_помощь/Помощь_ассистент/веса.npz",
        "sha256": паспорт["веса"]["sha256"],
    }
    ЛЁГКИЕ.write_text(json.dumps(лёгкие, ensure_ascii=False, separators=(",", ":")),
                      encoding="utf-8")
    return паспорт


ПРОВЕРКА = (
    "как установить программу",
    "что такое textual",
    "не запускается интерфейс",
    "зачем нужен nex cli",
    "как создать venv",
    "какие требования к системе",
    "как прогнать тесты",
    "как на linux",
    "что такое slotclash",
    "как настроить агента",
    "как обновить программу",
    "как удалить nex cli",
    "как проверить установку",
    "сколько будет два плюс два",
    "расскажи про погоду",
    "как приготовить борщ",
    "кто такой пушкин",
    "посоветуй фильм",
)


def main() -> int:
    ток, метки, темы = загрузить()
    print(f"NNL-блок помощи: {len(ток)} вопросов, {len(темы) - 1} тем + отказ")
    E, U, b, train, dev, лучший = обучить(ток, метки, темы)
    паспорт = сохранить(E, U, b, темы, train, dev, лучший, 0.0)
    print()
    print(f"  чисел в блоке: {паспорт['веса']['чисел']}")
    print(f"  dev-точность:  {лучший:.3f}")
    print(f"  паспорт:       {БЛОК / 'паспорт.json'}")
    print(f"  лёгкие веса:   {ЛЁГКИЕ}")

    # Проверяем уже готовый блок тем же путём, что и экран установки.
    from vliw.help_nnl import вероятности, спросить
    ok = 0
    print("\n  проверка вопросов:")
    for q in ПРОВЕРКА:
        p = вероятности(q)
        top = max(p, key=p.get) if p else "-"
        ответ = спросить(q)
        if q in ПРОВЕРКА[:13]:
            ok += int(ответ is not None)
            метка = ответ[0] if ответ else "ОТКАЗ"
        else:
            ok += int(ответ is None)
            метка = "отказ" if ответ is None else f"ОШИБКА:{ответ[0]}"
        print(f"    {q:42s} -> {top:12s} {p.get(top, 0):.2f}  {метка}")
    print(f"  верно: {ok}/{len(ПРОВЕРКА)}")
    return 0 if ok == len(ПРОВЕРКА) else 1


if __name__ == "__main__":
    raise SystemExit(main())
