"""Три приёма и условие законности у каждого.

Дерево ADD. Целое сложение ассоциативно по модулю 2^w. Промежуточный
результат можно убрать, только если его читает ровно один такой же ADD.
FADD/FMUL/FMA/FDIV этим приёмом не трогаются: порядок меняет округление.

Цепочка адресов. `p+8+8+…`, у каждого шага один регистровый предок и
непосредственное в тексте. Шаги зависят от базы, а не друг от друга.
Значения те же.

Сдвиг вместо деления. Только `udivs`/`udivd` на степень двойки от 2.
Знаковое деление и деление от регистра не трогаем: это уже не сдвиг.
В модели нет отдельного SHR, поэтому класс тот же, что у сценария
divstrength, — SHL (латентность модели не меняется).
"""

from __future__ import annotations

import heapq
import re
from dataclasses import dataclass

from vliw.core.baseline import GreedyListScheduler
from vliw.core.dag import DAG, Instr, compute_metrics

_FLOAT = frozenset({"FADD", "FMUL", "FMA", "FDIV"})
_UDIV = re.compile(r"^(udivs|udivd)\b", re.IGNORECASE)
_IMM = re.compile(r"(?<![\w%.])(0x[0-9a-fA-F]+|\d+)\b")
_GREEDY = GreedyListScheduler()


@dataclass(frozen=True)
class Итог:
    dag: DAG
    приём: str | None
    было: int
    стало: int
    причина: str

    @property
    def выигрыш(self) -> int:
        return self.было - self.стало


def _makespan(dag: DAG, model) -> tuple[int, list[str]]:
    res = _GREEDY.schedule(dag, model)
    return res.schedule.makespan, res.schedule.validate()


def _ok(dag: DAG, model, before: int) -> tuple[bool, int]:
    ms, errs = _makespan(dag, model)
    return (not errs and ms < before), ms


def _trees(dag: DAG, op: str) -> list[tuple[int, list[int], list[int]]]:
    n = len(dag)
    succs: list[list[int]] = [[] for _ in range(n)]
    for ins in dag:
        for p in ins.preds:
            succs[p].append(ins.id)
    found = []
    for ins in dag:
        if ins.op != op or len(ins.preds) != 2:
            continue
        users = succs[ins.id]
        if len(users) == 1 and dag[users[0]].op == op and len(dag[users[0]].preds) == 2:
            continue
        inns: list[int] = []
        leaves: list[int] = []

        def walk(node: int, parent: int | None) -> None:
            cur = dag[node]
            own = (
                cur.op == op and len(cur.preds) == 2
                and (node == ins.id or (len(succs[node]) == 1 and succs[node][0] == parent))
            )
            if own:
                inns.append(node)
                for p in cur.preds:
                    walk(p, node)
            else:
                leaves.append(node)

        walk(ins.id, None)
        if len(inns) >= 3 and len(leaves) == len(inns) + 1:
            found.append((ins.id, inns, leaves))
    return found


def _huffman(readies: list[int], lat: int):
    heap = [(t, i) for i, t in enumerate(readies)]
    heapq.heapify(heap)
    seq = len(readies)
    combos: list[tuple[tuple, tuple]] = []
    items: dict[int, tuple] = {i: ("leaf", i) for i in range(len(readies))}
    while len(heap) > 1:
        ta, ia = heapq.heappop(heap)
        tb, ib = heapq.heappop(heap)
        done = max(ta, tb) + lat
        combos.append((items[ia], items[ib]))
        items[seq] = ("add", len(combos) - 1)
        heapq.heappush(heap, (done, seq))
        seq += 1
    return combos, heap[0][0]


def переписать_дерево(dag: DAG, model, op: str) -> DAG | None:
    if op in _FLOAT and op != "FADD":
        return None
    trees = _trees(dag, op)
    if not trees:
        return None
    lat = [model.latency(i.op) for i in dag]
    asap = list(compute_metrics(dag, model).asap)
    step = model.latency(op)
    ready: dict[int, int] = {}
    built: dict[int, tuple[set[int], list[int], list]] = {}
    for root, inns, leaves in sorted(trees, key=lambda t: t[0]):
        readies = [
            ready[leaf] if leaf in ready else asap[leaf] + lat[leaf]
            for leaf in leaves
        ]
        combos, done = _huffman(readies, step)
        built[root] = (set(inns), leaves, combos)
        ready[root] = done

    new: list[Instr] = []
    mp: dict[int, int] = {}

    def emit(opn: str, name: str, preds: tuple[int, ...], text: str) -> int:
        i = len(new)
        new.append(Instr(i, name, opn, preds, text))
        return i

    for ins in dag:
        if ins.id in built:
            _inns, leaves, combos = built[ins.id]
            item: dict[tuple, int] = {("leaf", i): mp[leaf] for i, leaf in enumerate(leaves)}
            for ci, (a, b) in enumerate(combos):
                name = ins.name if ci == len(combos) - 1 else f"{ins.name}t{ci}"
                item[("add", ci)] = emit(op, name, (item[a], item[b]), f"{name} reassoc")
            mp[ins.id] = item[("add", len(combos) - 1)]
            continue
        if any(ins.id in built[r][0] for r in built):
            continue
        mp[ins.id] = emit(ins.op, ins.name, tuple(mp[p] for p in ins.preds), ins.text)
    return DAG(dag.key + f"+{op}", dag.title, dag.note, new, dag.profile)


def _immediates(text: str) -> list[int]:
    """Числа из текста операции, кроме канала мнемоники (первый токен)."""
    parts = text.split(None, 1)
    body = parts[1] if len(parts) > 1 else ""
    out = []
    for raw in _IMM.findall(body):
        out.append(int(raw, 16) if raw.lower().startswith("0x") else int(raw))
    return out


def _const_chains(dag: DAG) -> list[list[int]]:
    n = len(dag)
    succs: list[list[int]] = [[] for _ in range(n)]
    for ins in dag:
        for p in ins.preds:
            succs[p].append(ins.id)
    found = []
    for ins in dag:
        if ins.op != "ADD":
            continue
        if any(dag[p].op == "ADD" for p in ins.preds):
            continue
        cur = ins.id
        seq = [cur]
        seen = {cur}
        while True:
            nxt = [
                s for s in succs[cur]
                if dag[s].op == "ADD" and s not in seen and len(dag[s].preds) == 1
                and _immediates(dag[s].text)
            ]
            if len(nxt) != 1:
                break
            cur = nxt[0]
            seen.add(cur)
            seq.append(cur)
        if len(seq) >= 3:
            found.append(seq)
    return found


def переписать_цепочку(dag: DAG) -> DAG | None:
    chains = _const_chains(dag)
    if not chains:
        return None
    base_of = {}
    for seq in chains:
        for node in seq[1:]:
            base_of[node] = seq[0]
    new: list[Instr] = []
    mp: dict[int, int] = {}
    for ins in dag:
        if ins.id in base_of:
            preds = (mp[base_of[ins.id]],)
        else:
            preds = tuple(mp[p] for p in ins.preds)
        i = len(new)
        new.append(Instr(i, ins.name, ins.op, preds, ins.text))
        mp[ins.id] = i
    return DAG(dag.key + "+addr", dag.title, dag.note, new, dag.profile)


def _pow2(text: str) -> bool:
    head = text.split(None, 1)[0] if text.split() else ""
    if not _UDIV.match(head.split(",")[0]):
        return False
    return any(v >= 2 and (v & (v - 1)) == 0 for v in _immediates(text))


def переписать_сдвиг(dag: DAG) -> DAG | None:
    ids = [ins.id for ins in dag if ins.op == "DIV" and _pow2(ins.text)]
    if not ids:
        return None
    want = set(ids)
    instrs = [
        Instr(ins.id, ins.name, "SHL" if ins.id in want else ins.op, ins.preds, ins.text)
        for ins in dag
    ]
    return DAG(dag.key + "+shl", dag.title, dag.note, instrs, dag.profile)


def _candidates(dag: DAG, model, fp: bool) -> list[tuple[str, DAG]]:
    out: list[tuple[str, DAG]] = []
    tree = переписать_дерево(dag, model, "ADD")
    if tree is not None:
        out.append(("дерево ADD", tree))
    chain = переписать_цепочку(dag)
    if chain is not None:
        out.append(("цепочка адресов", chain))
    shift = переписать_сдвиг(dag)
    if shift is not None:
        out.append(("сдвиг вместо деления", shift))
    if fp:
        fadd = переписать_дерево(dag, model, "FADD")
        if fadd is not None:
            out.append(("дерево FADD (разрешено)", fadd))
    return out


def применить(dag: DAG, model, fp: bool = False) -> Итог:
    """Лучший законный вариант. fp=True — явное разрешение менять округление FADD.

    Не короче жадного или validate() не пуст — исходный граф и «не трогать».
    """
    before, errs = _makespan(dag, model)
    if errs:
        return Итог(dag, None, before, before, "исходное расписание не законно")
    best: tuple[str, DAG, int] | None = None
    for name, cand in _candidates(dag, model, fp):
        ok, ms = _ok(cand, model, before if best is None else best[2])
        if ok and (best is None or ms < best[2]):
            best = (name, cand, ms)
    if best is None:
        return Итог(dag, None, before, before, "не трогать")
    return Итог(best[1], best[0], before, best[2], "короче, проверено")


def правило(dag: DAG, model) -> str | None:
    """Синтаксическое правило, без планировщика.

    Дерево — если локальная готовность корня после Хаффмана раньше исходной.
    Цепочка — если шагов с непосредственным не меньше трёх.
    Сдвиг — если есть беззнаковое деление на степень двойки.
    """
    lat = [model.latency(i.op) for i in dag]
    asap = compute_metrics(dag, model).asap
    step = model.latency("ADD")
    ready: dict[int, int] = {}
    for root, _inns, leaves in sorted(_trees(dag, "ADD"), key=lambda t: t[0]):
        readies = [ready[leaf] if leaf in ready else asap[leaf] + lat[leaf] for leaf in leaves]
        _combos, done = _huffman(readies, step)
        ready[root] = done
        if done < asap[root] + step:
            return "дерево ADD"
    if _const_chains(dag):
        return "цепочка адресов"
    if any(ins.op == "DIV" and _pow2(ins.text) for ins in dag):
        return "сдвиг вместо деления"
    return None


def строка(dag: DAG, model) -> str:
    """Одна строка для панели. Сети нет."""
    it = применить(dag, model, fp=False)
    if it.приём is None:
        return "форма: не трогать"
    return f"форма: {it.приём}, −{it.выигрыш} т. (правило, проверено)"
