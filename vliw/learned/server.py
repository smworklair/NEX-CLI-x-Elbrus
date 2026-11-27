"""Persistent llama-server: load weights once per session instead of per command.

WHY. The previous path (`LlamaCppBackend`) spawned `llama-completion` on every
request, re-reading 2.1 GB of weights and warming up context each time.
Measured on `slotclash` with adapter `lora-eos`:

    subprocess per command  32 s,   first token ~20 s
    persistent server       14 s,   first token 2.6 s (cold)
                            14 s,   first token 0.11 s (warm cache)

Output matches line-for-line — same llama.cpp and weights, persistent process.

WHY A UNIX SOCKET INSTEAD OF A TCP PORT. `llama-server` listens on a UNIX
socket when the address ends in `.sock`: no port hunting, no accidental
network exposure, and multiple instances never fight over port 8080.

WHY ONE SERVER FOR ALL ADAPTERS. `--lora-init-without-apply` loads all LoRAs
upfront at scale 0; `POST /lora-adapters` toggles the active adapter in one
HTTP call without reloading 2.1 GB.

ZERO EXTERNAL DEPS. Uses stdlib `http.client` and `socket` only.
"""

from __future__ import annotations

import atexit
import contextlib
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

# Startup wait for /health. Cold disk loads take seconds on slower
# machines; leave margin without hanging forever — otherwise a
# stuck server looks like the tool froze.
STARTUP_TIMEOUT_S = 180

# Idle timeout before stopping the server to free memory. The tool
# holds ~3.5 GB while loaded, noticeable on 8 GB hosts. Kept longer
# than a typical pause between consecutive commands.
IDLE_SLEEP_S = 600


class ServerError(RuntimeError):
    """Server failed to start or returned an unexpected response (expected error)."""


class _UnixHTTPConnection(http.client.HTTPConnection):
    """`http.client` over a UNIX domain socket.

    Stdlib supports HTTP and AF_UNIX separately; overriding `connect()`
    bridges them.
    """

    def __init__(self, path: str, timeout: float | None = None):
        super().__init__("localhost", timeout=timeout)
        self._path = path

    def connect(self) -> None:
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        if self.timeout is not None:
            s.settimeout(self.timeout)
        try:
            s.connect(self._path)
        except OSError:
            # Always close: startup polling issues dozens of failed /health
            # calls, each of which would otherwise leak a file descriptor
            # until garbage collection.
            s.close()
            raise
        self.sock = s


class LlamaServer:
    """Single `llama-server` process shared across the tool.

    Lives from first request until process exit (stopped via `atexit`)
    so loaded weights persist across commands.
    """

    def __init__(self, binary: Path, base_gguf: Path,
                 adapters: list[tuple[str, Path]], threads: int, ctx: int,
                 env: dict[str, str]):
        self.binary = binary
        self.base_gguf = base_gguf
        self.adapters = adapters          # [(name, path to -f16.gguf), ...]
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
        # Second lock guards MODE, not startup. One process serves two
        # modes: scheduler (with adapter) and chat (bare base). Switching
        # mode mid-generation would corrupt an in-flight response, so
        # the mode lock is held for the entire generation and released
        # when it finishes.
        self._use_lock = threading.Lock()

    # --- lifecycle ---------------------------------------------------------

    @property
    def running(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    def ensure(self) -> None:
        """Start if not already running. Repeated calls are no-ops."""
        with self._lock:
            if self.running:
                return
            self._start()

    def _start(self) -> None:
        # Short dedicated socket directory: AF_UNIX path length limit is
        # ~108 bytes, which a deep project or /home path can exceed.
        #
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

        # Redirect stderr to a file, not a pipe: llama-server is verbose
        # and an unread pipe would fill up and deadlock the server.
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
                # Read log BEFORE stopping: stop() removes the temp directory.
                tail = self._tail_log()
                self.stop()
                raise ServerError("llama-server exited during startup:\n  " + tail)
            try:
                status, body = self._request("GET", "/health")
                if status == 200 and '"ok"' in body:
                    return
            except OSError:
                pass                      # socket not created yet — expected
            time.sleep(0.25)
        tail = self._tail_log()
        self.stop()
        raise ServerError(
            f"llama-server did not answer /health within {STARTUP_TIMEOUT_S} s:\n  " + tail)

    def _tail_log(self, n: int = 6) -> str:
        if self._log is None or not self._log.exists():
            return "no log"
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
        # Remove the entire temp directory (socket + server log) so
        # repeated runs do not leave empty directories behind in /tmp.
        #
        if self._dir:
            shutil.rmtree(self._dir, ignore_errors=True)
        self._dir = self._sock = self._log = None

    # --- requests ----------------------------------------------------------

    def _connect(self, timeout: float) -> _UnixHTTPConnection:
        if self._sock is None:
            raise ServerError("server is not running")
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
            raise ServerError(f"/lora-adapters returned {status}: {body[:200]}")
        by_path = {Path(row["path"]).name: row["id"] for row in json.loads(body)}
        self._ids = {name: by_path[path.name]
                     for name, path in self.adapters if path.name in by_path}

    def select(self, name: str) -> None:
        """Activate one adapter and disable all others.

        Scale 0.0 disables an adapter completely. Explicit disabling avoids
        stacking two adapters into an untested hybrid.
        """
        if name == self._active:
            return
        if name not in self._ids:
            raise ServerError(f"adapter {name!r} was not loaded into the server")
        scales = [{"id": i, "scale": 1.0 if n == name else 0.0}
                  for n, i in self._ids.items()]
        status, body = self._request("POST", "/lora-adapters", scales)
        if status != 200:
            raise ServerError(f"failed to switch adapter ({status}): {body[:200]}")
        self._active = name

    def select_base(self) -> None:
        """Disable all adapters, leaving the bare base model (currently Phi-4-mini).

        Trained adapters only know schedule lines and hurt chat quality.
        Chat runs on the bare base while scheduling uses `vliw/tiny/`, sharing
        the same server process.
        """
        if not self._ids:
            return
        scales = [{"id": i, "scale": 0.0} for i in self._ids.values()]
        status, body = self._request("POST", "/lora-adapters", scales)
        if status != 200:
            raise ServerError(f"failed to disable adapters ({status}): {body[:200]}")
        self._active = None

    @contextlib.contextmanager
    def using(self, adapter: str | None):
        """Acquire the model for one mode. `None` means chat on bare base."""
        with self._use_lock:
            if adapter is None:
                self.select_base()
            else:
                self.select(adapter)
            yield

    def chat(self, messages: list[dict], temperature: float = 0.3,
             max_tokens: int = 700, timeout: float = 900.0):
        """Chat with the base model, streaming text chunks.

        Uses `/v1/chat/completions` rather than `/completion` so the server
        applies the exact chat template embedded in the GGUF.
        """
        with self.using(None):
            conn = self._connect(timeout)
            try:
                body = json.dumps({"messages": messages,
                                   "temperature": temperature,
                                   "max_tokens": max_tokens, "stream": True,
                                   **self._chat_kwargs()})
                conn.request("POST", "/v1/chat/completions", body=body,
                             headers={"Content-Type": "application/json"})
                resp = conn.getresponse()
                if resp.status != 200:
                    raise ServerError(
                        f"/v1/chat/completions returned {resp.status}: "
                        + resp.read().decode("utf-8", "replace")[:200])
                for raw in resp:
                    line = raw.decode("utf-8", "replace").strip()
                    if not line.startswith("data:"):
                        continue
                    payload = line[5:].strip()
                    if not payload or payload == "[DONE]":
                        continue
                    try:
                        chunk = json.loads(payload)
                    except ValueError:
                        continue
                    choices = chunk.get("choices") or [{}]
                    piece = (choices[0].get("delta") or {}).get("content")
                    if piece:
                        yield piece
            finally:
                conn.close()

    def _chat_kwargs(self) -> dict:
        """Extra request body fields for /v1/chat/completions by base model family.

        Gemma 4 defaults to hybrid-thinking and can burn the entire token
        budget on reasoning, leaving `content` empty. Numbers are already
        computed by the core, so thinking is disabled. Omitted for Qwen.
        """
        if "gemma" in self.base_gguf.name.lower():
            return {"chat_template_kwargs": {"enable_thinking": False}}
        return {}

    def complete(self, prompt: str, n_predict: int, adapter: str | None = None,
                 timeout: float = 900.0, temperature: float = 0.0,
                 seed: int | None = None, grammar: str | None = None):
        """Stream completion chunks (continuation only, no prompt echo).

        `temperature`/`seed` enable sampling for best-of-N (`bench.py`).
        Defaults match deterministic greedy decoding.

        Cancellation: close the generator. Closing the connection in `finally`
        cancels the in-flight server task while keeping the process alive.
        """
        with self.using(adapter) if adapter else contextlib.nullcontext():
            yield from self._complete(prompt, n_predict, timeout,
                                      temperature=temperature, seed=seed,
                                      grammar=grammar)

    def _complete(self, prompt: str, n_predict: int, timeout: float,
                  temperature: float = 0.0, seed: int | None = None,
                  grammar: str | None = None):
        conn = self._connect(timeout)
        try:
            body: dict = {
                "prompt": prompt,
                "n_predict": n_predict,
                "temperature": temperature,   # 0 — deterministic, matching benchmarks
                "stream": True,
                "cache_prompt": True,   # reuse shared prompt prefix cache
            }
            if seed is not None:
                body["seed"] = int(seed)
            if grammar:
                # Structural guarantee: the server enforces the grammar so
                # illegal channels and broken syntax become impossible
                # rather than merely unlikely.
                body["grammar"] = grammar
            body = json.dumps(body)
            conn.request("POST", "/completion", body=body,
                         headers={"Content-Type": "application/json"})
            resp = conn.getresponse()
            if resp.status != 200:
                raise ServerError(f"/completion returned {resp.status}: "
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
