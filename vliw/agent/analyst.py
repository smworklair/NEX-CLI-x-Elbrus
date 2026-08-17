"""Типизированный агент: разбор системы по фиксированному контракту.

Отличие от чат-агента принципиальное, и оно архитектурное, а не косметическое:

  * тут НЕТ разговора и нет истории — каждый вызов независим;
  * ответ приходит не прозой, а СТРУКТУРОЙ по заданной схеме (вердикт,
    причина, план, риск, уверенность), поэтому его можно отрисовать таблицей,
    сравнить между запусками и сохранить в отчёт;
  * из-за схемы модель не тратит слова на вежливость и вступления —
    расход токенов в разы меньше, а ответ детерминированнее.

Числа по-прежнему считает ядро: сюда приходят готовые факты, а модель только
формулирует вывод и план. Если модель недоступна — собираем то же самое из
результатов `core.doctor`, просто без синтеза.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from . import context, llm

SCHEMA = {
    "type": "object",
    "properties": {
        "verdict": {"type": "string"},
        "root_cause": {"type": "string"},
        "plan": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "step": {"type": "string"},
                    "gain_cycles": {"type": "integer"},
                    "command": {"type": "string"},
                },
                "required": ["step", "gain_cycles"],
            },
        },
        "risk": {"type": "string"},
        "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
    },
    "required": ["verdict", "root_cause", "plan", "confidence"],
}

SYSTEM = """\
Ты — типизированный аналитический модуль NEX для VLIW-процессора Эльбрус (e2k).
Ты НЕ ведёшь диалог. Ты возвращаешь только структуру по схеме.

ПРАВИЛА:
1. Пиши ПО-РУССКИ. Все поля — на русском языке.
2. Числа бери ТОЛЬКО из блока ФАКТЫ. Ничего не выдумывай.
3. verdict — одна строка, суть: за сколько тактов идёт участок и что главное.
4. root_cause — корневая причина потерь. Если потерь нет — прямо скажи, что
   участок упирается в предел машины, и назови этот предел.
5. plan — конкретные шаги. gain_cycles — ожидаемый выигрыш в тактах, только
   если он следует из фактов; иначе 0. command — команда инструмента, если
   уместна (/compare, /doctor, /explain N, /asm).
6. risk — чего анализ НЕ учитывает (модель игрушечная: нет регистрового
   давления, спекуляции, предикатов, сложной памяти).
7. Никакой воды, вступлений и вежливости. Только по делу.
"""


@dataclass
class Step:
    step: str
    gain_cycles: int = 0
    command: str = ""


@dataclass
class Analysis:
    verdict: str = ""
    root_cause: str = ""
    plan: list[Step] = field(default_factory=list)
    risk: str = ""
    confidence: str = "low"
    offline: bool = False
    error: str = ""
    tokens: int = 0

    @property
    def total_gain(self) -> int:
        return sum(s.gain_cycles for s in self.plan)


def analyze(session) -> Analysis:
    """Разобрать текущий участок и вернуть структурный вывод."""
    # Факты обязаны быть посчитаны — иначе анализировать нечего.
    if session.peek() is None:
        session.results()
    facts = context.build(session, include_layout=True)
    prompt = (facts + "\n\nЗАДАЧА: выдай структурный разбор этого участка "
                      "по схеме. Только факты выше.")
    try:
        raw, used = _ask_structured(prompt)
    except llm.LLMError as e:
        a = _offline(session)
        a.offline, a.error = True, str(e)
        return a

    try:
        d = json.loads(raw)
    except ValueError:
        a = _offline(session)
        a.offline, a.error = True, "модель вернула не JSON"
        return a

    return Analysis(
        verdict=str(d.get("verdict", "")).strip(),
        root_cause=str(d.get("root_cause", "")).strip(),
        plan=[Step(str(s.get("step", "")).strip(),
                   int(s.get("gain_cycles", 0) or 0),
                   str(s.get("command", "")).strip())
              for s in d.get("plan", []) if isinstance(s, dict)],
        risk=str(d.get("risk", "")).strip(),
        confidence=str(d.get("confidence", "low")).strip(),
        tokens=used,
    )


def _ask_structured(prompt: str) -> tuple[str, int]:
    """Запрос со схемой ответа. Формат тела подбирает сам клиент по провайдеру."""
    return llm.structured(SYSTEM, prompt, SCHEMA)


def _offline(session) -> Analysis:
    """Тот же контракт, собранный из детерминированной диагностики."""
    from ..core.doctor import diagnose

    base, orc, met = session.peek()
    d = diagnose(session.dag_obj, session.model(), base.schedule, met)
    losses = [f for f in d.findings if f.recoverable]
    limits = [f for f in d.findings if not f.recoverable]
    b, o = base.schedule.makespan, orc.schedule.makespan

    a = Analysis(confidence="high")
    a.verdict = (f"{session.scenario}: {b} тактов, достижимо {o}, "
                 f"предел {met.lower_bound}.")
    if losses:
        f = losses[0]
        a.root_cause = f"{f.title}. {f.why}"
        a.plan.append(Step(f.fix, b - o, "/compare"))
    else:
        a.root_cause = ("Потерь из-за порядка выдачи нет: участок упирается в "
                        "предел машины.")
        if limits:
            a.root_cause += f" Ограничивает: {limits[0].title}."
    a.plan.append(Step("Посмотреть полную диагностику", 0, "/doctor"))
    a.risk = ("Модель машины игрушечная: нет регистрового давления, спекуляции, "
              "предикатов и сложной работы с памятью.")
    return a
