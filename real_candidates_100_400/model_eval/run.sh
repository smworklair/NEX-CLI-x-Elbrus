#!/bin/bash
# Воспроизведение model_eval БЕЗ модели: сырые ответы raw/*.txt + meta —
# вход (генерация долгая, ~6 мин/граф; команды — в REPORT.md, раздел 1).
# Всё ниже — детерминировано, кроме wall-clock в fair (см. REPORT).
# Время: layers_fixed ~6 мин, fair ~25 мин стена чанками, остальное ~2 мин.
set -e -u
ROOT=/home/shokha/vliw-ai-scheduler-demo
ME=$ROOT/real_candidates_100_400/model_eval

echo "== L0/L1/L2-fixed (25 графов) =="
python3 "$ME/layers_fixed.py"

echo "== L2-fair, бюджет T(g) (13 целей, чанки по 4) =="
python3 "$ME/fair_one.py" --name poly_covariance --seed 510010 \
  --out "$ME/layers/fair.poly_covariance.json" &
python3 "$ME/fair_one.py" --name poly_gemm --seed 510001 \
  --out "$ME/layers/fair.poly_gemm.json" &
python3 "$ME/fair_one.py" --name tsvc_s1111 --seed 510013 \
  --out "$ME/layers/fair.tsvc_s1111.json" &
python3 "$ME/fair_one.py" --name poly_adi --seed 510006 \
  --out "$ME/layers/fair.poly_adi.json" &
wait
python3 "$ME/fair_one.py" --name poly_gesummv --seed 510002 \
  --out "$ME/layers/fair.poly_gesummv.json" &
python3 "$ME/fair_one.py" --name emb_iir --seed 510012 \
  --out "$ME/layers/fair.emb_iir.json" &
python3 "$ME/fair_one.py" --name poly_floyd_int --seed 510008 \
  --out "$ME/layers/fair.poly_floyd_int.json" &
python3 "$ME/fair_one.py" --name poly_heat3d --seed 510009 \
  --out "$ME/layers/fair.poly_heat3d.json" &
wait
python3 "$ME/fair_one.py" --name poly_gramschmidt --seed 510004 \
  --out "$ME/layers/fair.poly_gramschmidt.json" &
python3 "$ME/fair_one.py" --name poly_fdtd --seed 510007 \
  --out "$ME/layers/fair.poly_fdtd.json" &
python3 "$ME/fair_one.py" --name emb_fir --seed 510011 \
  --out "$ME/layers/fair.emb_fir.json" &
python3 "$ME/fair_one.py" --name poly_jacobi2d --seed 510005 \
  --out "$ME/layers/fair.poly_jacobi2d.json" &
python3 "$ME/fair_one.py" --name poly_symm --seed 510003 \
  --out "$ME/layers/fair.poly_symm.json" &
wait

echo "== L3-реплей + слияние =="
python3 "$ME/replay.py"
python3 "$ME/replay_controls.py"
python3 "$ME/merge_results.py" >/dev/null
python3 "$ME/merge_all.py" >/dev/null

echo "== VERIFY =="
bash "$ME/VERIFY.sh"
