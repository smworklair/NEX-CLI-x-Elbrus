#!/usr/bin/env bash
# Push dataset and kernels to Kaggle in one command.
#
#   tools/kaggle_push.sh            # dataset + step0 kernel (baseline, no training)
#   tools/kaggle_push.sh run1       # dataset + ONLY run 1 (training with EOS)
#   tools/kaggle_push.sh run2       # dataset + ONLY run 2 (from scratch, train_merged)
#   tools/kaggle_push.sh resume     # ONLY resume run 2 from vliw-run2-merged
#                                   #   checkpoint -> --resume + eval
#   tools/kaggle_push.sh diag       # diagnostics: 20 examples, raw completion text
#   tools/kaggle_push.sh all        # dataset + step0 and run1 (excludes run2/resume/diag)
#   tools/kaggle_push.sh pull       # pull dumps back into training/checkpoints
#   tools/kaggle_push.sh status     # check Kaggle dataset/kernel status (read-only)
#
# Each mode pushes ONLY its own kernel (avoids re-running step0 unnecessarily).
#
#
#
#
#
# Run 2 (from scratch on train_merged) requires explicit `run2` due to GPU quota cost.
#
#
#
#
# Credentials: supports both legacy kaggle.json and new access_token / KAGGLE_API_TOKEN.
#
#   legacy  ~/.kaggle/kaggle.json        {"username": "...", "key": "..."}
#   new     ~/.kaggle/access_token       KGAT_... (or env KAGGLE_API_TOKEN)
# With access_token, username is resolved via `kaggle config view`.
#

set -euo pipefail
cd "$(dirname "$0")/.."
ROOT="$PWD"
BUILD="$ROOT/build/kaggle"
PY="${PY:-$ROOT/.venv/bin/python}"
MODE="${1:-step0}"

# --- CLI ---------------------------------------------------------------
# Install kaggle CLI before resolving username.
#
if ! "$PY" -c "import kaggle" 2>/dev/null; then
  echo "installing kaggle CLI into .venv"
  "$PY" -m pip install -q kaggle
fi
KG=("$PY" -m kaggle)

# --- credentials ---------------------------------------------------------
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
    echo "token present, but 'kaggle config view' returned no username — token" \
         "invalid or service unavailable" >&2
    exit 1
  fi
else
  cat >&2 <<'EOF'
Neither ~/.kaggle/kaggle.json (legacy) nor ~/.kaggle/access_token (new) was found.

  1. kaggle.com -> Settings -> API -> Create New Token
  2. the page will display a command like:
       mkdir -p ~/.kaggle && echo KGAT_... > ~/.kaggle/access_token \
         && chmod 600 ~/.kaggle/access_token
     run it (or export KAGGLE_API_TOKEN=KGAT_...)
  3. re-run this script

Everything else is ready: build/kaggle and kernel scripts are prepared.
EOF
  exit 1
fi
echo "Kaggle user: $USER_NAME"

# --- build ---------------------------------------------------------------
"$PY" tools/kaggle_prep.py

# Patch username in JSON id/dataset_sources fields safely via Python.
#
#
#
#
#
#
#
#
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

# Read dataset slug and kernel list dynamically from build/kaggle/.
#
#
#
#
DATASET_ID="$("$PY" -c "import json,sys; print(json.load(open(sys.argv[1]))['id'])" \
             "$BUILD/dataset/dataset-metadata.json")"
mapfile -t KERNEL_SLUGS < <(find "$BUILD" -mindepth 1 -maxdepth 1 -type d \
                            -not -name dataset -exec basename {} \; | sort)

case "$MODE" in
  pull)
    mkdir -p training/checkpoints
    for k in "${KERNEL_SLUGS[@]}"; do
      echo "pulling output for $k"
      "${KG[@]}" kernels output "$USER_NAME/$k" -p training/checkpoints || \
        echo "  (no output yet — kernel not finished)"
    done
    echo
    echo "next: $PY tools/report_runs.py"
    exit 0
    ;;
  status)
    # Read-only status check (does not upload or consume quota).
    echo "dataset: $DATASET_ID"
    # `kaggle ... status` omits trailing newline — add one.
    #
    "${KG[@]}" datasets status "$DATASET_ID" 2>&1 | sed 's/^/  /' || true
    echo
    for k in "${KERNEL_SLUGS[@]}"; do
      echo "kernel: $USER_NAME/$k"
      "${KG[@]}" kernels status "$USER_NAME/$k" 2>&1 | sed 's/^/  /' || true
    done
    exit 0
    ;;
  step0|run1|run2|resume|diag|diag3|all) ;;
  *) echo "unknown mode: $MODE (step0 | run1 | run2 | resume | diag | diag3 | all | pull | status)" >&2; exit 2 ;;
esac

# --- dataset -------------------------------------------------------------
# Try `version` first; fall back to `create` for new datasets.
#
echo "uploading dataset ($(du -sh "$BUILD/dataset" | cut -f1))"
T0=$(date -u +%s)
if ! "${KG[@]}" datasets version -p "$BUILD/dataset" -m "update $(date +%F_%H%M)" -q -r zip 2>/dev/null; then
  "${KG[@]}" datasets create -p "$BUILD/dataset" -q -r zip
fi

echo "waiting for Kaggle to unpack dataset (usually 1-3 min)"
# Fail fast on real API errors or timeout without starting GPU kernels.
#
#
#
#
#
#
ready=0
for _ in $(seq 1 30); do
  if ! st="$("${KG[@]}" datasets status "$DATASET_ID" 2>&1)"; then
    echo "!! dataset status check failed (real API error):" >&2
    echo "$st" >&2
    exit 1
  fi
  echo "  status: $st"
  if [[ "$st" == "ready" ]]; then
    ready=1
    break
  fi
  sleep 20
done
if [[ "$ready" != 1 ]]; then
  echo "!! dataset did not become 'ready' within 10 min — aborting kernel push." >&2
  echo "   check manually: $PY -m kaggle datasets status $DATASET_ID" >&2
  exit 1
fi

# Also verify freshness so kernels do not run against stale dataset versions.
#
#
#
#
fresh=0
ts=""
for _ in $(seq 1 30); do
  ts="$("${KG[@]}" datasets files "$DATASET_ID" 2>/dev/null \
        | awk '$1=="train_qlora.py" {print $3" "$4}' | cut -d. -f1)"
  if [[ -n "$ts" ]] && (( $(date -ud "$ts" +%s) >= T0 )); then
    fresh=1
    break
  fi
  sleep 20
done
if [[ "$fresh" != 1 ]]; then
  echo "!! dataset did not refresh within 10 min (files still older than upload:" \
       "$ts) — aborting kernel push." >&2
  exit 1
fi
echo "dataset fresh: train_qlora.py updated ${ts} UTC"

# --- kernel --------------------------------------------------------------
push_kernel () {
  local slug="$1"
  echo "pushing kernel $slug"
  "${KG[@]}" kernels push -p "$BUILD/$slug"
  echo "  monitor: https://www.kaggle.com/code/$USER_NAME/$slug"
}

pick_kernel () {   # find slug matching mode name (step0 / run1)
  local mode="$1" match
  match="$(printf '%s\n' "${KERNEL_SLUGS[@]}" | grep -m1 "$mode")" || {
    echo "!! no kernel found for mode '$mode' among: ${KERNEL_SLUGS[*]}" >&2
    exit 1
  }
  echo "$match"
}

case "$MODE" in
  step0) push_kernel "$(pick_kernel step0)" ;;
  run1)  push_kernel "$(pick_kernel run1)" ;;
  run2)  push_kernel "$(pick_kernel run2)" ;;
  # resume — continues from last vliw-run2-merged checkpoint
  #
  resume) push_kernel "$(pick_kernel resume)" ;;
  # diag — 20-example raw-completion diagnostic run
  #
  diag)  push_kernel "$(pick_kernel diag2)" ;;
  # diag3 — 2x2 matrix on eval_wide (2 adapters x 2 decoding modes)
  #
  diag3) push_kernel "$(pick_kernel diag3)" ;;
  # `all` pushes cheap kernels only; run2/resume require explicit invocation.
  #
  all)   for k in "${KERNEL_SLUGS[@]}"; do
           [[ "$k" == *run2* || "$k" == *diag* ]] || push_kernel "$k"
         done ;;
esac

cat <<EOF

Done. Kernels are running on Kaggle.
Check status:       $PY -m kaggle kernels status $USER_NAME/vliw-<slug>
Pull results:       tools/kaggle_push.sh pull
Aggregate report:   $PY tools/report_runs.py
EOF
