"""QLoRA-дообучение Qwen на парах граф→расписание. ТОЛЬКО для Kaggle/Colab с GPU.

ВТОРАЯ ВЕРСИЯ, БЕЗ trl. Первая использовала `trl.SFTTrainer`, но её пришлось
откатывать на старую версию (0.9.6), чтобы обойти баг новых `trl`
(`_patch_chunked_ce_lm_head` падает на модели, обёрнутой в LoRA+4bit). Откат
`trl` потянул за собой откат `transformers` и `numpy` — а те уже несовместимы
с версией, под которую в образе Kaggle собраны `torch`/`bitsandbytes`
(`ValueError: numpy.dtype size changed, may indicate binary incompatibility`).
Один откат породил цепочку из трёх новых поломок.

Эта версия использует обычный `transformers.Trainer` + ручную токенизацию —
`trl` не участвует вообще, поэтому НЕ НУЖНО ничего откатывать: работает на
тех версиях transformers/peft/bitsandbytes, что уже стоят в свежем образе
Kaggle по умолчанию (или после `pip install -q -U transformers peft
bitsandbytes accelerate datasets` — БЕЗ `trl` в списке и БЕЗ фиксации версий).

Не запускать локально/на Deepnote — здесь тяжёлые ML-зависимости, которых у
демо-инструмента намеренно нет (см. training/__init__.py).

`--base` — drop-in, формат данных один и тот же (сырой prompt+completion).
Проверенные кандидаты под T4 16 ГБ / 4-bit:

    Qwen/Qwen2.5-3B-Instruct          текущая, продолжать с --adapter
    Qwen/Qwen2.5-Coder-3B-Instruct    тот же размер, код
    Qwen/Qwen3-4B-Instruct-2507       соседний класс, без thinking
    Qwen/Qwen2.5-Coder-7B-Instruct    если влезет: --batch-size 2

Пример запуска в ячейке Kaggle-ноутбука:

    !python train_qlora.py \
        --base Qwen/Qwen2.5-3B-Instruct \
        --data /kaggle/input/vliw-dataset/dataset.jsonl \
        --out /kaggle/working/qwen-vliw-lora \
        --epochs 2

Продолжить уже обученный адаптер (вторая+ эпоха на той же базе):

    !python train_qlora.py \
        --base Qwen/Qwen2.5-3B-Instruct \
        --adapter /kaggle/input/.../qwen-vliw-lora \
        --data /kaggle/input/vliw-dataset/dataset.jsonl \
        --out /kaggle/working/qwen-vliw-lora \
        --epochs 2
"""

from __future__ import annotations

import argparse
import inspect
import json

import torch
from datasets import Dataset
from peft import LoraConfig, PeftModel, get_peft_model
from transformers import (
    AutoModelForCausalLM,
    AutoTokenizer,
    BitsAndBytesConfig,
    Trainer,
    TrainingArguments,
)


def load_rows(path: str, eos: str | None) -> list[dict]:
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            row = json.loads(line)
            # Вопрос+ответ склеены в одну последовательность. Раньше конца
            # последовательности не было — модель не видела EOS и на коротких
            # графах дописывала строки до «привычных» 12–14. Токен конца
            # учит её останавливаться после последней инструкции.
            text = row["prompt"] + "\n" + row["completion"]
            if eos and not text.endswith(eos):
                text = text + eos
            rows.append({"text": text})
    return rows


class CausalCollator:
    """Паддинг + labels. Под маску идёт ТОЛЬКО добивка, а не токен по совпадению id.

    Штатный `DataCollatorForLanguageModeling(mlm=False)` ставит -100 всюду, где
    встретился `pad_token_id`. Пока pad и eos — разные токены, всё хорошо: у
    Qwen2.5 pad = `<|endoftext|>` (151643), eos = `<|im_end|>` (151645), и
    настоящий EOS в конце примера остаётся в loss.

    Но выше стоит `if tok.pad_token is None: tok.pad_token = tok.eos_token`. У
    базы, где pad не задан (а `--base` меняется одним ключом), pad станет равен
    eos — и тот же самый collator замаскирует КОНЕЦ КАЖДОГО ПРИМЕРА. Модель
    никогда не получит градиента на «здесь надо остановиться», EOS в тексте при
    этом визуально на месте. Это ровно та поломка, из-за которой в eval живёт
    категория «хвост»: законный префикс, но модель не останавливается.

    Здесь маска берётся из `attention_mask` — какой токен выбран паддингом,
    больше не имеет значения.
    """

    def __init__(self, tok):
        self.tok = tok

    def __call__(self, features):
        batch = self.tok.pad(features, return_tensors="pt")
        labels = batch["input_ids"].clone()
        labels[batch["attention_mask"] == 0] = -100
        batch["labels"] = labels
        return batch


def check_eos(tok, rows: list[dict], collator) -> None:
    """Проверка, что EOS дошёл до loss, а не потерялся по дороге.

    Три места, где он может пропасть молча: не приклеился к тексту; приклеился
    строкой, но токенизатор разбил его на куски вместо одного спец-токена;
    доехал до батча, но получил -100 в labels. Печатаем факт, а не намерение.
    """
    ids = tok(rows[0]["text"], truncation=True, max_length=4096)["input_ids"]
    last = ids[-1]
    print(f"  последний токен примера: {last} {tok.decode([last])!r} "
          f"(eos_token_id={tok.eos_token_id}, pad_token_id={tok.pad_token_id})")
    if last != tok.eos_token_id:
        print("  !! ВНИМАНИЕ: пример не заканчивается EOS — модель не научится "
              "останавливаться (категория «хвост» в eval)")
        return

    batch = collator([tok(r["text"], truncation=True, max_length=4096)
                      for r in rows[:2]])
    pos = (batch["input_ids"][0] == tok.eos_token_id).nonzero()
    masked = all(batch["labels"][0][p] == -100 for p in pos)
    if masked:
        print("  !! ВНИМАНИЕ: EOS замаскирован в labels (-100) и в loss не "
              "попадает — модель не научится останавливаться")
    else:
        print("  EOS попадает в loss (labels != -100) — ОК")


def _silence_torchao() -> None:
    # peft 0.2x на Kaggle импортирует несовместимую torchao жёстким ImportError,
    # хотя обычный LoRA её не использует. Та же точечная заглушка, что в
    # validate_kaggle.py.
    try:
        import peft.tuners.lora.torchao as _torchao_mod
        _torchao_mod.is_torchao_available = lambda: False
    except Exception:
        pass


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base", default="Qwen/Qwen2.5-3B-Instruct",
                    help="открытый чекпойнт с HuggingFace; для T4/P100 не берите >7B")
    ap.add_argument("--adapter", default=None,
                    help="продолжить с уже обученного LoRA (та же --base)")
    ap.add_argument("--data", required=True, help="dataset.jsonl от generate_dataset.py")
    ap.add_argument("--out", default="./qwen-vliw-lora")
    ap.add_argument("--epochs", type=int, default=2)
    ap.add_argument("--batch-size", type=int, default=4)
    ap.add_argument("--lr", type=float, default=2e-4)
    ap.add_argument("--max-len", type=int, default=1024,
                    help="графы 4-24 инстр., самая длинная пара ~415 токенов — "
                         "запас двукратный")
    ap.add_argument("--no-eos", action="store_true",
                    help="не дописывать EOS (старое поведение, модель не учится стопать)")
    args = ap.parse_args()

    # 4-бита: P100/T4 не умеют bf16 нативно, поэтому compute_dtype=fp16.
    bnb = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=torch.float16,
        bnb_4bit_use_double_quant=True,
    )

    _silence_torchao()

    tok = AutoTokenizer.from_pretrained(args.base, trust_remote_code=True)
    if tok.pad_token is None:
        tok.pad_token = tok.eos_token
    tok.padding_side = "right"

    model = AutoModelForCausalLM.from_pretrained(
        args.base, quantization_config=bnb, device_map="auto",
        trust_remote_code=True,
    )

    if args.adapter:
        print(f"продолжаем адаптер: {args.adapter}")
        model = PeftModel.from_pretrained(model, args.adapter, is_trainable=True)
    else:
        # Стандартные проекции внимания/MLP для Qwen2/Qwen3 — этого
        # достаточно для задачи такого масштаба, embedding/lm_head не трогаем.
        lora = LoraConfig(
            r=16, lora_alpha=32, lora_dropout=0.05, bias="none",
            task_type="CAUSAL_LM",
            target_modules=["q_proj", "k_proj", "v_proj", "o_proj",
                            "gate_proj", "up_proj", "down_proj"],
        )
        model = get_peft_model(model, lora)
    model.print_trainable_parameters()   # для контроля: должно быть <1-2% весов

    eos = None if args.no_eos else (tok.eos_token or "")
    if eos:
        print(f"EOS в конце каждого примера: {eos!r}")
    rows = load_rows(args.data, eos)
    print(f"датасет: {len(rows)} примеров")
    ds = Dataset.from_list(rows)

    def tokenize(batch):
        return tok(batch["text"], truncation=True, max_length=args.max_len,
                   padding=False)

    ds = ds.map(tokenize, batched=True, remove_columns=["text"])

    # Обычное авторегрессивное предсказание следующего токена. Свой collator,
    # а не DataCollatorForLanguageModeling(mlm=False) — см. CausalCollator:
    # штатный маскирует labels по совпадению с pad_token_id и вместе с добивкой
    # съедает настоящий EOS, если pad и eos совпали.
    collator = CausalCollator(tok)
    if eos:
        check_eos(tok, rows, collator)

    targs = TrainingArguments(
        output_dir=args.out,
        num_train_epochs=args.epochs,
        per_device_train_batch_size=args.batch_size,
        gradient_accumulation_steps=4,
        learning_rate=args.lr,
        logging_steps=20,
        # save_strategy="epoch" уже стоило часа обучения на живом Kaggle:
        # сессия оборвалась на 93% первой эпохи, чекпоинт не успел
        # сохраниться. Сохраняемся каждые 100 шагов, а не раз в эпоху.
        save_strategy="steps",
        save_steps=100,
        save_total_limit=2,
        bf16=False, fp16=True,           # см. bnb_4bit_compute_dtype выше
        report_to="none",
    )

    # Разные версии transformers по-разному называют параметр под токенизатор
    # (tokenizer= в старых, processing_class= в новых, ~4.49+) — определяем
    # по факту, а не гадаем/фиксируем версию, чтобы скрипт работал что на
    # свежем Kaggle-образе, что на чуть более старом.
    kwargs = dict(model=model, args=targs, train_dataset=ds, data_collator=collator)
    if "processing_class" in inspect.signature(Trainer.__init__).parameters:
        kwargs["processing_class"] = tok
    else:
        kwargs["tokenizer"] = tok
    trainer = Trainer(**kwargs)
    trainer.train()

    model.save_pretrained(args.out)      # только адаптер, не базовые веса
    tok.save_pretrained(args.out)
    meta = {
        "base": args.base,
        "adapter_from": args.adapter,
        "epochs": args.epochs,
        "eos": eos,
        "n_train": len(rows),
    }
    from pathlib import Path as _Path
    meta_path = _Path(args.out) / "train_meta.json"
    meta_path.parent.mkdir(parents=True, exist_ok=True)
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"адаптер сохранён: {args.out}")


if __name__ == "__main__":
    main()
