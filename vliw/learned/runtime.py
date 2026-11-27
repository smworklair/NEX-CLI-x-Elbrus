"""Local execution of trained adapters: weight discovery, deps, generation.

Why this layer is separate from `scheduler.py`
----------------------------------------------
Previously weights only ran on Kaggle via standalone `training/validate_kaggle.py`.
This mirrors the same loading flow (including two environment workarounds) for
local CLI use: the model loads once and serves arbitrary DAGs.

Heavy imports (torch/transformers/peft) happen ONLY inside functions so
`import vliw` stays dependency-free when `/learned` is not used.
"""

from __future__ import annotations

import json
import os
import threading
import time
from dataclasses import dataclass
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent.parent
CHECKPOINTS = _ROOT / "training" / "checkpoints"
VENDOR = _ROOT / "vendor"

# Packages required for local torch execution. Checked individually so
# diagnostics name each missing package explicitly.
REQUIRED = ("torch", "transformers", "peft")


# --------------------------------------------------------------------------
# Discovered local assets
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Adapter:
    """Discovered LoRA adapter."""

    path: Path
    base: str
    """Base model from adapter_config.json (LoRA matches its tensor shapes)."""
    size_mb: float
    has_tokenizer: bool
    """Whether a tokenizer sits beside the adapter.

    `lora-eos` saved only adapter weights, so we fall back to the base model
    or sibling adapter tokenizer.
    """

    @property
    def name(self) -> str:
        return self.path.name


def find_adapters(root: Path | None = None) -> list[Adapter]:
    """All adapters in training/checkpoints containing adapter_config.json."""
    root = root or CHECKPOINTS
    out: list[Adapter] = []
    if not root.exists():
        return out
    for cfg in sorted(root.glob("*/adapter_config.json")):
        try:
            data = json.loads(cfg.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        weights = cfg.parent / "adapter_model.safetensors"
        out.append(Adapter(
            path=cfg.parent,
            base=data.get("base_model_name_or_path", "?"),
            size_mb=weights.stat().st_size / 1e6 if weights.exists() else 0.0,
            has_tokenizer=(cfg.parent / "tokenizer_config.json").exists(),
        ))
    return out


def resolve_adapter(name: str | None = None) -> Adapter | None:
    """Resolve adapter by name/path, or pick the most recently modified."""
    found = find_adapters()
    if name:
        p = Path(name)
        if (p / "adapter_config.json").exists():
            got = find_adapters(p.parent)
            return next((a for a in got if a.path == p), None)
        return next((a for a in found if a.name == name), None)
    if not found:
        return None
    return max(found, key=lambda a: a.path.stat().st_mtime)


def missing_deps() -> list[str]:
    """Missing Python packages required for local torch execution."""
    import importlib.util

    return [m for m in REQUIRED if importlib.util.find_spec(m) is None]


def _mem_total_gb() -> float | None:
    """Total host RAM in GiB, used for model-size warnings."""
    try:
        with open("/proc/meminfo", encoding="utf-8") as f:
            for line in f:
                if line.startswith("MemTotal:"):
                    return int(line.split()[1]) / 1e6
    except OSError:
        pass
    return None


def status(name: str | None = None) -> tuple[bool, list[str]]:
    """Return (ready, report_lines). Does not require torch."""
    lines: list[str] = []
    adapters = find_adapters()
    if adapters:
        lines.append("found adapters:")
        for a in adapters:
            tok = "" if a.has_tokenizer else "  (no tokenizer — will use base)"
            lines.append(f"  {a.name}  {a.size_mb:.0f} MB  base: {a.base}{tok}")
    else:
        lines.append(f"no adapters found in {CHECKPOINTS}")

    miss = missing_deps()
    if miss:
        lines.append("")
        lines.append("missing packages: " + ", ".join(miss))
        lines.append("  install:  .venv/bin/pip install " + " ".join(miss))
    else:
        lines.append("")
        lines.append("dependencies present: " + ", ".join(REQUIRED))

    mem = _mem_total_gb()
    if mem is not None:
        lines.append("")
        lines.append(f"host RAM: {mem:.1f} GB")
        if mem < 12:
            lines.append(
                "  WARNING: even at 4-bit, Phi-4-mini takes ~2.4 GB plus "
                "activations and KV cache. On this host it may swap and "
                "take minutes, or fail to start.")
            lines.append(
                "  Recommended CPU path: 4-bit GGUF via llama.cpp "
                "(~2.4 GB): see docs/LEARNED.md.")

    # llama.cpp is the primary CPU path — check it first.
    lines.append("")
    if adapters:
        best = resolve_adapter(name)
        if best is not None:
            ok, problems = llama_cpp_ready(best)
            if ok:
                b = find_gguf_base()
                srv_ok, _ = llama_server_ready(best)
                if srv_ok:
                    lines.append(f"llama-server: ready  (adapter {best.name})")
                    lines.append(f"  base {b.name}, "
                                 f"{b.stat().st_size / 1e9:.1f} GB, 4-bit")
                    lines.append(f"  weights load once per session, "
                                 f"{default_threads()} threads")
                    lines.append("  measured: 12 s/graph vs 32 s for "
                                 "per-command subprocess")
                else:
                    lines.append(f"llama.cpp: ready  (adapter {best.name})")
                    lines.append(f"  base {b.name}, "
                                 f"{b.stat().st_size / 1e9:.1f} GB, 4-bit")
                    lines.append("  per-command subprocess: weights reload "
                                 "each call, ~32 s/graph")
                return True, lines
            lines.append("llama.cpp: not ready")
            for pr in problems:
                lines.append("  " + pr)

    ready = bool(adapters) and not miss
    return ready, lines


# --------------------------------------------------------------------------
# Generation backends
# --------------------------------------------------------------------------


class Backend:
    """Base interface for text continuation backends.

    PRIMARY method is `generate_events()`, yielding response chunks so
    caller cancellation via `close()` triggers `GeneratorExit` and cleans
    up subprocesses in `finally`.

    `generate()` is a convenience wrapper that joins the stream.
    Subclasses only need to implement `generate_events()`.
    """

    name = "?"

    slow_start = False
    """Whether the backend loads weights on first call (for UI wait hints)."""

    def generate_events(self, prompt: str, max_new_tokens: int,
                        temperature: float = 0.0, seed: int | None = None):
        """Yield raw response chunks as generated (end markers unstripped).

        `temperature`/`seed` enable sampling for best-of-N (`bench.py`).
        Default is deterministic greedy (`temperature=0`).
        """
        raise NotImplementedError

    def generate(self, prompt: str, max_new_tokens: int,
                 on_text=None, temperature: float = 0.0,
                 seed: int | None = None) -> str:
        """Return full response. Calls `on_text(chunk)` as chunks arrive."""
        parts: list[str] = []
        kw = sampling_kwargs(temperature, seed)
        for chunk in self.generate_events(prompt, max_new_tokens, **kw):
            parts.append(chunk)
            if on_text:
                on_text(chunk)
        return "".join(parts).split(END_MARKER)[0]


def sampling_kwargs(temperature: float, seed: int | None,
                    grammar: str | None = None) -> dict:
    """Sampling kwargs for generate_events() — empty at defaults so mock
    backends with the 2-arg signature keep working untouched.
    """
    kw: dict = {}
    if temperature:
        kw["temperature"] = float(temperature)
    if seed is not None:
        kw["seed"] = int(seed)
    if grammar:
        kw["grammar"] = grammar
    return kw


END_MARKER = "[end of text]"
"""llama.cpp end-of-text markers; stripped on assembled text since chunks may split them."""


class ScriptedBackend(Backend):
    """Canned responses for tests and replaying recorded runs without torch/weights."""

    name = "scripted"

    def __init__(self, replies: list[str] | str):
        self._replies = [replies] if isinstance(replies, str) else list(replies)
        self._i = 0
        self.last_sampling: dict = {}
        """Last generation request parameters (inspection hook for tests)."""

    def generate_events(self, prompt: str, max_new_tokens: int,
                        temperature: float = 0.0, seed: int | None = None):
        self.last_sampling = {"temperature": temperature, "seed": seed}
        if not self._replies:
            return
        r = self._replies[min(self._i, len(self._replies) - 1)]
        self._i += 1
        yield r


class TransformersBackend(Backend):
    """Local execution via transformers + peft (same path as Kaggle).

    Loads weights once per instance.
    """

    name = "transformers"
    slow_start = True

    def __init__(self, adapter: Adapter, dtype: str = "auto", device: str = "auto"):
        self.adapter = adapter
        self.dtype = dtype
        self.device = device
        self._tok = None
        self._model = None

    def _resolve(self):
        """Resolve concrete device and dtype (bf16 on CPU, fp16 on GPU)."""
        import torch

        device = self.device
        if device == "auto":
            device = "cuda" if torch.cuda.is_available() else "cpu"
        if self.dtype != "auto":
            return device, getattr(torch, self.dtype)
        return device, (torch.float16 if device == "cuda" else torch.bfloat16)

    def _load(self):
        if self._model is not None:
            return
        from peft import PeftModel
        from transformers import AutoModelForCausalLM, AutoTokenizer

        # Same workaround as training/validate_kaggle.py: this peft version
        # raises ImportError on incompatible torchao even though we only
        # use standard LoRA without torchao quantization.
        try:
            import peft.tuners.lora.torchao as _torchao_mod

            _torchao_mod.is_torchao_available = lambda: False
        except Exception:
            pass

        # Tokenizer may be absent beside the adapter (e.g. lora-eos);
        # fall back to the base model tokenizer.
        tok_src = str(self.adapter.path) if self.adapter.has_tokenizer else self.adapter.base
        self._tok = AutoTokenizer.from_pretrained(tok_src, trust_remote_code=True)

        device, torch_dtype = self._resolve()

        # Use `torch_dtype=` (verified on Kaggle and accepted in
        # transformers 5.x via **kwargs).
        #
        #
        #
        #
        # Pass explicit base name from adapter_config.json so newer
        # transformers does not auto-load LoRA inside from_pretrained.
        # Apply the adapter separately below.
        base = AutoModelForCausalLM.from_pretrained(
            self.adapter.base,
            torch_dtype=torch_dtype,
            device_map="auto" if device == "cuda" else None,
            low_cpu_mem_usage=True,
            trust_remote_code=True,
        )
        model = PeftModel.from_pretrained(base, str(self.adapter.path))
        model.eval()
        if device == "cpu":
            model.to("cpu")
        self._model = model

    def generate_events(self, prompt: str, max_new_tokens: int,
                        temperature: float = 0.0, seed: int | None = None):
        """Single chunk: transformers runs non-streaming and yields once."""
        import torch

        self._load()
        inputs = self._tok(prompt, return_tensors="pt").to(self._model.device)
        # Default is deterministic (do_sample=False). Sampling activates
        # ONLY with explicit temperature so standard runs stay unchanged.
        #
        gen_kw: dict = {"do_sample": False}
        if temperature and temperature > 0:
            gen_kw = {"do_sample": True, "temperature": float(temperature)}
            if seed is not None:
                torch.manual_seed(int(seed))
        with torch.no_grad():
            out = self._model.generate(
                **inputs,
                max_new_tokens=max_new_tokens,
                pad_token_id=self._tok.pad_token_id or self._tok.eos_token_id,
                **gen_kw,
            )
        # Return ONLY the continuation so the parser does not mistake
        # echoed prompt lines for a schedule.
        gen = out[0][inputs["input_ids"].shape[1]:]
        yield self._tok.decode(gen, skip_special_tokens=True)


def make_backend(adapter: Adapter, device: str | None = None,
                 dtype: str = "auto", prefer: str = "auto") -> Backend:
    """Pick execution backend. Default order: persistent llama-server ->
    per-request llama-completion -> transformers+peft.
    """
    if prefer in ("auto", "llama-server"):
        ok, problems = llama_server_ready(adapter)
        if ok:
            return LlamaServerBackend(adapter)
        if prefer == "llama-server":
            raise RuntimeError("llama-server path not ready:\n  "
                               + "\n  ".join(problems))

    if prefer in ("auto", "llama.cpp"):
        ok, problems = llama_cpp_ready(adapter)
        if ok:
            return LlamaCppBackend(adapter)
        if prefer == "llama.cpp":
            raise RuntimeError("llama.cpp path not ready:\n  " + "\n  ".join(problems))

    miss = missing_deps()
    if miss:
        raise RuntimeError(
            "missing packages for local execution: " + ", ".join(miss)
            + ".\nInstall:  .venv/bin/pip install " + " ".join(miss)
            + "\nWithout them the tool still works normally — just without /learned.")
    device = device or os.environ.get("NEX_LEARNED_DEVICE", "auto")
    return TransformersBackend(adapter, dtype=dtype, device=device)


# Single llama-completion process at a time across the tool to prevent
# two 3.6 GB processes from triggering OOM.
#
# Kept as a safety guard against concurrent launches (/learned and
# /learned --bench at the same time), even though generator close()
# now kills canceled subprocesses cleanly.
#
#
#
#
#
#
#
#
_GENERATE_LOCK = threading.Lock()


def _llama_cmd(binary, base_gguf, lora_gguf, prompt_file: str,
               max_new_tokens: int, ctx: int, threads: int,
               temperature: float = 0.0, seed: int | None = None) -> list[str]:
    """Build llama-completion CLI arguments (pure function for testing)."""
    temp_arg = "0" if not temperature else f"{temperature:g}"
    cmd = [
        str(binary),
        "-m", str(base_gguf),
        "-f", prompt_file,
        "-n", str(max_new_tokens),
        "-c", str(ctx),
        "--temp", temp_arg,
        "-t", str(threads),
        "-no-cnv",                  # NO chat template: training used raw prompts
        "--no-warmup",
    ]
    if seed is not None:
        cmd += ["--seed", str(seed)]
    if lora_gguf is not None:
        cmd += ["--lora", str(lora_gguf)]
    return cmd


class LlamaCppBackend(Backend):
    """Local execution via llama.cpp (4-bit GGUF base on CPU, no GPU).

    Runs the prebuilt binary directly (~2.1 GB RAM vs ~6.2 GB bf16).
    """

    name = "llama.cpp"
    slow_start = True

    def __init__(self, adapter: Adapter, threads: int = 0):
        self.adapter = adapter
        self.threads = threads or default_threads()
        self.binary = find_llama_binary()
        self.base_gguf = find_gguf_base()
        self.lora_gguf = gguf_adapter_for(adapter)

    def generate_events(self, prompt: str, max_new_tokens: int,
                        temperature: float = 0.0, seed: int | None = None):
        """Stream response chunks. Lock is acquired before the first `yield` so
        early cancellation always reaches `finally`.
        """
        if not _GENERATE_LOCK.acquire(blocking=False):
            raise RuntimeError(
                "model is already running a previous request — wait for it "
                "to finish; launching another would spawn a second process "
                "and double memory usage")
        try:
            yield from self._generate_events_locked(prompt, max_new_tokens,
                                                    temperature, seed)
        finally:
            _GENERATE_LOCK.release()

    def _generate_events_locked(self, prompt: str, max_new_tokens: int,
                                temperature: float = 0.0,
                                seed: int | None = None):
        import subprocess
        import tempfile

        # Pass prompt via file instead of -p to avoid CLI newline/encoding issues.
        #
        with tempfile.NamedTemporaryFile("w", suffix=".txt", encoding="utf-8",
                                         delete=False) as f:
            f.write(prompt)
            prompt_file = f.name

        # -c caps context and KV cache (default 32768 wastes ~1.1 GB RAM).
        #
        #
        #
        #
        #
        #
        ctx = max(1024, (max_new_tokens + 400) * 2)
        cmd = _llama_cmd(self.binary, self.base_gguf, self.lora_gguf,
                         prompt_file, max_new_tokens, ctx, self.threads,
                         temperature=temperature, seed=seed)

        env = _llama_env(self.binary)

        # Use Popen to stream characters incrementally instead of buffering
        # the entire ~30 s generation.
        #
        #
        timeout_s = max(120, max_new_tokens * 3)
        deadline = time.monotonic() + timeout_s
        tail = prompt[-40:]          # separates echoed prompt from continuation
        buf: list[str] = []
        answer: list[str] = []
        echo_done = False
        proc = None
        try:
            proc = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                text=True, env=env, bufsize=1)
            while True:
                if time.monotonic() > deadline:
                    proc.kill()
                    raise TimeoutError(
                        f"model exceeded {timeout_s} s — CPU may be "
                        "busy with another model process")
                chunk = proc.stdout.read(1)
                if not chunk:
                    break
                buf.append(chunk)
                if echo_done:
                    answer.append(chunk)
                    yield chunk
                    continue
                # llama.cpp echoes the prompt first; suppress output until prompt tail passes.
                #
                if "".join(buf[-len(tail):]) == tail:
                    echo_done = True
            proc.wait(timeout=10)
        finally:
            if proc is not None and proc.poll() is None:
                proc.kill()
            try:
                os.unlink(prompt_file)
            except OSError:
                pass

        if echo_done:
            return

        # Fallback if streaming echo detector missed the prompt tail:
        # extract continuation from the full buffer and emit once.
        #
        #
        #
        out = "".join(buf)
        if tail in out:
            out = out.split(tail, 1)[1]
        if out:
            yield out


_SERVER = None
"""Singleton server per tool process. See `vliw/learned/server.py`."""

def default_threads() -> int:
    """Thread count for llama.cpp: half of logical cores, capped at 8
    (avoids hyperthreading cache contention).
    """
    return max(2, min(8, (os.cpu_count() or 4) // 2))


SERVER_CTX = 4096
"""Server context window: large enough for both scheduler and agent chat."""

SERVER_MAX_TOKENS = 768
"""Target response length for server context sizing (avoids circular import with scheduler)."""


class LlamaServerBackend(Backend):
    """Persistent llama-server backend: weights persist across commands and
    adapters switch via HTTP without restarting.
    """

    name = "llama-server"
    slow_start = True

    def __init__(self, adapter: Adapter, threads: int = 0):
        self.adapter = adapter
        self.threads = threads or default_threads()
        self.binary = find_llama_server()
        self.base_gguf = find_gguf_base()

    def generate_events(self, prompt: str, max_new_tokens: int,
                        temperature: float = 0.0, seed: int | None = None,
                        grammar: str | None = None):
        # Pass adapter into complete() so the mode lock stays held throughout
        # generation and chat cannot switch LoRA mid-request.
        #
        yield from shared_server().complete(prompt, max_new_tokens,
                                            adapter=self.adapter.name,
                                            temperature=temperature,
                                            seed=seed, grammar=grammar)


def shared_server():
    """Shared llama-server singleton for both scheduler and agent chat.

    Modes share one process and switch LoRA scales via `LlamaServer.using`.
    """
    global _SERVER

    from . import server as _srv

    if _SERVER is None:
        binary, base = find_llama_server(), find_gguf_base()
        if binary is None or base is None:
            raise _srv.ServerError("llama-server or GGUF base not found in vendor/")
        # Empty adapter list is valid: chat uses the bare base model.
        #
        #
        #
        # Project LoRAs target Qwen only; attach them only to a Qwen base.
        #
        #
        #
        adapters: list[tuple[str, Path]] = []
        if base_family(base) == "qwen":
            adapters = [(a.name, gguf_adapter_for(a)) for a in find_adapters()]
            adapters = [(n, p) for n, p in adapters if p is not None]
        # Context is fixed at startup and must fit both scheduler and agent chat
        # (system prompt ~1451 tokens + dialog + reply), without wasting RAM on
        # full 32768 KV cache.
        #
        #
        #
        #
        #
        #
        ctx = SERVER_CTX
        _SERVER = _srv.LlamaServer(binary=binary, base_gguf=base,
                                   adapters=adapters, threads=default_threads(),
                                   ctx=ctx, env=_llama_env(binary))
    _SERVER.ensure()
    return _SERVER


def llama_server_ready(adapter: Adapter) -> tuple[bool, list[str]]:
    """Check llama-server readiness: binary, base GGUF, converted adapter."""
    problems = []
    if find_llama_server() is None:
        problems.append("missing llama-server binary in vendor/")
    if find_gguf_base() is None:
        problems.append("missing quantized base (*.gguf) in vendor/models/")
    if gguf_adapter_for(adapter) is None:
        problems.append(f"adapter {adapter.name} is not converted to GGUF")
    return not problems, problems


def _llama_env(binary: Path) -> dict[str, str]:
    """Environment for running llama.cpp (reuses torch's bundled libgomp if present)."""
    env = dict(os.environ)
    libs = [str(binary.parent)]
    torch_lib = _torch_lib_dir()
    if torch_lib:
        libs.append(str(torch_lib))
    env["LD_LIBRARY_PATH"] = ":".join(libs + [env.get("LD_LIBRARY_PATH", "")])
    return env


def _torch_lib_dir():
    """Directory containing torch shared libraries (including libgomp.so.1)."""
    try:
        import importlib.util

        spec = importlib.util.find_spec("torch")
        if spec and spec.origin:
            d = Path(spec.origin).parent / "lib"
            if d.exists():
                return d
    except Exception:
        pass
    return None


def find_llama_server() -> Path | None:
    """Path to llama-server binary in vendor/."""
    for p in sorted(VENDOR.glob("llama-*/llama-server")):
        if os.access(p, os.X_OK):
            return p
    return None


def find_llama_binary() -> Path | None:
    """Path to non-interactive llama-completion binary in vendor/."""
    for p in sorted(VENDOR.glob("llama-*/llama-completion")):
        if os.access(p, os.X_OK):
            return p
    return None


def base_family(base: Path | None = None) -> str:
    """Base model family ('qwen' or stem) to guard Qwen-specific LoRA loading."""
    name = (base or find_gguf_base() or Path("")).name.lower()
    if "qwen" in name:
        return "qwen"
    return (base or find_gguf_base() or Path("unknown")).stem or "unknown"


def find_gguf_base() -> Path | None:
    """Find quantized base GGUF in vendor/models (excluding -f16.gguf adapters).

    Preference order: phi -> gemma -> any non-qwen -> qwen.
    """
    cands = sorted(p for p in (VENDOR / "models").glob("*.gguf")
                   if not p.name.endswith("-f16.gguf"))
    if not cands:
        return None

    def rank(p: Path) -> int:
        n = p.name.lower()
        if "phi" in n:
            return 0
        if "gemma" in n:
            return 1
        if "qwen" not in n:
            return 2
        return 3

    return sorted(cands, key=lambda p: (rank(p), p.name))[0]


def gguf_adapter_for(adapter: Adapter) -> Path | None:
    """Converted GGUF adapter alongside the base model."""
    p = VENDOR / "models" / f"{adapter.name}-f16.gguf"
    return p if p.exists() else None


def llama_cpp_ready(adapter: Adapter) -> tuple[bool, list[str]]:
    """Check llama.cpp readiness: binary, base GGUF, converted adapter."""
    problems = []
    if find_llama_binary() is None:
        problems.append("missing llama-completion binary in vendor/")
    if find_gguf_base() is None:
        problems.append("missing quantized base (*.gguf) in vendor/models/")
    if gguf_adapter_for(adapter) is None:
        problems.append(f"adapter {adapter.name} is not converted to GGUF")
    return not problems, problems
