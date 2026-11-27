"""Node features for Tiny-1 (priority). Pure stdlib.

Features come from vliw.core: DAG + machine model + metrics (asap/height).
No text or tokenizer: ordering is learned from numbers, not strings.
"""

from __future__ import annotations

from ..core.dag import DAG, DagBuilder, compute_metrics
from ..core.model import MachineModel

# Operations from the synthetic generator (tools/vliw_gen.py, random_dag):
# these appear in train_merged/eval_hard. Everything else (FADD, PRED,
# PACK, ...) maps to the "OTHER" bucket so Tiny does not fail on real
# code and gracefully degrades to height.
SYNTH_OPS: tuple[str, ...] = ("ADD", "SUB", "MUL", "DIV", "AND", "SHL", "LOAD", "STORE")

FEATURE_NAMES: tuple[str, ...] = (
    *[f"op_{o}" for o in SYNTH_OPS],  # 8 one-hot
    "height_n",    # remaining critical path / max
    "asap_n",      # earliest start (ASAP) / (max+1)
    "lat_n",       # latency / 11 (DIV is synthetic max)
    "occ_extra",   # occupancy-1 (0/1): holds port exclusively
    "nchan_n",     # number of valid channels / 6
    "indeg_n",     # predecessor count / 2
    "outdeg_n",    # successor count / n
    "is_div",      # exclusive port ,5 — main trap (slotclash)
    "is_store",    # narrow store ,2 ,5 — second trap (memstream)
)

N_FEATURES = len(FEATURE_NAMES)  # 18


def parse_graph_entries(prompt: str) -> list[tuple[int, str, tuple[int, ...]]]:
    """Parse 'ID OP <- preds' lines from prompt -> (id, op, preds).

    Format from training/encode.encode_prompt: header + graph lines,
    one line per instruction, ending with schedule marker.
    """
    out: list[tuple[int, str, tuple[int, ...]]] = []
    for line in prompt.splitlines():
        line = line.strip()
        if (not line or line.startswith(("profile:", "\u043f\u0440\u043e\u0444\u0438\u043b\u044c:"))
                or line in ("graph:", "schedule:", "\u0433\u0440\u0430\u0444:", "\u0440\u0430\u0441\u043f\u0438\u0441\u0430\u043d\u0438\u0435:")):
            continue
        parts = line.split()
        try:
            idx = int(parts[0])
        except ValueError:
            continue
        op = parts[1] if len(parts) > 1 else "ADD"
        preds: tuple[int, ...] = ()
        if "<-" in parts:
            arrow = parts.index("<-")
            preds = tuple(int(x) for x in parts[arrow + 1:])
        out.append((idx, op, preds))
    out.sort(key=lambda t: t[0])
    return out


def transitive_succs(succs: list[tuple[int, ...]], n: int) -> list[frozenset]:
    """Transitive descendants of each node (memoized DFS, acyclic DAG).

    Kept separate from featurize: used by both the exclusive-port rule
    (`scheduler.rule_holds`) and loss analysis.
    """
    memo: dict[int, frozenset] = {}

    def reach(i: int) -> frozenset:
        if i in memo:
            return memo[i]
        out: set[int] = set()
        stack = list(succs[i])
        while stack:
            j = stack.pop()
            if j in out or j == i:
                continue
            out.add(j)
            stack.extend(succs[j])
        memo[i] = frozenset(out)
        return memo[i]

    return [reach(i) for i in range(n)]


def build_dag(entries: list[tuple[int, str, tuple[int, ...]]], key: str = "tmp") -> DAG:
    """Build a DAG from parsed rows (IDs must be consecutive)."""
    b = DagBuilder(key, "", "")
    for idx, op, preds in entries:
        assert idx == len(b._instrs), f"non-consecutive id: {idx}"
        b.op(op, f"n{idx}", *preds)
    return b.build()


def parse_placements(completion: str) -> dict[int, tuple[int, int]]:
    """Parse completion 'i: cycle=c channel=ch' -> {id: (cycle, channel)}.
    Matches training/encode.decode_completion without importing training."""
    import re
    out: dict[int, tuple[int, int]] = {}
    for m in re.finditer(r"(\d+):\s*(?:cycle|\u0442\u0430\u043a\u0442)=(\d+)\s*(?:channel|\u043a\u0430\u043d\u0430\u043b)=(\d+)", completion):
        i, c, ch = (int(x) for x in m.groups())
        out[i] = (c, ch)
    return out


def oracle_order(placements: dict[int, tuple[int, int]], n: int) -> list[int]:
    """Oracle ordering: sorted by (cycle, channel). Matches the key in
    vliw/learned/portfolio.order_from_model — trains exactly what CAB consumes."""
    return sorted(range(n), key=lambda i: (placements[i][0], placements[i][1], i))


def featurize(dag: DAG, model: MachineModel) -> list[list[float]]:
    """DAG + machine model -> (n x 18) float matrix. Pure Python."""
    from ..core.dag import compute_metrics as _cm
    metrics = _cm(dag, model)
    n = len(dag)
    max_h = max(metrics.height) if n else 1
    max_a = max(metrics.asap) if n else 0
    succs = dag.succs
    X: list[list[float]] = []
    for ins in dag:
        i = ins.id
        row = [0.0] * N_FEATURES
        try:
            row[SYNTH_OPS.index(ins.op)] = 1.0
        except ValueError:
            pass  # OTHER: all zeros in one-hot — clean degradation
        row[8] = (metrics.height[i] / max_h) if max_h else 0.0
        row[9] = (metrics.asap[i] / (max_a + 1)) if n else 0.0
        row[10] = model.latency(ins.op) / 11.0
        row[11] = float(model.occupancy(ins.op) - 1)
        row[12] = len(model.channels_for(ins.op)) / 6.0
        row[13] = len(ins.preds) / 2.0
        row[14] = (len(succs[i]) / n) if n else 0.0
        row[15] = 1.0 if ins.op == "DIV" else 0.0
        row[16] = 1.0 if ins.op == "STORE" else 0.0
        X.append(row)
    return X
