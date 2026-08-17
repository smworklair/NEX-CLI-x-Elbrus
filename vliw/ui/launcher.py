"""Экран выбора режима: ядро / разбор / агент."""

from __future__ import annotations

from . import render
from .render import Style, paint, vlen

PANELS = [
    {
        "id": "work",
        "key": "1",
        "title": "ЯДРО",
        "subtitle": "интерпретатор",
        "role": "work",
        "lines": [
            "sum 8   ·   saxpy 8   ·   fir 8",
            "a=load; t=a*2; store t",
        ],
    },
    {
        "id": "lab",
        "key": "2",
        "title": "РАЗБОР",
        "subtitle": "исследование",
        "role": "lab",
        "lines": [
            "/run slotclash   /compare   /doctor",
            "/load examples/probe.s",
        ],
    },
    {
        "id": "mind",
        "key": "3",
        "title": "АГЕНТ",
        "subtitle": "диалог",
        "role": "mind",
        "lines": [
            "почему этот участок медленный?",
            "загрузи probe.s и разбери",
        ],
    },
]

APPS = PANELS


def card(app: dict, selected: bool, width: int) -> list[str]:
    role = app["role"]
    inner = max(36, min(width - 8, 56))
    hz = "─" * inner
    if selected:
        top = paint(role, "┌" + hz + "┐")
        bot = paint(role, "└" + hz + "┘")
        edge = paint(role, "│")
        key = paint(role, f" {app['key']} ")
        title = paint(role, app["title"])
        sub = paint(role, app["subtitle"])
    else:
        top = Style.dim("┌" + hz + "┐")
        bot = Style.dim("└" + hz + "┘")
        edge = Style.dim("│")
        key = Style.dim(f" {app['key']} ")
        title = paint("title", app["title"])
        sub = Style.dim(app["subtitle"])

    def row(body: str) -> str:
        pad = max(0, inner - vlen(body))
        return edge + body + (" " * pad) + edge

    out = [
        "  " + top,
        "  " + row(key + title + "  " + sub),
        "  " + row(" " * inner),
    ]
    for line in app["lines"]:
        out.append("  " + row("   " + Style.dim(line)))
    out.append("  " + bot)
    return out


def render_choice(selected: int = 0, width: int | None = None) -> list[str]:
    w = width or render.W
    out: list[str] = []
    for i, app in enumerate(PANELS):
        out += card(app, i == selected, w)
        out.append("")
    out.append("  " + Style.dim("1 / 2 / 3 выбрать    ↑↓ Enter    q выход    /clear — сюда"))
    return out


def prompt_plain() -> str:
    print()
    for line in render_choice(selected=1):
        print(line)
    print()
    while True:
        try:
            ans = input(paint("prompt", "  nex ") + Style.dim("▸ ")).strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            return ""
        if ans in ("1", "work", "ядро", "core"):
            return "work"
        if ans in ("2", "", "lab", "разбор", "explore"):
            return "lab"
        if ans in ("3", "mind", "агент", "chat", "agent"):
            return "mind"
        if ans in ("q", "quit", "exit"):
            return ""
        print(Style.dim("  наберите 1, 2 или 3"))
