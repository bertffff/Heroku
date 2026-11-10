# Дополнения инлайн-бота

[English](INLINE_API.md) · [Русский](INLINE_API.ru.md)

Инлайн-бот Kanjo — это инлайн-менеджер Heroku/Hikka. Новые аргументы и поля кнопок необязательны. Если их не передавать, остаётся прежнее поведение Hikka/FTG. Бот говорит с Telegram по MTProto через herokutl 2.2.1 (слой 230), а не через HTTP Bot API. Если сервер отклоняет запрос и в ошибке назван новый флаг, отправка повторяется без него. `FloodWait` не повторяется. Сброс `protect_content` пишется в лог как предупреждение, остальные откаты флагов — на уровне debug.

`self.inline`, `@loader.tds`, ключ базы `heroku.inline` и `from .. import loader, utils` не менялись. Смотри [MODULES.ru.md](MODULES.ru.md).

Виджеты из Bot API 10.4 в этом слое нет, поэтому их здесь нет.

## Кнопки

`style` (`"primary"`, `"success"`, `"danger"`) и `emoji_id` (id кастомного эмодзи, он же иконка кнопки) сохраняются у любого типа кнопки, включая `web_app` и `copy`.

```python
{
    "text": "Скопировать",
    "copy": "secret",
    "style": "success",
    "emoji_id": "5391234567890",
}
```

`{"text": "Позже", "disabled": True}` собирает `InlineButtonTypeDisabled` в сообщениях, которые бот шлёт сам. Выключенная кнопка не регистрирует колбэк пользователя, даже если рядом указан `callback`. Инлайн-результаты (`messages.setInlineBotResults`) этот тип отвергают и так же отвергают `web_app` (`InlineButtonTypeWebView`; `ButtonTypeSimpleWebView` — кнопка обычной клавиатуры, не инлайн). Поэтому формы, списки и галереи отправляют выключенную кнопку как тихий колбэк, а веб-приложение — как кнопку-ссылку, сохраняя `style` и `emoji_id`. Если сервер всё равно отвечает `BUTTON_TYPE_INVALID`, результат собирается ещё раз и отправляется повторно, с одним предупреждением. Кнопки копирования остаются кнопками копирования.

Иконки видны у ботов с юзернеймом с Fragment или в сообщениях, которые бот шлёт сам в личку или в группу, если у владельца бота есть Premium. Инлайн-формы уходят через `messages.sendInlineBotResult` от пользовательского аккаунта, поэтому цвет может показаться, а иконка — нет. Проверяй на живом клиенте.

`build_pagination(..., disabled_current=False)` по-прежнему даёт текущей странице колбэк, так что модули, которые читают номер страницы, не ломаются. Передай `disabled_current=True` или включи **disabled_current_page** в `.config InlineStuff` (по умолчанию выключено), чтобы `· N ·` рисовалась выключенной кнопкой.

## Эфемерные ответы

Их видит только тот, кто нажал кнопку. После успешной отправки бот всё равно отвечает на callback query пустым ответом.

```python
await call.answer_ephemeral("<b>только тебе</b>", reply_markup=markup)
await call.answer_ephemeral("rich", rich_message="<b>rich</b>")
```

Та же проверка доступа, что и у любого другого колбэка:

```python
{"text": "Подсказка", "action": "answer", "message": "только тебе", "ephemeral": True}
```

`replace=True` ставит флаг MTProto `anchor`. Это лишь догадка про Bot API `replace_callback_query_message`, и при отказе сервера запрос повторяется без флага. Любая другая ошибка RPC становится `call.answer(text[:200], show_alert=True)`. Если пользователь офлайн, доставка не гарантируется. Не клади туда то, что обязано дойти.

`client.send_rich_ephemeral` теперь приводит `receiver_id` к `InputUser`.

## Черновики (личные чаты)

Черновик — короткая подсказка. Текст, который должен остаться, отправляй обычным сообщением. Вне личного чата черновик пропускается, а итоговый `send_message` всё равно выполняется. Если действие черновика отклонено, бот шлёт обычный «печатает».

```python
await self.inline.bot.send_message_draft(user_id, "Работаю…", draft_id=123)

async with self.inline.stream(user_id) as draft:
    await draft.update("Шаг 1")
    await draft.update("Готово")  # троттлинг, а при выходе текст уходит по-настоящему
```

`stream()` ждёт не меньше 0,7 с между обновлениями и держит 4096 символов. `can_stop` и `keep_on_stop` пробрасываются. Исключение внутри блока останавливает черновик и не шлёт итоговое сообщение.

## Превью ссылок

На `form()` и на `InlineMessage.edit` / `_edit_unit`:

| Аргумент | Смысл |
| --- | --- |
| `link_preview=None` или `False` | без превью (так по умолчанию) |
| `link_preview=True` | Telegram сам выбирает превью из текста |
| `link_preview="https://…"` | эта страница, через `InputBotInlineMessageMediaWebPage` / `InputMediaWebPage` |
| `preview_size="large"` или `"small"` | принудительно крупное или мелкое медиа |
| `preview_above=True` | превью над текстом |

На веб-странице стоит `optional=True`, чтобы плохой URL не ронял всю отправку. Исключение — когда задан `preview_size`. Принудительная крупная или мелкая карточка не опциональна, иначе правка сжимает её до маленького превью. Отклонённая правка превью повторяется как обычный текст.

Форма без кнопок один раз правится уже после доставки, чтобы убрать кнопку-заглушку, без которой Telegram не даёт редактировать сообщение. Эта правка сохраняет `link_preview`, `preview_size`, `preview_above` и `invert_media`. Дальнейшие `msg.edit(text)` делают то же, пока ты не передашь новое значение (`link_preview=False` выключает карточку).

```python
await self.inline.form(
    "Заметки https://example.com",
    message,
    link_preview="https://example.com",
    preview_size="small",
    preview_above=True,
)
```

## Подпись над медиа

`invert_media=True` на `form()` (фото, gif, видео, файл, аудио) и на `gallery()`. Правки передают тот же флаг. У rich-форм флага подписи нет, там он игнорируется. Отклонённая правка повторяется без флага. Flood-wait и ошибки пропавшего медиа не глотаются.

## Защита содержимого и эффекты

Только прямые отправки бота: `TelethonBot.send_message`, `send_photo`, `send_document`, `send_audio`, `send_rich_message` и `BotMessage.answer` / `answer_photo`.

```python
await self.inline.bot.send_message(
    user_id,
    "Бэкап готов",
    protect_content=True,
    message_effect_id=5046509860389126442,
)
```

`protect_content` — это `noforwards`. Медиа уходит сырым `messages.sendMedia`, потому что `send_file` этот флаг теряет. Эффекты — для личных чатов. Если сервер отвергает любой из флагов, сообщение уходит ещё раз без них.

`form()`, `list()` и `gallery()` идут через `messages.sendInlineBotResult`, где нет полей `noforwards` и `effect`. Там эти аргументы ничего не делают.

## Обработчики апдейтов бота

`register_bot_update_handler` принимает ещё и эти типы. В обработчик приходит сырой апдейт MTProto. Старые типы не меняются. `ephemeral_callback_query` сам в `InlineCall` не превращается.

- `business_connection`
- `business_message`
- `edited_business_message`
- `deleted_business_messages`
- `purchased_paid_media`
- `bot_stopped` (`UpdateBotStopped`)
- `subscription`
- `ephemeral_callback_query`

## Rich-списки и раскрываемые цитаты

```python
await self.inline.list(message, ["<b>Страница</b>"], rich=True)
```

Отклонённый rich-результат или правка отправляются ещё раз как HTML.

`<blockquote expandable>` в rich-списке уходит свёрнутой цитатой (`PageBlockBlockquote.collapsed`), в том числе когда страницу правят. HTML-запасной путь сохраняет тот же тег, а обычный парсер кладёт его в `MessageEntityBlockquote(collapsed=True)`.

```python
from heroku import utils
utils.expandable("длинный лог")  # <blockquote expandable>длинный лог</blockquote>
```

Парсер HTML уже превращает этот тег в свёрнутую цитату.

## Попробовать

`examples/inline_qol_demo.py` сам с ядром не грузится. Ответь на файл командой `.loadmod`. Появятся:

| Команда | Что шлёт |
| --- | --- |
| `.qoldisabled` | форма с выключенной кнопкой и оформленными кнопками копирования и веб-приложения |
| `.qolephem` | кнопка эфемерного ответа и колбэк, который зовёт `answer_ephemeral` |
| `.qolpreview` | форма, у которой превью крупное и стоит над текстом |
| `.qolrich` | rich-список через `utils.expandable` |
| `.qolstream` | черновик в личку бота, затем настоящее сообщение |
| `.qolprotect` | защищённое сообщение в личку бота с эффектом |

## Что всё ещё нужно проверить на живом аккаунте

- Цветные кнопки и иконки-эмодзи на инлайн-формах и на прямых сообщениях бота
- Эфемерные ответы в группе, включая `replace=True`
- Черновики в личке бота, включая запасной «печатает»
- Размер веб-превью и положение над текстом
- Подпись над медиа при перелистывании галереи
- `protect_content` и эффект сообщения в личке бота
- Страница rich-списка на клиенте, который умеет rich-сообщения
