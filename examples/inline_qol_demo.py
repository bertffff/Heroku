# ©️ Codrago, 2024-2030
# This file is a part of Heroku Userbot
# 🌐 https://github.com/Heroku-userbot/Heroku
# You can redistribute it and/or modify it under the terms of the GNU AGPLv3
# 🔑 https://www.gnu.org/licenses/agpl-3.0.html

"""Manual checks for the opt-in inline Bot API additions.

Not a core module. Reply to this file with ``.loadmod``.
"""

import asyncio

from herokutl.tl.types import Message

from .. import loader, utils
from ..inline.types import InlineCall

# Private-chat effect. A rejected effect is resent without it.
_EFFECT_ID = 5046509860389126442


@loader.tds
class InlineQoLDemoMod(loader.Module):
    """Exercise disabled buttons, ephemeral replies, previews, rich lists, drafts and protected sends."""

    strings = {"name": "InlineQoLDemo"}

    @loader.command(en_doc="Form with a disabled button and styled copy/web app buttons")
    async def qoldisabledcmd(self, message: Message):
        """Form with a disabled button and styled copy/web app buttons"""
        await self.inline.form(
            "<b>Disabled</b> does nothing. Copy and the web app keep their colour.",
            message,
            reply_markup=[
                [
                    {
                        "text": "Disabled",
                        "disabled": True,
                        "style": "danger",
                    }
                ],
                [
                    {
                        "text": "Copy",
                        "copy": "heroku",
                        "style": "success",
                    },
                    {
                        "text": "Web app",
                        "web_app": "https://example.com",
                        "style": "primary",
                    },
                ],
            ],
        )

    async def _ephemeral_callback(self, call: InlineCall):
        await call.answer_ephemeral("<b>Sent only to you</b> via answer_ephemeral")

    @loader.command(en_doc="Ephemeral button action and answer_ephemeral")
    async def qolephemcmd(self, message: Message):
        """Ephemeral button action and answer_ephemeral"""
        await self.inline.form(
            "Both buttons answer only the person who presses them.",
            message,
            reply_markup=[
                [
                    {
                        "text": "Action",
                        "action": "answer",
                        "message": "<b>ephemeral action</b>",
                        "ephemeral": True,
                        "style": "primary",
                    }
                ],
                [
                    {
                        "text": "Callback",
                        "callback": self._ephemeral_callback,
                        "style": "success",
                    }
                ],
            ],
        )

    @loader.command(en_doc="Text form with a large link preview above the text")
    async def qolpreviewcmd(self, message: Message):
        """Text form with a large link preview above the text"""
        await self.inline.form(
            "Preview of https://telegram.org",
            message,
            link_preview="https://telegram.org",
            preview_size="large",
            preview_above=True,
        )

    @loader.command(en_doc="Rich list with an expandable blockquote")
    async def qolrichcmd(self, message: Message):
        """Rich list with an expandable blockquote"""
        await self.inline.list(
            message,
            [
                "<b>Page 1</b>\n" + utils.expandable("Hidden detail on the first page"),
                "<b>Page 2</b>\nSecond page, still rich.",
            ],
            rich=True,
        )

    @loader.command(en_doc="Stream a draft into your bot PM, then send it")
    async def qolstreamcmd(self, message: Message):
        """Stream a draft into your bot PM, then send it"""
        async with self.inline.stream(self.tg_id) as draft:
            await draft.update("QoL demo: working…")
            await asyncio.sleep(0.8)
            await draft.update("QoL demo: the draft is now a message")
        await utils.answer(message, "Streamed into your bot PM.")

    @loader.command(en_doc="Protected bot-PM message with a message effect")
    async def qolprotectcmd(self, message: Message):
        """Protected bot-PM message with a message effect"""
        await self.inline.bot.send_message(
            self.tg_id,
            "Protected bot PM. Forwarding is off; the effect is private-chat only.",
            protect_content=True,
            message_effect_id=_EFFECT_ID,
        )
        await utils.answer(message, "Sent a protected message to your bot PM.")
