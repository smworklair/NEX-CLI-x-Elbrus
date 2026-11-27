# `nnl_isa`: Two NNL Cores Predicting Mnemonic Classes

> **Status: experiment.** Not wired into the CLI.

Branch `nnl-isa` off `nnl-vliw` (`f7469eb`). Two cores, each a single network of four blocks (softmax over "none" and all block answers). The "name" core (19,307 parameters, dim 24) splits classes into integer/memory, floating-point, predicates/control, packed SIMD, and AAU. The "usage" core (17,491 parameters, dim 32, different hash salt) splits by channel set. The class table lives in `ядра.py`.
Labels were not modified: `MNEMONICS` and `model.py` remain unchanged.

Validation: leave-mnemonic-out, 5-fold, stratified by class. 158 mnemonics evaluated. Train-only (single mnemonic in class): `INCR`, `MOVAQ`. Abstention = "none" answer.

## A–C. Cores vs. Baselines (Identical Folds)

| | accuracy | abstention rate | accuracy on answered |
|---|---:|---:|---:|
| "name" core | 0.8418 | 0.0253 | 0.8636 |
| logistic regression, name tokens | 0.9304 | 0 | 0.9304 |
| nearest neighbor on n-grams | 0.8291 | 0 | 0.8291 |
| "usage" core | 0.2089 | 0.0316 | 0.2157 |
| logistic regression, usage tokens | 0.2785 | 0 | 0.2785 |

## D. Cross-Core Verification

Agreement (both cores predict the same class) → accept; otherwise "verify with assembler".
Accepted 30 of 158 (abstention 0.8101), of which 29 are correct (agreement accuracy 0.9667).
Random abstention at the same rate using the "name" core's answer gives an expected 25.25 correct.
Cross-checking beats that baseline (29 > 25.25) and beats the "name" core's answered accuracy (0.8636), though the margin is small. On the 13 unknown mnemonics there is zero agreement: all 13 are flagged "verify with assembler" (`предложения.md`).

## E. Latency Assumptions (10 Classes Present in the Files)

Minimum producer→consumer gap by dst/srcs within a function, never crossing a loop boundary.
True latency cannot exceed this minimum. An assumption larger than the minimum is refuted. Fewer than 3 pairs = "insufficient data". Minimum larger than the assumption = "questionable" (not a refutation, since the compiler may have left slack). The guide column cites Section 6.1, release 1.2, CC BY 4.0 — which covers **E4C/E8C, not `e2k-v6`**. Chapter 12 gives pair delays and is not folded into the class column. Blank where the class is absent from Section 6.1.

| class | assumption | pairs | min gap | verdict | MCST guide |
|---|---:|---:|---:|---|---|
| AAU | 1 | 4 | 7 | questionable | |
| AND | 1 | 9 | 1 | consistent | 1 (Int, Bitwise) |
| INCR | 1 | 0 | — | insufficient data | |
| INSF | 1 | 4 | 1 | consistent | |
| MERGE | 1 | 169 | 1 | consistent | |
| MOVA | 1 | 63 | 5 | questionable | |
| PACK | 1 | 6 | 5 | questionable | |
| PRED | 1 | 21 | 1 | consistent | 0.5–3 (consumer-dependent) |
| RW | 1 | 0 | — | insufficient data | |
| SHL | 1 | 167 | 1 | consistent | 1 (Int, Bitwise) |

Refuted assumptions: **0**. Questionable: AAU, MOVA, PACK. Insufficient data: INCR, RW (`incr`/`%lsr` destination is not read further within the parsed snippet).

## Conclusion

On mnemonic names, the NNL core (0.842) edges out n-gram nearest neighbor (0.829) but trails logistic regression on the same tokens (0.930). A linear model suffices here.
On usage context, both the NNL core (0.209) and logistic regression (0.278) are weak: only 55 of 160 mnemonics appear across the 25 files, and many classes share identical channels.
Cross-checking abstains 81% of the time. On the rare agreements, it slightly beats random abstention (29 correct vs. 25.3 expected) — unlike the earlier experiment where cross-checking failed to beat random, though the margin remains narrow.
No latency assumptions were refuted: all ten default to 1, and no observed gap is shorter than 1 cycle. AAU, MOVA, and PACK are questionable, with minimums above 1.
The two cores did not agree on any of the 13 unknown mnemonics; none of the proposals in `предложения.md` were added to the dictionary.
