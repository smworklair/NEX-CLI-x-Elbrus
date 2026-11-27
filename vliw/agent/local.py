"""On-device local agent: shares the same llama-server as the scheduler.

WHY. Previously the agent had only one path — a remote HTTP server (Mistral
or Gemini). That meant needing an API key, internet access, quota limits, and
sending questions about your code externally. Meanwhile a local LLM is already
available right next to the scheduler.

WHAT ANSWERS. Raw base Phi-4-mini WITHOUT trained scheduling adapters.
Project adapters (qwen-vliw-lora, etc.) are trained solely to emit lines like
`0: cycle=0 channel=1`; asking them "why is this slow?" produces a schedule
instead of prose. Moreover they target Qwen and won't load on another base
(see `runtime.shared_server`). So conversation runs on the base model while
scheduling uses TINY AI from `vliw/tiny/`, sharing the same process.

HISTORY: earlier bases were Qwen2.5-3B-Instruct (2.1 GB), then Gemma 4 E4B
(4.6 GB — accurate but slow on CPU at ~5 tok/s, plus hybrid thinking consumed
token budget). Since 2026-09-13: Phi-4-mini (2.4 GB, MIT, no thinking overhead),
twice as fast for the same phrasing task. Older bases live in `vendor/models/_retired/`.

HONEST QUALITY NOTE. A 4-bit 4B model phrases more plainly than a cloud LLM
and reasons more shallowly. This is acceptable because of the agent's design:
the parser loads files, exact search computes schedules, and `core.doctor`
identifies losses — the LLM only writes prose over verified numbers (see
`agent.py`). Numbers never change when switching models. For richer analysis,
set `NEX_PROVIDER=mistral` (or another cloud provider) with a key.
"""

from __future__ import annotations

import json

# Response timeout for interactive chat. Shorter expectations than batch
# scheduling: a human is watching the screen.
CHAT_TIMEOUT_S = 180
CHAT_MAX_TOKENS = 350
"""Response ceiling: the nudge asks for 2-4 sentences + a 'Next:' line (~100
tokens). Higher limits caused multi-minute CPU decodes with no extra value.
"""


# Warmup state. The first question in a session is slow due to two one-time
# costs: starting llama-server (~7s) and evaluating the system prompt (~1451
# tokens on CPU). Both are done once in the background while the user reads.
_WARM = {"state": "cold", "note": ""}
"""cold | warming | ready | failed — displayed in the UI."""


def warm_state() -> tuple[str, str]:
    """Return (state, note) for honest UI status reporting."""
    return _WARM["state"], _WARM["note"]


def warmup(system: str | None = None) -> None:
    """Start the local server and optionally prefill the prompt cache.

    Called from a background thread on entering AGENT mode. Returns nothing:
    if warmup fails, the first real question takes the normal path and shows
    the actual error.

    Prompt prefill requests ONE token so only the prefix is evaluated; later
    calls reuse the KV cache via `cache_prompt`.
    """
    if _WARM["state"] in ("warming", "ready"):
        return
    _WARM["state"], _WARM["note"] = "warming", "starting model"
    try:
        from ..learned import runtime

        server = runtime.shared_server()
        if system is not None:
            _WARM["note"] = "warming context"
            list(server.chat([{"role": "system", "content": system + SMALL_MODEL_NUDGE},
                              {"role": "user", "content": "."}],
                             temperature=0, max_tokens=1, timeout=CHAT_TIMEOUT_S))
        _WARM["state"], _WARM["note"] = "ready", ""
    except Exception as e:                # warmup must never crash the UI
        _WARM["state"] = "failed"
        _WARM["note"] = str(e)[:120]


def ready() -> bool:
    """Whether both the llama-server binary and base GGUF model are present."""
    try:
        from ..learned import runtime
    except Exception:
        return False
    return (runtime.find_llama_server() is not None
            and runtime.find_gguf_base() is not None)


def model_label() -> str:
    from ..learned import runtime

    base = runtime.find_gguf_base()
    return base.name if base is not None else "phi-4-mini-instruct"


SMALL_MODEL_NUDGE = (
    "\n\nIMPORTANT FOR THIS REPLY: first write 2–4 concise sentences directly "
    "answering the question using numbers from FACTS. Write in clear English. "
    "Add a 'Next:' line ONLY after those sentences. A reply consisting solely "
    "of a 'Next:' line is not allowed."
)
"""System prompt addendum — applied only to the local small model.

Small models otherwise latch onto the final instruction ('end with Next: <cmd>')
and emit only a command line without an explanation. Cloud models don't need
this nudge and don't receive it.
"""


def _messages(system: str, question: str,
              history: list[tuple[str, str]] | None,
              nudge: bool = True) -> list[dict]:
    if nudge:
        system = system + SMALL_MODEL_NUDGE
    msgs = [{"role": "system", "content": system}]
    for asked, answered in (history or []):
        msgs.append({"role": "user", "content": asked})
        msgs.append({"role": "assistant", "content": answered})
    msgs.append({"role": "user", "content": question})
    return msgs


def stream(system: str, question: str,
           history: list[tuple[str, str]] | None = None,
           temperature: float = 0.3, nudge: bool = True):
    """Stream response chunks. Server errors are wrapped as `LLMError`.

    `nudge=False` is used for small-talk turns ('hi', 'thanks'): the nudge
    forces numbers from FACTS into every reply, which causes small models to
    hallucinate technical breakdowns on a simple greeting.
    """
    from ..learned import runtime, server as srv

    from .llm import LLMError

    try:
        pump = runtime.shared_server().chat(
            _messages(system, question, history, nudge=nudge),
            temperature=temperature, max_tokens=CHAT_MAX_TOKENS,
            timeout=CHAT_TIMEOUT_S)
        yield from pump
    except srv.ServerError as e:
        raise LLMError(f"local model: {e}") from e
    except OSError as e:
        raise LLMError(f"local model unavailable: {e}") from e


def complete(system: str, question: str,
             history: list[tuple[str, str]] | None = None,
             temperature: float = 0.3, nudge: bool = True) -> str:
    return "".join(stream(system, question, history, temperature, nudge=nudge))


def structured(system: str, question: str, schema: dict,
               temperature: float = 0.1) -> tuple[str, int]:
    """Schema-constrained JSON output via llama.cpp grammar.

    If the server does not support it, raises `LLMError` so `analyst.py`
    falls back cleanly to deterministic diagnostics.
    """
    from ..learned import runtime, server as srv

    from .llm import LLMError

    msgs = _messages(system, question, None)
    try:
        server = runtime.shared_server()
        with server.using(None):
            status, body = server._request(
                "POST", "/v1/chat/completions",
                {"messages": msgs, "temperature": temperature,
                 "max_tokens": CHAT_MAX_TOKENS,
                 "response_format": {"type": "json_object", "schema": schema},
                 **server._chat_kwargs()},
                timeout=CHAT_TIMEOUT_S)
        if status != 200:
            raise LLMError(f"local model schema request: HTTP {status}")
        data = json.loads(body)
        text = data["choices"][0]["message"]["content"]
        used = int((data.get("usage") or {}).get("completion_tokens", 0))
        return text, used
    except (srv.ServerError, OSError, KeyError, ValueError) as e:
        raise LLMError(f"local model failed structured output: {e}") from e


def check() -> tuple[bool, str]:
    """Quick health check for `/ai`: start server and get a single word."""
    from .llm import LLMError, describe

    try:
        txt = complete("Reply with one word only.", 'Say "ready".',
                       temperature=0.0)
    except LLMError as e:
        return False, str(e)
    return True, f"{describe()}: {txt.strip()[:40]}"
