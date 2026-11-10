# ©️ bertffff, 2026
# This file is a part of Kanjo userbot
# 🌐 https://github.com/bertffff/Heroku
# You can redistribute it and/or modify it under the terms of the GNU AGPLv3
# 🔑 https://www.gnu.org/licenses/agpl-3.0.html

"""Built-in banners are uploaded from disk and then reused."""

from __future__ import annotations

import asyncio
import base64
import json
import unittest
from types import SimpleNamespace

from herokutl.errors import FileReferenceExpiredError
from herokutl.tl.types import InputMediaWebPage, InputPhoto

from heroku.banner_media import BANNER_CACHE_KEY, BANNER_CACHE_NS, reset_banner_cache
from heroku.brand import ASSET_BANNER
from heroku.utils.messages import answer_with_media_fallback, send_photo_resilient


class WebpageCurlFailedError(Exception):
    pass


class MemoryDb:
    def __init__(self):
        self.store = {}

    def get(self, owner, key, default=None):
        return self.store.get(owner, {}).get(key, default)

    def set(self, owner, key, value):
        self.store.setdefault(owner, {})[key] = value
        return True


def _uploaded(photo_id=11, access_hash=22, ref=b"abc"):
    return SimpleNamespace(
        media=SimpleNamespace(
            photo=SimpleNamespace(
                id=photo_id,
                access_hash=access_hash,
                file_reference=ref,
            )
        )
    )


class BannerCacheTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        reset_banner_cache()

    async def test_default_banner_uploads_once_and_reuses_the_database_ref(self):
        db = MemoryDb()
        uploads = []

        async def send_photo(photo):
            uploads.append(photo)
            if isinstance(photo, str):
                return _uploaded()
            return "reused"

        async def send_text():
            raise AssertionError("text fallback")

        first = await send_photo_resilient(
            send_photo,
            ASSET_BANNER,
            send_text=send_text,
            db=db,
            scope="bot",
        )
        self.assertIs(first.media.photo.id, 11)
        self.assertTrue(uploads[0].endswith("assets/banner.png"))
        self.assertFalse(uploads[0].startswith("http"))
        json.dumps(db.store)

        reset_banner_cache()
        second = await send_photo_resilient(
            send_photo,
            ASSET_BANNER,
            send_text=send_text,
            db=db,
            scope="bot",
        )
        self.assertEqual(second, "reused")
        self.assertIsInstance(uploads[-1], InputPhoto)
        self.assertEqual(uploads[-1].id, 11)
        self.assertEqual(uploads[-1].access_hash, 22)
        self.assertEqual(uploads[-1].file_reference, b"abc")
        self.assertEqual(sum(isinstance(item, str) for item in uploads), 1)
        cached = db.store[BANNER_CACHE_NS][BANNER_CACHE_KEY]["bot"]["banner.png"]
        self.assertEqual(cached["file_reference"], base64.b64encode(b"abc").decode())

    async def test_user_and_bot_scopes_do_not_share_a_file_reference(self):
        db = MemoryDb()
        uploads = []

        async def send_photo(photo):
            uploads.append(photo)
            if isinstance(photo, str):
                return _uploaded(photo_id=len(uploads))
            return photo

        async def send_text():
            raise AssertionError("text")

        await send_photo_resilient(
            send_photo, ASSET_BANNER, send_text=send_text, db=db, scope="bot"
        )
        await send_photo_resilient(
            send_photo, ASSET_BANNER, send_text=send_text, db=db, scope="user:7"
        )
        self.assertEqual(sum(isinstance(item, str) for item in uploads), 2)
        reset_banner_cache()
        await send_photo_resilient(
            send_photo, ASSET_BANNER, send_text=send_text, db=db, scope="bot"
        )
        self.assertIsInstance(uploads[-1], InputPhoto)
        self.assertEqual(uploads[-1].id, 1)

    async def test_stale_stamp_and_expired_reference_upload_again(self):
        db = MemoryDb()
        db.set(
            BANNER_CACHE_NS,
            BANNER_CACHE_KEY,
            {
                "bot": {
                    "banner.png": {
                        "id": 1,
                        "access_hash": 2,
                        "file_reference": base64.b64encode(b"old").decode(),
                        "kind": "photo",
                        "mtime_ns": 1,
                        "size": 1,
                    }
                }
            },
        )
        uploads = []

        async def send_photo(photo):
            uploads.append(photo)
            if not isinstance(photo, str):
                raise FileReferenceExpiredError(None)
            return _uploaded(photo_id=9, ref=b"new")

        await send_photo_resilient(
            send_photo,
            ASSET_BANNER,
            send_text=lambda: (_ for _ in ()).throw(AssertionError("text")),
            db=db,
            scope="bot",
        )
        self.assertTrue(uploads[0].endswith("banner.png"))
        reset_banner_cache()
        await send_photo_resilient(
            send_photo,
            ASSET_BANNER,
            send_text=lambda: (_ for _ in ()).throw(AssertionError("text")),
            db=db,
            scope="bot",
        )
        self.assertIsInstance(uploads[1], InputPhoto)
        self.assertTrue(uploads[2].endswith("banner.png"))
        self.assertEqual(
            db.store[BANNER_CACHE_NS][BANNER_CACHE_KEY]["bot"]["banner.png"]["id"],
            9,
        )

    async def test_concurrent_sends_upload_once(self):
        db = MemoryDb()
        entered = asyncio.Event()
        release = asyncio.Event()
        paths = []

        async def send_photo(photo):
            if isinstance(photo, str):
                paths.append(photo)
                entered.set()
                await release.wait()
                return _uploaded()
            return "cached"

        first = asyncio.create_task(
            send_photo_resilient(
                send_photo,
                ASSET_BANNER,
                send_text=lambda: (_ for _ in ()).throw(AssertionError("text")),
                db=db,
                scope="bot",
            )
        )
        await asyncio.wait_for(entered.wait(), 1)
        second = asyncio.create_task(
            send_photo_resilient(
                send_photo,
                ASSET_BANNER,
                send_text=lambda: (_ for _ in ()).throw(AssertionError("text")),
                db=db,
                scope="bot",
            )
        )
        await asyncio.sleep(0)
        self.assertFalse(second.done())
        release.set()
        self.assertEqual((await first).media.photo.id, 11)
        self.assertEqual(await second, "cached")
        self.assertEqual(len(paths), 1)

    async def test_custom_url_is_not_treated_as_the_builtin_file(self):
        seen = []

        async def send_photo(photo):
            seen.append(photo)
            if isinstance(photo, str) and photo.startswith("http"):
                raise WebpageCurlFailedError(photo)
            return "local"

        result = await send_photo_resilient(
            send_photo,
            "https://example.com/mine.png",
            send_text=lambda: "text",
        )
        self.assertEqual(result, "local")
        self.assertTrue(seen[0].startswith("https://example.com/"))
        self.assertTrue(seen[1].endswith("assets/banner.png"))

    async def test_flood_wait_is_not_replaced_with_text(self):
        class FloodWaitError(Exception):
            pass

        async def send_photo(photo):
            raise FloodWaitError()

        with self.assertRaises(FloodWaitError):
            await send_photo_resilient(
                send_photo,
                ASSET_BANNER,
                send_text=lambda: "text",
            )

    async def test_quoted_default_banner_uploads_the_local_file(self):
        import heroku.utils.messages as messages

        seen = []

        async def fake_answer(message, *args, **kwargs):
            seen.append(kwargs.get("file"))
            return _uploaded()

        page = InputMediaWebPage(ASSET_BANNER, optional=True)
        original = messages.answer
        messages.answer = fake_answer
        try:
            await answer_with_media_fallback(None, "help", file=page)
            reset_banner_cache()
            db = MemoryDb()
            message = SimpleNamespace(
                client=SimpleNamespace(heroku_db=db, tg_id=42)
            )
            await answer_with_media_fallback(message, "info", file=ASSET_BANNER)
            reset_banner_cache()
            await answer_with_media_fallback(message, "info", file=ASSET_BANNER)
        finally:
            messages.answer = original

        self.assertTrue(seen[0].endswith("assets/banner.png"))
        self.assertNotIsInstance(seen[0], InputMediaWebPage)
        self.assertTrue(seen[1].endswith("assets/banner.png"))
        self.assertIsInstance(seen[2], InputPhoto)
        self.assertEqual(
            db.store[BANNER_CACHE_NS][BANNER_CACHE_KEY]["user:42"]["banner.png"]["id"],
            11,
        )

    async def test_backup_prompt_does_not_block_inline_ready(self):
        import sys

        argv = sys.argv
        sys.argv = ["kanjo", "--no-auth", "--no-git", "--data-root", "/tmp"]
        try:
            import heroku.main  # finish the import cycle before the module
            from heroku.modules.heroku_backup import HerokuBackupMod
        finally:
            sys.argv = argv

        gate = asyncio.Event()
        sent = []

        async def send_photo(chat, photo=None, **kwargs):
            sent.append(photo)
            await gate.wait()
            return _uploaded()

        async def send_message(*args, **kwargs):
            raise AssertionError("text fallback")

        mod = HerokuBackupMod()
        mod._db = MemoryDb()
        mod.tg_id = 5
        mod.strings = {"period": "pick a period"}
        mod.get = lambda key, default=None: None
        mod.inline = SimpleNamespace(
            generate_markup=lambda rows: {"ok": True},
            bot=SimpleNamespace(send_photo=send_photo, send_message=send_message),
        )

        await asyncio.wait_for(mod.inline_ready(), 1)
        await asyncio.sleep(0)
        self.assertFalse(mod._backup_prompt_task.done())
        gate.set()
        await mod._backup_prompt_task
        self.assertTrue(sent[0].endswith("assets/banner.png"))
        self.assertFalse(str(sent[0]).startswith("http"))


if __name__ == "__main__":
    unittest.main()
