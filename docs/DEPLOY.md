# Deploy this fork

Personal VPS deploy of [bertffff/Heroku](https://github.com/bertffff/Heroku). One process per Telegram account. The database is JSON on disk (`config-<id>.json`). Command prefix stays `.`. Languages are `en` and `ru`. Updates are manual `.update` from this fork. There is no background autoupdate and no pull from `Heroku-userbot/Heroku`.

`eval` and `translate` stay unloaded until you opt in (`HEROKU_OPTIONAL_MODULES=eval,translate` or `optional_modules` in `config.json`). Terminal and `heroku_web` stay installed.

## Secrets

Do not put `api_id`, `api_hash`, session files, or `config.json` in the image or in git.

Accepted environment names, in order: `api_id` + `api_hash`, then `API_ID` + `API_HASH`. Blank values are ignored so an empty compose variable does not hide a saved config.

Files the process writes (`config.json`, `config-<id>.json`) are mode `0600`. `sessions/` is mode `0700`. On the host:

```bash
sudo install -d -m 0700 -o 1000 -g 1000 /var/lib/heroku
```

`/etc/heroku/account.env` example:

```bash
api_id=123456
api_hash=your_api_hash
HEROKU_TRANSPORT=auto
```

Get `api_id` and `api_hash` from [my.telegram.org](https://my.telegram.org).

## Transport

| `HEROKU_TRANSPORT` | When |
| --- | --- |
| `auto` (default) | WebSocket only when `SAND_EGRESS_TUNNEL_PROXY_ADDR` is set, or when `127.0.0.1:8791` accepts TCP. Otherwise direct TCP. |
| `ws` | Always `wss://<dc>.web.telegram.org/apiws`. Use this when the host can open HTTPS but the network drops raw DC TCP (`149.154.*`). Set `SAND_EGRESS_TUNNEL_PROXY_ADDR` (`host:port`, `http://…`, or `socks5://…`) when that WebSocket itself must go through an HTTP CONNECT or SOCKS proxy. |
| `tcp` | Always direct TCP. |

WebSocket keepalive pings every 20s so an idle proxy is less likely to drop the socket. A missing WebSocket pong does not close a live session. If a proxy still closes it, the client reconnects. A socket that dies in under 5 seconds backs off (1s, 2s, 4s, 8s, 16s). Longer drops, including an idle close, reconnect immediately. The inline bot uses the same transport and retries the same way, instead of stopping after a handful of failures.

## Docker

Build from this checkout. The Dockerfile copies the build context. It does not `git clone` another remote.

```bash
docker compose build
docker compose run --rm heroku
```

The first run is interactive (phone or QR, then 2FA). Session and config land in the `heroku-data` volume. After login the process restarts itself; start it in the background:

```bash
docker compose up -d
docker compose logs -f
```

Stop and start again with `docker compose restart`. Data survives recreate.

A second account is a second process and a second volume. Copy the service (different volume, optional different `HEROKU_TRANSPORT`) or run another compose project:

```bash
docker compose -p heroku-b run --rm heroku
docker compose -p heroku-b up -d
```

`.update` inside the container fetches `https://github.com/bertffff/Heroku` only. The image user is uid 1000, the checkout is writable by that user, and `pip` installs for that user go to `/home/heroku/.local` (already on `sys.path`). Rebuild the image when you want OS packages such as `ffmpeg` updated. Bind-mount a host directory instead of the named volume only after `chown 1000:1000` on that directory.

`docker.sh` clones this fork and then builds the same compose file.

## systemd (no Docker)

Install the checkout under `/opt/heroku`, with a virtualenv at `/opt/heroku/.venv`, owned by a `heroku` user. Data directory `/var/lib/heroku` mode `0700`. Example unit: [`heroku.service`](heroku.service).

```bash
sudo useradd --system --create-home --shell /usr/sbin/nologin heroku
sudo install -d -m 0700 -o heroku -g heroku /var/lib/heroku
sudo install -d -m 0750 -o root -g heroku /etc/heroku
sudo touch /etc/heroku/account.env
sudo chown root:heroku /etc/heroku/account.env
sudo chmod 0640 /etc/heroku/account.env
sudo cp docs/heroku.service /etc/systemd/system/heroku.service
sudo systemctl daemon-reload
sudo systemctl enable --now heroku
```

First login needs a TTY. Run once in the foreground as that user, then let systemd keep it up:

```bash
sudo -u heroku HEROKU_TRANSPORT=auto \
  /opt/heroku/.venv/bin/python -m heroku --data-root /var/lib/heroku
```

Another account: another data directory (`/var/lib/heroku-b`), another env file, and a second unit with its own `ExecStart` `--data-root`. Do not put two accounts in one process.

`.update` pulls this fork. `Restart=on-failure` brings the process back if it exits from a crash. `systemctl restart heroku` is the manual restart.
