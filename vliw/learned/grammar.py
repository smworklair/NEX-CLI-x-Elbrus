"""Response grammar for llama.cpp: schedule skeleton instead of free text.

WHY. Measurements in `docs/archive/DIAG3.md` showed the key finding: the model
schedules well, but fails on formatting. For the run-1 adapter, 97 of 98 valid
responses were EXACT optima — whenever it emitted a parseable schedule, it was
nearly always optimal. Failures came from unsupported channels and broken
syntax. Removing those two failure modes lifts eval_wide from 15% to 84% valid
(run-2 adapter), 74% at exact CP-SAT optimum.

WHY GRAMMAR INSTEAD OF LOGIT MASKING. On Kaggle this uses logit masking
(`training/validate_kaggle.py`) where transformers exposes logits. Locally,
llama.cpp runs over a socket without exposing logits, but supports GBNF: the
server enforces the grammar directly. Same guarantee, different mechanism.

WHAT GRAMMAR CANNOT DO. It constrains EACH line independently: cycle is any
integer, channel is drawn from valid channels for that op. It does not track
whether a channel is already occupied IN THE SAME CYCLE, which depends on
earlier generated lines. Thus invalid channels drop to 0 (from 315), while
conflicts rise (144 -> 208) as choices narrow. `repair.py` resolves conflicts
via bipartite matching — grammar and repair are two halves of one solution.
"""

from __future__ import annotations


def _escape(text: str) -> str:
    """GBNF string literal.

    Newlines must be escaped as `\\n`, never raw bytes: GBNF rejects raw
    newlines inside quotes and the server rejects the whole grammar with a
    generic parse error.
    """
    return (text.replace("\\", "\\\\")
                .replace('"', '\\"')
                .replace("\n", "\\n"))


def schedule_grammar(dag, model) -> str:
    """Build GBNF grammar for a specific DAG.

    Matches the training format character-for-character (no trailing newline).

    Channels come from the machine model — one grammar rule per instruction,
    since operation classes differ: STORE uses `,2 ,5`, DIV uses exclusive
    port `,5`, ADD uses all six. A single shared digit set would reintroduce
    the exact error this grammar prevents.
    """
    lines = []
    rules = []
    for idx, ins in enumerate(dag.instrs):
        chans = model.channels_for(ins.op)
        if not chans:
            # Class absent from the machine profile. Allow any channel —
            # grammar narrows choices, it should not fail here.
            chans = tuple(range(model.width))
        alts = " | ".join(f'"{c}"' for c in sorted(chans))
        name = f"op{idx}"
        cycle_kw = "\u0442\u0430\u043a\u0442"
        chan_kw = "\u043a\u0430\u043d\u0430\u043b"
        rules.append(
            f'{name} ::= "{_escape(chr(10) + str(ins.id) + ": " + cycle_kw + "=")}" '
            f'cycle " {chan_kw}=" ({alts})')
        lines.append(name)

    body = " ".join(lines)
    return "\n".join([
        f"root ::= {body}",
        # Cycle is a non-negative integer without leading zeros ("0" itself is valid).
        'cycle ::= "0" | [1-9] [0-9]*',
        *rules,
    ])


def grammar_stats(dag, model) -> dict:
    """How much the grammar narrows choices — for reporting only."""
    total = sum(len(model.channels_for(i.op)) or model.width
                for i in dag.instrs)
    return {
        "operations": len(dag.instrs),
        "channel_options_total": total,
        "without_grammar": len(dag.instrs) * model.width,
    }
