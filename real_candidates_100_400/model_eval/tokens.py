"""Токены промптов для 25 графов через /tokenize живого сервера.

Сервер стартует кодом проекта (shared_server, ctx 4096): проверяется, что
путь работает с починенным LD_LIBRARY_PATH. Только чтение/замеры.
"""
import json
import os
import sys

GOMP = "/home/shokha/.local/lib/gomp/usr/lib/x86_64-linux-gnu"
os.environ["LD_LIBRARY_PATH"] = GOMP + ":" + os.environ.get("LD_LIBRARY_PATH", "")

sys.path.insert(0, "/home/shokha/vliw-ai-scheduler-demo")
from vliw.core import asm_parser
from vliw.core.model import get_profile, DEFAULT_PROFILE
from training.encode import encode_prompt
from vliw.learned import runtime

BASE = "/home/shokha/vliw-ai-scheduler-demo/real_candidates_100_400"

adapter = runtime.resolve_adapter("lora-merged")
assert adapter is not None
print("adapter:", adapter.name, flush=True)
srv = runtime.shared_server()
srv.ensure()
print("server up", flush=True)

model = get_profile(DEFAULT_PROFILE)
manifest = json.load(open(BASE + "/manifest.json"))
for m in manifest:
    name = m["name"]
    res = asm_parser.parse_asm(open(f"{BASE}/asm/{name}.s").read(), source=name)
    dag = asm_parser.build_dag(res, key=name, title=name)
    prompt = encode_prompt(dag, model)
    status, body = srv._request("POST", "/tokenize", {"content": prompt},
                               timeout=120.0)
    assert status == 200, (name, status, body[:200])
    ntok = len(json.loads(body)["tokens"])
    print(f"{name:20s} n={len(dag):4d} prompt_lines={len(prompt.splitlines()):4d} "
          f"prompt_tokens={ntok:5d} ctx_left={4096 - ntok:5d}", flush=True)
