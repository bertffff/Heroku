# ©️ Codrago, 2024-2030
# This file is a part of Heroku Userbot
# 🌐 https://github.com/Heroku-userbot/Heroku
# You can redistribute it and/or modify it under the terms of the GNU AGPLv3
# 🔑 https://www.gnu.org/licenses/agpl-3.0.html

"""Markup, kwargs and fallbacks for the opt-in inline Bot API additions.

No live Telegram connection. Clients are fakes.
"""

from __future__ import annotations

import inspect
import os
import sys
import tempfile
import unittest
from types import SimpleNamespace

os.environ.setdefault("HEROKU_NO_GIT", "1")

from herokutl.errors.rpcbaseerrors import RPCError
from herokutl.errors.rpcerrorlist import FloodWaitError, MessageNotModifiedError
from herokutl.tl import types
from herokutl.tl.functions.messages import SendMediaRequest, SetTypingRequest

from heroku.inline.tl import (
    DraftStream,
    TelethonBot,
    apply_invert_media,
    make_button,
)
from heroku.inline.types import InlineQuery, _CallbackMixin
from heroku.inline.utils import Utils
from heroku.utils.messages import expandable


def _rpc(message="CHAT_WRITE_FORBIDDEN"):
    return RPCError(types.InputPeerEmpty(), message, 403)


def _ensure_main():
    """Import heroku.main without letting pytest's argv reach argparse."""
    if "heroku.main" in sys.modules:
        return
    argv = sys.argv
    root = tempfile.mkdtemp(prefix="heroku-markup-test-")
    sys.argv = [
        "heroku",
        "--data-root",
        root,
        "--no-auth",
        "--no-git",
        "--transport",
        "tcp",
    ]
    try:
        import heroku.main  # noqa: F401
    finally:
        sys.argv = argv


class MarkupHost(Utils):
    def __init__(self):
        self._units = {}
        self._custom_map = {}


class MarkupTests(unittest.TestCase):
    def test_style_and_icon_on_every_button_type(self):
        cases = [
            make_button(text="U", url="https://example.com", style="danger", icon=1),
            make_button(text="D", data=b"x", style="primary", icon=2),
            make_button(
                text="S",
                switch_inline_query="q",
                style="success",
                icon=3,
            ),
            make_button(
                text="C",
                switch_inline_query_current_chat="q",
                style="danger",
                icon=4,
            ),
            make_button(
                text="W",
                web_app="https://example.com/app",
                style="primary",
                icon=5,
            ),
            make_button(
                text="W2",
                web_app={"url": "https://example.com/app2"},
                style="success",
                icon=6,
            ),
            make_button(text="Copy", copy_text="hi", style="danger", icon=7),
            make_button(text="Off", disabled=True, style="success", icon=8),
        ]
        flags = [
            "bg_danger",
            "bg_primary",
            "bg_success",
            "bg_danger",
            "bg_primary",
            "bg_success",
            "bg_danger",
            "bg_success",
        ]
        icons = [1, 2, 3, 4, 5, 6, 7, 8]
        for button, flag, icon in zip(cases, flags, icons):
            self.assertIsInstance(button, types.KeyboardInlineButton)
            self.assertTrue(getattr(button.style, flag))
            self.assertEqual(button.style.icon, icon)

        web = cases[4]
        self.assertIsInstance(web.type, types.InlineButtonTypeWebView)
        self.assertEqual(web.type.url, "https://example.com/app")
        copy = cases[6]
        self.assertIsInstance(copy.type, types.InlineButtonTypeCopy)
        self.assertEqual(copy.type.copy_text, "hi")
        disabled = cases[7]
        self.assertIsInstance(disabled.type, types.InlineButtonTypeDisabled)

    def test_web_app_and_copy_without_style_stay_unstyled(self):
        web = make_button(text="W", web_app="https://example.com")
        copy = make_button(text="C", copy_text="x")
        self.assertIsNone(web.style)
        self.assertIsNone(copy.style)

    def test_generate_markup_disabled_skips_callback(self):
        host = MarkupHost()
        called = {}

        async def callback(call):
            called["hit"] = True

        markup = host._generate_markup(
            [
                [
                    {
                        "text": "Nope",
                        "disabled": True,
                        "callback": callback,
                        "style": "danger",
                        "emoji_id": "42",
                    },
                    {
                        "text": "Copy",
                        "copy": "token",
                        "style": "primary",
                        "emoji_id": "9",
                    },
                    {
                        "text": "App",
                        "web_app": "https://example.com",
                        "style": "success",
                        "emoji_id": "11",
                    },
                ]
            ]
        )
        disabled, copy, web = markup[0]
        self.assertIsInstance(disabled.type, types.InlineButtonTypeDisabled)
        self.assertTrue(disabled.style.bg_danger)
        self.assertEqual(disabled.style.icon, 42)
        self.assertEqual(host._custom_map, {})
        self.assertIsInstance(copy.type, types.InlineButtonTypeCopy)
        self.assertTrue(copy.style.bg_primary)
        self.assertEqual(copy.style.icon, 9)
        self.assertIsInstance(web.type, types.InlineButtonTypeWebView)
        self.assertTrue(web.style.bg_success)
        self.assertEqual(web.style.icon, 11)

    def test_validate_markup_accepts_disabled_only(self):
        host = MarkupHost()
        buttons = [[{"text": "X", "disabled": True}]]
        self.assertEqual(host._validate_markup(buttons), buttons)
        self.assertIsNone(host._validate_markup([[{"text": "bare"}]]))
        self.assertIsNone(
            host._validate_markup([[{"text": "X", "disabled": False}]])
        )

    def test_ephemeral_answer_action_is_wired(self):
        host = MarkupHost()
        markup = host._generate_markup(
            [
                [
                    {
                        "text": "Hint",
                        "action": "answer",
                        "message": "secret",
                        "ephemeral": True,
                    }
                ]
            ]
        )
        self.assertIsInstance(markup[0][0].type, types.InlineButtonTypeCallback)
        handler = next(iter(host._custom_map.values()))["handler"]
        self.assertIs(handler.func.__func__, Utils._answer_ephemeral_unit_handler)
        self.assertEqual(handler.keywords["text"], "secret")

    def test_pagination_keeps_callback_unless_opted_in(self):
        host = MarkupHost()

        def callback(page):
            return page

        current = host.build_pagination(
            callback, total_pages=3, current_page=2, disabled_current=False
        )[0]
        self.assertEqual(current[1]["text"], "· 2 ·")
        self.assertEqual(current[1]["args"], (1,))
        self.assertIs(current[1]["callback"], callback)
        self.assertNotIn("disabled", current[1])

        disabled = host.build_pagination(
            callback, total_pages=3, current_page=2, disabled_current=True
        )[0]
        self.assertEqual(disabled[1], {"text": "· 2 ·", "disabled": True})
        self.assertIs(disabled[0]["callback"], callback)
        self.assertEqual(disabled[0]["args"], (0,))

        early = host.build_pagination(
            callback, total_pages=10, current_page=2, disabled_current=False
        )[0]
        self.assertEqual(
            [button["text"] for button in early],
            [1, "· 2 ·", 3, "4 ›", "10 »"],
        )
        self.assertEqual(
            [button["args"] for button in early],
            [(0,), (1,), (2,), (3,), (9,)],
        )

        middle = host.build_pagination(
            callback, total_pages=10, current_page=5, disabled_current=True
        )[0]
        self.assertEqual(middle[2], {"text": "· 5 ·", "disabled": True})
        self.assertEqual(middle[4]["args"], (9,))
        self.assertEqual(middle[1]["text"], "‹ 4")

        tail = host.build_pagination(
            callback, total_pages=10, current_page=9, disabled_current=True
        )[0]
        self.assertEqual(tail[3], {"text": "· 9 ·", "disabled": True})
        self.assertEqual(tail[0]["text"], "« 1")
        self.assertEqual(tail[1]["args"], (6,))

    def test_pagination_reads_db_flag(self):
        host = MarkupHost()
        host._db = SimpleNamespace(
            get=lambda ns, key, default=None: (
                {"disabled_current_page": True}
                if ns == "InlineStuff" and key == "__config__"
                else default
            )
        )
        page = host.build_pagination(lambda n: n, total_pages=1, current_page=1)[0][0]
        self.assertEqual(page, {"text": "· 1 ·", "disabled": True})

    def test_expandable_helper(self):
        self.assertEqual(
            expandable("<b>log</b>"),
            "<blockquote expandable><b>log</b></blockquote>",
        )

    def test_apply_invert_media_respects_tl_shape(self):
        media = types.InputBotInlineMessageMediaAuto(message="cap")
        result = types.InputBotInlineResult(
            id="1", type="photo", title="t", send_message=media
        )
        apply_invert_media(result, False)
        self.assertFalse(media.invert_media)
        apply_invert_media(result, True)
        self.assertTrue(media.invert_media)

        rich = types.InputBotInlineMessageRichMessage(
            rich_message=types.InputRichMessageHTML(html="<b>x</b>")
        )
        rich_result = types.InputBotInlineResult(
            id="2", type="article", title="t", send_message=rich
        )
        apply_invert_media(rich_result, True)
        self.assertFalse(hasattr(rich, "invert_media"))


class _Recorder:
    def __init__(self, *, fail_protected=False, fail_effect=False, private=True):
        self.calls = []
        self.sent = []
        self.fail_protected = fail_protected
        self.fail_effect = fail_effect
        self.private = private

    async def get_input_entity(self, chat_id):
        if self.private:
            return types.InputPeerUser(int(chat_id), 5)
        return types.InputPeerChannel(int(chat_id), 5)

    async def _parse_message_text(self, text, mode):
        return text or "", []

    async def _file_to_media(self, file, **kwargs):
        return None, types.InputMediaEmpty(), None

    def build_reply_markup(self, markup):
        return markup

    async def __call__(self, request):
        self.calls.append(request)
        if self.fail_protected and isinstance(request, SendMediaRequest):
            raise _rpc("CHAT_FORWARDS_RESTRICTED")
        action = getattr(request, "action", None)
        if self.fail_effect and isinstance(action, types.SendMessageTextDraftAction):
            raise _rpc("CHAT_TYPE_INVALID")
        if getattr(request, "noforwards", None) or getattr(request, "effect", None):
            if self.fail_effect and isinstance(request, SendMediaRequest):
                raise _rpc()
        return SimpleNamespace(id=1)

    def _get_response_message(self, request, result, entity):
        return SimpleNamespace(id=3)

    async def send_message(self, *args, **kwargs):
        self.sent.append(kwargs)
        if kwargs.get("noforwards") or kwargs.get("message_effect_id"):
            raise _rpc("EFFECT_INVALID CHAT_FORWARDS_RESTRICTED")
        return SimpleNamespace(id=4)

    async def send_file(self, *args, **kwargs):
        self.sent.append(kwargs)
        return SimpleNamespace(id=5)


class SendFallbackTests(unittest.IsolatedAsyncioTestCase):
    async def test_send_message_strips_rejected_flags(self):
        client = _Recorder()
        with self.assertLogs("heroku.inline.tl", level="WARNING") as logs:
            message = await TelethonBot(client).send_message(
                7,
                "hi",
                protect_content=True,
                message_effect_id=99,
            )
        self.assertEqual(message.id, 4)
        self.assertEqual(len(client.sent), 2)
        self.assertTrue(client.sent[0]["noforwards"])
        self.assertEqual(client.sent[0]["message_effect_id"], 99)
        self.assertFalse(client.sent[1]["noforwards"])
        self.assertIsNone(client.sent[1]["message_effect_id"])
        self.assertTrue(any("protect_content" in line for line in logs.output))

    async def test_send_message_does_not_retry_unrelated_or_flood(self):
        client = _Recorder()

        async def send_message(*args, **kwargs):
            client.sent.append(kwargs)
            raise _rpc("CHAT_WRITE_FORBIDDEN")

        client.send_message = send_message
        with self.assertRaises(RPCError):
            await TelethonBot(client).send_message(
                7, "hi", protect_content=True, message_effect_id=1
            )
        self.assertEqual(len(client.sent), 1)

        client.sent.clear()

        async def flood(*args, **kwargs):
            client.sent.append(kwargs)
            raise FloodWaitError(types.InputPeerEmpty(), 3)

        client.send_message = flood
        with self.assertRaises(FloodWaitError):
            await TelethonBot(client).send_message(
                7, "hi", protect_content=True, message_effect_id=1
            )
        self.assertEqual(len(client.sent), 1)

        class RichClient:
            def __init__(self):
                self.calls = 0

            async def get_input_entity(self, chat_id):
                return types.InputPeerUser(1, 2)

            def build_reply_markup(self, markup):
                return markup

            def _get_response_message(self, request, result, entity):
                return SimpleNamespace(id=1)

            async def __call__(self, request):
                self.calls += 1
                raise FloodWaitError(request, 4)

        rich = RichClient()
        with self.assertRaises(FloodWaitError):
            await TelethonBot(rich).send_rich_message(
                1, html="<b>x</b>", protect_content=True, message_effect_id=9
            )
        self.assertEqual(rich.calls, 1)

    async def test_protected_media_uses_send_media_then_send_file(self):
        client = _Recorder(fail_protected=True)
        with self.assertLogs("heroku.inline.tl", level="WARNING") as logs:
            message = await TelethonBot(client).send_photo(
                7,
                b"jpeg",
                caption="pic",
                protect_content=True,
                message_effect_id=5,
            )
        self.assertEqual(message.id, 5)
        self.assertTrue(any("protect_content" in line for line in logs.output))
        self.assertIsInstance(client.calls[0], SendMediaRequest)
        self.assertTrue(client.calls[0].noforwards)
        self.assertEqual(client.calls[0].effect, 5)
        self.assertNotIn("noforwards", client.sent[0])
        self.assertEqual(client.sent[0]["message_effect_id"], 5)

    async def test_protected_media_flood_wait_is_not_resent(self):
        class FloodClient(_Recorder):
            async def __call__(self, request):
                self.calls.append(request)
                raise FloodWaitError(request, 2)

        client = FloodClient()
        with self.assertRaises(FloodWaitError):
            await TelethonBot(client).send_photo(7, b"jpeg", protect_content=True)
        self.assertEqual(client.sent, [])
        self.assertEqual(len(client.calls), 1)

    async def test_media_effect_fallback(self):
        client = _Recorder()

        async def send_file(*args, **kwargs):
            client.sent.append(kwargs)
            if kwargs.get("message_effect_id"):
                raise _rpc("EFFECT_INVALID")
            return SimpleNamespace(id=8)

        client.send_file = send_file
        message = await TelethonBot(client).send_document(7, b"doc", message_effect_id=3)
        self.assertEqual(message.id, 8)
        self.assertEqual(client.sent[0]["message_effect_id"], 3)
        self.assertIsNone(client.sent[1]["message_effect_id"])
        self.assertTrue(client.sent[0]["force_document"])

    async def test_draft_private_and_typing_fallback(self):
        client = _Recorder()
        bot = TelethonBot(client)
        result = await bot.send_message_draft(7, "<b>hi</b>", draft_id=42, can_stop=True)
        self.assertTrue(result)
        action = client.calls[0].action
        self.assertIsInstance(client.calls[0], SetTypingRequest)
        self.assertIsInstance(action, types.SendMessageTextDraftAction)
        self.assertEqual(action.random_id, 42)
        self.assertEqual(action.text.text, "<b>hi</b>")
        self.assertTrue(action.can_stop)

        failing = _Recorder(fail_effect=True)
        await TelethonBot(failing).send_message_draft(7, "x", draft_id=1)
        self.assertIsInstance(
            failing.calls[1].action, types.SendMessageTypingAction
        )

        group = _Recorder(private=False)
        self.assertFalse(
            await TelethonBot(group).send_message_draft(7, "x", draft_id=1)
        )
        self.assertEqual(group.calls, [])

    async def test_stream_throttles_and_finalizes(self):
        class Bot:
            def __init__(self):
                self.drafts = []
                self.stops = 0
                self.sent = []

            async def send_message_draft(self, chat_id, text="", *, draft_id, **kwargs):
                self.drafts.append(text)
                return True

            async def stop_message_draft(self, *args, **kwargs):
                self.stops += 1
                return True

            async def send_message(self, chat_id, text="", **kwargs):
                self.sent.append((text, kwargs.get("protect_content")))
                return SimpleNamespace(id=1)

        bot = Bot()
        async with DraftStream(bot, 5, min_interval=0, protect_content=True) as draft:
            await draft.update("one")
            await draft.update("two" * 5000)
        self.assertEqual(bot.drafts[0], "Thinking…")
        self.assertEqual(bot.drafts[1], "one")
        self.assertEqual(len(bot.drafts[2]), 4096)
        self.assertEqual(bot.sent, [(bot.drafts[2], True)])
        self.assertEqual(bot.stops, 1)

        bot = Bot()
        async with DraftStream(bot, 5, min_interval=100) as draft:
            await draft.update("one")
            await draft.update("two")
        self.assertEqual(bot.drafts, ["Thinking…"])
        self.assertEqual(bot.sent, [("two", None)])

        bot = Bot()
        with self.assertRaises(RuntimeError):
            async with DraftStream(bot, 5, min_interval=0) as draft:
                await draft.update("keep")
                raise RuntimeError("boom")
        self.assertEqual(bot.sent, [])
        self.assertEqual(bot.stops, 1)


class EphemeralTests(unittest.IsolatedAsyncioTestCase):
    def _call(self):
        answered = []

        class Call:
            async def get_input_sender(self):
                return types.InputPeerUser(5, 9)

            async def answer(self, text=None, **kwargs):
                answered.append((text, kwargs))

        mixin = _CallbackMixin()
        mixin.original_call = Call()
        mixin.sender_id = 5
        mixin.chat_id = 5
        mixin.id = 77
        mixin.answered = answered
        return mixin

    def _manager(self, client):
        return SimpleNamespace(
            _bot_client=client,
            generate_markup=lambda markup: markup,
        )

    async def test_answer_ephemeral_resolves_input_user(self):
        client = _Recorder()
        mixin = self._call()
        mixin.inline_manager = self._manager(client)
        self.assertTrue(await mixin.answer_ephemeral("<b>secret</b>"))
        request = client.calls[0]
        self.assertIsInstance(request.receiver_id, types.InputUser)
        self.assertEqual(request.receiver_id.user_id, 5)
        self.assertEqual(request.receiver_id.access_hash, 9)
        self.assertEqual(request.query_id, 77)
        self.assertEqual(request.message, "<b>secret</b>")
        self.assertEqual(mixin.answered, [(None, {})])

    async def test_answer_ephemeral_falls_back_to_alert(self):
        class Client(_Recorder):
            async def __call__(self, request):
                raise _rpc("METHOD_INVALID")

        mixin = self._call()
        mixin.inline_manager = self._manager(Client())
        await mixin.answer_ephemeral("x" * 250)
        text, kwargs = mixin.answered[0]
        self.assertEqual(len(text), 200)
        self.assertTrue(kwargs["alert"])

    async def test_rich_only_alert_is_plain_text(self):
        class Client(_Recorder):
            async def __call__(self, request):
                raise _rpc("METHOD_INVALID")

        mixin = self._call()
        mixin.inline_manager = self._manager(Client())
        await mixin.answer_ephemeral(rich_message="<b>hello</b> secret")
        text, kwargs = mixin.answered[0]
        self.assertEqual(text, "hello secret")
        self.assertTrue(kwargs["alert"])

    async def test_replace_retries_without_anchor(self):
        class Client(_Recorder):
            async def __call__(self, request):
                self.calls.append(request)
                if request.anchor:
                    raise _rpc()
                return True

        client = Client()
        mixin = self._call()
        mixin.inline_manager = self._manager(client)
        self.assertTrue(await mixin.answer_ephemeral("ok", replace=True))
        self.assertTrue(client.calls[0].anchor)
        self.assertIsNone(client.calls[1].anchor)


class PreviewAndRichTests(unittest.IsolatedAsyncioTestCase):
    async def test_webpage_article_flags(self):
        class Builder:
            class Client:
                def build_reply_markup(self, buttons):
                    return buttons

            _client = Client()

        query = InlineQuery(SimpleNamespace(id=1, text="", sender_id=2, builder=Builder()))
        result = await query.webpage_article(
            "Heroku",
            "hello <b>there</b>",
            "https://example.com",
            preview_size="large",
            preview_above=True,
            id="fixed",
        )
        message = result.send_message
        self.assertIsInstance(message, types.InputBotInlineMessageMediaWebPage)
        self.assertEqual(message.url, "https://example.com")
        self.assertTrue(message.force_large_media)
        self.assertTrue(message.invert_media)
        self.assertTrue(message.optional)
        self.assertEqual(message.message, "hello there")
        self.assertEqual(result.id, "fixed")

    async def test_edit_unit_preview_and_fallback(self):
        calls = []

        class Client:
            async def edit_message(self, *args, **kwargs):
                calls.append((args, kwargs))
                if kwargs.get("file") is not None or kwargs.get("invert_media"):
                    raise _rpc("WEBPAGE_MEDIA_EMPTY")

        host = MarkupHost()
        host._bot_client = Client()
        host.sanitise_text = lambda text: text
        ok = await host._edit_unit(
            "see https://example.com",
            chat_id=1,
            message_id=2,
            link_preview="https://example.com",
            preview_size="small",
            preview_above=True,
        )
        self.assertTrue(ok)
        self.assertIsInstance(calls[0][1]["file"], types.InputMediaWebPage)
        self.assertTrue(calls[0][1]["file"].force_small_media)
        self.assertTrue(calls[0][1]["file"].optional)
        self.assertTrue(calls[0][1]["invert_media"])
        self.assertTrue(calls[0][1]["link_preview"])
        self.assertNotIn("file", calls[1][1])
        self.assertNotIn("invert_media", calls[1][1])
        self.assertFalse(calls[1][1]["link_preview"])

    async def test_edit_unit_invert_media_fallback(self):
        calls = []

        class Client:
            async def edit_message(self, *args, **kwargs):
                calls.append(kwargs)
                if kwargs.get("invert_media"):
                    raise _rpc()

        host = MarkupHost()
        host._bot_client = Client()
        host.sanitise_text = lambda text: text
        ok = await host._edit_unit(
            "cap",
            photo="https://example.com/a.jpg",
            chat_id=1,
            message_id=2,
            invert_media=True,
        )
        self.assertTrue(ok)
        self.assertTrue(calls[0]["invert_media"])
        self.assertNotIn("invert_media", calls[1])
        self.assertEqual(calls[1]["file"], "https://example.com/a.jpg")

    def test_form_link_preview_modes(self):
        _ensure_main()
        from heroku.inline.form import Form

        plain = Form._form_link_preview(None, {"text": "hi"})
        self.assertEqual(plain, {"mode": "article", "show": False, "above": False})
        webpage = Form._form_link_preview(
            None,
            {
                "text": "see https://example.com/a",
                "preview_size": "large",
                "preview_above": True,
            },
        )
        self.assertEqual(webpage["mode"], "webpage")
        self.assertEqual(webpage["url"], "https://example.com/a")
        self.assertEqual(webpage["size"], "large")
        self.assertTrue(webpage["above"])
        auto = Form._form_link_preview(None, {"text": "no url", "link_preview": True})
        self.assertEqual(auto["mode"], "article")
        self.assertTrue(auto["show"])

    async def test_list_rich_result_and_edit_fallback(self):
        _ensure_main()
        from heroku.inline.list import List

        answered = {}

        class Query:
            from_user = SimpleNamespace(id=1)
            query = "unit"

            async def rich_article(self, **kwargs):
                return {"rich": kwargs["html"]}

            class Builder:
                async def article(self, **kwargs):
                    return {"html": kwargs["text"]}

            builder = Builder()

            async def answer(self, results, **kwargs):
                answered["results"] = results

        host = SimpleNamespace(
            _me=1,
            _units={
                "unit": {
                    "uid": "unit",
                    "type": "list",
                    "rich": True,
                    "strings": ["<b>page</b>"],
                    "premium_emoji_pre_edit": False,
                }
            },
            _error_events={},
            sanitise_text=lambda text: text,
            _list_markup=lambda unit_id: [],
        )
        await List._list_inline_handler(host, Query())
        self.assertEqual(answered["results"], [{"rich": "<b>page</b>"}])

        edits = []

        class Bot:
            async def edit_rich_message(self, *args, **kwargs):
                raise _rpc()

        class BotClient:
            async def edit_message(self, *args, **kwargs):
                edits.append((args, kwargs))

        host.bot = Bot()
        host._bot_client = BotClient()
        await List._edit_list_text(host, "inline-id", "<b>page</b>", "unit")
        self.assertEqual(edits[0][0][0], "inline-id")
        self.assertEqual(edits[0][0][1], "<b>page</b>")
        self.assertEqual(edits[0][1]["parse_mode"], "HTML")

    async def test_rich_list_edit_reraises_flood_wait(self):
        _ensure_main()
        from heroku.inline.list import List

        class Bot:
            async def edit_rich_message(self, *args, **kwargs):
                raise FloodWaitError(types.InputPeerEmpty(), 5)

        class BotClient:
            async def edit_message(self, *args, **kwargs):
                raise AssertionError("HTML fallback")

        host = SimpleNamespace(
            _units={"unit": {"rich": True}},
            bot=Bot(),
            _bot_client=BotClient(),
            _list_markup=lambda unit_id: [],
        )
        with self.assertRaises(FloodWaitError):
            await List._edit_list_text(host, "id", "page", "unit")

    async def test_gallery_invert_does_not_retry_not_modified(self):
        _ensure_main()
        from heroku.inline.gallery import Gallery

        calls = []

        class Client:
            async def edit_message(self, *args, **kwargs):
                calls.append(kwargs)
                raise MessageNotModifiedError(types.InputPeerEmpty())

        host = SimpleNamespace(
            _units={"u": {"invert_media": True}},
            _bot_client=Client(),
            _gallery_markup=lambda unit_id: [],
        )
        with self.assertRaises(MessageNotModifiedError):
            await Gallery._edit_gallery_message(host, "mid", "cap", "u")
        self.assertEqual(len(calls), 1)
        self.assertTrue(calls[0]["invert_media"])


class SignatureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _ensure_main()

    def test_public_kwargs_are_optional(self):
        _ensure_main()
        from heroku.inline.core import _BOT_UPDATE_EVENTS
        from heroku.inline.form import Form
        from heroku.inline.gallery import Gallery
        from heroku.inline.list import List

        form = inspect.signature(Form.form)
        for name, default in (
            ("link_preview", None),
            ("preview_size", None),
            ("preview_above", False),
            ("invert_media", False),
        ):
            self.assertIs(form.parameters[name].default, default)
            self.assertEqual(
                form.parameters[name].kind, inspect.Parameter.KEYWORD_ONLY
            )

        gallery = inspect.signature(Gallery.gallery)
        self.assertIs(gallery.parameters["invert_media"].default, False)
        self.assertEqual(
            gallery.parameters["invert_media"].kind, inspect.Parameter.KEYWORD_ONLY
        )

        listing = inspect.signature(List.list)
        self.assertIs(listing.parameters["rich"].default, False)

        edit = inspect.signature(Utils._edit_unit)
        self.assertIs(edit.parameters["link_preview"].default, None)
        self.assertIs(edit.parameters["invert_media"].default, None)

        added = {
            "business_connection",
            "business_message",
            "edited_business_message",
            "deleted_business_messages",
            "purchased_paid_media",
            "bot_stopped",
            "subscription",
            "ephemeral_callback_query",
        }
        self.assertTrue(added <= set(_BOT_UPDATE_EVENTS))
        self.assertIn("callback_query", _BOT_UPDATE_EVENTS)
        for key in added:
            self.assertIsNotNone(_BOT_UPDATE_EVENTS[key]())


class RichEphemeralReceiverTests(unittest.IsolatedAsyncioTestCase):
    async def test_receiver_becomes_input_user(self):
        from heroku.tl_cache import CustomTelegramClient

        class Client:
            async def get_input_entity(self, entity):
                if entity == "peer":
                    return types.InputPeerUser(1, 2)
                return types.InputPeerUser(3, 4)

            async def __call__(self, request):
                self.request = request
                return "ok"

        client = Client()
        client._rich_input = CustomTelegramClient._rich_input
        await CustomTelegramClient.send_rich_ephemeral(client, "peer", 3, html="<b>hi</b>")
        self.assertIsInstance(client.request.receiver_id, types.InputUser)
        self.assertEqual(client.request.receiver_id.user_id, 3)
        self.assertEqual(client.request.receiver_id.access_hash, 4)
        self.assertIsInstance(client.request.peer, types.InputPeerUser)


if __name__ == "__main__":
    unittest.main()
