#!/bin/bash
# Перепроверка model_eval без запуска модели: всё пересчитывается из
# asm/*.s и сохранённых raw/*.txt средствами проекта, заявленное читается
# из manifest.json / results.json / decode.json. Печать — до 40 строк.
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
python3 "$ROOT/real_candidates_100_400/model_eval/verify_impl.py"
