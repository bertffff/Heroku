# ©️ Dan Gazizullin, 2021-2023
# This file is a part of Hikka Userbot
# 🌐 https://github.com/hikariatama/Hikka
# You can redistribute it and/or modify it under the terms of the GNU AGPLv3
# 🔑 https://www.gnu.org/licenses/agpl-3.0.html

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

"""User-facing identity for Kanjo.

The import package stays ``heroku`` so existing modules, database keys and
``python -m heroku`` keep working. Change ``REPO_URL`` here when the Git
remote is renamed; the updater and install docs read this constant.
"""

from __future__ import annotations

import os
from collections.abc import MutableMapping

NAME = "Kanjo"
EMOJI = "🎴"

# Display version. Independent from heroku.version.__version__, which stays
# at the Heroku 2.2.0 baseline so `# scope: heroku_min` checks still pass.
KANJO_VERSION = (1, 0, 0)
UPSTREAM_VERSION = (2, 2, 0)
UPSTREAM_LABEL = "Heroku " + ".".join(map(str, UPSTREAM_VERSION))

ATTRIBUTION = (
    "Kanjo is based on Heroku Userbot (github.com/coddrago/Heroku), "
    "itself a fork of Hikka (github.com/hikariatama/Hikka); licensed AGPL-3.0"
)
ATTRIBUTION_HTML = (
    'Kanjo is based on <a href="https://github.com/coddrago/Heroku">Heroku Userbot</a>, '
    'itself a fork of <a href="https://github.com/hikariatama/Hikka">Hikka</a>; '
    "licensed AGPL-3.0."
)

# Single source for the Git remote. The GitHub repository is still named Heroku.
REPO_SLUG = "bertffff/Heroku"
REPO_URL = f"https://github.com/{REPO_SLUG}"
REPO_GIT = REPO_URL + ".git"
RAW_BASE = f"https://raw.githubusercontent.com/{REPO_SLUG}/master"
ASSET_BANNER = f"{RAW_BASE}/assets/banner.png"
ASSET_LOGO = f"{RAW_BASE}/assets/logo.png"
ASSET_FAVICON = f"{RAW_BASE}/assets/favicon.png"

# HEROKU_* remains the name the rest of the code writes. KANJO_* is accepted
# when the Heroku variable is unset or blank. A non-empty HEROKU_* wins.
ENV_SUFFIXES = (
    "TRANSPORT",
    "NO_GIT",
    "OPTIONAL_MODULES",
    "DO_NOT_RESTART",
    "DO_NOT_RESTART2",
    "ALLOW_INSECURE_PROXY",
    "REPO_URL",
    "VENV_DIR",
    "MINIMAL",
    "BRANCH",
    "FORCE_INSTALL",
)


def display_version() -> str:
    """User-facing version, for example ``Kanjo 1.0.0``."""
    return NAME + " " + ".".join(map(str, KANJO_VERSION))


def app_version() -> str:
    """String stored as the Telegram client app version."""
    return display_version()


def _mapping(environ: MutableMapping[str, str] | None) -> MutableMapping[str, str]:
    return os.environ if environ is None else environ


def _nonempty(value: str | None) -> bool:
    return value is not None and str(value).strip() != ""


def env_get(
    suffix: str,
    default: str | None = None,
    environ: MutableMapping[str, str] | None = None,
) -> str | None:
    """Read ``HEROKU_<suffix>``, then ``KANJO_<suffix>``."""
    env = _mapping(environ)
    heroku_val = env.get(f"HEROKU_{suffix}")
    if _nonempty(heroku_val):
        return heroku_val
    kanjo_val = env.get(f"KANJO_{suffix}")
    if _nonempty(kanjo_val):
        return kanjo_val
    return default


def env_get_source(
    suffix: str,
    environ: MutableMapping[str, str] | None = None,
) -> tuple[str | None, str]:
    """Return ``(value, variable name)`` for logs. Blank values are skipped."""
    env = _mapping(environ)
    heroku_key = f"HEROKU_{suffix}"
    kanjo_key = f"KANJO_{suffix}"
    heroku_val = env.get(heroku_key)
    if _nonempty(heroku_val):
        return heroku_val, heroku_key
    kanjo_val = env.get(kanjo_key)
    if _nonempty(kanjo_val):
        return kanjo_val, kanjo_key
    return None, heroku_key


def env_flag(suffix: str, environ: MutableMapping[str, str] | None = None) -> bool:
    """True when the alias pair is exactly ``1``."""
    return str(env_get(suffix, "", environ) or "").strip() == "1"


def apply_env_aliases(environ: MutableMapping[str, str] | None = None) -> None:
    """Copy ``KANJO_*`` into ``HEROKU_*`` when ``HEROKU_*`` is unset or blank.

    Existing non-empty ``HEROKU_*`` values are left alone, so current installs
    and scripts keep their behavior. Call this before code that still reads
    ``HEROKU_*`` directly.
    """
    env = _mapping(environ)
    for suffix in ENV_SUFFIXES:
        heroku_key = f"HEROKU_{suffix}"
        if _nonempty(env.get(heroku_key)):
            continue
        alias = env.get(f"KANJO_{suffix}")
        if _nonempty(alias):
            env[heroku_key] = alias
