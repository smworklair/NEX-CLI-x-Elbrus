"""vliw.tiny — Tiny-1: learned priority for list_schedule instead of Qwen.

Why: Qwen2.5-3B generates schedules as text (seconds, GPU, 17% valid
on hard cases without CAB). Tiny needs no text: it only outputs a priority
vector, while deterministic list_schedule handles all bookkeeping
(dependencies, ports, latencies) — valid by construction, zero
hallucinations by design.

Inference uses pure stdlib, no numpy/torch: an MLP forward pass on a graph
with n<=386 takes microseconds on CPU.
"""

from __future__ import annotations
