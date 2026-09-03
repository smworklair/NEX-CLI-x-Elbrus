"""Агент: понимает вопрос на обычном языке, сам смотрит данные, отвечает.

Схема одного хода:

    вопрос → (1) распознать действие → (2) выполнить его ядром →
    (3) собрать ФАКТЫ → (4) языковая модель объясняет → ответ + следующий шаг

Пункты 1–3 детерминированные: файлы грузит парсер, расписание считает точный
поиск, потери находит `core.doctor`. Языковая модель отвечает только за
формулировку и рассуждение поверх готовых чисел — поэтому ответ можно
перепроверить командой и он не «плывёт» от запуска к запуску.

Если сети нет или ключ не принят, агент не ломается: он отвечает офлайн,
опираясь на те же факты, просто без свободной формулировки.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from . import context, llm

# --- распознавание действий ------------------------------------------------
# Не «понимание языка вообще», а узкий набор намерений предметной области.
# Работает и без сети, и служит подсказкой для модели.

_ACTIONS = [
    ("load",     r"(загруз|открой|прочит|разбер|load)\w*\s+([\w./\\-]+\.s)\b"),
    ("scenario", r"(прогони|запусти|покажи|возьми|run)\w*\s+(\w+)"),
    ("doctor",   r"(диагност|что не так|где теря|почему медлен|проблем|доктор|потер)"),
    ("compare",  r"(сравн|разниц|baseline\s*(vs|против)|оракул\w*\s+против)"),
    ("bounds",   r"(предел|нижн\w*\s+границ|быстрее\s+нельзя|теоретическ)"),
    ("path",     r"(критическ\w*\s+пут|critical\s*path)"),
    ("asm",      r"(широк\w*\s+команд|\.s\b|ассемблер|asm|как\s+в\s+lcc)"),
    ("model",    r"(модель\s+машин|порт\w*|матриц\w*\s+возможн|монопол)"),
    ("explain",  r"(такт\w*\s+(\d+)|в\s+такте\s+(\d+))"),
]

# Ключи сценариев берём из самого реестра, чтобы новые (seqreduce, divstrength,
# unroll4 …) распознавались в вопросах без правки этого файла.
def _scenario_hint() -> re.Pattern:
    from ..core import SCENARIOS

    keys = sorted(SCENARIOS, key=len, reverse=True)
    return re.compile(r"\b(" + "|".join(map(re.escape, keys)) + r"|rand\d+)\b", re.I)


_SCENARIO_HINT = _scenario_hint()

#: Реплики не по делу. Список шире приветствий намеренно: «спасибо» и «ок»
#: получали такой же нелепый хвост «Дальше: /explain 13», потому что под
#: правило приветствия не подпадали, а системный промпт требует заканчивать
#: командой. Проверять в благодарности нечего ровно так же, как в «привет».
_SMALLTALK = re.compile(
    r"^(привет|прив|здравствуй(те)?|хай|hello|hi|hey|"
    r"добр(ый|ого)\s+(день|вечер|утро)|йоу|"
    r"спасибо|спс|благодарю|thanks|thank\s+you|"
    r"пока|до\s+свидания|бывай|bye|"
    r"ок|окей|ok|okay|ясно|понял|понятно|угу|ага|"
    r"как\s+дела|что\s+умеешь|кто\s+ты)[\s!.?)]*$",
    re.I,
)


def _is_smalltalk(q: str) -> bool:
    return bool(_SMALLTALK.match(q.strip()))


#: Вопросы НЕ про участок, а про сам ответ: «уверен?», «точно?», «не врёшь?».
_DOUBT = re.compile(
    r"^(а\s+)?(ты\s+)?(точно|уверен[аы]?|правда|серьёзно|не\s+врёшь|"
    r"не\s+ошиб(аешься|ся)|проверь|перепроверь|откуда|почему\s+так\s+решил)"
    r"[\s!?.]*$",
    re.I,
)


def _is_doubt(q: str) -> bool:
    """Сомнение в предыдущем ответе.

    Отдельная ветка нужна потому, что системный промпт целиком построен на
    «отвечай по ФАКТАМ участка», а у вопроса «уверен?» предмет другой — не
    участок, а происхождение уже сказанного. Модели на 3B ответить нечем, и
    она хватается за единственное разрешённое ей окончание: выдаёт голую
    строку «Дальше: /compare» и всё. Воспроизводится стабильно.

    Замалчивать этот вопрос — худшее, что можно сделать именно в ЭТОМ
    проекте: вся его дисциплина стоит на «у каждого числа проставлен
    источник». Человек, спрашивающий «уверен?», задаёт самый уместный
    вопрос из возможных, и ответ на него у инструмента есть — надо только
    достать его из того же места, где лежат источники чисел.
    """
    return bool(_DOUBT.match(q.strip()))


@dataclass
class Turn:
    question: str
    answer: str = ""
    actions: list[str] = field(default_factory=list)
    offline: bool = False
    error: str = ""


@dataclass
class Agent:
    """Диалоговая сессия поверх текущего состояния исследования."""

    session: object
    history: list[Turn] = field(default_factory=list)
    last_error: str = ""

    # --- действия ---------------------------------------------------------

    def _detect(self, q: str) -> list[tuple[str, str]]:
        ql = q.lower()
        found: list[tuple[str, str]] = []
        m = re.search(_ACTIONS[0][1], ql)
        if m:
            found.append(("load", m.group(2)))
        sc = _SCENARIO_HINT.search(q)
        if sc:
            found.append(("scenario", sc.group(1).lower()))
        for name, pat in _ACTIONS[2:]:
            if re.search(pat, ql):
                found.append((name, ""))
        return found

    def _run_actions(self, q: str) -> list[str]:
        """Выполнить то, что вытекает из вопроса, ДО обращения к модели."""
        from ..core import asm_parser, get_scenario

        done: list[str] = []
        for kind, arg in self._detect(q):
            try:
                if kind == "load" and arg:
                    parsed = asm_parser.parse_file(arg)
                    if parsed.ops:
                        dag = asm_parser.build_dag(parsed, key=f"asm:{arg}", title=arg)
                        self.session.set_dag(dag, f"asm:{arg.split('/')[-1]}")
                        done.append(f"разобрал {arg}: {len(parsed.ops)} операций, "
                                    f"{parsed.bundles} широких команд")
                elif kind == "scenario" and arg:
                    self.session.set_scenario(arg)
                    done.append(f"переключился на сценарий {arg}")
            except Exception as e:
                done.append(f"не смог выполнить {kind} {arg}: {e}")
        # Приветствие не требует расписания — иначе «привет» гоняет оракул.
        if _is_smalltalk(q):
            return done
        # Любой содержательный вопрос требует посчитанного расписания.
        if self.session.peek() is None:
            try:
                self.session.results()
                done.append("посчитал расписание (baseline и точный поиск)")
            except Exception as e:
                done.append(f"не смог посчитать расписание: {e}")
        return done

    # --- ответ -------------------------------------------------------------

    def _needs_layout(self, q: str) -> bool:
        """Раскладку в факты — всегда, если расписание уже посчитано.

        Раньше здесь стоял отбор по словам («такт|расписан|разлож|порядок|
        когда|выдал»), и это был источник выдуманных чисел: вопрос «на каком
        КАНАЛЕ стоит z0?» под шаблон не подходил, раскладка в факты не
        попадала — а ответить модель всё равно пыталась. Взять такт и канал ей
        было неоткуда, кроме как из головы. Тот же провал у «где размещена g1»,
        «в какой широкой команде идёт m0», «почему dc позже».

        Дописывать слова в шаблон бессмысленно: список формулировок открыт, а
        цена промаха — уверенно названное неверное число. Раскладка стоит
        десяток строк, поэтому она просто идёт всегда. Единственное условие —
        чтобы её было откуда взять.
        """
        return self.session.peek() is not None

    def _history_pairs(self, limit: int = 6) -> list[tuple[str, str]]:
        pairs: list[tuple[str, str]] = []
        for t in self.history[-limit:]:
            if t.answer:
                pairs.append(("user", t.question))
                pairs.append(("model", t.answer))
        return pairs

    def ask_stream(self, question: str,
                   panel: tuple[str, list[str]] | None = None):
        """Ответ по частям. Отдаёт кортежи ('action'|'text'|'error', значение).

        `panel` — (заголовок, факты) открытой панели, если спрашивают ИЗ
        всплывающей строки конкретной панели, а не из общего диалога АГЕНТА.
        Это НЕ отдельный урезанный режим: действия (переключить сценарий,
        загрузить файл, посчитать расписание) выполняются те же самые — то
        есть спросить «переключись на wide_ilp и сравни» можно из всплывающей
        строки МАШИНЫ в РАЗБОРЕ точно так же, как из ДИАЛОГА в АГЕНТЕ.
        `panel` лишь сужает, о чём говорить в ответе, и идёт суффиксом
        промпта (см. `context.system_prompt`), не ломая кэш префикса.
        """
        turn = Turn(question=question)
        self.history.append(turn)

        for note in self._run_actions(question):
            turn.actions.append(note)
            yield ("action", note)

        # «Уверен?» — вопрос не про участок, а про происхождение сказанного.
        # Отвечаем сами и точно: у инструмента ЕСТЬ этот ответ, потому что
        # он всюду хранит источник каждого числа. Отдавать такой вопрос
        # модели на 3B значит получить голое «Дальше: /compare».
        if _is_doubt(question) and self.history[:-1]:
            answer = self._provenance()
            turn.answer = answer
            yield ("text", answer)
            return

        small = _is_smalltalk(question)
        system = context.system_prompt(self.session, self._needs_layout(question),
                                       panel=panel, smalltalk=small)
        chunks: list[str] = []
        try:
            for piece in llm.stream(system, question, self._history_pairs(),
                                    nudge=not small):
                chunks.append(piece)
                yield ("text", piece)
            turn.answer = "".join(chunks).strip()
            if not turn.answer:
                raise llm.LLMError("пустой ответ модели")
        except llm.LLMError as e:
            turn.offline = True
            turn.error = str(e)
            self.last_error = str(e)
            fallback = self.offline_answer(question)
            turn.answer = fallback
            yield ("error", str(e))
            yield ("text", fallback)

    def _provenance(self) -> str:
        """Откуда взялись числа предыдущего ответа — по-честному, с оговорками.

        Это самый уместный вопрос, который можно задать этому инструменту, и
        единственный, на который он отвечает ЛУЧШЕ любой модели: происхождение
        каждого числа у него записано.
        """
        got = self.session.peek()
        lines: list[str] = []
        if not got:
            return ("Расписание ещё не считалось — проверять нечего. "
                    "Посчитайте: /run или F5.\n\nДальше: /run")

        # peek() отдаёт (baseline, оракул, метрики): нас интересует оракул —
        # именно он что-то ДОКАЗЫВАЕТ, у жадного доказывать нечего.
        _base, orc, _met = got
        proven = getattr(orc, "optimal", None)
        stats = getattr(orc, "search_stats", {}) or {}
        makespan = orc.schedule.makespan

        if proven:
            lines.append(
                f"Да, в той части, которую можно доказать. {makespan} тактов — "
                "это ДОКАЗАННЫЙ оптимум: точный поиск перебрал все более "
                "короткие расписания и показал, что их не существует.")
            if stats.get("nodes"):
                lines.append(f"Разобрано узлов перебора: {stats['nodes']}.")
        else:
            lb = stats.get("lower_bound")
            lines.append(
                f"Не полностью. {makespan} тактов — лучшее НАЙДЕННОЕ, а не "
                "доказанное: точный поиск не уложился в бюджет."
                + (f" Доказано лишь, что короче {lb} тактов не бывает."
                   if lb else ""))

        # Главная оговорка проекта: модель машины проще настоящей.
        lines.append(
            "Но всё это — относительно МОДЕЛИ машины, а она заведомо проще "
            "настоящей: в ней нет зависимостей через память, межкластерных "
            "задержек и штрафа на передачу между целочисленными и "
            "вещественными операциями.")

        try:
            from ..core.isa import collect
            rows = collect(self.session.model())
            guessed = [r.name for r in rows if not r.latency_measured]
            if guessed:
                lines.append(
                    f"Латентность измерена у {len(rows) - len(guessed)} классов "
                    f"из {len(rows)}; у остальных стоит допущение "
                    f"({', '.join(guessed[:5])}"
                    + ("…" if len(guessed) > 5 else "") + ").")
        except Exception:
            pass

        lines.append("Перепроверить: /isa — источник у каждого числа, "
                     "/selfcheck — сверка оракула независимым перебором.")
        return "\n".join(lines) + "\n\nДальше: /isa"

    def ask(self, question: str) -> Turn:
        """Ответ целиком (для разового вызова из скрипта)."""
        turn = Turn(question=question)
        self.history.append(turn)
        turn.actions = self._run_actions(question)
        system = context.system_prompt(self.session, self._needs_layout(question))
        try:
            turn.answer = llm.complete(system, question, self._history_pairs(),
                                       nudge=not _is_smalltalk(question))
        except llm.LLMError as e:
            turn.offline = True
            turn.error = str(e)
            turn.answer = self.offline_answer(question)
        return turn

    # --- офлайновый запасной ответ ----------------------------------------

    def offline_answer(self, question: str) -> str:
        """Ответ без сети: те же факты, только без свободной формулировки."""
        from ..core.doctor import diagnose

        if _is_smalltalk(question):
            return ("Модель сейчас недоступна. Наберите /ai — там видно, "
                    "какой ключ отвечает, и повторите вопрос.")

        s = self.session
        cached = s.peek()
        lines = ["Модель недоступна — отвечаю по посчитанным данным."]
        if cached is None:
            lines.append("Расписание ещё не считалось: наберите /run.")
            return "\n".join(lines)

        base, orc, met = cached
        b, o = base.schedule.makespan, orc.schedule.makespan
        lines.append(f"Участок {s.scenario}: baseline {b} т., точный поиск {o} т., "
                     f"предел {met.lower_bound} т.")
        try:
            d = diagnose(s.dag_obj, s.model(), base.schedule, met)
            losses = [f for f in d.findings if f.recoverable]
            if losses:
                f = losses[0]
                lines.append(f"Главная потеря: −{f.cycles_lost} т. — {f.title}.")
                lines.append(f"Почему: {f.why}")
                lines.append(f"Решение: {f.fix}")
            else:
                lines.append("Потерь из-за порядка выдачи нет — упирается в предел машины.")
        except Exception:
            pass
        lines.append("Дальше: /doctor — полный разбор.")
        return "\n".join(lines)


def status() -> tuple[bool, str]:
    return llm.check()
