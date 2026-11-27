"""Regression test: the agent must never give the model a reason to fabricate cycles.

Bug history
-----------
Mistral reported an incorrect cycle for an instruction. Investigation showed the
model wasn't at fault — it was WHAT it was given: the FACTS block only included
the schedule layout if the question matched a narrow keyword pattern. A question
like "which port is z0 on?" missed the pattern, so the layout was omitted from
FACTS, yet the model still tried to answer with no source for the numbers.

We cannot unit-test an LLM's output directly (it is nondeterministic and
requires a network call), but we CAN test GROUNDING — that FACTS contains all
the ground truth needed to answer and matches the core `Schedule` exactly.
That is the exact half that broke and that we control.

Four properties are verified:
  1. EVERY instruction appears in the layout with its issue cycle and port;
  2. numbers in the layout match the core (`Schedule`), not recomputed separately;
  3. the layout is included in FACTS for any placement question;
  4. truncation of a long layout is explicitly announced, never silent.
"""

from __future__ import annotations

import re
import unittest
from types import SimpleNamespace

from vliw.agent import context
from vliw.agent.agent import Agent
from vliw.cli import Session

# Questions the old keyword regex missed. Each requires knowing instruction
# placement, and none (except the first) contains the word "cycle".
PLACEMENT_QUESTIONS = [
    "which cycle is dc issued in?",
    "which port is z0 on?",
    "where is operation g1 placed?",
    "which VLIW bundle contains m0?",
    "why is division dc delayed?",
    "what is happening here overall?",
]


def session(scenario: str = "slotclash") -> Session:
    s = Session(args=SimpleNamespace(budget=5.0, portfolio=1.0), scenario=scenario)
    s.results()
    return s


class TestLayoutCompleteness(unittest.TestCase):
    def setUp(self):
        self.s = session()
        self.base, _, _ = self.s.peek()

    def test_every_instruction_is_in_the_layout(self):
        lay = "\n".join(context.schedule_layout(self.s))
        for ins in self.s.dag_obj:
            self.assertIn(ins.name, lay, f"{ins.name} missing from schedule layout")

    def test_cycles_and_channels_match_the_core(self):
        """The layout must reflect Schedule directly, not an independent computation."""
        lines = context.schedule_layout(self.s)
        model, dag = self.s.model(), self.s.dag_obj
        seen: dict[str, tuple[int, int]] = {}
        for line in lines:
            m = re.match(r"\s*c\.(\d+):\s*(.+)", line)
            if not m:
                continue
            cycle = int(m.group(1))
            for cell in m.group(2).split(", "):
                port, _, rest = cell.partition("=")
                name = rest.split()[-1]
                seen[name] = (cycle, int(port.strip().lstrip(",")))

        for p in self.base.schedule.placements.values():
            name = dag[p.instr].name
            self.assertIn(name, seen)
            self.assertEqual(seen[name], (p.cycle, p.channel),
                             f"{name}: in facts {seen[name]}, "
                             f"in schedule ({p.cycle}, {p.channel})")

    def test_layout_names_which_schedule_it_is(self):
        lay = "\n".join(context.schedule_layout(self.s))
        self.assertIn("baseline", lay)


class TestLayoutReachesTheModel(unittest.TestCase):
    def test_placement_questions_all_get_the_layout(self):
        """Regression guard: port/placement queries must trigger layout inclusion."""
        s = session()
        agent = Agent(session=s)
        for q in PLACEMENT_QUESTIONS:
            with self.subTest(question=q):
                self.assertTrue(agent._needs_layout(q))

    def test_facts_contain_the_layout(self):
        s = session()
        facts = context.build(s, include_layout=True)
        self.assertIn("SCHEDULE", facts)
        for ins in s.dag_obj:
            self.assertIn(ins.name, facts)

    def test_no_layout_promised_before_the_run(self):
        """Before a schedule exists, there is nothing to report and no layout should appear."""
        s = Session(args=SimpleNamespace(budget=5.0, portfolio=1.0),
                    scenario="slotclash")
        agent = Agent(session=s)
        self.assertFalse(agent._needs_layout("which cycle is dc in?"))
        self.assertEqual(context.schedule_layout(s), [])
        self.assertIn("NOT been computed", context.build(s))


class TestTruncationIsAnnounced(unittest.TestCase):
    def test_cut_layout_says_so(self):
        s = session("ptrchase")
        lay = context.schedule_layout(s, max_rows=3)
        tail = "\n".join(lay)
        self.assertIn("truncated", tail)
        self.assertIn("NOT shown", tail, "model must be explicitly warned about truncation")

    def test_full_layout_says_nothing_extra(self):
        s = session("simple4")
        self.assertNotIn("truncated", "\n".join(context.schedule_layout(s)))


class TestMachineFacts(unittest.TestCase):
    """Refuted machine assumptions must never leak into the prompt via FACTS."""

    def test_divider_named_as_the_only_monopoly(self):
        facts = "\n".join(context.machine_facts(session().model()))
        self.assertIn("DIV", facts)
        # Port ,5 is exclusive to both integer DIV and floating-point FDIV —
        # the assembler rejects fdivd on all other issue ports. Verify the
        # exclusivity fact and that DIV is named, regardless of listing order.
        self.assertRegex(facts, r"Port ,5 is the SOLE executor for [\w/]*DIV")
        self.assertIn("exclusive", facts)
        self.assertNotRegex(facts, r"SOLE executor for MUL")

    def test_narrow_ops_are_listed_with_their_ports(self):
        facts = "\n".join(context.machine_facts(session().model()))
        self.assertIn("MUL executes on ports", facts)
        self.assertIn("STORE executes on ports", facts)

    def test_system_prompt_forbids_inventing_numbers(self):
        self.assertIn("ONLY from the FACTS block", context.SYSTEM)


class TestTinyFactsInGrounding(unittest.TestCase):
    """Agent awareness of TINY Flash: the third makespan figure appears in FACTS and offline mode.

    The synergy is one-way and deterministic: TINY Flash computes its schedule
    deterministically, and the agent only reports the resulting number. We verify
    the controlled half: the number in FACTS matches a direct TinyFlashScheduler run.
    """

    def test_facts_match_direct_tiny_run(self):
        from vliw.tiny.fast import TinyFlashScheduler

        s = session()
        lines = context.tiny_facts(s)
        self.assertEqual(len(lines), 1)
        res = TinyFlashScheduler().schedule(s.dag_obj, s.model())
        self.assertIn(str(res.schedule.makespan), lines[0])
        self.assertIn(res.search_stats.get("tiny_winner", "?"), lines[0])

    def test_no_schedule_no_facts(self):
        s = Session(args=SimpleNamespace(budget=5.0, portfolio=1.0),
                    scenario="slotclash")
        self.assertEqual(context.tiny_facts(s), [])

    def test_build_contains_tiny(self):
        facts = context.build(session(), include_layout=True)
        self.assertIn("NEX", facts)
        self.assertIn("rule_", facts)

    def test_offline_answer_mentions_tiny(self):
        a = Agent(session=session())
        self.assertIn("TINY Flash", a.offline_answer("why is this basic block slow?"))


if __name__ == "__main__":
    unittest.main()
