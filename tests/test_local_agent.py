"""Local-model agent tests: provider selection and offline routing.

No real GGUF weights (~5 GB) are loaded here. Instead, we verify provider
routing so that local mode never silently attempts network calls when no API
key is configured.
"""

from __future__ import annotations

import unittest
import unittest.mock as mock

from vliw.agent import llm, local


class TestProviderChoice(unittest.TestCase):
    """Provider selection: local model, Le Chat (Mistral), or Gemini."""

    def _with(self, env: dict, local_ready: bool = True, key: str = ""):
        # Mask the project `.env` so tests are deterministic regardless of local `/ai` settings.
        return (mock.patch.dict(llm.os.environ, env, clear=False),
                mock.patch.object(local, "ready", lambda: local_ready),
                mock.patch.object(llm, "_raw_key", lambda: key),
                mock.patch.object(llm, "_dotenv_values", lambda: {}))

    def _provider(self, env, local_ready=True, key=""):
        a, b, c, d = self._with(env, local_ready, key)
        with a, b, c, d:
            return llm.provider()

    def test_explicit_local_wins(self) -> None:
        self.assertEqual(self._provider({"NEX_PROVIDER": "local"}), "local")
        self.assertEqual(self._provider({"NEX_PROVIDER": "локально"}), "local")

    def test_no_key_falls_to_local_when_weights_are_here(self) -> None:
        """With no API key and local weights present, route to local instead of failing online."""
        self.assertEqual(self._provider({"NEX_PROVIDER": ""}, local_ready=True),
                         "local")

    def test_no_key_and_no_weights_keeps_the_cloud_default(self) -> None:
        """Without local weights, preserve the default cloud provider behavior."""
        self.assertEqual(
            self._provider({"NEX_PROVIDER": ""}, local_ready=False),
            llm.DEFAULT_PROVIDER)

    def test_explicit_cloud_is_not_overridden_by_local_weights(self) -> None:
        """Explicitly requesting a cloud provider must override available local weights."""
        self.assertEqual(self._provider({"NEX_PROVIDER": "mistral"}), "mistral")
        self.assertEqual(self._provider({"NEX_PROVIDER": "gemini"}), "gemini")

    def test_key_present_means_cloud(self) -> None:
        """When an API key is configured, default cloud routing is preserved."""
        self.assertEqual(
            self._provider({"NEX_PROVIDER": ""}, local_ready=True, key="abc123"),
            llm.DEFAULT_PROVIDER)


class TestRouting(unittest.TestCase):
    """Public `llm` entry points must never hit the network in local mode."""

    def setUp(self) -> None:
        patcher = mock.patch.object(llm, "provider", lambda: "local")
        patcher.start()
        self.addCleanup(patcher.stop)
        net = mock.patch.object(llm, "_make_backend",
                                mock.Mock(side_effect=AssertionError(
                                    "local mode must never make network calls")))
        net.start()
        self.addCleanup(net.stop)

    def test_complete_goes_local(self) -> None:
        with mock.patch.object(local, "complete", lambda *a, **k: "local reply"):
            self.assertEqual(llm.complete("sys", "question"), "local reply")

    def test_stream_goes_local(self) -> None:
        with mock.patch.object(local, "stream", lambda *a, **k: iter(["a", "b"])):
            self.assertEqual(list(llm.stream("sys", "question")), ["a", "b"])

    def test_structured_goes_local(self) -> None:
        with mock.patch.object(local, "structured", lambda *a, **k: ("{}", 7)):
            self.assertEqual(llm.structured("sys", "question", {}), ("{}", 7))

    def test_check_goes_local(self) -> None:
        with mock.patch.object(local, "check", lambda: (True, "ready")):
            self.assertEqual(llm.check(), (True, "ready"))

    def test_describe_says_where_it_runs(self) -> None:
        with mock.patch.object(local, "model_label", lambda: "Phi-4-mini-instruct-Q4_K_M.gguf"):
            self.assertIn("local", llm.describe())
            self.assertTrue(llm.is_local())


class TestSmallModelNudge(unittest.TestCase):
    """Prompt nudge applies only to technical questions, never to greetings/smalltalk.

    With the nudge attached to casual greetings, small 3B local models dragged
    unrelated numbers from FACTS into the reply. Disabling the nudge on
    smalltalk keeps greetings natural.
    """

    def test_nudge_on_by_default(self) -> None:
        msgs = local._messages("SYSTEM", "question", None)
        self.assertEqual(msgs[0]["role"], "system")
        self.assertTrue(msgs[0]["content"].startswith("SYSTEM"))
        self.assertIn("Next:", msgs[0]["content"])
        self.assertEqual(msgs[-1], {"role": "user", "content": "question"})

    def test_nudge_can_be_switched_off(self) -> None:
        """Smalltalk turns omit the nudge completely rather than softening it."""
        msgs = local._messages("SYSTEM", "hello", None, nudge=False)
        self.assertEqual(msgs[0]["content"], "SYSTEM")
        self.assertNotIn("Next:", msgs[0]["content"])

    def test_history_becomes_alternating_turns(self) -> None:
        msgs = local._messages("S", "new", [("prev", "reply")])
        self.assertEqual([m["role"] for m in msgs],
                         ["system", "user", "assistant", "user"])


class TestSmalltalkSkipsNudge(unittest.TestCase):
    """The agent decides based on the question, not the provider: smalltalk skips the nudge."""

    def setUp(self) -> None:
        patcher = mock.patch.object(llm, "provider", lambda: "local")
        patcher.start()
        self.addCleanup(patcher.stop)

    def _asked_nudge(self, question: str) -> bool:
        from vliw import cli
        from vliw.agent.agent import Agent

        session = cli.Session(args=cli._build_parser().parse_args([]))
        seen = {}

        def fake_stream(system, q, history=None, temperature=0.3, nudge=True):
            seen["nudge"] = nudge
            yield "ok"

        with mock.patch.object(llm, "stream", fake_stream):
            list(Agent(session).ask_stream(question))
        return seen["nudge"]

    def test_greeting_gets_no_nudge(self) -> None:
        self.assertFalse(self._asked_nudge("hello"))

    def test_real_question_gets_nudge(self) -> None:
        self.assertTrue(self._asked_nudge("why is this basic block slow?"))


class TestCellAnswerGuard(unittest.TestCase):
    """Guard against fabricated numbers in cursor-hover cell explanations.

    Added after a local 3B model hallucinated "blocked port 2 for 21 cycles"
    when none of those numbers existed in the core explanation.
    """

    FACTS = ["issued in cycle 2, result ready at 13, latency 11",
             "waited on operands: a0 ready at c.1"]

    def test_answer_within_the_facts_passes(self) -> None:
        from vliw.agent import context

        ok = context.cell_answer_is_grounded(
            "Waited for operand a0 until cycle 1, so it issued in cycle 2.",
            self.FACTS)
        self.assertTrue(ok)

    def test_invented_number_is_caught(self) -> None:
        from vliw.agent import context

        ok = context.cell_answer_is_grounded(
            "Blocked channel 2 for 21 cycles.", self.FACTS)
        self.assertFalse(ok, "21 is not in FACTS — must be caught")

    def test_answer_without_numbers_passes(self) -> None:
        """A number-free sentence cannot fabricate metrics and passes by construction."""
        from vliw.agent import context

        self.assertTrue(context.cell_answer_is_grounded(
            "The operation waited on an operand and therefore issued later.", self.FACTS))

    def test_guard_does_not_catch_wrong_relations(self) -> None:
        """Documented limitation: swapping existing numbers between roles passes regex checks.

        Because regex checking only verifies number presence, the deterministic
        core breakdown always stays displayed ABOVE the model's phrasing.
        """
        from vliw.agent import context

        self.assertTrue(context.cell_answer_is_grounded(
            "Issued in cycle 11, latency 2.", self.FACTS))


if __name__ == "__main__":
    unittest.main()
