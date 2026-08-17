"""Проверка ответов модели: разбор текста → Schedule → validate() → метрики.

Два режима использования:

  1. Самопроверка кодировки (без модели, без GPU) — раунд-трип
     encode → decode → validate на датасете, которого только что сгенерирован
     `generate_dataset.py`. Если тут есть расхождения — сломан не ИИ, а
     формат encode.py, и чинить надо здесь, прежде чем вообще садиться
     дообучать модель.

         python3 training/validate.py --self-check dataset.jsonl

  2. Оценка обученной модели (нужен GPU + transformers/peft, запускать на
     Kaggle рядом с train_qlora.py) — для каждого прогона из отложенной
     выборки модель генерирует расписание, а этот файл его разбирает,
     валидирует и сравнивает makespan с эталонным (оптимальным).

         python3 training/validate.py --model ./qwen-vliw-lora eval.jsonl
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from vliw.core import DAG, Instr, MachineModel, get_profile  # noqa: E402
from training.encode import build_schedule, decode_completion, encode_completion  # noqa: E402

_GRAPH_LINE = re.compile(r"^(\d+)\s+(\w+)(?:\s+<-\s+(.*))?$")


def parse_prompt(prompt: str) -> tuple[DAG, MachineModel]:
    """Обратное к `encode_prompt` — нужно только для самопроверки/восстановления
    графа при оценке модели (при генерации датасета граф и так под рукой)."""
    lines = prompt.strip().splitlines()
    profile_name = lines[0].split(":", 1)[1].strip()
    model = get_profile(profile_name)
    instrs = []
    for line in lines[2:]:
        if line.strip() == "расписание:":
            break
        m = _GRAPH_LINE.match(line.strip())
        if not m:
            continue
        idx, op, preds_s = m.groups()
        preds = tuple(int(p) for p in preds_s.split()) if preds_s else ()
        instrs.append(Instr(int(idx), f"n{idx}", op, preds, f"n{idx} = {op}"))
    dag = DAG("eval", "восстановлено из prompt", "", instrs)
    return dag, model


def self_check(path: Path) -> None:
    """Раунд-трип по уже сгенерированному датасету — без модели."""
    total = ok = 0
    for line in path.read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        dag, model = parse_prompt(row["prompt"])
        decoded = decode_completion(row["completion"])
        sched = build_schedule(dag, model, decoded)
        errs = sched.validate()
        total += 1
        if not errs:
            ok += 1
        elif total <= 5:
            print(f"  [{total}] ошибки валидации: {errs}", file=sys.stderr)
        # Кодировка должна быть однозначно обратимой: то, что закодировали,
        # обязано декодироваться слово в слово.
        if encode_completion(sched) != row["completion"].strip():
            print(f"  [{total}] РАСХОЖДЕНИЕ round-trip (баг в encode.py, "
                 f"не в данных)", file=sys.stderr)
    print(f"self-check: {ok}/{total} валидны, round-trip проверен")


def eval_model(model_path: str, path: Path) -> None:
    """Оценка обученной модели. Требует GPU + transformers/peft — не для CPU."""
    try:
        import torch
        from peft import PeftModel
        from transformers import AutoModelForCausalLM, AutoTokenizer
    except ImportError:
        raise SystemExit(
            "нужны torch/transformers/peft — этот режим только на Kaggle "
            "(см. training/README.md), не здесь"
        )

    tok = AutoTokenizer.from_pretrained(model_path)
    base = AutoModelForCausalLM.from_pretrained(
        tok.name_or_path, torch_dtype=torch.bfloat16, device_map="auto")
    model = PeftModel.from_pretrained(base, model_path)

    total = valid = 0
    gaps = []
    for line in path.read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        dag, machine = parse_prompt(row["prompt"])
        inputs = tok(row["prompt"], return_tensors="pt").to(model.device)
        out = model.generate(**inputs, max_new_tokens=400, do_sample=False)
        text = tok.decode(out[0][inputs["input_ids"].shape[1]:],
                          skip_special_tokens=True)

        decoded = decode_completion(text)
        sched = build_schedule(dag, machine, decoded)
        errs = sched.validate()
        total += 1
        if not errs:
            valid += 1
            gaps.append(sched.makespan - row["meta"]["makespan"])

    print(f"валидных расписаний: {valid}/{total} ({100*valid/max(1,total):.0f}%)")
    if gaps:
        print(f"среди валидных — средний разрыв до оптимума: "
             f"{sum(gaps)/len(gaps):.2f} такта, "
             f"точно оптимальных: {sum(1 for g in gaps if g == 0)}/{len(gaps)}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("dataset", type=Path)
    ap.add_argument("--self-check", action="store_true",
                    help="проверить кодировку без модели (по умолчанию)")
    ap.add_argument("--model", default=None, help="путь к LoRA-адаптеру (режим 2)")
    args = ap.parse_args()

    if args.model:
        eval_model(args.model, args.dataset)
    else:
        self_check(args.dataset)


if __name__ == "__main__":
    main()
