# ©️ Codrago, 2024-2030
# This file is a part of Heroku Userbot
# 🌐 https://github.com/Heroku-userbot/Heroku
# You can redistribute it and/or modify it under the terms of the GNU AGPLv3
# 🔑 https://www.gnu.org/licenses/agpl-3.0.html

"""Network transports used by the Heroku client."""

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
    "dc_number",
    "decide_connection_mode",
    "egress_proxy_url",
    "normalize_transport_name",
    "redact_proxy_url",
    "resolve_transport",
    "web_host_for_dc",
]
