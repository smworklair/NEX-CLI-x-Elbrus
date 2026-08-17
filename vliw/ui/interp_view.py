"""Вывод интерпретатора: сначала число, потом имена."""

from __future__ import annotations

from . import render
from .render import Style, paint, wrap


def render_welcome(width: int = 72) -> list[str]:
    w = max(20, width)
    out = [
        paint("accent", "NEX CLI") + Style.dim("  ·  интерпретатор"),
        Style.dim("считает здесь. память с начала: 1 2 3 4 …"),
        "",
        paint("accent", "считайте"),
        Style.dim("  2+2"),
        Style.dim("  a=10"),
        Style.dim("  b=3"),
        Style.dim("  a*b+1"),
        "",
        paint("accent", "память"),
        Style.dim("  x=load 0          взять mem[0]"),
        Style.dim("  store a 3         mem[3]=a"),
        Style.dim("  mem 10 20 30      заполнить с нуля"),
        "",
        paint("accent", "ядра") + Style.dim("   sum 8   dot 4   saxpy 8   fir 8"),
        Style.dim("  считают по памяти, печатают число"),
        "",
        paint("accent", "ещё") + Style.dim("   names   mem   reset   go"),
    ]
    _ = w
    return out


def render_result(ws, result, width: int = 72) -> list[str]:
    w = max(20, width)
    out: list[str] = []

    if result.kind == "reset":
        out.append(Style.dim(result.message or "сброс"))
        return out

    if result.kind == "env":
        if not ws.regs:
            out.append(Style.dim("имён нет"))
            return out
        out.append(paint("accent", "имена"))
        for n, v in ws.regs.items():
            out.append(f"  {paint('title', n):<16} {paint('accent', str(v))}")
        return out

    if result.kind == "mem":
        if result.message:
            out.append(Style.dim(result.message))
        out += _mem(ws, w)
        return out

    if result.kind == "go":
        out.append(paint("accent2", "go") + Style.dim("  → разбор"))
        if result.value is not None:
            out.append(paint("accent", f"= {result.value}"))
        return out

    if result.kind == "list":
        out += _listing(ws)
        return out

    if result.value is not None:
        if result.kind == "assign":
            out.append(paint("title", result.name) + "  "
                       + paint("accent", f"= {result.value}"))
        elif result.kind == "store":
            out.append(paint("accent", f"mem[{result.message}]")
                       + f"  = {result.value}")
        elif result.kind == "kernel":
            out.append(paint("accent", result.name or "ядро")
                       + Style.dim(f"  {result.message}"))
            out.append(paint("title", f"= {result.value}"))
        else:
            out.append(paint("title", f"= {result.value}"))
        return out

    return out or [Style.dim("ok")]


def _mem(ws, width: int) -> list[str]:
    out = [paint("accent", "mem") + Style.dim(f"  {len(ws.mem)} ячеек, с 1")]
    row: list[str] = []
    line_w = 0
    for i, v in enumerate(ws.mem[:32]):
        cell = f"{i}:{v}"
        if line_w and line_w + len(cell) + 2 > max(24, width - 2):
            out.append("  " + Style.dim("  ".join(row)))
            row, line_w = [], 0
        row.append(cell)
        line_w += len(cell) + 2
    if row:
        out.append("  " + Style.dim("  ".join(row)))
    return out


def _listing(ws) -> list[str]:
    dag = ws.snapshot()
    if not dag.instrs:
        return [Style.dim("графа нет — считали без записи в программу")]
    out = [paint("accent", "граф") + Style.dim(f"   {len(dag)} оп.")]
    for ins in dag:
        out.append(f"  {paint('title', f'{ins.name:<8}')} "
                   + Style.dim(ins.text))
    return out
