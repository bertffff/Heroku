# ©️ Codrago, 2024-2030
# This file is a part of Heroku Userbot
# 🌐 https://github.com/Heroku-userbot/Heroku
# You can redistribute it and/or modify it under the terms of the GNU AGPLv3
# 🔑 https://www.gnu.org/licenses/agpl-3.0.html

"""Network transports used by the Heroku client."""

from herokutl.network.connection import (
    ConnectionTcpFull,
    ConnectionTcpMTProxyRandomizedIntermediate,
)

from .transport import (
    cli_transport_default,
    dc_number,
    decide_connection_mode,
    egress_proxy_url,
    normalize_transport_name,
    redact_proxy_url,
    resolve_transport,
    web_host_for_dc,
)
from .ws_obfuscated import ConnectionWsObfuscated

__all__ = [
    "ConnectionWsObfuscated",
    "cli_transport_default",
    "client_transport",
    "connection_for_settings",
    "dc_number",
    "decide_connection_mode",
    "egress_proxy_url",
    "normalize_transport_name",
    "redact_proxy_url",
    "resolve_transport",
    "web_host_for_dc",
]


def _runtime_transport_choice():
    """
    ``--transport`` / proxy flags from the running Heroku process.

    Returns ``(transport, proxy_host, proxy_port, proxy_secret, proxy_type)``.
    Missing process state is treated as ``auto`` with no explicit proxy.
    """
    from .. import main as heroku_main

    heroku = getattr(heroku_main, "heroku", None)

    arguments = getattr(heroku, "arguments", None) if heroku is not None else None
    transport = normalize_transport_name(
        getattr(arguments, "transport", None) if arguments is not None else None
    )
    host = getattr(arguments, "proxy_host", None) if arguments is not None else None
    port = getattr(arguments, "proxy_port", None) if arguments is not None else None
    secret = getattr(arguments, "proxy_secret", None) if arguments is not None else None
    proxy_type = (
        (getattr(arguments, "proxy_type", None) or "mtproxy").lower()
        if arguments is not None
        else "mtproxy"
    )
    return transport, host, port, secret, proxy_type


def connection_for_settings(
    transport: str | None,
    *,
    proxy_host: str | None = None,
    proxy_port: int | None = None,
    proxy_secret: str | None = None,
    proxy_type: str | None = None,
    egress_url: str | None = None,
) -> tuple[type, tuple | dict | None]:
    """
    Same connection class and proxy as ``Heroku._get_proxy``.

    Explicit proxy flags keep MTProxy / SOCKS / HTTP. Otherwise ``auto`` uses
    obfuscated WebSocket when ``egress_url`` is set, ``ws`` always does, and
    ``tcp`` stays on ``ConnectionTcpFull``.
    """
    proxy_type = (proxy_type or "mtproxy").lower()
    mode = decide_connection_mode(
        transport,
        proxy_host=proxy_host,
        proxy_port=proxy_port,
        proxy_secret=proxy_secret,
        egress_url=egress_url,
    )
    if mode == "ws":
        return ConnectionWsObfuscated, None

    if mode != "proxy":
        return ConnectionTcpFull, None

    if not proxy_host or not proxy_port:
        raise ValueError("--proxy-host and --proxy-port must be passed together")

    if proxy_type == "mtproxy":
        if not proxy_secret:
            raise ValueError("--proxy-secret is required for --type-proxy mtproxy")
        return (
            ConnectionTcpMTProxyRandomizedIntermediate,
            (proxy_host, proxy_port, proxy_secret),
        )

    if proxy_secret:
        raise ValueError(
            "--proxy-secret can only be used with --type-proxy mtproxy"
        )

    return ConnectionTcpFull, {
        "proxy_type": proxy_type,
        "addr": proxy_host,
        "port": proxy_port,
    }


def client_transport(client) -> tuple[type, tuple | dict | None]:
    """
    Connection class and proxy for another Telegram client.

    The running user client already picked these (``_connection`` / ``_proxy``),
    including obfuscated WebSocket when raw DC TCP is blocked. Fall back to the
    same auto/ws/tcp rules as ``main.py`` only when that client has no class yet.
    """
    connection = getattr(client, "_connection", None)
    if isinstance(connection, type):
        return connection, getattr(client, "_proxy", None)

    transport, host, port, secret, proxy_type = _runtime_transport_choice()
    explicit_proxy = bool(host or port or secret)
    egress = None if transport == "tcp" or explicit_proxy else egress_proxy_url()
    return connection_for_settings(
        transport,
        proxy_host=host,
        proxy_port=port,
        proxy_secret=secret,
        proxy_type=proxy_type,
        egress_url=egress,
    )
