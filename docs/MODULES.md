# Writing a module for Kanjo

[English](MODULES.md) · [Русский](MODULES.ru.md)

A Kanjo module is a Hikka module. The same file loads on Hikka, FTG-style trees and Heroku. Kanjo does not make you import a new package.

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
        await utils.answer(message, "hello")
```

Load it by replying `.loadmod` to the file, or `.dlmod <link>` for an HTTPS URL.

## Imports that already work

Relative imports are what core modules and most community modules use:

```python
from .. import loader, utils
```

These also resolve:

```python
import heroku
from heroku import loader
import hikka          # the loader maps this to heroku
from hikka import utils
import herokutl       # the Telegram library (Hikka's hikkatl name is accepted too)
```

`python -m kanjo` does not change this. There is a `kanjo` package, and `from kanjo.loader import Modules` works, but modules should keep importing `heroku` or `hikka`. That is the API they already have.

## Names that must stay

- `@loader.tds` marks the class to load.
- `strings["name"]` is the name `.help` searches. Core modules still use ids such as `HerokuInfo`. Do not rename those if you are patching core: the database namespace is the class name (`HelloMod` above, `HerokuInfoMod` in core), and lookup also accepts `strings["name"]`.
- `self.inline` is the inline manager. `self.get` / `self.set` store JSON under the class name. Core keys `heroku.main`, `heroku.inline` and `heroku.loader` are unchanged. Read them if you must; do not invent a `kanjo.main` key and expect old data to be there.
- `# scope: heroku_min 1.2.3` is checked against `heroku.version.__version__`, which is still `(2, 2, 0)` (Heroku 2.2.0). The string users see is `Kanjo 1.0.0`. A module that requires 1.6.0 still loads. Do not compare against the Kanjo display version.
- `# meta developer:` and `# meta banner:` are still read. A banner URL in the module is yours. Core screens use the images in `assets/`.

`self.client`, `self._client`, `message` and `utils.answer` behave as they do on Heroku and Hikka. Inline forms go through `self.inline.form`, `.list` and `.gallery`. New optional arguments are in [INLINE_API.md](INLINE_API.md). Leaving them out keeps the old behaviour.

## What not to do

Do not vendor a second copy of the userbot or pin `import kanjo` as the only import. Do not rewrite `hikka.` database keys yourself unless you are restoring a Hikka backup: Kanjo already rewrites those keys to `heroku.` when it loads one.

Commands such as `.heroku`, `.update`, `.ch_heroku_bot` and `.uninstall_heroku` kept their names so old aliases and muscle memory work. Their text says Kanjo.
