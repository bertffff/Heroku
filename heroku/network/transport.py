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


"""Choose TCP or WebSocket MTProto when raw DC addresses are blocked."""

from __future__ import annotations

import logging
import os
import socket
from collections.abc import Mapping
from urllib.parse import urlsplit, urlunsplit

logger = logging.getLogger(__name__)

TRANSPORTS = ("auto", "tcp", "ws")

# Telegram Web DC names. Media DCs use the same hosts with a negative id.
DC_WEB_NAMES = {
    1: "pluto",
    2: "venus",
    3: "aurora",
    4: "vesta",
    5: "flora",
}
DEFAULT_DC = 2

# Sandbox egress often publishes this local HTTP CONNECT tunnel.
EGRESS_PROXY_ENV = "SAND_EGRESS_TUNNEL_PROXY_ADDR"
DEFAULT_TUNNEL_HOST = "127.0.0.1"
DEFAULT_TUNNEL_PORT = 8791
DEFAULT_TUNNEL_URL = f"http://{DEFAULT_TUNNEL_HOST}:{DEFAULT_TUNNEL_PORT}"

_tunnel_probe_cache: bool | None = None


def normalize_transport_name(value: str | None) -> str:
    """Return ``auto``, ``tcp``, or ``ws``. Unknown values become ``auto``."""
    raw = (value or "auto").strip().lower()
    if raw in TRANSPORTS:
        return raw
    return "auto"


def cli_transport_default(environ: Mapping[str, str] | None = None) -> str:
    """Default for ``--transport``.

    ``HEROKU_TRANSPORT`` wins when it is non-empty. Otherwise
    ``KANJO_TRANSPORT`` is used. Missing or blank means ``auto``.
    """
    from ..brand import env_get_source

    raw, source = env_get_source("TRANSPORT", environ)
    if raw is None or not str(raw).strip():
        return "auto"

    normalized = normalize_transport_name(str(raw))
    if normalized != str(raw).strip().lower():
        logger.warning(
            "%s=%r is not auto, tcp, or ws; using auto",
            source,
            raw,
        )
    return normalized


def resolve_transport(choice: str | None, *, egress: bool) -> str:
    """
    Resolve a requested mode to the connection that should be opened.

    ``auto`` uses WebSocket only when an egress proxy signal is present.
    ``ws`` and ``tcp`` are explicit.
    """
    mode = normalize_transport_name(choice)
    if mode == "tcp":
        return "tcp"
    if mode == "ws":
        return "ws"
    return "ws" if egress else "tcp"


def decide_connection_mode(
    transport: str | None,
    *,
    proxy_host: str | None,
    proxy_port: int | None,
    proxy_secret: str | None,
    egress_url: str | None,
) -> str:
    """
    Return ``proxy``, ``ws``, or ``tcp``.

    Explicit ``--proxy-host`` / ``--proxy-port`` / ``--proxy-secret`` keep the
    historical MTProxy, SOCKS, and HTTP proxy setup.
    """
    if proxy_host or proxy_port or proxy_secret:
        return "proxy"
    return resolve_transport(transport, egress=egress_url is not None)


def normalize_proxy_addr(raw: str) -> str:
    """Accept ``host:port`` or a full proxy URL."""
    value = raw.strip()
    if not value:
        raise ValueError("empty proxy address")
    if "://" not in value:
        value = f"http://{value}"
    return value


def redact_proxy_url(url: str) -> str:
    """Hide userinfo before a proxy URL is written to a log."""
    try:
        parts = urlsplit(url)
    except ValueError:
        return "proxy://***"

    if parts.username is None and parts.password is None:
        return url

    hostname = parts.hostname or ""
    if ":" in hostname and not hostname.startswith("["):
        hostname = f"[{hostname}]"
    port = f":{parts.port}" if parts.port else ""
    netloc = f"***:***@{hostname}{port}"
    return urlunsplit((parts.scheme, netloc, parts.path, "", ""))


def clear_egress_cache() -> None:
    """Forget the cached localhost tunnel probe (tests and reconfiguration)."""
    global _tunnel_probe_cache
    _tunnel_probe_cache = None


def local_tunnel_available(
    host: str = DEFAULT_TUNNEL_HOST,
    port: int = DEFAULT_TUNNEL_PORT,
    timeout: float = 0.25,
) -> bool:
    """True when the well-known local HTTP CONNECT tunnel accepts TCP."""
    global _tunnel_probe_cache

    use_cache = host == DEFAULT_TUNNEL_HOST and port == DEFAULT_TUNNEL_PORT
    if use_cache and _tunnel_probe_cache is not None:
        return _tunnel_probe_cache

    open_ = False
    try:
        with socket.create_connection((host, port), timeout=timeout):
            open_ = True
    except OSError:
        open_ = False

    if use_cache:
        _tunnel_probe_cache = open_
    return open_


def egress_proxy_url(
    environ: Mapping[str, str] | None = None,
    *,
    probe: bool = True,
) -> str | None:
    """
    HTTP(S) or SOCKS proxy for the WebSocket transport.

    ``SAND_EGRESS_TUNNEL_PROXY_ADDR`` wins. Otherwise, when ``probe`` is set,
    ``http://127.0.0.1:8791`` is used if that port accepts connections.
    """
    env = os.environ if environ is None else environ
    raw = str(env.get(EGRESS_PROXY_ENV, "")).strip()
    if raw:
        return normalize_proxy_addr(raw)
    if probe and local_tunnel_available():
        return DEFAULT_TUNNEL_URL
    return None


def dc_number(dc_id: int | None) -> int:
    """Absolute production DC id. Unknown values fall back to DC 2."""
    try:
        number = abs(int(dc_id))
    except (TypeError, ValueError):
        return DEFAULT_DC
    if number in DC_WEB_NAMES:
        return number
    return DEFAULT_DC


def web_host_for_dc(dc_id: int | None) -> str:
    """``{planet}.web.telegram.org`` for a Telegram DC."""
    try:
        number = abs(int(dc_id))
    except (TypeError, ValueError):
        number = DEFAULT_DC
    name = DC_WEB_NAMES.get(number, DC_WEB_NAMES[DEFAULT_DC])
    return f"{name}.web.telegram.org"


def dc_host_was_known(dc_id: int | None) -> bool:
    try:
        return abs(int(dc_id)) in DC_WEB_NAMES
    except (TypeError, ValueError):
        return False
