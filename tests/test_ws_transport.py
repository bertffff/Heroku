# ©️ Codrago, 2024-2030
# This file is a part of Heroku Userbot
# 🌐 https://github.com/Heroku-userbot/Heroku
# You can redistribute it and/or modify it under the terms of the GNU AGPLv3
# 🔑 https://www.gnu.org/licenses/agpl-3.0.html

"""WebSocket MTProto transport selection and byte stream."""

from __future__ import annotations

import argparse
import asyncio
import inspect
import logging
import os
import shutil
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
from urllib.parse import urlsplit

import websockets
from herokutl.network.connection import (
    ConnectionTcpFull,
    ConnectionTcpMTProxyRandomizedIntermediate,
)
from herokutl.network.connection.connection import Connection

from heroku.network import (
    ConnectionWsObfuscated,
    decide_connection_mode,
    redact_proxy_url,
    resolve_transport,
    web_host_for_dc,
)
from heroku.network.transport import (
    clear_egress_cache,
    cli_transport_default,
    dc_number,
    egress_proxy_url,
    local_tunnel_available,
    normalize_proxy_addr,
)
from heroku.network.ws_obfuscated import (
    WS_STABLE_UPTIME,
    _WsByteReader,
    _WsByteWriter,
    benign_socket_close,
)

_DATA_ROOT = tempfile.mkdtemp(prefix="heroku-ws-test-")
_MAIN = None


def _main():
    """Import ``heroku.main`` once, without parsing the test runner's argv."""
    global _MAIN
    if _MAIN is not None:
        return _MAIN

    argv = sys.argv
    env_transport = os.environ.pop("HEROKU_TRANSPORT", None)
    env_egress = os.environ.pop("SAND_EGRESS_TUNNEL_PROXY_ADDR", None)
    sys.argv = ["heroku", "--data-root", _DATA_ROOT, "--no-auth", "--no-git"]
    try:
        import heroku.main as main
    finally:
        sys.argv = argv
        if env_transport is not None:
            os.environ["HEROKU_TRANSPORT"] = env_transport
        if env_egress is not None:
            os.environ["SAND_EGRESS_TUNNEL_PROXY_ADDR"] = env_egress
    _MAIN = main
    return main


def tearDownModule():
    shutil.rmtree(_DATA_ROOT, ignore_errors=True)
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        return
    if not loop.is_closed() and not loop.is_running():
        loop.close()


def _loggers():
    return {Connection.__module__: logging.getLogger("test.ws")}


def _connection(dc_id=2, **kwargs):
    return ConnectionWsObfuscated(
        "149.154.167.51",
        443,
        dc_id,
        loggers=_loggers(),
        **kwargs,
    )


class TransportPolicyTest(unittest.TestCase):
    def test_resolve_modes(self):
        self.assertEqual(resolve_transport("auto", egress=False), "tcp")
        self.assertEqual(resolve_transport("auto", egress=True), "ws")
        self.assertEqual(resolve_transport("tcp", egress=True), "tcp")
        self.assertEqual(resolve_transport("ws", egress=False), "ws")
        self.assertEqual(resolve_transport("nope", egress=False), "tcp")
        self.assertEqual(resolve_transport(None, egress=True), "ws")

    def test_explicit_proxy_flags_win(self):
        self.assertEqual(
            decide_connection_mode(
                "ws",
                proxy_host="10.0.0.8",
                proxy_port=443,
                proxy_secret="ee" * 16,
                egress_url="http://127.0.0.1:8791",
            ),
            "proxy",
        )
        self.assertEqual(
            decide_connection_mode(
                "auto",
                proxy_host=None,
                proxy_port=None,
                proxy_secret=None,
                egress_url=None,
            ),
            "tcp",
        )

    def test_dc_hosts(self):
        self.assertEqual(web_host_for_dc(1), "pluto.web.telegram.org")
        self.assertEqual(web_host_for_dc(2), "venus.web.telegram.org")
        self.assertEqual(web_host_for_dc(3), "aurora.web.telegram.org")
        self.assertEqual(web_host_for_dc(4), "vesta.web.telegram.org")
        self.assertEqual(web_host_for_dc(5), "flora.web.telegram.org")
        self.assertEqual(web_host_for_dc(-4), "vesta.web.telegram.org")
        self.assertEqual(web_host_for_dc(99), "venus.web.telegram.org")
        self.assertEqual(dc_number(-2), 2)
        self.assertEqual(dc_number("nope"), 2)

    def test_proxy_url_normalization_and_redaction(self):
        self.assertEqual(
            normalize_proxy_addr("127.0.0.1:8791"),
            "http://127.0.0.1:8791",
        )
        self.assertEqual(
            normalize_proxy_addr("socks5://127.0.0.1:1080"),
            "socks5://127.0.0.1:1080",
        )
        self.assertEqual(
            redact_proxy_url("http://user:s3cret@127.0.0.1:8791"),
            "http://***:***@127.0.0.1:8791",
        )
        self.assertEqual(
            redact_proxy_url("http://127.0.0.1:8791"),
            "http://127.0.0.1:8791",
        )

    def test_egress_env_and_probe(self):
        clear_egress_cache()
        env = {"SAND_EGRESS_TUNNEL_PROXY_ADDR": "10.1.2.3:8791"}
        self.assertEqual(egress_proxy_url(env, probe=False), "http://10.1.2.3:8791")
        self.assertIsNone(egress_proxy_url({}, probe=False))

        async def scenario():
            async def handle(reader, writer):
                writer.close()

            server = await asyncio.start_server(handle, "127.0.0.1", 0)
            port = server.sockets[0].getsockname()[1]
            try:
                self.assertTrue(local_tunnel_available("127.0.0.1", port, timeout=1))
            finally:
                server.close()
                await server.wait_closed()
            self.assertFalse(local_tunnel_available("127.0.0.1", port, timeout=0.3))

        asyncio.run(scenario())
        clear_egress_cache()

    def test_cli_default(self):
        self.assertEqual(cli_transport_default({}), "auto")
        self.assertEqual(
            cli_transport_default({"HEROKU_TRANSPORT": "WS"}),
            "ws",
        )
        with self.assertLogs("heroku.network.transport", level="WARNING"):
            self.assertEqual(
                cli_transport_default({"HEROKU_TRANSPORT": "websocket"}),
                "auto",
            )


class ApiCredentialTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.credentials = staticmethod(_main().api_credentials_from_environ)

    def test_blank_env_is_ignored(self):
        credentials = self.credentials
        self.assertIsNone(credentials({}))
        self.assertIsNone(credentials({"api_id": "", "api_hash": ""}))
        self.assertIsNone(credentials({"api_id": "  ", "api_hash": "abc"}))
        self.assertEqual(
            credentials({"API_ID": "9", "API_HASH": "hash"}),
            ("9", "hash"),
        )
        self.assertEqual(
            credentials({"api_id": "1", "api_hash": "a", "API_ID": "2", "API_HASH": "b"}),
            ("1", "a"),
        )


class CliWiringTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _main()

    def test_parse_transport_flag_and_env(self):
        parse_arguments = _main().parse_arguments
        argv = sys.argv
        try:
            with patch.dict(os.environ, {"HEROKU_TRANSPORT": "ws"}, clear=False):
                sys.argv = ["heroku"]
                self.assertEqual(parse_arguments().transport, "ws")
            with patch.dict(os.environ, {"HEROKU_TRANSPORT": "ws"}, clear=False):
                sys.argv = ["heroku", "--transport", "TCP"]
                self.assertEqual(parse_arguments().transport, "tcp")
        finally:
            sys.argv = argv

    def _proxy(self, **overrides):
        client = _main().Heroku.__new__(_main().Heroku)
        values = {
            "proxy_host": None,
            "proxy_port": None,
            "proxy_secret": None,
            "proxy_type": "mtproxy",
            "transport": "auto",
        }
        values.update(overrides)
        client.arguments = argparse.Namespace(**values)
        return client

    def test_get_proxy_matrix(self):
        with patch("heroku.main.egress_proxy_url", return_value=None):
            client = self._proxy(transport="auto")
            client._get_proxy()
            self.assertIs(client.conn, ConnectionTcpFull)
            self.assertIsNone(client.proxy)

            client = self._proxy(transport="ws")
            client._get_proxy()
            self.assertIs(client.conn, ConnectionWsObfuscated)
            self.assertIsNone(client.proxy)

            client = self._proxy(transport="tcp")
            client._get_proxy()
            self.assertIs(client.conn, ConnectionTcpFull)

        with patch(
            "heroku.main.egress_proxy_url",
            return_value="http://user:s3cret@127.0.0.1:8791",
        ):
            client = self._proxy(transport="auto")
            with self.assertLogs("root", level="INFO") as captured:
                client._get_proxy()
            self.assertIs(client.conn, ConnectionWsObfuscated)
            self.assertIsNone(client.proxy)
            joined = "\n".join(captured.output)
            self.assertIn("***:***", joined)
            self.assertNotIn("s3cret", joined)

        client = self._proxy(
            transport="ws",
            proxy_host="10.0.0.8",
            proxy_port=443,
            proxy_secret="ab",
            proxy_type="mtproxy",
        )
        client._get_proxy()
        self.assertIs(client.conn, ConnectionTcpMTProxyRandomizedIntermediate)
        self.assertEqual(client.proxy, ("10.0.0.8", 443, "ab"))

        client = self._proxy(
            transport="ws",
            proxy_host="10.0.0.9",
            proxy_port=1080,
            proxy_type="socks5",
        )
        client._get_proxy()
        self.assertIs(client.conn, ConnectionTcpFull)
        self.assertEqual(
            client.proxy,
            {"proxy_type": "socks5", "addr": "10.0.0.9", "port": 1080},
        )

        client = self._proxy(
            transport="tcp",
            proxy_host="10.0.0.10",
            proxy_port=8080,
            proxy_type="http",
        )
        client._get_proxy()
        self.assertEqual(client.proxy["proxy_type"], "http")
        self.assertIs(client.conn, ConnectionTcpFull)


class ByteStreamTest(unittest.IsolatedAsyncioTestCase):
    async def test_reader_reassembles_and_writer_flushes(self):
        buffer = bytearray()
        condition = asyncio.Condition()
        closed = asyncio.Event()
        reader = _WsByteReader(buffer, condition, closed)

        async def produce():
            await asyncio.sleep(0.01)
            async with condition:
                buffer.extend(b"abcdef")
                condition.notify_all()
            await asyncio.sleep(0.01)
            async with condition:
                buffer.extend(b"ghij")
                condition.notify_all()

        task = asyncio.create_task(produce())
        self.assertEqual(await reader.readexactly(4), b"abcd")
        self.assertEqual(await reader.readexactly(6), b"efghij")
        await task

        closed.set()
        async with condition:
            condition.notify_all()
        with self.assertRaises(asyncio.IncompleteReadError):
            await reader.readexactly(2)

        sent = []

        class FakeWS:
            async def send(self, data):
                sent.append(bytes(data))

        writer = _WsByteWriter(FakeWS(), [])
        writer.write(b"ab")
        writer.write(bytearray(b"cd"))
        await writer.drain()
        await writer.drain()
        self.assertEqual(sent, [b"abcd"])
        writer.close()
        writer.write(b"nope")
        await writer.drain()
        self.assertEqual(sent, [b"abcd"])

    async def test_writer_maps_websocket_close_to_connection_error(self):
        from websockets.exceptions import ConnectionClosed as RealClosed

        class ClosingWS:
            async def send(self, data):
                raise RealClosed(None, None)

        writer = _WsByteWriter(ClosingWS(), [])
        writer.write(b"ping")
        with self.assertRaises(ConnectionError) as caught:
            await writer.drain()
        self.assertIsInstance(caught.exception.__cause__, RealClosed)

        class ResetWS:
            async def send(self, data):
                raise ConnectionResetError("reset")

        writer = _WsByteWriter(ResetWS(), [])
        writer.write(b"ping")
        with self.assertRaises(ConnectionResetError):
            await writer.drain()

        class BugWS:
            async def send(self, data):
                raise RuntimeError("bug")

        writer = _WsByteWriter(BugWS(), [])
        writer.write(b"ping")
        with self.assertRaises(RuntimeError):
            await writer.drain()


class _LocalConnection(ConnectionWsObfuscated):
    def __init__(self, uri, *args, **kwargs):
        self._uri = uri
        super().__init__(*args, **kwargs)

    def _websocket_target(self):
        parsed = urlsplit(self._uri)
        return parsed.hostname or "127.0.0.1", self._uri


class LiveWebSocketTest(unittest.IsolatedAsyncioTestCase):
    async def _serve(self, state):
        async def handler(websocket):
            request = websocket.request
            headers = {}
            if request is not None:
                headers = {str(k).lower(): str(v) for k, v in request.headers.items()}
            state["origin"] = headers.get("origin")
            state["user_agent"] = headers.get("user-agent")
            state["subprotocol"] = websocket.subprotocol
            state["message"] = await websocket.recv()
            await websocket.send(b"hello!!")
            state["ready"].set()
            try:
                await websocket.wait_closed()
            except Exception:
                pass

        state["ready"] = asyncio.Event()
        server = await websockets.serve(
            handler,
            "127.0.0.1",
            0,
            subprotocols=["binary"],
        )
        port = server.sockets[0].getsockname()[1]
        return server, port

    async def _connect_proxy(self, target_port):
        async def pipe(reader, writer):
            try:
                while True:
                    chunk = await reader.read(65536)
                    if not chunk:
                        break
                    writer.write(chunk)
                    await writer.drain()
            except Exception:
                pass
            finally:
                try:
                    writer.close()
                except Exception:
                    pass

        async def handle(reader, writer):
            try:
                header = await reader.readuntil(b"\r\n\r\n")
                if not header.startswith(b"CONNECT "):
                    writer.write(b"HTTP/1.1 405 Method Not Allowed\r\n\r\n")
                    await writer.drain()
                    return
                upstream_r, upstream_w = await asyncio.open_connection(
                    "127.0.0.1", target_port
                )
                writer.write(b"HTTP/1.1 200 Connection Established\r\n\r\n")
                await writer.drain()
                await asyncio.gather(
                    pipe(reader, upstream_w),
                    pipe(upstream_r, writer),
                )
            except Exception:
                try:
                    writer.close()
                except Exception:
                    pass

        server = await asyncio.start_server(handle, "127.0.0.1", 0)
        port = server.sockets[0].getsockname()[1]
        return server, port

    async def test_direct_websocket_carries_obfuscated_header(self):
        state = {}
        server, port = await self._serve(state)
        uri = f"ws://127.0.0.1:{port}/apiws"
        conn = _LocalConnection(uri, "149.154.167.51", 443, 3, loggers=_loggers())
        try:
            with patch(
                "heroku.network.ws_obfuscated.egress_proxy_url",
                return_value=None,
            ):
                await conn._connect(timeout=5)
            await asyncio.wait_for(state["ready"].wait(), 2)
            self.assertEqual(state["origin"], "https://web.telegram.org")
            self.assertIn("Mozilla/5.0", state["user_agent"])
            self.assertEqual(state["subprotocol"], "binary")
            header = state["message"]
            self.assertEqual(len(header), 64)
            self.assertNotEqual(header[0], 0xEF)
            self.assertNotIn(
                header[:4],
                (b"PVrG", b"GET ", b"POST", b"\xee\xee\xee\xee"),
            )
            self.assertNotEqual(header[4:8], b"\x00\x00\x00\x00")
            self.assertEqual(await conn._reader.readexactly(7), b"hello!!")
            self.assertIsNotNone(conn._obfuscation)
            self.assertEqual(len(bytes(conn._obfuscation.header)), 64)
            await conn.disconnect()
            await conn.disconnect()
        finally:
            server.close()
            await server.wait_closed()

    async def test_http_connect_proxy_and_wss_kwargs(self):
        state = {}
        server, port = await self._serve(state)
        proxy, proxy_port = await self._connect_proxy(port)
        uri = f"ws://127.0.0.1:{port}/apiws"
        conn = _LocalConnection(uri, "149.154.167.51", 443, -5, loggers=_loggers())
        proxy_url = f"http://user:s3cret@127.0.0.1:{proxy_port}"
        try:
            with patch(
                "heroku.network.ws_obfuscated.egress_proxy_url",
                return_value=proxy_url,
            ), self.assertLogs(
                "heroku.network.ws_obfuscated", level="INFO"
            ) as captured:
                await conn._connect(timeout=5)
            await asyncio.wait_for(state["ready"].wait(), 2)
            joined = "\n".join(captured.output)
            self.assertIn("***:***", joined)
            self.assertNotIn("s3cret", joined)
            self.assertEqual(len(state["message"]), 64)
            self.assertEqual(conn._ip, "127.0.0.1")
            self.assertEqual(conn._port, port)
            await conn.disconnect()
        finally:
            proxy.close()
            server.close()
            await proxy.wait_closed()
            await server.wait_closed()

        prod = _connection(4)
        host, prod_uri = prod._websocket_target()
        self.assertEqual(host, "vesta.web.telegram.org")
        self.assertEqual(prod_uri, "wss://vesta.web.telegram.org/apiws")
        kwargs = prod._connect_kwargs(
            host=host,
            secure=True,
            timeout=5,
            sock=None,
        )
        self.assertIsInstance(kwargs["ssl"], __import__("ssl").SSLContext)
        self.assertEqual(kwargs["server_hostname"], host)
        self.assertEqual(kwargs["origin"], "https://web.telegram.org")
        self.assertEqual(kwargs["subprotocols"], ["binary"])
        self.assertIsNone(kwargs["proxy"])
        self.assertEqual(kwargs["ping_interval"], 20.0)
        self.assertIsNone(kwargs["ping_timeout"])
        self.assertIsNone(kwargs["compression"])
        inspect.signature(websockets.connect).bind(prod_uri, **kwargs)

    async def test_failed_handshake_closes_proxy_socket(self):
        sock_box = {}

        class FakeProxy:
            @classmethod
            def from_url(cls, url):
                return cls()

            async def connect(self, **kwargs):
                left, right = socketpair()
                right.close()
                sock_box["sock"] = left
                return left

        async def explode(uri, **kwargs):
            raise OSError("handshake failed")

        conn = _connection(2)
        with patch(
            "heroku.network.ws_obfuscated.egress_proxy_url",
            return_value="http://127.0.0.1:8791",
        ), patch(
            "heroku.network.ws_obfuscated.Proxy",
            FakeProxy,
        ), patch(
            "heroku.network.ws_obfuscated.websockets.connect",
            explode,
        ):
            with self.assertRaises(OSError):
                await conn._connect(timeout=5)
        self.assertEqual(sock_box["sock"].fileno(), -1)

    async def test_peer_close_is_an_empty_read(self):
        state = {"got": asyncio.Event(), "release": asyncio.Event()}

        async def handler(websocket):
            await websocket.recv()
            state["got"].set()
            await state["release"].wait()
            await websocket.close()

        server = await websockets.serve(
            handler,
            "127.0.0.1",
            0,
            subprotocols=["binary"],
        )
        port = server.sockets[0].getsockname()[1]
        uri = f"ws://127.0.0.1:{port}/apiws"
        conn = _LocalConnection(uri, "149.154.167.51", 443, 2, loggers=_loggers())
        try:
            with patch(
                "heroku.network.ws_obfuscated.egress_proxy_url",
                return_value=None,
            ):
                await conn._connect(timeout=5)
            await asyncio.wait_for(state["got"].wait(), 2)
            state["release"].set()
            with self.assertRaises(asyncio.IncompleteReadError) as caught:
                await asyncio.wait_for(conn._reader.readexactly(1), 2)
            self.assertEqual(len(caught.exception.partial), 0)
            self.assertTrue(benign_socket_close(caught.exception))
            await conn.disconnect()
        finally:
            state["release"].set()
            server.close()
            await server.wait_closed()


class ClosePolicyTest(unittest.TestCase):
    def test_empty_read_is_benign_and_a_partial_packet_is_not(self):
        self.assertTrue(benign_socket_close(asyncio.IncompleteReadError(b"", 0)))
        self.assertTrue(benign_socket_close(asyncio.IncompleteReadError(b"", 1)))
        self.assertFalse(benign_socket_close(asyncio.IncompleteReadError(b"\x01", 8)))
        self.assertTrue(benign_socket_close(ConnectionResetError("reset")))
        self.assertFalse(benign_socket_close(RuntimeError("bug")))

    def test_short_lived_close_backs_off_and_a_stable_one_does_not(self):
        conn = _connection()
        conn._opened_at = time.monotonic()
        conn._account_close()
        self.assertEqual(conn._backoff_step, 1)
        self.assertEqual(conn._reconnect_delay(), 1.0)

        conn._opened_at = time.monotonic()
        conn._account_close()
        self.assertEqual(conn._reconnect_delay(), 2.0)

        conn._backoff_step = 5
        self.assertEqual(conn._reconnect_delay(), 16.0)

        conn._opened_at = time.monotonic() - (WS_STABLE_UPTIME + 1)
        conn._account_close()
        self.assertEqual(conn._backoff_step, 0)
        self.assertEqual(conn._reconnect_delay(), 0.0)

    def test_failed_open_uses_the_same_backoff(self):
        conn = _connection()
        conn._note_failed_open()
        conn._note_failed_open()
        self.assertEqual(conn._reconnect_delay(), 2.0)


class QuietReconnectTest(unittest.IsolatedAsyncioTestCase):
    async def _run_recv(self, error):
        conn = _connection()
        conn._connected = True

        async def fail():
            raise error

        conn._recv = fail
        with self.assertNoLogs("test.ws", level="WARNING"):
            with self.assertLogs("test.ws", level="DEBUG") as captured:
                await conn._recv_loop()
        queued, err = conn._recv_queue.get_nowait()
        return conn, captured.output, queued, err

    async def test_idle_close_is_debug_and_still_queued(self):
        conn, output, queued, err = await self._run_recv(
            asyncio.IncompleteReadError(b"", 0)
        )
        self.assertFalse(conn._connected)
        self.assertIsNone(queued)
        self.assertIsInstance(err, asyncio.IncompleteReadError)
        joined = "\n".join(output)
        self.assertIn("reconnecting", joined)
        self.assertNotIn("Server closed the connection", joined)

    async def test_truncated_packet_stays_a_warning(self):
        conn = _connection()
        conn._connected = True

        async def fail():
            raise asyncio.IncompleteReadError(b"\xab", 8)

        conn._recv = fail
        with self.assertLogs("test.ws", level="WARNING") as captured:
            await conn._recv_loop()
        self.assertIn("Server closed the connection", "\n".join(captured.output))
        _, err = conn._recv_queue.get_nowait()
        self.assertIsInstance(err, asyncio.IncompleteReadError)

    async def test_backoff_sleeps_only_after_a_short_life(self):
        from unittest.mock import AsyncMock

        conn = _connection()
        with patch(
            "heroku.network.ws_obfuscated.asyncio.sleep",
            new_callable=AsyncMock,
        ) as sleep:
            await conn._await_reconnect_backoff()
        sleep.assert_not_awaited()

        conn._backoff_step = 3
        with patch(
            "heroku.network.ws_obfuscated.asyncio.sleep",
            new_callable=AsyncMock,
        ) as sleep:
            await conn._await_reconnect_backoff()
        sleep.assert_awaited_once_with(4.0)

    async def test_recv_loop_task_closes_without_cancelling_itself(self):
        conn = _connection()
        conn._connected = True

        async def fail():
            raise asyncio.IncompleteReadError(b"", 1)

        conn._recv = fail
        task = asyncio.create_task(conn._recv_loop())
        conn._recv_task = task
        await asyncio.wait_for(task, 2)
        self.assertTrue(task.done())
        self.assertFalse(task.cancelled())
        self.assertIsNone(task.exception())
        self.assertFalse(conn._connected)
        queued, err = conn._recv_queue.get_nowait()
        self.assertIsNone(queued)
        self.assertIsInstance(err, asyncio.IncompleteReadError)


class PrivateFileTest(unittest.TestCase):
    def test_private_write_mode(self):
        from heroku._internal import private_write

        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "config.json")
            private_write(path, '{"api_hash": "secret"}')
            self.assertEqual(oct(os.stat(path).st_mode & 0o777), "0o600")


def socketpair():
    import socket

    return socket.socketpair()


if __name__ == "__main__":
    unittest.main()
