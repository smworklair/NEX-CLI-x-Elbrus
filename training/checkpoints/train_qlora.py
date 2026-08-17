"""QLoRA-дообучение Qwen на парах граф→расписание. БЕЗ trl."""

from __future__ import annotations

import argparse
import inspect
import json

import torch
from datasets import Dataset
from peft import LoraConfig, get_peft_model
from transformers import (
    AutoModelForCausalLM,
    AutoTokenizer,
    BitsAndBytesConfig,
    DataCollatorForLanguageModeling,
    Trainer,
    TrainingArguments,
)


def load_rows(path: str) -> list[dict]:
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            row = json.loads(line)
            rows.append({"text": row["prompt"] + "\n" + row["completion"]})
    return rows


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="Qwen/Qwen2.5-3B-Instruct")
    ap.add_argument("--data", required=True)
    ap.add_argument("--out", default="./qwen-vliw-lora")
    ap.add_argument("--epochs", type=int, default=1)
    ap.add_argument("--batch-size", type=int, default=4)
    ap.add_argument("--lr", type=float, default=2e-4)
    ap.add_argument("--max-len", type=int, default=1024)
    args = ap.parse_args()

    bnb = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=torch.float16,
        bnb_4bit_use_double_quant=True,
    )

    tok = AutoTokenizer.from_pretrained(args.base)
    if tok.pad_token is None:
        tok.pad_token = tok.eos_token

    model = AutoModelForCausalLM.from_pretrained(
        args.base, quantization_config=bnb, device_map="auto",
    )

    lora = LoraConfig(
        r=16, lora_alpha=32, lora_dropout=0.05, bias="none",
        task_type="CAUSAL_LM",
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj",
                        "gate_proj", "up_proj", "down_proj"],
    )
    model = get_peft_model(model, lora)
    model.print_trainable_parameters()

    rows = load_rows(args.data)
    print(f"датасет: {len(rows)} примеров")
    ds = Dataset.from_list(rows)

    def tokenize(batch):
        return tok(batch["text"], truncation=True, max_length=args.max_len,
                   padding=False)

    ds = ds.map(tokenize, batched=True, remove_columns=["text"])

    collator = DataCollatorForLanguageModeling(tokenizer=tok, mlm=False)

    targs = TrainingArguments(
        output_dir=args.out,
        num_train_epochs=args.epochs,
        per_device_train_batch_size=args.batch_size,
        gradient_accumulation_steps=4,
        learning_rate=args.lr,
        logging_steps=20,
        save_strategy="steps",
        save_steps=100,
        save_total_limit=2,
        bf16=False, fp16=True,
        report_to="none",
    )

    kwargs = dict(model=model, args=targs, train_dataset=ds, data_collator=collator)
    if "processing_class" in inspect.signature(Trainer.__init__).parameters:
        kwargs["processing_class"] = tok
    else:
        kwargs["tokenizer"] = tok
    trainer = Trainer(**kwargs)
    trainer.train()

    model.save_pretrained(args.out)
    tok.save_pretrained(args.out)
    print(f"адаптер сохранён: {args.out}")


if __name__ == "__main__":
    main()
