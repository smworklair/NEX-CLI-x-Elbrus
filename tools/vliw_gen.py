"""Генератор синтетических примеров планирования для e2k-v6-measured.

Зачем это нужно
---------------
Модель учится не «знаниям об Эльбрусе», а структурной задаче: по графу
зависимостей выдать законное расписание широкой команды. Тексты и статьи про
Эльбрус такой модели не помогают вообще — ей нужны ПАРЫ «граф → расписание».
Этот скрипт их и делает.

Матрица портов, латентности, occupancy и ширина НЕ дублируются: они берутся
импортом из `vliw.core.model` — единственного источника истины по профилю.
Профиль выбирается ключом `--profile` (по умолчанию e2k-v6-measured).
Проверка расписаний идёт настоящим `Schedule.validate()` из `vliw.core`, а не
копией логики.

(Первая версия этого файла лежала вне проекта и дублировала константы из
validate_kaggle.py. Дубли убраны — расхождение профиля теперь невозможно.)

Расписания считаются через CP-SAT и **доказуемо оптимальны** (не эвристика):
meta.makespan — истинный минимум, поэтому «разрыв до оптимума» в валидации
остаётся честной метрикой.

Формат берётся из твоего существующего датасета
-----------------------------------------------
Первые 2 строки промпта validate_kaggle.py пропускает (`splitlines()[2:]`),
то есть это шапка. Что в ней написано — знает только твой генератор, поэтому
скрипт НЕ придумывает её сам, а считывает из образца:

    python vliw_gen.py --format-from train.jsonl --n 20000 --out train_extra.jsonl

Он же определит по образцу, в каком порядке идут строки расписания
(по id или по такту). Без --format-from будет использована шапка по умолчанию
(--header), и это почти наверняка НЕ совпадёт с твоим форматом.

Проверка
--------
    python -m tools.vliw_gen --selftest

Прогоняет сгенерированное через `Schedule.validate()` из vliw.core:
все примеры обязаны быть законны и с разрывом до оптимума 0.
"""

from __future__ import annotations

import argparse
import json
import random
import re
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:      # запуск и как `python tools/vliw_gen.py`
    sys.path.insert(0, str(_ROOT))

from vliw.core.dag import DAG, Instr as DagInstr          # noqa: E402
from vliw.core.model import DEFAULT_PROFILE, get_profile  # noqa: E402
from vliw.core.schedule import Schedule                   # noqa: E402

# ---------------------------------------------------------------------------
# Профиль. Источник истины — vliw.core.model, здесь только ссылка на него.
# Модуль-глобальные CHANNELS/LATENCY/OCCUPANCY/WIDTH — производные кэши для
# горячих циклов CP-SAT; переключаются через set_profile().
# ---------------------------------------------------------------------------

MODEL = get_profile(DEFAULT_PROFILE)
WIDTH: int = MODEL.width
CHANNELS: dict[str, tuple[int, ...]] = {}
LATENCY: dict[str, int] = {}
OCCUPANCY: dict[str, int] = {}


def set_profile(name: str) -> None:
    """Переключить профиль машины и пересобрать производные таблицы."""
    global MODEL, WIDTH, CHANNELS, LATENCY, OCCUPANCY
    MODEL = get_profile(name)
    WIDTH = MODEL.width
    CHANNELS = {op: MODEL.channels_for(op) for op in MODEL.ops}
    LATENCY = {op: MODEL.latency(op) for op in MODEL.ops}
    OCCUPANCY = {op: MODEL.occupancy(op) for op in MODEL.ops}


set_profile(DEFAULT_PROFILE)


def occupancy(op: str) -> int:
    return OCCUPANCY.get(op, 1)


# Как часто встречается операция. Дешёвая арифметика — костяк, DIV — редкость
# (он занимает единственный канал 5 на 2 такта и тянет makespan на 11).
OP_WEIGHTS = {
    "ADD": 26, "SUB": 16, "AND": 12, "SHL": 10,
    "LOAD": 14, "STORE": 8, "MUL": 11, "DIV": 3,
}
_OPS = list(OP_WEIGHTS)
_W = [OP_WEIGHTS[o] for o in _OPS]


# ---------------------------------------------------------------------------
# Разбор формата + проверка настоящим валидатором проекта
# ---------------------------------------------------------------------------

class Instr:
    __slots__ = ("id", "op", "preds")

    def __init__(self, id_: int, op: str, preds: tuple[int, ...]):
        self.id = id_
        self.op = op
        self.preds = preds


_GRAPH_LINE = re.compile(r"^(\d+)\s+(\w+)(?:\s+<-\s+(.*))?$")
_COMPLETION_LINE = re.compile(r"(\d+):\s*такт=(\d+)\s*канал=(\d+)")


def parse_prompt(prompt: str) -> list[Instr]:
    instrs = []
    for line in prompt.strip().splitlines()[2:]:
        if line.strip() == "расписание:":
            break
        m = _GRAPH_LINE.match(line.strip())
        if not m:
            continue
        idx, op, preds_s = m.groups()
        preds = tuple(int(p) for p in preds_s.split()) if preds_s else ()
        instrs.append(Instr(int(idx), op, preds))
    return instrs


def decode_completion(text: str) -> dict[int, tuple[int, int]]:
    return {int(i): (int(c), int(ch)) for i, c, ch in _COMPLETION_LINE.findall(text)}


def to_dag(instrs: list[Instr], key: str = "gen") -> DAG:
    """Локальные Instr → настоящий DAG проекта (для Schedule.validate)."""
    return DAG(key, key, "", [
        DagInstr(ins.id, f"n{ins.id}", ins.op, ins.preds, f"n{ins.id}")
        for ins in instrs
    ])


def build_schedule(instrs: list[Instr],
                   placements: dict[int, tuple[int, int]]) -> Schedule:
    sch = Schedule(to_dag(instrs), MODEL)
    for i, (cycle, ch) in placements.items():
        sch.place(i, cycle, ch)
    return sch


def validate(instrs: list[Instr], placements: dict[int, tuple[int, int]]) -> list[str]:
    """Проверка НАСТОЯЩИМ валидатором проекта (vliw.core.schedule.Schedule).

    Единственное, что добавлено сверху, — отсев id вне диапазона: Schedule
    хранит размещения в словаре и на мусорных id падал бы по KeyError, а нам
    нужен внятный текст ошибки.
    """
    errs: list[str] = []
    n = len(instrs)
    bad_ids = sorted(i for i in placements if not (0 <= i < n))
    if bad_ids:
        errs.append(f"несуществующие id инструкций в ответе модели: {bad_ids}")
        placements = {i: p for i, p in placements.items() if 0 <= i < n}

    return errs + build_schedule(instrs, placements).validate()


def makespan(instrs: list[Instr], placements: dict[int, tuple[int, int]]) -> int:
    return build_schedule(instrs, placements).makespan


# ---------------------------------------------------------------------------
# Генерация графа
# ---------------------------------------------------------------------------

def gen_graph(rng: random.Random, n: int, shape: str) -> list[Instr]:
    """Случайный DAG в топологическом порядке (preds всегда < id).

    shape задаёт «характер» графа, чтобы датасет не был однообразным:
      wide   — много независимых операций, мало связей (проверяет ширину/каналы)
      chain  — длинные цепочки (проверяет латентности и критический путь)
      mixed  — среднее между ними
      layer  — слоями, каждый слой зависит от предыдущего (типично для циклов)
    """
    instrs: list[Instr] = []

    if shape == "layer":
        layers: list[list[int]] = []
        i = 0
        while i < n:
            k = min(n - i, rng.randint(2, 5))
            layers.append(list(range(i, i + k)))
            i += k
        for li, layer in enumerate(layers):
            for idx in layer:
                op = rng.choices(_OPS, weights=_W)[0]
                if li == 0:
                    preds: tuple[int, ...] = ()
                else:
                    prev = layers[li - 1]
                    k = min(len(prev), rng.randint(1, 2))
                    preds = tuple(sorted(rng.sample(prev, k)))
                instrs.append(Instr(idx, op, preds))
        return instrs

    if shape == "wide":
        p_dep, max_deps = 0.30, 1
    elif shape == "chain":
        p_dep, max_deps = 0.95, 2
    else:
        p_dep, max_deps = 0.65, 2

    for idx in range(n):
        op = rng.choices(_OPS, weights=_W)[0]
        preds: tuple[int, ...] = ()
        if idx > 0 and rng.random() < p_dep:
            k = min(idx, rng.randint(1, max_deps))
            if shape == "chain" and rng.random() < 0.7:
                # тянем зависимость от свежих — получаются длинные цепочки
                lo = max(0, idx - 3)
                pool = list(range(lo, idx))
                k = min(k, len(pool))
                preds = tuple(sorted(rng.sample(pool, k)))
            else:
                preds = tuple(sorted(rng.sample(range(idx), k)))
        instrs.append(Instr(idx, op, preds))
    return instrs


# ---------------------------------------------------------------------------
# Оптимальное расписание через CP-SAT
# ---------------------------------------------------------------------------

def schedule_optimal(instrs: list[Instr], time_limit: float = 10.0):
    """Возвращает (placements, makespan) с ДОКАЗАННЫМ оптимумом или None."""
    from ortools.sat.python import cp_model

    n = len(instrs)
    horizon = sum(LATENCY[ins.op] for ins in instrs) + 2

    m = cp_model.CpModel()
    start = [m.NewIntVar(0, horizon, f"s{i}") for i in range(n)]
    end = [m.NewIntVar(0, horizon + 12, f"e{i}") for i in range(n)]
    for i, ins in enumerate(instrs):
        m.Add(end[i] == start[i] + LATENCY[ins.op])

    # зависимости: операнд должен быть готов
    for ins in instrs:
        for p in ins.preds:
            m.Add(start[ins.id] >= end[p])

    # канал: ровно один из разрешённых
    on_ch: dict[tuple[int, int], object] = {}
    for i, ins in enumerate(instrs):
        allowed = CHANNELS[ins.op]
        lits = []
        for c in allowed:
            b = m.NewBoolVar(f"x{i}_{c}")
            on_ch[(i, c)] = b
            lits.append(b)
        m.AddExactlyOne(lits)

    # занятость канала: интервалы не пересекаются
    for c in range(WIDTH):
        ivs = []
        for i, ins in enumerate(instrs):
            if (i, c) not in on_ch:
                continue
            occ = occupancy(ins.op)
            iv = m.NewOptionalIntervalVar(
                start[i], occ, m.NewIntVar(0, horizon + 12, f"o{i}_{c}"),
                on_ch[(i, c)], f"iv{i}_{c}")
            ivs.append(iv)
        if ivs:
            m.AddNoOverlap(ivs)

    # Ширина (<= WIDTH выдач в такте) отдельным ограничением НЕ задаётся:
    # каналов ровно WIDTH=6, NoOverlap разрешает на каждом канале не больше
    # одной операции в такте, а выданные в такте t — подмножество занимающих
    # канал в такте t. Значит выдач в такте не может быть больше 6 по
    # построению. Явная запись через n x horizon булевых переменных замедляла
    # решатель на порядок и ничего не добавляла. Валидатор всё равно проверяет
    # это условие на выходе, а selftest подтверждает, что нарушений нет.

    ms = m.NewIntVar(0, horizon + 12, "makespan")
    m.AddMaxEquality(ms, end)
    m.Minimize(ms)

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = time_limit
    solver.parameters.num_search_workers = 8
    status = solver.Solve(m)
    if status != cp_model.OPTIMAL:
        return None  # берём только доказанный оптимум

    placements: dict[int, tuple[int, int]] = {}
    for i, ins in enumerate(instrs):
        ch = next(c for c in CHANNELS[ins.op] if solver.Value(on_ch[(i, c)]))
        placements[i] = (solver.Value(start[i]), ch)
    return placements, solver.Value(ms)


# ---------------------------------------------------------------------------
# Формат
# ---------------------------------------------------------------------------

DEFAULT_HEADER = ["ширина 6, каналы 0-5", "граф:"]


def sniff_format(path: Path) -> tuple[list[str], str]:
    """Достаёт шапку (2 строки) и порядок строк расписания из образца."""
    line = path.read_text(encoding="utf-8").splitlines()[0]
    row = json.loads(line)
    header = row["prompt"].strip().splitlines()[:2]

    order = "id"
    pairs = _COMPLETION_LINE.findall(row.get("completion", ""))
    if pairs:
        ids = [int(i) for i, _, _ in pairs]
        cycles = [int(c) for _, c, _ in pairs]
        if ids != sorted(ids) and cycles == sorted(cycles):
            order = "cycle"
    return header, order


def render(instrs, placements, header: list[str], order: str) -> tuple[str, str]:
    lines = list(header)
    for ins in instrs:
        if ins.preds:
            lines.append(f"{ins.id} {ins.op} <- {' '.join(str(p) for p in ins.preds)}")
        else:
            lines.append(f"{ins.id} {ins.op}")
    lines.append("расписание:")
    # БЕЗ завершающего перевода строки — так кодирует training/encode.py
    # (`"\n".join(lines)`), и так лежит во всех 20 000 строк dataset.jsonl.
    # Лишний '\n' в конце промпта и ответа — не косметика: он меняет
    # токенизацию стыка и то, на чём стоит EOS.
    prompt = "\n".join(lines)

    items = sorted(placements.items(),
                   key=(lambda kv: (kv[1][0], kv[1][1])) if order == "cycle"
                   else (lambda kv: kv[0]))
    completion = "\n".join(f"{i}: такт={c} канал={ch}" for i, (c, ch) in items)
    return prompt, completion


# ---------------------------------------------------------------------------

SHAPES = ("mixed", "wide", "chain", "layer")


def generate(n_examples: int, lo: int, hi: int, seed: int,
             header: list[str], order: str, out: Path,
             time_limit: float, quiet: bool = False) -> int:
    rng = random.Random(seed)
    written = skipped = 0
    seen_prompts: set[str] = set()

    with out.open("w", encoding="utf-8") as f:
        attempts = 0
        while written < n_examples and attempts < n_examples * 12:
            attempts += 1
            n = rng.randint(lo, hi)
            shape = rng.choice(SHAPES)
            instrs = gen_graph(rng, n, shape)
            res = schedule_optimal(instrs, time_limit)
            if res is None:
                skipped += 1
                continue
            placements, ms = res

            errs = validate(instrs, placements)
            if errs:  # страховка: сами себе не доверяем
                skipped += 1
                continue

            prompt, completion = render(instrs, placements, header, order)
            if prompt in seen_prompts:
                continue
            seen_prompts.add(prompt)

            f.write(json.dumps({
                "prompt": prompt,
                "completion": completion,
                "meta": {"makespan": ms, "n": n, "shape": shape},
            }, ensure_ascii=False) + "\n")
            written += 1
            if not quiet and written % 200 == 0:
                print(f"  ...{written}/{n_examples}", flush=True)

    if not quiet:
        print(f"записано {written} примеров в {out}"
              + (f" (пропущено {skipped}: оптимум не доказан за {time_limit}s)"
                 if skipped else ""))
    return written


def rehead(src: Path, dst: Path, header: list[str], order: str) -> None:
    """Переписывает шапку (и, если надо, порядок строк) в готовом jsonl.

    Нужно, если файл уже сгенерирован с шапкой по умолчанию, а потом выяснилось,
    какая шапка на самом деле. Пересчитывать расписания заново не требуется —
    они от шапки не зависят.
    """
    n = 0
    with dst.open("w", encoding="utf-8") as out:
        for line in src.read_text(encoding="utf-8").splitlines():
            row = json.loads(line)
            instrs = parse_prompt(row["prompt"])
            placements = decode_completion(row["completion"])
            prompt, completion = render(instrs, placements, header, order)
            row["prompt"], row["completion"] = prompt, completion
            out.write(json.dumps(row, ensure_ascii=False) + "\n")
            n += 1
    print(f"переписано {n} примеров: {src} -> {dst}")
    print(f"  шапка:  {header}")
    print(f"  порядок строк расписания: по {order}")


def selftest() -> None:
    print(f"selftest: профиль {MODEL.name}, ширина {WIDTH}")
    print("генерируем 40 примеров и проверяем их Schedule.validate() из vliw.core\n")
    tmp = Path("/tmp/_vliw_selftest.jsonl")
    generate(40, 6, 14, seed=1, header=DEFAULT_HEADER, order="id",
             out=tmp, time_limit=10.0, quiet=True)

    rows = tmp.read_text(encoding="utf-8").splitlines()
    bad = 0
    gaps = []
    per_shape: dict[str, int] = {}
    for line in rows:
        row = json.loads(line)
        instrs = parse_prompt(row["prompt"])
        placements = decode_completion(row["completion"])
        errs = validate(instrs, placements)
        if errs:
            bad += 1
            print("  ОШИБКА:", errs[:2])
            continue
        gaps.append(makespan(instrs, placements) - row["meta"]["makespan"])
        per_shape[row["meta"]["shape"]] = per_shape.get(row["meta"]["shape"], 0) + 1
        if len(instrs) != row["meta"]["n"]:
            print("  ОШИБКА: граф не разобрался целиком")
            bad += 1

    print(f"примеров:            {len(rows)}")
    print(f"невалидных:          {bad}")
    print(f"разрыв до оптимума:  min={min(gaps)} max={max(gaps)}")
    print(f"по типам графов:     {per_shape}")
    print("\nОК" if bad == 0 and max(gaps) == 0 else "\nЕСТЬ ПРОБЛЕМЫ")

    print("\nпример промпта:\n" + "-" * 50)
    row = json.loads(rows[0])
    print(row["prompt"] + row["completion"], end="")
    print("-" * 50)


def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--n", type=int, default=5000, help="сколько примеров")
    ap.add_argument("--min-instr", type=int, default=6)
    ap.add_argument("--max-instr", type=int, default=16)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--out", type=Path, default=Path("train_extra.jsonl"))
    ap.add_argument("--format-from", type=Path, default=None,
                    help="jsonl твоего датасета — с него снимаются шапка и порядок строк")
    ap.add_argument("--header", default=None,
                    help="шапка вручную, 2 строки через '||'")
    ap.add_argument("--time-limit", type=float, default=10.0)
    ap.add_argument("--profile", default=DEFAULT_PROFILE,
                    help="профиль машины из vliw.core.model")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--rehead", type=Path, default=None,
                    help="готовый jsonl: переписать в нём шапку (нужен --format-from)")
    args = ap.parse_args()
    set_profile(args.profile)

    if args.selftest:
        selftest()
        return

    if args.rehead:
        if not args.format_from:
            raise SystemExit("--rehead требует --format-from")
        header, order = sniff_format(args.format_from)
        rehead(args.rehead, args.out, header, order)
        return

    order = "id"
    if args.format_from:
        header, order = sniff_format(args.format_from)
        print(f"формат снят с {args.format_from}:")
        print(f"  шапка:  {header}")
        print(f"  порядок строк расписания: по {order}")
    elif args.header:
        header = args.header.split("||")
    else:
        header = DEFAULT_HEADER
        print("!! ВНИМАНИЕ: шапка по умолчанию, почти наверняка не совпадёт")
        print("!! с твоим датасетом. Лучше запусти с --format-from train.jsonl")

    if len(header) != 2:
        raise SystemExit("шапка должна быть ровно 2 строки (validate_kaggle.py "
                         "пропускает splitlines()[:2])")

    generate(args.n, args.min_instr, args.max_instr, args.seed,
             header, order, args.out, args.time_limit)


if __name__ == "__main__":
    main()
