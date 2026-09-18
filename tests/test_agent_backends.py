"""Универсальные backend'ы агента: фабрика, тела запросов, разбор ответов.

Без сети: HTTP-слой мокается, проверяется склейка «фабрика -> backend ->
текст», а не чужие серверы. Формат — как в Nex-pilot: один интерфейс,
по файлу на провайдер.
"""

from __future__ import annotations

import contextlib
import io
import os
import unittest
import unittest.mock as mock
from pathlib import Path

from vliw.agent import envfile, llm
from vliw.agent.backends import base as bbase
from vliw.agent.backends import gigachat as bgiga
from vliw.agent.backends import openai_compat as bcompat
from vliw.agent.backends import yandex as byandex


class TestProviderAliases(unittest.TestCase):
    def test_aliases(self) -> None:
        cases = {"lechat": "mistral", "google": "gemini",
                 "yandexgpt": "yandex", "giga": "gigachat",
                 "openrouter": "openrouter", "ollama": "local-server"}
        for raw, want in cases.items():
            with self.subTest(raw=raw):
                with mock.patch.dict(llm.os.environ, {"NEX_PROVIDER": raw}, clear=False):
                    with mock.patch.object(llm, "_raw_key", lambda: "k"), \
                            mock.patch.object(llm.local, "ready", lambda: False):
                        self.assertEqual(llm.provider(), want)

    def test_explicit_new_providers(self) -> None:
        for name in ("openai", "deepseek", "qwen", "kimi", "custom",
                     "gigachat", "yandex"):
            with self.subTest(name=name):
                with mock.patch.dict(llm.os.environ, {"NEX_PROVIDER": name}, clear=False):
                    self.assertEqual(llm.provider(), name)


class TestProviderConfigIntegration(unittest.TestCase):
    def test_provider_config_routes_requests(self):
        import json

        cases = (
            ("grok", "XAI_API_KEY", "https://api.x.ai/v1/chat/completions"),
            ("vercel", "VERCEL_API_KEY", "https://ai-gateway.vercel.sh/v1/chat/completions"),
            ("openrouter", "OPENROUTER_API_KEY", "https://openrouter.ai/api/v1/chat/completions"),
        )
        payload = {"choices": [{"message": {"content": "ok"}}]}
        for prov, key_var, endpoint in cases:
            with self.subTest(provider=prov), \
                    mock.patch.dict(os.environ, {}, clear=True), \
                    mock.patch.object(llm.envfile, "load", return_value={
                        "NEX_PROVIDER": prov, key_var: "fake-provider-key",
                        "NEX_MODEL": "test-model", "NEX_BASE_URL": "https://foreign.invalid/v1",
                    }), \
                    mock.patch.object(llm, "_raw_key", return_value=""), \
                    mock.patch.object(bbase.urllib.request, "urlopen",
                                      return_value=io.BytesIO(json.dumps(payload).encode())) as http:
                self.assertEqual(llm.provider(), prov)
                self.assertEqual(llm._make_backend(llm.provider()).complete("system", "question"), "ok")
                request = http.call_args.args[0]
                self.assertEqual(request.full_url, endpoint)
                self.assertEqual(request.get_header("Authorization"), "Bearer fake-provider-key")
                self.assertEqual(json.loads(request.data)["model"], "test-model")

    def test_local_server_uses_own_vars(self):
        import json

        payload = {"choices": [{"message": {"content": "ok"}}]}
        with mock.patch.dict(os.environ, {
            "NEX_PROVIDER": "local-server",
            "NEX_LOCAL_URL": "http://127.0.0.1:11434/v1",
            "NEX_LOCAL_MODEL": "llama3",
        }, clear=True), \
                mock.patch.object(llm, "_dotenv_values", lambda: {}), \
                mock.patch.object(bbase.urllib.request, "urlopen",
                                  return_value=io.BytesIO(json.dumps(payload).encode())) as http:
            be = llm._make_backend("local-server")
            self.assertEqual(be.complete("s", "q"), "ok")
            request = http.call_args.args[0]
            self.assertEqual(request.full_url, "http://127.0.0.1:11434/v1/chat/completions")
            self.assertEqual(json.loads(request.data)["model"], "llama3")

    def test_local_server_rejects_non_loopback(self):
        with mock.patch.dict(os.environ, {"NEX_LOCAL_URL": "https://example.com/v1"},
                             clear=True), \
                mock.patch.object(llm, "_dotenv_values", lambda: {}):
            with self.assertRaises(llm.LLMError):
                llm._make_backend("local-server")

    def test_muse_enabled(self):
        with mock.patch.dict(os.environ, {"NEX_PROVIDER": "muse",
                                           "META_API_KEY": "fake-meta-key"},
                             clear=True), \
                mock.patch.object(llm, "_dotenv_values", lambda: {}):
            self.assertTrue(llm.available())
            be = llm._make_backend("muse")
            self.assertEqual(be._base_url, "https://api.meta.ai/v1")
            self.assertEqual(be._model, "muse-spark-1.3")
            be = llm.configured_backend("muse", "muse-spark-1.2",
                                        api_key="k")
            self.assertEqual(be._model, "muse-spark-1.2")

    def test_configured_backend_snapshot(self):
        with mock.patch.dict(os.environ, {}, clear=True), \
                mock.patch.object(llm, "_dotenv_values", lambda: {}):
            be = llm.configured_backend("grok", "grok-3", api_key="k1")
            self.assertEqual(be._key, "k1")
            self.assertEqual(be._base_url, "https://api.x.ai/v1")
            self.assertEqual(be._model, "grok-3")
            with self.assertRaises(AttributeError):
                be._key = "k2"
            with self.assertRaises(AttributeError):
                del be._key

    def test_configured_backend_local_requires_loopback(self):
        with mock.patch.dict(os.environ, {}, clear=True), \
                mock.patch.object(llm, "_dotenv_values", lambda: {}):
            with self.assertRaises(llm.LLMError):
                llm.configured_backend("local-server", "m",
                                       base_url="https://example.com/v1")

    def test_foreign_base_url_does_not_reach_preset(self):
        with mock.patch.dict(os.environ, {
            "NEX_PROVIDER": "deepseek", "DEEPSEEK_API_KEY": "k",
            "NEX_BASE_URL": "https://evil.example/v1",
        }, clear=True), \
                mock.patch.object(llm, "_dotenv_values", lambda: {}):
            be = llm._make_backend("deepseek")
            self.assertEqual(be._base_url, "https://api.deepseek.com/v1")

    def test_specific_env_key_beats_generic(self):
        with mock.patch.dict(os.environ, {
            "NEX_PROVIDER": "deepseek", "DEEPSEEK_API_KEY": "specific",
            "NEX_API_KEY": "generic",
        }, clear=True), \
                mock.patch.object(llm, "_dotenv_values", lambda: {}):
            self.assertEqual(llm.api_key(), "specific")


class TestFactory(unittest.TestCase):
    def setUp(self) -> None:
        # Настоящий `.env` глушим: фабрика читает его через `setting()`,
        # и сохранённые пользователем значения ломали бы проверки «нужно Х».
        patcher = mock.patch.object(llm, "_dotenv_values", lambda: {})
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_unknown_provider(self) -> None:
        with self.assertRaises(llm.LLMError):
            llm._make_backend("nosuch")

    def test_openai_needs_base_or_default(self) -> None:
        with mock.patch.dict(llm.os.environ, {"NEX_API_KEY": "k"}, clear=True):
            be = llm._make_backend("openai")
            self.assertTrue(be._base_url.startswith("https://"))

    def test_custom_needs_base_url(self) -> None:
        with mock.patch.dict(llm.os.environ, {"NEX_API_KEY": "k"}, clear=True):
            with self.assertRaises(llm.LLMError):
                llm._make_backend("custom")

    def test_gigachat_needs_credentials(self) -> None:
        with mock.patch.dict(llm.os.environ, {}, clear=True):
            with self.assertRaises(llm.LLMError):
                llm._make_backend("gigachat")

    def test_yandex_needs_folder(self) -> None:
        env = {"NEX_PROVIDER": "yandex", "YANDEX_API_KEY": "k"}
        with mock.patch.dict(llm.os.environ, env, clear=True):
            with self.assertRaises(llm.LLMError):
                llm._make_backend("yandex")


class TestBodies(unittest.TestCase):
    def test_openai_complete_parses_choices(self) -> None:
        be = bcompat.OpenAICompatBackend("k", base_url="https://x/v1", model="m")
        payload = {"choices": [{"message": {"content": "  привет  "},
                                "finish_reason": "stop"}],
                   "usage": {"completion_tokens": 5}}
        with mock.patch.object(bcompat, "post_json_retry", lambda *a, **k: payload):
            self.assertEqual(be.complete("s", "q"), "привет")
            text, used = be.structured("s", "q", {"type": "object"})
            self.assertEqual((text, used), ("привет", 5))

    def test_openai_stream_yields_deltas(self) -> None:
        be = bcompat.OpenAICompatBackend("k", base_url="https://x/v1", model="m")
        chunks = [{"choices": [{"delta": {"content": "a"}}]},
                  {"choices": [{"delta": {"content": "б"}}]}]
        with mock.patch.object(bcompat, "post_sse", lambda *a, **k: iter(chunks)):
            self.assertEqual(list(be.stream("s", "q")), ["a", "б"])

    def test_yandex_complete_parses_result(self) -> None:
        be = byandex.YandexBackend(api_key="k", folder_id="f")
        payload = {"result": {"alternatives": [{"message": {"text": " готово "}}],
                               "usage": {"completionTokens": 3}}}
        with mock.patch.object(byandex, "post_json_retry", lambda *a, **k: payload):
            self.assertEqual(be.complete("s", "q"), "готово")

    def test_gigachat_body_asks_json_object(self) -> None:
        be = bgiga.GigaChatBackend(client_id="id", client_secret="s")
        body = be._body("s", "q", [], 0.1, {"type": "object"}, False)
        self.assertEqual(body["response_format"], {"type": "json_object"})
        self.assertEqual(body["model"], "GigaChat")


class TestContentShapes(unittest.TestCase):
    """Content бывает и строкой, и списком чанков — оба разбираются."""
    """Content бывает и строкой, и списком чанков — оба разбираются."""

    def test_string_and_list(self) -> None:
        self.assertEqual(bbase.content_str("hi"), "hi")
        self.assertEqual(
            bbase.content_str([{"type": "text", "text": "a"},
                               {"type": "text", "text": "б"}]), "aб")
        self.assertEqual(bbase.content_str([{"type": "other"}]), "")
        self.assertEqual(bbase.content_str(None), "")
        self.assertEqual(bbase.content_str(42), "")

    def test_mistral_list_content_parses(self) -> None:
        import vliw.agent.backends.mistral as bmistral

        payload = {"choices": [{"message": {"content": [
            {"type": "text", "text": " serializers"},
            {"type": "text", "text": " ok"}]}, "finish_reason": "stop"}],
            "usage": {"completion_tokens": 2}}
        text, used = bmistral._text_of(payload)
        self.assertEqual(text, "serializers ok")
        self.assertEqual(used, 2)

    def test_structured_falls_back_to_json_object(self) -> None:
        import vliw.agent.backends.mistral as bmistral

        be = bmistral.MistralBackend("k", model="m")
        seen = []

        def fake_post(url, body, headers, timeout=60.0):
            seen.append(body.get("response_format", {}).get("type"))
            if len(seen) == 1:
                raise llm.LLMError("HTTP 400: strict failed")
            return {"choices": [{"message": {"content": "{}"},
                                 "finish_reason": "stop"}],
                    "usage": {"completion_tokens": 1}}

        with mock.patch.object(bmistral, "post_json_retry", fake_post):
            text, _ = be.structured("s", "q", {"type": "object"})
        self.assertEqual(text, "{}")
        self.assertEqual(seen, ["json_schema", "json_object"])

    def test_structured_reraises_non_schema_errors(self) -> None:
        import vliw.agent.backends.mistral as bmistral

        be = bmistral.MistralBackend("k", model="m")

        def fake_post(url, body, headers, timeout=60.0):
            raise llm.LLMError("HTTP 401: bad key")

        with mock.patch.object(bmistral, "post_json_retry", fake_post):
            with self.assertRaises(llm.LLMError):
                be.structured("s", "q", {"type": "object"})


class TestGigaChatTokenExpiry(unittest.TestCase):
    def _backend_with_token_response(self, payload: dict):
        import io
        import json as _json
        import urllib.request as _urlreq

        be = bgiga.GigaChatBackend(client_id="id", client_secret="s")

        class FakeResp:
            def __enter__(self):
                return io.BytesIO(_json.dumps(payload).encode())

            def __exit__(self, *a):
                return False

        return be, mock.patch.object(_urlreq, "urlopen", lambda *a, **k: FakeResp())

    def test_absolute_expiry_not_added_to_now(self) -> None:
        import time as _time

        exp_abs = int(_time.time()) + 1800  # так отдаёт Сбер: unix-время
        be, net = self._backend_with_token_response(
            {"access_token": "tok", "expires_at": exp_abs})
        with net:
            self.assertEqual(be._fetch_token(), "tok")
        # Было: now() + expires_at = токен «на десятилетия». Должно: ~exp-60.
        self.assertLess(abs(be._token_until - (exp_abs - 60)), 5)

    def test_relative_expiry(self) -> None:
        import time as _time

        be, net = self._backend_with_token_response(
            {"access_token": "tok", "expires_at": 1800})
        before = _time.time()
        with net:
            be._fetch_token()
        self.assertGreater(be._token_until, before + 1700)
        self.assertLess(be._token_until, before + 1800)


class TestYandexHeaders(unittest.TestCase):
    def test_iam_gets_folder_header(self) -> None:
        be = byandex.YandexBackend(iam_token="tok", folder_id="f")
        h = be._headers()
        self.assertEqual(h["Authorization"], "Bearer tok")
        self.assertEqual(h["x-folder-id"], "f")
        be = byandex.YandexBackend(api_key="k", folder_id="f")
        self.assertEqual(be._headers()["Authorization"], "Api-Key k")
        self.assertNotIn("x-folder-id", be._headers())
    def test_extracts_provider_message(self) -> None:
        raw = '{"error": {"message": "quota exceeded"}}'
        self.assertIn("quota", bbase._extract_error(raw))
        self.assertIn("oops", bbase._extract_error('{"message": "oops"}'))

    def test_exhausted_detection(self) -> None:
        self.assertTrue(bbase._is_exhausted("HTTP 429: quota exceeded"))
        self.assertFalse(bbase._is_exhausted("HTTP 401: bad key"))


class TestNormalizeProvider(unittest.TestCase):
    def test_canonical_and_aliases(self) -> None:
        self.assertEqual(llm.normalize_provider("deepseek"), "deepseek")
        self.assertEqual(llm.normalize_provider("LeChat"), "mistral")
        self.assertEqual(llm.normalize_provider("yandexgpt"), "yandex")
        self.assertEqual(llm.normalize_provider("openrouter"), "openrouter")

    def test_unknown_and_empty(self) -> None:
        self.assertIsNone(llm.normalize_provider("nosuch"))
        self.assertIsNone(llm.normalize_provider(""))
        self.assertEqual(llm.normalize_provider("local"), "local")


class TestEnvFile(unittest.TestCase):
    def test_roundtrip_preserves_comments(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as d:
            p = f"{d}/.env"
            with open(p, "w", encoding="utf-8") as f:
                f.write("# комментарий\nNEX_PROVIDER=mistral\nMISTRAL_API_KEY=old\n")
            written = envfile.save(p, {"MISTRAL_API_KEY": "new", "NEX_MODEL": "m",
                                       "GONE": None})
            self.assertEqual(sorted(written), ["MISTRAL_API_KEY", "NEX_MODEL"])
            data = envfile.load(p)
            self.assertEqual(data["MISTRAL_API_KEY"], "new")
            self.assertEqual(data["NEX_MODEL"], "m")
            text = Path(p).read_text(encoding="utf-8")
            self.assertIn("# комментарий", text)
            self.assertIn("NEX_PROVIDER=mistral", text)

    def test_delete_and_quoting(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as d:
            p = f"{d}/.env"
            with open(p, "w", encoding="utf-8") as f:
                f.write("NEX_MODEL=x\n")
            envfile.save(p, {"NEX_MODEL": None})
            self.assertNotIn("NEX_MODEL", envfile.load(p))
            envfile.save(p, {"NEX_API_KEY": "a b#c"})
            self.assertEqual(envfile.load(p)["NEX_API_KEY"], "a b#c")

    def test_mask_never_shows_full_key(self) -> None:
        secret = "sk-abcdefgh123456"
        shown = envfile.mask(secret)
        self.assertNotIn(secret, shown)
        self.assertIn("sk-", shown)
        self.assertEqual(envfile.mask("short"), "•×5")
        self.assertEqual(envfile.mask(""), "•×0")


class TestKeyUpdates(unittest.TestCase):
    def test_single_key_goes_to_provider_var(self) -> None:
        self.assertEqual(llm.key_updates("deepseek", ["sk-x"]),
                         {"DEEPSEEK_API_KEY": "sk-x"})
        self.assertEqual(llm.key_updates("custom", ["k"]),
                         {"NEX_API_KEY": "k"})

    def test_gigachat_pair_and_colon_form(self) -> None:
        self.assertEqual(llm.key_updates("gigachat", ["id", "sec"]),
                         {"GIGACHAT_CLIENT_ID": "id", "GIGACHAT_SECRET": "sec"})
        self.assertEqual(llm.key_updates("gigachat", ["id:sec"]),
                         {"GIGACHAT_CLIENT_ID": "id", "GIGACHAT_SECRET": "sec"})

    def test_bad_forms_raise_with_usage(self) -> None:
        with self.assertRaises(llm.LLMError):
            llm.key_updates("gigachat", ["lonely"])
        with self.assertRaises(llm.LLMError):
            llm.key_updates("mistral", [])
        with self.assertRaises(llm.LLMError):
            llm.key_updates("mistral", ["a", "b"])


class TestHumanError(unittest.TestCase):
    def test_maps_to_actions(self) -> None:
        self.assertIn("/key", llm._human_error("mistral", "ключ не задан для le chat"))
        out = llm._human_error("deepseek", "deepseek: HTTP 401: bad")
        self.assertIn("отклонён", out)
        self.assertIn("/key", out)
        out = llm._human_error("gemini", "gemini: HTTP 429: quota exceeded")
        self.assertIn("квота", out)
        self.assertIn("/ai", out)
        out = llm._human_error("openai", "openai: HTTP 404: no such model")
        self.assertIn("модель не найдена", out)
        self.assertIn("openai: HTTP 500: boom",
                      llm._human_error("openai", "openai: HTTP 500: boom"))

    def test_custom_shows_server_message_and_mangled_length(self) -> None:
        out = llm._human_error(
            "custom", 'custom: HTTP 401: {"error":{"message":"User not found.","code":401}}',
            key="k" * 146)
        self.assertIn("User not found", out)
        self.assertIn("146", out)
        self.assertIn("дважды", out)
        # HTTP-слой обычно уже извлёк message — эта форма тоже разбирается.
        out = llm._human_error("custom", "custom: HTTP 401: User not found.",
                               key="k" * 73)
        self.assertIn("User not found", out)
        self.assertNotIn("дважды", out)

    def test_check_reports_human_text(self) -> None:
        with mock.patch.object(llm, "provider", lambda: "mistral"), \
                mock.patch.object(llm, "complete",
                                  mock.Mock(side_effect=llm.LLMError("HTTP 401: no"))):
            ok, detail = llm.check()
            self.assertFalse(ok)
            self.assertIn("отклонён", detail)

    def test_check_spots_foreign_key(self) -> None:
        with mock.patch.object(llm, "provider", lambda: "mistral"), \
                mock.patch.object(llm, "complete",
                                  mock.Mock(side_effect=llm.LLMError("HTTP 401: no"))), \
                mock.patch.object(llm, "api_key", lambda: "xxsk-or-v1-yy"):
            ok, detail = llm.check()
            self.assertFalse(ok)
            self.assertIn("OpenRouter", detail)
            self.assertIn("/ai openrouter", detail)

    def test_misfit_hint_forms(self) -> None:
        self.assertIn("/ai gemini", llm._misfit_hint("mistral", "AIza123"))
        self.assertIn("/ai mistral", llm._misfit_hint("gemini", "long-enough-key"))
        self.assertIn("gigachat", llm._misfit_hint("mistral", "myid:mysecret"))
        self.assertIn("/ai vercel", llm._misfit_hint("mistral", "vck_abc123"))
        self.assertIn("/ai openrouter", llm._misfit_hint("custom", "sk-or-v1-abc"))
        self.assertEqual("", llm._misfit_hint("openrouter", "sk-or-v1-abc"))
        self.assertEqual("", llm._misfit_hint("mistral", ""))


class TestStatusHint(unittest.TestCase):
    def test_next_step_rendered(self) -> None:
        from vliw.ui import agent_view

        with mock.patch.object(llm, "provider", lambda: "mistral"), \
                mock.patch.object(llm, "describe", lambda: "le chat · m"), \
                mock.patch.object(llm, "is_local", lambda: False):
            lines = agent_view.render_status(
                False, "ключ не задан (le chat) — вставьте: /key <ключ>")
            text = "\n".join(lines)
            self.assertIn("Дальше: /key <ключ>", text)
            self.assertIn("/key <ключ>", text)
            self.assertNotIn("NEX_API_KEY", text)
            lines = agent_view.render_status(True, "le chat · m: готово")
            self.assertNotIn("Дальше:", "\n".join(lines))

    def test_foreign_key_hint_wins_over_reinsert(self) -> None:
        from vliw.ui import agent_view

        with mock.patch.object(llm, "provider", lambda: "mistral"), \
                mock.patch.object(llm, "describe", lambda: "le chat · m"), \
                mock.patch.object(llm, "is_local", lambda: False):
            detail = ("ключ отклонён (le chat) — вставьте заново: /key <ключ>. "
                      "похоже на ключ OpenRouter (sk-or-v1-…) — ему нужен: "
                      "/ai openrouter key=...")
            text = "\n".join(agent_view.render_status(False, detail))
            self.assertIn("Дальше: /ai openrouter", text)


class TestKeySourceHint(unittest.TestCase):
    def test_hint_has_url(self) -> None:
        self.assertIn("console.mistral.ai", llm.key_source_hint("mistral"))
        self.assertIn("Ollama", llm.key_source_hint("custom"))
        self.assertIn("yandex", llm.key_source_hint("yandex").lower())

    def test_no_key_error_points_to_source(self) -> None:
        out = llm._human_error("mistral", "ключ не задан для le chat")
        self.assertIn("/key <ключ>", out)
        self.assertIn("console.mistral.ai", out)


class TestKeyGuide(unittest.TestCase):
    def test_bare_key_prints_guide_not_form_error(self) -> None:
        import tempfile

        from vliw import cli

        with tempfile.TemporaryDirectory() as d:
            out = _run_cmd(cli.cmd_key, "", d)
            self.assertIn("Что такое ключ", out)
            self.assertIn("console.mistral.ai", out)
            self.assertIn("/ai mistral key=...", out)
            self.assertNotIn("форма:", out)
            self.assertEqual(envfile.load(f"{d}/.env"), {})


class TestLooksLikeKey(unittest.TestCase):
    def test_questions_are_not_keys(self) -> None:
        for q in ("привет", "почему этот участок медленный?", "что это",
                  "спасибо", "/key abc", "", "slotclash"):
            with self.subTest(q=q):
                self.assertFalse(llm.looks_like_key_text(q))

    def test_key_shapes_are_keys(self) -> None:
        self.assertTrue(llm.looks_like_key_text("k" * 32))
        self.assertTrue(llm.looks_like_key_text("sk-or-v1-abc"))
        self.assertTrue(llm.looks_like_key_text("AIzaSyD-abc"))
        self.assertTrue(llm.looks_like_key_text("myid:mysecret"))
        self.assertTrue(llm.looks_like_key_text("i" * 36 + " " + "s" * 40))


class TestRepairPastedKey(unittest.TestCase):
    def test_clean_key_untouched(self) -> None:
        clean, notes = llm.repair_pasted_key("sk-or-v1-" + "a" * 64)
        self.assertEqual(clean, "sk-or-v1-" + "a" * 64)
        self.assertEqual(notes, [])

    def test_exact_double_collapses(self) -> None:
        half = "k" * 32
        clean, notes = llm.repair_pasted_key(half + half)
        self.assertEqual(clean, half)
        self.assertTrue(notes)

    def test_real_world_double_openrouter_key(self) -> None:
        """Живой случай: 146 символов = дважды склеенный ключ на 73."""
        real = "sk-or-v1-" + "a" * 64
        self.assertEqual(len(real), 73)
        clean, notes = llm.repair_pasted_key(real + real)
        self.assertEqual(clean, real)
        self.assertTrue(notes)


class TestGigachatReadyKey(unittest.TestCase):
    """Готовый ключ Сбера — base64(id:secret) одной строкой."""

    def _b64(self, cid: str, sec: str) -> str:
        import base64

        return base64.b64encode(f"{cid}:{sec}".encode()).decode()

    def test_decode_roundtrip(self) -> None:
        cid, sec = "11111111-2222-3333-4444-555555555555", "s" * 32
        got = llm.try_decode_gigachat_key(self._b64(cid, sec))
        self.assertEqual(got, (cid, sec))

    def test_rejects_foreign_shapes(self) -> None:
        self.assertIsNone(llm.try_decode_gigachat_key("k" * 32))
        self.assertIsNone(llm.try_decode_gigachat_key("sk-or-v1-abc"))
        self.assertIsNone(llm.try_decode_gigachat_key("AIza123"))
        self.assertIsNone(llm.try_decode_gigachat_key("not-base64!!!"))
        self.assertIsNone(llm.try_decode_gigachat_key(""))
        self.assertIsNone(llm.try_decode_gigachat_key("a:b"))  # короткие части

    def test_adopt_detects_ready_key(self) -> None:
        import tempfile

        cid, sec = "11111111-2222-3333-4444-555555555555", "s" * 32
        with tempfile.TemporaryDirectory() as d:
            with mock.patch.object(llm, "_PROJECT_ROOT", Path(d)), \
                    mock.patch.dict(os.environ, {}, clear=True):
                label, shown, notes = llm.adopt_pasted_key(self._b64(cid, sec))
                self.assertEqual(os.environ["NEX_PROVIDER"], "gigachat")
                self.assertEqual(os.environ["GIGACHAT_CLIENT_ID"], cid)
                self.assertEqual(os.environ["GIGACHAT_SECRET"], sec)
                self.assertIn("пару", " ".join(notes))
                self.assertNotIn(cid, shown)
        _ = label


class TestVercelBackend(unittest.TestCase):
    def test_factory_defaults(self) -> None:
        with mock.patch.dict(os.environ, {"NEX_API_KEY": "vck_123"},
                             clear=True), \
                mock.patch.object(llm, "_dotenv_values", lambda: {}):
            be = llm._make_backend("vercel")
            self.assertEqual(be._base_url, "https://ai-gateway.vercel.sh/v1")
            self.assertTrue(be._model)

    def test_alias_and_key_var(self) -> None:
        self.assertEqual(llm.normalize_provider("vercel"), "vercel")
        self.assertEqual(llm.KEY_VAR["vercel"], "VERCEL_API_KEY")
        self.assertIn("vercel", llm.PROVIDERS)

    def test_prefix_junk_cut(self) -> None:
        clean, notes = llm.repair_pasted_key("misterialsk-or-v1-" + "b" * 64)
        self.assertEqual(clean, "sk-or-v1-" + "b" * 64)
        self.assertTrue(notes)

    def test_overlong_tail_cut(self) -> None:
        clean, notes = llm.repair_pasted_key("sk-or-v1-" + "c" * 100)
        self.assertEqual(len(clean), 73)
        self.assertTrue(notes)

    def test_short_garbage_untouched(self) -> None:
        clean, notes = llm.repair_pasted_key("misterial")
        self.assertEqual(clean, "misterial")
        self.assertEqual(notes, [])

    def test_adopt_reports_repair(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as d:
            with mock.patch.object(llm, "_PROJECT_ROOT", Path(d)), \
                    mock.patch.dict(os.environ, {}, clear=True):
                label, shown, notes = llm.adopt_pasted_key(
                    "misterialsk-or-v1-" + "d" * 64)
                self.assertEqual(label, "openrouter")
                self.assertTrue(notes)
                self.assertNotIn("misterial",
                                 os.environ.get("OPENROUTER_API_KEY", ""))
                self.assertEqual(len(os.environ["OPENROUTER_API_KEY"]), 73)


class TestAdoptPastedKey(unittest.TestCase):
    """Вставка — только в память сессии: на диск ничего не пишется."""

    def _adopt(self, text: str, extra: dict | None = None):
        import tempfile

        with tempfile.TemporaryDirectory() as d:
            env = dict(extra or {})
            with mock.patch.object(llm, "_PROJECT_ROOT", Path(d)), \
                    mock.patch.dict(os.environ, env, clear=True):
                label_shown = llm.adopt_pasted_key(text)
                left_file = Path(d, ".env").exists()
                return label_shown, left_file, dict(os.environ)

    def test_plain_key_goes_to_mistral(self) -> None:
        (label, shown, _), left_file, environ = self._adopt("k" * 32)
        self.assertEqual(label, "le chat")
        self.assertEqual(environ["NEX_PROVIDER"], "mistral")
        self.assertEqual(environ["MISTRAL_API_KEY"], "k" * 32)
        self.assertNotIn("k" * 32, shown)
        self.assertFalse(left_file, "вставка не должна писать на диск")

    def test_openrouter_key_sets_openrouter_provider(self) -> None:
        (label, _, _), _, environ = self._adopt("sk-or-v1-abc123")
        self.assertEqual(environ["NEX_PROVIDER"], "openrouter")
        self.assertEqual(environ["OPENROUTER_API_KEY"], "sk-or-v1-abc123")
        self.assertEqual(label, "openrouter")
        self.assertNotIn("NEX_BASE_URL", environ)

    def test_openrouter_keeps_existing_url(self) -> None:
        (_, _, _), _, environ = self._adopt(
            "sk-or-v1-abc123", {"NEX_BASE_URL": "https://my/proxy/v1"})
        self.assertEqual(environ["NEX_PROVIDER"], "openrouter")
        self.assertEqual(environ["NEX_BASE_URL"], "https://my/proxy/v1")

    def test_gemini_and_gigachat_shapes(self) -> None:
        (label, _, _), _, environ = self._adopt("AIzaSyD-abc")
        self.assertEqual(environ["NEX_PROVIDER"], "gemini")
        (label, _, _), _, environ = self._adopt("i" * 36 + " " + "s" * 40)
        self.assertEqual(environ["NEX_PROVIDER"], "gigachat")
        self.assertEqual(environ["GIGACHAT_CLIENT_ID"], "i" * 36)

    def test_empty_raises(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as d:
            with mock.patch.object(llm, "_PROJECT_ROOT", Path(d)), \
                    mock.patch.dict(os.environ, {}, clear=True):
                with self.assertRaises(llm.LLMError):
                    llm.adopt_pasted_key("   ")

    def test_has_session_key_sees_memory_only(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as d:
            Path(d, ".env").write_text("NEX_PROVIDER=mistral\n"
                                       "MISTRAL_API_KEY=filekey\n",
                                       encoding="utf-8")
            with mock.patch.object(llm, "_PROJECT_ROOT", Path(d)), \
                    mock.patch.dict(os.environ, {}, clear=True):
                # Ключ есть в файле, но не в сессии — просьба нужна.
                self.assertFalse(llm.has_session_key())
            with mock.patch.object(llm, "_PROJECT_ROOT", Path(d)), \
                    mock.patch.dict(os.environ, {"NEX_API_KEY": "k" * 32},
                                    clear=True):
                self.assertTrue(llm.has_session_key())


class TestModelCatalog(unittest.TestCase):
    def test_locked_without_key_no_network(self) -> None:
        from vliw.agent import models as catalog

        with mock.patch.object(catalog, "_fetch_json") as fetch:
            for prov in ("mistral", "gemini", "openai", "deepseek", "qwen",
                         "kimi", "grok", "anthropic", "glm", "muse",
                         "openrouter", "vercel", "gigachat"):
                with self.subTest(prov=prov):
                    self.assertEqual(catalog.catalog(prov), ([], "locked"))
            fetch.assert_not_called()

    def test_hidden_and_unsupported(self) -> None:
        from vliw.agent import models as catalog

        self.assertEqual(catalog.catalog("custom"), ([], "text"))
        self.assertEqual(catalog.catalog("local"), ([], "text"))
        self.assertEqual(catalog.catalog("nosuch"), ([], "text"))
        self.assertEqual(catalog.catalog("yandex", api_key="k"),
                         ([], "unsupported"))

    def test_openrouter_live_free_first(self) -> None:
        from vliw.agent import models as catalog

        payload = {"data": [{"id": "b-paid", "name": "B"},
                            {"id": "a-free:free", "name": "A"},
                            {"id": "c-paid", "name": "C"}]}
        try:
            with mock.patch.object(catalog, "_fetch_json",
                                   return_value=payload) as fetch:
                rows, src = catalog.catalog("openrouter", api_key="k")
                self.assertEqual(src, "live")
                self.assertEqual([r.id for r in rows],
                                 ["a-free:free", "b-paid", "c-paid"])
                self.assertTrue(rows[0].free)
                self.assertEqual(fetch.call_args.args[0],
                                 "https://openrouter.ai/api/v1/models")
        finally:
            catalog.reset_cache()

    def test_mistral_live_with_key(self) -> None:
        from vliw.agent import models as catalog

        payload = {"data": [{"id": "m1"}, {"id": "m2"}]}
        try:
            with mock.patch.object(catalog, "_fetch_json",
                                   return_value=payload) as fetch:
                rows, src = catalog.catalog("mistral", api_key="k")
                self.assertEqual(src, "live")
                self.assertEqual([r.id for r in rows], ["m1", "m2"])
                self.assertEqual(fetch.call_args.args[0],
                                 "https://api.mistral.ai/v1/models")
                self.assertIn("Bearer k", fetch.call_args.args[1][
                    "Authorization"])
        finally:
            catalog.reset_cache()

    def test_gemini_parses_names_and_skips_non_chat(self) -> None:
        from vliw.agent import models as catalog

        payload = {"models": [
            {"name": "models/gemini-2.5-flash", "displayName": "Flash",
             "supportedGenerationMethods": ["generateContent"]},
            {"name": "models/tts-1", "displayName": "TTS",
             "supportedGenerationMethods": ["generateSpeech"]},
        ]}
        try:
            with mock.patch.object(catalog, "_fetch_json",
                                   return_value=payload):
                rows, src = catalog.catalog("gemini", api_key="k")
                self.assertEqual(src, "live")
                self.assertEqual([(r.id, r.label) for r in rows],
                                 [("gemini-2.5-flash", "Flash")])
        finally:
            catalog.reset_cache()

    def test_anthropic_parses_display_names(self) -> None:
        from vliw.agent import models as catalog

        payload = {"data": [{"id": "claude-x", "display_name": "Claude X"}]}
        try:
            with mock.patch.object(catalog, "_fetch_json",
                                   return_value=payload) as fetch:
                rows, src = catalog.catalog("anthropic", api_key="k")
                self.assertEqual(src, "live")
                self.assertEqual([(r.id, r.label) for r in rows],
                                 [("claude-x", "Claude X")])
                self.assertEqual(fetch.call_args.args[1]["x-api-key"], "k")
        finally:
            catalog.reset_cache()

    def test_bad_key_raises_actionable_error(self) -> None:
        from vliw.agent import models as catalog

        with mock.patch.object(
                catalog, "_fetch_json",
                side_effect=catalog.LLMError("ключ отклонён (HTTP 401)")):
            with self.assertRaises(catalog.LLMError) as ctx:
                catalog.catalog("mistral", api_key="bad")
            self.assertIn("отклонён", str(ctx.exception))

    def test_local_loopback_only(self) -> None:
        from vliw.agent import models as catalog

        self.assertEqual(catalog.local_base_url("http://localhost:11434/v1"),
                         "http://localhost:11434/v1")
        with self.assertRaises(ValueError):
            catalog.local_base_url("https://example.com/v1")
        with self.assertRaises(catalog.LLMError):
            catalog.catalog("local-server",
                            base_url="https://example.com/v1")


class TestProviderUpdates(unittest.TestCase):
    def test_model_set_and_cleared(self) -> None:
        with mock.patch.dict(os.environ, {}, clear=True):
            u = llm.provider_updates("deepseek", {"model": "m"})
            self.assertEqual(u["NEX_MODEL"], "m")
            self.assertEqual(u["NEX_PROVIDER"], "deepseek")
        with mock.patch.dict(os.environ, {"NEX_MODEL": "x"}, clear=True):
            u = llm.provider_updates("deepseek", {})
            self.assertIsNone(u["NEX_MODEL"])

    def test_required_fields_raise(self) -> None:
        with mock.patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(llm.LLMError):
                llm.provider_updates("custom", {"model": "m"})
            with self.assertRaises(llm.LLMError):
                llm.provider_updates("yandex", {})
            with self.assertRaises(llm.LLMError):
                llm.provider_updates("gigachat", {})

    def test_yandex_gigachat_model_vars(self) -> None:
        with mock.patch.dict(os.environ, {}, clear=True):
            u = llm.provider_updates("yandex", {"folder": "f", "model": "ym"})
            self.assertEqual(u["YANDEX_MODEL"], "ym")
            self.assertNotIn("NEX_MODEL", u)
            u = llm.provider_updates("gigachat", {"id": "i", "secret": "s"})
            self.assertNotIn("NEX_MODEL", u)


class TestEnvPersistence(unittest.TestCase):
    """Настройки из `.env` работают без переменных окружения (как после рестарта)."""

    def _env(self, tmp: str, dotenv: str = ""):
        if dotenv:
            Path(f"{tmp}/.env").write_text(dotenv, encoding="utf-8")
        return (mock.patch.object(llm, "_PROJECT_ROOT", Path(tmp)),
                mock.patch.dict(os.environ, {}, clear=True),
                mock.patch.object(llm.local, "ready", lambda: False))

    def test_provider_from_dotenv(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as d:
            a, b, c = self._env(d, "NEX_PROVIDER=deepseek\n")
            with a, b, c:
                self.assertEqual(llm.provider(), "deepseek")

    def test_env_beats_dotenv(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as d:
            a, _, c = self._env(d, "NEX_PROVIDER=deepseek\n")
            with a, mock.patch.dict(os.environ, {"NEX_PROVIDER": "mistral"},
                                    clear=True), c:
                self.assertEqual(llm.provider(), "mistral")

    def test_generic_key_in_dotenv_fits(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as d:
            a, b, c = self._env(d, "NEX_PROVIDER=mistral\nNEX_API_KEY=abc123\n")
            with a, b, c:
                self.assertEqual(llm.api_key(), "abc123")
                self.assertTrue(llm.available())

    def test_specific_key_beats_generic_in_dotenv(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as d:
            a, b, c = self._env(
                d, "NEX_API_KEY=generic\nMISTRAL_API_KEY=specific\n")
            with a, b, c, mock.patch.dict(os.environ, {"NEX_PROVIDER": "mistral"},
                                          clear=True):
                self.assertEqual(llm.api_key(), "specific")

    def test_custom_url_from_dotenv(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as d:
            a, b, c = self._env(
                d, "NEX_PROVIDER=custom\nNEX_API_KEY=k\n"
                   "NEX_BASE_URL=https://x/v1\nNEX_MODEL=m\n")
            with a, b, c:
                be = llm._make_backend("custom")
                self.assertEqual(be._base_url, "https://x/v1")
                self.assertEqual(be._model, "m")


def _run_cmd(fn, arg: str, tmp: str, extra: dict | None = None) -> str:
    """Вызвать CLI-команду с временным `.env` и чистым окружением."""
    env = {"NEX_PROVIDER": "mistral"}
    env.update(extra or {})
    buf = io.StringIO()
    with mock.patch.object(llm, "_PROJECT_ROOT", Path(tmp)), \
            mock.patch.dict(os.environ, env, clear=True), \
            mock.patch.object(llm, "check", lambda: (True, "ok")), \
            contextlib.redirect_stdout(buf):
        fn(None, arg)
    return buf.getvalue()


class TestCliAiKey(unittest.TestCase):
    """`/ai <провайдер>` и `/key <ключ>`: смена, память сессии, маскировка.

    Команды пишут ТОЛЬКО в память процесса (на диск — ничего): закрыл
    терминал — настроек нет. Поэтому тесты смотрят в окружение, а не в файл.
    """

    def _run_mem(self, fn, arg: str, extra: dict | None = None):
        """Команда с пустым окружением. Возвращает (вывод, окружение, файл?)."""
        import tempfile

        from vliw import cli  # noqa: F401 — импорт ради побочного эффекта

        with tempfile.TemporaryDirectory() as d:
            env = {"NEX_PROVIDER": "mistral"}
            env.update(extra or {})
            buf = io.StringIO()
            with mock.patch.object(llm, "_PROJECT_ROOT", Path(d)), \
                    mock.patch.dict(os.environ, env, clear=True), \
                    mock.patch.object(llm, "check", lambda: (True, "ok")), \
                    contextlib.redirect_stdout(buf):
                fn(None, arg)
                return buf.getvalue(), dict(os.environ), Path(d, ".env").exists()

    def test_ai_switch_sets_provider_and_clears_foreign_model(self) -> None:
        from vliw import cli

        out, environ, left_file = self._run_mem(
            cli.cmd_ai, "deepseek", {"NEX_MODEL": "deepseek-chat"})
        self.assertEqual(environ["NEX_PROVIDER"], "deepseek")
        self.assertNotIn("NEX_MODEL", environ)
        self.assertFalse(left_file, "команда не должна писать на диск")
        _ = out

    def test_ai_unknown_and_custom_without_url(self) -> None:
        import tempfile

        from vliw import cli

        with tempfile.TemporaryDirectory() as d:
            out = _run_cmd(cli.cmd_ai, "nosuch", d)
            self.assertIn("неизвестный провайдер", out)
            out = _run_cmd(cli.cmd_ai, "custom model=m", d)
            self.assertIn("нужен адрес сервера", out)
            self.assertEqual(envfile.load(f"{d}/.env"), {})

    def test_ai_custom_and_gigachat_forms(self) -> None:
        from vliw import cli

        _, environ, left_file = self._run_mem(
            cli.cmd_ai, "custom url=https://x/v1 model=m1")
        self.assertEqual(environ["NEX_BASE_URL"], "https://x/v1")
        self.assertEqual(environ["NEX_MODEL"], "m1")
        _, environ, _ = self._run_mem(cli.cmd_ai, "gigachat id=abc secret=def")
        self.assertEqual(environ["GIGACHAT_CLIENT_ID"], "abc")
        self.assertEqual(environ["GIGACHAT_SECRET"], "def")
        self.assertFalse(left_file)

    def test_ai_one_shot_with_key(self) -> None:
        from vliw import cli

        out, environ, left_file = self._run_mem(
            cli.cmd_ai, "deepseek key=sk-oneshot model=deepseek-chat")
        self.assertEqual(environ["NEX_PROVIDER"], "deepseek")
        self.assertEqual(environ["DEEPSEEK_API_KEY"], "sk-oneshot")
        self.assertEqual(environ["NEX_MODEL"], "deepseek-chat")
        self.assertNotIn("sk-oneshot", out)
        out, environ, _ = self._run_mem(cli.cmd_ai, "gigachat key=myid:mysec")
        self.assertEqual(environ["GIGACHAT_CLIENT_ID"], "myid")
        self.assertNotIn("mysec", out)
        self.assertFalse(left_file)

    def test_ai_spaced_equals_parsed(self) -> None:
        """`key = abc` с пробелами — раньше ключ молча терялся (видели живьём)."""
        from vliw import cli

        out, environ, _ = self._run_mem(cli.cmd_ai, "vercel key = vck_test123")
        self.assertEqual(environ["NEX_PROVIDER"], "vercel")
        self.assertEqual(environ["VERCEL_API_KEY"], "vck_test123")
        self.assertNotIn("vck_test123", out)

    def test_adopt_detects_vercel(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as d:
            with mock.patch.object(llm, "_PROJECT_ROOT", Path(d)), \
                    mock.patch.dict(os.environ, {}, clear=True):
                label, _, _ = llm.adopt_pasted_key("vck_test12345678901234567890")
                self.assertEqual(os.environ["NEX_PROVIDER"], "vercel")
                self.assertEqual(label, "vercel")

    def test_key_sets_memory_and_masks(self) -> None:
        from vliw import cli

        out, environ, left_file = self._run_mem(cli.cmd_key, "sk-abcdefgh123456")
        self.assertNotIn("sk-abcdefgh123456", out)
        self.assertIn("MISTRAL_API_KEY", out)
        self.assertEqual(environ["MISTRAL_API_KEY"], "sk-abcdefgh123456")
        self.assertFalse(left_file)

    def test_key_gigachat_pair(self) -> None:
        from vliw import cli

        out, environ, left_file = self._run_mem(
            cli.cmd_key, "myid mysecret", {"NEX_PROVIDER": "gigachat"})
        self.assertEqual(environ["GIGACHAT_CLIENT_ID"], "myid")
        self.assertEqual(environ["GIGACHAT_SECRET"], "mysecret")
        self.assertNotIn("mysecret", out)
        self.assertFalse(left_file)


if __name__ == "__main__":
    unittest.main()
