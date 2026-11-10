[English](README.md) · [Русский](README.ru.md)

<p align="center">
  <img src="assets/banner.png" alt="Kanjo" width="640">
</p>

# Kanjo

Kanjo — юзербот для Telegram. Он работает от твоего аккаунта, ставит модули и держит небольшого инлайн-бота для кнопок и форм.

Kanjo основан на Heroku Userbot (github.com/coddrago/Heroku), а тот — на Hikka (github.com/hikariatama/Hikka); лицензия AGPL-3.0.

Репозиторий — [bertffff/Heroku](https://github.com/bertffff/Heroku). На GitHub он по-прежнему называется Heroku. В чате и в логах это Kanjo 1.0.0 поверх API модулей Heroku 2.2.0. Пакет Python остаётся `heroku`, поэтому уже стоящие копии и чужие модули переезжать не должны.

## Что внутри

- Префикс команд `.` (его можно сменить), модули, инлайн-формы, списки и галереи.
- Обфусцированный WebSocket, если сеть режет голый MTProto TCP. Подробности в [docs/DEPLOY.ru.md](docs/DEPLOY.ru.md).
- Терминал, который спрашивает sudo в чате и не оставляет лишнюю root-оболочку. Об этом в [docs/SECURITY.ru.md](docs/SECURITY.ru.md).
- `eval` и `translate` не грузятся, пока их явно не включишь.
- Дополнения инлайн-бота (выключенные кнопки, эфемерные ответы, черновики, превью ссылок) — в [docs/INLINE_API.ru.md](docs/INLINE_API.ru.md).
- Модули Hikka, FTG, GeekTG и Heroku. `from .. import loader, utils`, `import heroku`, `import hikka`, `@loader.tds` и `self.inline` работают как раньше. Коротко: [docs/MODULES.ru.md](docs/MODULES.ru.md).

## Установка

Нужен Python 3.10 или новее. `api_id` и `api_hash` берутся на [my.telegram.org](https://my.telegram.org). В git их класть не надо.

### Docker

```bash
git clone https://github.com/bertffff/Heroku Kanjo
cd Kanjo
docker compose build
docker compose run --rm kanjo
docker compose up -d
```

Сервис называется `kanjo`, образ — `kanjo:local`. Сессия и конфиг лежат в томе `heroku-data`: том, созданный до переименования, подхватится снова. Внутри образа `python -m heroku` запускает то же самое; команда образа — `python -m kanjo`.

`docker.sh` клонирует этот репозиторий и собирает тот же compose-файл.

### VPS и systemd

Новая установка: [docs/kanjo.service](docs/kanjo.service), пользователь `kanjo`, данные в `/var/lib/kanjo`.

Если уже крутится `heroku.service` из `/opt/heroku`, юнит лучше не трогать. Он по-прежнему стартует `python -m heroku`. Файл [docs/heroku.service](docs/heroku.service) — как раз этот старый вариант.

Пошагово: [docs/DEPLOY.ru.md](docs/DEPLOY.ru.md).

### Без Docker и без systemd

```bash
git clone https://github.com/bertffff/Heroku Kanjo
cd Kanjo
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python3 -m kanjo
```

`python3 -m heroku` — тот же процесс. Установщик понимает оба имени:

```bash
curl -fsSL https://raw.githubusercontent.com/bertffff/Heroku/master/install.sh | bash
```

Повторный запуск просто стартует уже найденную копию, в том числе каталог `Heroku`. Команды выполняются от root: `bash -s -- --root`. `HEROKU_FORCE_INSTALL=1` или `KANJO_FORCE_INSTALL=1` ставит заново.

## Настройки

Пустые значения пропускаются. Если заданы обе переменные пары, берётся непустая `HEROKU_*`. `KANJO_*` срабатывает, только когда парная `HEROKU_*` пустая или её нет.

| Зачем | Имена |
| --- | --- |
| Транспорт `auto`, `tcp` или `ws` | `HEROKU_TRANSPORT`, `KANJO_TRANSPORT` |
| Без git | `HEROKU_NO_GIT=1`, `KANJO_NO_GIT=1` |
| Подгрузить `eval` и/или `translate` | `HEROKU_OPTIONAL_MODULES`, `KANJO_OPTIONAL_MODULES` (через запятую) |
| URL клона, venv, ветка, урезанный режим, переустановка | `HEROKU_REPO_URL` / `KANJO_REPO_URL` и так же `VENV_DIR`, `BRANCH`, `MINIMAL`, `FORCE_INSTALL` |

Ключи API: `api_id` и `api_hash`, либо `API_ID` и `API_HASH`.

`auto` выбирает WebSocket, если задан `SAND_EGRESS_TUNNEL_PROXY_ADDR` или на `127.0.0.1:8791` кто-то слушает. Иначе остаётся прямой TCP. `--proxy-host` по-прежнему важнее транспорта.

Ключи базы вроде `heroku.main` и `heroku.inline`, файлы сессий `heroku-<id>.session`, `config.json`, `config-<id>.json` и `.modules_cache` не переименовывались.

## Обновление

Команда `.update` забирает только этот репозиторий. Адрес записан в `REPO_URL` в `heroku/brand.py` (`https://github.com/bertffff/Heroku`). Если репозиторий переедет, достаточно поменять эту константу. Фоновое автообновление выключено, с `Heroku-userbot/Heroku` код не тянется.

## Несколько аккаунтов

Один процесс и один каталог данных на аккаунт. В Docker — другой проект compose или другой том. В systemd — другой `--data-root` и другой юнит. Два аккаунта в одном процессе не смешивай.

## Безопасность

Kanjo может выполнять код и команды оболочки от того пользователя, под которым запущен. Прежде чем ставить модули из интернета, прочитай [docs/SECURITY.ru.md](docs/SECURITY.ru.md). Telegram юзерботы не поддерживает: бан возможен.

## Модули

Имена встроенных модулей (`HerokuInfo`, `Settings`, `Loader` и остальные) те же, поэтому `.help HerokuInfo` их по-прежнему находит. Как писать свой модуль: [docs/MODULES.ru.md](docs/MODULES.ru.md). Сторонний каталог модулей по умолчанию — upstream (`https://raw.githubusercontent.com/coddrago/modules/main`). Это источник модулей, а не чат поддержки Kanjo. Его можно сменить в `.config` у модуля Loader (`MODULES_REPO`). Дополнительные каталоги задаются в `ADDITIONAL_REPOS`.

## Авторы и лицензия

Kanjo основан на Heroku Userbot (github.com/coddrago/Heroku), а тот — на Hikka (github.com/hikariatama/Hikka); лицензия AGPL-3.0.

Строки копирайта Dan Gazizullin (Hikka) и Codrago (Heroku) в исходниках на месте. Рядом добавлены участники Kanjo (bertffff, 2026). Смотри [NOTICE](NOTICE) и [LICENSE](LICENSE).

Цвета, печать и 🎴 описаны в [docs/BRAND.md](docs/BRAND.md).
