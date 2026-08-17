"""Логика прототипа: модель машины, граф, планировщики, метрики, проверка.

Здесь НЕТ ничего про вывод: ни цвета, ни таблиц, ни print(). Всё это —
структуры данных и алгоритмы. Форматированием занимается пакет `vliw.ui`,
склейкой — `vliw.cli`. Такое разделение позволяет подставить будущую обученную
модель (`vliw.learned`) без правок в отрисовке и CLI.
"""

from .api import Candidate, DecisionStep, Scheduler, SchedulingResult
from .baseline import GreedyListScheduler, list_schedule
from .dag import (
    DAG,
    SCENARIOS,
    DagBuilder,
    DagMetrics,
    Instr,
    compute_metrics,
    get_scenario,
    random_dag,
)
from .interp import (
    ExecResult,
    InterpError,
    Workspace,
    interpret,
    kernel_help,
    looks_like_work,
)
from .model import (
    ASSUMED,
    DEFAULT_PROFILE,
    MEASURED,
    PROBED,
    PROFILES,
    MachineModel,
    OpClass,
    Port,
    capability_matrix,
    describe_model,
    get_profile,
)
from .oracle import OracleScheduler
from .schedule import ChannelState, Placement, Schedule
from .selfcheck import SelfcheckResult, brute_force_makespan, run_selfcheck

__all__ = [
    "Candidate",
    "DecisionStep",
    "Scheduler",
    "SchedulingResult",
    "GreedyListScheduler",
    "list_schedule",
    "OracleScheduler",
    "DAG",
    "Instr",
    "DagMetrics",
    "DagBuilder",
    "SCENARIOS",
    "compute_metrics",
    "get_scenario",
    "random_dag",
    "interpret",
    "looks_like_work",
    "InterpError",
    "Workspace",
    "ExecResult",
    "kernel_help",
    "MachineModel",
    "Port",
    "OpClass",
    "PROFILES",
    "DEFAULT_PROFILE",
    "get_profile",
    "describe_model",
    "capability_matrix",
    "MEASURED",
    "PROBED",
    "ASSUMED",
    "Schedule",
    "Placement",
    "ChannelState",
    "run_selfcheck",
    "brute_force_makespan",
    "SelfcheckResult",
]
