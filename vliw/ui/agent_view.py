"""Agent dialogue formatting — same visual language as the other panes."""

from __future__ import annotations

import re

from . import render
from .render import Style, paint, wrap

_BOLD = re.compile(r"\*\*(.+?)\*\*")
_CODE = re.compile(r"`([^`]+)`")
_BULLET = re.compile(r"^\s*[-*]\s+")


def markup(text: str) -> str:
    text = _BOLD.sub(lambda m: paint("title", m.group(1)), text)
    text = _CODE.sub(lambda m: paint("mind", m.group(1)), text)
    return text


def question_line(text: str) -> list[str]:
    out = [paint("faint", "▌ ") + Style.dim("you")]
    out += wrap(text, render.W, "  ")
    return out


def _emit(line: str) -> None:
    print(line)


class AnswerPrinter:
    def __init__(self, indent: str = "  ") -> None:
        self.indent = indent
        self._buf = ""
        self._blank = True

    def feed(self, chunk: str) -> None:
        self._buf += chunk
        while "\n" in self._buf:
            line, self._buf = self._buf.split("\n", 1)
            self._line(line)

    def _line(self, line: str) -> None:
        if not line.strip():
            if not self._blank:
                _emit("")
                self._blank = True
            return
        self._blank = False
        body = _BULLET.sub("— ", line.strip())
        for l in wrap(markup(body), render.W, self.indent):
            _emit(l)

    def close(self) -> None:
        if self._buf.strip():
            self._line(self._buf)
        self._buf = ""


def stream_turn(agent, question: str) -> None:
    for l in question_line(question):
        _emit(l)
    _emit("")
    _emit(paint("accent", "▌ ") + paint("accent", "nex"))
    printer = AnswerPrinter(indent="  ")
    saw_text = False
    for kind, value in agent.ask_stream(question):
        if kind == "action":
            _emit(Style.dim(f"  · {value}"))
        elif kind == "error":
            _emit(paint("warning", f"  offline: {value[:120]}"))
            _emit("")
        elif kind == "text":
            if not saw_text:
                saw_text = True
                _emit("")
            printer.feed(value)
    printer.close()
    _emit("")


def _next_hint(detail: str) -> str:
    """Derive a concrete 'Next:' command from an error message.

    Order matters: provider mismatch hints (which already give the exact
    command) come before generic key/quota fallbacks.
    """
    low = detail.lower()
    if "OpenRouter" in detail:
        return "Next: /ai openrouter key=..."
    if "looks like a Gemini" in detail:
        return "Next: /ai gemini"
    if "does not look like a Gemini" in detail:
        return "Next: /ai mistral"
    if "GigaChat" in detail and "switch" in low:
        return "Next: /ai gigachat key=<id>:<secret>"
    if "paste again" in low:
        return "Next: /key <key>"
    if "set via:" in low or "api key not set" in low:
        return "Next: /key <key>"
    if "quota" in low:
        return "Next: /ai <other provider>"
    if "model not found" in low:
        return "Next: /ai — shows the active model"
    return ""


def render_status(ok: bool, detail: str) -> list[str]:
    from ..agent import llm

    out = [paint("mind", "* ") + paint("title", "language model")]
    if ok:
        out.append("  " + paint("success", "available") + Style.dim(f"   {detail}"))
    else:
        out.append("  " + paint("error", "unavailable") + Style.dim(f"   {detail[:160]}"))
        out += wrap(Style.dim(
            "the agent answers from precomputed numbers without free-form LLM prose."),
            render.W, "  ")
    out.append("")
    out.append("  " + Style.dim(f"model   {llm.describe()}"))
    if llm.is_local():
        out.append("  " + Style.dim("mode    local on this machine, offline, no key needed"))
        out.append("  " + Style.dim(
            "switch  /ai " + "|".join(p for p in llm.PROVIDERS if p != "local")
            + "  (key required)"))
    else:
        out.append("  " + Style.dim("key     /key <key>  (session-only, never stored on disk)"))
        try:
            from ..agent import envfile

            prov = llm.provider()
            if prov in llm.KEY_VAR:
                cur = llm.api_key()
                if cur:
                    out.append("  " + Style.dim(f"active  {envfile.mask(cur)}"))
        except Exception:
            pass
        out.append("  " + Style.dim(
            "switch  /ai " + "|".join(p for p in llm.PROVIDERS if p != "local")))
        out.append("  " + Style.dim("all-in-one /ai deepseek key=sk-... model=..."))
    if not ok:
        hint = _next_hint(detail)
        if hint:
            out.append("  " + paint("work", hint))
    out.append("")
    out += wrap(Style.dim(
        "all numbers come from the core. verify: doctor  ·  compare"), render.W, "  ")
    return out


def render_intro(width: int | None = None) -> list[str]:
    w = width or render.W
    out = [paint("mind", "NEX") + Style.dim("  — plain-English Q&A")]
    out.append("")
    for q in ("why is this block slow?",
              "where are cycles lost and what should change?",
              "load examples/probe.s and analyze it",
              "compare baseline against the exact oracle",
              "what is the exclusive port ,5?"):
        out += wrap(paint("mind_soft", "> ") + Style.dim(q), w, "")
    out.append("")
    out.append(Style.dim("/ai  ·  /ask  ·  /exit"))
    return out
