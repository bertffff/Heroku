# Deploy Kanjo

[English](DEPLOY.md) · [Русский](DEPLOY.ru.md)

One process per Telegram account. The database is JSON on disk (`config-<id>.json`). The command prefix stays `.`. Languages built in are English and Russian. `.update` pulls [bertffff/Heroku](https://github.com/bertffff/Heroku) only. There is no background autoupdate and no fetch from `Heroku-userbot/Heroku`. The remote is `REPO_URL` in `heroku/brand.py`.

`eval` and `translate` stay unloaded until you opt in (`HEROKU_OPTIONAL_MODULES=eval,translate`, or `KANJO_OPTIONAL_MODULES` when the Heroku variable is empty, or `optional_modules` in `config.json`). Terminal and account management stay installed.

The program reports itself as Kanjo 1.0.0. Modules still see compatibility version 2.2.0.

## Secrets

Do not put `api_id`, `api_hash`, session files or `config.json` in the image or in git.

Accepted environment names, in order: `api_id` + `api_hash`, then `API_ID` + `API_HASH`. Blank values are ignored, so an empty compose variable does not hide a saved config.

Files the process writes (`config.json`, `config-<id>.json`) are mode `0600`. `sessions/` is mode `0700`.

```bash
sudo install -d -m 0700 -o 1000 -g 1000 /var/lib/kanjo
```

`/etc/kanjo/account.env` example:

```bash
api_id=123456
api_hash=your_api_hash
# Set one of these. A non-empty HEROKU_TRANSPORT wins.
HEROKU_TRANSPORT=auto
# KANJO_TRANSPORT=ws
```

Get `api_id` and `api_hash` from [my.telegram.org](https://my.telegram.org).

## Transport

| Value | When |
| --- | --- |
| `auto` (default) | WebSocket only when `SAND_EGRESS_TUNNEL_PROXY_ADDR` is set, or when `127.0.0.1:8791` accepts TCP. Otherwise direct TCP. |
| `ws` | Always `wss://<dc>.web.telegram.org/apiws`. Use this when the host can open HTTPS but the network drops raw DC TCP (`149.154.*`). Set `SAND_EGRESS_TUNNEL_PROXY_ADDR` (`host:port`, `http://…`, or `socks5://…`) when that WebSocket itself must go through an HTTP CONNECT or SOCKS proxy. |
| `tcp` | Always direct TCP. |

The variable is `HEROKU_TRANSPORT` or, if that one is unset or blank, `KANJO_TRANSPORT`. `--transport` on the command line overrides both. `--proxy-host` still wins over the transport.

WebSocket keepalive pings every 20s so an idle proxy is less likely to drop the socket. A missing WebSocket pong does not close a live session. If a proxy still closes it, the client reconnects. A socket that dies in under 5 seconds backs off (1s, 2s, 4s, 8s, 16s). Longer drops, including an idle close, reconnect immediately. The inline bot uses the same transport and retries the same way.

Web DC hosts: 1 `pluto`, 2 `venus`, 3 `aurora`, 4 `vesta`, 5 `flora`.

## Docker

Build from this checkout. The Dockerfile copies the build context. It does not clone another remote.

```bash
docker compose build
docker compose run --rm kanjo
```

The first run is interactive (phone or QR, then 2FA). Session and config land in the `heroku-data` volume. The volume key is intentionally the old name, so an existing volume stays attached. After login the process restarts itself; start it in the background:

```bash
docker compose up -d
docker compose logs -f
```

Stop and start again with `docker compose restart`. Data survives recreate.

The image user is `kanjo`, uid 1000. Pip installs for that user go to `/home/kanjo/.local`. The command is `python -m kanjo`; `python -m heroku` works too.

A second account is a second process and a second volume. Copy the service or run another compose project:

```bash
docker compose -p kanjo-b run --rm kanjo
docker compose -p kanjo-b up -d
```

`.update` inside the container fetches `https://github.com/bertffff/Heroku` only. Rebuild the image when you want OS packages such as `ffmpeg` updated. Bind-mount a host directory instead of the named volume only after `chown 1000:1000` on that directory.

`docker.sh` clones this fork and then builds the same compose file.

## systemd

New install, checkout under `/opt/kanjo`, virtualenv at `/opt/kanjo/.venv`, user `kanjo`, data directory `/var/lib/kanjo` mode `0700`. Unit: [`kanjo.service`](kanjo.service).

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

First login needs a TTY:

```bash
sudo -u kanjo /opt/kanjo/.venv/bin/python -m kanjo --data-root /var/lib/kanjo
```

Another account: another data directory, another env file, and a second unit with its own `--data-root`.

### Already on heroku.service

Leave [`heroku.service`](heroku.service) if the checkout is `/opt/heroku`, the user is `heroku` and the data is `/var/lib/heroku`. That unit still runs `python -m heroku`. You do not have to rename the user or the data directory for Kanjo to start. `HEROKU_*` in `/etc/heroku/account.env` keeps working.

`.update` pulls this fork. `Restart=on-failure` brings the process back after a crash. `systemctl restart kanjo` (or `heroku`, if that is the unit you kept) is the manual restart.
