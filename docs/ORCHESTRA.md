# Orchestra: Dialogue, HQ, Connections, TINY AI

> Stage 8 of 13 · [← Agent](AGENT_PROMPTS.md) · [Roadmap](README.md) · [TINY AI →](TINY.md)

The core computes the numbers; the agent explains them. The orchestra is everything around the model: who you talk to, who you dispatch, how you connect, and what computes without an LLM.

Ready-to-use prompts: [`AGENT_PROMPTS.md`](AGENT_PROMPTS.md).

## Quick Start

1. Paste an API key directly into the chat input. The key lives until the terminal closes and is never saved to disk. Without a key, the agent still works — answering from already computed numbers.
2. Ask in plain language. Whatever the agent executed before answering appears in the trace on the right.
3. Need multiple perspectives? Dispatch a mission from HQ: pick a connection, a focus area, and a task.

## Dialogue

One conversation per session. The tab in CODE, the side column, and the AGENT screen all show the same thread.
Prompt history lives in the expanded dialogue view; clicking an entry repeats the question. `/clear` clears the feed without erasing history.

## HQ

Background agents running on selected connections. Each has its own backend, focus area, and extra prompt instructions. An agent is read-only with respect to session state: it does not switch scenarios, load files, or write anything.

Focus areas: losses, comparison, lower bound, layout, custom question. Expanding the panel shows connections, the script, and the mission list.

## Connecting Models

Simple rule: no key, no model list.

1. Paste your key.
2. Click "connect" — the provider returns a live model catalog.
3. Click a model to activate it for the session.

Search filters the list. Where no catalog endpoint exists (e.g., Yandex), enter the model ID manually.
Local servers (Ollama / LM Studio / llama.cpp) are configured via preset or custom URL; downloading and starting local models is handled outside this tool.

Everything stays in process memory: changing the key fetches a fresh catalog, and restarting clears all state.

## TINY AI

The learned scheduler without an LLM (`vliw/tiny/`):

- net 1 — priority ordering from MLP scores;
- net 2 — "not earlier than" defer constraints;
- net 3 — beam of candidates with exact makespan selection.

Never worse than greedy by construction. Numbers and retraining: [`TINY.md`](TINY.md).

The link to the orchestra is one-way: TINY AI facts flow into the agent's context so the agent can explain them. The reverse — letting an LLM guide the scheduler — is forbidden by the honesty rule.

## Honesty Rules

1. The model does not see raw source code or the grid, and cannot do arithmetic. It narrates facts from "what the agent sees". Any number absent from that list is fabricated.
2. Ties in the portfolio go to greedy, not the model: the algorithm never takes credit for a tie.
3. Every step the agent took can be reproduced manually using the commands printed in its response.

## File Map

| file | role |
|---|---|
| `vliw/agent/agent.py` | dialogue and pre-response actions |
| `vliw/agent/context.py` | facts supplied to the model |
| `vliw/agent/llm.py` | providers, keys, active model |
| `vliw/agent/models.py` | live model catalog |
| `vliw/agent/hq.py` | HQ and missions |
| `vliw/agent/local.py` | local learned-model launcher |
| `vliw/tui/screens/agent_screen.py` | AGENT screen |

## Checks

```bash
python -m unittest tests.test_tui_smoke.TestHeadquartersPanel \
    tests.test_tui_smoke.TestModelCatalogPanel tests.test_hq \
    tests.test_agent_backends
```

No test writes to disk or hits the network: the catalog is mocked.
