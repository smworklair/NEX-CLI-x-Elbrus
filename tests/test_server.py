"""Persistent llama-server transport tests: AF_UNIX socket, HTTP, and SSE parsing.

Uses a lightweight mock server over AF_UNIX emitting `llama-server`-style SSE
chunks (no 2.1 GB weights required) to verify socket connection, `data:` line
parsing, `stop` termination, and clean connection teardown on cancellation.
"""

from __future__ import annotations

import json
import os
import shutil
import socket
import tempfile
import threading
import unittest

from vliw.learned import runtime
from vliw.learned.server import LlamaServer, ServerError


def _sse(payloads: list[dict]) -> bytes:
    body = b"".join(b"data: " + json.dumps(p).encode() + b"\n\n"
                    for p in payloads)
    return (b"HTTP/1.1 200 OK\r\n"
            b"Content-Type: text/event-stream\r\n"
            b"Connection: close\r\n\r\n" + body)


class FakeServer:
    """Mock AF_UNIX HTTP server returning a scripted response per connection."""

    def __init__(self, response: bytes, status_line: bytes | None = None):
        self.dir = tempfile.mkdtemp(prefix="nex-test-")
        self.path = os.path.join(self.dir, "l.sock")
        self.response = response
        self.requests: list[bytes] = []
        self._sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self._sock.bind(self.path)
        self._sock.listen(4)
        self._stop = False
        self._thread = threading.Thread(target=self._serve, daemon=True)
        self._thread.start()

    def _serve(self) -> None:
        """Serve each connection in its own thread to match real llama-server concurrency."""
        while not self._stop:
            try:
                conn, _ = self._sock.accept()
            except OSError:
                return
            threading.Thread(target=self._handle, args=(conn,),
                             daemon=True).start()

    def _handle(self, conn) -> None:
        try:
            conn.settimeout(2.0)
            self.requests.append(self._read_request(conn))
            conn.sendall(self.response)
        except OSError:
            pass
        finally:
            conn.close()

    @staticmethod
    def _read_request(conn) -> bytes:
        """Read the full HTTP request (headers + Content-Length body) before responding."""
        buf = b""
        while b"\r\n\r\n" not in buf:
            part = conn.recv(65536)
            if not part:
                return buf
            buf += part
        head, _, body = buf.partition(b"\r\n\r\n")
        want = 0
        for line in head.split(b"\r\n"):
            if line.lower().startswith(b"content-length:"):
                want = int(line.split(b":", 1)[1])
        while len(body) < want:
            part = conn.recv(65536)
            if not part:
                break
            body += part
        return head + b"\r\n\r\n" + body

    def close(self) -> None:
        self._stop = True
        self._sock.close()
        shutil.rmtree(self.dir, ignore_errors=True)


def _server_at(path: str) -> LlamaServer:
    """Create a `LlamaServer` pointed at an existing socket without spawning a process."""
    srv = LlamaServer(binary=None, base_gguf=None, adapters=[], threads=2,
                      ctx=2048, env={})
    srv._sock = path
    return srv


@unittest.skipUnless(hasattr(socket, "AF_UNIX"),
                     "AF_UNIX unavailable on this platform (Windows): "
                     "llama-server transport is tested on POSIX")
class TestCompletionStream(unittest.TestCase):

    def test_chunks_arrive_and_stop_flag_ends_the_stream(self) -> None:
        fake = FakeServer(_sse([
            {"content": "0: ", "stop": False},
            {"content": "такт=0 ", "stop": False},
            {"content": "канал=1\n", "stop": False},
            {"content": "", "stop": True, "stop_type": "eos"},
            {"content": "AFTER STOP", "stop": False},
        ]))
        self.addCleanup(fake.close)
        got = list(_server_at(fake.path).complete("prompt", 64))
        self.assertEqual("".join(got), "0: такт=0 канал=1\n")

    def test_prompt_and_settings_reach_the_server(self) -> None:
        """Default temperature=0.0 is deterministic and omits `seed` when unset."""
        fake = FakeServer(_sse([{"content": "x", "stop": True}]))
        self.addCleanup(fake.close)
        list(_server_at(fake.path).complete("my prompt", 123))
        body = json.loads(fake.requests[0].split(b"\r\n\r\n", 1)[1])
        self.assertEqual(body["prompt"], "my prompt")
        self.assertEqual(body["n_predict"], 123)
        self.assertEqual(body["temperature"], 0)
        self.assertNotIn("seed", body)     # omit seed when not explicitly passed
        self.assertTrue(body["stream"])

    def test_sampling_reaches_the_server(self) -> None:
        """temperature and seed for best-of sampling are forwarded verbatim to /completion."""
        fake = FakeServer(_sse([{"content": "x", "stop": True}]))
        self.addCleanup(fake.close)
        list(_server_at(fake.path).complete("prompt", 8, temperature=0.7, seed=42))
        body = json.loads(fake.requests[0].split(b"\r\n\r\n", 1)[1])
        self.assertEqual(body["temperature"], 0.7)
        self.assertEqual(body["seed"], 42)

    def test_cancel_closes_the_connection(self) -> None:
        """Closing the generator mid-stream tears down cleanly without hanging."""
        fake = FakeServer(_sse([{"content": f"{i}\n", "stop": False}
                                for i in range(50)]))
        self.addCleanup(fake.close)
        gen = _server_at(fake.path).complete("prompt", 999)
        self.assertEqual(next(gen), "0\n")
        gen.close()          # must neither raise nor hang

    def test_non_200_is_an_expected_failure(self) -> None:
        """HTTP server errors raise `ServerError`, not raw stdlib exceptions."""
        body = "not ready".encode()
        fake = FakeServer(b"HTTP/1.1 503 Service Unavailable\r\n"
                          + f"Content-Length: {len(body)}\r\n\r\n".encode()
                          + body)
        self.addCleanup(fake.close)
        with self.assertRaises(ServerError):
            list(_server_at(fake.path).complete("prompt", 8))


class TestThreadDefault(unittest.TestCase):
    """Default thread count is half of logical CPU cores."""

    def test_half_of_logical_cores(self) -> None:
        import unittest.mock as mock

        for cores, want in ((1, 2), (4, 2), (12, 6), (16, 8), (64, 8)):
            with self.subTest(cores=cores):
                with mock.patch.object(runtime.os, "cpu_count", lambda: cores):
                    self.assertEqual(runtime.default_threads(), want)


if __name__ == "__main__":
    unittest.main()
