"""Генерация ответа модели на одном графе НАСТОЯЩИМ путём проекта.

prompt: training.encode.encode_prompt; backend: runtime.make_backend
(lora-merged, llama-server); temperature=0. Сырой текст сохраняется
байт-в-байт в raw/<graph>.txt вместе с meta-JSON (времена, токены).
Компилятор не используется; vliw/** только читается/импортируется.
"""
import argparse
import json
import os
import sys
import time

GOMP = "/home/shokha/.local/lib/gomp/usr/lib/x86_64-linux-gnu"
os.environ["LD_LIBRARY_PATH"] = GOMP + ":" + os.environ.get("LD_LIBRARY_PATH", "")

sys.path.insert(0, "/home/shokha/vliw-ai-scheduler-demo")
from vliw.core import asm_parser
from vliw.core.model import get_profile, DEFAULT_PROFILE
from training.encode import encode_prompt
from vliw.learned import runtime

BASE = "/home/shokha/vliw-ai-scheduler-demo/real_candidates_100_400"
ME = BASE + "/model_eval"


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--name", required=True)
    p.add_argument("--temperature", type=float, default=0.0)
    p.add_argument("--seed", type=int, default=None)
    p.add_argument("--tag", default="t0")
    return p.parse_args()


def main():
    a = parse_args()
    model = get_profile(DEFAULT_PROFILE)
    res = asm_parser.parse_asm(open(f"{BASE}/asm/{a.name}.s").read(),
                               source=a.name)
    dag = asm_parser.build_dag(res, key=a.name, title=a.name)
    n = len(dag)
    prompt = encode_prompt(dag, model)

    adapter = runtime.resolve_adapter("lora-merged")
    assert adapter is not None and adapter.name == "lora-merged"
    t_mk = time.monotonic()
    backend = runtime.make_backend(adapter)
    mk_s = time.monotonic() - t_mk
    srv = runtime.shared_server()
    srv.ensure()
    status, body = srv._request("POST", "/tokenize", {"content": prompt},
                               timeout=120.0)
    assert status == 200, body[:200]
    prompt_tokens = len(json.loads(body)["tokens"])

    max_new_tokens = n * 12
    t0 = time.monotonic()
    raw = backend.generate(prompt, max_new_tokens, temperature=a.temperature,
                           seed=a.seed)
    gen_s = time.monotonic() - t0
    status, body = srv._request("POST", "/tokenize", {"content": raw},
                               timeout=120.0)
    assert status == 200, body[:200]
    out_tokens = len(json.loads(body)["tokens"])

    tag = "" if a.tag == "t0" else f".{a.tag}"
    with open(f"{ME}/raw/{a.name}{tag}.txt", "w", encoding="utf-8") as f:
        f.write(raw)
    meta = {"graph": a.name, "nodes": n, "adapter": adapter.name,
            "backend": getattr(backend, "name", "?"),
            "temperature": a.temperature, "seed": a.seed,
            "prompt_tokens": prompt_tokens,
            "prompt_lines": len(prompt.splitlines()),
            "max_new_tokens": max_new_tokens,
            "out_tokens": out_tokens,
            "gen_s": gen_s, "backend_setup_s": mk_s,
            "tok_per_s": out_tokens / gen_s if gen_s > 0 else 0.0,
            "server_ctx": 4096}
    with open(f"{ME}/raw/{a.name}{tag}.meta.json", "w",
              encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=1)
    print(f"[{a.name}{tag}] prompt_tok={prompt_tokens} out_tok={out_tokens} "
          f"time={gen_s:.1f}s {out_tokens / gen_s:.1f} tok/s", flush=True)


if __name__ == "__main__":
    main()
