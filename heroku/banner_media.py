# ©️ bertffff, 2026
# This file is a part of Kanjo userbot
# 🌐 https://github.com/bertffff/Heroku
# You can redistribute it and/or modify it under the terms of the GNU AGPLv3
# 🔑 https://www.gnu.org/licenses/agpl-3.0.html

"""Send the built-in banner from disk and reuse Telegram's file reference.

Telegram's own fetcher often fails ``send_photo`` for
``raw.githubusercontent.com`` (``WebpageCurlFailedError``), including when a
previous 404 is still cached. The stock banner is a file in ``assets/``, so
that URL is not sent. The uploaded photo's file reference is kept in memory
for this process and in the database for the next start. Custom URLs are not
handled here.
"""

from __future__ import annotations

import asyncio
import base64
import logging
from pathlib import Path

from .brand import ASSET_BANNER, ASSET_FAVICON, ASSET_LOGO, local_asset

logger = logging.getLogger(__name__)

BANNER_CACHE_NS = "heroku.main"
BANNER_CACHE_KEY = "banner_file_refs"

_URL_TO_ASSET = {
    ASSET_BANNER: "banner.png",
    ASSET_LOGO: "logo.png",
    ASSET_FAVICON: "favicon.png",
}
_ASSET_NAMES = frozenset(_URL_TO_ASSET.values())

# (id(db) or 0, scope, asset name) -> (stamp, reusable media)
_memory: dict[tuple, tuple[dict, object]] = {}
_locks: dict[tuple, asyncio.Lock] = {}


class _NotBuiltin:
    pass


NOT_BUILTIN = _NotBuiltin()


def reset_banner_cache() -> None:
    """Drop the in-memory file references. The database is left as it is."""
    _memory.clear()
    _locks.clear()


def is_flood(error: BaseException) -> bool:
    return type(error).__name__ in {"FloodWaitError", "FloodPremiumWaitError"}


def builtin_asset_name(photo) -> str | None:
    """Asset file name when ``photo`` is a built-in default, else None.

    Exact URL matches count, and so does the local ``assets`` path. A custom
    URL that merely ends in ``banner.png`` does not.
    """
    if isinstance(photo, str):
        mapped = _URL_TO_ASSET.get(photo)
        if mapped:
            return mapped
        return _local_asset_name(photo)
    url = None
    for attr in ("url", "webpage"):
        value = getattr(photo, attr, None)
        if isinstance(value, str):
            url = value
            break
    if url is None:
        return None
    return _URL_TO_ASSET.get(url)


def _local_asset_name(value: str) -> str | None:
    try:
        path = Path(value)
        if path.name not in _ASSET_NAMES or not path.is_file():
            return None
        if path.resolve() != local_asset(path.name).resolve():
            return None
    except OSError:
        return None
    return path.name


def _cache_key(db, scope: str, name: str) -> tuple:
    return (id(db) if db is not None else 0, str(scope), name)


def _lock(key: tuple) -> asyncio.Lock:
    lock = _locks.get(key)
    if lock is None:
        lock = asyncio.Lock()
        _locks[key] = lock
    return lock


def _asset_stamp(name: str) -> dict | None:
    path = local_asset(name)
    try:
        if not path.is_file():
            return None
        stat = path.stat()
    except OSError:
        return None
    return {"mtime_ns": int(stat.st_mtime_ns), "size": int(stat.st_size)}


def _bucket(db, scope: str) -> dict:
    if db is None:
        return {}
    try:
        raw = db.get(BANNER_CACHE_NS, BANNER_CACHE_KEY, {})
    except Exception:
        logger.debug("Banner cache read failed", exc_info=True)
        return {}
    if not isinstance(raw, dict):
        return {}
    bucket = raw.get(scope)
    return bucket if isinstance(bucket, dict) else {}


def _write_bucket(db, scope: str, bucket: dict) -> None:
    if db is None:
        return
    try:
        raw = db.get(BANNER_CACHE_NS, BANNER_CACHE_KEY, {})
        if not isinstance(raw, dict):
            raw = {}
        else:
            raw = dict(raw)
        raw[str(scope)] = bucket
        db.set(BANNER_CACHE_NS, BANNER_CACHE_KEY, raw)
    except Exception:
        logger.warning("Could not store the banner file reference", exc_info=True)


def _reusable_media(result):
    candidates = [result]
    media = getattr(result, "media", None)
    if media is not None:
        candidates.append(media)
        candidates.append(getattr(media, "photo", None))
        candidates.append(getattr(media, "document", None))
    candidates.append(getattr(result, "photo", None))
    candidates.append(getattr(result, "document", None))
    for obj in candidates:
        if obj is None:
            continue
        ref = getattr(obj, "file_reference", None)
        photo_id = getattr(obj, "id", None)
        access_hash = getattr(obj, "access_hash", None)
        if (
            isinstance(photo_id, int)
            and not isinstance(photo_id, bool)
            and isinstance(access_hash, int)
            and not isinstance(access_hash, bool)
            and isinstance(ref, (bytes, bytearray))
            and ref
        ):
            return obj
    return None


def _kind(media) -> str:
    if "document" in type(media).__name__.lower():
        return "document"
    return "photo"


def _record(media, stamp: dict) -> dict:
    return {
        "id": int(media.id),
        "access_hash": int(media.access_hash),
        "file_reference": base64.b64encode(bytes(media.file_reference)).decode("ascii"),
        "kind": _kind(media),
        "mtime_ns": stamp["mtime_ns"],
        "size": stamp["size"],
    }


def _media_from_record(record: dict):
    from herokutl.tl.types import InputDocument, InputPhoto

    try:
        ref = base64.b64decode(record["file_reference"], validate=True)
        photo_id = int(record["id"])
        access_hash = int(record["access_hash"])
    except (KeyError, TypeError, ValueError):
        return None
    if not ref:
        return None
    cls = InputDocument if record.get("kind") == "document" else InputPhoto
    return cls(id=photo_id, access_hash=access_hash, file_reference=ref)


def _lookup(db, scope: str, name: str):
    stamp = _asset_stamp(name)
    if stamp is None:
        return None
    key = _cache_key(db, scope, name)
    cached = _memory.get(key)
    if cached is not None and cached[0] == stamp:
        return cached[1]
    record = _bucket(db, scope).get(name)
    if not isinstance(record, dict):
        return None
    if record.get("mtime_ns") != stamp["mtime_ns"] or record.get("size") != stamp["size"]:
        return None
    media = _media_from_record(record)
    if media is None:
        return None
    _memory[key] = (stamp, media)
    return media


def _remember(result, name: str, *, db, scope: str) -> None:
    media = _reusable_media(result)
    stamp = _asset_stamp(name)
    if media is None or stamp is None:
        return
    _memory[_cache_key(db, scope, name)] = (stamp, media)
    bucket = dict(_bucket(db, scope))
    bucket[name] = _record(media, stamp)
    _write_bucket(db, scope, bucket)


def _forget(db, scope: str, name: str) -> None:
    _memory.pop(_cache_key(db, scope, name), None)
    if db is None:
        return
    bucket = dict(_bucket(db, scope))
    bucket.pop(name, None)
    _write_bucket(db, scope, bucket)


async def send_builtin_banner(send, photo, *, db=None, scope: str = "session"):
    """Upload or reuse a built-in banner.

    Returns ``NOT_BUILTIN`` when ``photo`` is not a stock asset that exists
    on disk. The caller then keeps its URL behaviour. Flood waits propagate.
    A cached reference that Telegram rejects is dropped and the local file
    is uploaded once. Flood waits propagate.
    """
    name = builtin_asset_name(photo)
    if not name or _asset_stamp(name) is None:
        return NOT_BUILTIN
    key = _cache_key(db, scope, name)
    async with _lock(key):
        cached = _lookup(db, scope, name)
        if cached is not None:
            try:
                logger.debug("Reusing cached banner %s (%s)", name, scope)
                return await send(cached)
            except Exception as error:
                if is_flood(error):
                    raise
                logger.warning(
                    "Cached banner %s failed (%s); uploading it again",
                    name,
                    type(error).__name__,
                )
                _forget(db, scope, name)
        logger.debug("Uploading built-in banner %s (%s)", name, scope)
        result = await send(str(local_asset(name)))
        _remember(result, name, db=db, scope=scope)
        return result
