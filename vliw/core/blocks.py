"""Режим «по блокам»: `.s` от lcc режется на базовые блоки, каждый — свой граф.

Зачем. `asm_parser.build_dag` строит ОДИН граф на весь текст. Метки внутри файла
при этом ничего не значат, и граф тянется через границы блоков — а переходы
между блоками планировщик не переставляет. Последствие измерено на 25 настоящих
файлах lcc: расписание самого компилятора на графе файла целиком восстанавливается
и проходит проверку в 4 файлах из 25, а по блокам — в 71 блоке из 93 (n >= 10).
То есть сравнивать с lcc, считать запас и доказывать оптимум честно можно только
по блокам. Так же работает и статья GRASP (ICS '26): единица работы — базовый блок.

Что считается блоком. Блок начинается с метки (или с начала файла) и
заканчивается широкой командой, в которой есть передача управления:
`ct`, `ibranch`, `call`, `return`, `rbranch`. Новая метка закрывает предыдущий
блок, даже если перехода не было (провал вниз). Значения, пришедшие в блок
снаружи, разбор считает готовыми к такту 0 — это стандартное допущение
`build_dag`: чтение регистра, которого в блоке никто не писал, зависимости не
создаёт.

Что здесь НЕ делается. Блок не оптимизируется «в контексте» соседей (какие
регистры живы на выходе, что ждёт после перехода) — как и в остальном проекте,
считается длина линейного куска по модели машины. Циклы `loop_mode`
(аппаратная конвейеризация) размечены флагом `Block.loop`: для них такты на
итерацию — другая величина, чем длина текста, и модель их не описывает.

Модуль только читает текст; существующий код не меняет.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from . import asm_parser
from .dag import DAG
from .model import MachineModel

_COMMENT = re.compile(r"(//|!|;).*$")
_LABEL = re.compile(r"^\s*([.\w$]+):\s*$")
_XFER = re.compile(r"^\s*(?:ct|ibranch|call|return|rbranch)\b")

#: Корзины по числу операций (как в отчёте по блокам).
BUCKETS: tuple[tuple[str, int], ...] = (
    ("<10", 9), ("10-49", 49), ("50-99", 99), ("100-199", 199), ("200+", 10 ** 9),
)


def bucket_of(n_ops: int) -> str:
    for name, hi in BUCKETS:
        if n_ops <= hi:
            return name
    return BUCKETS[-1][0]


@dataclass(frozen=True)
class Block:
    """Один базовый блок исходного текста."""

    index: int       # номер блока в файле (с нуля, только блоки с широкими командами)
    label: str       # метка в начале блока ("" — блок начался без метки)
    text: str        # строки блока, как в файле
    bundles: int     # широких команд `{ ... }` в блоке
    loop: bool       # в блоке есть `loop_mode`


@dataclass
class BlockGraph:
    """Блок + его разбор + граф. Всё, что нужно планировщику и сравнению с lcc."""

    block: Block
    parsed: "asm_parser.ParsedAsm"
    dag: DAG

    @property
    def n(self) -> int:
        return len(self.dag)

    @property
    def bucket(self) -> str:
        return bucket_of(self.n)

    def lcc_schedule(self, model: MachineModel):
        """Расписание, которое построил сам lcc, и причина, если его нельзя
        показывать: `(Schedule|None, (заголовок, подробность)|None)`."""
        return asm_parser.compiler_schedule_checked(self.parsed, self.dag, model)


def split_blocks(text: str) -> list[Block]:
    """Разрезать текст `.s` на базовые блоки. Блоки без единой широкой команды
    (одни метки и директивы) не возвращаются."""
    out: list[Block] = []
    cur: list[str] = []
    label = ""
    in_bundle = False
    has_transfer = False
    n_bundles = 0

    def flush() -> None:
        nonlocal cur, n_bundles, label
        if n_bundles:
            body = "\n".join(cur)
            out.append(Block(index=len(out), label=label, text=body,
                             bundles=n_bundles, loop="loop_mode" in body))
        cur, n_bundles, label = [], 0, ""

    for raw in text.splitlines():
        s = _COMMENT.sub("", raw).strip()
        if not in_bundle:
            m = _LABEL.match(s)
            if m:
                flush()
                label = m.group(1)
                cur.append(raw)
                continue
            if s.startswith("{"):
                in_bundle, has_transfer = True, False
                n_bundles += 1
                cur.append(raw)
                if _XFER.match(s[1:].strip()):
                    has_transfer = True
                continue
        else:
            if s.startswith("}"):
                in_bundle = False
                cur.append(raw)
                if has_transfer:
                    flush()
                continue
            if _XFER.match(s):
                has_transfer = True
        cur.append(raw)
    flush()
    return out


def block_graphs(text: str, source: str = "", min_ops: int = 1) -> list[BlockGraph]:
    """Блоки текста вместе с графами. `min_ops`: отбросить блоки короче
    (по числу операций после разбора; в отчётах обычно 10)."""
    stem = Path(source).stem if source else "asm"
    res: list[BlockGraph] = []
    for b in split_blocks(text):
        parsed = asm_parser.parse_asm(b.text, source=f"{source or 'asm'}#{b.index}")
        if len(parsed.ops) < max(min_ops, 1):
            continue
        dag = asm_parser.build_dag(parsed, key=f"{stem}#{b.index}", title="")
        res.append(BlockGraph(b, parsed, dag))
    return res


def block_graphs_of_file(path: str | Path, min_ops: int = 1) -> list[BlockGraph]:
    p = Path(path)
    return block_graphs(p.read_text(encoding="utf-8"), source=p.name, min_ops=min_ops)


# --------------------------------------------------------------------------
# Окна: куски блока из подряд идущих широких команд
# --------------------------------------------------------------------------

#: Целевые размеры окон в операциях (как в замерах: короткие участки, где точный
#: поиск доказывает оптимум за миллисекунды).
WINDOW_TARGETS: tuple[int, ...] = (16, 24, 32, 48)


@dataclass
class WindowGraph:
    """Окно блока + граф. Граф окна — отдельный участок: всё, что пришло из
    предыдущих широких команд блока, считается готовым."""

    block_index: int
    start_bundle: int
    target: int
    loop: bool
    parsed: "asm_parser.ParsedAsm"
    dag: DAG

    @property
    def n(self) -> int:
        return len(self.dag)


def _bundle_texts(block_text: str) -> list[str]:
    out: list[str] = []
    cur: list[str] = []
    in_bundle = False
    for raw in block_text.splitlines():
        s = _COMMENT.sub("", raw).strip()
        if not in_bundle and s.startswith("{"):
            in_bundle, cur = True, [raw]
            continue
        if in_bundle:
            cur.append(raw)
            if s.startswith("}"):
                in_bundle = False
                out.append("\n".join(cur))
    return out


def window_graphs(text: str, source: str = "",
                  targets: tuple[int, ...] = WINDOW_TARGETS,
                  min_ops: int = 12, max_ops: int = 56) -> list[WindowGraph]:
    """Скользящие окна по блокам: для каждого целевого размера окно набирается из
    подряд идущих широких команд, пока не наберётся `target` операций, и сдвигается
    примерно на половину окна. Берутся окна, в которых от `min_ops` до `max_ops`
    операций. Окна разных целевых размеров могут совпадать по составу — это
    допущено (как и в замерах, из которых взяты эти параметры)."""
    stem = Path(source).stem if source else "asm"
    res: list[WindowGraph] = []
    for b in split_blocks(text):
        bl = _bundle_texts(b.text)
        counts = [len(asm_parser.parse_asm(x).ops) for x in bl]
        for target in targets:
            step_ops = max(target // 2, 8)
            i = 0
            while i < len(bl):
                j, tot = i, 0
                while j < len(bl) and tot < target:
                    tot += counts[j]
                    j += 1
                if min_ops <= tot <= max_ops:
                    wtxt = "\n".join(bl[i:j])
                    wp = asm_parser.parse_asm(wtxt, source=source)
                    if len(wp.ops) >= min_ops:
                        dag = asm_parser.build_dag(
                            wp, key=f"{stem}#{b.index}w{i}t{target}", title="")
                        res.append(WindowGraph(b.index, i, target, b.loop, wp, dag))
                acc, k = 0, i
                while k < len(bl) and acc < step_ops:
                    acc += counts[k]
                    k += 1
                i = max(k, i + 1)
    return res
