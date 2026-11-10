# Kanjo brand

[English](BRAND.md)

Kanjo is the name of this userbot. The mark is an original seal: a red disk
on warm paper, with a spine, two bars and a small enclosure. It is not a
Heroku, Hikka or Telegram glyph, and it is not a dictionary kanji.

## Palette

| Role | Hex | Use |
| --- | --- | --- |
| Ink | `#1C1915` | Wordmark, seal strokes, dark backgrounds |
| Paper | `#F4EFE6` | Banner background, seal interior |
| Seal | `#C23B22` | The red disk and the banner rule |
| Gold | `#C4A574` | Thin line under the wordmark, frame of the square mark |
| Moss | `#2F5D50` | The small “userbot” line |

## Mark and wordmark

- `assets/logo.svg`, `assets/logo.png` — square mark, also the picture set on a newly created inline bot
- `assets/favicon.png` — 64×64 export of the same mark (this tree has no HTTP UI to attach it to)
- `assets/banner.svg`, `assets/banner.png` — README banner and the image used in `.info`, `.help`, `.ping`, `/start` and the startup badge
- `assets/banner.txt` — terminal wordmark printed at startup

In-bot image URLs point at this repository:

`https://raw.githubusercontent.com/bertffff/Heroku/master/assets/banner.png`

`https://raw.githubusercontent.com/bertffff/Heroku/master/assets/logo.png`

The slug is `heroku.brand.REPO_SLUG`. Change `REPO_URL` there if the GitHub repository is renamed; the asset URLs follow it.

## Emoji

The chat stand-in for the mark is 🎴 (flower playing cards). It replaces the Heroku planet 🪐 in user-visible text. Premium custom-emoji ids that drew that planet are not reused, because those stickers are the old brand.

## Name in the product

User-visible strings say **Kanjo**. The version string is `Kanjo 1.0.0`. The compatibility tuple `heroku.version.__version__` stays `(2, 2, 0)`, which is Heroku 2.2.0, so `# scope: heroku_min` checks keep passing. `.info` and `.heroku` show both.

Module ids such as `HerokuInfo` stay. `.help HerokuInfo` and database namespaces are unchanged.

## Attribution line

Use this sentence wherever a short credit is needed:

> Kanjo is based on Heroku Userbot (github.com/coddrago/Heroku), itself a fork of Hikka (github.com/hikariatama/Hikka); licensed AGPL-3.0

## Русский

Kanjo — имя этого юзербота. Знак — оригинальная печать: красный круг на тёплой бумаге, стержень, две перекладины и маленькая рамка. Это не логотип Heroku, Hikka или Telegram и не иероглиф из словаря.

Цвета: чернила `#1C1915`, бумага `#F4EFE6`, печать `#C23B22`, золото `#C4A574`, мох `#2F5D50`.

В чате вместо планеты 🪐 стоит 🎴. Картинки берутся из этого репозитория (`assets/banner.png`, `assets/logo.png`). Строка версии для человека — `Kanjo 1.0.0`. Для модулей по-прежнему считается база Heroku 2.2.0.

Короткая атрибуция:

> Kanjo основан на Heroku Userbot (github.com/coddrago/Heroku), а тот — на Hikka (github.com/hikariatama/Hikka); лицензия AGPL-3.0.
