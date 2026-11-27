# Agent: How to Ask Questions

> Stage 7 of 13 · [← CORE](CORE_MODE.md) · [Roadmap](README.md) · [Orchestra →](ORCHESTRA.md)

The agent answers based on the numbers the scheduler has already computed for the current block. Before answering, it can automatically perform actions implied by your question: load a file, switch scenarios, or finish computing the schedule.

You can ask from the workspace (AGENT tab) or with a single command:

```bash
python -m vliw ask "why is this block slow?"
```

## API Key

Without a key, the agent does not stay silent: it answers offline from computed data (greedy, exact search, and TINY AI). With a key, it explains those same facts in natural language.

- Paste the key directly into the chat or run `/ai PROVIDER key=...`.
- It lives only until the terminal closes: never written to `.env`, git, or command history.
- The provider is often auto-detected from the key format.
- Status: `/ai`. Switch provider: `/ai gemini`, then `/key ...`.

Supported providers: `mistral` (default), `gemini`, `openai`, `deepseek`, `qwen`, `kimi`, `vercel`, `grok`, `anthropic`, `glm`, `muse`, `openrouter`, `gigachat`, `yandex`, `local`, `local-server`, `custom`.

```text
/ai deepseek key=sk-...
/ai gigachat key=<client_id>:<client_secret>
/ai yandex folder=... key=...
/ai local-server url=http://localhost:11434/v1 model=qwen2.5:3b
```

## Tested Prompts

These phrasings appear in the welcome message and match what the agent reliably handles:

```text
why is this block slow?
where are cycles lost and what should change?
load examples/probe.s and analyze it
compare baseline with exact search
what is the monopoly port ,5?
```

You can also ask in your own words — with a connected model the response will be conversational, though not guaranteed to be accurate.

## What Actually Happens

- **"Load FILE and analyze it"** — the agent actually parses the file and sets it as the current block.
- **"Switch to scenario NAME"** — the active scenario actually changes.
- **Substantive question** — computes the schedule first if it has not been computed yet.
- **Greeting** — does not trigger heavy computation.

## Honest Note on Accuracy

The numbers in the NUMBERS panel and on the schedule grid do not lie. A model's prose layered on top of them sometimes can.
While verifying this document, a model claimed `g1` was scheduled on channel `,2`, when it was actually on `,1`. Always double-check specific figures visually against the grid.

This echoes the conclusion in the [research archive](archive/CAB.md): an LLM does not add reliability to what has already been computed exactly.

## Where to Look Next

- [`ORCHESTRA.md`](ORCHESTRA.md) — dialogue, HQ, model connections, TINY AI.
- [`../vliw/agent/`](../vliw/agent/) — agent source code.
