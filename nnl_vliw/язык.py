# -*- coding: utf-8 -*-
"""«Язык» графов для блоков NNL: граф зависимостей инструкций -> токены и понятия.

Матплате NNL от языка нужен один метод `перевести(текст) -> {"токены": [...]}`. Здесь «текст» —
это prompt из наших наборов (`профиль: ...\\nграф:\\n0 DIV\\n1 LOAD <- 0 ...`). Токены — мешок
строк с признаками графа; блок хеширует их в свои корзины (`мешок_шина`).

Токены намеренно простые и целиком считаются из графа и модели машины, без обращения к
планировщикам: язык не должен знать ответ.

  n:<корзина>            число операций
  кп:/рс:/нб:            критический путь, ресурсная граница, их максимум
  зазор:<рс-кп>          насколько ресурсы «длиннее» пути (со знаком)
  привязка:<путь|ресурс|оба>
  ширина:<корзина>       n / критический путь (в десятых)
  оп:<ОП>:<число>        сколько операций каждого типа (число в корзине)
  доля:<ОП>:<десятые>    доля типа в графе
  ребро:<А>><Б>:<число>  сколько зависимостей «А -> Б»
  крит:<ОП>:<число>      операции типа на критическом пути
  истоки/стоки/веер:<..> источники, стоки, максимальная степень выхода

Понятия (то, что блоки пишут на шину; метка 1/0 считается из графа, не из ответа):
  деления:есть / деления:нет    в графе есть DIV или FDIV (делитель — монопольный порт)
  память:много / память:мало    LOAD+STORE не меньше ПОРОГ_ПАМЯТИ от всех операций

Почему именно такие: у наших графов ресурсная граница всегда не меньше пути, так что «путь или
ресурсы» их не делит. А вот деления и память делят: почти все трудные синтетические графы с
делениями, а у настоящего кода трудные случаи есть и без них (см. nnl_vliw/README.md).
"""

from __future__ import annotations

from collections import Counter

from vliw.core.dag import compute_metrics
from vliw.core.model import get_profile
from vliw.tiny.features import build_dag, parse_graph_entries

ИМЯ = "NNL-VLIW"
ВЕРСИЯ = "0.1"
ПОРОГ_ПАМЯТИ = 0.4          # доля LOAD+STORE, с которой памяти «много»


def корзина(x: int) -> int:
    """Грубее при росте: точно до 16, потом шаг 4 до 48, потом шаг 8."""
    x = int(x)
    if x <= 16:
        return x
    if x <= 48:
        return 16 + (x - 16 + 3) // 4 * 4
    return 48 + (x - 48 + 7) // 8 * 8


def понятия_графа(dag) -> dict:
    c = Counter(i.op for i in dag)
    n = max(1, len(dag))
    есть = (c["DIV"] + c["FDIV"]) > 0
    много = (c["LOAD"] + c["STORE"]) / n >= ПОРОГ_ПАМЯТИ
    return {"деления:есть": 1.0 if есть else 0.0, "деления:нет": 0.0 if есть else 1.0,
            "память:много": 1.0 if много else 0.0, "память:мало": 0.0 if много else 1.0}


ВСЕ_ПОНЯТИЯ = ["деления:есть", "деления:нет", "память:много", "память:мало"]


def токены_графа(dag, model) -> tuple[list[str], dict]:
    n = len(dag)
    m = compute_metrics(dag, model)
    cp, rb = m.critical_path_bound, m.resource_bound
    lb = max(cp, rb)
    ops = [i.op for i in dag]
    cnt = Counter(ops)
    succ = dag.succs
    tok = [f"n:{корзина(n)}", f"кп:{корзина(cp)}", f"рс:{корзина(rb)}", f"нб:{корзина(lb)}",
           f"зазор:{max(-8, min(8, rb - cp))}",
           "привязка:" + ("путь" if cp > rb else "ресурс" if rb > cp else "оба"),
           f"ширина:{int(10 * n / max(1, cp))}"]
    for o, c in sorted(cnt.items()):
        tok.append(f"оп:{o}:{min(c, 12) if c <= 12 else корзина(c)}")
        tok.append(f"доля:{o}:{int(10 * c / n)}")
    edges = Counter()
    for i in dag:
        for p in i.preds:
            edges[(ops[p], ops[i.id])] += 1
    for (a, b), c in sorted(edges.items()):
        tok.append(f"ребро:{a}>{b}:{min(c, 8)}")
    crit = [i for i in range(n) if m.asap[i] + m.height[i] >= cp]
    cc = Counter(ops[i] for i in crit)
    tok.append(f"крит_n:{корзина(len(crit))}")
    for o, c in sorted(cc.items()):
        tok.append(f"крит:{o}:{min(c, 8)}")
    sources = sum(1 for i in dag if not i.preds)
    sinks = sum(1 for s in succ if not s)
    fan = max((len(s) for s in succ), default=0)
    tok += [f"истоки:{корзина(sources)}", f"стоки:{корзина(sinks)}", f"веер:{min(fan, 12)}"]
    return tok, {"n": n, "кп": cp, "рс": rb}


class ЯзыкГрафов:
    """Объект «язык» для Матплаты: `матплата.язык.перевести(текст)`."""

    имя = ИМЯ
    версия = ВЕРСИЯ

    def __init__(self, профиль: str = "e2k-v6-measured") -> None:
        self.model = get_profile(профиль)

    def перевести(self, текст: str) -> dict:
        dag = build_dag(parse_graph_entries(текст))
        токены, п = токены_графа(dag, self.model)
        return {"токены": токены, "понятия": понятия_графа(dag), "признаки": п}

    def паспорт_языка(self) -> dict:
        return {"имя": ИМЯ, "версия": ВЕРСИЯ, "понятия": list(ВСЕ_ПОНЯТИЯ), "порог_памяти": ПОРОГ_ПАМЯТИ}
