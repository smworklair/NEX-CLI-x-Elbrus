# -*- coding: utf-8 -*-
"""NNL (Neural Network Lego) — Слой 1: Материнская плата (Матплата).

Физическая инфраструктура и шина коммуникации:
  1. Слоты расширения: подключение (хот-плаг) и снятие блоков на ходу.
  2. Валидация паспортов: проверка обязательных полей, sha256 весов.
  3. Общая шина данных: хранилище понятий и значений.
  4. Контракт изоляции на такт:
     - Такт 1: каждый блок получает строго изолированный срез {} (Lego-индекс = 0.0000).
     - Такт 2: блок получает только подтверждённые понятия, на которые он подписан (читает).
  5. Происхождение значений на шине и конфликты. Понятие могут писать несколько блоков. Значения хранятся по источникам; если один источник говорит
     «да» (≥ +ПОРОГ_ЗНАКА), а другой «нет» (≤ −ПОРОГ_ЗНАКА), это конфликт: понятие НЕ попадает ни в один срез (читатель получает «никто не написал»),
     а запись о конфликте остаётся в `конфликты`. Прежде побеждал тот, кто писал последним, и ответ зависел от порядка блоков. Согласные источники
     не складываются (значение — наибольшее по модулю): согласие нескольких блоков не усиливает понятие, иначе влияние растёт с числом блоков.
"""
import hashlib
import importlib.util
import json
import os
import sys

ОБЯЗАТЕЛЬНО = ("имя", "версия", "архитектура", "веса", "пишет", "читает", "ответы")
ПОРОГ_ЗНАКА = 1.0        # значение на шине считается «да» при ≥ +порога и «нет» при ≤ −порога; между ними — слабый сигнал, не конфликт


def _sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _load_module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class Блок:
    """Универсальный дескриптор подключенного блока."""
    def __init__(self, папка, паспорт, arch, obj):
        self.папка = папка
        self.паспорт = паспорт
        self.arch = arch
        self.obj = obj
        self.имя = паспорт["имя"]
        self.роль = паспорт.get("роль", self.имя)
        self.пишет = list(паспорт.get("пишет", []))
        self.читает = list(паспорт.get("читает", []))
        self.ответы = list(паспорт.get("ответы", []))
        self.проекции = dict(паспорт.get("проекции", {}))
        self.чисел = arch.чисел(obj)


class Матплата:
    """Материнская плата NNL."""
    def __init__(self, язык, arch_dir):
        self.язык = язык
        self.arch_dir = os.path.abspath(arch_dir)
        self.блоки = {}
        self.шина = {}               # понятие → значение (только без конфликтов)
        self.конфликты = {}          # понятие → {источник: значение}: понятие, по которому источники противоречат друг другу
        self._записи = {}            # понятие → {источник: значение}
        self._arch_cache = {}

    def _архитектура(self, имя):
        if имя not in self._arch_cache:
            p = os.path.join(self.arch_dir, имя + ".py")
            if not os.path.exists(p):
                # Проверяем также в родительской папке архитектур
                alt_p = os.path.join(os.path.dirname(self.arch_dir), "архитектуры", имя + ".py")
                if os.path.exists(alt_p):
                    p = alt_p
                else:
                    raise ValueError(f"Нет кода архитектуры {имя!r} (искали в {p})")
            if os.path.dirname(p) not in sys.path:
                sys.path.insert(0, os.path.dirname(p))
            self._arch_cache[имя] = _load_module(p, f"nnl_arch_{имя}_{id(self)}")
        return self._arch_cache[имя]

    def проверить_паспорт(self, папка):
        pp = os.path.join(папка, "паспорт.json")
        if not os.path.exists(pp):
            return None, ["нет паспорт.json"]
        with open(pp, encoding="utf-8") as f:
            ps = json.load(f)
        errs = [f"в паспорте нет обязательного поля {k!r}" for k in ОБЯЗАТЕЛЬНО if k not in ps]
        if errs:
            return ps, errs
        wp = os.path.join(папка, ps["веса"].get("файл", ""))
        if not os.path.isfile(wp):
            errs.append(f"нет файла весов {ps['веса'].get('файл')!r}")
        elif _sha256_file(wp) != ps["веса"].get("sha256"):
            errs.append("файл весов не совпадает с паспортом (контрольная сумма sha256 нарушена)")
        return ps, errs

    def подключить(self, папка):
        ps, errs = self.проверить_паспорт(папка)
        if errs:
            return False, errs
        имя = ps["имя"]
        if имя in self.блоки:
            return False, [f"блок с именем {имя!r} уже подключён к матплате"]
        arch = self._архитектура(ps["архитектура"])
        obj = arch.загрузить(os.path.join(папка, ps["веса"]["файл"]), ps)
        b = Блок(папка, ps, arch, obj)
        self.блоки[имя] = b
        return True, имя

    def снять(self, имя):
        return self.блоки.pop(имя, None) is not None

    def очистить_шину(self):
        self.шина = {}
        self.конфликты = {}
        self._записи = {}

    def записать_на_шину(self, понятие, значение=1.0, источник=None):
        """Запись источника (имя блока) по понятию. Один источник пишет значение один раз (повторная запись заменяет), без источника — как раньше."""
        self._записи.setdefault(понятие, {})[источник] = float(значение)
        значения = list(self._записи[понятие].values())
        if any(v >= ПОРОГ_ЗНАКА for v in значения) and any(v <= -ПОРОГ_ЗНАКА for v in значения):
            self.шина.pop(понятие, None)
            self.конфликты[понятие] = dict(self._записи[понятие])
        else:
            self.конфликты.pop(понятие, None)
            self.шина[понятие] = max(значения, key=abs)

    def пространства(self):
        """Пространства имён понятий (часть до «:»), объявленные в паспортах подключённых блоков: `пишет`, `читает` и `проекции`."""
        res = set()
        for b in self.блоки.values():
            понятия = list(b.пишет) + list(b.читает) + [k for п in b.проекции.values() for k in п]
            res.update(k.split(":", 1)[0] for k in понятия if ":" in k)
        return res

    def срез_шины(self, имя_блока, такт=1):
        """Контракт изоляции на такт:
        такт=1: строго пустой срез {} (изоляция от соседей -> Lego-индекс = 0.0000).
        такт=2: только понятия, на которые блок подписан (читает). Поддерживает префиксы.
        """
        if такт == 1:
            return {}
        b = self.блоки.get(имя_блока)
        if not b:
            return {}
        res = {}
        for k, v in self.шина.items():
            if k in b.читает or any(k.startswith(pat + ":") for pat in b.читает):
                res[k] = v
        return res
