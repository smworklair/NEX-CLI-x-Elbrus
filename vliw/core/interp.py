"""Вычислительный интерпретатор: считает числа, держит память и имена.

Параллельно собирает граф — его можно отдать планировщику командой go.
Это не «текст → DAG». Сначала результат, граф — побочный продукт.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .dag import DAG, DagBuilder, Instr

_BIN = {"+": "ADD", "-": "SUB", "*": "MUL", "/": "DIV", "&": "AND", "<<": "SHL"}
_UNARY = {"load": "LOAD", "ld": "LOAD", "shl": "SHL"}
_ASSIGN = re.compile(
    r"^(\w+)\s*=\s*(load|ld|shl|[-+]?\w+)(?:\s*(\+|-|\*|/|&|<<)\s*(\w+))?\s*$",
    re.I,
)
_STORE = re.compile(r"^(?:store|st)\s+(\w+)\s*$", re.I)

KERNELS: dict[str, tuple[str, int]] = {
    "sum":   ("сумма mem[0..n)", 8),
    "dot":   ("скалярное произведение двух векторов длины n", 4),
    "saxpy": ("y[i] += a*x[i], n точек", 8),
    "chase": ("цепочка указателей длины n", 6),
    "div":   ("n делений подряд", 4),
    "gemm":  ("матрица n×n, n=2 или 3", 2),
    "horner":("полином степени n схемой Горнера", 6),
    "fir":   ("свёртка окна n", 8),
    "rms":   ("сумма квадратов / n", 8),
    "copy":  ("копирование n ячеек", 8),
    "addn":  ("поэлементная сумма двух массивов", 8),
}

_KERNEL = re.compile(
    r"^(" + "|".join(KERNELS) + r")(?:\s+(\d+))?\s*$",
    re.I,
)

VERBS = ("reset", "new", "names", "env", "list", "graph", "ops", "go", "mem")
MEM_SIZE = 64

_OPS = {"+", "-", "*", "/", "&", "<<"}


class InterpError(ValueError):
    pass


def _did_you_mean(name: str, known) -> str:
    """Хвост сообщения об ошибке: что человек, скорее всего, имел в виду.

    Появилось по живому промаху: на `mul m0 a0 b0` — совершенно разумную для
    e2k строку — интерпретатор отвечал «нет имени mul» и замолкал. Человек
    не знает, что можно писать, а инструмент знает и молчит. Тупик на ровном
    месте, причём в первой же строке, которую набирает новый пользователь.

    Похожие имена ищем всегда, а список доступного показываем, только если
    похожих нет: иначе подсказка тонет в перечислении.
    """
    import difflib

    pool = sorted(set(known) | set(KERNELS) | set(VERBS))
    close = difflib.get_close_matches(name, pool, n=3, cutoff=0.6)
    if close:
        return "  может быть: " + ", ".join(close)
    # Похожего нет — значит человек, скорее всего, пишет не на том языке.
    # Самый частый случай: набирают мнемонику e2k (`mul m0 a0 b0`), потому
    # что весь остальной инструмент про них и говорит. Показываем не список
    # слов, а ФОРМУ строки: одного примера хватает, чтобы понять правило.
    real = [n for n in sorted(known) if not n.startswith("_")]
    tail = ("  имена: " + ", ".join(real[:8])) if real else \
           ("  ядра: " + ", ".join(sorted(KERNELS)))
    return ("  здесь считают выражениями, а не мнемониками e2k:\n"
            "    a0 = load [0]      b0 = load [1]      s = a0 * b0\n"
            + tail)


def looks_like_work(text: str, known: dict | None = None) -> bool:
    s = text.strip()
    if not s:
        return False
    head = s.split()[0].lower()
    if head in VERBS or head in KERNELS:
        return True
    if _KERNEL.match(s):
        return True
    if head in ("load", "ld", "store", "st", "mem"):
        return True
    if "=" in s:
        return True
    if any(op in s for op in ("+", "*", "/", "<<", "&")) or (s.count("-") and not s.isidentifier()):
        return True
    if re.fullmatch(r"[-+]?\d+", s):
        return True
    if s.isidentifier() and known is not None and s in known:
        return True
    parts = [p.strip() for p in s.split(";") if p.strip()]
    return bool(parts) and all(_ASSIGN.match(p) or _STORE.match(p) for p in parts)


@dataclass
class ExecResult:
    ok: bool
    kind: str
    value: int | None = None
    name: str = ""
    message: str = ""
    added: list[str] = field(default_factory=list)


class Workspace:
    """Машина: имена → числа, память, последний результат.

    go отдаёт собранный граф в разбор. Счёт не зависит от планировщика.
    """

    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self.regs: dict[str, int] = {}
        self.mem: list[int] = [i + 1 for i in range(MEM_SIZE)]
        self._lp = 0
        self.log: list[str] = []
        self.last: int | None = None
        self._b = _b("ws", "интерпретатор", "считает здесь. go — в разбор.")
        self._ids: dict[str, int] = {}
        self._last_node: int | None = None
        self._used_names: set[str] = set()

    @property
    def names(self) -> dict[str, int]:
        return self.regs

    def empty(self) -> bool:
        return not self._b._instrs

    def snapshot(self) -> DAG:
        src = self._b
        instrs = [
            Instr(i, ins.name, ins.op, ins.preds, ins.text)
            for i, ins in enumerate(src._instrs)
        ]
        return DAG(src.key, src.title, src.note, instrs, src.profile,
                   src.family, src.lesson)

    def exec(self, text: str) -> ExecResult:
        s = text.strip()
        if not s:
            return ExecResult(True, "empty")
        parts = [p.strip() for p in s.split(";") if p.strip()]
        last = ExecResult(True, "empty")
        for part in parts:
            last = self._exec_one(part)
        self.log.append(s)
        return last

    def _exec_one(self, s: str) -> ExecResult:
        head = s.split()[0].lower()
        if head == "mem":
            return self._mem_line(s)
        if head in VERBS and "=" not in s:
            return self._verb(head, s)
        km = _KERNEL.match(s)
        if km:
            return self._kernel(km.group(1), km.group(2))
        if re.match(r"^(store|st)\b", s, re.I):
            return self._store_line(s)
        if re.match(r"^mem\b", s, re.I) or s.lower() == "mem":
            return self._mem_line(s)
        if "=" in s:
            left, _, right = s.partition("=")
            name = left.strip()
            if not name.isidentifier():
                raise InterpError(f"плохое имя {name!r}")
            src = right.strip()
            val = self._eval(src, dest=name)
            self.regs[name] = val
            self.last = val
            return ExecResult(True, "assign", value=val, name=name)
        val = self._eval(s)
        self.last = val
        return ExecResult(True, "value", value=val)

    def _verb(self, head: str, raw: str) -> ExecResult:
        if head in ("reset", "new"):
            self.reset()
            return ExecResult(True, "reset", message="регистры пусты, память 1,2,3…")
        if head in ("names", "env"):
            return ExecResult(True, "env")
        if head == "mem":
            return ExecResult(True, "mem")
        if head in ("list", "graph", "ops"):
            return ExecResult(True, "list")
        if head == "go":
            if self.empty() and not self.regs:
                raise InterpError("нечего планировать — нет графа")
            if self.empty():
                self._b = _b("ws", "интерпретатор", "граф из вычислений")
            return ExecResult(True, "go", value=self.last)
        raise InterpError(f"нет команды {head}")

    def _mem_line(self, s: str) -> ExecResult:
        rest = s.split(None, 1)
        if len(rest) == 1:
            return ExecResult(True, "mem")
        nums = []
        for tok in rest[1].replace(",", " ").split():
            try:
                nums.append(int(tok, 0))
            except ValueError:
                raise InterpError(f"mem: не число {tok!r}")
        for i, v in enumerate(nums):
            if i >= MEM_SIZE:
                break
            self.mem[i] = v
        return ExecResult(True, "mem", message=f"записано {len(nums)}")

    def _store_line(self, s: str) -> ExecResult:
        body = re.sub(r"^(store|st)\s+", "", s, flags=re.I).strip()
        if not body:
            raise InterpError("store что [куда]")
        # store x        → mem[0] = x  (или последний свободный)
        # store x 3      → mem[3] = x
        # store 9 3      → mem[3] = 9
        bits = body.rsplit(None, 1)
        if len(bits) == 2 and re.fullmatch(r"[-+]?\d+", bits[1]):
            val = self._eval(bits[0])
            addr = int(bits[1])
        else:
            val = self._eval(body)
            addr = 0
        if not 0 <= addr < MEM_SIZE:
            raise InterpError(f"адрес {addr} вне памяти 0..{MEM_SIZE - 1}")
        self.mem[addr] = val
        if self._last_node is not None:
            self._b.op("STORE", self._fresh(f"st{addr}"), self._last_node)
        self.last = val
        return ExecResult(True, "store", value=val, message=str(addr))

    def _kernel(self, kind: str, nraw: str | None) -> ExecResult:
        n = int(nraw) if nraw else KERNELS[kind.lower()][1]
        n = max(1, n)
        val = self._eval_kernel(kind.lower(), n)
        self.regs["_"] = val
        self.last = val
        dag = kernel(kind, n)
        self._b = _b(dag.key, dag.title, dag.lesson)
        self._b._instrs = [
            Instr(i, ins.name, ins.op, ins.preds, ins.text)
            for i, ins in enumerate(dag.instrs)
        ]
        self._ids = {ins.name: ins.id for ins in self._b._instrs}
        self._used_names = set(self._ids)
        self._last_node = None
        return ExecResult(True, "kernel", value=val, name=kind.lower(),
                          message=dag.title)

    def _eval_kernel(self, k: str, n: int) -> int:
        m = self.mem
        if k == "sum":
            return sum(m[:n])
        if k == "dot":
            return sum(m[i] * m[n + i] for i in range(n))
        if k == "saxpy":
            a = m[0]
            for i in range(n):
                m[n + 1 + i] = m[n + 1 + i] + a * m[1 + i]
            return m[n + n]
        if k == "addn":
            for i in range(n):
                m[2 * n + i] = m[i] + m[n + i]
            return m[2 * n + n - 1]
        if k == "copy":
            for i in range(n):
                m[n + i] = m[i]
            return m[n + n - 1]
        if k == "div":
            acc = m[0]
            for i in range(1, n + 1):
                d = m[i] or 1
                acc = acc // d
            return acc
        if k == "horner":
            x = m[0]
            acc = m[1]
            for i in range(2, n + 2):
                acc = acc * x + m[i]
            return acc
        if k == "fir":
            return sum(m[i] * m[n + i] for i in range(n))
        if k == "rms":
            s = sum(v * v for v in m[:n])
            return s // max(1, n)
        if k == "gemm":
            n = min(n, 3)
            # A в mem[0:n*n], B в mem[n*n:2n*n], C в 2n*n
            out = 0
            for i in range(n):
                for j in range(n):
                    acc = 0
                    for t in range(n):
                        acc += m[i * n + t] * m[n * n + t * n + j]
                    m[2 * n * n + i * n + j] = acc
                    out = acc
            return out
        if k == "chase":
            p = 0
            for _ in range(n):
                nxt = m[p] % MEM_SIZE
                p = nxt
            return p
        raise InterpError(_unknown_kernel(k))

    # --- вычисление и сборка графа ----------------------------------------
    #
    # Одна рекурсия делает обе вещи сразу: считает значение и кладёт в граф
    # ту операцию, которую машина действительно выполнила бы. Раньше это были
    # два независимых прохода — вычисление и отдельный разбор строки регулярным
    # выражением — и они расходились: `x=load 0` добавлял LOAD дважды (один раз
    # при вычислении, второй при разборе), а `t=x*a+b` не попадал в граф вовсе,
    # потому что регулярное выражение знало только про одну бинарную операцию.
    # Отсюда же берётся правило про константы: у числа нет узла, поэтому `a=10`
    # ничего в граф не кладёт, а `t=a*2` кладёт умножение с одним операндом.

    def _fresh(self, name: str) -> str:
        """Уникальное имя узла: одно имя в графе — одна операция."""
        if name not in self._used_names:
            self._used_names.add(name)
            return name
        k = 2
        while f"{name}.{k}" in self._used_names:
            k += 1
        self._used_names.add(f"{name}.{k}")
        return f"{name}.{k}"

    def _emit(self, op: str, a: int | None, b: int | None) -> int:
        preds = tuple(p for p in (a, b) if p is not None)
        return self._b.op(op, self._fresh(f"v{len(self._b._instrs)}"), *preds)

    def _rename(self, node: int, dest: str) -> None:
        """Дать узлу-результату имя, под которым его назвал человек."""
        ins = self._b._instrs[node]
        name = self._fresh(dest)
        text = ins.text.replace(ins.name, name, 1)
        self._b._instrs[node] = Instr(ins.id, name, ins.op, ins.preds, text)

    def _eval(self, s: str, dest: str | None = None) -> int:
        tokens = _tokenize(s)
        if not tokens:
            raise InterpError("пустое выражение")
        val, node, i = self._expr(tokens, 0)
        if i != len(tokens):
            raise InterpError(f"лишнее после выражения: {tokens[i][1]}")
        self._last_node = node
        if dest:
            if node is None:
                # имя стало просто числом — прежняя привязка к узлу неверна
                self._ids.pop(dest, None)
            else:
                self._rename(node, dest)
                self._ids[dest] = node
        return val

    def _expr(self, tok: list, i: int) -> tuple[int, int | None, int]:
        val, node, i = self._term(tok, i)
        while i < len(tok) and tok[i][1] in ("+", "-", "&", "<<"):
            op = tok[i][1]
            rhs, rnode, i = self._term(tok, i + 1)
            val = _apply(op, val, rhs)
            node = self._emit(_BIN[op], node, rnode)
        return val, node, i

    def _term(self, tok: list, i: int) -> tuple[int, int | None, int]:
        val, node, i = self._factor(tok, i)
        while i < len(tok) and tok[i][1] in ("*", "/"):
            op = tok[i][1]
            rhs, rnode, i = self._factor(tok, i + 1)
            val = _apply(op, val, rhs)
            node = self._emit(_BIN[op], node, rnode)
        return val, node, i

    def _factor(self, tok: list, i: int) -> tuple[int, int | None, int]:
        if i >= len(tok):
            raise InterpError("ожидал число, имя или load")
        kind, val = tok[i]
        if kind == "num":
            return int(val), None, i + 1
        if kind == "op" and val == "-":
            v, node, i = self._factor(tok, i + 1)
            return -v, node, i
        if kind == "id" and val.lower() in ("load", "ld"):
            return self._load_factor(tok, i + 1)
        if kind == "id":
            name = val
            if name not in self.regs:
                raise InterpError(f"нет имени {name}\n"
                                  + _did_you_mean(name, self.regs))
            return self.regs[name], self._ids.get(name), i + 1
        if kind == "op" and val == "(":
            v, node, i = self._expr(tok, i + 1)
            if i >= len(tok) or tok[i][1] != ")":
                raise InterpError("нет закрывающей )")
            return v, node, i + 1
        raise InterpError(f"не понял {val!r}")

    def _load_factor(self, tok: list, i: int) -> tuple[int, int | None, int]:
        if i < len(tok) and tok[i][0] == "num":
            addr = int(tok[i][1])
            i += 1
        else:
            addr = self._lp
            self._lp += 1
        if not 0 <= addr < MEM_SIZE:
            raise InterpError(f"load: адрес {addr} вне 0..{MEM_SIZE - 1}")
        node = self._b.op("LOAD", self._fresh(f"ld{addr}"))
        return self.mem[addr], node, i


def _apply(op: str, a: int, b: int) -> int:
    if op == "+":
        return a + b
    if op == "-":
        return a - b
    if op == "*":
        return a * b
    if op == "/":
        if b == 0:
            raise InterpError("деление на ноль")
        return a // b
    if op == "&":
        return a & b
    if op == "<<":
        return a << (b & 31)
    raise InterpError(f"нет операции {op}")


def _tokenize(s: str) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    i = 0
    n = len(s)
    while i < n:
        c = s[i]
        if c.isspace():
            i += 1
            continue
        if c == "<" and i + 1 < n and s[i + 1] == "<":
            out.append(("op", "<<"))
            i += 2
            continue
        if c in "+-*/&()=":
            out.append(("op", c))
            i += 1
            continue
        if c.isdigit() or (c == "-" and i + 1 < n and s[i + 1].isdigit()
                           and (not out or out[-1][0] == "op")):
            j = i + 1
            while j < n and s[j].isdigit():
                j += 1
            out.append(("num", s[i:j]))
            i = j
            continue
        if c.isalpha() or c == "_":
            j = i + 1
            while j < n and (s[j].isalnum() or s[j] == "_"):
                j += 1
            out.append(("id", s[i:j]))
            i = j
            continue
        raise InterpError(f"странный символ {c!r}")
    return out


def _tree(b: DagBuilder, ids: list[int], prefix: str) -> int:
    level = list(ids)
    k = 0
    while len(level) > 1:
        nxt = []
        for i in range(0, len(level) - 1, 2):
            nxt.append(b.op("ADD", f"{prefix}{k}", level[i], level[i + 1]))
            k += 1
        if len(level) % 2:
            nxt.append(level[-1])
        level = nxt
    return level[0]


def _b(key: str, title: str, lesson: str) -> DagBuilder:
    return DagBuilder(key, title, family="интерпретатор", lesson=lesson)


def kernel(kind: str, n: int | None) -> DAG:
    k = kind.lower()
    if k not in KERNELS:
        raise InterpError(_unknown_kernel(kind))
    default = KERNELS[k][1]
    n = default if n is None else max(2, n)

    if k == "sum":
        b = _b("sum", f"сумма {n} загрузок", f"sum {n}: загрузки и дерево сложений")
        r = _tree(b, [b.op("LOAD", f"v{i}") for i in range(n)], "s")
        b.op("STORE", "out", r)
        return b.build()

    if k == "dot":
        b = _b("dot", f"скалярное произведение {n}", f"dot {n}: load+load+mul, дерево")
        muls = []
        for i in range(n):
            a, c = b.op("LOAD", f"a{i}"), b.op("LOAD", f"b{i}")
            muls.append(b.op("MUL", f"p{i}", a, c))
        b.op("STORE", "out", _tree(b, muls, "s"))
        return b.build()

    if k == "saxpy":
        b = _b("saxpy", f"SAXPY ×{n}", f"saxpy {n}: запись только в двух каналах")
        for i in range(n):
            x, y = b.op("LOAD", f"x{i}"), b.op("LOAD", f"y{i}")
            t = b.op("MUL", f"t{i}", x)
            s = b.op("ADD", f"s{i}", y, t)
            b.op("STORE", f"o{i}", s)
        return b.build()

    if k == "chase":
        b = _b("chase", f"обход ×{n}", f"chase {n}: зависимые загрузки, lat 5")
        p = b.op("LOAD", "p0")
        for i in range(1, n):
            p = b.op("LOAD", f"p{i}", p)
        w = _tree(b, [b.op("ADD", f"w{i}") for i in range(4)], "u")
        b.op("STORE", "out", b.op("ADD", "r", p, w))
        return b.build()

    if k == "div":
        b = _b("divn", f"{n} делений", f"div {n}: очередь на порт ,5")
        b.op("STORE", "out", _tree(b, [b.op("DIV", f"d{i}") for i in range(n)], "s"))
        return b.build()

    if k == "gemm":
        n = min(n, 3)
        b = _b("gemm", f"матрица {n}×{n}", f"gemm {n}: независимые mul, свёртка по k")
        for i in range(n):
            for j in range(n):
                acc = None
                for kk in range(n):
                    a, c = b.op("LOAD", f"A{i}{kk}"), b.op("LOAD", f"B{kk}{j}")
                    m = b.op("MUL", f"m{i}{j}{kk}", a, c)
                    acc = m if acc is None else b.op("ADD", f"c{i}{j}{kk}", acc, m)
                b.op("STORE", f"C{i}{j}", acc)
        return b.build()

    if k == "horner":
        b = _b("horner", f"Горнер, степень {n}",
               f"horner {n}: каждое mul+add ждёт предыдущее, ILP=1")
        acc = b.op("LOAD", "c0")
        x = b.op("LOAD", "x")
        for i in range(1, n + 1):
            c = b.op("LOAD", f"c{i}")
            acc = b.op("MUL", f"m{i}", acc, x)
            acc = b.op("ADD", f"a{i}", acc, c)
        b.op("STORE", "out", acc)
        return b.build()

    if k == "fir":
        b = _b("fir", f"FIR окно {n}", f"fir {n}: независимые tap, потом свёртка")
        taps = []
        for i in range(n):
            x = b.op("LOAD", f"x{i}")
            h = b.op("LOAD", f"h{i}")
            taps.append(b.op("MUL", f"t{i}", x, h))
        b.op("STORE", "out", _tree(b, taps, "s"))
        return b.build()

    if k == "rms":
        b = _b("rms", f"RMS {n}", f"rms {n}: квадраты + одно деление")
        sq = []
        for i in range(n):
            v = b.op("LOAD", f"v{i}")
            sq.append(b.op("MUL", f"q{i}", v, v))
        s = _tree(b, sq, "s")
        b.op("STORE", "out", b.op("DIV", "inv", s))
        return b.build()

    if k == "copy":
        b = _b("copy", f"копирование {n}", f"copy {n}: load→store, 4 vs 2 канала")
        for i in range(n):
            v = b.op("LOAD", f"v{i}")
            b.op("STORE", f"o{i}", v)
        return b.build()

    if k == "addn":
        b = _b("addn", f"a[i]+b[i] ×{n}", f"addn {n}: две загрузки, сложение, запись")
        for i in range(n):
            a, c = b.op("LOAD", f"a{i}"), b.op("LOAD", f"b{i}")
            s = b.op("ADD", f"s{i}", a, c)
            b.op("STORE", f"o{i}", s)
        return b.build()

    raise InterpError(_unknown_kernel(kind))


def _unknown_kernel(kind: str) -> str:
    known = ", ".join(sorted(KERNELS))
    return f"нет ядра {kind!r}. есть: {known}"


def parse_ir(text: str) -> DAG:
    names: dict[str, int] = {}
    b = _b("ir", "заданная работа", "граф из записи интерпретатора")
    n_store = 0
    for raw in text.split(";"):
        line = raw.strip()
        if not line:
            continue
        sm = _STORE.match(line)
        if sm:
            src = sm.group(1)
            if src not in names:
                raise InterpError(f"store {src}: такого имени ещё нет")
            b.op("STORE", f"st{n_store}", names[src])
            n_store += 1
            continue
        m = _ASSIGN.match(line)
        if not m:
            raise InterpError(
                f"не разобрал «{line}». пример: a=load; b=load; t=a*b; store t")
        dest, left, op, right = m.group(1), m.group(2), m.group(3), m.group(4)
        if left.lower() in _UNARY and not op:
            names[dest] = b.op(_UNARY[left.lower()], dest)
            continue
        if op:
            if left not in names:
                raise InterpError(f"нет имени {left} (сначала {left}=load или …)")
            if right not in names:
                names[dest] = b.op(_BIN[op], dest, names[left])
            else:
                names[dest] = b.op(_BIN[op], dest, names[left], names[right])
            continue
        raise InterpError(f"не разобрал «{line}»")
    if not b._instrs:
        raise InterpError("пустая запись")
    return b.build()


def interpret(text: str) -> DAG:
    """Граф для планировщика. Для счёта — Workspace.exec."""
    s = text.strip()
    km = _KERNEL.match(s)
    if km:
        n = int(km.group(2)) if km.group(2) else None
        return kernel(km.group(1), n)
    ws = Workspace()
    try:
        ws.exec(s)
        if not ws.empty():
            return ws.snapshot()
    except InterpError:
        pass
    if looks_like_work(s):
        return parse_ir(s)
    raise InterpError("это не работа для машины")


def kernel_help() -> list[tuple[str, int, str]]:
    return [(name, default, hint) for name, (hint, default) in KERNELS.items()]
