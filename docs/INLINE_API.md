# Inline bot API additions

These kwargs and button keys are opt-in. Omitting them keeps the previous
Hikka/FTG behaviour. The inline bot speaks MTProto through herokutl 2.2.1
(layer 230), not the HTTP Bot API. If a server or client rejects a new flag,
the call logs at debug and falls back to the old request.

Widgets from Bot API 10.4 are not in this layer, so they are not exposed.

## Buttons

`style` (`"primary"`, `"success"`, `"danger"`) and `emoji_id` (custom-emoji
document id, sent as the button icon) are kept for every button type,
including `web_app` and `copy`.

```python
{
    "text": "Copy",
    "copy": "secret",
    "style": "success",
    "emoji_id": "5391234567890",
}
```

`{"text": "Later", "disabled": True}` builds `InlineButtonTypeDisabled`. A
disabled button does not register a callback, even if `callback` is also set.
If the constructor is missing, the button becomes an inert placeholder
(`data="­"`).

Icons only render for bots with a Fragment username, or on messages the bot
sends directly in a private or group chat when the bot owner has Premium.
Inline forms are delivered with `messages.sendInlineBotResult` from the user
account, so the colour can show while the icon does not. Confirm on a real
client.

`build_pagination(..., disabled_current=False)` still gives the current page a
callback, so modules that read the page argument keep working. Pass
`disabled_current=True`, or set the database key `heroku.inline` /
`disabled_current_page` to true, to render `· N ·` as a disabled button.

## Ephemeral replies

Visible only to the user who pressed the button. The bot still answers the
callback query (empty) after a successful ephemeral send.

```python
await call.answer_ephemeral("<b>only you</b>", reply_markup=markup)
await call.answer_ephemeral("rich", rich_message="<b>rich</b>")
```

Button form, same security checks as any other callback:

```python
{"text": "Hint", "action": "answer", "message": "only you", "ephemeral": True}
```

`replace=True` sets the MTProto `anchor` flag. That is only a guess for Bot
API `replace_callback_query_message` and is retried without the flag if the
server rejects it. Any other RPC error becomes `call.answer(text[:200],
show_alert=True)`. Ephemeral delivery is not guaranteed when the user is
offline. Do not put data there that must arrive.

`client.send_rich_ephemeral` now resolves `receiver_id` to `InputUser`.

## Draft streaming (private chats)

Drafts are a short-lived preview. Persist the text with a real send. Outside
a private chat the draft is skipped and the final `send_message` still runs.
If the draft action is rejected, the bot sends a normal typing action.

```python
await self.inline.bot.send_message_draft(user_id, "Working…", draft_id=123)

async with self.inline.stream(user_id) as draft:
    await draft.update("Step 1")
    await draft.update("Done")  # throttled, then sent for real on exit
```

`stream()` waits at least 0.7s between updates and keeps 4096 characters.
`can_stop` and `keep_on_stop` are forwarded. An exception inside the block
stops the draft and does not send the final message.

## Link previews

On `form()` and on `InlineMessage.edit` / `_edit_unit`:

| kwarg | meaning |
|---|---|
| `link_preview=None` or `False` | no preview (the default) |
| `link_preview=True` | Telegram picks a preview from the text |
| `link_preview="https://…"` | that page, via `InputBotInlineMessageMediaWebPage` / `InputMediaWebPage` |
| `preview_size="large"` or `"small"` | force large or small media |
| `preview_above=True` | preview above the text |

`optional=True` is set on the webpage so a bad URL does not fail the whole
send. A rejected preview edit is retried as a plain text edit.

```python
await self.inline.form(
    "Notes https://example.com",
    message,
    link_preview="https://example.com",
    preview_size="small",
    preview_above=True,
)
```

## Caption above media

`invert_media=True` on `form()` (photo, gif, video, file, audio) and
`gallery()`. Edits pass the same flag. Rich forms have no caption flag, so it
is ignored there. A rejected edit is retried without the flag. Flood-wait and
missing-media errors are not swallowed.

## Protect content and message effects

Direct bot sends only: `TelethonBot.send_message`, `send_photo`,
`send_document`, `send_audio`, `send_rich_message`, and
`BotMessage.answer` / `answer_photo`.

```python
await self.inline.bot.send_message(
    user_id,
    "Backup is ready",
    protect_content=True,
    message_effect_id=5046509860389126442,
)
```

`protect_content` is `noforwards`. Media uses raw `messages.sendMedia` because
`send_file` drops that flag. Effects are for private chats. If the server
rejects either flag, the message is sent again without them.

`form()`, `list()` and `gallery()` go out through `messages.sendInlineBotResult`,
which has no `noforwards` or `effect` field. Those kwargs do nothing there.

## Bot update handlers

`register_bot_update_handler` accepts these extra types. Handlers receive the
raw MTProto update. Nothing about existing types changes.
`ephemeral_callback_query` is not turned into `InlineCall` automatically.

- `business_connection`
- `business_message`
- `edited_business_message`
- `deleted_business_messages`
- `purchased_paid_media`
- `bot_stopped` and `my_chat_member_private` (both are `UpdateBotStopped`)
- `subscription`
- `ephemeral_callback_query`

## Rich lists and expandable quotes

```python
await self.inline.list(message, ["<b>Page</b>"], rich=True)
```

A rejected rich result or edit is sent again as HTML.

```python
from heroku import utils
utils.expandable("long log")  # <blockquote expandable>long log</blockquote>
```

The HTML parser already maps that tag to a collapsed blockquote.

## What still needs a real account

- Coloured buttons and custom-emoji icons on inline forms versus direct bot messages
- Ephemeral replies in a group, including `replace=True`
- Draft streaming in bot PM, including the typing fallback
- Webpage size and above-text placement
- Caption-above-media on a gallery page turn
- `protect_content` and a message effect in bot PM
- A rich list page on a client that supports rich messages
