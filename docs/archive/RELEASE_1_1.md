# Release 1.1 beta: From a Solo AI to an Orchestra

In short: first there was a solo AI (chatting with a model), then an API layer was added
(providers, keys, catalog), and now it is an orchestra — dialog, headquarters,
connection, and tiny schedulers working together. Version check:
`python -m vliw --version` → `NEX CLI 1.1 beta (1.1.0b1)`.

Dry numbers are in [`CHANGELOG.md`](../../CHANGELOG.md); the orchestra architecture is
in [`ORCHESTRA.md`](../ORCHESTRA.md). Here is what changed for a human user.

## The path: AI → API → orchestra

1. **Solo AI.** The agent replied with text in the same feed where reports were
   printed — and it was unclear what the answer was based on. The key was pasted
   into who-knows-where, and there was only one provider.
2. **API.** Added 15 providers (`vliw/agent/backends/` — one file per API:
   Mistral, Gemini, OpenAI, DeepSeek, Qwen, Kimi, Grok, Anthropic,
   GLM, Muse, OpenRouter, Vercel, GigaChat, Yandex, local server),
   a live model catalog, and a session-only key (close the terminal —
   the key is gone; nothing is written to disk).
3. **Orchestra (this release).** The parts are connected: the dialog asks questions,
   headquarters dispatches background agents over verified connections, the connection
   is fixed in two clicks, and the tiny schedulers compute with no model at all — while
   the agent explains their numbers instead of inventing its own.

## The agent block has been massively overhauled

Before: one chat + a dumping ground of model settings inside it. Now: four blocks,
each expandable to full screen with a double-click.

| block | mini (always visible) | full screen |
|---|---|---|
| **DIALOG** | conversation feed | question history with timers (click to repeat), `^L` clear, `^R` repeat |
| **HQ** (primary) | summary (connections · missions · latest) + task input, Enter sends | connections (which one runs the task), focus area (losses / comparison / lower bound / layout / custom question), prompt addendum script, mission list (retry / remove / clear completed) |
| **CONNECTION** | provider, 5 API buttons, key field + "connect" | 3 steps: provider → key → catalog; search is labeled honestly (list filter only); manual ID with a paid probe; local server presets |
| **WHAT THE AGENT SEES / TRACE** | number summary / recent actions | verbatim model context / all steps with reproduction commands |

The honesty rules remain the same and stricter: the model does not compute (numbers
come only from facts), the trace is reproducible by hand, and keys live only in memory.

## Tiny schedulers: 219 → 284/300

The trained non-LLM scheduler grew into a 9-opinion portfolio (never worse than
baseline by construction):

- `greedy` → `prio` (MLP ordering) → `prio_defer` / `prio_hold` (two-head
  holds) → `rule_hold` / `rule_hold_far` (handcrafted monopoly-port holds —
  closed the "slot gap for DIV" class) → `beam_t/h/d` (beam fan).
- `eval_hard`: **284/300** optimal (was 219), gap 0.270 → **0.053**,
  wins 203 → 267. The remaining 16 graphs are all off by exactly 1 cycle.
- Real code: 5/13 → **7/13**, 0 losses. Speed is the same order of magnitude:
  ~75 ms synthetic, ~2.5 s for a 386-node graph.
- Weight pipeline: supervised → ES fine-tuning (`es.py --mode prio|hold`).
- Rejected with numbers (details in `docs/TINY.md`): 20 features, mixing in
  hard examples, 140K weights, gap-gate, ES fine-tuning of hold.

## Codebase cleanup

- Removed `.presentation/` (marketing material; nothing in the repo referenced it).
- Normalized line endings to LF (Windows wrote CRLF and dirtied `git status`).
- Junk (`Zone.Identifier`, generator output) added to `.gitignore`.
- Created `CHANGELOG.md` and the first tag `v1.1.0b1`.

## How to verify in 5 minutes

```bash
python -m vliw --version            # 1.1 beta
python -m vliw tiny slotclash       # tiny schedulers vs. baseline and oracle
python -m vliw.tiny.eval --eval eval_hard.jsonl --limit 20
python -m unittest tests.test_tiny tests.test_hq -v
```
