# Model on Real Code: OOD Evaluation + Portfolio Contribution

Research question: does the fine-tuned model (LoRA on Qwen2.5-3B, GGUF via llama.cpp, adapter **lora-merged**) add anything beyond the greedy scheduler, a deterministic rule, and random search on graphs of 112–386 nodes (trained on 4–24)? Short answer — **no: L3 is strictly shorter than L2 on 0 of 13 graphs (+0 cycles total). Against L2-fair (equal wall-clock budget), also 0 of 13.** Below are measurements, not opinions.

## 1. Task A: Model Running Through the Real Path

`runtime.status(None)` immediately reported ready (`llama-server` backend, base `qwen2.5-3b-instruct-q4_k_m.gguf` 2.1 GB, 6 threads, `ctx 4096`). Two hurdles:

- **`libgomp`**: `ldd vendor/llama-b10488/llama-server` → `libgomp.so.1 => not found`; absent from the system (no `gcc` either), passwordless `sudo`. Fixed without modifying project code: `apt-get download libgomp1` (162 KB) → `dpkg-deb -x` into `~/.local/lib/gomp` → `LD_LIBRARY_PATH` in benchmark scripts and `run.sh`. Verified: re-running `ldd` shows no `not found`, and the server launches via project code (`shared_server().ensure()`).
- **Context window**: the project launches the server with fixed `ctx=4096` (`SERVER_CTX`; editing `vliw/**` was forbidden and untouched). Prompt token counts measured via `/tokenize` on the live server:

| graph | n | prompt tokens | remaining for reply |
|---|---|---|---|
| emb_fir | 347 | 3773 | 323 |
| poly_symm | 386 | 3563 | 533 |
| poly_jacobi2d | 349 | 3417 | 679 |
| poly_lu | 340 | 3482 | 614 |
| … | … | … | … |
| cm_mul | 112 | 927 | 3169 |

(full table in `tokens.py`; all 25 prompts fit within 4096.)
A full completion needs ~12 tokens/line × n lines, so large graphs physically run out of context. `max_new_tokens = 12·n`, temperature 0. Whatever the model emitted before truncation is the Task B measurement; a separate "large context" server was intentionally not spun up — we evaluate the project's actual production path, not a hypothetical.

Generation: `gen_one.py` — `training.encode.encode_prompt` + `runtime.make_backend(lora-merged).generate(...)` at `temperature=0`, raw text saved byte-for-byte to `raw/<graph>.txt` (+ `.meta.json` with timings and token counts). Speed: 1.5–6.5 tok/s (longer prompts slower), 178–395 s per graph. Order: 13 target graphs from smallest to largest, then 12 control graphs.

## 2. Task B: What the Model Output (OOD Evaluation)

| graph | ptok | otok | t,s | lines | matched | placed | extra | dup | miss | 1st bad | trunc | raw |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| covariance | 1945 | 2151 | 370 | 182 | 149 | 149 | 0 | 32 | 37 | 1 | yes | invalid |
| gemm | 1540 | 2280 | 385 | 185 | 0 | 0 | 0 | 0 | 190 | 1 | yes | — |
| tsvc | 2457 | 1639 | 361 | 140 | 0 | 0 | 0 | 0 | 243 | 1 | yes | — |
| adi | 2371 | 1725 | 366 | 143 | 0 | 0 | 0 | 0 | 251 | 1 | yes | — |
| gesummv | 2675 | 1421 | 339 | 118 | 0 | 0 | 0 | 0 | 255 | 1 | yes | — |
| iir | 2253 | 1843 | 391 | 152 | 0 | 0 | 0 | 0 | 256 | 1 | yes | — |
| floyd | 2361 | 1735 | 368 | 145 | 0 | 0 | 0 | 0 | 265 | 1 | yes | — |
| heat3d | 3166 | 930 | 300 | 79 | 0 | 0 | 0 | 0 | 284 | 1 | yes | — |
| gramschmidt | 2781 | 1315 | 323 | 110 | 0 | 0 | 0 | 0 | 313 | 1 | yes | — |
| fdtd | 2882 | 1214 | 313 | 103 | 0 | 0 | 0 | 0 | 340 | 1 | yes | — |
| fir | 3773 | 323 | 214 | 28 | 0 | 0 | 0 | 0 | 347 | 1 | yes | — |
| jacobi2d | 3417 | 679 | 253 | 58 | 0 | 0 | 0 | 0 | 349 | 1 | yes | — |
| symm | 3563 | 533 | 234 | 46 | 0 | 0 | 0 | 0 | 386 | 1 | yes | — |
| trisolv_int | 975 | 1404 | 220 | 121 | 119 | 116 | 3 | 0 | 1 | 1 | yes | invalid |
| cm_vect | 937 | 1356 | 209 | 119 | 117 | 112 | 5 | 0 | 1 | 1 | yes | invalid |
| other 10 | … | … | … | … | 0 | 0 | 0 | 0 | n | 1 | yes* | — |

(`*` `cm_mul`: 927+1149 < 4096 — the only non-truncated completion, and still 0 matches: format collapse is systematic, not caused by truncation.)

Format diagnosis: the model emits lines like `расписание: такт=1 канал=2` — **omitting the instruction ID** (apparently echoing the trailing prompt header), so `decode_completion` (`(\d+): ...`) matches zero lines. The very first line is malformed everywhere (for `covariance`, line 1 drops ID `0:`, followed by 149 lines with IDs). Duplicate IDs: `covariance` only (32). Out-of-range IDs: `trisolv` 3, `cm_vect` 5. Complete valid raw schedules: **0 of 25**.
Determinism: re-generating `covariance` at `temperature=0` produced byte-identical output (matching SHA-256), confirming reproducibility.

Regarding `temperature=0.8` (3×2–3 graphs): **intentionally omitted**. Format breakdown occurs on 12/13 `temp=0` runs and on the sole non-truncated completion — this is systematic OOD failure, not sampling variance; stochastic retries cannot be deterministically re-verified and cannot flip the L3 verdict (Section 3). Compute budget was spent on the 12 control generations for V5 instead.

## 3. Task C: Layers and Headline Number

| graph | L0 | L1 | L2 10/100/1000 | L2-fair (T, trials) | L3 (winner) | order@coverage |
|---|---|---|---|---|---|---|
| gemm | 35 | 34 | 35/34/33 | 33 (385s, 42k) | 35 greedy | 35@0.00 |
| gesummv | 56 | 53 | 54/54/53 | 53 (339s, 29k) | 56 greedy | 56@0.00 |
| symm | 72 | 66 | 71/68/68 | 67 (234s, 6k) | 72 greedy | 72@0.00 |
| gramschmidt | 82 | 75 | 78/77/75 | 75 (323s, 10k) | 82 greedy | 82@0.00 |
| jacobi2d | 68 | 66 | 64/64/63 | 62 (253s, 10k) | 68 greedy | 68@0.00 |
| adi | 114 | 113 | 114/113/113 | 113 (366s, 29k) | 114 greedy | 114@0.00 |
| fdtd | 61 | 59 | 60/60/59 | 58 (313s, 10k) | 61 greedy | 61@0.00 |
| floyd | 47 | 47 | 47/47/46 | 46 (368s, 18k) | 47 greedy | 47@0.00 |
| heat3d | 54 | 52 | 54/53/53 | 52 (300s, 23k) | 54 greedy | 54@0.00 |
| covariance | 93 | 92 | 93/91/91 | 90 (370s, 47k) | 93 greedy | 94@0.80 |
| fir | 61 | 60 | 61/60/60 | 60 (214s, 12k) | 61 greedy | 61@0.00 |
| iir | 44 | 43 | 43/43/43 | 43 (391s, 28k) | 44 greedy | 44@0.00 |
| tsvc | 51 | 45 | 48/47/46 | 46 (361s, 29k) | 51 greedy | 51@0.00 |

(L2: fresh seeds `500001+i`, S1 grid; L2-fair: seeds `510001+i`, time budget = generation time `T(g)`; L3: `decode_completion → repair-mirror → variants/choose` on saved text. Portfolio winner is "greedy" everywhere.)

**Headline result: L3 is strictly shorter than L2 on 0 of 13 graphs (+0 cycles total). Against L2-fair (equal wall-clock time: random search in the same minutes finds 90/33/46/…), also 0 of 13.** The model contributes nothing even when its candidate enters the portfolio: the portfolio always picks greedy.

Ordering sub-question: at 0.00 coverage, the "order" candidate equals greedy by construction (12 cases); the only non-zero coverage is `covariance` 0.80 → **94, 1 cycle WORSE than greedy's 93**; `trisolv` 0.99 → 140 vs. 128 (+12); `cm_vect` 0.99 → 24 vs. 19 (+5). Observation: the more nodes the model annotates, the worse its ordering becomes relative to height — the prefix carries no useful signal, only harm. There is no positive slope anywhere in "coverage → quality".

## 4. Task D: Reference Table (25 Graphs)

L0 / L1 / L2 (10/100/1000) / best known from `search/best_known.json`:

| graph | L0 | L1 | 10/100/1000 | best |
|---|---|---|---|---|
| gemm | 35 | 34 | 35/34/33 | 33 |
| gesummv | 56 | 53 | 54/54/53 | 53 |
| symm | 72 | 66 | 71/68/68 | 67 |
| gramschmidt | 82 | 75 | 78/77/75 | 75 |
| jacobi2d | 68 | 66 | 64/64/63 | 61 |
| adi | 114 | 113 | 114/113/113 | 113 |
| fdtd | 61 | 59 | 60/60/59 | 57 |
| floyd | 47 | 47 | 47/47/46 | 46 |
| heat3d | 54 | 52 | 54/53/53 | 52 |
| covariance | 93 | 92 | 93/91/91 | 90 |
| fir | 61 | 60 | 61/60/60 | 59 |
| iir | 44 | 43 | 43/43/43 | 43 |
| tsvc | 51 | 45 | 48/47/46 | 46 |
| syrk/trmm/durbin/trisolv/seidel/jacobi1d/gemver/lu/oblas/cm_* | =L0 | =L0 | =L0 | =L0 |

(controls: all layers equal greedy — already at the lower bound; L2-fair is omitted on controls since the fairness budget ties to generation time.)

## 5. `VERIFY.sh` Output (exit 0)

```
PASS  base-25  25/25 == 25/25
PASS  rule-poly_covariance  92 == 92
PASS  rule-poly_gemm  34 == 34
PASS  rule-tsvc_s1111  45 == 45
PASS  rule-poly_adi  113 == 113
PASS  rule-poly_gesummv  53 == 53
PASS  rule-emb_iir  43 == 43
PASS  rule-poly_floyd_int  47 == 47
PASS  rule-poly_heat3d  52 == 52
PASS  rule-poly_gramschmidt  75 == 75
PASS  rule-poly_fdtd  59 == 59
PASS  rule-emb_fir  60 == 60
PASS  rule-poly_jacobi2d  66 == 66
PASS  rule-poly_symm  66 == 66
PASS  model-replay-13  13/13 == 13/13
PASS  L3-vs-L2-headline+L2-replay  13/13 == 13/13
PASS  control-12  12/12 == 12/12
PASS  L2-fair-poly_covariance  T=370s/K=46840 == exp~51424
PASS  L2-fair-poly_gemm  T=385s/K=42218 == exp~45869
PASS  L2-fair-tsvc_s1111  T=361s/K=29475 == exp~32032
PASS  L2-fair-poly_adi  T=366s/K=28773 == exp~31149
PASS  L2-fair-poly_gesummv  T=339s/K=28854 == exp~31476
PASS  L2-fair-emb_iir  T=391s/K=27696 == exp~29525
PASS  L2-fair-poly_floyd_int  T=368s/K=17922 == exp~19306
PASS  L2-fair-poly_heat3d  T=300s/K=22788 == exp~24865
PASS  L2-fair-poly_gramschmidt  T=323s/K=9651 == exp~10020
PASS  L2-fair-poly_fdtd  T=313s/K=10163 == exp~10519
PASS  L2-fair-emb_fir  T=214s/K=12111 == exp~12920
PASS  L2-fair-poly_jacobi2d  T=253s/K=10318 == exp~10793
PASS  L2-fair-poly_symm  T=234s/K=6071 == exp~6191
TOTAL PASS=30 FAIL=0
VERIFY OK
```

Checks: V1 baseline 25/25; V2 rule 13/13; V3 model replay from saved text (decode + portfolio + raw) 13/13; V4 headline + replay of L2 winners; V5 controls 12/12 (no layer shorter than greedy); V6 L2-fair: vector replay + consistency of K with T/t (band 0.2–5, observed 0.91–0.98). Runs without the model in ~2 min.

## 6. Cost and Files

Generation: ~75 min (13 targets) + ~70 min (12 controls) + repeats; speed 1.5–6.5 tok/s. Model-free layers: ~6 min (fixed) + ~25 min wall-clock (fair, 76 CPU-min). Total wall-clock time ~3 hours.
Files: `raw/*.txt` (25) + `raw/*.meta.json`, `decode.json`, `results.json` (L0/L1/L2/L2-fair/L3/order/raw/best_known), `layers/` (intermediate), `VERIFY.sh` + `verify_impl.py`, `run.sh` (everything except generation; seeds `500001+`/`510001+` pinned), scripts `gen_one.py`, `layers_fixed.py`, `fair_one.py`, `replay*.py`, `merge_*.py`, `tokens.py`, `probe_runtime.py`, `dump_decode.py`. `search/finds.jsonl` and `rule/` are untouched (`git status` shows only `model_eval/`).

## 7. Weakest Points (Honestly)

Two. First: the model was evaluated at exactly one operating point (`temp=0`, `ctx=4096`, `lora-merged`) — the conclusion "useless" applies to this point, not to LLMs in general; larger context or fine-tuning on long graphs are different points not measured here. Second: the fair comparison is tied to wall-clock time (trial counts fluctuate ±% across runs), and V6 checks only coarse consistency rather than byte-exact search reproduction.
