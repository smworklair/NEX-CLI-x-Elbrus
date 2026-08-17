#!/usr/bin/env bash
# Заливка в Kaggle одной командой. Требует только ~/.kaggle/kaggle.json.
#
#   tools/kaggle_push.sh            # датасет + ядро шага 0 (baseline, без обучения)
#   tools/kaggle_push.sh run1       # то же + запуск прогона 1 (обучение с EOS)
#   tools/kaggle_push.sh pull       # забрать дампы обратно в training/checkpoints
#
# Прогон 2 (с нуля на train_merged) отсюда НЕ запускается намеренно: он дорогой
# по квоте, решение о нём принимается отдельно. См. docs/RUNBOOK_EOS.md.

set -euo pipefail
cd "$(dirname "$0")/.."
ROOT="$PWD"
BUILD="$ROOT/build/kaggle"
PY="${PY:-$ROOT/.venv/bin/python}"
MODE="${1:-step0}"

# --- ключ ------------------------------------------------------------------
CREDS="${KAGGLE_CONFIG_DIR:-$HOME/.kaggle}/kaggle.json"
if [[ ! -f "$CREDS" ]]; then
  cat >&2 <<'EOF'
Нет ~/.kaggle/kaggle.json.

  1. kaggle.com -> Settings -> API -> Create New Token
  2. скачается kaggle.json, положить его сюда:
       mkdir -p ~/.kaggle && mv ~/Downloads/kaggle.json ~/.kaggle/
       chmod 600 ~/.kaggle/kaggle.json
  3. запустить эту команду снова

Всё остальное уже готово: build/kaggle собран, скрипты ядер написаны.
EOF
  exit 1
fi
chmod 600 "$CREDS" 2>/dev/null || true

USER_NAME="$("$PY" -c "import json,sys; print(json.load(open(sys.argv[1]))['username'])" "$CREDS")"
echo "пользователь Kaggle: $USER_NAME"

# --- CLI -------------------------------------------------------------------
if ! "$PY" -c "import kaggle" 2>/dev/null; then
  echo "ставлю kaggle CLI в .venv (единственная новая зависимость)"
  "$PY" -m pip install -q kaggle
fi
KG=("$PY" -m kaggle)

# --- сборка ----------------------------------------------------------------
"$PY" tools/kaggle_prep.py

# Подставляем настоящий username вместо заглушки — метаданные пересобираются
# каждый запуск, поэтому правка идемпотентна.
for f in "$BUILD/dataset/dataset-metadata.json" "$BUILD"/*/kernel-metadata.json; do
  [[ -f "$f" ]] && sed -i "s|USERNAME/|$USER_NAME/|g" "$f"
done

case "$MODE" in
  pull)
    mkdir -p training/checkpoints
    for k in vliw-step0-baseline vliw-run1-eos; do
      echo "забираю вывод $k"
      "${KG[@]}" kernels output "$USER_NAME/$k" -p training/checkpoints || \
        echo "  (ещё нет вывода — ядро не отработало)"
    done
    echo
    echo "дальше: $PY tools/report_runs.py"
    exit 0
    ;;
  step0|run1) ;;
  *) echo "неизвестный режим: $MODE (step0 | run1 | pull)" >&2; exit 2 ;;
esac

# --- датасет ---------------------------------------------------------------
# create падает, если датасет уже есть; version — если ещё нет. Пробуем
# version, при неудаче создаём. Так скрипт можно гонять повторно.
echo "заливаю датасет ($(du -sh "$BUILD/dataset" | cut -f1))"
if ! "${KG[@]}" datasets version -p "$BUILD/dataset" -m "обновление $(date +%F_%H%M)" -q -r zip 2>/dev/null; then
  "${KG[@]}" datasets create -p "$BUILD/dataset" -q -r zip
fi

echo "жду, пока Kaggle распакует датасет (обычно 1-3 минуты)"
for _ in $(seq 1 30); do
  st="$("${KG[@]}" datasets status "$USER_NAME/vliw-eos-run" 2>/dev/null || echo pending)"
  echo "  статус: $st"
  [[ "$st" == "ready" ]] && break
  sleep 20
done

# --- ядро ------------------------------------------------------------------
push_kernel () {
  local slug="$1"
  echo "запускаю ядро $slug"
  "${KG[@]}" kernels push -p "$BUILD/$slug"
  echo "  следить: https://www.kaggle.com/code/$USER_NAME/$slug"
}

push_kernel vliw-step0-baseline
[[ "$MODE" == "run1" ]] && push_kernel vliw-run1-eos

cat <<EOF

Готово. Ядра считаются на стороне Kaggle, ждать здесь нечего.
Проверить статус:   $PY -m kaggle kernels status $USER_NAME/vliw-step0-baseline
Забрать результаты: tools/kaggle_push.sh pull
Свести в таблицу:   $PY tools/report_runs.py
EOF
