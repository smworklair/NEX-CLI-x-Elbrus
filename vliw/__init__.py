"""Прототип ИИ-планировщика инструкций для VLIW (калибровка по e2k-v6).

Пакеты:
  vliw.core     — логика (модель, граф, планировщики, метрики, проверка)
  vliw.ui       — визуализация (цвет, рамки, таблицы, логотип)
  vliw.learned  — каркас под будущую обученную модель (пока заглушка)
  vliw.cli      — единая точка входа: команда → core → ui → печать

Публичный API проекта — из vliw.core (переэкспортируется здесь для удобства).
"""

# Две записи одной и той же версии намеренно. `__version__` — машинная, по
# PEP 440, чтобы её понимали упаковщики и сравнивали как версию. `VERSION_LABEL`
# — человеческая, для баннера и подписей: «0.8.0a1» в шапке читается как
# опечатка, а «0.8 alpha» сразу говорит, что инструмент ещё не устоялся.
#
# 0.7 — три полноэкранных режима на Textual.
# 0.8 — редизайн командного слоя: команды сгруппированы по занятию (справка,
# палитра «/» и --help показывают разделы, «/help <команда>» рассказывает
# об одной), легаси-экран на curses удалён — полноэкранный только Textual,
# при проблемах откат в построчный режим. Альфа: раскладки ещё будут меняться.
__version__ = "0.8.0a1"
VERSION_LABEL = "0.8 alpha"

from .core import (
    DAG,
    DEFAULT_PROFILE,
    PROFILES,
    SCENARIOS,
    Candidate,
    DecisionStep,
    GreedyListScheduler,
    MachineModel,
    OracleScheduler,
    Schedule,
    Scheduler,
    SchedulingResult,
    compute_metrics,
    get_profile,
    get_scenario,
    list_schedule,
    random_dag,
)

__all__ = [
    "Candidate",
    "DecisionStep",
    "Scheduler",
    "SchedulingResult",
    "GreedyListScheduler",
    "list_schedule",
    "DAG",
    "SCENARIOS",
    "compute_metrics",
    "get_scenario",
    "random_dag",
    "DEFAULT_PROFILE",
    "PROFILES",
    "MachineModel",
    "get_profile",
    "OracleScheduler",
    "Schedule",
]
