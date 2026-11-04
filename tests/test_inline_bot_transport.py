# ©️ Codrago, 2024-2030
# This file is a part of Heroku Userbot
# 🌐 https://github.com/Heroku-userbot/Heroku
# You can redistribute it and/or modify it under the terms of the GNU AGPLv3
# 🔑 https://www.gnu.org/licenses/agpl-3.0.html

"""Inline bot client follows the user MTProto transport.

No live Telegram connection. The bot used to be constructed with Telethon's
default TCP full transport, so on hosts where only WSS to ``*.web.telegram.org``
works the bot never started and invites crashed on a missing username.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import os
import shutil
import sqlite3
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

_DATA_ROOT = tempfile.mkdtemp(prefix="heroku-inline-bot-test-")
_ARGV = sys.argv
_ENV_TRANSPORT = os.environ.pop("HEROKU_TRANSPORT", None)
_ENV_EGRESS = os.environ.pop("SAND_EGRESS_TUNNEL_PROXY_ADDR", None)
_ENV_NO_GIT = os.environ.get("HEROKU_NO_GIT")
os.environ["HEROKU_NO_GIT"] = "1"
sys.argv = [
    "heroku",
    "--data-root",
    _DATA_ROOT,
    "--no-auth",
    "--no-git",
    "--transport",
    "tcp",
]

import heroku.main as main  # noqa: E402
from heroku.inline.core import (  # noqa: E402
    InlineManager,
    inline_disconnect_is_recoverable,
)
from heroku.network import (  # noqa: E402
    ConnectionWsObfuscated,
    client_transport,
    connection_for_settings,
)
from heroku.utils.other import (  # noqa: E402
    InlineBotNotReady,
    invite_inline_bot,
    invite_inline_bot_or_skip,
)
from herokutl.network.connection import (  # noqa: E402
    ConnectionTcpFull,
    ConnectionTcpMTProxyRandomizedIntermediate,
)
from herokutl.tl.functions.channels import (  # noqa: E402
    EditAdminRequest,
    InviteToChannelRequest,
)

sys.argv = _ARGV
if _ENV_TRANSPORT is not None:
    os.environ["HEROKU_TRANSPORT"] = _ENV_TRANSPORT
if _ENV_EGRESS is not None:
    os.environ["SAND_EGRESS_TUNNEL_PROXY_ADDR"] = _ENV_EGRESS
if _ENV_NO_GIT is None:
    os.environ.pop("HEROKU_NO_GIT", None)
else:
    os.environ["HEROKU_NO_GIT"] = _ENV_NO_GIT


def tearDownModule():
    shutil.rmtree(_DATA_ROOT, ignore_errors=True)


_SOCKS = {"proxy_type": "socks5", "addr": "10.0.0.9", "port": 1080}


def _user(connection=None, proxy=None, **extra):
    data = {
        "tg_id": 100,
        "heroku_me": object(),
        "api_id": 12345,
        "api_hash": "unit-test-hash",
        "_proxy": proxy,
    }
    if connection is not None:
        data["_connection"] = connection
    data.update(extra)
    return SimpleNamespace(**data)


@contextlib.contextmanager
def _arguments(**overrides):
    values = {
        "transport": "auto",
        "proxy_host": None,
        "proxy_port": None,
        "proxy_secret": None,
        "proxy_type": "mtproxy",
    }
    values.update(overrides)
    previous = main.heroku.arguments
    main.heroku.arguments = argparse.Namespace(**values)
    try:
        yield
    finally:
        main.heroku.arguments = previous


class ClientTransportTest(unittest.TestCase):
    def test_reuses_user_connection_and_proxy(self):
        connection, proxy = client_transport(
            _user(ConnectionWsObfuscated, None),
        )
        self.assertIs(connection, ConnectionWsObfuscated)
        self.assertIsNone(proxy)

        connection, proxy = client_transport(_user(ConnectionTcpFull, _SOCKS))
        self.assertIs(connection, ConnectionTcpFull)
        self.assertEqual(proxy, _SOCKS)

        mtproxy = ("10.0.0.8", 443, "ab")
        connection, proxy = client_transport(
            _user(ConnectionTcpMTProxyRandomizedIntermediate, mtproxy),
        )
        self.assertIs(connection, ConnectionTcpMTProxyRandomizedIntermediate)
        self.assertEqual(proxy, mtproxy)

    def test_user_connection_wins_over_process_transport(self):
        with _arguments(transport="tcp"), patch(
            "heroku.network.egress_proxy_url",
            return_value="http://127.0.0.1:8791",
        ):
            connection, proxy = client_transport(
                _user(ConnectionWsObfuscated, None),
            )
        self.assertIs(connection, ConnectionWsObfuscated)
        self.assertIsNone(proxy)

    def test_fallback_matches_main_rules(self):
        bare = SimpleNamespace()

        with _arguments(transport="ws"), patch(
            "heroku.network.egress_proxy_url",
            return_value=None,
        ):
            connection, proxy = client_transport(bare)
        self.assertIs(connection, ConnectionWsObfuscated)
        self.assertIsNone(proxy)

        with _arguments(transport="auto"), patch(
            "heroku.network.egress_proxy_url",
            return_value="http://127.0.0.1:8791",
        ):
            connection, proxy = client_transport(bare)
        self.assertIs(connection, ConnectionWsObfuscated)
        self.assertIsNone(proxy)

        with _arguments(transport="tcp"), patch(
            "heroku.network.egress_proxy_url",
            return_value="http://127.0.0.1:8791",
        ):
            connection, proxy = client_transport(bare)
        self.assertIs(connection, ConnectionTcpFull)
        self.assertIsNone(proxy)

        with _arguments(transport="auto"), patch(
            "heroku.network.egress_proxy_url",
            return_value=None,
        ):
            connection, proxy = client_transport(bare)
        self.assertIs(connection, ConnectionTcpFull)

        with _arguments(
            transport="ws",
            proxy_host="10.0.0.9",
            proxy_port=1080,
            proxy_type="socks5",
        ):
            connection, proxy = client_transport(bare)
        self.assertIs(connection, ConnectionTcpFull)
        self.assertEqual(proxy, _SOCKS)

        self.assertEqual(
            connection_for_settings(
                "ws",
                proxy_host="10.0.0.8",
                proxy_port=443,
                proxy_secret="ab",
                proxy_type="mtproxy",
                egress_url="http://127.0.0.1:8791",
            ),
            (ConnectionTcpMTProxyRandomizedIntermediate, ("10.0.0.8", 443, "ab")),
        )


class _RecordingClient:
    def __init__(self, username):
        self.loader = SimpleNamespace(
            inline=SimpleNamespace(bot_username=username, bot_id=7),
        )
        self.calls = []

    async def __call__(self, request):
        self.calls.append(request)


class _FailingClient(_RecordingClient):
    async def __call__(self, request):
        raise ConnectionError("socket down")


class InviteInlineBotTest(unittest.IsolatedAsyncioTestCase):
    async def test_missing_username_does_not_cast_peer(self):
        for username in (None, "", "  ", "@", False):
            client = _RecordingClient(username)
            with self.subTest(username=username):
                with self.assertRaises(InlineBotNotReady) as caught:
                    await invite_inline_bot(client, "asset-chat")
                message = str(caught.exception)
                self.assertIn("username", message.lower())
                self.assertNotIn("NoneType", message)
                self.assertNotIn("Cannot cast", message)
                self.assertNotIn("old asset chat", message)
                self.assertEqual(client.calls, [])

        client = _RecordingClient(None)
        client.loader = SimpleNamespace()
        with self.assertRaises(InlineBotNotReady):
            await invite_inline_bot(client, "asset-chat")
        self.assertEqual(client.calls, [])

    async def test_skip_logs_and_real_errors_still_raise(self):
        client = _RecordingClient(None)
        with self.assertLogs("heroku.utils.other", level="WARNING") as captured:
            invited = await invite_inline_bot_or_skip(client, "asset-chat")
        self.assertFalse(invited)
        self.assertEqual(client.calls, [])
        self.assertIn("username", "\n".join(captured.output).lower())

        failing = _FailingClient("ready_bot")
        with self.assertRaises(RuntimeError) as caught:
            await invite_inline_bot(failing, "asset-chat")
        self.assertNotIsInstance(caught.exception, InlineBotNotReady)
        self.assertIn("old asset chat", str(caught.exception))
        self.assertIn("socket down", str(caught.exception))

        with self.assertRaises(RuntimeError) as caught:
            await invite_inline_bot_or_skip(failing, "asset-chat")
        self.assertNotIsInstance(caught.exception, InlineBotNotReady)

    async def test_ready_bot_is_invited_by_username(self):
        client = _RecordingClient("@Ready_Bot")
        invited = await invite_inline_bot_or_skip(client, "asset-chat")
        self.assertTrue(invited)
        self.assertIsInstance(client.calls[0], InviteToChannelRequest)
        self.assertEqual(client.calls[0].users, ["Ready_Bot"])
        self.assertIsInstance(client.calls[1], EditAdminRequest)
        self.assertEqual(client.calls[1].user_id, "Ready_Bot")


class BotClientWiringTest(unittest.IsolatedAsyncioTestCase):
    async def _register(self, user):
        seen = {}

        class FakeBot:
            def __init__(self, session, api_id, api_hash, **kwargs):
                seen["session"] = session
                seen["api_id"] = api_id
                seen["api_hash"] = api_hash
                seen["kwargs"] = kwargs

            async def start(self, **kwargs):
                seen["start"] = kwargs
                raise sqlite3.OperationalError("locked")

            async def disconnect(self):
                return None

        manager = InlineManager.__new__(InlineManager)
        manager._client = user
        manager._token = "42:unit-test"
        manager._bot_client = None

        with patch("heroku.inline.core.TelegramClient", FakeBot), patch(
            "heroku.inline.core.get_display_name",
            return_value="Tester",
        ), self.assertLogs("heroku.inline.core", level="CRITICAL"):
            result = await manager.register_manager(ignore_token_checks=True)

        self.assertFalse(result)
        self.assertEqual(seen["api_id"], user.api_id)
        self.assertEqual(seen["api_hash"], user.api_hash)
        self.assertIn("heroku-100-bot-42", seen["session"].filename)
        self.assertEqual(seen["start"], {"bot_token": "42:unit-test"})
        self.assertTrue(seen["kwargs"]["receive_updates"])
        self.assertIsNone(seen["kwargs"]["connection_retries"])
        self.assertTrue(seen["kwargs"]["auto_reconnect"])
        self.assertEqual(seen["kwargs"]["retry_delay"], 1)
        return seen["kwargs"]

    async def test_bot_client_copies_user_transport(self):
        kwargs = await self._register(_user(ConnectionWsObfuscated, None))
        self.assertIs(kwargs["connection"], ConnectionWsObfuscated)
        self.assertIsNone(kwargs["proxy"])

        kwargs = await self._register(_user(ConnectionTcpFull, _SOCKS))
        self.assertIs(kwargs["connection"], ConnectionTcpFull)
        self.assertEqual(kwargs["proxy"], _SOCKS)

    async def test_bot_client_falls_back_to_ws_rules(self):
        with _arguments(transport="ws"), patch(
            "heroku.network.egress_proxy_url",
            return_value=None,
        ):
            kwargs = await self._register(SimpleNamespace(
                tg_id=100,
                heroku_me=object(),
                api_id=12345,
                api_hash="unit-test-hash",
            ))
        self.assertIs(kwargs["connection"], ConnectionWsObfuscated)
        self.assertIsNone(kwargs["proxy"])


class InlineReconnectTest(unittest.IsolatedAsyncioTestCase):
    def test_recoverable_classification(self):
        self.assertTrue(inline_disconnect_is_recoverable(None))
        self.assertTrue(inline_disconnect_is_recoverable(ConnectionError("closed")))
        self.assertTrue(
            inline_disconnect_is_recoverable(asyncio.IncompleteReadError(b"", 0))
        )
        self.assertFalse(inline_disconnect_is_recoverable(RuntimeError("token revoked")))

    async def test_guard_reconnects_after_network_drop(self):
        loop = asyncio.get_running_loop()
        dropped = loop.create_future()
        dropped.set_exception(ConnectionError("0 bytes read on a total of 0 expected bytes"))

        class Client:
            def __init__(self):
                self.disconnected = dropped
                self.connects = 0
                self._up = False

            def is_connected(self):
                return self._up

            async def connect(self):
                self.connects += 1
                self._up = True
                self.disconnected = loop.create_future()

        manager = InlineManager.__new__(InlineManager)
        manager.init_complete = True
        manager._bot_stop = asyncio.Event()
        manager._bot_client = Client()
        manager._bot_guard_task = asyncio.create_task(manager._watch_inline_bot())
        try:
            for _ in range(50):
                if manager._bot_client.connects:
                    break
                await asyncio.sleep(0.01)
            self.assertEqual(manager._bot_client.connects, 1)
            self.assertTrue(manager._bot_client.is_connected())
        finally:
            await manager._stop_inline_bot_guard()

    async def test_guard_leaves_auth_failures_down(self):
        loop = asyncio.get_running_loop()
        dropped = loop.create_future()

        class TokenRevoked(Exception):
            pass

        dropped.set_exception(TokenRevoked("auth key unregistered"))

        class Client:
            def __init__(self):
                self.disconnected = dropped
                self.connects = 0

            def is_connected(self):
                return False

            async def connect(self):
                self.connects += 1

        manager = InlineManager.__new__(InlineManager)
        manager.init_complete = True
        manager._bot_stop = asyncio.Event()
        manager._bot_client = Client()
        with self.assertLogs("heroku.inline.core", level="ERROR"):
            await asyncio.wait_for(manager._watch_inline_bot(), 1)
        self.assertEqual(manager._bot_client.connects, 0)


if __name__ == "__main__":
    unittest.main()
