# ©️ bertffff, 2026
# This file is a part of Kanjo userbot
# 🌐 https://github.com/bertffff/Heroku
# You can redistribute it and/or modify it under the terms of the GNU AGPLv3
# 🔑 https://www.gnu.org/licenses/agpl-3.0.html

"""Legacy Heroku branding is rewritten only when it is still the stock default."""

from __future__ import annotations

import unittest
from types import SimpleNamespace

from herokutl.tl.functions.bots import SetBotInfoRequest
from herokutl.tl.functions.channels import EditTitleRequest
from herokutl.tl.functions.messages import GetDialogFiltersRequest, UpdateDialogFilterRequest

from heroku.brand import (
    ASSET_BANNER,
    KANJO_BOT_NAME,
    LEGACY_BANNER_URLS,
    LEGACY_BOT_NAMES,
    asset_topic_id,
    module_lookup_names,
    module_public_name,
    retarget_forums_cache,
    visible_config_text,
)
from heroku.legacy_branding import (
    bot_rename_target,
    channel_rename_target,
    folder_rename_target,
    migrate_module_banners,
    replacement_banner,
    run_legacy_branding,
)


OLD_INFO = (
    "https://raw.githubusercontent.com/Heroku-userbot/assets/refs/heads/main/heroku_info.jpg"
)
CUSTOM = "https://example.com/my-banner.png"


class BannerMigrationTest(unittest.TestCase):
    def test_only_exact_upstream_defaults_change(self):
        self.assertIn(OLD_INFO, LEGACY_BANNER_URLS)
        self.assertEqual(replacement_banner(OLD_INFO, ASSET_BANNER), ASSET_BANNER)
        self.assertIsNone(replacement_banner(CUSTOM, ASSET_BANNER))
        self.assertIsNone(replacement_banner(ASSET_BANNER, ASSET_BANNER))
        self.assertIsNone(replacement_banner(OLD_INFO + "?size=1", ASSET_BANNER))
        self.assertEqual(replacement_banner(OLD_INFO, OLD_INFO), ASSET_BANNER)

    def test_list_and_tuple_values_replace_only_exact_defaults(self):
        import sys

        sys.argv = ["kanjo", "--no-auth", "--no-git", "--data-root", "/tmp"]
        import heroku.main  # finish the import cycle before validators
        from heroku.validators import RandomLinkList

        self.assertEqual(
            replacement_banner([OLD_INFO], ASSET_BANNER),
            [ASSET_BANNER],
        )
        self.assertEqual(
            replacement_banner([OLD_INFO, CUSTOM], ASSET_BANNER),
            [ASSET_BANNER, CUSTOM],
        )
        self.assertEqual(
            replacement_banner((OLD_INFO, CUSTOM, OLD_INFO + "?x=1"), ASSET_BANNER),
            (ASSET_BANNER, CUSTOM, OLD_INFO + "?x=1"),
        )
        self.assertEqual(
            replacement_banner(RandomLinkList([OLD_INFO, CUSTOM]), ASSET_BANNER),
            [ASSET_BANNER, CUSTOM],
        )
        self.assertIsNone(replacement_banner([CUSTOM], ASSET_BANNER))
        self.assertIsNone(replacement_banner([ASSET_BANNER], ASSET_BANNER))
        self.assertIsNone(replacement_banner([], ASSET_BANNER))
        self.assertIsNone(replacement_banner((CUSTOM,), ASSET_BANNER))
        self.assertIsNone(replacement_banner(None, ASSET_BANNER))
        self.assertEqual(
            replacement_banner([OLD_INFO, 1, CUSTOM], ASSET_BANNER),
            [ASSET_BANNER, 1, CUSTOM],
        )

    def test_saved_random_link_list_is_rewritten_in_config(self):
        import sys

        sys.argv = ["kanjo", "--no-auth", "--no-git", "--data-root", "/tmp"]
        import heroku.main  # finish the import cycle before validators
        from heroku.types import ConfigValue, ModuleConfig
        from heroku.validators import RandomLink

        saved = {}

        def pointer(key, default=None):
            self.assertEqual(key, "__config__")
            return saved

        config = ModuleConfig(
            ConfigValue(
                "banner_url",
                ASSET_BANNER,
                "banner",
                validator=RandomLink(),
            )
        )
        config["banner_url"] = [OLD_INFO, CUSTOM]
        module = SimpleNamespace(name="HerokuInfoMod", config=config, pointer=pointer)
        self.assertEqual(
            migrate_module_banners([module]),
            [("HerokuInfoMod", "banner_url")],
        )
        self.assertEqual(list(config["banner_url"]), [ASSET_BANNER, CUSTOM])
        self.assertEqual(saved["banner_url"], [ASSET_BANNER, CUSTOM])
        self.assertEqual(migrate_module_banners([module]), [])

    def test_apply_is_idempotent_and_keeps_custom_values(self):
        class Cfg(dict):
            def getdef(self, key):
                return {"banner_url": ASSET_BANNER, "note": "keep"}[key]

        info = SimpleNamespace(
            name="HerokuInfo",
            config=Cfg(banner_url=OLD_INFO, note=CUSTOM),
        )
        ping = SimpleNamespace(
            name="Tester",
            config=Cfg(banner_url=CUSTOM, note="keep"),
        )
        self.assertEqual(
            migrate_module_banners([info, ping]),
            [("HerokuInfo", "banner_url")],
        )
        self.assertEqual(info.config["banner_url"], ASSET_BANNER)
        self.assertEqual(ping.config["banner_url"], CUSTOM)
        self.assertEqual(migrate_module_banners([info, ping]), [])


class NameAliasTest(unittest.TestCase):
    def test_lookup_accepts_heroku_and_kanjo_names(self):
        import sys

        argv = sys.argv
        sys.argv = ["kanjo", "--no-auth", "--no-git", "--data-root", "/tmp"]
        try:
            from heroku.loader import Modules
        finally:
            sys.argv = argv

        class HerokuInfoMod:
            name = "HerokuInfo"

        module = HerokuInfoMod()
        self.assertEqual(module_public_name(module), "KanjoInfo")
        self.assertIn("herokuinfo", module_lookup_names(module))
        self.assertIn("kanjoinfo", module_lookup_names(module))
        self.assertIn("herokuinfomod", module_lookup_names(module))

        stub = SimpleNamespace(modules=[module], libraries=[])
        self.assertIs(Modules.lookup(stub, "HerokuInfo"), module)
        self.assertIs(Modules.lookup(stub, "KanjoInfo"), module)
        self.assertIs(Modules.lookup(stub, "herokuinfomod"), module)
        self.assertFalse(Modules.lookup(stub, "OtherInfo"))

    def test_config_value_shows_emoji_fallback(self):
        raw = '<tg-emoji emoji-id="4974681956907221809">▪️</tg-emoji>'
        shown = visible_config_text(raw)
        self.assertEqual(shown, "▪️")
        self.assertNotIn("tg-emoji", shown)
        self.assertEqual(raw, '<tg-emoji emoji-id="4974681956907221809">▪️</tg-emoji>')

    def test_bot_and_titles_match_only_the_old_default(self):
        self.assertEqual(bot_rename_target("🪐 Heroku userbot"), KANJO_BOT_NAME)
        self.assertIsNone(bot_rename_target("My helper"))
        self.assertIsNone(bot_rename_target(KANJO_BOT_NAME))
        self.assertEqual(next(iter(LEGACY_BOT_NAMES)), "🪐 Heroku userbot")
        self.assertEqual(channel_rename_target("heroku-userbot"), "kanjo-userbot")
        self.assertIsNone(channel_rename_target("kanjo-userbot"))
        self.assertIsNone(channel_rename_target("heroku-userbot-extra"))
        self.assertEqual(folder_rename_target("Heroku"), "Kanjo")
        self.assertIsNone(folder_rename_target("Kanjo"))
        self.assertIsNone(folder_rename_target("heroku"))


class MigrationRunTest(unittest.IsolatedAsyncioTestCase):
    async def test_run_renames_exact_defaults_once(self):
        store = {
            "heroku.main": {},
            "heroku.forums": {
                "channel_id": 10,
                "forums_cache": {"heroku-userbot": {"Assets": 3}},
            },
            "heroku.inline": {"bot_token": "1:abc"},
        }

        class Db:
            def get(self, owner, key, default=None):
                return store.get(owner, {}).get(key, default)

            def set(self, owner, key, value):
                store.setdefault(owner, {})[key] = value

        class Cfg(dict):
            def getdef(self, key):
                return ASSET_BANNER

        module = SimpleNamespace(name="HerokuInfo", config=Cfg(banner_url=OLD_INFO))
        calls = []

        class Client:
            heroku_inline = SimpleNamespace(
                init_complete=True,
                bot_username="kanjo_abcdef_bot",
                _db=Db(),
            )

            async def get_entity(self, ref):
                calls.append(("entity", ref))
                if ref == 10:
                    return SimpleNamespace(id=10, title="heroku-userbot")
                return SimpleNamespace(id=99, first_name="🪐 Heroku userbot", username=ref)

            async def __call__(self, request):
                calls.append(request)
                if isinstance(request, GetDialogFiltersRequest):
                    return SimpleNamespace(
                        filters=[
                            SimpleNamespace(
                                id=2,
                                title=SimpleNamespace(text="Heroku", entities=[]),
                                include_peers=[],
                            )
                        ]
                    )
                return True

        client = Client()
        done = await run_legacy_branding(
            Db(),
            client,
            [module],
            enabled=True,
            inline_wait=0,
        )
        self.assertTrue(done)
        self.assertEqual(module.config["banner_url"], ASSET_BANNER)
        self.assertEqual(store["heroku.main"]["legacy_branding_version"], 2)
        self.assertTrue(store["heroku.main"]["legacy_branding_migrated"])
        self.assertEqual(store["heroku.forums"]["forums_cache"]["kanjo-userbot"]["Assets"], 3)
        self.assertEqual(asset_topic_id(store["heroku.forums"]["forums_cache"], "Assets"), 3)
        titles = [call for call in calls if isinstance(call, EditTitleRequest)]
        self.assertEqual(titles[0].title, "kanjo-userbot")
        folders = [call for call in calls if isinstance(call, UpdateDialogFilterRequest)]
        self.assertEqual(folders[0].filter.title.text, "Kanjo")
        renames = [call for call in calls if isinstance(call, SetBotInfoRequest)]
        self.assertEqual(renames[0].name, KANJO_BOT_NAME)
        self.assertFalse(hasattr(renames[0], "username") and False)

        calls_after = len(calls)
        module.config["banner_url"] = CUSTOM
        again = await run_legacy_branding(
            Db(),
            client,
            [module],
            enabled=True,
            inline_wait=0,
        )
        self.assertFalse(again)
        self.assertEqual(module.config["banner_url"], CUSTOM)
        self.assertEqual(len(calls), calls_after)

    async def test_finished_install_migrates_list_banners_without_renames(self):
        from herokutl.tl.functions.messages import GetDialogFiltersRequest

        store = {"heroku.main": {"legacy_branding_migrated": True}}

        class Db:
            def get(self, owner, key, default=None):
                return store.get(owner, {}).get(key, default)

            def set(self, owner, key, value):
                store.setdefault(owner, {})[key] = value

        class Cfg(dict):
            def getdef(self, key):
                return ASSET_BANNER

        saved = {}

        def pointer(key, default=None):
            return saved

        module = SimpleNamespace(
            name="HerokuInfoMod",
            config=Cfg(banner_url=[OLD_INFO, CUSTOM]),
            pointer=pointer,
        )
        calls = []

        class Client:
            heroku_inline = SimpleNamespace(init_complete=True, bot_username="kanjo_bot")

            async def get_entity(self, ref):
                raise AssertionError(ref)

            async def __call__(self, request):
                calls.append(request)
                if isinstance(request, GetDialogFiltersRequest):
                    raise AssertionError("folder rename is a finished step")
                raise AssertionError(type(request).__name__)

        done = await run_legacy_branding(
            Db(),
            Client(),
            [module],
            enabled=True,
            inline_wait=0,
        )
        self.assertTrue(done)
        self.assertEqual(calls, [])
        self.assertEqual(module.config["banner_url"], [ASSET_BANNER, CUSTOM])
        self.assertEqual(saved["banner_url"], [ASSET_BANNER, CUSTOM])
        self.assertEqual(store["heroku.main"]["legacy_branding_version"], 2)
        self.assertTrue(store["heroku.main"]["legacy_branding_migrated"])

        module.config["banner_url"] = [OLD_INFO]
        again = await run_legacy_branding(
            Db(),
            Client(),
            [module],
            enabled=True,
            inline_wait=0,
        )
        self.assertFalse(again)
        self.assertEqual(module.config["banner_url"], [OLD_INFO])

    async def test_pending_bot_rename_does_not_mark_later_steps_done(self):
        class Db:
            def __init__(self):
                self.store = {
                    "heroku.main": {},
                    "heroku.inline": {"bot_token": "1:abc"},
                }

            def get(self, owner, key, default=None):
                return self.store.get(owner, {}).get(key, default)

            def set(self, owner, key, value):
                self.store.setdefault(owner, {})[key] = value

        database = Db()

        class Cfg(dict):
            def getdef(self, key):
                return ASSET_BANNER

        module = SimpleNamespace(
            name="HerokuInfo",
            config=Cfg(banner_url=[OLD_INFO]),
        )

        class Client:
            heroku_inline = SimpleNamespace(
                init_complete=True,
                bot_username=None,
                _db=database,
            )

            async def get_entity(self, ref):
                raise AssertionError(ref)

            async def __call__(self, request):
                from herokutl.tl.functions.messages import GetDialogFiltersRequest

                if isinstance(request, GetDialogFiltersRequest):
                    return SimpleNamespace(filters=[])
                raise AssertionError(type(request).__name__)

        done = await run_legacy_branding(
            database,
            Client(),
            [module],
            enabled=True,
            inline_wait=0,
        )
        self.assertFalse(done)
        self.assertNotIn("legacy_branding_version", database.store["heroku.main"])
        self.assertEqual(module.config["banner_url"], [ASSET_BANNER])

    def test_retarget_keeps_topics_under_the_new_title(self):
        cache = retarget_forums_cache({"heroku-userbot": {"Logs": 9}})
        self.assertEqual(cache["kanjo-userbot"]["Logs"], 9)
        self.assertEqual(asset_topic_id(cache, "Logs"), 9)


if __name__ == "__main__":
    unittest.main()
