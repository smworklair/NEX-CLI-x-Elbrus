"""Замер на real_candidates_100_400/asm. eval_* не читается.

Пишет nnl_rewrite/results/сводка.json. Числа в README берутся отсюда.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from nnl_rewrite.базис import SEEDS, логрегрессия, признаки
from nnl_rewrite.приёмы import применить, правило
from vliw.core.blocks import block_graphs_of_file
from vliw.core.model import E2K_V6_MEASURED as M

ROOT = Path(__file__).resolve().parents[1]
ASM = ROOT / "real_candidates_100_400" / "asm"
OUT = Path(__file__).resolve().parent / "results" / "сводка.json"


def main() -> None:
    rows = []
    for path in sorted(ASM.glob("*.s")):
        for bg in block_graphs_of_file(path, min_ops=1):
            it = применить(bg.dag, M, fp=False)
            fp = применить(bg.dag, M, fp=True)
            rule = правило(bg.dag, M)
            rows.append({
                "file": path.name,
                "index": bg.block.index,
                "loop": bg.block.loop,
                "n": len(bg.dag),
                "было": it.было,
                "стало": it.стало,
                "приём": it.приём,
                "правило": rule,
                "fp_стало": fp.стало,
                "fp_приём": fp.приём,
                "x": признаки(bg.dag),
                "y": int(it.приём is not None),
                "rule": int(rule is not None),
            })
    linear = [r for r in rows if not r["loop"]]
    gain = sum(r["было"] - r["стало"] for r in rows)
    gain_lin = sum(r["было"] - r["стало"] for r in linear)
    fp_gain_lin = sum(r["было"] - r["fp_стало"] for r in linear)
    by = Counter(r["приём"] or "не трогать" for r in rows)
    agree = sum(int((r["приём"] is not None) == (r["правило"] is not None)) for r in rows)
    basis_rows = [
        {"file": r["file"], "x": r["x"], "y": r["y"], "rule": r["rule"]}
        for r in rows
    ]
    seeds = [логрегрессия(basis_rows, s) for s in SEEDS]
    # Ядро нужно, только если на каждом сиде и правило, и логрегрессия
    # ошиблись хотя бы раз. Иначе учить нечего.
    both_missed = all(
        s["правило_верно"] < s["блоков_тест"] and s["логрегрессия_верно"] < s["блоков_тест"]
        for s in seeds
    )
    summary = {
        "блоков": len(rows),
        "линейных": len(linear),
        "loop_mode": sum(1 for r in rows if r["loop"]),
        "тактов_жадный_линейные": sum(r["было"] for r in linear),
        "тактов_жадный_все": sum(r["было"] for r in rows),
        "законный_выигрыш_линейные": gain_lin,
        "законный_выигрыш_все": gain,
        "по_приёмам": dict(by),
        "где_короче": [
            {"файл": r["file"], "блок": r["index"], "loop": r["loop"],
             "приём": r["приём"], "было": r["было"], "стало": r["стало"]}
            for r in rows if r["приём"]
        ],
        "правило_совпало_с_движком": agree,
        "fp_выигрыш_линейные_не_применяется": fp_gain_lin,
        "сиды": seeds,
        "nnl": "не училось" if not both_missed else "базисы промахнулись",
        "оба_базиса_промахнулись_на_всех_сидах": both_missed,
    }
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
