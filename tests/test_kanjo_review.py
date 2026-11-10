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

"""Asset-channel cache, folder peers, banner fallback, and command aliases."""

from __future__ import annotations

import unittest
from types import SimpleNamespace

from heroku.brand import asset_topic_id, preferred_asset_channel
from heroku.utils.entity import (
    _matching_dialog_folder,
    attach_bot_to_folder,
    folder_includes_user,
    get_topic_id,
)
from heroku.utils.messages import answer_with_media_fallback, send_photo_resilient


class WebpageCurlFailedError(Exception):
    """Stand-in for the Telethon error raised when a webpage URL 404s."""


class AssetChannelCacheTest(unittest.TestCase):
    def test_kanjo_channel_topic_is_visible(self):
        cache = {"kanjo-userbot": {"Assets": 42}}
        self.assertEqual(asset_topic_id(cache, "Assets"), 42)

    def test_legacy_channel_topic_still_works(self):
        cache = {"heroku-userbot": {"Assets": 7, "Backups": 8}}
        self.assertEqual(asset_topic_id(cache, "Backups"), 8)

    def test_existing_channel_wins_when_both_are_cached(self):
        cache = {
            "heroku-userbot": {"Assets": 1},
            "kanjo-userbot": {"Assets": 2},
        }
        self.assertEqual(asset_topic_id(cache, "Assets"), 1)
        found = {"kanjo-userbot": "new", "heroku-userbot": "old"}
        self.assertEqual(preferred_asset_channel(found), "old")

    def test_missing_topic_is_empty(self):
        self.assertIsNone(asset_topic_id({"kanjo-userbot": {}}, "Assets"))
        self.assertIsNone(asset_topic_id(None, "Assets"))

    def test_get_topic_id_reads_both_titles(self):
        class Db:
            def get(self, owner, key, default=None):
                self.seen = (owner, key)
                return {"kanjo-userbot": {"Logs": 15}}

        import asyncio

        db = Db()
        self.assertEqual(asyncio.run(get_topic_id(db, "Logs")), 15)
        self.assertEqual(db.seen, ("heroku.forums", "forums_cache"))


class FolderPeersTest(unittest.TestCase):
    def test_include_peers_is_the_attribute_that_is_read(self):
        from herokutl.tl.types import InputPeerUser

        folder = SimpleNamespace(
            include_peers=[InputPeerUser(user_id=5, access_hash=0)],
        )
        # The old name must not be required.
        self.assertFalse(hasattr(folder, "include_peer"))
        self.assertTrue(folder_includes_user(folder, 5))
        self.assertFalse(folder_includes_user(folder, 9))

    def test_reuses_heroku_folder_when_kanjo_also_exists(self):
        heroku = SimpleNamespace(title=SimpleNamespace(text="Heroku"), id=1)
        kanjo = SimpleNamespace(title=SimpleNamespace(text="Kanjo"), id=2)
        chosen = _matching_dialog_folder([kanjo, heroku], "kanjo")
        self.assertIs(chosen, heroku)
        self.assertIs(_matching_dialog_folder([kanjo], "heroku"), kanjo)

    def test_updating_a_folder_keeps_the_existing_title(self):
        class DialogFilter:
            def __init__(self, id, title, *args, **kwargs):
                if title is None:
                    raise TypeError(
                        "DialogFilter.__init__() missing 1 required "
                        "positional argument: 'title'"
                    )
                self.id = id
                self.title = title
                self.include_peers = list(kwargs.get("include_peers") or [])
                self.pinned_peers = list(kwargs.get("pinned_peers") or [])
                self.emoticon = kwargs.get("emoticon")
                self.color = kwargs.get("color")

        title = SimpleNamespace(text="Kanjo", entities=[])
        folder = DialogFilter(
            4,
            title,
            include_peers=[],
            pinned_peers=["kept-pin"],
            emoticon="🎴",
            color=1,
        )
        from herokutl.tl.types import InputPeerUser

        bot = InputPeerUser(user_id=9, access_hash=0)
        updated = attach_bot_to_folder(folder, bot)

        self.assertIs(updated, folder)
        self.assertIs(updated.title, title)
        self.assertEqual(updated.title.text, "Kanjo")
        self.assertEqual(updated.pinned_peers, ["kept-pin"])
        self.assertEqual(updated.emoticon, "🎴")
        self.assertEqual(updated.include_peers, [bot])
        with self.assertRaises(TypeError) as caught:
            DialogFilter(4)
        self.assertIn("title", str(caught.exception))


class BannerFallbackTest(unittest.IsolatedAsyncioTestCase):
    async def test_remote_curl_failure_retries_local_file(self):
        import heroku.utils.messages as messages

        seen = []

        async def fake_answer(message, *args, **kwargs):
            seen.append(kwargs.get("file"))
            if isinstance(kwargs.get("file"), str) and kwargs["file"].startswith("http"):
                raise WebpageCurlFailedError("404")
            return "sent"

        original = messages.answer
        messages.answer = fake_answer
        try:
            result = await answer_with_media_fallback(
                None,
                "hello",
                file="https://raw.githubusercontent.com/bertffff/Heroku/master/assets/banner.png",
            )
        finally:
            messages.answer = original

        self.assertEqual(result, "sent")
        self.assertEqual(len(seen), 2)
        self.assertTrue(seen[1].endswith("assets/banner.png"))

    async def test_local_failure_sends_without_photo(self):
        import heroku.utils.messages as messages

        seen = []

        async def fake_answer(message, *args, **kwargs):
            seen.append("file" in kwargs)
            if kwargs.get("file"):
                raise WebpageCurlFailedError("nope")
            return "text-only"

        original = messages.answer
        messages.answer = fake_answer
        try:
            result = await answer_with_media_fallback(
                None,
                "hello",
                file="https://example.invalid/banner.png",
            )
        finally:
            messages.answer = original

        self.assertEqual(result, "text-only")
        self.assertTrue(seen[0])
        self.assertFalse(seen[-1])

    async def test_send_photo_resilient_drops_photo(self):
        calls = []

        async def send_photo(photo):
            calls.append(photo)
            raise WebpageCurlFailedError(photo)

        async def send_text():
            calls.append("text")
            return "ok"

        result = await send_photo_resilient(
            send_photo,
            "https://example.invalid/logo.png",
            send_text=send_text,
        )
        self.assertEqual(result, "ok")
        self.assertEqual(calls[-1], "text")
        self.assertGreaterEqual(len(calls), 2)


class CommandAliasTest(unittest.TestCase):
    def test_kanjo_aliases_resolve_to_the_heroku_commands(self):
        import sys

        argv = sys.argv
        sys.argv = ["kanjo", "--no-auth", "--no-git", "--data-root", "/tmp"]
        try:
            from heroku.loader import Modules
            from heroku.modules.inline_stuff import InlineStuff
            from heroku.modules.settings import CoreMod
        finally:
            sys.argv = argv

        self.assertEqual(CoreMod.herokucmd.alias, "kanjo")
        self.assertEqual(InlineStuff.ch_heroku_bot.alias, "ch_kanjo_bot")

        stub = SimpleNamespace(
            commands={
                "heroku": CoreMod.herokucmd,
                "ch_heroku_bot": InlineStuff.ch_heroku_bot,
            },
            aliases={},
            _core_commands=["heroku", "ch_heroku_bot"],
        )
        self.assertEqual(Modules.find_alias(stub, "kanjo"), "heroku")
        self.assertEqual(Modules.find_alias(stub, "ch_kanjo_bot"), "ch_heroku_bot")
        self.assertIsNone(Modules.find_alias(stub, "heroku"))


if __name__ == "__main__":
    unittest.main()
