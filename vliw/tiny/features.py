"""Фичи узла для крошки-1 (priority). Только stdlib.

Фичи берутся из vliw.core: граф + модель машины + метрики (asap/height).
Никакого текста и токенизатора: порядок учим по числам, а не по строкам.
"""

from __future__ import annotations

from ..core.dag import DAG, DagBuilder, compute_metrics
from ..core.model import MachineModel

# Операции синтетического генератора (tools/vliw_gen.py, random_dag):
# именно они встречаются в train_merged/eval_hard. Остальное (FADD, PRED,
# PACK, ...) маппим в корзину "OTHER", чтобы крошка не падала на реальном
# коде, а деградировала к height.
SYNTH_OPS: tuple[str, ...] = ("ADD", "SUB", "MUL", "DIV", "AND", "SHL", "LOAD", "STORE")

FEATURE_NAMES: tuple[str, ...] = (
    *[f"op_{o}" for o in SYNTH_OPS],  # 8 one-hot
    "height_n",    # остаточный критпуть / max
    "asap_n",      # ранний старт / (max+1)
    "lat_n",       # латентность / 11 (DIV — макс. синтетики)
    "occ_extra",   # occupancy-1 (0/1): держит ли порт монопольно
    "nchan_n",     # число допустимых каналов / 6
    "indeg_n",     # число предков / 2
    "outdeg_n",    # число потомков / n
    "is_div",      # монополист ,5 — главная ловушка (slotclash)
    "is_store",    # узкая запись ,2 ,5 — вторая ловушка (memstream)
)

N_FEATURES = len(FEATURE_NAMES)  # 18


def parse_graph_entries(prompt: str) -> list[tuple[int, str, tuple[int, ...]]]:
    """Строки 'ID OP <- preds' из промпта -> (id, op, preds).

    Формат из training/encode.encode_prompt: шапка 'профиль:' + 'граф:',
    дальше по строке на инструкцию, в конце 'расписание:'.
    """
    out: list[tuple[int, str, tuple[int, ...]]] = []
    for line in prompt.splitlines():
        line = line.strip()
        if not line or line.startswith("профиль:") or line in ("граф:", "расписание:"):
            continue
        parts = line.split()
        try:
            idx = int(parts[0])
        except ValueError:
            continue
        op = parts[1] if len(parts) > 1 else "ADD"
        preds: tuple[int, ...] = ()
        if "<-" in parts:
            arrow = parts.index("<-")
            preds = tuple(int(x) for x in parts[arrow + 1:])
        out.append((idx, op, preds))
    out.sort(key=lambda t: t[0])
    return out


def transitive_succs(succs: list[tuple[int, ...]], n: int) -> list[frozenset]:
    """Транзитивные потомки каждого узла (мемоизированный DFS, DAG без циклов).

    Вынесено отдельно от featurize: нужно и правилу монопольного порта
    (`scheduler.rule_holds`), и разборам проигрышей.
    """
    memo: dict[int, frozenset] = {}

    def reach(i: int) -> frozenset:
        if i in memo:
            return memo[i]
        out: set[int] = set()
        stack = list(succs[i])
        while stack:
            j = stack.pop()
            if j in out or j == i:
                continue
            out.add(j)
            stack.extend(succs[j])
        memo[i] = frozenset(out)
        return memo[i]

    return [reach(i) for i in range(n)]


def build_dag(entries: list[tuple[int, str, tuple[int, ...]]], key: str = "tmp") -> DAG:
    """Собрать DAG из распарсенных строк (id обязаны идти подряд)."""
    b = DagBuilder(key, "", "")
    for idx, op, preds in entries:
        assert idx == len(b._instrs), f"id не подряд: {idx}"
        b.op(op, f"n{idx}", *preds)
    return b.build()


def parse_placements(completion: str) -> dict[int, tuple[int, int]]:
    """'i: такт=c канал=ch' -> {id: (cycle, channel)}. Тот же шаблон, что
    training/encode.decode_completion, но без импорта training-пакета."""
    import re
    out: dict[int, tuple[int, int]] = {}
    for m in re.finditer(r"(\d+):\s*такт=(\d+)\s*канал=(\d+)", completion):
        i, c, ch = (int(x) for x in m.groups())
        out[i] = (c, ch)
    return out


def oracle_order(placements: dict[int, tuple[int, int]], n: int) -> list[int]:
    """Порядок оракула: сортировка по (такт, канал). Совпадает с ключом
    vliw/learned/portfolio.order_from_model — учим ровно то, что ест CAB."""
    return sorted(range(n), key=lambda i: (placements[i][0], placements[i][1], i))


def featurize(dag: DAG, model: MachineModel) -> list[list[float]]:
    """DAG + модель -> матрица (n x 18) float. Чистый Python."""
    from ..core.dag import compute_metrics as _cm
    metrics = _cm(dag, model)
    n = len(dag)
    max_h = max(metrics.height) if n else 1
    max_a = max(metrics.asap) if n else 0
    succs = dag.succs
    X: list[list[float]] = []
    for ins in dag:
        i = ins.id
        row = [0.0] * N_FEATURES
        try:
            row[SYNTH_OPS.index(ins.op)] = 1.0
        except ValueError:
            pass  # OTHER: все нули в one-hot — честная деградация
        row[8] = (metrics.height[i] / max_h) if max_h else 0.0
        row[9] = (metrics.asap[i] / (max_a + 1)) if n else 0.0
        row[10] = model.latency(ins.op) / 11.0
        row[11] = float(model.occupancy(ins.op) - 1)
        row[12] = len(model.channels_for(ins.op)) / 6.0
        row[13] = len(ins.preds) / 2.0
        row[14] = (len(succs[i]) / n) if n else 0.0
        row[15] = 1.0 if ins.op == "DIV" else 0.0
        row[16] = 1.0 if ins.op == "STORE" else 0.0
        X.append(row)
    return X
