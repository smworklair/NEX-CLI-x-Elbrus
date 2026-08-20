"""Постоянный llama-server: веса грузятся один раз за сессию, а не на команду.

ЗАЧЕМ. Прежний путь (`LlamaCppBackend`) поднимал `llama-completion` заново на
каждый запрос: 2.1 ГБ весов читались с диска, прогревался контекст, и только
потом шла генерация. Измерено на `slotclash`, адаптер `lora-eos`:

    подпроцесс на команду   32 с,   первый токен через ~20 с
    постоянный сервер       14 с,   первый токен через 2.6 с (холодный)
                            14 с,   первый токен через 0.11 с (тёплый кэш)

Ответ при этом совпадает до строки — это тот же llama.cpp и те же веса, просто
процесс не умирает между запросами.

ПОЧЕМУ UNIX-СОКЕТ, А НЕ ПОРТ. `llama-server` слушает сокет, если адрес
кончается на `.sock`. Это снимает целый класс проблем разом: не надо искать
свободный порт, нельзя случайно открыть модель наружу, и два экземпляра
инструмента не дерутся за 8080. Права на сокет — обычные права файла в личном
каталоге.

ПОЧЕМУ ОДИН СЕРВЕР НА ВСЕ АДАПТЕРЫ. Флаг `--lora-init-without-apply` грузит
все адаптеры сразу, но ни один не применяет; какой из них жив в данный
момент, решает `POST /lora-adapters` со шкалами. Поэтому смена адаптера — это один
HTTP-запрос, а не перезапуск с чтением 2.1 ГБ заново.

ЧЕГО ЗДЕСЬ НЕТ. Зависимостей: HTTP через `http.client`, сокет через `socket`,
и то и другое — стандартная библиотека. Проект по-прежнему ставится без `pip
install`, см. шапку `vliw/agent/llm.py` — там ровно тот же принцип.
"""

from __future__ import annotations

import atexit
import http.client
import json
import os
import shutil
import socket
import subprocess
import tempfile
import threading
import time
from pathlib import Path

# Сколько ждём, пока сервер поднимется и ответит /health. Холодный старт с
# диска на медленной машине занимает секунды; берём с запасом, но не вечность —
# иначе зависший сервер выглядит как «инструмент задумался».
STARTUP_TIMEOUT_S = 180

# Через сколько простоя сервер засыпает и отдаёт память. Инструмент держит
# 3.5 ГБ, пока модель загружена, а на машине с 8 ГБ это заметно. Значение
# намеренно больше, чем пауза между двумя командами подряд.
IDLE_SLEEP_S = 600


class ServerError(RuntimeError):
    """Сервер не поднялся или ответил не тем. Ожидаемый отказ, не поломка."""


class _UnixHTTPConnection(http.client.HTTPConnection):
    """`http.client` поверх UNIX-сокета.

    Стандартная библиотека умеет HTTP и умеет AF_UNIX, но вместе их не
    соединяет. Подменяем `connect()` — это весь объём работы.
    """

    def __init__(self, path: str, timeout: float | None = None):
        super().__init__("localhost", timeout=timeout)
        self._path = path

    def connect(self) -> None:
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        if self.timeout is not None:
            s.settimeout(self.timeout)
        s.connect(self._path)
        self.sock = s


class LlamaServer:
    """Один процесс `llama-server` на весь инструмент.

    Живёт от первого запроса до выхода из инструмента. Останавливается через
    `atexit`, а не по завершении команды: смысл всей затеи в том, чтобы веса
    пережили команду.
    """

    def __init__(self, binary: Path, base_gguf: Path,
                 adapters: list[tuple[str, Path]], threads: int, ctx: int,
                 env: dict[str, str]):
        self.binary = binary
        self.base_gguf = base_gguf
        self.adapters = adapters          # [(имя, путь к -f16.gguf), ...]
        self.threads = threads
        self.ctx = ctx
        self.env = env
        self._proc: subprocess.Popen | None = None
        self._dir: str | None = None
        self._sock: str | None = None
        self._log: Path | None = None
        self._ids: dict[str, int] = {}
        self._active: str | None = None
        self._lock = threading.Lock()

    # --- жизненный цикл ---------------------------------------------------

    @property
    def running(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    def ensure(self) -> None:
        """Поднять, если ещё не поднят. Повторный вызов — бесплатный."""
        with self._lock:
            if self.running:
                return
            self._start()

    def _start(self) -> None:
        # Каталог под сокет — короткий и свой. У AF_UNIX предел длины пути
        # около 108 байт, и путь внутри проекта (или в /home с длинным именем)
        # в него может не влезть.
        self._dir = tempfile.mkdtemp(prefix="nex-")
        self._sock = os.path.join(self._dir, "l.sock")
        self._log = Path(self._dir) / "server.log"

        cmd = [
            str(self.binary),
            "-m", str(self.base_gguf),
            "--host", self._sock,
            "-c", str(self.ctx),
            "-t", str(self.threads),
            "--no-warmup",
            "--lora-init-without-apply",
            "--sleep-idle-seconds", str(IDLE_SLEEP_S),
        ]
        for _name, path in self.adapters:
            cmd += ["--lora", str(path)]

        # stderr в файл, а не в трубу: llama-server пишет туда много, и
        # непрочитанная труба однажды заполнится и подвесит сервер намертво.
        with open(self._log, "wb") as log:
            self._proc = subprocess.Popen(cmd, stdout=log, stderr=log,
                                          env=self.env)
        atexit.register(self.stop)
        self._wait_healthy()
        self._load_adapter_ids()

    def _wait_healthy(self) -> None:
        deadline = time.monotonic() + STARTUP_TIMEOUT_S
        while time.monotonic() < deadline:
            if not self.running:
                # Лог читаем ДО остановки: она сносит каталог вместе с ним.
                tail = self._tail_log()
                self.stop()
                raise ServerError("llama-server завершился при старте:\n  " + tail)
            try:
                status, body = self._request("GET", "/health")
                if status == 200 and '"ok"' in body:
                    return
            except OSError:
                pass                      # сокета ещё нет — это нормально
            time.sleep(0.25)
        tail = self._tail_log()
        self.stop()
        raise ServerError(
            f"llama-server не ответил /health за {STARTUP_TIMEOUT_S} с:\n  " + tail)

    def _tail_log(self, n: int = 6) -> str:
        if self._log is None or not self._log.exists():
            return "лога нет"
        lines = self._log.read_text("utf-8", "replace").strip().split("\n")
        return "\n  ".join(lines[-n:])

    def stop(self) -> None:
        proc, self._proc = self._proc, None
        if proc is not None and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
        # Каталог целиком, а не только сокет: в нём лежит ещё и лог сервера,
        # и без уборки каждый запуск инструмента оставлял бы в /tmp по пустому
        # каталогу навсегда. Найдено по факту — 25 штук за один день возни.
        if self._dir:
            shutil.rmtree(self._dir, ignore_errors=True)
        self._dir = self._sock = self._log = None

    # --- запросы ----------------------------------------------------------

    def _connect(self, timeout: float) -> _UnixHTTPConnection:
        if self._sock is None:
            raise ServerError("сервер не запущен")
        return _UnixHTTPConnection(self._sock, timeout=timeout)

    def _request(self, method: str, url: str, body=None,
                 timeout: float = 30.0) -> tuple[int, str]:
        conn = self._connect(timeout)
        try:
            payload = json.dumps(body) if body is not None else None
            headers = {"Content-Type": "application/json"} if payload else {}
            conn.request(method, url, body=payload, headers=headers)
            resp = conn.getresponse()
            return resp.status, resp.read().decode("utf-8", "replace")
        finally:
            conn.close()

    def _load_adapter_ids(self) -> None:
        status, body = self._request("GET", "/lora-adapters")
        if status != 200:
            raise ServerError(f"/lora-adapters ответил {status}: {body[:200]}")
        by_path = {Path(row["path"]).name: row["id"] for row in json.loads(body)}
        self._ids = {name: by_path[path.name]
                     for name, path in self.adapters if path.name in by_path}

    def select(self, name: str) -> None:
        """Сделать активным один адаптер, остальные погасить.

        Шкала 0.0 — не «выключен наполовину», а «не применяется». Гасим все
        остальные явно: если оставить два включёнными, их правки сложатся, и
        получится модель, которую никто не обучал и не замерял.
        """
        if name == self._active:
            return
        if name not in self._ids:
            raise ServerError(f"адаптер {name!r} серверу не передавался")
        scales = [{"id": i, "scale": 1.0 if n == name else 0.0}
                  for n, i in self._ids.items()]
        status, body = self._request("POST", "/lora-adapters", scales)
        if status != 200:
            raise ServerError(f"смена адаптера не удалась ({status}): {body[:200]}")
        self._active = name

    def complete(self, prompt: str, n_predict: int, timeout: float = 900.0):
        """Поток кусков ответа. Только продолжение — эха промпта здесь нет.

        Отмена: закрыть генератор. Соединение закрывается в `finally`, сервер
        видит обрыв клиента и снимает свою задачу — процесс при этом остаётся
        жить и готов к следующему запросу. Это и есть выигрыш по сравнению с
        подпроцессом, где отмена означала убийство процесса и повторное
        чтение 2.1 ГБ весов на следующий запрос.
        """
        conn = self._connect(timeout)
        try:
            body = json.dumps({
                "prompt": prompt,
                "n_predict": n_predict,
                "temperature": 0,       # детерминированно — как на замерах
                "stream": True,
                "cache_prompt": True,   # общий префикс промпта не считается заново
            })
            conn.request("POST", "/completion", body=body,
                         headers={"Content-Type": "application/json"})
            resp = conn.getresponse()
            if resp.status != 200:
                raise ServerError(f"/completion ответил {resp.status}: "
                                  + resp.read().decode("utf-8", "replace")[:200])
            for raw in resp:
                line = raw.decode("utf-8", "replace").strip()
                if not line.startswith("data:"):
                    continue
                chunk = json.loads(line[5:])
                text = chunk.get("content", "")
                if text:
                    yield text
                if chunk.get("stop"):
                    return
        finally:
            conn.close()
