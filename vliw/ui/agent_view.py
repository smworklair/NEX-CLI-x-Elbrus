"""Оформление диалога с агентом — тот же язык, что у остальных панелей."""

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
    out = [paint("faint", "▌ ") + Style.dim("вы")]
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
            _emit(paint("warning", f"  без модели: {value[:120]}"))
            _emit("")
        elif kind == "text":
            if not saw_text:
                saw_text = True
                _emit("")
            printer.feed(value)
    printer.close()
    _emit("")


def _next_hint(detail: str) -> str:
    """Следующий шаг из текста ошибки — той же строкой «Дальше:», что у агента.

    Порядок важен: сначала «ключ не от этого провайдера» (там уже есть
    точная команда), потом общие случаи. Иначе при чужом ключе советовали
    бы вставить его заново в тот же провайдер — бессмысленно.
    """
    if "OpenRouter" in detail:
        return "Дальше: /ai openrouter key=..."
    if "похож на Gemini" in detail:
        return "Дальше: /ai gemini"
    if "не похож на Gemini" in detail:
        return "Дальше: /ai mistral"
    if "GigaChat" in detail and "переключите" in detail:
        return "Дальше: /ai gigachat key=<id>:<secret>"
    if "вставьте заново" in detail:
        return "Дальше: /key <ключ>"
    if "вставьте:" in detail or "вставьте :" in detail or "вставьте" in detail:
        return "Дальше: /key <ключ>"
    if "квота" in detail:
        return "Дальше: /ai <другой провайдер>"
    if "модель не найдена" in detail:
        return "Дальше: /ai — там видно текущую модель"
    return ""


def render_status(ok: bool, detail: str) -> list[str]:
    from ..agent import llm

    out = [paint("mind", "◆ ") + paint("title", "языковая модель")]
    if ok:
        out.append("  " + paint("success", "доступна") + Style.dim(f"   {detail}"))
    else:
        out.append("  " + paint("error", "не работает") + Style.dim(f"   {detail[:160]}"))
        out += wrap(Style.dim(
            "агент отвечает по уже посчитанным числам, без свободной формулировки."),
            render.W, "  ")
    out.append("")
    out.append("  " + Style.dim(f"модель  {llm.describe()}"))
    if llm.is_local():
        # В локальном режиме строка про ключ была бы враньём: ключ не нужен,
        # в сеть агент не ходит вовсе.
        out.append("  " + Style.dim("где     на этой машине, без сети и без ключа"))
        out.append("  " + Style.dim(
            "смена   /ai " + "|".join(p for p in llm.PROVIDERS if p != "local")
            + "  (нужен ключ)"))
    else:
        out.append("  " + Style.dim("ключ    /key <ключ>  (только на сессию, нигде не хранится)"))
        try:
            # Что реально сохранено (маской): склеенный дважды ключ виден
            # сразу по длине, не дожидаясь 401 от сервера.
            from ..agent import envfile

            prov = llm.provider()
            if prov in llm.KEY_VAR:
                cur = llm.api_key()
                if cur:
                    out.append("  " + Style.dim(f"сейчас  {envfile.mask(cur)}"))
        except Exception:
            pass
        out.append("  " + Style.dim(
            "смена   /ai " + "|".join(p for p in llm.PROVIDERS if p != "local")))
        out.append("  " + Style.dim("всё сразу  /ai deepseek key=sk-... model=..."))
    if not ok:
        hint = _next_hint(detail)
        if hint:
            out.append("  " + paint("work", hint))
    out.append("")
    out += wrap(Style.dim(
        "числа считает ядро. перепроверить: doctor  ·  compare"), render.W, "  ")
    return out


def render_intro(width: int | None = None) -> list[str]:
    w = width or render.W
    out = [paint("mind", "NEX") + Style.dim("  — обычным языком")]
    out.append("")
    for q in ("почему этот участок медленный?",
              "где теряются такты и что менять?",
              "загрузи examples/probe.s и разбери",
              "сравни baseline с точным поиском",
              "что за монопольный порт ,5?"):
        out += wrap(paint("mind_soft", "› ") + Style.dim(q), w, "")
    out.append("")
    out.append(Style.dim("/ai  ·  /ask  ·  /exit"))
    return out
