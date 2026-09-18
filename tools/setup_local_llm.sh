#!/usr/bin/env bash
# Поднять локальный запуск обученной модели: движок, база, адаптеры.
#
#   tools/setup_local_llm.sh          # всё сразу
#   tools/setup_local_llm.sh check    # только проверить, что уже есть
#
# Зачем скрипт, а не инструкция в README: шагов четыре, три из них качают
# файлы, и один (конвертация адаптера) требует точного ключа --base-model-id,
# который легко забыть — без него скрипт llama.cpp ищет базу как локальную
# папку и падает с FileNotFoundError на строке 'Qwen/Qwen2.5-3B-Instruct'.
#
# Ничего не требует root: компилятора на машине может не быть, поэтому берётся
# ГОТОВЫЙ бинарник ggml-org, а не сборка llama-cpp-python из исходников
# (готовых колёс у него нет вообще ни под какой Python).

set -euo pipefail
cd "$(dirname "$0")/.."
ROOT="$PWD"
PY="${PY:-$ROOT/.venv/bin/python}"
VENDOR="$ROOT/vendor"
BUILD="b10944"
# Актуальная база агента: Phi-4-mini (MIT, без thinking, ~2.4 ГБ).
# Переопределяется окружением, если понадобится другая
# (но LoRA-адаптеры проекта — только под Qwen).
BASE_REPO="${BASE_REPO:-unsloth/Phi-4-mini-instruct-GGUF}"
BASE_FILE="${BASE_FILE:-Phi-4-mini-instruct-Q4_K_M.gguf}"
# Адаптеры, обученные в этом проекте — ТОЛЬКО под Qwen2.5-3B (лежат в
# vendor/models/_qwen_retired/). На чужой базе сервер с ними не стартует,
# поэтому качаем только когда база — qwen.
ADAPTER_REPO="Shmonika/nex-vliw-lora"
ADAPTERS="lora-merged qwen-vliw-lora lora-eos"

have () { [ -e "$1" ]; }

check () {
  echo "движок:  $(have "$VENDOR/llama-$BUILD/llama-completion" && echo есть || echo НЕТ)"
  echo "база:    $(have "$VENDOR/models/$BASE_FILE" && echo "есть ($(du -h "$VENDOR/models/$BASE_FILE" | cut -f1))" || echo НЕТ)"
  for n in $ADAPTERS; do
    echo "адаптер $n: $(have "$VENDOR/models/$n-f16.gguf" && echo есть || echo НЕТ)"
  done
}

if [ "${1:-all}" = "check" ]; then check; exit 0; fi

mkdir -p "$VENDOR/models"

# 1. Движок. Готовый CPU-бинарник, распаковывается как есть.
if ! have "$VENDOR/llama-$BUILD/llama-completion"; then
  echo "== качаю движок llama.cpp ($BUILD) =="
  curl -fsSL -o "$VENDOR/llama.tar.gz" \
    "https://github.com/ggml-org/llama.cpp/releases/download/$BUILD/llama-$BUILD-bin-ubuntu-x64.tar.gz"
  tar xzf "$VENDOR/llama.tar.gz" -C "$VENDOR"
  rm -f "$VENDOR/llama.tar.gz"
fi

# 2. Квантованная база. Единственная тяжёлая загрузка (~2.4 ГБ).
if ! have "$VENDOR/models/$BASE_FILE"; then
  echo "== качаю базу $BASE_FILE (~4.6 ГБ) =="
  curl -fL --progress-bar -o "$VENDOR/models/$BASE_FILE" \
    "https://huggingface.co/$BASE_REPO/resolve/main/$BASE_FILE"
fi

# 3. Адаптеры — только под Qwen-базу (см. шапку). На Gemma/Phi сервер с ними
#    не стартует, а планировщик на LoRA заменён крошками (vliw/tiny/).
if [[ "$BASE_FILE" == *[Qq]wen* ]]; then
for n in $ADAPTERS; do
  out="$VENDOR/models/$n-f16.gguf"
  have "$out" && { echo "== адаптер $n уже на месте =="; continue; }
  echo "== качаю адаптер $n (~58 МБ) =="
  curl -fL --progress-bar -o "$out" \
    "https://huggingface.co/$ADAPTER_REPO/resolve/main/gguf/$n-f16.gguf" \
    || { echo "не скачался: $n"; rm -f "$out"; }
done
else
  echo "== база не Qwen — адаптеры пропускаю (они только под Qwen) =="
fi

# 4. Конвертация СВОИХ адаптеров — путь автора, не скачавшего. Нужен только
#    если в training/checkpoints/ лежит адаптер, которого нет в готовых GGUF:
#    то есть вы обучили новый. Тогда доезжают исходники llama.cpp ради
#    convert_lora_to_gguf.py (он тянет пакет conversion/, по отдельным файлам
#    его не собрать) и адаптер конвертируется на месте.
for a in "$ROOT"/training/checkpoints/*/adapter_config.json; do
  [ -e "$a" ] || continue
  dir="$(dirname "$a")"; n="$(basename "$dir")"
  out="$VENDOR/models/$n-f16.gguf"
  have "$out" && continue

  if ! have "$VENDOR/llama.cpp-$BUILD/convert_lora_to_gguf.py"; then
    echo "== качаю исходники для конвертера =="
    curl -fsSL -o "$VENDOR/src.tar.gz" \
      "https://github.com/ggml-org/llama.cpp/archive/refs/tags/$BUILD.tar.gz"
    tar xzf "$VENDOR/src.tar.gz" -C "$VENDOR"
    rm -f "$VENDOR/src.tar.gz"
  fi
  "$PY" -m pip install -q gguf transformers peft 2>/dev/null || true

  echo "== конвертирую свой адаптер $n =="
  # --base-model-id, а не --base: качается только config базы, сами 6 ГБ
  # весов для этого не нужны.
  base="$("$PY" -c "import json,sys;print(json.load(open(sys.argv[1]))['base_model_name_or_path'])" "$a")"
  "$PY" "$VENDOR/llama.cpp-$BUILD/convert_lora_to_gguf.py" \
    --base-model-id "$base" --outfile "$out" --outtype f16 "$dir"
done

echo; echo "== готово =="; check
echo; echo "проверить:  $PY -m vliw learned --status"
echo "запустить:  $PY -m vliw learned"
