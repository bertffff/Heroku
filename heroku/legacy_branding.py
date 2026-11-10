# ©️ bertffff, 2026
# This file is a part of Kanjo userbot
# 🌐 https://github.com/bertffff/Heroku
# You can redistribute it and/or modify it under the terms of the GNU AGPLv3
# 🔑 https://www.gnu.org/licenses/agpl-3.0.html

"""Rewrite of stock Heroku branding on an upgraded install.

Every step matches an exact upstream default. A custom banner, bot name,
channel title, or folder title is left alone. Steps are versioned: a finished
step is not repeated, and a newer step still runs when
``heroku.main.legacy_branding_migrated`` is already true. The boolean flag
stays set so older code can see that version 1 finished. Failures are logged
and do not stop the userbot.
"""

from __future__ import annotations

import asyncio
import logging

from .brand import (
    ASSET_BANNER,
    KANJO_BOT_NAME,
    KANJO_CHANNEL_TITLE,
    KANJO_FOLDER_TITLE,
    LEGACY_BANNER_URLS,
    LEGACY_BOT_NAMES,
    LEGACY_CHANNEL_TITLE,
    LEGACY_FOLDER_TITLE,
    MIGRATION_DB_KEY,
    MIGRATION_DB_NS,
    MIGRATION_VERSION_KEY,
    retarget_forums_cache,
)

logger = logging.getLogger(__name__)


def migration_done(db) -> bool:
    return bool(db.get(MIGRATION_DB_NS, MIGRATION_DB_KEY, False))


def migration_version(db) -> int:
    """Highest finished step.

    A stored integer wins. The older boolean flag, with no integer, is
    version 1: those installs already ran the string-banner and rename step.
    """
    raw = db.get(MIGRATION_DB_NS, MIGRATION_VERSION_KEY, None)
    if isinstance(raw, int) and not isinstance(raw, bool) and raw >= 0:
        return raw
    if migration_done(db):
        return 1
    return 0


def mark_migration_version(db, version: int) -> None:
    db.set(MIGRATION_DB_NS, MIGRATION_VERSION_KEY, int(version))
    if version >= 1:
        db.set(MIGRATION_DB_NS, MIGRATION_DB_KEY, True)


def mark_migration_done(db) -> None:
    mark_migration_version(db, max(migration_version(db), 1))


def _banner_replacement(default) -> str:
    if isinstance(default, str) and default and default not in LEGACY_BANNER_URLS:
        return default
    return ASSET_BANNER


def replacement_banner(current, default):
    """New banner value, or None when nothing is a stock Heroku URL.

    Strings must match a legacy default exactly. List and tuple values are
    walked element by element: only exact legacy defaults are replaced, and
    custom entries stay. The result is a list for a list (including list
    subclasses such as ``RandomLinkList``) and a tuple for a tuple.
    """
    if isinstance(current, (list, tuple)):
        replacement = _banner_replacement(default)
        changed = False
        items = []
        for item in current:
            if isinstance(item, str) and item in LEGACY_BANNER_URLS:
                items.append(replacement)
                changed = True
            else:
                items.append(item)
        if not changed:
            return None
        if isinstance(current, tuple):
            return tuple(items)
        return list(items)
    if not isinstance(current, str) or current not in LEGACY_BANNER_URLS:
        return None
    return _banner_replacement(default)


def migrate_module_banners(modules) -> list[tuple[str, str]]:
    """Reset persisted banner options that still hold an upstream default."""
    changed = []
    for mod in modules or []:
        config = getattr(mod, "config", None)
        if not config:
            continue
        try:
            keys = list(config)
        except Exception:
            logger.warning("Cannot read config of %s", mod, exc_info=True)
            continue
        for key in keys:
            try:
                current = config[key]
                default = config.getdef(key) if hasattr(config, "getdef") else None
                new = replacement_banner(current, default)
                if new is None or new == current:
                    continue
                # Config values are JSON. Tuples become lists, which is what
                # ConfigValue already does on write.
                stored = list(new) if isinstance(new, tuple) else new
                config[key] = stored
                pointer = getattr(mod, "pointer", None)
                if callable(pointer):
                    pointer("__config__", {})[key] = stored
                changed.append((getattr(mod, "name", mod.__class__.__name__), key))
            except Exception:
                logger.warning(
                    "Banner migration skipped %s.%s",
                    getattr(mod, "name", mod),
                    key,
                    exc_info=True,
                )
    if changed:
        logger.info("Replaced stock banner values: %s", changed)
    return changed


def bot_rename_target(current: str | None) -> str | None:
    if current in LEGACY_BOT_NAMES:
        return KANJO_BOT_NAME
    return None


def channel_rename_target(title: str | None) -> str | None:
    if title == LEGACY_CHANNEL_TITLE:
        return KANJO_CHANNEL_TITLE
    return None


def folder_rename_target(title: str | None) -> str | None:
    if title == LEGACY_FOLDER_TITLE:
        return KANJO_FOLDER_TITLE
    return None


def _folder_text(folder) -> str:
    title = getattr(folder, "title", None)
    text = getattr(title, "text", title)
    return str(text or "").strip()


async def _rename_channel(db, client) -> None:
    from herokutl.tl.functions.channels import EditTitleRequest

    channel_id = db.get("heroku.forums", "channel_id", None)
    if not channel_id:
        return
    entity = await client.get_entity(channel_id)
    new_title = channel_rename_target(getattr(entity, "title", None))
    if not new_title:
        return
    await client(EditTitleRequest(entity, new_title))
    try:
        entity.title = new_title
    except Exception:
        logger.warning("Renamed channel title could not be updated in memory", exc_info=True)
    cache = retarget_forums_cache(db.get("heroku.forums", "forums_cache", {}) or {})
    db.set("heroku.forums", "forums_cache", cache)
    logger.info("Renamed asset channel to %s", new_title)


async def _rename_folder(client) -> None:
    from herokutl.tl.functions.messages import (
        GetDialogFiltersRequest,
        UpdateDialogFilterRequest,
    )
    from herokutl.tl.types import TextWithEntities

    folders = await client(GetDialogFiltersRequest())
    for folder in getattr(folders, "filters", folders) or []:
        if folder_rename_target(_folder_text(folder)) != KANJO_FOLDER_TITLE:
            continue
        folder.title = TextWithEntities(text=KANJO_FOLDER_TITLE, entities=[])
        await client(UpdateDialogFilterRequest(folder.id, folder))
        logger.info("Renamed dialog folder to %s", KANJO_FOLDER_TITLE)
        return


async def _rename_bot(client, inline) -> bool:
    """True when the step is finished. False if the bot is not visible yet.

    The username is never changed. A name that is not the old default is
    left as the owner set it.
    """
    from herokutl.tl.functions.bots import SetBotInfoRequest

    username = getattr(inline, "bot_username", None) if inline else None
    token = None
    db = getattr(inline, "_db", None) if inline else None
    if db is not None:
        try:
            token = db.get("heroku.inline", "bot_token", None)
        except Exception:
            token = None
    if not username:
        # A saved token means the inline bot is still starting.
        return not bool(token)
    entity = await client.get_entity(username)
    current = (getattr(entity, "first_name", None) or "").strip()
    target = bot_rename_target(current)
    if target is None:
        return True
    await client(SetBotInfoRequest(lang_code="", bot=entity, name=target))
    logger.info("Renamed inline bot display name to %s", target)
    return True


async def _wait_inline(client, timeout: float = 20):
    if timeout <= 0:
        return getattr(client, "heroku_inline", None)
    waited = 0.0
    while waited < timeout:
        inline = getattr(client, "heroku_inline", None)
        if inline and getattr(inline, "init_complete", False):
            return inline
        await asyncio.sleep(1)
        waited += 1
    return getattr(client, "heroku_inline", None)


async def _step_stock_defaults(db, client, modules, inline_wait: float) -> bool:
    """Version 1: string banners plus the stock channel, folder and bot name.

    Returns False when the inline bot is not visible yet. The caller leaves
    the version unchanged so this step can run again. Banner edits from this
    attempt are kept; they are idempotent.
    """
    try:
        migrate_module_banners(modules)
    except Exception:
        logger.warning("Banner migration failed", exc_info=True)
    try:
        await _rename_channel(db, client)
    except Exception:
        logger.warning("Asset channel rename failed", exc_info=True)
    try:
        await _rename_folder(client)
    except Exception:
        logger.warning("Dialog folder rename failed", exc_info=True)
    bot_ready = True
    try:
        inline = await _wait_inline(client, inline_wait)
        bot_ready = await _rename_bot(client, inline)
    except Exception:
        logger.warning("Inline bot rename failed", exc_info=True)
        bot_ready = False
    if not bot_ready:
        logger.warning("Legacy branding will retry the inline bot on the next start")
        return False
    return True


async def _step_banner_sequences(db, client, modules, inline_wait: float) -> bool:
    """Version 2: banner options stored as a list or tuple.

    Version 1 only rewrote strings, so a ``RandomLink`` value such as
    ``['https://.../heroku_info.jpg']`` was left in place on installs that
    already had ``legacy_branding_migrated`` set.
    """
    del db, client, inline_wait
    migrate_module_banners(modules)
    return True


# (version, name, step). Versions are contiguous and ascending.
_STEPS = (
    (1, "stock_defaults", _step_stock_defaults),
    (2, "banner_sequences", _step_banner_sequences),
)
MIGRATION_VERSION = _STEPS[-1][0]


async def run_legacy_branding(
    db,
    client,
    modules,
    *,
    enabled: bool = True,
    inline_wait: float = 20,
) -> bool:
    """Run migration steps newer than the stored version.

    Returns True when the stored version is the current one after this call.
    A disabled migration, or one that was already current, returns False.
    A step that is not finished does not advance the watermark, and later
    steps wait so a half-finished rename is not skipped.
    """
    if not enabled:
        return False
    try:
        version = migration_version(db)
    except Exception:
        logger.warning("Could not read the branding migration version", exc_info=True)
        return False
    if version >= MIGRATION_VERSION:
        return False
    for step_version, name, step in _STEPS:
        if step_version <= version:
            continue
        try:
            ok = await step(db, client, modules, inline_wait)
        except Exception:
            logger.warning("Legacy branding step %s failed", name, exc_info=True)
            return False
        if not ok:
            logger.warning(
                "Legacy branding step %s will retry on the next start",
                name,
            )
            return False
        try:
            mark_migration_version(db, step_version)
        except Exception:
            logger.warning(
                "Could not store branding migration version %s",
                step_version,
                exc_info=True,
            )
            return False
        version = step_version
    return version >= MIGRATION_VERSION
