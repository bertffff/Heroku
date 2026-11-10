# ©️ Codrago, 2024-2030
# This file is a part of Heroku Userbot
# 🌐 https://github.com/Heroku-userbot/Heroku
# You can redistribute it and/or modify it under the terms of the GNU AGPLv3
# 🔑 https://www.gnu.org/licenses/agpl-3.0.html

# ©️ bertffff, 2026
# This file is a part of Kanjo userbot
# 🌐 https://github.com/bertffff/Heroku
# You can redistribute it and/or modify it under the terms of the GNU AGPLv3
# 🔑 https://www.gnu.org/licenses/agpl-3.0.html


"""Obfuscated abridged MTProto over ``wss://*.web.telegram.org/apiws``."""

from __future__ import annotations

import asyncio
import inspect
import logging
import ssl as ssl_mod
import time
from urllib.parse import urlsplit

import websockets
from herokutl.errors import InvalidBufferError, InvalidChecksumError
from herokutl.network.connection.connection import ObfuscatedConnection
from herokutl.network.connection.tcpabridged import AbridgedPacketCodec
from herokutl.network.connection.tcpobfuscated import ObfuscatedIO
from python_socks.async_.asyncio import Proxy
from websockets.exceptions import ConnectionClosed

from .transport import (
    dc_host_was_known,
    egress_proxy_url,
    redact_proxy_url,
    web_host_for_dc,
)

logger = logging.getLogger(__name__)

# One MTProto packet is at most 16 MiB. Keep a little extra queued.
_MAX_WS_MESSAGE = 16 * 1024 * 1024
_MAX_BUFFER = 32 * 1024 * 1024
# Shorter than common proxy and NAT idle timeouts (30–60s). Pongs are not
# required: a datacenter that ignores WebSocket pings must not be dropped.
WS_PING_INTERVAL = 20.0
# A socket that dies before this has lived through a handshake only.
# Longer closes (idle proxy, planned reconnect) retry immediately.
WS_STABLE_UPTIME = 5.0
WS_RECONNECT_BACKOFF_BASE = 1.0
WS_RECONNECT_BACKOFF_CAP = 16.0
WS_BACKOFF_MAX_STEP = 5
_BROWSER_UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
_ORIGIN = "https://web.telegram.org"

_CONNECT_PARAMS = inspect.signature(websockets.connect).parameters


def _connect_accepts(name: str) -> bool:
    param = _CONNECT_PARAMS.get(name)
    return param is not None and param.kind is not inspect.Parameter.VAR_KEYWORD


def benign_socket_close(exc: BaseException) -> bool:
    """True when the peer closed the socket without a partial MTProto packet.

    Idle proxies and NAT timeouts surface as an empty read or a WebSocket
    close frame. Those are reconnects, not protocol failures.
    """
    if isinstance(exc, asyncio.IncompleteReadError):
        return len(exc.partial or b"") == 0
    if isinstance(exc, (ConnectionResetError, BrokenPipeError, ConnectionAbortedError)):
        return True
    if isinstance(exc, ConnectionClosed):
        return True
    return False


class _WsByteReader:
    """Byte stream assembled from WebSocket binary messages."""

    def __init__(
        self,
        buffer: bytearray,
        condition: asyncio.Condition,
        closed: asyncio.Event,
    ):
        self._buffer = buffer
        self._condition = condition
        self._closed = closed

    async def readexactly(self, n: int) -> bytes:
        if n < 0:
            raise ValueError("readexactly size must be >= 0")
        if n == 0:
            return b""

        async with self._condition:
            while len(self._buffer) < n:
                if self._closed.is_set():
                    raise asyncio.IncompleteReadError(bytes(self._buffer), n)
                await self._condition.wait()
            data = bytes(self._buffer[:n])
            del self._buffer[:n]
            return data


class _WsByteWriter:
    """Queues TCP-style writes and flushes them as one WebSocket message."""

    def __init__(self, ws, pending: list[bytes]):
        self._ws = ws
        self._pending = pending
        self._closing = False
        self._lock = asyncio.Lock()

    def write(self, data: bytes):
        if self._closing:
            return
        payload = bytes(data)
        if not payload:
            return
        self._pending.append(payload)

    async def drain(self):
        async with self._lock:
            if self._closing or not self._pending:
                return
            payload = b"".join(self._pending)
            self._pending.clear()
            try:
                await self._ws.send(payload)
            except OSError:
                self._closing = True
                raise
            except Exception as exc:
                self._closing = True
                # websockets.ConnectionClosed is not an OSError. Telethon's
                # send loop treats only OSError as a normal peer close.
                if benign_socket_close(exc):
                    raise ConnectionError("WebSocket closed") from exc
                raise

    def close(self):
        self._closing = True
        self._pending.clear()

    async def wait_closed(self):
        return


class ConnectionWsObfuscated(ObfuscatedConnection):
    """
    Same framing as ``ConnectionTcpObfuscated``, carried on a WebSocket.

    The HTTP handshake uses ``Origin: https://web.telegram.org`` and
    ``Sec-WebSocket-Protocol: binary``. When an egress proxy is configured,
    the TCP connection is an HTTP CONNECT (or SOCKS) tunnel; TLS still ends
    at ``*.web.telegram.org``.
    """

    obfuscated_io = ObfuscatedIO
    packet_codec = AbridgedPacketCodec

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._ws = None
        self._recv_task_ws = None
        self._buffer = bytearray()
        self._buf_cond = asyncio.Condition()
        self._ws_closed = asyncio.Event()
        self._pending_writes: list[bytes] = []
        self._close_lock = asyncio.Lock()
        self._opened_at: float | None = None
        self._backoff_step = 0

    def _websocket_target(self) -> tuple[str, str]:
        host = web_host_for_dc(self._dc_id)
        return host, f"wss://{host}/apiws"

    def _normalized_local_addr(self):
        addr = self._local_addr
        if not addr:
            return None
        if isinstance(addr, tuple) and len(addr) == 2:
            return addr
        if isinstance(addr, str):
            return (addr, 0)
        logger.warning("Ignoring unsupported local address %r", addr)
        return None

    def _connect_kwargs(self, *, host: str, secure: bool, timeout, sock):
        headers: dict[str, str] = {}
        kwargs: dict = {
            "subprotocols": ["binary"],
            "open_timeout": timeout,
            "max_size": _MAX_WS_MESSAGE,
        }
        if sock is not None:
            kwargs["sock"] = sock
        else:
            local_addr = self._normalized_local_addr()
            if local_addr is not None:
                kwargs["local_addr"] = local_addr
        if secure:
            kwargs["ssl"] = ssl_mod.create_default_context()
            kwargs["server_hostname"] = host

        if _connect_accepts("origin"):
            kwargs["origin"] = _ORIGIN
        else:
            headers["Origin"] = _ORIGIN

        if _connect_accepts("user_agent_header"):
            kwargs["user_agent_header"] = _BROWSER_UA
        else:
            headers["User-Agent"] = _BROWSER_UA

        if headers:
            if _connect_accepts("additional_headers"):
                kwargs["additional_headers"] = headers
            elif _connect_accepts("extra_headers"):
                kwargs["extra_headers"] = headers
            else:
                kwargs["additional_headers"] = headers

        # The egress tunnel, when used, is already applied to ``sock``.
        # ``proxy=None`` also stops websockets from picking up HTTPS_PROXY.
        if _connect_accepts("proxy"):
            kwargs["proxy"] = None
        # MTProto is already encrypted. permessage-deflate uses RSV bits that
        # some egress proxies mishandle, and it does not help this traffic.
        if _connect_accepts("compression"):
            kwargs["compression"] = None
        # Ping frames refresh proxy/NAT idle timers. A pong timeout must stay
        # off: Telegram answers MTProto pings, not necessarily WebSocket pongs,
        # and the previous ``ping_interval=None`` let idle proxies close the
        # socket (logged as "0 bytes read").
        if _connect_accepts("ping_interval") and _connect_accepts("ping_timeout"):
            kwargs["ping_interval"] = WS_PING_INTERVAL
            kwargs["ping_timeout"] = None
        elif _connect_accepts("ping_interval"):
            kwargs["ping_interval"] = None
        return kwargs

    async def _open_proxy_socket(
        self, proxy_url: str, dest_host: str, dest_port: int, timeout
    ):
        proxy = Proxy.from_url(proxy_url)
        connect_kwargs = {
            "dest_host": dest_host,
            "dest_port": dest_port,
            "timeout": timeout,
        }
        local_addr = self._normalized_local_addr()
        if local_addr is not None:
            connect_kwargs["local_addr"] = local_addr
        return await asyncio.wait_for(
            proxy.connect(**connect_kwargs),
            timeout=timeout,
        )

    async def _connect(self, timeout=None, ssl=None):
        if ssl is not None:
            logger.debug(
                "Ignoring connection ssl=%r; WebSocket TLS follows the wss:// URI",
                ssl,
            )
        timeout = timeout or 20
        host, uri = self._websocket_target()
        parsed = urlsplit(uri)
        dest_host = parsed.hostname or host
        if parsed.scheme == "wss":
            dest_port = parsed.port or 443
            secure = True
        elif parsed.scheme == "ws":
            dest_port = parsed.port or 80
            secure = False
        else:
            raise ValueError(f"Unsupported WebSocket URI: {uri}")

        self._ip = dest_host
        self._port = dest_port
        if not dc_host_was_known(self._dc_id):
            logger.warning(
                "No WebSocket host for DC %s; using %s",
                self._dc_id,
                host,
            )

        proxy_url = egress_proxy_url()
        via = f" via {redact_proxy_url(proxy_url)}" if proxy_url else ""
        logger.info("Opening obfuscated MTProto WebSocket to %s%s", uri, via)
        await self._await_reconnect_backoff()

        sock = None
        try:
            if proxy_url:
                sock = await self._open_proxy_socket(
                    proxy_url, dest_host, dest_port, timeout
                )
            kwargs = self._connect_kwargs(
                host=host,
                secure=secure,
                timeout=timeout,
                sock=sock,
            )
            self._ws = await websockets.connect(uri, **kwargs)
            sock = None
            self._ws_closed.clear()
            self._buffer.clear()
            self._pending_writes.clear()
            self._reader = _WsByteReader(self._buffer, self._buf_cond, self._ws_closed)
            self._writer = _WsByteWriter(self._ws, self._pending_writes)
            self._opened_at = time.monotonic()
            self._recv_task_ws = asyncio.create_task(self._ws_recv_loop())
            self._codec = self.packet_codec(self)
            self._init_conn()
            await self._writer.drain()
        except asyncio.CancelledError:
            if sock is not None:
                try:
                    sock.close()
                except OSError:
                    pass
            await self._close_ws()
            raise
        except BaseException:
            if sock is not None:
                try:
                    sock.close()
                except OSError:
                    pass
            opened = self._opened_at is not None
            await self._close_ws()
            if not opened:
                self._note_failed_open()
            raise

    async def _ws_recv_loop(self):
        try:
            async for message in self._ws:
                if isinstance(message, str):
                    message = message.encode("latin-1")
                else:
                    message = bytes(message)
                async with self._buf_cond:
                    if len(self._buffer) + len(message) > _MAX_BUFFER:
                        logger.warning(
                            "WebSocket MTProto buffer exceeded %s bytes; closing",
                            _MAX_BUFFER,
                        )
                        self._ws_closed.set()
                        self._buf_cond.notify_all()
                        break
                    self._buffer.extend(message)
                    self._buf_cond.notify_all()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.debug("WebSocket MTProto receive loop ended", exc_info=True)
        finally:
            self._ws_closed.set()
            async with self._buf_cond:
                self._buf_cond.notify_all()

    def _account_close(self) -> None:
        opened = self._opened_at
        self._opened_at = None
        if opened is None:
            return
        lived = time.monotonic() - opened
        if lived >= WS_STABLE_UPTIME:
            self._backoff_step = 0
            return
        self._backoff_step = min(self._backoff_step + 1, WS_BACKOFF_MAX_STEP)

    def _note_failed_open(self) -> None:
        self._backoff_step = min(self._backoff_step + 1, WS_BACKOFF_MAX_STEP)

    def _reconnect_delay(self) -> float:
        step = self._backoff_step
        if step <= 0:
            return 0.0
        delay = WS_RECONNECT_BACKOFF_BASE * (2 ** (step - 1))
        return min(WS_RECONNECT_BACKOFF_CAP, delay)

    async def _await_reconnect_backoff(self) -> None:
        delay = self._reconnect_delay()
        if delay <= 0:
            return
        logger.info(
            "WebSocket reconnect backoff %.0fs after a short-lived connection",
            delay,
        )
        await asyncio.sleep(delay)

    async def _close_ws(self):
        async with self._close_lock:
            self._account_close()
            self._ws_closed.set()
            async with self._buf_cond:
                self._buf_cond.notify_all()

            task = self._recv_task_ws
            self._recv_task_ws = None
            if (
                task is not None
                and not task.done()
                and task is not asyncio.current_task()
            ):
                task.cancel()
                try:
                    await task
                except (asyncio.CancelledError, Exception):
                    pass

            ws = self._ws
            self._ws = None
            if ws is not None:
                try:
                    await ws.close()
                except Exception:
                    logger.debug("WebSocket close failed", exc_info=True)

    async def _recv_loop(self):
        """Same queue protocol as Telethon, without a warning on idle EOF.

        ``Connection._recv_loop`` logs every ``IncompleteReadError`` at
        WARNING ("Server closed the connection: 0 bytes read..."). An egress
        proxy closing an idle WebSocket is that exception with an empty
        partial. Reconnect still happens: the error is queued and the sender
        treats it as a dropped link.
        """
        try:
            while self._connected:
                try:
                    data = await self._recv()
                except asyncio.CancelledError:
                    break
                except (OSError, asyncio.IncompleteReadError) as exc:
                    if benign_socket_close(exc):
                        self._log.debug("WebSocket closed (%s); reconnecting", exc)
                    else:
                        self._log.warning("Server closed the connection: %s", exc)
                    await self._recv_queue.put((None, exc))
                    await self.disconnect()
                except InvalidChecksumError as exc:
                    self._log.warning("Server response had invalid checksum: %s", exc)
                    await self._recv_queue.put((None, exc))
                except InvalidBufferError as exc:
                    self._log.warning("Server response had invalid buffer: %s", exc)
                    await self._recv_queue.put((None, exc))
                except Exception as exc:
                    self._log.exception("Unexpected exception in the receive loop")
                    await self._recv_queue.put((None, exc))
                    await self.disconnect()
                else:
                    await self._recv_queue.put((data, None))
        finally:
            await self.disconnect()

    async def disconnect(self):
        # Telethon cancels the receive task from inside that task. Awaiting
        # the current task aborts this cleanup, so the WebSocket can stay
        # half-open across the reconnect.
        current = asyncio.current_task()
        if current is not None and self._recv_task is current:
            self._recv_task = None
        if current is not None and self._send_task is current:
            self._send_task = None
        try:
            await super().disconnect()
        finally:
            await self._close_ws()
