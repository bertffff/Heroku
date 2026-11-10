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

import asyncio
import contextlib
import functools
import io
import itertools
import logging
import os
import re
import typing
from collections.abc import Callable
from copy import deepcopy
from urllib.parse import urlparse

from herokutl.errors.rpcbaseerrors import RPCError
from herokutl.errors.rpcerrorlist import (
    FloodWaitError,
    MediaPrevInvalidError,
    MessageNotModifiedError,
)
from herokutl.tl.types import InputMediaWebPage

from .. import utils
from ..types import HerokuReplyMarkup
from .tl import INLINE_DISABLED_DATA, DraftStream, make_button
from .types import InlineCall, InlineUnit

if typing.TYPE_CHECKING:
    from ..inline.core import InlineManager

logger = logging.getLogger(__name__)

VALID_BUTTON_STYLES = {"danger", "primary", "success"}
TG_EMOJI_RE = re.compile(
    r"<tg-emoji\b[^>]*\bemoji-id\s*=\s*['\"]?\d+['\"]?[^>]*>(.*?)</tg-emoji>",
    flags=re.IGNORECASE | re.DOTALL,
)


class Utils(InlineUnit):
    def _has_premium_emoji(self, text: typing.Any) -> bool:
        return isinstance(text, str) and bool(TG_EMOJI_RE.search(text))

    def _needs_premium_emoji_pre_edit(self, text: typing.Any) -> bool:
        return self._has_premium_emoji(text) and bool(
            getattr(getattr(self._client, "heroku_me", None), "premium", False)
        )

    def _get_button_style(self, button: dict) -> str | None:
        """Extract and validate button style from button dict"""
        style = button.get("style")
        if style and style in VALID_BUTTON_STYLES:
            return style
        return None

    def _get_button_emoji_id(self, button: dict) -> str | None:
        """Extract button custom emoji ID (for premium emoji support)"""

        emoji_id = button.get("emoji_id")

        if emoji_id:
            return str(emoji_id).strip()
        return None

    def _ensure_inline_disabled_noop(self: "InlineManager"):
        """Register the silent callback used when a disabled button cannot be sent."""
        data = INLINE_DISABLED_DATA.decode()
        if data in self._custom_map:
            return
        self._custom_map[data] = {
            "handler": self._disabled_inline_button,
            "always_allow": [],
            "args": [],
            "kwargs": {},
            "force_me": False,
            "disable_security": True,
        }

    async def _disabled_inline_button(self: "InlineManager", call: InlineCall):
        """Answer a disabled inline button with an empty toast. No user callback runs."""
        try:
            await call.answer()
        except Exception:
            logger.debug(
                "Silent answer for an emulated disabled button failed", exc_info=True
            )

    def _generate_markup(
        self: "InlineManager",
        markup_obj: HerokuReplyMarkup | str | None,
        *,
        inline_safe: bool = False,
    ) -> list[list[typing.Any]] | None:
        """Generate markup for form or list of `dict`s.

        ``inline_safe`` rewrites types ``messages.setInlineBotResults`` rejects:
        web apps become URL buttons (same colour and icon) and disabled buttons
        become a silent callback. Direct bot messages keep the original types.
        """
        if not markup_obj:
            return None

        if hasattr(markup_obj, "SUBCLASS_OF_ID"):
            return markup_obj

        markup = []

        map_ = (
            self._units[markup_obj]["buttons"]
            if isinstance(markup_obj, str)
            else markup_obj
        )

        map_ = self._normalize_markup(map_)

        setup_callbacks = False

        for row in map_:
            for button in row:
                if not isinstance(button, dict):
                    logger.error(
                        "Button %s is not a `dict`, but `%s` in %s",
                        button,
                        type(button),
                        map_,
                    )
                    return None

                if button.get("disabled"):
                    continue

                if "callback" not in button:
                    if button.get("action") == "close":
                        button["callback"] = self._close_unit_handler

                    if button.get("action") == "unload":
                        button["callback"] = self._unload_unit_handler

                    if button.get("action") == "answer":
                        if not button.get("message"):
                            logger.error(
                                "Button %s has no `message` to answer with", button
                            )
                            return None

                        if button.get("ephemeral"):
                            button["callback"] = functools.partial(
                                self._answer_ephemeral_unit_handler,
                                text=button["message"],
                            )
                        else:
                            button["callback"] = functools.partial(
                                self._answer_unit_handler,
                                show_alert=button.get("show_alert", False),
                                text=button["message"],
                            )

                if "callback" in button and "_callback_data" not in button:
                    button["_callback_data"] = utils.rand(30)
                    setup_callbacks = True

                if "input" in button and "_switch_query" not in button:
                    button["_switch_query"] = utils.rand(10)

        for row in map_:
            line = []
            for button in row:
                try:
                    btn_kwargs = {"text": str(button["text"])}

                    if style := self._get_button_style(button):
                        btn_kwargs["style"] = style

                    if emoji_id := self._get_button_emoji_id(button):
                        btn_kwargs["icon"] = int(emoji_id)

                    match True:
                        case _ if button.get("disabled"):
                            if inline_safe:
                                self._ensure_inline_disabled_noop()
                                btn_kwargs["data"] = INLINE_DISABLED_DATA.decode()
                                logger.debug(
                                    "Disabled buttons are not sent in inline results; "
                                    "using a silent callback"
                                )
                            else:
                                btn_kwargs["disabled"] = True

                        case _ if "url" in button:
                            if not utils.check_url(button["url"]):
                                logger.warning(
                                    "Button have not been added to form, "
                                    "because its url is invalid"
                                )
                                continue
                            btn_kwargs["url"] = button["url"]

                        case _ if "callback" in button:
                            btn_kwargs["data"] = button["_callback_data"]

                            if setup_callbacks:
                                self._custom_map[button["_callback_data"]] = {
                                    "handler": button["callback"],
                                    "always_allow": button.get("always_allow", [])
                                    or [],
                                    "args": button.get("args", {}),
                                    "kwargs": button.get("kwargs", {}),
                                    "force_me": button.get("force_me", False),
                                    "disable_security": button.get(
                                        "disable_security", False
                                    ),
                                }

                        case _ if "input" in button:
                            btn_kwargs["switch_inline_query_current_chat"] = (
                                button["_switch_query"] + " "
                            )

                        case _ if "data" in button:
                            btn_kwargs["data"] = button["data"]

                        case _ if "web_app" in button:
                            if inline_safe:
                                app = button["web_app"]
                                app_url = app if isinstance(app, str) else app.get("url")
                                if not app_url or not utils.check_url(app_url):
                                    logger.debug(
                                        "Skipping inline web_app button with an invalid url"
                                    )
                                    continue
                                # ButtonTypeSimpleWebView is a reply-keyboard type.
                                # Inline results have no equivalent, so this is a URL.
                                logger.debug(
                                    "web_app is not valid in inline results; using a URL button"
                                )
                                btn_kwargs["url"] = app_url
                            else:
                                btn_kwargs["web_app"] = button["web_app"]

                        case _ if "copy" in button:
                            btn_kwargs["copy_text"] = button["copy"]

                        case _ if "switch_inline_query_current_chat" in button:
                            btn_kwargs["switch_inline_query_current_chat"] = button[
                                "switch_inline_query_current_chat"
                            ]

                        case _ if "switch_inline_query" in button:
                            btn_kwargs["switch_inline_query"] = button[
                                "switch_inline_query"
                            ]

                        case _:
                            logger.warning(
                                (
                                    "Button have not been added to "
                                    "form, because it is not structured "
                                    "properly. %s"
                                ),
                                button,
                            )
                            continue

                    line.append(make_button(**btn_kwargs))

                except KeyError:
                    logger.exception(
                        "Error while forming markup! Probably, you "
                        "passed wrong type combination for button. "
                        "Contact developer of module."
                    )
                    return None
                except Exception as e:
                    if button.get("disabled"):
                        logger.debug(
                            "Disabled button is unsupported; using a placeholder: %s",
                            e,
                        )
                        try:
                            line.append(
                                make_button(text=str(button.get("text", "­")), data="­")
                            )
                            continue
                        except Exception:
                            logger.exception(
                                "Placeholder for a disabled button failed"
                            )
                            return None

                    logger.exception(f"Unexpected error creating button: {e}")
                    return None

            markup.append(line)

        return markup

    generate_markup = _generate_markup

    async def _close_unit_handler(self: "InlineManager", call: InlineCall):
        deleted = await self._delete_unit_message(call, unit_id=call.unit_id)
        try:
            await call.answer(
                "" if deleted else "Error occurred", show_alert=not deleted
            )
        except Exception:
            pass
        return deleted

    async def _unload_unit_handler(self: "InlineManager", call: InlineCall):
        await call.unload()

    async def _answer_unit_handler(
        self: "InlineManager", call: InlineCall, text: str, show_alert: bool
    ):
        await call.answer(text, show_alert=show_alert)

    async def _answer_ephemeral_unit_handler(
        self: "InlineManager", call: InlineCall, text: str
    ):
        """``{"action": "answer", "ephemeral": True}``. Same security path as other callbacks."""
        await call.answer_ephemeral(text)

    def _reverse_method_lookup(
        self: "InlineManager", needle: Callable, /
    ) -> str | None:
        return next(
            (
                name
                for name, method in itertools.chain(
                    self._allmodules.inline_handlers.items(),
                    self._allmodules.callback_handlers.items(),
                )
                if method == needle
            ),
            None,
        )

    async def check_inline_security(
        self: "InlineManager", *, func: typing.Callable, user: int
    ) -> bool:
        """Checks if user with id `user` is allowed to run function `func`"""
        return await self._client.dispatcher.security.check(
            message=None,
            func=func,
            user_id=user,
            inline_cmd=self._reverse_method_lookup(func),
        )

    def _find_caller_sec_map(
        self: "InlineManager",
    ) -> typing.Callable[[], int] | None:
        try:
            caller = utils.find_caller()
            if not caller:
                return None

            logger.debug("Found caller: %s", caller)

            return lambda: self._client.dispatcher.security.get_flags(
                getattr(caller, "__self__", caller),
            )
        except Exception:
            logger.debug("Can't parse security mask in form", exc_info=True)

        return None

    def _normalize_markup(
        self: "InlineManager", reply_markup: HerokuReplyMarkup
    ) -> list[list[dict[str, typing.Any]]]:
        if isinstance(reply_markup, dict):
            return [[reply_markup]]

        if isinstance(reply_markup, list) and any(
            isinstance(i, dict) for i in reply_markup
        ):
            return [reply_markup]

        return reply_markup

    def sanitise_text(self: "InlineManager", text: str) -> str:
        return re.sub(r"</?emoji.*?>", "", text)

    async def _edit_unit(
        self: "InlineManager",
        text: str | None = None,
        reply_markup: HerokuReplyMarkup | None = None,
        *,
        photo: str | None = None,
        file: str | None = None,
        video: str | None = None,
        audio: dict | str | None = None,
        gif: str | None = None,
        mime_type: str | None = None,
        force_me: bool | None = None,
        disable_security: bool | None = None,
        always_allow: list[int] | None = None,
        disable_web_page_preview: bool = True,
        query: typing.Any | None = None,
        unit_id: str | None = None,
        inline_message_id: str | None = None,
        chat_id: int | None = None,
        message_id: int | None = None,
        link_preview: str | bool | None = None,
        preview_size: str | None = None,
        preview_above: bool | None = None,
        invert_media: bool | None = None,
    ) -> bool:
        """
        Edits unit message
        :param text: Text of message
        :param reply_markup: Inline keyboard
        :param photo: Url to a valid photo to attach to message
        :param file: Url to a valid file to attach to message
        :param video: Url to a valid video to attach to message
        :param audio: Url to a valid audio to attach to message
        :param gif: Url to a valid gif to attach to message
        :param mime_type: Mime type of file
        :param force_me: Allow only userbot owner to interact with buttons
        :param disable_security: Disable security check for buttons
        :param always_allow: List of user ids, which will always be allowed
        :param disable_web_page_preview: Disable web page preview
        :param link_preview: ``False``/``None`` keeps the default (no preview unless
            ``disable_web_page_preview`` is false). ``True`` lets Telegram pick a
            preview from the text. A URL builds an ``InputMediaWebPage``.
        :param preview_size: ``"large"`` or ``"small"`` webpage media
        :param preview_above: Show the link preview above the text.
            ``None`` keeps the value stored on the unit.
        :param invert_media: Caption above media, when the edit carries media
        :param query: Callback query
        :return: Status of edit
        """
        reply_markup = self._validate_markup(reply_markup) or []

        if text is not None and not isinstance(text, str):
            logger.error(
                "Invalid type for `text`. Expected `str`, got `%s`", type(text)
            )
            return False

        if file and not mime_type:
            logger.error(
                "You must pass `mime_type` along with `file` field\n"
                "It may be either 'application/zip' or 'application/pdf'"
            )
            return False

        if isinstance(audio, str):
            audio = {"url": audio}

        if isinstance(text, str):
            text = self.sanitise_text(text)

        media_params = [
            photo is None,
            gif is None,
            file is None,
            video is None,
            audio is None,
        ]

        if media_params.count(False) > 1:
            logger.error("You passed two or more exclusive parameters simultaneously")
            return False

        pending_unit_update = {}

        if unit_id is not None and unit_id in self._units:
            unit = self._units[unit_id]

            pending_unit_update["buttons"] = reply_markup
            if text is not None:
                pending_unit_update["text"] = text

            if isinstance(force_me, bool):
                pending_unit_update["force_me"] = force_me

            if isinstance(disable_security, bool):
                pending_unit_update["disable_security"] = disable_security

            if isinstance(always_allow, list):
                pending_unit_update["always_allow"] = always_allow
        else:
            unit = {}

        def commit_unit_update():
            if unit_id is not None and unit_id in self._units:
                self._units[unit_id].update(pending_unit_update)

        if unit:
            chat_id = chat_id or unit.get("chat")
            message_id = message_id or unit.get("message_id")

        inline_message_id = (
            inline_message_id
            or unit.get("inline_message_id", False)
            or getattr(query, "inline_message_id", None)
        )
        (
            link_preview,
            preview_size,
            preview_above,
            invert_media,
        ) = self._inherit_unit_preview(
            unit,
            link_preview=link_preview,
            preview_size=preview_size,
            preview_above=preview_above,
            invert_media=invert_media,
        )
        inline_safe = bool(inline_message_id)

        def markup_for(source):
            return self.generate_markup(source, inline_safe=inline_safe)

        if not chat_id and not message_id and not inline_message_id:
            logger.warning(
                "Attempted to edit message with no `inline_message_id`. "
                "Possible reasons:\n"
                "- Form was sent without buttons and due to "
                "the limits of Telegram API can't be edited\n"
                "- There is an in-userbot error, which you should report"
            )
            return False

        try:
            path = urlparse(photo).path
            ext = os.path.splitext(path)[1]
        except Exception:
            ext = None

        if photo is not None and ext in {".gif", ".mp4"}:
            gif = deepcopy(photo)
            photo = None

        media = next(
            (media for media in [photo, file, video, audio, gif] if media), None
        )
        if isinstance(media, dict):
            media = media["url"]

        if isinstance(media, bytes):
            media = io.BytesIO(media)
            media.name = "upload.mp4"

        if isinstance(media, io.BytesIO):
            media.name = getattr(media, "name", "upload.mp4")

        kind = (
            "file"
            if file
            else (
                "photo"
                if photo
                else "audio" if audio else "video" if video else "gif" if gif else None
            )
        )

        if media is None and text is None and reply_markup:
            try:
                await self._bot_client.edit_message(
                    inline_message_id or chat_id,
                    (unit.get("text") or "") if inline_message_id else message_id,
                    buttons=markup_for(reply_markup),
                )
            except Exception:
                return False

            commit_unit_update()
            return True

        if media is None and text is None:
            logger.error("You must pass either `text` or `media` or `reply_markup`")
            return False

        if media is None:
            show_preview, webpage, caption_above = self._preview_edit_options(
                text,
                disable_web_page_preview=disable_web_page_preview,
                link_preview=link_preview,
                preview_size=preview_size,
                preview_above=preview_above,
                invert_media=invert_media,
            )
            buttons = markup_for(
                reply_markup
                if isinstance(reply_markup, list)
                else unit.get("buttons", [])
            )
            preview_requested = (
                webpage is not None
                or caption_above
                or link_preview not in (None, False)
                or bool(preview_size)
            )

            async def edit_text(target, message_ref, *, use_preview: bool):
                edit_kwargs = {
                    "parse_mode": "HTML",
                    "link_preview": (
                        show_preview if use_preview else not disable_web_page_preview
                    ),
                    "buttons": buttons,
                }
                if use_preview and webpage is not None:
                    edit_kwargs["file"] = webpage
                if use_preview and caption_above:
                    edit_kwargs["invert_media"] = True
                await self._bot_client.edit_message(
                    target,
                    message_ref,
                    text,
                    **edit_kwargs,
                )

            try:
                await edit_text(
                    inline_message_id or chat_id,
                    None if inline_message_id else message_id,
                    use_preview=True,
                )
            except MessageNotModifiedError:
                commit_unit_update()
                return True
            except FloodWaitError as e:
                logger.info("Sleeping %ss on Telethon FloodWait...", e.seconds)
                await asyncio.sleep(e.seconds)
                return await self._edit_unit(**utils.get_kwargs())
            except (RPCError, TypeError) as e:
                if isinstance(e, TypeError) and not preview_requested:
                    raise
                if preview_requested:
                    logger.debug(
                        "Link preview edit is unsupported (%s); "
                        "falling back to a plain text edit",
                        e,
                    )
                    try:
                        await edit_text(
                            inline_message_id or chat_id,
                            None if inline_message_id else message_id,
                            use_preview=False,
                        )
                    except MessageNotModifiedError:
                        commit_unit_update()
                        return True
                    except FloodWaitError as flood:
                        logger.info(
                            "Sleeping %ss on Telethon FloodWait...", flood.seconds
                        )
                        await asyncio.sleep(flood.seconds)
                        return await self._edit_unit(**utils.get_kwargs())
                    except (RPCError, TypeError) as retry_error:
                        e = retry_error
                    else:
                        commit_unit_update()
                        return True

                if not isinstance(e, RPCError):
                    logger.debug("Text edit failed", exc_info=True)
                    return False

                logger.warning(
                    "RPCError while editing inline message via inline_message_id: %s. "
                    "Attempting fallback via chat_id + message_id...",
                    e,
                )
                if inline_message_id and chat_id and message_id:
                    with contextlib.suppress(Exception):
                        await edit_text(
                            chat_id,
                            message_id,
                            use_preview=False,
                        )
                        commit_unit_update()
                        return True
                if query:
                    with contextlib.suppress(Exception):
                        await query.answer()
                return False
            else:
                commit_unit_update()
                return True

        media_buttons = markup_for(
            reply_markup
            if isinstance(reply_markup, list)
            else unit.get("buttons", [])
        )
        use_invert = bool(invert_media)

        async def edit_media(with_invert: bool):
            edit_kwargs = {
                "parse_mode": "HTML",
                "file": media,
                "force_document": kind == "file",
                "buttons": media_buttons,
            }
            if with_invert:
                edit_kwargs["invert_media"] = True
            await self._bot_client.edit_message(
                inline_message_id or chat_id,
                None if inline_message_id else message_id,
                text,
                **edit_kwargs,
            )

        try:
            await edit_media(use_invert)
        except FloodWaitError as e:
            logger.info("Sleeping %ss on Telethon FloodWait...", e.seconds)
            await asyncio.sleep(e.seconds)
            return await self._edit_unit(**utils.get_kwargs())
        except (RPCError, MediaPrevInvalidError, TypeError) as exc:
            if isinstance(exc, TypeError) and not use_invert:
                raise
            if use_invert and not isinstance(exc, MediaPrevInvalidError):
                logger.debug(
                    "invert_media edit was rejected; retrying without it",
                    exc_info=True,
                )
                try:
                    await edit_media(False)
                except FloodWaitError as e:
                    logger.info("Sleeping %ss on Telethon FloodWait...", e.seconds)
                    await asyncio.sleep(e.seconds)
                    return await self._edit_unit(**utils.get_kwargs())
                except (RPCError, MediaPrevInvalidError, TypeError):
                    with contextlib.suppress(Exception):
                        await query.answer(
                            "I should have edited some message, but it is deleted :("
                        )
                    return False
                else:
                    commit_unit_update()
                    return True

            if isinstance(exc, TypeError):
                logger.debug("Media edit failed", exc_info=True)
                return False

            with contextlib.suppress(Exception):
                await query.answer(
                    "I should have edited some message, but it is deleted :("
                )
            return False
        else:
            commit_unit_update()
            return True

    def _preview_edit_options(
        self: "InlineManager",
        text: str | None,
        *,
        disable_web_page_preview: bool,
        link_preview: str | bool | None,
        preview_size: str | None,
        preview_above: bool | None,
        invert_media: bool | None,
    ) -> tuple[bool, InputMediaWebPage | None, bool]:
        """Resolve link-preview kwargs into edit_message arguments.

        Defaults match the historical edit: preview off unless
        ``disable_web_page_preview`` is false.
        """
        if preview_above is None:
            preview_above = False
        if preview_size not in (None, "large", "small"):
            logger.debug("Ignoring invalid preview_size %r", preview_size)
            preview_size = None

        show = not disable_web_page_preview
        url = None
        if link_preview is False:
            show = False
        elif link_preview is True:
            show = True
        elif isinstance(link_preview, str) and link_preview.strip():
            show = True
            url = link_preview.strip()

        if preview_size or preview_above:
            show = True

        wants_webpage = bool(preview_size or preview_above or isinstance(link_preview, str))
        if url is None and show and wants_webpage:
            found = utils.extract_urls(text or "")
            url = found[0] if found else None

        webpage = None
        if url and wants_webpage:
            webpage = InputMediaWebPage(
                url=url,
                force_large_media=True if preview_size == "large" else None,
                force_small_media=True if preview_size == "small" else None,
                # Same rule as the inline result: a forced size is not optional,
                # or the edit replaces a large card with the compact thumbnail.
                optional=None if preview_size else True,
            )
            show = True

        invert = bool(invert_media) or bool(preview_above)
        return show, webpage, invert

    def _inherit_unit_preview(
        self: "InlineManager",
        unit: dict,
        *,
        link_preview: str | bool | None,
        preview_size: str | None,
        preview_above: bool | None,
        invert_media: bool | None,
    ) -> tuple[str | bool | None, str | None, bool, bool | None]:
        """Keep a form's link preview and caption placement on later edits.

        Omitted kwargs reuse the values stored when the form was created.
        An explicit ``False`` still turns the option off. Webpage options are
        not applied to a unit that already has its own photo, video, or file.
        """
        textual = not any(
            unit.get(key) for key in ("photo", "gif", "video", "file", "audio", "location")
        )
        if textual:
            if link_preview is None and "link_preview" in unit:
                link_preview = unit["link_preview"]
            if preview_size is None and unit.get("preview_size"):
                preview_size = unit["preview_size"]
            if preview_above is None and unit.get("preview_above"):
                preview_above = True
        if invert_media is None and unit.get("invert_media"):
            invert_media = True
        if preview_above is None:
            preview_above = False
        return link_preview, preview_size, preview_above, invert_media

    def stream(
        self: "InlineManager",
        chat_id,
        *,
        min_interval: float = 0.7,
        can_stop: bool | None = None,
        keep_on_stop: bool | None = None,
        message_thread_id: int | None = None,
        reply_markup=None,
        protect_content: bool | None = None,
        message_effect_id: int | None = None,
    ) -> DraftStream:
        """Throttled draft in a private chat, finalized with ``send_message``.

        Example::

            async with self.inline.stream(chat_id) as draft:
                await draft.update("Working…")
                await draft.update("Done")
        """
        return DraftStream(
            self.bot,
            chat_id,
            min_interval=min_interval,
            can_stop=can_stop,
            keep_on_stop=keep_on_stop,
            message_thread_id=message_thread_id,
            reply_markup=reply_markup,
            protect_content=protect_content,
            message_effect_id=message_effect_id,
        )

    async def _delete_unit_message(
        self: "InlineManager",
        call: typing.Any | None = None,
        unit_id: str | None = None,
        chat_id: int | None = None,
        message_id: int | None = None,
    ) -> bool:
        """Params `self`, `unit_id` are for internal use only, do not try to pass them"""
        if not isinstance(call, InlineCall):
            chat_id = chat_id or getattr(
                getattr(getattr(call, "message", None), "chat", None), "id", None
            )
            message_id = message_id or getattr(
                getattr(call, "message", None), "id", None
            )
            if chat_id and message_id:
                try:
                    await self.bot.delete_message(chat_id, message_id)
                except Exception:
                    logger.debug(
                        "Failed to delete bot message %s", unit_id, exc_info=True
                    )
                    return False

                return True

        if not unit_id and getattr(call, "unit_id", None):
            unit_id = call.unit_id

        unit = self._units.get(unit_id) or {}
        if not (unit.get("chat") and unit.get("message_id")):
            return False

        try:
            await self._client.delete_messages(unit["chat"], unit["message_id"])
        except Exception:
            logger.debug("Failed to delete unit message %s", unit_id, exc_info=True)
            return False

        return True

    async def _unload_unit(self: "InlineManager", unit_id: str) -> bool:
        """Params `self`, `unit_id` are for internal use only, do not try to pass them"""
        try:
            if "on_unload" in self._units[unit_id] and callable(
                self._units[unit_id]["on_unload"]
            ):
                self._units[unit_id]["on_unload"]()

            if unit_id in self._units:
                del self._units[unit_id]
            else:
                return False
        except Exception:
            return False

        return True

    def build_pagination(
        self: "InlineManager",
        callback: typing.Callable[[int], typing.Awaitable[typing.Any]],
        total_pages: int,
        unit_id: str | None = None,
        current_page: int | None = None,
        disabled_current: bool | None = None,
    ) -> list[list[dict[str, typing.Any]]]:
        # Based on https://github.com/pystorage/pykeyboard/blob/master/pykeyboard/inline_pagination_keyboard.py#L4
        if current_page is None:
            current_page = self._units[unit_id]["current_index"] + 1

        if disabled_current is None:
            disabled_current = False
            getter = getattr(getattr(self, "_db", None), "get", None)
            if callable(getter):
                try:
                    config = getter("InlineStuff", "__config__", {}) or {}
                    disabled_current = bool(
                        config.get("disabled_current_page", False)
                    )
                except Exception:
                    logger.debug(
                        "Can't read InlineStuff disabled_current_page",
                        exc_info=True,
                    )
                    disabled_current = False

        def button(number: int, text, *, current: bool = False):
            # The current page keeps its callback unless disabled_current is set,
            # so modules that read the page argument keep working by default.
            if current and disabled_current:
                return {"text": text, "disabled": True}
            return {
                "text": text,
                "args": (number - 1,),
                "callback": callback,
            }

        if total_pages <= 5:
            return [
                [
                    button(
                        number,
                        f"· {number} ·" if number == current_page else number,
                        current=number == current_page,
                    )
                    for number in range(1, total_pages + 1)
                ]
            ]

        if current_page <= 3:
            def early(number: int):
                if number == current_page:
                    return button(number, f"· {number} ·", current=True)
                if number == 4:
                    return button(number, f"{number} ›")
                if number == 5:
                    return button(total_pages, f"{total_pages} »")
                return button(number, number)

            return [[early(number) for number in range(1, 6)]]

        if current_page > total_pages - 3:
            return [
                [
                    button(1, "« 1"),
                    button(total_pages - 3, f"‹ {total_pages - 3}"),
                    *[
                        button(
                            number,
                            f"· {number} ·" if number == current_page else number,
                            current=number == current_page,
                        )
                        for number in range(total_pages - 2, total_pages + 1)
                    ],
                ]
            ]

        return [
            [
                button(1, "« 1"),
                button(current_page - 1, f"‹ {current_page - 1}"),
                button(current_page, f"· {current_page} ·", current=True),
                button(current_page + 1, f"{current_page + 1} ›"),
                button(total_pages, f"{total_pages} »"),
            ]
        ]

    def _validate_markup(
        self: "InlineManager",
        buttons: HerokuReplyMarkup | None,
    ) -> list[list[dict[str, typing.Any]]]:
        if buttons is None:
            buttons = []

        if not isinstance(buttons, (list, dict)):
            logger.error(
                "Reply markup ommited because passed type is not valid (%s)",
                type(buttons),
            )
            return None

        buttons = self._normalize_markup(buttons)

        if not all(all(isinstance(button, dict) for button in row) for row in buttons):
            logger.error(
                "Reply markup ommited because passed invalid type for one of the"
                " buttons"
            )
            return None

        if not all(
            all(
                "url" in button
                or "callback" in button
                or "input" in button
                or "data" in button
                or "action" in button
                or "copy" in button
                or "web_app" in button
                or "switch_inline_query_current_chat" in button
                or "switch_inline_query" in button
                or button.get("disabled")
                for button in row
            )
            for row in buttons
        ):
            logger.error(
                "Invalid button specified. "
                "Button must contain one of the following fields:\n"
                "  - `url`\n"
                "  - `callback`\n"
                "  - `input`\n"
                "  - `data`\n"
                "  - `action`\n"
                "  - `copy`\n"
                "  - `web_app`\n"
                "  - `switch_inline_query_current_chat`\n"
                "  - `switch_inline_query`\n"
                "  - `disabled`"
            )
            return None

        return buttons
