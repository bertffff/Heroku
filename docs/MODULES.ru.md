# Как написать модуль для Kanjo

[English](MODULES.md) · [Русский](MODULES.ru.md)

Модуль Kanjo — это модуль Hikka. Тот же файл встаёт на Hikka, на деревья в духе FTG и на Heroku. Отдельный пакет импортировать не нужно.

```python
# meta developer: you
# scope: heroku_min 1.6.0

from .. import loader, utils


@loader.tds
class HelloMod(loader.Module):
    """Says hello"""

    strings = {"name": "Hello"}
    strings_ru = {"_cls_doc": "Здоровается"}

    @loader.command()
    async def hellocmd(self, message):
        """Say hello"""
        await utils.answer(message, "привет")
```

Поставить его можно ответом `.loadmod` на файл или командой `.dlmod <ссылка>` на HTTPS-адрес.

## Какие импорты уже работают

Относительный импорт — то, чем пользуются ядро и почти все чужие модули:

```python
from .. import loader, utils
```

Срабатывают и такие:

```python
import heroku
from heroku import loader
import hikka          # загрузчик подменяет это на heroku
from hikka import utils
import herokutl       # библиотека Telegram (имя hikkatl из Hikka тоже принимается)
```

`python -m kanjo` этого не меняет. Пакет `kanjo` есть, и `from kanjo.loader import Modules` работает, но модулям лучше по-прежнему импортировать `heroku` или `hikka`. Это тот API, который у них уже есть.

## Имена, которые лучше не трогать

- `@loader.tds` помечает класс, который надо загрузить.
- `strings["name"]` — имя, которое ищет `.help`. У встроенных модулей по-прежнему id вроде `HerokuInfo`. Если правишь ядро, не переименовывай их: в базе пространство имён — это имя класса (`HelloMod` в примере, `HerokuInfoMod` в ядре), а поиск ещё и смотрит на `strings["name"]`.
- `self.inline` — инлайн-менеджер. `self.get` / `self.set` кладут JSON под именем класса. Ключи ядра `heroku.main`, `heroku.inline` и `heroku.loader` на месте. Читать их можно. Ключа `kanjo.main` со старыми данными нет.
- `# scope: heroku_min 1.2.3` сравнивается с `heroku.version.__version__`, а это всё ещё `(2, 2, 0)` — Heroku 2.2.0. Человеку показывается `Kanjo 1.0.0`. Модуль, которому нужна 1.6.0, по-прежнему загрузится. С отображаемой версией Kanjo это число сравнивать не надо.
- `# meta developer:` и `# meta banner:` по-прежнему читаются. Ссылка на баннер в модуле — твоя. Экраны ядра берут картинки из `assets/`.

`self.client`, `self._client`, `message` и `utils.answer` ведут себя как на Heroku и Hikka. Инлайн-формы идут через `self.inline.form`, `.list` и `.gallery`. Новые необязательные аргументы описаны в [INLINE_API.ru.md](INLINE_API.ru.md). Если их не передавать, остаётся старое поведение.

## Чего лучше не делать

Не тащи вторую копию юзербота и не делай `import kanjo` единственным импортом. Не переписывай ключи `hikka.` сам, если только ты не чинишь бэкап Hikka руками: при загрузке такого бэкапа Kanjo сам меняет эти ключи на `heroku.`.

Команды `.heroku`, `.update`, `.ch_heroku_bot` и `.uninstall_heroku` сохранили имена, чтобы старые алиасы и привычка не сломались. Текст в них говорит «Kanjo».
