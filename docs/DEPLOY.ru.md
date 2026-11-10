# Как поставить Kanjo

[English](DEPLOY.md) · [Русский](DEPLOY.ru.md)

Один процесс на один аккаунт Telegram. База — JSON на диске (`config-<id>.json`). Префикс команд остаётся `.`. В сборке есть английский и русский. `.update` забирает только [bertffff/Heroku](https://github.com/bertffff/Heroku). Фонового автообновления нет, и с `Heroku-userbot/Heroku` код не тянется. Адрес лежит в `REPO_URL` в `heroku/brand.py`.

`eval` и `translate` не грузятся, пока их не включишь (`HEROKU_OPTIONAL_MODULES=eval,translate`, или `KANJO_OPTIONAL_MODULES`, если переменная `HEROKU_` пустая, или `optional_modules` в `config.json`). Терминал и управление аккаунтами остаются на месте.

Себя программа называет Kanjo 1.0.0. Модули по-прежнему видят совместимую версию 2.2.0.

## Секреты

`api_id`, `api_hash`, файлы сессий и `config.json` не клади в образ и не коммить.

Имена в окружении, по порядку: сначала `api_id` и `api_hash`, потом `API_ID` и `API_HASH`. Пустые значения пропускаются, поэтому пустая переменная в compose не затирает уже сохранённый конфиг.

Файлы, которые процесс пишет сам (`config.json`, `config-<id>.json`), получают права `0600`. Каталог `sessions/` — `0700`.

```bash
sudo install -d -m 0700 -o 1000 -g 1000 /var/lib/kanjo
```

Пример `/etc/kanjo/account.env`:

```bash
api_id=123456
api_hash=your_api_hash
# Достаточно одной. Непустая HEROKU_TRANSPORT важнее.
HEROKU_TRANSPORT=auto
# KANJO_TRANSPORT=ws
```

`api_id` и `api_hash` берутся на [my.telegram.org](https://my.telegram.org).

## Транспорт

| Значение | Когда |
| --- | --- |
| `auto` (по умолчанию) | WebSocket, только если задан `SAND_EGRESS_TUNNEL_PROXY_ADDR` или `127.0.0.1:8791` принимает TCP. Иначе прямой TCP. |
| `ws` | Всегда `wss://<dc>.web.telegram.org/apiws`. Нужен, когда HTTPS открывается, а сырой TCP до DC (`149.154.*`) режется. Если сам WebSocket должен идти через прокси, задай `SAND_EGRESS_TUNNEL_PROXY_ADDR` (`host:port`, `http://…` или `socks5://…`). |
| `tcp` | Всегда прямой TCP. |

Переменная — `HEROKU_TRANSPORT`. Если её нет или она пустая, читается `KANJO_TRANSPORT`. Флаг `--transport` перекрывает обе. `--proxy-host` по-прежнему важнее транспорта.

Пинги WebSocket идут каждые 20 секунд, чтобы простой прокси реже рвал сокет. Пропавший pong живую сессию не закрывает. Если прокси всё же оборвал связь, клиент переподключается. Сокет, который умер быстрее чем за 5 секунд, ждёт 1, 2, 4, 8, потом 16 секунд. Более долгие обрывы, в том числе тихий простой, переподключаются сразу. Инлайн-бот ходит тем же транспортом и повторяет так же.

Имена веб-DC: 1 `pluto`, 2 `venus`, 3 `aurora`, 4 `vesta`, 5 `flora`.

## Docker

Собирай из этого дерева. Dockerfile копирует контекст сборки и никуда больше не клонирует.

```bash
docker compose build
docker compose run --rm kanjo
```

Первый запуск интерактивный: телефон или QR, затем 2FA. Сессия и конфиг попадают в том `heroku-data`. Имя тома специально старое, чтобы уже созданный том остался подключён. После входа процесс перезапускается сам. Дальше:

```bash
docker compose up -d
docker compose logs -f
```

`docker compose restart` останавливает и поднимает снова. Данные переживают пересоздание контейнера.

Пользователь в образе — `kanjo`, uid 1000. Пакеты pip для него ставятся в `/home/kanjo/.local`. Команда образа — `python -m kanjo`; `python -m heroku` тоже запускает программу.

Второй аккаунт — второй процесс и второй том. Скопируй сервис или запусти другой проект compose:

```bash
docker compose -p kanjo-b run --rm kanjo
docker compose -p kanjo-b up -d
```

`.update` внутри контейнера ходит только на `https://github.com/bertffff/Heroku`. Образ пересобирай, когда нужны системные пакеты вроде `ffmpeg`. Каталог с хоста вместо именованного тома монтируй только после `chown 1000:1000`.

`docker.sh` клонирует этот форк и собирает тот же compose-файл.

## systemd

Новая установка: дерево в `/opt/kanjo`, virtualenv в `/opt/kanjo/.venv`, пользователь `kanjo`, данные в `/var/lib/kanjo` с правами `0700`. Юнит: [`kanjo.service`](kanjo.service).

```bash
sudo useradd --system --create-home --shell /usr/sbin/nologin kanjo
sudo install -d -m 0700 -o kanjo -g kanjo /var/lib/kanjo
sudo install -d -m 0750 -o root -g kanjo /etc/kanjo
sudo touch /etc/kanjo/account.env
sudo chown root:kanjo /etc/kanjo/account.env
sudo chmod 0640 /etc/kanjo/account.env
sudo cp docs/kanjo.service /etc/systemd/system/kanjo.service
sudo systemctl daemon-reload
sudo systemctl enable --now kanjo
```

Первый вход нужен в терминале:

```bash
sudo -u kanjo /opt/kanjo/.venv/bin/python -m kanjo --data-root /var/lib/kanjo
```

Ещё один аккаунт — другой каталог данных, другой env-файл и второй юнит со своим `--data-root`.

### Уже стоит heroku.service

Оставь [`heroku.service`](heroku.service), если код лежит в `/opt/heroku`, пользователь — `heroku`, а данные — в `/var/lib/heroku`. Этот юнит по-прежнему запускает `python -m heroku`. Переименовывать пользователя и каталог, чтобы Kanjo стартовал, не нужно. `HEROKU_*` в `/etc/heroku/account.env` продолжают работать.

`.update` забирает этот форк. `Restart=on-failure` поднимает процесс после падения. Ручной перезапуск — `systemctl restart kanjo` или `heroku`, если юнит ты оставил старый.
