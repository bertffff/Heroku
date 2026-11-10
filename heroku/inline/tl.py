import io
import logging
import os
import time
import typing

from herokutl import Button
from herokutl.errors.rpcbaseerrors import RPCError
from herokutl.extensions import html as html_parser
from herokutl import utils as tl_utils
from herokutl.tl import types
from herokutl.tl.functions.messages import (
    EditInlineBotMessageRequest,
    EditMessageRequest,
    SendMediaRequest,
    SendMessageRequest,
    SetInlineBotResultsRequest,
    SetTypingRequest,
)
from herokutl.tl.types import (
    DocumentAttributeAudio,
    InputReplyToMessage,
    InputRichMessageHTML,
    InputRichMessageMarkdown,
)
from herokutl.tl import TLObject

from .._internal import normalize_rich_html

logger = logging.getLogger(__name__)


def _button_style(style: str | None = None, icon: int | None = None):
    """Same colour/icon mapping as ``Button.inline``. ``None`` when both are unset."""
    if style is None and icon is None:
        return None
    return Button._get_style(style, icon)


def apply_invert_media(result, enabled: bool):
    """Set caption-above-media on an inline result when that TL message has the flag."""
    if not enabled or result is None:
        return result

    message = getattr(result, "send_message", None)
    if message is None or not hasattr(message, "invert_media"):
        return result

    message.invert_media = True
    return result


class TelethonBot:
    def __init__(self, client):
        self.client = client

    async def __call__(self, value):
        if isinstance(value, TLObject):
            return await self.client(value)
        if hasattr(value, "__await__"):
            return await value
        return value

    def __getattr__(self, item: str):
        return getattr(self.client, item)

    @staticmethod
    def _normalise_file(file):
        if isinstance(file, bytes):
            media = io.BytesIO(file)
            media.name = "file"
            return media

        if hasattr(file, "data"):
            media = io.BytesIO(file.data)
            media.name = getattr(file, "filename", "file")
            return media

        if hasattr(file, "seek"):
            try:
                file.seek(0)
            except Exception:
                pass

        return file

    @staticmethod
    def _thread_kwargs(message_thread_id: int | None) -> dict:
        return {"reply_to": message_thread_id} if message_thread_id else {}

    @staticmethod
    def _with_message_id_alias(message):
        if (
            message is not None
            and not hasattr(message, "message_id")
            and hasattr(message, "id")
        ):
            try:
                message.message_id = message.id
            except Exception:
                pass

        return message

    def _build_reply_markup(self, reply_markup):
        if reply_markup is None:
            return None
        if isinstance(
            reply_markup,
            (
                types.ReplyInlineMarkup,
                types.ReplyKeyboardMarkup,
                types.ReplyKeyboardHide,
                types.ReplyKeyboardForceReply,
            ),
        ):
            return reply_markup
        return self.client.build_reply_markup(reply_markup)

    @staticmethod
    def _peer_owner_id(peer) -> int:
        if isinstance(peer, types.PeerUser):
            return peer.user_id
        if isinstance(peer, types.PeerChannel):
            return peer.channel_id
        if isinstance(peer, types.PeerChat):
            return peer.chat_id
        raise TypeError(f"Unsupported inline peer type: {type(peer)!r}")

    @classmethod
    def _coerce_inline_message_id(cls, inline_message_id):
        if inline_message_id is None:
            return None

        if isinstance(
            inline_message_id,
            (types.InputBotInlineMessageID, types.InputBotInlineMessageID64),
        ):
            return inline_message_id

        if not isinstance(inline_message_id, str):
            raise TypeError(
                "inline_message_id must be str or InputBotInlineMessageID/64, "
                f"got {type(inline_message_id)!r}"
            )

        message_id, peer, dc_id, access_hash = tl_utils.resolve_inline_message_id(
            inline_message_id
        )

        if peer is None:
            raise ValueError(f"Invalid inline_message_id: {inline_message_id!r}")

        return types.InputBotInlineMessageID64(
            dc_id=dc_id,
            owner_id=cls._peer_owner_id(peer),
            id=message_id,
            access_hash=access_hash,
        )

    @staticmethod
    def _coerce_input_media(media):
        if media is None:
            return None

        if isinstance(
            media,
            (
                types.InputMediaDocument,
                types.InputMediaPhoto,
                types.InputMediaUploadedDocument,
                types.InputMediaUploadedPhoto,
                types.InputMediaWebPage,
                types.InputMediaEmpty,
            ),
        ):
            return media

        try:
            return tl_utils.get_input_media(media)
        except TypeError as e:
            raise TypeError(
                "For inline media edits pass a TL InputMedia object "
                "(InputMediaDocument, InputMediaPhoto, etc.), not raw bytes/path."
            ) from e

    async def get_me(self):
        return await self.client.get_me()

    async def send_message(
        self,
        chat_id,
        text: str = "",
        *,
        reply_markup=None,
        message_thread_id: int | None = None,
        disable_notification: bool | None = None,
        rich_message: str | None = None,
        protect_content: bool | None = None,
        message_effect_id: int | None = None,
        **kwargs,
    ):
        if protect_content is None:
            protect_content = kwargs.pop("protect_content", None)
        else:
            kwargs.pop("protect_content", None)
        if message_effect_id is None:
            message_effect_id = kwargs.pop("message_effect_id", None)
        else:
            kwargs.pop("message_effect_id", None)

        if rich_message is not None:
            return await self.send_rich_message(
                chat_id,
                rich_message,
                reply_markup=reply_markup,
                message_thread_id=message_thread_id,
                disable_notification=disable_notification,
                protect_content=protect_content,
                message_effect_id=message_effect_id,
            )

        silent = (
            disable_notification
            if disable_notification is not None
            else kwargs.get("disable_notification")
        )
        link_preview = not kwargs.get("disable_web_page_preview", False)

        async def _send(protected: bool, effect):
            return self._with_message_id_alias(
                await self.client.send_message(
                    chat_id,
                    text,
                    parse_mode="HTML",
                    buttons=reply_markup,
                    silent=silent,
                    link_preview=link_preview,
                    noforwards=bool(protected),
                    message_effect_id=effect,
                    **self._thread_kwargs(message_thread_id),
                )
            )

        try:
            return await _send(bool(protect_content), message_effect_id)
        except RPCError:
            if not protect_content and message_effect_id is None:
                raise
            logger.debug(
                "protect_content/message_effect_id rejected on send_message; "
                "resending without them",
                exc_info=True,
            )
            return await _send(False, None)

    @staticmethod
    def _rich_input(html=None, markdown=None, rich_message=None):
        if rich_message is not None:
            return rich_message
        if html is not None:
            return InputRichMessageHTML(html=normalize_rich_html(html))
        if markdown is not None:
            return InputRichMessageMarkdown(markdown=markdown)
        raise ValueError("One of html, markdown or rich_message is required")

    @staticmethod
    def _rich_fallback_text(html=None, markdown=None, rich_message=None):
        if html:
            text, _ = html_parser.parse(html)
            return text or " "
        if markdown:
            return str(markdown) or " "
        if rich_message is not None:
            rich_html = getattr(rich_message, "html", None)
            if rich_html:
                text, _ = html_parser.parse(rich_html)
                return text or " "
            rich_markdown = getattr(rich_message, "markdown", None)
            if rich_markdown:
                return str(rich_markdown)
            try:
                from ..utils.rich import rich_message_to_html

                text, _ = html_parser.parse(rich_message_to_html(rich_message))
                return text or " "
            except Exception:
                return " "
        return " "

    async def send_rich_message(
        self,
        chat_id,
        html: str | None = None,
        *,
        markdown: str | None = None,
        rich_message=None,
        reply_markup=None,
        message_thread_id: int | None = None,
        disable_notification: bool | None = None,
        protect_content: bool | None = None,
        message_effect_id: int | None = None,
    ):
        if html is not None and not isinstance(html, str):
            raise TypeError("html must be a str")

        entity = await self.client.get_input_entity(chat_id)
        rich_input = self._rich_input(html, markdown, rich_message)
        fallback = self._rich_fallback_text(html, markdown, rich_message)
        markup = self.client.build_reply_markup(reply_markup)
        reply_to = (
            InputReplyToMessage(message_thread_id)
            if message_thread_id is not None
            else None
        )

        async def _send(protected: bool, effect):
            request = SendMessageRequest(
                peer=entity,
                message=fallback,
                no_webpage=True,
                silent=disable_notification,
                reply_to=reply_to,
                reply_markup=markup,
                rich_message=rich_input,
                noforwards=True if protected else None,
                effect=effect,
            )
            result = await self.client(request)
            return self.client._get_response_message(request, result, entity)

        try:
            return await _send(bool(protect_content), message_effect_id)
        except RPCError:
            if not protect_content and message_effect_id is None:
                raise
            logger.debug(
                "protect_content/message_effect_id rejected on send_rich_message; "
                "resending without them",
                exc_info=True,
            )
            return await _send(False, None)

    async def edit_rich_message(
        self,
        html: str | None = None,
        *,
        markdown: str | None = None,
        rich_message=None,
        inline_message_id=None,
        chat_id=None,
        message_id=None,
        reply_markup=None,
    ):
        if html is not None and not isinstance(html, str):
            raise TypeError("html must be a str")

        markup = self._build_reply_markup(reply_markup)
        rich_input = self._rich_input(html, markdown, rich_message)
        fallback_text = self._rich_fallback_text(html, markdown, rich_message)
        if inline_message_id is not None:
            request = EditInlineBotMessageRequest(
                id=self._coerce_inline_message_id(inline_message_id),
                message=fallback_text,
                no_webpage=True,
                rich_message=rich_input,
                reply_markup=markup,
            )
            return await self.client(request)

        entity = await self.client.get_input_entity(chat_id)
        request = EditMessageRequest(
            peer=entity,
            id=message_id,
            message=fallback_text,
            no_webpage=True,
            rich_message=rich_input,
            reply_markup=markup,
        )
        return await self.client(request)

    @staticmethod
    def _rewind(file):
        if hasattr(file, "seek"):
            try:
                file.seek(0)
            except Exception:
                pass

    async def _send_protected_media(
        self,
        chat_id,
        file,
        *,
        caption: str | None = None,
        reply_markup=None,
        message_thread_id: int | None = None,
        force_document: bool = False,
        attributes=None,
        thumb=None,
        silent: bool | None = None,
        message_effect_id: int | None = None,
    ):
        """``send_file`` drops ``noforwards``. Protected media goes through raw sendMedia."""
        entity = await self.client.get_input_entity(chat_id)
        caption_text = caption or ""
        entities = None
        if caption:
            caption_text, entities = await self.client._parse_message_text(
                caption, "html"
            )

        self._rewind(file)
        _handle, media, _image = await self.client._file_to_media(
            file,
            force_document=force_document,
            attributes=attributes,
            thumb=thumb,
        )
        if media is None:
            raise TypeError("Cannot use this file as protected media")

        request = SendMediaRequest(
            peer=entity,
            media=media,
            message=caption_text or "",
            entities=entities,
            reply_markup=self._build_reply_markup(reply_markup),
            silent=silent,
            reply_to=(
                types.InputReplyToMessage(message_thread_id)
                if message_thread_id
                else None
            ),
            noforwards=True,
            effect=message_effect_id,
        )
        result = await self.client(request)
        return self._with_message_id_alias(
            self.client._get_response_message(request, result, entity)
        )

    async def _dispatch_file(
        self,
        chat_id,
        file,
        *,
        caption: str | None = None,
        reply_markup=None,
        message_thread_id: int | None = None,
        force_document: bool = False,
        attributes=None,
        thumb=None,
        silent: bool | None = None,
        protect_content: bool | None = None,
        message_effect_id: int | None = None,
        parse_html: bool = True,
    ):
        file = self._normalise_file(file)
        if thumb is not None:
            thumb = self._normalise_file(thumb)

        async def via_send_file(effect):
            self._rewind(file)
            self._rewind(thumb)
            send_kwargs = {
                "caption": caption,
                "force_document": force_document,
                "attributes": attributes,
                "thumb": thumb,
                "buttons": reply_markup,
                "silent": silent,
                "message_effect_id": effect,
                **self._thread_kwargs(message_thread_id),
            }
            if parse_html:
                send_kwargs["parse_mode"] = "HTML"
            return self._with_message_id_alias(
                await self.client.send_file(chat_id, file, **send_kwargs)
            )

        if protect_content:
            try:
                return await self._send_protected_media(
                    chat_id,
                    file,
                    caption=caption,
                    reply_markup=reply_markup,
                    message_thread_id=message_thread_id,
                    force_document=force_document,
                    attributes=attributes,
                    thumb=thumb,
                    silent=silent,
                    message_effect_id=message_effect_id,
                )
            except RPCError:
                logger.debug(
                    "protect_content is not available for this media send; "
                    "falling back to send_file",
                    exc_info=True,
                )

        try:
            return await via_send_file(message_effect_id)
        except RPCError:
            if message_effect_id is None:
                raise
            logger.debug(
                "message_effect_id was rejected; resending media without it",
                exc_info=True,
            )
            return await via_send_file(None)

    async def send_document(
        self,
        chat_id,
        document,
        *,
        caption: str | None = None,
        reply_markup=None,
        message_thread_id: int | None = None,
        protect_content: bool | None = None,
        message_effect_id: int | None = None,
        **kwargs,
    ):
        return await self._dispatch_file(
            chat_id,
            document,
            caption=caption,
            reply_markup=reply_markup,
            message_thread_id=message_thread_id,
            force_document=True,
            silent=kwargs.get("disable_notification"),
            protect_content=protect_content or kwargs.get("protect_content"),
            message_effect_id=(
                message_effect_id
                if message_effect_id is not None
                else kwargs.get("message_effect_id")
            ),
        )

    async def send_photo(
        self,
        chat_id,
        photo,
        *,
        caption: str | None = None,
        reply_markup=None,
        message_thread_id: int | None = None,
        protect_content: bool | None = None,
        message_effect_id: int | None = None,
        **kwargs,
    ):
        return await self._dispatch_file(
            chat_id,
            photo,
            caption=caption,
            reply_markup=reply_markup,
            message_thread_id=message_thread_id,
            silent=kwargs.get("disable_notification"),
            protect_content=protect_content or kwargs.get("protect_content"),
            message_effect_id=(
                message_effect_id
                if message_effect_id is not None
                else kwargs.get("message_effect_id")
            ),
        )

    async def send_audio(
        self,
        chat_id,
        audio,
        *,
        title: str | None = None,
        performer: str | None = None,
        duration: int | None = None,
        thumbnail=None,
        reply_markup=None,
        message_thread_id: int | None = None,
        protect_content: bool | None = None,
        message_effect_id: int | None = None,
        **kwargs,
    ):
        attributes = [
            DocumentAttributeAudio(
                duration=duration or 0,
                title=title,
                performer=performer,
            )
        ]
        return await self._dispatch_file(
            chat_id,
            audio,
            reply_markup=reply_markup,
            message_thread_id=message_thread_id,
            attributes=attributes,
            thumb=thumbnail,
            silent=kwargs.get("disable_notification"),
            protect_content=protect_content or kwargs.get("protect_content"),
            message_effect_id=(
                message_effect_id
                if message_effect_id is not None
                else kwargs.get("message_effect_id")
            ),
            parse_html=False,
        )

    async def _private_input_peer(self, chat_id):
        try:
            entity = await self.client.get_input_entity(chat_id)
        except Exception:
            logger.debug("Draft peer lookup failed for %r", chat_id, exc_info=True)
            return None

        if isinstance(entity, (types.InputPeerUser, types.InputPeerSelf)):
            return entity

        logger.debug(
            "Message drafts are limited to private chats (got %s)",
            type(entity).__name__,
        )
        return None

    async def send_message_draft(
        self,
        chat_id,
        text: str = "",
        *,
        draft_id: int,
        entities=None,
        can_stop: bool | None = None,
        keep_on_stop: bool | None = None,
        message_thread_id: int | None = None,
    ):
        """Stream a temporary draft into a private chat (bot PM).

        Empty text is a valid "Thinking…" draft. Unsupported servers fall back
        to a plain typing action. Returns ``False`` outside private chats.
        """
        entity = await self._private_input_peer(chat_id)
        if entity is None:
            return False

        if entities is None:
            try:
                text, entities = await self.client._parse_message_text(text or "", "html")
            except Exception:
                logger.debug("Draft HTML parse failed", exc_info=True)
                entities = []

        action = types.SendMessageTextDraftAction(
            text=types.TextWithEntities(text=text or "", entities=list(entities or [])),
            random_id=draft_id,
            can_stop=can_stop,
            keep_on_stop=keep_on_stop,
        )
        try:
            return await self.client(
                SetTypingRequest(
                    peer=entity,
                    action=action,
                    top_msg_id=message_thread_id,
                )
            )
        except RPCError:
            logger.debug(
                "Text draft is unsupported; falling back to a typing action",
                exc_info=True,
            )
            try:
                return await self.client(
                    SetTypingRequest(
                        peer=entity,
                        action=types.SendMessageTypingAction(),
                        top_msg_id=message_thread_id,
                    )
                )
            except RPCError:
                logger.debug("Typing fallback failed", exc_info=True)
                return False

    async def stop_message_draft(
        self,
        chat_id,
        draft_id: int,
        *,
        message_thread_id: int | None = None,
    ):
        entity = await self._private_input_peer(chat_id)
        if entity is None:
            return False

        try:
            return await self.client(
                SetTypingRequest(
                    peer=entity,
                    action=types.SendMessageStopDraftAction(random_id=draft_id),
                    top_msg_id=message_thread_id,
                )
            )
        except RPCError:
            logger.debug("Stop-draft action failed", exc_info=True)
            return False

    async def delete_message(self, chat_id, message_id):
        return await self.client.delete_messages(chat_id, message_id)

    async def answer_inline_query(
        self,
        inline_query_id: int,
        results: list,
        *,
        cache_time: int = 0,
        is_personal: bool = False,
        next_offset: str | None = None,
        **kwargs,
    ):
        prepared = []
        for item in results:
            if hasattr(item, "__await__"):
                item = await item
            prepared.append(item)

        return await self.client(
            SetInlineBotResultsRequest(
                query_id=inline_query_id,
                results=prepared,
                cache_time=cache_time,
                private=is_personal,
                next_offset=next_offset or "",
                gallery=kwargs.get("gallery", False),
            )
        )

    async def edit_message_media(
        self,
        *,
        inline_message_id: typing.Any = None,
        chat_id: typing.Any = None,
        message_id: typing.Any = None,
        media=None,
        reply_markup: typing.Any = None,
        **kwargs,
    ):
        if inline_message_id is not None:
            inline_id = self._coerce_inline_message_id(inline_message_id)
            input_media = self._coerce_input_media(media)
            markup = self._build_reply_markup(reply_markup)
            return await self.client(
                EditInlineBotMessageRequest(
                    id=inline_id,
                    media=input_media,
                    reply_markup=markup,
                )
            )

        return await self.client.edit_message(
            chat_id,
            message_id,
            file=media,
            buttons=reply_markup,
        )

    async def edit_message_text(
        self,
        *,
        text: str,
        inline_message_id: typing.Any = None,
        chat_id: typing.Any = None,
        message_id: typing.Any = None,
        reply_markup: typing.Any = None,
        disable_web_page_preview: bool = True,
        **kwargs: typing.Any,
    ) -> typing.Any:
        markup = self._build_reply_markup(reply_markup)

        if inline_message_id is not None:
            inline_id = self._coerce_inline_message_id(inline_message_id)
            return await self.client.edit_message(
                inline_id,
                text,
                parse_mode="HTML",
                link_preview=not disable_web_page_preview,
                buttons=markup,
            )

        return await self.client.edit_message(
            chat_id,
            message_id,
            text,
            parse_mode="HTML",
            link_preview=not disable_web_page_preview,
            buttons=markup,
        )

    async def edit_message_reply_markup(
        self,
        *,
        inline_message_id: typing.Any = None,
        chat_id: typing.Any = None,
        message_id: typing.Any = None,
        reply_markup: typing.Any = None,
    ):
        markup = self._build_reply_markup(reply_markup)

        if inline_message_id is not None:
            inline_id = self._coerce_inline_message_id(inline_message_id)
            return await self.client(
                EditInlineBotMessageRequest(
                    id=inline_id,
                    reply_markup=markup,
                )
            )

        return await self.client.edit_message(
            chat_id,
            message_id,
            buttons=markup,
        )


def web_document(
    url: str | None,
    *,
    mime_type: str = "image/jpeg",
    width: int = 128,
    height: int = 128,
) -> types.InputWebDocument | None:
    if not url:
        return None

    return types.InputWebDocument(
        url=url,
        size=0,
        mime_type=mime_type,
        attributes=[
            types.DocumentAttributeImageSize(
                w=width,
                h=height,
            )
        ],
    )


def make_button(
    *,
    text: str,
    style: str | None = None,
    icon: str | None = None,
    url: str | None = None,
    data: str | bytes | None = None,
    switch_inline_query_current_chat: str | None = None,
    switch_inline_query: str | None = None,
    web_app: str | dict | None = None,
    copy_text: str | None = None,
    disabled: bool = False,
):
    style_obj = _button_style(style, icon)

    if disabled:
        try:
            return types.KeyboardInlineButton(
                text,
                types.InlineButtonTypeDisabled(),
                style=style_obj,
            )
        except Exception:
            logger.debug(
                "InlineButtonTypeDisabled is unavailable; using a placeholder button",
                exc_info=True,
            )
            return Button.inline(text, "­", style=style, icon=icon)

    if url is not None:
        return Button.url(text, url, style=style, icon=icon)

    if data is not None:
        return Button.inline(text, data, style=style, icon=icon)

    if switch_inline_query_current_chat is not None:
        return Button.switch_inline(
            text,
            switch_inline_query_current_chat,
            same_peer=True,
            style=style,
            icon=icon,
        )

    if switch_inline_query is not None:
        return Button.switch_inline(
            text,
            switch_inline_query,
            same_peer=False,
            style=style,
            icon=icon,
        )

    if web_app is not None:
        app_url = web_app if isinstance(web_app, str) else web_app["url"]
        return types.KeyboardInlineButton(
            text,
            types.InlineButtonTypeWebView(url=app_url),
            style=style_obj,
        )

    if copy_text is not None:
        return types.KeyboardInlineButton(
            text,
            types.InlineButtonTypeCopy(copy_text=copy_text),
            style=style_obj,
        )

    return Button.inline(text, text, style=style, icon=icon)


class DraftStream:
    """Throttled private-chat draft that ends as a real message.

    Drafts are a ~30 second preview. ``update`` is throttled (default 0.7s,
    4096 characters). On a clean exit the latest text is sent with
    ``send_message``. A non-private chat skips the draft and still sends the
    final message.
    """

    def __init__(
        self,
        bot: TelethonBot,
        chat_id,
        *,
        min_interval: float = 0.7,
        can_stop: bool | None = None,
        keep_on_stop: bool | None = None,
        message_thread_id: int | None = None,
        reply_markup=None,
        protect_content: bool | None = None,
        message_effect_id: int | None = None,
    ):
        self.bot = bot
        self.chat_id = chat_id
        self.min_interval = min_interval
        self.can_stop = can_stop
        self.keep_on_stop = keep_on_stop
        self.message_thread_id = message_thread_id
        self.reply_markup = reply_markup
        self.protect_content = protect_content
        self.message_effect_id = message_effect_id
        self.draft_id = int.from_bytes(os.urandom(8), "big", signed=True)
        self.text = ""
        self._last_sent = 0.0
        self._last_payload = None

    async def __aenter__(self):
        await self._push("Thinking…", force=True)
        return self

    async def update(self, text: str):
        self.text = (text or "")[:4096]
        await self._push(self.text, force=False)

    async def _push(self, text: str, *, force: bool):
        now = time.monotonic()
        if not force and text == self._last_payload:
            return
        if not force and now - self._last_sent < self.min_interval:
            return

        sent = await self.bot.send_message_draft(
            self.chat_id,
            text,
            draft_id=self.draft_id,
            can_stop=self.can_stop,
            keep_on_stop=self.keep_on_stop,
            message_thread_id=self.message_thread_id,
        )
        self._last_sent = now
        if sent is not False:
            self._last_payload = text

    async def __aexit__(self, exc_type, exc, tb):
        await self.bot.stop_message_draft(
            self.chat_id,
            self.draft_id,
            message_thread_id=self.message_thread_id,
        )
        if exc_type is None and self.text:
            await self.bot.send_message(
                self.chat_id,
                self.text,
                reply_markup=self.reply_markup,
                message_thread_id=self.message_thread_id,
                protect_content=self.protect_content,
                message_effect_id=self.message_effect_id,
            )
        return False
