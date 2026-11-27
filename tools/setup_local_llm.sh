#!/usr/bin/env bash
# Set up local LLM inference: llama.cpp binary, base GGUF, and adapters.
#
#   tools/setup_local_llm.sh          # install everything
#   tools/setup_local_llm.sh check    # check existing setup only
#
# Automates prebuilt llama.cpp download, base model fetch, and GGUF LoRA conversion
# without requiring root or a C++ compiler.
#
#
#
#
#
#

set -euo pipefail
cd "$(dirname "$0")/.."
ROOT="$PWD"
PY="${PY:-$ROOT/.venv/bin/python}"
VENDOR="$ROOT/vendor"
BUILD="b10944"
# Default agent base model: Phi-4-mini (MIT, non-thinking, ~2.4 GB).
# Overridable via env (note: project LoRA adapters target Qwen only).
#
BASE_REPO="${BASE_REPO:-unsloth/Phi-4-mini-instruct-GGUF}"
BASE_FILE="${BASE_FILE:-Phi-4-mini-instruct-Q4_K_M.gguf}"
# Project LoRA adapters target Qwen2.5-3B only; skip for non-Qwen bases.
#
#
ADAPTER_REPO="Shmonika/nex-vliw-lora"
ADAPTERS="lora-merged qwen-vliw-lora lora-eos"

have () { [ -e "$1" ]; }

check () {
  echo "engine:  $(have "$VENDOR/llama-$BUILD/llama-completion" && echo present || echo MISSING)"
  echo "base:    $(have "$VENDOR/models/$BASE_FILE" && echo "present ($(du -h "$VENDOR/models/$BASE_FILE" | cut -f1))" || echo MISSING)"
  for n in $ADAPTERS; do
    echo "adapter $n: $(have "$VENDOR/models/$n-f16.gguf" && echo present || echo MISSING)"
  done
}

if [ "${1:-all}" = "check" ]; then check; exit 0; fi

mkdir -p "$VENDOR/models"

# 1. Engine: prebuilt CPU binary.
if ! have "$VENDOR/llama-$BUILD/llama-completion"; then
  echo "== downloading llama.cpp ($BUILD) =="
  curl -fsSL -o "$VENDOR/llama.tar.gz" \
    "https://github.com/ggml-org/llama.cpp/releases/download/$BUILD/llama-$BUILD-bin-ubuntu-x64.tar.gz"
  tar xzf "$VENDOR/llama.tar.gz" -C "$VENDOR"
  rm -f "$VENDOR/llama.tar.gz"
fi

# 2. Quantized base model (~2.4 GB).
if ! have "$VENDOR/models/$BASE_FILE"; then
  echo "== downloading base $BASE_FILE =="
  curl -fL --progress-bar -o "$VENDOR/models/$BASE_FILE" \
    "https://huggingface.co/$BASE_REPO/resolve/main/$BASE_FILE"
fi

# 3. Adapters — Qwen base only (scheduling moved to vliw/tiny/).
#
if [[ "$BASE_FILE" == *[Qq]wen* ]]; then
for n in $ADAPTERS; do
  out="$VENDOR/models/$n-f16.gguf"
  have "$out" && { echo "== adapter $n already present =="; continue; }
  echo "== downloading adapter $n (~58 MB) =="
  curl -fL --progress-bar -o "$out" \
    "https://huggingface.co/$ADAPTER_REPO/resolve/main/gguf/$n-f16.gguf" \
    || { echo "download failed: $n"; rm -f "$out"; }
done
else
  echo "== base is not Qwen — skipping adapters (Qwen-only) =="
fi

# 4. Convert custom local adapters in training/checkpoints/ to GGUF.
#
#
#
#
for a in "$ROOT"/training/checkpoints/*/adapter_config.json; do
  [ -e "$a" ] || continue
  dir="$(dirname "$a")"; n="$(basename "$dir")"
  out="$VENDOR/models/$n-f16.gguf"
  have "$out" && continue

  if ! have "$VENDOR/llama.cpp-$BUILD/convert_lora_to_gguf.py"; then
    echo "== downloading converter sources =="
    curl -fsSL -o "$VENDOR/src.tar.gz" \
      "https://github.com/ggml-org/llama.cpp/archive/refs/tags/$BUILD.tar.gz"
    tar xzf "$VENDOR/src.tar.gz" -C "$VENDOR"
    rm -f "$VENDOR/src.tar.gz"
  fi
  "$PY" -m pip install -q gguf transformers peft 2>/dev/null || true

  echo "== converting local adapter $n =="
  # --base-model-id fetches only base config without 6 GB weights.
  #
  base="$("$PY" -c "import json,sys;print(json.load(open(sys.argv[1]))['base_model_name_or_path'])" "$a")"
  "$PY" "$VENDOR/llama.cpp-$BUILD/convert_lora_to_gguf.py" \
    --base-model-id "$base" --outfile "$out" --outtype f16 "$dir"
done

echo; echo "== done =="; check
echo; echo "check:  $PY -m vliw learned --status"
echo "run:    $PY -m vliw learned"
