#!/usr/bin/env bash
# Заливка в Kaggle одной командой.
#
#   tools/kaggle_push.sh            # датасет + ядро шага 0 (baseline, без обучения)
#   tools/kaggle_push.sh run1       # датасет + ТОЛЬКО прогон 1 (обучение с EOS)
#   tools/kaggle_push.sh all        # датасет + оба ядра разом
#   tools/kaggle_push.sh pull       # забрать дампы обратно в training/checkpoints
#   tools/kaggle_push.sh status     # статус датасета и ядер на Kaggle, без заливки
#
# Каждый режим заливает ТОЛЬКО своё ядро — раньше `run1` тянул за собой ещё и
# повторный прогон step0 (уместно было, пока step0 ни разу не отработал; после
# первого успешного прогона это лишние ~8 часов GPU впустую на детерминированный
# повтор — do_sample=False, тот же адаптер, тот же результат). Обнаружено
# 17.08.2026: `run1` перезапустил step0 версией 5 без всякой пользы.
#
# Прогон 2 (с нуля на train_merged) отсюда НЕ запускается намеренно: он дорогой
# по квоте, решение о нём принимается отдельно. См. docs/RUNBOOK_EOS.md.
#
# Ключ: поддержаны ОБА формата, потому что Kaggle сменил их в процессе работы
# над этим проектом (17.08.2026 выдавали уже только новый).
#   старый  ~/.kaggle/kaggle.json        {"username": "...", "key": "..."}
#   новый   ~/.kaggle/access_token       KGAT_... (или переменная KAGGLE_API_TOKEN)
# У нового username в файле не лежит — его отдаёт `kaggle config view` уже
# после того, как CLI сходил на сервер и опознал токен.

set -euo pipefail
cd "$(dirname "$0")/.."
ROOT="$PWD"
BUILD="$ROOT/build/kaggle"
PY="${PY:-$ROOT/.venv/bin/python}"
MODE="${1:-step0}"

# --- CLI ---------------------------------------------------------------
# Ставится ДО определения username: у нового формата username узнаёт сам
# kaggle CLI, инструмента без него ещё нет.
if ! "$PY" -c "import kaggle" 2>/dev/null; then
  echo "ставлю kaggle CLI в .venv (единственная новая зависимость)"
  "$PY" -m pip install -q kaggle
fi
KG=("$PY" -m kaggle)

# --- ключ ----------------------------------------------------------------
CONFIG_DIR="${KAGGLE_CONFIG_DIR:-$HOME/.kaggle}"
LEGACY_CREDS="$CONFIG_DIR/kaggle.json"
TOKEN_FILE="$CONFIG_DIR/access_token"

if [[ -f "$LEGACY_CREDS" ]]; then
  chmod 600 "$LEGACY_CREDS" 2>/dev/null || true
  USER_NAME="$("$PY" -c "import json,sys; print(json.load(open(sys.argv[1]))['username'])" "$LEGACY_CREDS")"
elif [[ -f "$TOKEN_FILE" || -n "${KAGGLE_API_TOKEN:-}" ]]; then
  chmod 600 "$TOKEN_FILE" 2>/dev/null || true
  USER_NAME="$("${KG[@]}" config view 2>/dev/null | sed -n 's/^- username: //p')"
  if [[ -z "$USER_NAME" ]]; then
    echo "токен есть, но 'kaggle config view' не назвал username — токен" \
         "недействителен или сервис недоступен" >&2
    exit 1
  fi
else
  cat >&2 <<'EOF'
Нет ни ~/.kaggle/kaggle.json (старый формат), ни ~/.kaggle/access_token (новый).

  1. kaggle.com -> Settings -> API -> Create New Token
  2. страница покажет команду вида:
       mkdir -p ~/.kaggle && echo KGAT_... > ~/.kaggle/access_token \
         && chmod 600 ~/.kaggle/access_token
     выполнить её (или export KAGGLE_API_TOKEN=KGAT_...)
  3. запустить эту команду снова

Всё остальное уже готово: build/kaggle собран, скрипты ядер написаны.
EOF
  exit 1
fi
echo "пользователь Kaggle: $USER_NAME"

# --- сборка ----------------------------------------------------------------
"$PY" tools/kaggle_prep.py

# Подставляем настоящий username в id/dataset_sources ТОЧЕЧНО через JSON, а
# не глобальным sed по всему файлу. Раньше здесь стоял
# `sed -i "s|USERNAME/|$USER_NAME/|g"` — небезопасен в обе стороны: (а) не
# экранировал $USER_NAME в шаблоне замены (метасимволы sed вроде `&`/`|`
# сломали бы подстановку, если бы когда-нибудь оказались в имени), (б) бил по
# ЛЮБОМУ вхождению строки "USERNAME/" во всём файле, а не только по полям
# id/dataset_sources — будущий title/description с тем же текстом испортился
# бы молча. Оба класса регрессии сюда больше не попадут: правим только
# конкретные JSON-поля, значение подставляем как данные, а не как текст sed.
"$PY" - "$USER_NAME" "$BUILD/dataset/dataset-metadata.json" "$BUILD"/*/kernel-metadata.json <<'PYEOF'
import json, sys
user, *paths = sys.argv[1:]
for p in paths:
    d = json.load(open(p, encoding="utf-8"))
    if d.get("id", "").startswith("USERNAME/"):
        d["id"] = user + d["id"][len("USERNAME"):]
    for s in ("dataset_sources", "competition_sources", "kernel_sources"):
        if s in d:
            d[s] = [user + v[len("USERNAME"):] if v.startswith("USERNAME/") else v
                    for v in d[s]]
    json.dump(d, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
PYEOF

# Слаг датасета и список ядер — из того, что реально лежит в build/kaggle/,
# а не отдельные литералы, которые легко забыть поправить при переименовании
# или добавлении нового ядра (так уже вышло однажды: kaggle_push.sh молча
# продолжал пушить только два старых ядра). id датасета теперь уже "user/slug"
# — подставлен строкой выше.
DATASET_ID="$("$PY" -c "import json,sys; print(json.load(open(sys.argv[1]))['id'])" \
             "$BUILD/dataset/dataset-metadata.json")"
mapfile -t KERNEL_SLUGS < <(find "$BUILD" -mindepth 1 -maxdepth 1 -type d \
                            -not -name dataset -exec basename {} \; | sort)

case "$MODE" in
  pull)
    mkdir -p training/checkpoints
    for k in "${KERNEL_SLUGS[@]}"; do
      echo "забираю вывод $k"
      "${KG[@]}" kernels output "$USER_NAME/$k" -p training/checkpoints || \
        echo "  (ещё нет вывода — ядро не отработало)"
    done
    echo
    echo "дальше: $PY tools/report_runs.py"
    exit 0
    ;;
  status)
    # Только чтение: ничего не заливает и не запускает, квоту не трогает.
    echo "датасет: $DATASET_ID"
    # `kaggle ... status` не завершает вывод переводом строки — добавляем
    # свой, иначе следующая строка приклеивается прямо к «ready».
    "${KG[@]}" datasets status "$DATASET_ID" 2>&1 | sed 's/^/  /' || true
    echo
    for k in "${KERNEL_SLUGS[@]}"; do
      echo "ядро: $USER_NAME/$k"
      "${KG[@]}" kernels status "$USER_NAME/$k" 2>&1 | sed 's/^/  /' || true
    done
    exit 0
    ;;
  step0|run1|all) ;;
  *) echo "неизвестный режим: $MODE (step0 | run1 | all | pull | status)" >&2; exit 2 ;;
esac

# --- датасет ---------------------------------------------------------------
# create падает, если датасет уже есть; version — если ещё нет. Пробуем
# version, при неудаче создаём. Так скрипт можно гонять повторно.
echo "заливаю датасет ($(du -sh "$BUILD/dataset" | cut -f1))"
if ! "${KG[@]}" datasets version -p "$BUILD/dataset" -m "обновление $(date +%F_%H%M)" -q -r zip 2>/dev/null; then
  "${KG[@]}" datasets create -p "$BUILD/dataset" -q -r zip
fi

echo "жду, пока Kaggle распакует датасет (обычно 1-3 минуты)"
# Раньше эта проверка не гейтила ничего после себя: таймаут молча проваливался
# в запуск ядра против датасета, который мог быть ещё не готов, а любая
# НАСТОЯЩАЯ ошибка API (протухший токен, rate limit, сеть) неотличимо
# сливалась с обычным "ещё не готово" через `2>/dev/null || echo pending` —
# оба случая жгли полные 10 минут впустую и всё равно запускали GPU-ядро.
# Теперь: настоящая ошибка — стоп сразу; таймаут без "ready" — тоже стоп,
# ядро не запускается вообще.
ready=0
for _ in $(seq 1 30); do
  if ! st="$("${KG[@]}" datasets status "$DATASET_ID" 2>&1)"; then
    echo "!! ошибка проверки статуса датасета (не 'ещё не готов', настоящий сбой API):" >&2
    echo "$st" >&2
    exit 1
  fi
  echo "  статус: $st"
  if [[ "$st" == "ready" ]]; then
    ready=1
    break
  fi
  sleep 20
done
if [[ "$ready" != 1 ]]; then
  echo "!! датасет не стал 'ready' за 10 минут — ядро НЕ запускаю, квоту не жгу." >&2
  echo "   проверить вручную: $PY -m kaggle datasets status $DATASET_ID" >&2
  exit 1
fi

# --- ядро ------------------------------------------------------------------
push_kernel () {
  local slug="$1"
  echo "запускаю ядро $slug"
  "${KG[@]}" kernels push -p "$BUILD/$slug"
  echo "  следить: https://www.kaggle.com/code/$USER_NAME/$slug"
}

pick_kernel () {   # находит слаг, содержащий имя режима (step0 / run1)
  local mode="$1" match
  match="$(printf '%s\n' "${KERNEL_SLUGS[@]}" | grep -m1 "$mode")" || {
    echo "!! не нашёл ядро для режима '$mode' среди: ${KERNEL_SLUGS[*]}" >&2
    exit 1
  }
  echo "$match"
}

case "$MODE" in
  step0) push_kernel "$(pick_kernel step0)" ;;
  run1)  push_kernel "$(pick_kernel run1)" ;;
  all)   for k in "${KERNEL_SLUGS[@]}"; do push_kernel "$k"; done ;;
esac

cat <<EOF

Готово. Ядра считаются на стороне Kaggle, ждать здесь нечего.
Проверить статус:   $PY -m kaggle kernels status $USER_NAME/vliw-<slug>
Забрать результаты: tools/kaggle_push.sh pull
Свести в таблицу:   $PY tools/report_runs.py
EOF
