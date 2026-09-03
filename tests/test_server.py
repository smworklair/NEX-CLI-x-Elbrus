"""Транспорт к постоянному llama-server: UNIX-сокет, HTTP, разбор SSE.

Настоящий сервер здесь НЕ поднимается: он грузит 2.1 ГБ весов, и тест из-за
этого не шёл бы ни в CI, ни на чужой машине. Вместо него — поддельный сервер
на таком же UNIX-сокете, отвечающий такими же кусками SSE, какие даёт
`llama-server` (проверено вживую на сборке b10488). Проверяется ровно то, что
написано у нас: соединение через AF_UNIX, разбор `data:`-строк, остановка по
флагу `stop` и закрытие соединения при отмене.

Почему это стоит теста: разбор потока — единственное место, где мы полагаемся
на формат чужой программы. Смена формата в новой сборке llama.cpp проявится
здесь, а не молчаливым «модель ничего не написала».
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
    """Один UNIX-сокет, один заготовленный ответ на каждое соединение."""

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
        """Каждое соединение — в своём потоке.

        Раньше цикл обслуживал их по одному, и тест был флакающим: одно
        падение на пять прогонов. Пока поток сидел в `sendall` отменённого
        запроса (клиент уже ушёл, ядро копит EPIPE), следующее соединение
        ждало в очереди, и клиент получал разрыв на отправке заголовков.
        Настоящий llama-server держит слоты параллельно — подставной должен
        вести себя так же, иначе он проверяет не то.
        """
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
        """Прочитать запрос ЦЕЛИКОМ: заголовки и тело по Content-Length.

        Одного `recv` не хватало, и это была вторая причина флака (первая —
        последовательный `accept`, см. `_serve`). `http.client` отправляет
        заголовки и тело разными вызовами. Подставной сервер успевал
        прочитать 126 байт заголовков, ответить и ЗАКРЫТЬ сокет — а клиент в
        этот момент ещё дописывал тело и получал EPIPE прямо на
        `conn.request`. Отсюда и обманчивая картина в отчёте: падал тест
        отмены, хотя до отмены дело не доходило вовсе.

        Настоящий сервер читает запрос до конца, и подставной обязан вести
        себя так же, иначе он проверяет не тот протокол.
        """
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
    """`LlamaServer`, указывающий на готовый сокет: без запуска процесса."""
    srv = LlamaServer(binary=None, base_gguf=None, adapters=[], threads=2,
                      ctx=2048, env={})
    srv._sock = path
    return srv


class TestCompletionStream(unittest.TestCase):

    def test_chunks_arrive_and_stop_flag_ends_the_stream(self) -> None:
        fake = FakeServer(_sse([
            {"content": "0: ", "stop": False},
            {"content": "такт=0 ", "stop": False},
            {"content": "канал=1\n", "stop": False},
            {"content": "", "stop": True, "stop_type": "eos"},
            {"content": "ЭТО УЖЕ ПОСЛЕ stop", "stop": False},
        ]))
        self.addCleanup(fake.close)
        got = list(_server_at(fake.path).complete("промпт", 64))
        self.assertEqual("".join(got), "0: такт=0 канал=1\n")

    def test_prompt_and_settings_reach_the_server(self) -> None:
        """Температура 0 — не украшение: на ней сняты все замеры."""
        fake = FakeServer(_sse([{"content": "x", "stop": True}]))
        self.addCleanup(fake.close)
        list(_server_at(fake.path).complete("мой промпт", 123))
        body = json.loads(fake.requests[0].split(b"\r\n\r\n", 1)[1])
        self.assertEqual(body["prompt"], "мой промпт")
        self.assertEqual(body["n_predict"], 123)
        self.assertEqual(body["temperature"], 0)
        self.assertNotIn("seed", body)     # без явного seed его нет и в запросе
        self.assertTrue(body["stream"])

    def test_sampling_reaches_the_server(self) -> None:
        """temperature/seed для best-of доходят до /completion как есть."""
        fake = FakeServer(_sse([{"content": "x", "stop": True}]))
        self.addCleanup(fake.close)
        list(_server_at(fake.path).complete("промпт", 8, temperature=0.7, seed=42))
        body = json.loads(fake.requests[0].split(b"\r\n\r\n", 1)[1])
        self.assertEqual(body["temperature"], 0.7)
        self.assertEqual(body["seed"], 42)

    def test_cancel_closes_the_connection(self) -> None:
        """Отмена на середине потока не оставляет соединение висеть."""
        fake = FakeServer(_sse([{"content": f"{i}\n", "stop": False}
                                for i in range(50)]))
        self.addCleanup(fake.close)
        gen = _server_at(fake.path).complete("промпт", 999)
        self.assertEqual(next(gen), "0\n")
        gen.close()          # не должно ни падать, ни висеть

    def test_non_200_is_an_expected_failure(self) -> None:
        """Отказ сервера — `ServerError`, а не голое исключение из stdlib."""
        body = "не готов".encode()
        fake = FakeServer(b"HTTP/1.1 503 Service Unavailable\r\n"
                          + f"Content-Length: {len(body)}\r\n\r\n".encode()
                          + body)
        self.addCleanup(fake.close)
        with self.assertRaises(ServerError):
            list(_server_at(fake.path).complete("промпт", 8))


class TestThreadDefault(unittest.TestCase):
    """Число потоков — половина логических ядер, см. замер в `default_threads`."""

    def test_half_of_logical_cores(self) -> None:
        import unittest.mock as mock

        for cores, want in ((1, 2), (4, 2), (12, 6), (16, 8), (64, 8)):
            with self.subTest(cores=cores):
                with mock.patch.object(runtime.os, "cpu_count", lambda: cores):
                    self.assertEqual(runtime.default_threads(), want)


if __name__ == "__main__":
    unittest.main()
