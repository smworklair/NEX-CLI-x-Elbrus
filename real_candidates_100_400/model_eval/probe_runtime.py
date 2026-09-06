"""Probe model runtime status (read-only, no server start)."""
import sys

sys.path.insert(0, "/home/shokha/vliw-ai-scheduler-demo")
from vliw.learned import runtime

ready, lines = runtime.status(None)
print("ready:", ready)
for ln in lines:
    print(ln)
