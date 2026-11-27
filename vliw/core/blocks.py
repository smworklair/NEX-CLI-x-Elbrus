"""Basic-block splitting for lcc `.s` output: one DAG per basic block.

Splits on labels and control-transfer wide instructions (`ct`, `ibranch`,
`call`, `return`, `rbranch`). Live-in registers are treated as ready at cycle 0.
Hardware-pipelined `loop_mode` blocks are flagged via `Block.loop`.
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

#: Size buckets by instruction count (matching block reports).
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
    """Single basic block extracted from assembly text."""

    index: int       # 0-based block index in file (only blocks containing wide instructions)
    label: str       # leading label ("" if block started without a label)
    text: str        # raw source lines of the block
    bundles: int     # count of wide instructions `{ ... }` in the block
    loop: bool       # whether the block contains `loop_mode`


@dataclass
class BlockGraph:
    """Block + parsed assembly + DAG for scheduling and lcc comparison."""

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
        """Reconstructed lcc schedule and optional rejection reason: `(Schedule|None, (title, detail)|None)`."""
        return asm_parser.compiler_schedule_checked(self.parsed, self.dag, model)


def split_blocks(text: str) -> list[Block]:
    """Split `.s` text into basic blocks, omitting blocks without wide instructions."""
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
    """Parse text into blocks with DAGs, filtering blocks shorter than `min_ops`."""
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
# Sliding windows of consecutive wide instructions
# --------------------------------------------------------------------------

#: Target window sizes in operations (short blocks where exact search
#: proves optimality in milliseconds).
WINDOW_TARGETS: tuple[int, ...] = (16, 24, 32, 48)


@dataclass
class WindowGraph:
    """Block window + standalone DAG (values from earlier bundles assumed ready)."""

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
    """Extract sliding windows across blocks for each target size, keeping
    windows with `min_ops`..`max_ops` operations."""
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
