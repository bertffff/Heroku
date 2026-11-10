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
import re
from collections.abc import Mapping, MutableMapping
from pathlib import Path

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

# Cache reads prefer the renamed title, then the legacy one.
ASSET_CHANNEL_TITLES = ("kanjo-userbot", "heroku-userbot")
# Which dialog to attach to before a rename: an existing Heroku channel wins.
ASSET_CHANNEL_DIALOG_TITLES = ("heroku-userbot", "kanjo-userbot")
ASSET_FOLDER_TITLES = ("heroku", "kanjo")
LEGACY_CHANNEL_TITLE = "heroku-userbot"
KANJO_CHANNEL_TITLE = "kanjo-userbot"
LEGACY_FOLDER_TITLE = "Heroku"
KANJO_FOLDER_TITLE = "Kanjo"
LEGACY_BOT_NAMES = frozenset({"🪐 Heroku userbot"})
KANJO_BOT_NAME = "🎴 Kanjo userbot"

# Exact banner URLs that shipped as Heroku defaults. A saved custom URL
# is left alone.
LEGACY_BANNER_URLS = frozenset(
    {
        "https://raw.githubusercontent.com/Heroku-userbot/assets/refs/heads/main/heroku_info.jpg",
        "https://raw.githubusercontent.com/Heroku-userbot/assets/refs/heads/main/heroku_cmd.jpg",
        "https://raw.githubusercontent.com/Heroku-userbot/assets/refs/heads/main/start_cmd.jpg",
        "https://raw.githubusercontent.com/Heroku-userbot/assets/refs/heads/main/heroku_started.jpg",
        "https://raw.githubusercontent.com/Heroku-userbot/assets/refs/heads/main/heroku_installation.jpg",
        "https://raw.githubusercontent.com/Heroku-userbot/assets/refs/heads/main/heroku.jpg",
        "https://raw.githubusercontent.com/Heroku-userbot/assets/refs/heads/main/joined_jr.jpg",
        "https://raw.githubusercontent.com/Heroku-userbot/assets/refs/heads/main/declined_jr.jpg",
        "https://raw.githubusercontent.com/Heroku-userbot/assets/refs/heads/main/join_request.jpg",
        "https://raw.githubusercontent.com/Heroku-userbot/assets/refs/heads/main/unit_alpha.jpg",
        "https://raw.githubusercontent.com/Heroku-userbot/assets/refs/heads/main/ping_cmd.jpg",
    }
)

# Stable module ids stay the strings["name"] / database id. .help and
# .config show the Kanjo label, and lookup accepts both.
CORE_DISPLAY_NAMES = {
    "HerokuInfo": "KanjoInfo",
    "HerokuConfig": "KanjoConfig",
    "HerokuSettings": "KanjoSettings",
    "HerokuBackup": "KanjoBackup",
    "HerokuAccounts": "KanjoAccounts",
    "HerokuSecurity": "KanjoSecurity",
}

_TG_EMOJI = re.compile(r"<tg-emoji\b[^>]*>(.*?)</tg-emoji>", re.IGNORECASE | re.DOTALL)

MIGRATION_DB_NS = "heroku.main"
MIGRATION_DB_KEY = "legacy_branding_migrated"
# Integer watermark. Installs that only have the boolean flag are version 1.
MIGRATION_VERSION_KEY = "legacy_branding_version"


def local_asset(name: str) -> Path:
    """Path of a file under the repository ``assets`` directory."""
    return Path(__file__).resolve().parent.parent / "assets" / name


def empty_forums_cache() -> dict:
    """Cache reset that keeps both channel titles addressable."""
    return {title: {} for title in ASSET_CHANNEL_TITLES}


def asset_topic_id(forums_cache: Mapping | None, topic_name: str):
    """Topic id stored under either asset-channel title.

    ``heroku-userbot`` wins when both buckets contain the topic, so an
    install that already has assets keeps using them.
    """
    if not isinstance(forums_cache, Mapping):
        return None
    for title in ASSET_CHANNEL_TITLES:
        bucket = forums_cache.get(title)
        if isinstance(bucket, Mapping) and bucket.get(topic_name):
            return bucket[topic_name]
    return None


def preferred_asset_channel(found: Mapping):
    """Entity for an existing asset channel, legacy title first."""
    for title in ASSET_CHANNEL_DIALOG_TITLES:
        if title in found:
            return found[title]
    return None


def public_module_name(name: str | None) -> str:
    """Name shown in .help and .config. Unknown names pass through."""
    if not name:
        return ""
    return CORE_DISPLAY_NAMES.get(str(name), str(name))


def module_stable_name(mod) -> str:
    """Lookup id stored on the module. Class names and DB keys stay put."""
    stable = str(getattr(mod, "name", "") or "")
    if stable:
        return stable
    strings = getattr(mod, "strings", None)
    try:
        if callable(strings):
            stable = str(strings("name") or "")
        elif isinstance(strings, Mapping):
            stable = str(strings.get("name") or "")
    except Exception:
        stable = ""
    return stable or mod.__class__.__name__


def module_public_name(mod) -> str:
    return public_module_name(module_stable_name(mod))


def module_lookup_names(mod) -> set[str]:
    """Every name that should resolve to this module, lowercased."""
    stable = module_stable_name(mod)
    names = {mod.__class__.__name__, stable, public_module_name(stable)}
    for legacy, shown in CORE_DISPLAY_NAMES.items():
        if stable == shown:
            names.add(legacy)
        if stable == legacy:
            names.add(shown)
    return {name.lower() for name in names if name}


def visible_config_text(value: str) -> str:
    """Fallback character inside a tg-emoji tag. The stored value stays."""
    return _TG_EMOJI.sub(lambda match: match.group(1), value)


def retarget_forums_cache(cache: Mapping | None) -> dict:
    """Keep topic ids readable under both channel titles.

    Both keys share one dict so a later write through either title is seen
    by the other during this process. After a restart, ``kanjo-userbot`` is
    checked first.
    """
    data = dict(cache or {})
    old = data.get(LEGACY_CHANNEL_TITLE)
    new = data.get(KANJO_CHANNEL_TITLE)
    old = dict(old) if isinstance(old, Mapping) else {}
    new = dict(new) if isinstance(new, Mapping) else {}
    merged = {**old, **new}
    data[KANJO_CHANNEL_TITLE] = merged
    data[LEGACY_CHANNEL_TITLE] = merged
    return data

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
