"""Оценка обученной модели — САМОДОСТАТОЧНАЯ версия для Kaggle.

`training/validate.py` (тот, что в проекте) для парсинга графа и проверки
расписания импортирует `vliw.core` — а на Kaggle этого пакета нет, только
файлы, которые вы туда сами загрузили. Этот файл — тот же режим `--model`,
но вся нужная логика (граф, латентности портов, проверка расписания)
скопирована сюда прямо в текст, без внешних импортов проекта. Нужны только
torch/transformers/peft (см. requirements-kaggle.txt).

Профиль зашит один — `e2k-v6-measured` (тот, на котором генерировался
датасет). Если когда-нибудь будете обучать на другом профиле, матрицу портов
ниже нужно будет обновить вручную — здесь она не читается из проекта.

Запуск на Kaggle:

    !python validate_kaggle.py --model /kaggle/input/.../qwen-vliw-lora \
        /kaggle/input/.../eval.jsonl

Состав ошибок (без полного прогона на 300):

    !python validate_kaggle.py --model /kaggle/input/.../qwen-vliw-lora \
        --limit 50 --dump /kaggle/working/eval_kinds.jsonl \
        /kaggle/input/.../eval.jsonl

Две цифры в конце — это не подгон:
  «как есть» — модель выдала ровно id графа и расписание законно;
  «префикс»  — то же после отрезания id, которых в графе нет (хвост).
Хвост считается отдельно: префикс может быть верным, а стоп — нет.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

# --------------------------------------------------------------------------
# Матрица портов e2k-v6-measured — копия того, что в vliw/core/model.py.
# Проверено ассемблером lcc (см. examples/probes/README.md в проекте).
# --------------------------------------------------------------------------

WIDTH = 6
CHANNELS = {
    "ADD": (0, 1, 2, 3, 4, 5), "SUB": (0, 1, 2, 3, 4, 5),
    "AND": (0, 1, 2, 3, 4, 5), "SHL": (0, 1, 2, 3, 4, 5),
    "MUL": (0, 1, 3, 4),
    "DIV": (5,),
    "LOAD": (0, 2, 3, 5),
    "STORE": (2, 5),
}
LATENCY = {"ADD": 1, "SUB": 1, "AND": 1, "SHL": 1, "MUL": 4, "DIV": 11,
          "LOAD": 5, "STORE": 1}
OCCUPANCY = {"MUL": 1, "DIV": 2}  # остальные по умолчанию 1


def occupancy(op: str) -> int:
    return OCCUPANCY.get(op, 1)


# --------------------------------------------------------------------------
# Граф — минимум, нужный для проверки (без DagBuilder/DagMetrics из проекта)
# --------------------------------------------------------------------------


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


def validate(instrs: list[Instr], placements: dict[int, tuple[int, int]]) -> list[str]:
    """Портированная копия Schedule.validate() из vliw/core/schedule.py.

    Модель может нагаллюцинировать номер инструкции, которого в графе нет
    (например, ответить про инструкцию 15, когда их всего 13) — это такая
    же невалидность, как и любая другая, а не повод уронить весь прогон
    оценки. Раньше `instrs[i]` на таком номере кидал IndexError наружу.
    """
    errs: list[str] = []
    n = len(instrs)
    bad_ids = sorted(i for i in placements if not (0 <= i < n))
    if bad_ids:
        errs.append(f"несуществующие id инструкций в ответе модели: {bad_ids}")
        placements = {i: p for i, p in placements.items() if 0 <= i < n}

    missing = sorted(set(range(n)) - set(placements))
    if missing:
        errs.append(f"не размещены инструкции: {missing}")
        return errs

    ready_at = {i: placements[i][0] + LATENCY[instrs[i].op] for i in placements}

    for ins in instrs:
        for p in ins.preds:
            need, got = ready_at[p], placements[ins.id][0]
            if got < need:
                errs.append(f"{ins.id} выдана в {got}, операнд {p} готов к {need}")

    for i, (cycle, ch) in placements.items():
        if ch not in CHANNELS[instrs[i].op]:
            errs.append(f"{i} ({instrs[i].op}) на канале {ch}, который её не исполняет")

    seen: dict[tuple[int, int], int] = {}
    for i, (cycle, ch) in sorted(placements.items(), key=lambda kv: (kv[1][0], kv[1][1])):
        for k in range(occupancy(instrs[i].op)):
            cell = (cycle + k, ch)
            if cell in seen:
                errs.append(f"конфликт на канале {ch} в такте {cycle + k}: {seen[cell]} и {i}")
            seen[cell] = i

    per_cycle: dict[int, int] = {}
    for cycle, _ in placements.values():
        per_cycle[cycle] = per_cycle.get(cycle, 0) + 1
    for c, k in per_cycle.items():
        if k > WIDTH:
            errs.append(f"такт {c}: {k} операций при ширине {WIDTH}")

    return errs


def makespan(instrs: list[Instr], placements: dict[int, tuple[int, int]]) -> int:
    return max(placements[i][0] + LATENCY[instrs[i].op] for i in placements)


# --------------------------------------------------------------------------
# Тип ошибки. Хвост (id вне графа) — отдельный ярлык, не «мимо».
# --------------------------------------------------------------------------

# Ярлык → (корзина, что это значит)
_KIND = {
    "валидно":       ("валидно", "ровно id графа, расписание законно"),
    "хвост":         ("хвост",   "префикс 0..n-1 законный, модель не остановилась"),
    "сдвиг":         ("почти",   "верные id, операнд ещё не готов"),
    "ресурс":        ("почти",   "верные id, канал / конфликт / ширина"),
    "галлюцинация":  ("мимо",    "дыры в настоящих id"),
    "мусор":         ("мимо",    "ни одной разобранной строки расписания"),
}


def clip_placements(decoded: dict[int, tuple[int, int]], n: int
                    ) -> tuple[dict[int, tuple[int, int]], list[int]]:
    keep = {i: p for i, p in decoded.items() if 0 <= i < n}
    extra = sorted(i for i in decoded if not (0 <= i < n))
    return keep, extra


def classify(errs: list[str], n_keep: int, n_extra: int) -> str:
    """Ярлык по ПРЕФИКСУ (id из графа). Хвост не делает префикс невалидным."""
    if n_keep == 0:
        return "мусор"
    if any(e.startswith("не размещены") for e in errs):
        return "галлюцинация"
    if not errs:
        return "хвост" if n_extra else "валидно"
    if any("выдана в" in e for e in errs):
        return "сдвиг"
    return "ресурс"


def _print_composition(counts: dict[str, int], total: int) -> None:
    as_is = counts.get("валидно", 0)
    prefix_ok = as_is + counts.get("хвост", 0)
    print(f"\nкак есть (без хвоста):     {as_is}/{total} "
          f"({100 * as_is / max(1, total):.0f}%)")
    print(f"префикс 0..n-1 законный:   {prefix_ok}/{total} "
          f"({100 * prefix_ok / max(1, total):.0f}%)")
    print("состав:")
    for kind in ("валидно", "хвост", "сдвиг", "ресурс", "галлюцинация", "мусор"):
        n = counts.get(kind, 0)
        if not n:
            continue
        bucket, meaning = _KIND[kind]
        print(f"  {kind:14} {n:4}  ({100 * n / max(1, total):.0f}% всех)  "
              f"{bucket}: {meaning}")
    broken = total - prefix_ok
    if not broken:
        print("\nпрефиксы все законные. Если хвост > 0 — стоп (EOS / ещё эпохи), "
              "не смена базы")
        return
    miss = counts.get("галлюцинация", 0) + counts.get("мусор", 0)
    almost = counts.get("сдвиг", 0) + counts.get("ресурс", 0)
    print(f"\nсреди сломанных префиксов ({broken}): "
          f"почти {almost} ({100 * almost / max(1, broken):.0f}%), "
          f"мимо {miss} ({100 * miss / max(1, broken):.0f}%)")
    if miss > almost:
        print("по составу — мимо (дыры/мусор): смотреть смену базы")
    else:
        print("по составу — почти (порядок/ресурсы): та же база, ещё эпохи")


# --------------------------------------------------------------------------
# Оценка модели
# --------------------------------------------------------------------------


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("dataset", type=Path)
    ap.add_argument("--model", required=True, help="путь к LoRA-адаптеру")
    ap.add_argument("--max-new-tokens", type=int, default=400)
    ap.add_argument("--limit", type=int, default=None,
                    help="сколько первых примеров взять (для состава ошибок хватит 50)")
    ap.add_argument("--dump", type=Path, default=None,
                    help="jsonl: ярлык и ошибки по каждому примеру")
    args = ap.parse_args()

    import torch
    from peft import PeftModel
    from transformers import AutoModelForCausalLM, AutoTokenizer

    # Явно берём имя БАЗОВОЙ модели из adapter_config.json, а не даём
    # AutoModelForCausalLM.from_pretrained угадывать его самому: если
    # указать путь к папке адаптера напрямую, новые transformers (4.5x+)
    # сами пытаются подгрузить LoRA прямо внутри from_pretrained — и это
    # падает на несовместимой версии torchao, которая нам не нужна вообще
    # (мы применяем адаптер отдельно, строкой ниже, через PeftModel).
    adapter_cfg = json.loads((Path(args.model) / "adapter_config.json").read_text())
    base_name = adapter_cfg["base_model_name_or_path"]

    # peft у этой версии кодирует несовместимую torchao (0.10.0, нужно
    # >=0.16.0) не мягкой проверкой, а прямым ImportError — даже несмотря
    # на то, что мы torchao вообще не используем (обычный LoRA, не
    # torchao-квантование). Отключаем эту проверку точечно, только для
    # модуля, который её реально вызывает (peft.tuners.lora.torchao) —
    # апгрейдить/удалять сам пакет не нужно, он нам не мешает ничем другим.
    import peft.tuners.lora.torchao as _torchao_mod
    _torchao_mod.is_torchao_available = lambda: False

    tok = AutoTokenizer.from_pretrained(args.model, trust_remote_code=True)
    base = AutoModelForCausalLM.from_pretrained(
        base_name, torch_dtype=torch.float16, device_map="auto",
        trust_remote_code=True)
    model = PeftModel.from_pretrained(base, args.model)

    rows = args.dataset.read_text(encoding="utf-8").splitlines()
    if args.limit is not None:
        rows = rows[: max(0, args.limit)]
    print(f"оценка {len(rows)} примеров", flush=True)

    total = 0
    gaps: list[int] = []
    counts: dict[str, int] = {}
    shown: dict[str, int] = {}
    dump = args.dump.open("w", encoding="utf-8") if args.dump else None
    step = 10 if len(rows) <= 60 else 20
    gen_kw = dict(max_new_tokens=args.max_new_tokens, do_sample=False)
    if tok.eos_token_id is not None:
        gen_kw["eos_token_id"] = tok.eos_token_id
    if tok.pad_token_id is not None:
        gen_kw["pad_token_id"] = tok.pad_token_id

    try:
        for line in rows:
            row = json.loads(line)
            instrs = parse_prompt(row["prompt"])
            n_graph = len(instrs)
            inputs = tok(row["prompt"], return_tensors="pt").to(model.device)
            out = model.generate(**inputs, **gen_kw)
            text = tok.decode(out[0][inputs["input_ids"].shape[1]:],
                              skip_special_tokens=True)

            decoded = decode_completion(text)
            keep, extra = clip_placements(decoded, n_graph)
            errs = validate(instrs, keep)
            kind = classify(errs, len(keep), len(extra))
            counts[kind] = counts.get(kind, 0) + 1
            total += 1
            gap = None
            if kind in ("валидно", "хвост"):
                gap = makespan(instrs, keep) - row["meta"]["makespan"]
                gaps.append(gap)
            else:
                shown[kind] = shown.get(kind, 0) + 1
                if shown[kind] <= 2:
                    print(f"[{total}] {kind}: {errs[:2]}", flush=True)
            if extra and kind == "хвост" and counts["хвост"] <= 2:
                print(f"[{total}] хвост: лишние id {extra}", flush=True)

            if dump is not None:
                rec = {"i": total, "kind": kind, "errs": errs, "extra": extra,
                       "n_decoded": len(decoded), "n_graph": n_graph,
                       "gold": row["meta"]["makespan"]}
                if gap is not None:
                    rec["gap"] = gap
                dump.write(json.dumps(rec, ensure_ascii=False) + "\n")

            if total % step == 0:
                print(f"  ...{total}/{len(rows)}  "
                      f"как есть {counts.get('валидно', 0)}  "
                      f"хвост {counts.get('хвост', 0)}  "
                      f"сдвиг {counts.get('сдвиг', 0)}  "
                      f"дыры {counts.get('галлюцинация', 0)}", flush=True)
    finally:
        if dump is not None:
            dump.close()

    _print_composition(counts, total)
    if gaps:
        print(f"среди законных префиксов — средний разрыв до оптимума: "
              f"{sum(gaps) / len(gaps):.2f} такта, "
              f"точно оптимальных: {sum(1 for g in gaps if g == 0)}/{len(gaps)}")


if __name__ == "__main__":
    main()
