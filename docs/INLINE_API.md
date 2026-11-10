# Inline bot API additions

These kwargs and button keys are opt-in. Omitting them keeps the previous
Hikka/FTG behaviour. The inline bot speaks MTProto through herokutl 2.2.1
(layer 230), not the HTTP Bot API. A rejection that names the new flag is
retried without it. `FloodWait` is never retried. Dropping `protect_content`
is logged as a warning; other flag fallbacks are debug.

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

`{"text": "Later", "disabled": True}` builds `InlineButtonTypeDisabled` on
messages the bot sends itself. A disabled button does not register a user
callback, even if `callback` is also set. Inline results
(`messages.setInlineBotResults`) reject that type and also reject `web_app`
(`InlineButtonTypeWebView`; `ButtonTypeSimpleWebView` is a reply-keyboard
button, not an inline one). Forms, lists and galleries therefore send a
disabled button as a silent callback and a web app as a URL button, keeping
`style` and `emoji_id`. If the server still returns `BUTTON_TYPE_INVALID`,
the result is rebuilt once and resent, with a single warning. Copy buttons
stay copy buttons.

Icons only render for bots with a Fragment username, or on messages the bot
sends directly in a private or group chat when the bot owner has Premium.
Inline forms are delivered with `messages.sendInlineBotResult` from the user
account, so the colour can show while the icon does not. Confirm on a real
client.

`build_pagination(..., disabled_current=False)` still gives the current page a
callback, so modules that read the page argument keep working. Pass
`disabled_current=True`, or turn on **disabled_current_page** in
`.config InlineStuff` (default off), to render `· N ·` as a disabled button.

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

A form with no buttons is edited once after it is delivered, to remove the
placeholder button Telegram needs in order to edit the message. That edit
keeps `link_preview`, `preview_size`, `preview_above` and `invert_media`.
Later `msg.edit(text)` calls do the same unless you pass a new value
(`link_preview=False` turns the card off).

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
- `bot_stopped` (`UpdateBotStopped`)
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

## Try it

`examples/inline_qol_demo.py` is not loaded with the core modules. Reply to
that file with `.loadmod`. It adds:

| command | what it sends |
|---|---|
| `.qoldisabled` | form with a disabled button plus styled copy and web app buttons |
| `.qolephem` | ephemeral answer button, and a callback that calls `answer_ephemeral` |
| `.qolpreview` | form whose link preview is large and above the text |
| `.qolrich` | rich list using `utils.expandable` |
| `.qolstream` | draft stream into your bot PM, then a real message |
| `.qolprotect` | protected bot-PM message with a message effect |

## What still needs a real account

- Coloured buttons and custom-emoji icons on inline forms versus direct bot messages
- Ephemeral replies in a group, including `replace=True`
- Draft streaming in bot PM, including the typing fallback
- Webpage size and above-text placement
- Caption-above-media on a gallery page turn
- `protect_content` and a message effect in bot PM
- A rich list page on a client that supports rich messages
